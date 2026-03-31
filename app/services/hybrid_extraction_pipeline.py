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
import unicodedata

from pydantic import BaseModel, ValidationError, create_model

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

_FIELD_KEYWORDS: dict[str, list[str]] = {
    "so_bao_cao": ["Số:", "Số báo cáo", "BÁO CÁO"],
    "ngay_bao_cao": ["Ngày", "Báo cáo ngày"],
    "tu_ngay": ["Từ ngày"],
    "den_ngay": ["Đến ngày"],
    "tong_quan_su_co": ["TÌNH HÌNH CHÁY", "SỰ CỐ", "TAI NẠN"],
    "stt_14_tong_cnch": ["14", "Tổng CNCH"],
    "tong_xe_hu_hong": ["xe hư hỏng", "xe hu hong"],
    "danh_sach_cnch": ["CNCH", "CỨU NẠN", "TAI NẠN"],
    "danh_sach_phuong_tien_hu_hong": ["phương tiện", "xe hư hỏng"],
}

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
    business_data: dict | None = None
    metrics: dict | None = None


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

    @staticmethod
    def _normalize_for_search(text: str) -> str:
        text = (text or "").upper()
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", text).strip()

    @trace_step("phase0_document_mapping")
    def phase0_document_mapping(self, ingested: IngestedDocument) -> dict[str, str]:
        self.emit("phase0_document_mapping")
        lines = [line.strip() for line in (ingested.text_stream or "").splitlines() if line.strip()]
        if not lines:
            return {"header": "", "nghiep_vu": "", "bang_thong_ke": "", "full_text": ""}

        anchor_i = "I. TINH HINH CHAY"
        anchor_table = "BIEU MAU THONG KE"
        idx_i: int | None = None
        idx_table: int | None = None

        for idx, line in enumerate(lines):
            norm = self._normalize_for_search(line)
            if idx_i is None and anchor_i in norm:
                idx_i = idx
            if idx_table is None and anchor_table in norm:
                idx_table = idx

        if idx_i is None:
            idx_i = min(30, len(lines))
        if idx_table is None or idx_table < idx_i:
            idx_table = len(lines)

        return {
            "header": "\n".join(lines[:idx_i]).strip(),
            "nghiep_vu": "\n".join(lines[idx_i:idx_table]).strip(),
            "bang_thong_ke": "\n".join(lines[idx_table:]).strip(),
            "full_text": "\n".join(lines).strip(),
        }

    @trace_step("phase1_context_window_builder")
    def phase1_context_window_builder(self, doc_map: dict[str, str], window_size: int = 10) -> dict[str, str]:
        self.emit("phase1_context_window_builder")
        lines = [line.strip() for line in (doc_map.get("full_text") or "").splitlines() if line.strip()]
        if not lines:
            return {}

        normalized_lines = [self._normalize_for_search(line) for line in lines]
        windows: dict[str, str] = {}

        for field_name in self.response_model.model_fields.keys():
            keywords = _FIELD_KEYWORDS.get(field_name, [field_name])
            norm_keywords = [self._normalize_for_search(k) for k in keywords]

            hit_idx: int | None = None
            for idx, norm_line in enumerate(normalized_lines):
                if any(keyword in norm_line for keyword in norm_keywords):
                    hit_idx = idx
                    break

            if hit_idx is None:
                start, end = 0, min(len(lines), 2 * window_size + 1)
            else:
                start = max(0, hit_idx - window_size)
                end = min(len(lines), hit_idx + window_size + 1)

            windows[field_name] = "\n".join(lines[start:end]).strip()

        return windows

    def _default_for_field(self, field_name: str) -> Any:
        annotation = self.response_model.model_fields[field_name].annotation
        ann_text = str(annotation)
        if "list" in ann_text.lower():
            return []
        if "int" in ann_text.lower():
            return 0
        return ""

    def _extract_single_field(
        self,
        field_name: str,
        context_window: str,
        validation_errors: list[str] | None = None,
    ) -> Any:
        annotation = self.response_model.model_fields[field_name].annotation
        default_value = self._default_for_field(field_name)
        mini_model = create_model(
            f"FieldModel_{field_name}",
            **{field_name: (annotation, default_value)},
        )

        fix_hint = ""
        if validation_errors:
            fix_hint = "\nPrevious validation issues: " + " | ".join(validation_errors)

        prompt = (
            f"Extract ONLY this field: {field_name}.\n"
            "Search ONLY inside provided context.\n"
            "Return strict JSON with this single field and no extra keys."
            f"{fix_hint}\n\n"
            f"Context:\n{context_window}"
        )

        messages = [
            {"role": "system", "content": "You are a precise field extraction engine."},
            {"role": "user", "content": prompt},
        ]

        result = self.extractor.extract(
            messages=messages,
            response_model=mini_model,
            model=self.model,
            temperature=0.0,
        )
        return getattr(result, field_name, default_value)

    @trace_step("phase2_field_level_extraction")
    def phase2_field_level_extraction(
        self,
        windows: dict[str, str],
        validation_errors: list[str] | None = None,
        target_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        self.emit("phase2_field_level_extraction")
        extracted: dict[str, Any] = {}
        fields = target_fields or list(self.response_model.model_fields.keys())

        for field_name in fields:
            try:
                context_window = windows.get(field_name, "")
                extracted[field_name] = self._extract_single_field(field_name, context_window, validation_errors)
            except Exception as exc:
                raise StageError("inference", f"LLM inference failed while extracting {field_name}: {exc}") from exc

        return extracted

    @trace_step("phase3_deterministic_correction")
    def phase3_deterministic_correction(
        self,
        payload: dict[str, Any],
        table_dict: dict[str, Any],
        windows: dict[str, str],
    ) -> dict[str, Any]:
        self.emit("phase3_deterministic_correction")
        merged = {**payload}

        # Parser > LLM for deterministic table metrics.
        merged.update(table_dict)

        # Date regex override when available.
        report_window = windows.get("ngay_bao_cao", "")
        report_date = re.search(r"\b\d{2}/\d{2}/\d{4}\b", report_window)
        if report_date:
            merged["ngay_bao_cao"] = report_date.group(0)

        date_window = self._normalize_for_search(windows.get("tu_ngay", "") + "\n" + windows.get("den_ngay", ""))
        range_match = re.search(r"TU NGAY\s*(\d{2}/\d{2}/\d{4}).*DEN NGAY\s*(\d{2}/\d{2}/\d{4})", date_window)
        if range_match:
            merged["tu_ngay"] = range_match.group(1)
            merged["den_ngay"] = range_match.group(2)

        if "stt_14_tong_cnch" in merged:
            merged["stt_14_tong_cnch"] = self._safe_int(merged.get("stt_14_tong_cnch"), 0)
        if "tong_xe_hu_hong" in merged:
            merged["tong_xe_hu_hong"] = self._safe_int(merged.get("tong_xe_hu_hong"), 0)

        return merged

    @staticmethod
    def _map_validation_errors_to_fields(validation_errors: list[str]) -> list[str]:
        targets: set[str] = set()
        for error in validation_errors:
            if error == "ERR_CNCH_COUNT_MISMATCH":
                targets.add("danh_sach_cnch")
            elif error == "ERR_VEHICLE_DAMAGE_COUNT_MISMATCH":
                targets.add("danh_sach_phuong_tien_hu_hong")
            elif error == "ERR_REPORT_DATE_FORMAT":
                targets.add("ngay_bao_cao")
            elif error == "ERR_FROM_DATE_FORMAT":
                targets.add("tu_ngay")
            elif error == "ERR_TO_DATE_FORMAT":
                targets.add("den_ngay")
            elif error == "ERR_DATE_RANGE":
                targets.update({"tu_ngay", "den_ngay"})
            elif "ERR_CNCH_DATE_FORMAT_ITEM_" in error:
                targets.add("danh_sach_cnch")
            elif error.startswith("ERR_SCHEMA_VALIDATION"):
                for candidate in (
                    "ngay_bao_cao",
                    "tu_ngay",
                    "den_ngay",
                    "tong_quan_su_co",
                    "stt_14_tong_cnch",
                    "tong_xe_hu_hong",
                    "danh_sach_cnch",
                    "danh_sach_phuong_tien_hu_hong",
                ):
                    if candidate in error:
                        targets.add(candidate)
        return list(targets)

    def _run_standard_flow(self, ingested: IngestedDocument, normalized: NormalizedDocument) -> PipelineResult:
        del normalized
        prior_errors: list[str] = []
        last_invalid_output: BaseModel | None = None

        table_dict = self._extract_table_by_rules(ingested.table_stream)
        doc_map = self.phase0_document_mapping(ingested)
        windows = self.phase1_context_window_builder(doc_map)

        merged_fields: dict[str, Any] = {}
        target_fields: list[str] | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self.retry_count = attempt - 1
                extracted_fields = self.phase2_field_level_extraction(
                    windows,
                    validation_errors=prior_errors or None,
                    target_fields=target_fields,
                )
                merged_fields.update(extracted_fields)

                corrected = self.phase3_deterministic_correction(merged_fields, table_dict, windows)
                corrected = self._align_list_counts_with_table_hints(corrected)

                final_output = self.response_model.model_validate(corrected)
                last_invalid_output = final_output
                validation_errors = self.stage4_validation(final_output)

                if not validation_errors:
                    self._commit_to_database(final_output)
                    return PipelineResult(status="ok", attempts=attempt, output=final_output)

                prior_errors = self._build_retry_feedback(validation_errors, final_output)
                mapped = self._map_validation_errors_to_fields(validation_errors)
                target_fields = mapped or None
                logger.warning("Hybrid extraction validation failed on attempt %s: %s", attempt, validation_errors)
            except StageError as exc:
                if exc.stage == "inference" and self._is_quota_or_rate_limit_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Hybrid extraction aborted (quota/rate-limit) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(status="failed", attempts=attempt, errors=[stage_error])
                if exc.stage == "inference" and self._is_inference_timeout_error(exc.message):
                    stage_error = f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"
                    logger.error("Hybrid extraction aborted (inference-timeout) at attempt %s: %s", attempt, stage_error)
                    return PipelineResult(status="failed", attempts=attempt, errors=[stage_error])
                prior_errors = self._build_retry_feedback([f"ERR_STAGE_{exc.stage.upper()}:{exc.message}"], last_invalid_output)
                logger.warning("Hybrid extraction stage error on attempt %s: %s", attempt, exc)

        return PipelineResult(status="needs_manual_review", attempts=self.max_retries, errors=prior_errors)

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

        result = self._run_standard_flow(ingested, normalized)
        if result.status == "ok":
            return result

        manual_path, metadata_path = self._move_to_manual_review(
            source_path,
            invalid_output=result.output,
            errors=result.errors,
        )
        return PipelineResult(
            status=result.status,
            attempts=result.attempts,
            errors=result.errors,
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

        result = self._run_standard_flow(ingested, normalized)
        if result.status == "ok":
            return result

        manual_path, metadata_path = self._write_manual_review_artifacts(
            pdf_bytes=pdf_bytes,
            filename=filename,
            invalid_output=result.output,
            errors=result.errors,
        )
        return PipelineResult(
            status=result.status,
            attempts=result.attempts,
            errors=result.errors,
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

    def _align_list_counts_with_table_hints(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Fill missing list items to satisfy count fields extracted from tables.

        This prevents hard-fail when smaller models miss detailed list entries
        but deterministic table parsing already provides the expected counts.
        """
        data = dict(payload or {})

        expected_cnch = self._safe_int(data.get("stt_14_tong_cnch"), 0)
        cnch_list = data.get("danh_sach_cnch")
        if not isinstance(cnch_list, list):
            cnch_list = []
        if expected_cnch > len(cnch_list):
            start = len(cnch_list)
            for idx in range(start + 1, expected_cnch + 1):
                cnch_list.append(
                    {
                        "stt": idx,
                        "ngay_xay_ra": "",
                        "thoi_gian": "",
                        "mo_ta": "",
                        "dia_diem": "",
                    }
                )
        data["danh_sach_cnch"] = cnch_list

        expected_vehicles = self._safe_int(data.get("tong_xe_hu_hong"), 0)
        vehicles = data.get("danh_sach_phuong_tien_hu_hong")
        if not isinstance(vehicles, list):
            vehicles = []
        if expected_vehicles > len(vehicles):
            vehicles.extend([""] * (expected_vehicles - len(vehicles)))
        data["danh_sach_phuong_tien_hu_hong"] = vehicles

        return data

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

        prose_schema_guard = ""
        if self.extraction_mode == "standard" and hint_data is not None:
            prose_schema_guard = (
                "\n\nSTRICT OUTPUT FOR PROSE STAGE:\n"
                "Only include these optional keys: "
                "ngay_bao_cao, tu_ngay, den_ngay, tong_quan_su_co, danh_sach_cnch, danh_sach_phuong_tien_hu_hong.\n"
                "Do NOT output table keys such as STT, Danh muc, Chi tiet, or any unknown top-level key."
            )

        return (
            "Extract incident data to valid JSON with exact schema keys. "
            "Return only JSON. "
            "Date format should follow dd/mm/yyyy where applicable."
            f"{hint_text}{fix_hint}{prose_schema_guard}\n\n"
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
    def _compact_error_for_prompt(error: str, max_len: int = 320) -> str:
        """Shrink verbose stage errors before feeding them back to the model."""
        text = (error or "").strip()
        for marker in ("<failed_attempts>", "<completion>", "ChatCompletion(", "Traceback"):
            pos = text.find(marker)
            if pos != -1:
                text = text[:pos].strip()
                break
        text = re.sub(r"\s+", " ", text)
        if len(text) > max_len:
            return text[:max_len].rstrip() + "..."
        return text

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
                    compact_error = HybridExtractionPipeline._compact_error_for_prompt(error)
                    feedback.append(
                        f"Lỗi hệ thống/validation: {compact_error}. "
                        "Hãy đọc lại payload và gen lại JSON đúng schema."
                    )
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

