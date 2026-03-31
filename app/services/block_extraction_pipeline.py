"""Block-based extraction pipeline using a parser-first 5-stage pattern.

All document-specific patterns, keywords and prompts are loaded from a YAML
template (see ``app/templates/``).  The pipeline itself is generic.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from uuid import uuid4
from typing import Any, Callable

from pydantic import BaseModel, create_model

from app.core.config import settings
from app.core.metrics import PipelineMetrics, global_metrics
from app.core.tracing import trace_step
from app.schemas.hybrid_extraction_schema import (
    BlockBangThongKe,
    BlockExtractionOutput,
    BlockHeader,
    ChiTieu,
    BlockNghiepVu,
)
from app.business.engine import run_business_rules
from app.business.template_loader import DocumentTemplate, get_default_template
from app.services.extractor_strategies import OllamaInstructorExtractor
from app.services.hybrid_extraction_pipeline import PipelineResult

logger = logging.getLogger(__name__)


class BlockExtractionPipeline:
    """5-stage IDP extraction: layout -> block detect -> extract -> enforce -> validate."""

    def __init__(
        self,
        job_id: str | None = None,
        progress_callback: Callable[[str, str], Any] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        template: DocumentTemplate | None = None,
    ) -> None:
        self.job_id = job_id
        self.trace_id = str(uuid4())
        self.retry_count = 0
        self.progress_callback = progress_callback
        self.model = model or settings.OLLAMA_MODEL
        self.temperature = temperature
        self.tpl = template or get_default_template()
        self.metrics = PipelineMetrics()
        self.extractor = OllamaInstructorExtractor(
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

    @staticmethod
    def _normalize(text: str) -> str:
        text = (text or "").upper()
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _smart_join(prev: dict[str, Any], curr: dict[str, Any], threshold: float = 2.0) -> str:
        prev_text = (prev.get("text") or "").strip()
        curr_text = (curr.get("text") or "").strip()
        if not prev_text:
            return curr_text
        gap = float(curr.get("x0", 0.0)) - float(prev.get("x1", 0.0))
        return (" " + curr_text) if gap > threshold else curr_text

    @trace_step("block_stage1_layout_reconstruction")
    def _rebuild_layout(self, pdf_bytes: bytes) -> tuple[str, list[list[list[str]]]]:
        self.emit("block_stage1_layout_reconstruction")
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("pdfplumber is not installed") from exc

        pages_text: list[str] = []
        table_stream: list[list[list[str]]] = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                words = page.extract_words(use_text_flow=True) or []
                words = sorted(
                    words,
                    key=lambda w: (
                        round(float(w.get("top", 0.0)), 1),
                        float(w.get("x0", 0.0)),
                    ),
                )

                left_line_tokens: list[dict[str, Any]] = []
                right_line_tokens: list[dict[str, Any]] = []
                mid = float(page.width) / 2.0 if page.width else 0.0

                for w in words:
                    token = (w.get("text") or "").strip()
                    if not token:
                        continue
                    if float(w.get("x0", 0.0)) < mid:
                        left_line_tokens.append(w)
                    else:
                        right_line_tokens.append(w)

                def build_text_from_tokens(tokens: list[dict[str, Any]]) -> list[str]:
                    if not tokens:
                        return []
                    rows: dict[float, list[dict[str, Any]]] = {}
                    for token in tokens:
                        row_key = round(float(token.get("top", 0.0)), 1)
                        rows.setdefault(row_key, []).append(token)

                    built_lines: list[str] = []
                    for _, row_tokens in sorted(rows.items(), key=lambda item: item[0]):
                        row_tokens = sorted(row_tokens, key=lambda t: float(t.get("x0", 0.0)))
                        if not row_tokens:
                            continue
                        line = (row_tokens[0].get("text") or "").strip()
                        for idx in range(1, len(row_tokens)):
                            line += self._smart_join(row_tokens[idx - 1], row_tokens[idx])
                        if line.strip():
                            built_lines.append(line.strip())
                    return built_lines

                left_lines = build_text_from_tokens(left_line_tokens)
                right_lines = build_text_from_tokens(right_line_tokens)

                page_text = "\n".join(left_lines + right_lines).strip()
                if page_text:
                    pages_text.append(page_text)

                raw_tables = page.extract_tables() or []
                for table in raw_tables:
                    if not table:
                        continue
                    normalized_rows: list[list[str]] = []
                    for row in table:
                        cells = [str(cell).strip() if cell is not None else "" for cell in row]
                        if any(cells):
                            normalized_rows.append(cells)
                    if normalized_rows:
                        table_stream.append(normalized_rows)

        full_text = "\n".join(pages_text)
        # Restore common missing spaces between text <-> number boundaries.
        full_text = re.sub(r"([A-Za-zÀ-ỹ])([0-9])", r"\1 \2", full_text)
        full_text = re.sub(r"([0-9])([A-Za-zÀ-ỹ])", r"\1 \2", full_text)
        # Vietnamese lowercase→uppercase spacing fix (from testdoc flow).
        full_text = re.sub(
            r"([a-zàáạảãăắằẵặẳâấầẫậẩđèéẹẻẽêếềễệểìíịỉĩòóọỏõôốồỗộổơớờỡợởùúụủũưứừữựửỳýỵỷỹ])([A-Z])",
            r"\1 \2",
            full_text,
        )

        logger.info("TABLE COUNT = %s", len(table_stream))
        logger.info("Block stage1 done: chars=%s tables=%s", len(full_text), len(table_stream))
        return full_text, table_stream

    @trace_step("block_stage2_detect_blocks")
    def _detect_blocks(self, content: str) -> dict[str, str]:
        self.emit("block_stage2_detect_blocks")
        blocks = {"header": "", "phan_nghiep_vu": "", "bang_thong_ke": ""}
        lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
        if not lines:
            return blocks

        narrative_start_re = self.tpl.narrative_start_re
        table_anchor_re = self.tpl.table_anchor_re

        narrative_start: int | None = None
        table_start: int | None = None

        for idx, line in enumerate(lines):
            nline = self._normalize(line)
            if narrative_start is None and narrative_start_re.search(nline):
                narrative_start = idx
            if table_start is None and table_anchor_re.search(nline):
                table_start = idx

        if narrative_start is None:
            narrative_start = min(self.tpl.narrative_start_fallback_lines, len(lines))
        if table_start is None or table_start < narrative_start:
            table_start = len(lines)

        blocks["header"] = "\n".join(lines[:narrative_start]).strip()
        blocks["phan_nghiep_vu"] = "\n".join(lines[narrative_start:table_start]).strip()
        blocks["bang_thong_ke"] = "\n".join(lines[table_start:]).strip()

        logger.info(
            "Block stage2 done: header=%s lines, narrative=%s lines, table=%s lines",
            len(blocks["header"].splitlines()) if blocks["header"] else 0,
            len(blocks["phan_nghiep_vu"].splitlines()) if blocks["phan_nghiep_vu"] else 0,
            len(blocks["bang_thong_ke"].splitlines()) if blocks["bang_thong_ke"] else 0,
        )
        return blocks

    @trace_step("block_extract_block")
    def _extract_block(self, block_text: str, schema: type[BaseModel], block_name: str) -> BaseModel:
        self.emit(f"block_extract_{block_name}")
        if not block_text:
            return schema()

        messages = [
            {
                "role": "system",
                "content": self.tpl.extraction_prompt(block_name),
            },
            {"role": "user", "content": f"Dữ liệu {block_name}:\n{block_text}"},
        ]

        try:
            self.metrics.inc("llm_calls")
            result = self.extractor.extract(
                messages=messages,
                response_model=schema,
                model=self.model,
                temperature=self.temperature,
            )
            return result
        except Exception as exc:
            self.metrics.inc("llm_extract_fallback")
            # Local models can return truncated JSON for long table blocks.
            # Fall back to deterministic line parsing instead of failing the whole job.
            if schema is BlockNghiepVu:
                logger.warning(
                    "Block narrative extraction fallback activated due to LLM parse error: %s",
                    exc,
                )
                return self._parse_phan_nghiep_vu_fallback(block_text)
            if schema is BlockBangThongKe:
                logger.warning(
                    "Block table extraction fallback activated due to LLM parse error: %s",
                    exc,
                )
                return self._parse_bang_thong_ke_fallback(block_text)
            raise

    @trace_step("block_stage3_header_agent")
    def _extract_header(self, header_text: str) -> BlockHeader:
        self.emit("block_stage3_header_agent")
        max_lines = self.tpl.header_max_lines
        first_n = "\n".join([line for line in header_text.splitlines() if line.strip()][:max_lines])

        # Normalize spaced slash-dates produced by the spacing fix: "21 / 03 / 2026" → "21/03/2026"
        first_n_norm = re.sub(r"(\d{1,2})\s*/\s*(\d{2})\s*/\s*(\d{4})", r"\1/\2/\3", first_n)

        deterministic_date = ""

        # 1st priority: long-form date (e.g. "ngày 21 tháng 03 năm 2026")
        date_match = self.tpl.date_long_form_re.search(first_n_norm)
        if date_match:
            deterministic_date = f"{int(date_match.group(1)):02d}/{int(date_match.group(2)):02d}/{date_match.group(3)}"

        # 2nd priority: short-form date on a non-period line
        if not deterministic_date:
            period_markers = self.tpl.date_period_markers
            for line in first_n_norm.splitlines():
                if any(marker in line for marker in period_markers):
                    continue
                m = self.tpl.date_short_form_re.search(line)
                if m:
                    parts = m.group(1).split("/")
                    deterministic_date = f"{int(parts[0]):02d}/{parts[1]}/{parts[2]}"
                    break

        with self.metrics.timer("stage3_header_llm"):
            extracted = self._extract_block(first_n, BlockHeader, "Header")
        if deterministic_date:
            extracted.ngay_bao_cao = deterministic_date
        return extracted

    @trace_step("block_stage3_narrative_agent")
    def _extract_narrative(self, narrative_text: str) -> BlockNghiepVu:
        self.emit("block_stage3_narrative_agent")
        return self._extract_block(narrative_text, BlockNghiepVu, "Phần Nghiệp Vụ")

    def _parse_phan_nghiep_vu_fallback(self, text: str) -> BlockNghiepVu:
        self.metrics.inc("narrative_fallback")
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        joined = "\n".join(lines)
        normalized = BlockExtractionPipeline._normalize(joined)

        def extract_after_keyword(patterns: list[str]) -> int:
            for pat in patterns:
                match = re.search(pat, normalized)
                if match:
                    try:
                        return int(match.group(1))
                    except Exception:
                        continue
            return 0

        tong_so_vu_chay = extract_after_keyword(self.tpl.narrative_count_patterns("tong_so_vu_chay"))
        tong_so_vu_no = extract_after_keyword(self.tpl.narrative_count_patterns("tong_so_vu_no"))
        tong_so_vu_cnch = extract_after_keyword(self.tpl.narrative_count_patterns("tong_so_vu_cnch"))
        quan_so_truc = extract_after_keyword(self.tpl.narrative_count_patterns("quan_so_truc"))

        detail_kw = self.tpl.detail_keywords
        max_detail = self.tpl.detail_max_lines
        chi_tiet_lines: list[str] = []
        for line in lines:
            nline = BlockExtractionPipeline._normalize(line)
            if any(kw in nline for kw in detail_kw):
                chi_tiet_lines.append(line)
        chi_tiet_cnch = "\n".join(chi_tiet_lines[:max_detail]).strip()

        return BlockNghiepVu(
            tong_so_vu_chay=tong_so_vu_chay,
            tong_so_vu_no=tong_so_vu_no,
            tong_so_vu_cnch=tong_so_vu_cnch,
            chi_tiet_cnch=chi_tiet_cnch,
            quan_so_truc=quan_so_truc,
        )

    @trace_step("block_stage3_table_agent")
    def _extract_table(self, table_stream: list[list[list[str]]], table_text: str) -> BlockBangThongKe:
        self.emit("block_stage3_table_agent")
        # Parse ALL extracted tables; pdfplumber can split a long table into many parts.
        merged_items: list[ChiTieu] = []
        seen_stt: set[str] = set()

        for table in table_stream or []:
            parsed = self._parse_bang_thong_ke_from_tables([table])
            for item in parsed.danh_sach_chi_tieu:
                key = (item.stt or "").strip()
                if not key or key in seen_stt:
                    continue
                seen_stt.add(key)
                merged_items.append(item)

        if merged_items:
            logger.info("Block table parser collected %s rows from %s tables", len(merged_items), len(table_stream or []))
            return BlockBangThongKe(danh_sach_chi_tieu=merged_items)

        self.metrics.inc("table_grid_fallback")
        if not (table_stream or []):
            logger.warning("Block table parser detected fake-table document (table_stream empty), switching to text-grid parser")

        grid_parsed = self._parse_bang_thong_ke_from_text_grid(table_text)
        if grid_parsed.danh_sach_chi_tieu:
            logger.info("Block text-grid parser collected %s rows", len(grid_parsed.danh_sach_chi_tieu))
            return grid_parsed

        self.metrics.inc("table_line_fallback")
        logger.warning("Block table parser found no rows from table_stream and text-grid parser, fallback to loose line parser")
        return self._parse_bang_thong_ke_fallback(table_text)

    def _parse_bang_thong_ke_from_text_grid(self, table_text: str) -> BlockBangThongKe:
        """Parse fake tables represented as plain text rows (Word-exported PDF)."""
        if not table_text:
            return BlockBangThongKe(danh_sach_chi_tieu=[])

        skip_kw = self.tpl.table_header_skip_keywords

        # Normalize spacing to increase regex hit-rate on glued text.
        normalized_text = re.sub(r"([A-Za-zÀ-ỹ])([0-9])", r"\1 \2", table_text)
        normalized_text = re.sub(r"([0-9])([A-Za-zÀ-ỹ])", r"\1 \2", normalized_text)

        # Row shape: STT + content + last numeric result.
        rows = re.findall(
            r"(?m)^\s*(\d{1,3})\s+(.+?)\s+(-?\d+)\s*$",
            normalized_text,
        )

        items: list[ChiTieu] = []
        seen_stt: set[str] = set()
        for stt, noi_dung, value in rows:
            clean_noi_dung = re.sub(r"\s+", " ", (noi_dung or "").strip())
            if not clean_noi_dung:
                continue

            upper_noi_dung = BlockExtractionPipeline._normalize(clean_noi_dung)
            if any(kw in upper_noi_dung for kw in skip_kw):
                continue

            if stt in seen_stt:
                continue
            seen_stt.add(stt)

            try:
                ket_qua = int(value)
            except Exception:
                ket_qua = 0

            items.append(
                ChiTieu(
                    stt=stt,
                    noi_dung=clean_noi_dung,
                    ket_qua=ket_qua,
                )
            )

        return BlockBangThongKe(danh_sach_chi_tieu=items)

    def _parse_bang_thong_ke_from_tables(self, table_stream: list[list[list[str]]]) -> BlockBangThongKe:
        seen: set[str] = set()
        items: list[ChiTieu] = []
        skip_kw = self.tpl.table_header_skip_keywords
        law_tail_re = self.tpl.law_citation_tail_re

        for table in table_stream or []:
            # ── Dynamic column detection ──────────────────────────────
            # Try to find column indices from the header row instead of
            # assuming a fixed [STT, noi_dung, ket_qua, ...] layout.
            col_stt: int = 0
            col_nd: int = 1
            col_kq: int = 2
            num_cols: int = 0
            detected_header = False

            if table:
                first_row_norm = [self._normalize(c) for c in table[0]]
                num_cols = len(first_row_norm)
                for i, h in enumerate(first_row_norm):
                    if "STT" in h or "TT" == h.strip():
                        col_stt = i
                    elif "KET QUA" in h or "SO LIEU" in h or "THUC HIEN" in h:
                        col_kq = i
                        detected_header = True
                    elif "NOI DUNG" in h or "CHI TIEU" in h or "DANH MUC" in h:
                        col_nd = i
                        detected_header = True

                if detected_header:
                    self.metrics.inc("dynamic_col_detected")
                    logger.info(
                        "Dynamic column map: stt=%s nd=%s kq=%s (from %s cols)",
                        col_stt, col_nd, col_kq, num_cols,
                    )

            for row in table:
                cleaned = [re.sub(r"\s+", " ", (cell or "").strip()) for cell in row]
                joined = " ".join([c for c in cleaned if c]).strip()
                if not joined:
                    continue

                # Skip table header rows.
                normalized = BlockExtractionPipeline._normalize(joined)
                if any(kw in normalized for kw in skip_kw):
                    continue

                stt_match = re.search(r"^\s*(\d{1,3})\b", joined)
                if not stt_match:
                    continue
                stt = stt_match.group(1).strip()

                # Use detected column indices when table has enough columns;
                # fall back to trailing-number in joined for narrow layouts.
                if len(cleaned) >= 3:
                    noi_dung = cleaned[col_nd].strip() if col_nd < len(cleaned) else ""
                    kq_cell = cleaned[col_kq].strip() if col_kq < len(cleaned) else ""
                    ket_qua = int(kq_cell) if re.match(r"^-?\d+$", kq_cell) else 0
                else:
                    if not law_tail_re.search(joined):
                        nm = re.findall(r"-?\d+", joined)
                        ket_qua = int(nm[-1]) if len(nm) >= 2 else 0
                    else:
                        ket_qua = 0
                    noi_dung = cleaned[1] if len(cleaned) >= 2 else joined
                    if ket_qua:
                        noi_dung = re.sub(
                            rf"\b{re.escape(str(ket_qua))}\b\s*$", "", noi_dung
                        )

                noi_dung = re.sub(r"\s+", " ", noi_dung).strip(" .:-")

                if not noi_dung:
                    continue

                if stt in seen:
                    continue
                seen.add(stt)
                items.append(ChiTieu(stt=stt, noi_dung=noi_dung, ket_qua=ket_qua))

        return BlockBangThongKe(danh_sach_chi_tieu=items)

    @staticmethod
    def _parse_bang_thong_ke_fallback(block_text: str) -> BlockBangThongKe:
        items: list[ChiTieu] = []
        for raw_line in block_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Match common row forms: "14 Noi dung ... 3" or "14. Noi dung"
            match = re.match(r"^(\d{1,3})[\.)]?\s+(.*)$", line)
            if not match:
                continue

            stt = match.group(1)
            rest = match.group(2).strip()

            number_match = re.search(r"(-?\d+)\s*$", rest)
            if number_match:
                ket_qua = int(number_match.group(1))
                noi_dung = rest[: number_match.start()].strip(" .:-")
            else:
                ket_qua = 0
                noi_dung = rest.strip(" .:-")

            if not noi_dung:
                continue

            items.append(ChiTieu(stt=stt, noi_dung=noi_dung, ket_qua=ket_qua))

        return BlockBangThongKe(danh_sach_chi_tieu=items)

    @trace_step("block_stage4_schema_enforcer")
    def _enforce_schema(self, header: BlockHeader, header_context: str) -> BlockHeader:
        self.emit("block_stage4_schema_enforcer")
        required_fields = self.tpl.header_required_fields
        max_ctx = self.tpl.header_max_context_chars

        for field_name in required_fields:
            current = (getattr(header, field_name, "") or "").strip()
            if current:
                continue

            self.metrics.inc("schema_enforcer_reask")
            OneFieldModel = create_model("OneFieldModel", value=(str, ""))
            messages = [
                {
                    "role": "system",
                    "content": self.tpl.enforcer_prompt(field_name),
                },
                {"role": "user", "content": header_context[:max_ctx]},
            ]
            try:
                result = self.extractor.extract(
                    messages=messages,
                    response_model=OneFieldModel,
                    model=self.model,
                    temperature=0.0,
                )
                value = (getattr(result, "value", "") or "").strip()
                if value:
                    setattr(header, field_name, value)
            except Exception:
                logger.warning("Schema enforcer re-ask failed for field: %s", field_name, exc_info=True)

        return header

    @trace_step("block_stage5_validator")
    def _validate_output(self, output: BlockExtractionOutput) -> None:
        self.emit("block_stage5_validator")
        if output.header is None:
            raise ValueError("header is missing")
        if not any(
            [
                (output.header.so_bao_cao or "").strip(),
                (output.header.ngay_bao_cao or "").strip(),
                (output.header.don_vi_bao_cao or "").strip(),
            ]
        ):
            raise ValueError("header metadata is empty")
        if not isinstance(output.bang_thong_ke, list) or len(output.bang_thong_ke) == 0:
            raise ValueError("bang_thong_ke is empty")

    def _segment_sections(self, text: str) -> dict[str, list[str]]:
        """Split reconstructed text into sections based on template-defined markers."""
        split_re = self.tpl.section_split_re
        sections: dict[str, list[str]] = {"header": []}
        current = "header"
        for line in text.split("\n"):
            if split_re.match(line):
                current = line.strip()
                sections[current] = []
                continue
            sections[current].append(line)
        return sections

    @staticmethod
    def _normalize_tables_from_stream(table_stream: list[list[list[str]]]) -> list[dict[str, Any]]:
        """Convert table_stream to the dict format expected by business rules."""
        return [{"page": idx + 1, "rows": table} for idx, table in enumerate(table_stream)]

    @trace_step("block_stage6_business_rules")
    def _run_business_rules(
        self,
        reconstructed_text: str,
        table_stream: list[list[list[str]]],
        header_data: BlockHeader,
    ) -> dict[str, Any]:
        """Run testdoc business rules on block pipeline output."""
        self.emit("block_stage6_business_rules")
        sections = self._segment_sections(reconstructed_text)
        tables = self._normalize_tables_from_stream(table_stream)

        llm_fallback = {
            "so_bao_cao": header_data.so_bao_cao,
            "ngay_bao_cao": header_data.ngay_bao_cao,
            "don_vi": header_data.don_vi_bao_cao,
        }

        return run_business_rules(sections, tables, llm_fallback, full_text=reconstructed_text, tpl=self.tpl)

    def run_from_bytes(self, pdf_bytes: bytes, filename: str) -> PipelineResult:
        del filename
        try:
            with self.metrics.timer("stage1_layout"):
                reconstructed_text, table_stream = self._rebuild_layout(pdf_bytes)

            with self.metrics.timer("stage2_detect"):
                blocks = self._detect_blocks(reconstructed_text)

            with self.metrics.timer("stage3_extract"):
                header_data = self._extract_header(blocks["header"])
                header_data = self._enforce_schema(header_data, blocks["header"])
                phan_nghiep_vu_data = self._extract_narrative(blocks["phan_nghiep_vu"])
                bang_data_wrapper = self._extract_table(table_stream, blocks["bang_thong_ke"])

            with self.metrics.timer("stage6_business"):
                # Stage 6 — business rules (testdoc flow integration)
                business_data = self._run_business_rules(
                    reconstructed_text, table_stream, header_data
                )

            final_output = BlockExtractionOutput(
                header=header_data,
                phan_I_va_II_chi_tiet_nghiep_vu=phan_nghiep_vu_data,
                bang_thong_ke=bang_data_wrapper.danh_sach_chi_tieu,
            )

            self._validate_output(final_output)

            # Merge per-run metrics into global aggregator
            self.metrics.inc("pipeline_success")
            global_metrics.merge(self.metrics)

            return PipelineResult(
                status="ok",
                attempts=1,
                output=final_output,
                errors=[],
                business_data=business_data,
                metrics=self.metrics.to_dict(),
            )
        except Exception as exc:
            logger.error("Block extraction pipeline failed: %s", exc)
            self.metrics.inc("pipeline_failure")
            global_metrics.merge(self.metrics)
            return PipelineResult(
                status="failed",
                attempts=1,
                errors=[str(exc)],
                metrics=self.metrics.to_dict(),
            )
