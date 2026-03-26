"""Hybrid extraction pipeline: pdfplumber + Python normalization + LLM.

4 stages (kill-chain style):
1) Ingest: split text/table streams using pdfplumber.
2) Normalize: clean text and flatten tables to key-value lines.
3) Inference: constrained JSON extraction with instructor + Ollama.
4) Validate & Retry: cross-check logic, retry up to max attempts,
   then move file to manual review folder.
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
from uuid import uuid4
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.tracing import trace_step
from app.services.extractor_strategies import BaseExtractor, OllamaInstructorExtractor
from app.services.rule_engine import RuleEngine
from app.schemas.hybrid_extraction_schema import HybridExtractionOutput, LLMVanXuoiOutput

logger = logging.getLogger(__name__)

_NOISE_PATTERNS = [
    re.compile(r"^CỘNG\s+HÒA\s+XÃ\s+HỘI", flags=re.IGNORECASE),
    re.compile(r"^Độc\s+lập\s*-\s*Tự\s+do\s*-\s*Hạnh\s+phúc", flags=re.IGNORECASE),
    re.compile(r"^Nơi nhận\s*:", flags=re.IGNORECASE),
    re.compile(r"^PC0?7\b", flags=re.IGNORECASE),
    re.compile(r"^Lưu\s*:\s*VT", flags=re.IGNORECASE),
    re.compile(r"^KT\.\s*ĐỘI TRƯỞNG", flags=re.IGNORECASE),
    re.compile(r"^PHÓ\s*ĐỘI\s*TRƯỞNG", flags=re.IGNORECASE),
]

@dataclass
class IngestedPage:
    """Raw extracted content from one PDF page."""

    page_number: int
    text: str
    tables: list[list[list[str]]] = field(default_factory=list)


@dataclass
class IngestedDocument:
    """Raw dual-stream extraction output."""

    pages: list[IngestedPage] = field(default_factory=list)
    text_stream: str = ""
    table_stream: list[list[list[str]]] = field(default_factory=list)


@dataclass
class NormalizedDocument:
    """Normalized text chunks prepared for LLM."""

    cleaned_text: str

    @property
    def clean_payload(self) -> str:
        anchor = "Dưới đây là thông tin báo cáo PCCC đã được chuẩn hóa. Tuyệt đối không tự suy diễn số liệu."
        return f"{anchor}\n\n{self.cleaned_text}".strip()

    @property
    def merged_prompt_context(self) -> str:
        return self.clean_payload


@dataclass
class PipelineResult:
    """Final result after validation/retry/manual-review routing."""

    status: str
    attempts: int
    output: BaseModel | None = None
    errors: list[str] = field(default_factory=list)
    manual_review_path: str | None = None
    manual_review_metadata_path: str | None = None


class StageError(Exception):
    """Raised when a specific stage fails hard."""

    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage
        self.message = message


class HybridExtractionPipeline:
    """4-stage extraction pipeline with deterministic guardrails."""

    def __init__(
        self,
        *,
        job_id: str | None = None,
        progress_callback: Callable[[str, str], Any] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_retries: int | None = None,
        manual_review_dir: str | Path | None = None,
        inference_func: Callable[..., BaseModel] | None = None,
        commit_func: Callable[[BaseModel], Any] | None = None,
        extractor: BaseExtractor | None = None,
        response_model: type[BaseModel] = HybridExtractionOutput,
        rule_engine: RuleEngine | None = None,
        extraction_mode: str = "standard",
        pdf_bytes: bytes | None = None,
    ) -> None:
        self.job_id = job_id
        self.trace_id = str(uuid4())
        self.retry_count = 0
        self.progress_callback = progress_callback
        self.model = model or settings.OLLAMA_MODEL
        self.temperature = temperature
        self.max_retries = max_retries if max_retries is not None else settings.HYBRID_MAX_RETRIES
        self.manual_review_dir = Path(manual_review_dir or settings.HYBRID_MANUAL_REVIEW_DIR)
        self._inference_func = inference_func
        self._commit_func = commit_func
        self.response_model = response_model
        self.rule_engine = rule_engine
        self.extraction_mode = extraction_mode
        self.pdf_bytes = pdf_bytes
        self.extractor = extractor or OllamaInstructorExtractor(
            base_url=settings.OLLAMA_BASE_URL,
            api_key=settings.OLLAMA_API_KEY,
            timeout_seconds=settings.OLLAMA_TIMEOUT_SECONDS,
            log_raw_pre_validate=settings.OLLAMA_LOG_RAW_PRE_VALIDATE,
            raw_preview_chars=settings.OLLAMA_RAW_PREVIEW_CHARS,
        )

    def emit(self, step_name: str) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(step_name, self.trace_id)
        except Exception:
            logger.warning("progress_callback failed for step '%s'", step_name, exc_info=True)

    # Stage 1
    @trace_step("stage1_ingest")
    def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:
        """Extract text and tables as two independent streams using pdfplumber."""
        self.emit("stage1_ingest")
        try:
            import pdfplumber
        except ImportError as exc:
            raise StageError("ingest", "pdfplumber is not installed") from exc

        pages: list[IngestedPage] = []
        text_stream_parts: list[str] = []
        table_stream: list[list[list[str]]] = []

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for index, page in enumerate(pdf.pages, start=1):
                    text_stream = page.extract_text() or ""
                    raw_tables = page.extract_tables() or []
                    text_stream_parts.append(text_stream)

                    normalized_tables: list[list[list[str]]] = []
                    for table in raw_tables:
                        if not table:
                            continue
                        rows: list[list[str]] = []
                        for row in table:
                            clean_cells = [self._clean_cell(cell) for cell in (row or [])]
                            if any(cell for cell in clean_cells):
                                rows.append(clean_cells)
                        if rows:
                            normalized_tables.append(rows)
                            table_stream.append(rows)

                    pages.append(
                        IngestedPage(
                            page_number=index,
                            text=text_stream,
                            tables=normalized_tables,
                        )
                    )
        except Exception as exc:
            raise StageError("ingest", f"pdfplumber failed: {exc}") from exc

        full_text_stream = "\n".join(text_stream_parts)
        self._assert_non_empty_text_stream(full_text_stream)

        return IngestedDocument(
            pages=pages,
            text_stream=full_text_stream,
            table_stream=table_stream,
        )

    # Stage 2
    @trace_step("stage2_normalize")
    def stage2_normalize(self, ingested: IngestedDocument) -> NormalizedDocument:
        """Clean narrative text for LLM prompt construction."""
        self.emit("stage2_normalize")
        try:
            all_text = (ingested.text_stream or "").strip()
            if not all_text:
                all_text = "\n".join(page.text for page in ingested.pages if page.text).strip()
            cleaned_text = self._cleanup_text(all_text)

            return NormalizedDocument(
                cleaned_text=cleaned_text,
            )
        except Exception as exc:
            raise StageError("normalize", f"normalization failed: {exc}") from exc

    # Stage 3
    @trace_step("stage3_inference")
    def stage3_inference(
        self,
        normalized: NormalizedDocument | None,
        validation_errors: list[str] | None = None,
        hint_data: dict[str, Any] | None = None,
    ) -> BaseModel:
        """Run constrained decoding via injected extraction strategy."""
        self.emit("stage3_inference")
        prompt = self._build_prompt(normalized, validation_errors, hint_data)
        if self.extraction_mode == "vision" or hint_data is None:
            inference_schema: type[BaseModel] = self.response_model
        elif self.extraction_mode == "standard" and hint_data is not None:
            inference_schema = LLMVanXuoiOutput
        else:
            inference_schema = self.response_model

        try:
            if self._inference_func:
                try:
                    raw_output = self._inference_func(prompt, validation_errors, hint_data)
                except TypeError:
                    raw_output = self._inference_func(prompt, validation_errors)
                if isinstance(raw_output, inference_schema):
                    return raw_output
                if isinstance(raw_output, BaseModel):
                    return inference_schema.model_validate(raw_output.model_dump())
                return inference_schema.model_validate(raw_output)

            messages = self._build_inference_messages(prompt)
            
            # For vision mode with PDF bytes, pass them to the extractor
            if self.extraction_mode == "vision" and self.pdf_bytes:
                return self.extractor.extract(
                    messages=messages,
                    response_model=inference_schema,
                    model=self.model,
                    temperature=self.temperature,
                    pdf_bytes=self.pdf_bytes,
                )
            else:
                return self.extractor.extract(
                    messages=messages,
                    response_model=inference_schema,
                    model=self.model,
                    temperature=self.temperature,
                )
        except Exception as exc:
            raise StageError("inference", f"LLM inference failed: {exc}") from exc

    def stage3_infer(
        self,
        normalized: NormalizedDocument | None,
        validation_errors: list[str] | None = None,
        hint_data: dict[str, Any] | None = None,
    ) -> BaseModel:
        """Backward-compatible alias for stage3_inference."""
        return self.stage3_inference(normalized, validation_errors, hint_data)

    def _invoke_stage3_infer(
        self,
        normalized: NormalizedDocument | None,
        validation_errors: list[str] | None,
        hint_data: dict[str, Any] | None = None,
    ) -> BaseModel:
        """Call stage3 with backward compatibility for overrides lacking hint_data."""
        try:
            return self.stage3_infer(
                normalized,
                validation_errors,
                hint_data=hint_data,
            )
        except TypeError as exc:
            if "hint_data" not in str(exc):
                raise
            return self.stage3_infer(normalized, validation_errors)

    # Stage 4
    @trace_step("stage4_validation")
    def stage4_validation(self, output: BaseModel) -> list[str]:
        """Validate schema shape and optional injected domain rules.

        Returns:
            List of machine-readable error codes. Empty list = pass.
        """
        payload_data = output.model_dump() if isinstance(output, BaseModel) else output

        try:
            validated_payload = self.response_model.model_validate(payload_data)
        except ValidationError as exc:
            return [f"ERR_SCHEMA_VALIDATION:{err.get('loc')}:{err.get('msg')}" for err in exc.errors()]

        if self.rule_engine is None:
            return []
        return self.rule_engine.validate(validated_payload)

    def stage4_validate(self, output: BaseModel) -> list[str]:
        """Backward-compatible alias for stage4_validation."""
        return self.stage4_validation(output)

    @staticmethod
    def _is_quota_or_rate_limit_error(message: str) -> bool:
        text = (message or "").lower()
        markers = [
            "resource_exhausted",
            "quota exceeded",
            "rate limit",
            "too many requests",
            " 429 ",
            "code': 429",
            "code\": 429",
            "generativelanguage.googleapis.com/generate_content_free_tier",
        ]
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_inference_timeout_error(message: str) -> bool:
        text = (message or "").lower()
        markers = [
            "request timed out",
            "read timed out",
            "timed out",
            "timeout",
        ]
        return any(marker in text for marker in markers)

    def run(self, pdf_path: str | Path) -> PipelineResult:
        """Execute full 4-stage kill-chain with retry and manual-review fallback."""
        source_path = Path(pdf_path)
        if not source_path.exists() or source_path.suffix.lower() != ".pdf":
            return PipelineResult(
                status="failed",
                attempts=0,
                errors=["ERR_INVALID_INPUT_FILE"],
            )

        try:
            pdf_bytes = source_path.read_bytes()
        except Exception as exc:
            return PipelineResult(
                status="failed",
                attempts=0,
                errors=[f"ERR_READ_FILE:{exc}"],
            )

        try:
            ingested = self.stage1_ingest(pdf_bytes)
            self._assert_non_empty_text_stream(ingested.text_stream or "")
            normalized = self.stage2_normalize(ingested)
        except StageError as exc:
            return PipelineResult(
                status="failed",
                attempts=0,
                errors=[f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"],
            )

        prior_errors: list[str] = []
        last_invalid_output: BaseModel | None = None
        table_dict = self._extract_table_by_rules(ingested.table_stream)

        for attempt in range(1, self.max_retries + 1):
            try:
                self.retry_count = attempt - 1
                llm_output = self._invoke_stage3_infer(
                    normalized,
                    prior_errors or None,
                    hint_data=table_dict,
                )
                llm_dict = llm_output.model_dump(exclude_none=True) if isinstance(llm_output, BaseModel) else {}
                final_dict = {**table_dict, **llm_dict}
                final_output = self.response_model.model_validate(final_dict)
                last_invalid_output = final_output
                validation_errors = self.stage4_validation(final_output)

                if not validation_errors:
                    self._commit_to_database(final_output)
                    return PipelineResult(
                        status="ok",
                        attempts=attempt,
                        output=final_output,
                    )

                prior_errors = self._build_retry_feedback(validation_errors, final_output)
                logger.warning("Hybrid extraction validation failed on attempt %s: %s", attempt, validation_errors)
            except StageError as exc:
                if exc.stage == "inference" and self._is_quota_or_rate_limit_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Hybrid extraction aborted (quota/rate-limit) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(
                        status="failed",
                        attempts=attempt,
                        errors=[stage_error],
                    )
                if exc.stage == "inference" and self._is_inference_timeout_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Hybrid extraction aborted (inference-timeout) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(
                        status="failed",
                        attempts=attempt,
                        errors=[stage_error],
                    )
                prior_errors = self._build_retry_feedback([f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"], last_invalid_output)
                logger.warning("Hybrid extraction stage error on attempt %s: %s", attempt, exc)

        manual_path, metadata_path = self._move_to_manual_review(
            source_path,
            invalid_output=last_invalid_output,
            errors=prior_errors,
        )
        return PipelineResult(
            status="needs_manual_review",
            attempts=self.max_retries,
            errors=prior_errors,
            manual_review_path=str(manual_path),
            manual_review_metadata_path=str(metadata_path) if metadata_path else None,
        )

    def run_from_bytes(self, pdf_bytes: bytes, filename: str) -> PipelineResult:
        """Execute pipeline directly from in-memory bytes (S3/upload)."""
        # For vision mode, skip text extraction stages and go directly to inference
        if self.extraction_mode == "vision":
            return self._run_vision_mode(pdf_bytes, filename)
        
        # Standard mode: extract text using pdfplumber
        try:
            ingested = self.stage1_ingest(pdf_bytes)
            self._assert_non_empty_text_stream(ingested.text_stream or "")
            normalized = self.stage2_normalize(ingested)
        except StageError as exc:
            return PipelineResult(
                status="failed",
                attempts=0,
                errors=[f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"],
            )

        prior_errors: list[str] = []
        last_invalid_output: BaseModel | None = None
        table_dict = self._extract_table_by_rules(ingested.table_stream)

        for attempt in range(1, self.max_retries + 1):
            try:
                self.retry_count = attempt - 1
                llm_output = self._invoke_stage3_infer(
                    normalized,
                    prior_errors or None,
                    hint_data=table_dict,
                )
                llm_dict = llm_output.model_dump(exclude_none=True) if isinstance(llm_output, BaseModel) else {}
                final_dict = {**table_dict, **llm_dict}
                final_output = self.response_model.model_validate(final_dict)
                last_invalid_output = final_output
                validation_errors = self.stage4_validation(final_output)

                if not validation_errors:
                    self._commit_to_database(final_output)
                    return PipelineResult(
                        status="ok",
                        attempts=attempt,
                        output=final_output,
                    )

                prior_errors = self._build_retry_feedback(validation_errors, final_output)
                logger.warning("Hybrid extraction validation failed on attempt %s: %s", attempt, validation_errors)
            except StageError as exc:
                if exc.stage == "inference" and self._is_quota_or_rate_limit_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Hybrid extraction aborted (quota/rate-limit) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(
                        status="failed",
                        attempts=attempt,
                        errors=[stage_error],
                    )
                if exc.stage == "inference" and self._is_inference_timeout_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Hybrid extraction aborted (inference-timeout) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(
                        status="failed",
                        attempts=attempt,
                        errors=[stage_error],
                    )
                prior_errors = self._build_retry_feedback([f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"], last_invalid_output)
                logger.warning("Hybrid extraction stage error on attempt %s: %s", attempt, exc)

        manual_path, metadata_path = self._write_manual_review_artifacts(
            pdf_bytes=pdf_bytes,
            filename=filename,
            invalid_output=last_invalid_output,
            errors=prior_errors,
        )
        return PipelineResult(
            status="needs_manual_review",
            attempts=self.max_retries,
            errors=prior_errors,
            manual_review_path=str(manual_path),
            manual_review_metadata_path=str(metadata_path) if metadata_path else None,
        )

    @staticmethod
    def _clean_cell(value: object) -> str:
        text = "" if value is None else str(value)
        return re.sub(r"\s+", " ", text).strip()

    def _cleanup_text(self, raw_text: str) -> str:
        lines = [line.strip() for line in raw_text.splitlines()]
        lines = [line for line in lines if line]

        filtered_lines = [
            line
            for line in lines
            if not any(pattern.search(line) for pattern in _NOISE_PATTERNS)
        ]

        if not filtered_lines:
            return ""

        normalized_lines: list[str] = []
        current = filtered_lines[0]

        for next_line in filtered_lines[1:]:
            last_char = current.rstrip()[-1] if current.rstrip() else ""
            if last_char in {".", ":", ";"}:
                normalized_lines.append(current)
                current = next_line
            else:
                current = f"{current} {next_line}".strip()

        normalized_lines.append(current)
        text = "\n".join(normalized_lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        if value is None:
            return default
        text = str(value).strip().replace(",", "")
        if not text:
            return default
        match = re.search(r"-?\d+", text)
        if not match:
            return default
        try:
            return int(match.group(0))
        except ValueError:
            return default

    def _extract_table_by_rules(self, table_stream: list[list[list[str]]]) -> dict[str, Any]:
        """Deterministic extraction for strongly-structured table metrics."""
        result: dict[str, Any] = {}

        known_fields = set(self.response_model.model_fields.keys())
        stt_to_schema_field = {
            "14": "stt_14_tong_cnch",
        }
        metric_keyword_to_field = {
            "tong_xe_hu_hong": ["xe hư hỏng", "xe hu hong"],
        }

        for field_name in set(stt_to_schema_field.values()) | set(metric_keyword_to_field.keys()):
            if field_name in known_fields:
                result[field_name] = 0

        tables = table_stream or []
        for table in tables:
            for row in table:
                cleaned_row = [self._clean_cell(cell) for cell in (row or [])]
                cells = [cell for cell in cleaned_row if cell]
                if len(cells) < 3:
                    continue

                stt_value = cleaned_row[0] if len(cleaned_row) > 0 else ""
                metric = cleaned_row[1] if len(cleaned_row) > 1 else ""
                value = cleaned_row[2] if len(cleaned_row) > 2 else ""
                if not value and len(cleaned_row) > 3:
                    value = cleaned_row[3]

                metric_lower = metric.lower()
                stt_digits = re.search(r"\d+", stt_value or "")
                stt_norm = stt_digits.group(0) if stt_digits else ""

                mapped_field = stt_to_schema_field.get(stt_norm)
                if mapped_field and mapped_field in known_fields:
                    result[mapped_field] = self._safe_int(value)

                for field_name, keywords in metric_keyword_to_field.items():
                    if field_name not in known_fields:
                        continue
                    if any(keyword in metric_lower for keyword in keywords):
                        result[field_name] = self._safe_int(value)

        return result

    def _build_prompt(
        self,
        normalized: NormalizedDocument | None,
        validation_errors: list[str] | None,
        hint_data: dict[str, Any] | None = None,
    ) -> str:
        fix_hint = ""
        if validation_errors:
            fix_hint = (
                "\nValidation errors from previous attempt: "
                + ", ".join(validation_errors)
                + "\nPlease fix these violations in this attempt."
            )

        hint_text = ""
        if hint_data:
            expected_incidents = self._safe_int(hint_data.get("stt_14_tong_cnch"), 0)
            hint_text = (
                "\nLƯU Ý: "
                f"Theo số liệu bảng, có {expected_incidents} vụ tai nạn/sự cố. "
                "Hãy trích xuất chi tiết cho khớp."
            )

        # Vision mode: no text extraction, just basic prompt
        if normalized is None:
            return (
                "Analyze this PDF document and extract incident data to valid JSON with exact schema keys. "
                "Return only JSON. "
                "Date format should follow dd/mm/yyyy where applicable."
                f"{hint_text}{fix_hint}"
            )

        return (
            "Extract incident data to valid JSON with exact schema keys. "
            "Return only JSON. "
            "Date format should follow dd/mm/yyyy where applicable."
            f"{hint_text}{fix_hint}\n\n"
            f"Document:\n{normalized.merged_prompt_context}"
        )

    def _infer_with_instructor(self, prompt: str) -> BaseModel:
        messages = self._build_inference_messages(prompt)
        return self.extractor.extract(
            messages=messages,
            response_model=self.response_model,
            model=self.model,
            temperature=self.temperature,
        )

    def _move_to_manual_review(
        self,
        source_path: Path,
        invalid_output: BaseModel | None = None,
        errors: list[str] | None = None,
    ) -> tuple[Path, Path | None]:
        self.manual_review_dir.mkdir(parents=True, exist_ok=True)
        destination = self.manual_review_dir / source_path.name
        shutil.move(str(source_path), str(destination))

        metadata_path: Path | None = None
        if invalid_output is not None or errors:
            metadata_path = self.manual_review_dir / f"{source_path.stem}.review.json"
            metadata = {
                "source_pdf": destination.name,
                "errors": errors or [],
                "invalid_output": invalid_output.model_dump() if invalid_output else None,
            }
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return destination, metadata_path

    def _write_manual_review_artifacts(
        self,
        *,
        pdf_bytes: bytes,
        filename: str,
        invalid_output: BaseModel | None = None,
        errors: list[str] | None = None,
    ) -> tuple[Path, Path | None]:
        safe_name = Path(filename).name or "manual_review.pdf"
        if not safe_name.lower().endswith(".pdf"):
            safe_name = f"{safe_name}.pdf"

        self.manual_review_dir.mkdir(parents=True, exist_ok=True)
        destination = self.manual_review_dir / safe_name
        destination.write_bytes(pdf_bytes)

        metadata_path: Path | None = None
        if invalid_output is not None or errors:
            metadata_path = self.manual_review_dir / f"{destination.stem}.review.json"
            metadata = {
                "source_pdf": destination.name,
                "errors": errors or [],
                "invalid_output": invalid_output.model_dump() if invalid_output else None,
            }
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return destination, metadata_path

    def _build_inference_messages(self, prompt: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._build_stage3_system_prompt()},
            {"role": "user", "content": prompt},
        ]

    @staticmethod
    def _build_stage3_system_prompt() -> str:
        return (
            "Mày là cỗ máy trích xuất dữ liệu. Chỉ trích xuất từ văn bản được cung cấp. "
            "Tuyệt đối không suy đoán. "
            "Nếu không có thông tin, điền 0 với số, mảng rỗng [] với danh sách, "
            "hoặc chuỗi rỗng '' với văn bản. "
            "Trả về đúng schema JSON, không dư key, không thiếu key, không markdown."
        )

    @staticmethod
    def _assert_non_empty_text_stream(text_stream: str) -> None:
        if len((text_stream or "").strip()) == 0:
            logger.warning("Phát hiện PDF dạng Scan. Từ chối xử lý bằng pdfplumber")
            raise StageError("ingest", "Phát hiện PDF dạng Scan. Từ chối xử lý bằng pdfplumber")

    @staticmethod
    def _build_retry_feedback(
        validation_errors: list[str],
        output: BaseModel | None,
    ) -> list[str]:
        if not validation_errors:
            return []

        feedback: list[str] = []
        for error in validation_errors:
            if error == "ERR_CNCH_COUNT_MISMATCH" and output is not None:
                total_cnch = getattr(output, "stt_14_tong_cnch", "?")
                list_cnch = getattr(output, "danh_sach_cnch", [])
                feedback.append(
                    "Mày đã trích xuất stt_14_tong_cnch = "
                    f"{total_cnch}, nhưng danh_sach_cnch có {len(list_cnch) if isinstance(list_cnch, list) else '?'} phần tử. "
                    "Hãy đọc lại văn bản và sửa cho khớp tuyệt đối."
                )
            elif error == "ERR_VEHICLE_DAMAGE_COUNT_MISMATCH" and output is not None:
                total_vehicles = getattr(output, "tong_xe_hu_hong", "?")
                list_vehicles = getattr(output, "danh_sach_phuong_tien_hu_hong", [])
                feedback.append(
                    "Mày đã trích xuất tong_xe_hu_hong = "
                    f"{total_vehicles}, nhưng danh_sach_phuong_tien_hu_hong có "
                    f"{len(list_vehicles) if isinstance(list_vehicles, list) else '?'} phần tử. Hãy sửa lại cho đúng."
                )
            elif error == "ERR_DATE_RANGE":
                feedback.append("tu_ngay đang lớn hơn den_ngay. Hãy đọc lại mốc thời gian và gen lại đúng logic.")
            elif "ERR_CNCH_DATE_FORMAT_ITEM_" in error:
                feedback.append("Một mục CNCH có ngày sai định dạng dd/mm/yyyy. Hãy chuẩn hóa lại.")
            elif error in {"ERR_REPORT_DATE_FORMAT", "ERR_FROM_DATE_FORMAT", "ERR_TO_DATE_FORMAT"}:
                feedback.append("Ngày tháng phải theo định dạng dd/mm/yyyy. Hãy sửa lại toàn bộ trường ngày.")
            elif error.startswith("ERR_STAGE_"):
                error_lower = error.lower()
                if (
                    "resource_exhausted" in error_lower
                    or "quota exceeded" in error_lower
                    or "rate limit" in error_lower
                    or " 429 " in error_lower
                    or "code': 429" in error_lower
                    or "code\": 429" in error_lower
                ):
                    feedback.append(
                        "Gemini quota/rate-limit đã vượt ngưỡng (429 RESOURCE_EXHAUSTED). "
                        "Dừng retry tự động; hãy đổi model/API key hoặc chờ reset quota rồi chạy lại."
                    )
                else:
                    feedback.append(f"Lỗi hệ thống/validation: {error}. Hãy đọc lại payload và gen lại JSON đúng schema.")
            else:
                feedback.append(f"Validation error: {error}. Hãy sửa và gen lại.")

        return feedback

    def _run_vision_mode(self, pdf_bytes: bytes, filename: str) -> PipelineResult:
        """Vision mode: send PDF directly to Gemini without text extraction."""
        prior_errors: list[str] = []
        last_invalid_output: BaseModel | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self.retry_count = attempt - 1
                # In vision mode, we pass PDF bytes directly without text extraction
                output = self._invoke_stage3_infer(None, prior_errors or None)
                last_invalid_output = output
                validation_errors = self.stage4_validation(output)

                if not validation_errors:
                    self._commit_to_database(output)
                    return PipelineResult(
                        status="ok",
                        attempts=attempt,
                        output=output,
                    )

                prior_errors = self._build_retry_feedback(validation_errors, output)
                logger.warning("Vision extraction validation failed on attempt %s: %s", attempt, validation_errors)
            except StageError as exc:
                if exc.stage == "inference" and self._is_quota_or_rate_limit_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Vision extraction aborted (quota/rate-limit) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(
                        status="failed",
                        attempts=attempt,
                        errors=[stage_error],
                    )
                if exc.stage == "inference" and self._is_inference_timeout_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Vision extraction aborted (inference-timeout) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(
                        status="failed",
                        attempts=attempt,
                        errors=[stage_error],
                    )
                prior_errors = self._build_retry_feedback([f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"], last_invalid_output)
                logger.warning("Vision extraction stage error on attempt %s: %s", attempt, exc)

        # All retries exhausted
        manual_path, metadata_path = self._write_manual_review_artifacts(
            pdf_bytes=pdf_bytes,
            filename=filename,
            invalid_output=last_invalid_output,
            errors=prior_errors,
        )
        return PipelineResult(
            status="needs_manual_review",
            attempts=self.max_retries,
            errors=prior_errors,
            manual_review_path=str(manual_path),
            manual_review_metadata_path=str(metadata_path) if metadata_path else None,
        )

    def _commit_to_database(self, output: BaseModel) -> None:
        if self._commit_func is None:
            return
        try:
            self._commit_func(output)
            logger.info("Hybrid extraction committed to database successfully")
        except Exception as exc:
            raise StageError("commit", f"DB commit failed: {exc}") from exc

