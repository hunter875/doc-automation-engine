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
from app.utils.metrics import PipelineMetrics, global_metrics
from app.core.tracing import trace_step
from app.engines.extraction.schemas import (
    BlockBangThongKe,
    BlockExtractionOutput,
    BlockHeader,
    CNCHItem,
    CNCHListOutput,
    ChiTieu,
    BlockNghiepVu,
    CongVanItem,
    PhuongTienHuHongItem,
    PipelineResult,
)
from app.domain.rules.engine import run_business_rules
from app.domain.rules.normalizers import _restore_vn_word_spacing, _collapse_whitespace
from app.domain.templates.template_loader import DocumentTemplate, get_default_template
from app.engines.extraction.extractors import OllamaInstructorExtractor

logger = logging.getLogger(__name__)


def _inject_computed_bang_thong_ke_rows(items: list) -> list:
    """Insert rows that pdfplumber drops at PDF page breaks using known formulas.

    STT 33 (Kiểm tra đột xuất theo chuyên đề) = STT 31 (tổng) − STT 32 (định kỳ).
    Inserted in sorted STT order so downstream consumers see a complete sequence.
    """
    by_stt = {item.stt: item for item in items}
    insertions = []

    if "33" not in by_stt and "31" in by_stt and "32" in by_stt:
        kq31 = int(by_stt["31"].ket_qua or 0)
        kq32 = int(by_stt["32"].ket_qua or 0)
        insertions.append(
            ChiTieu(stt="33", noi_dung="Kiểm tra đột xuất theo chuyên đề", ket_qua=max(0, kq31 - kq32))
        )

    if not insertions:
        return items

    merged = list(items) + insertions
    merged.sort(key=lambda x: int(x.stt) if str(x.stt).isdigit() else 9999)
    return merged


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
    def _smart_join(prev: dict[str, Any], curr: dict[str, Any], threshold: float = -1.0) -> str:
        # threshold=-1.0 so we always insert a space between tokens returned by
        # extract_words() — pdfplumber already handles word boundary detection;
        # these are word-level objects, not individual characters.
        prev_text = (prev.get("text") or "").strip()
        curr_text = (curr.get("text") or "").strip()
        if not prev_text:
            return curr_text
        gap = float(curr.get("x0", 0.0)) - float(prev.get("x1", 0.0))
        return (" " + curr_text) if gap > threshold else curr_text

    @trace_step("block_stage1_layout_reconstruction")
    def _rebuild_layout(self, pdf_bytes: bytes) -> tuple[str, list[list[list[str]]], str]:
        self.emit("block_stage1_layout_reconstruction")
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("pdfplumber is not installed") from exc

        pages_text: list[str] = []
        layout_pages_text: list[str] = []
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

                def build_text_from_tokens(tokens: list[dict[str, Any]]) -> list[tuple[float, str]]:
                    """Build (row_key, line_text) pairs sorted by vertical position."""
                    if not tokens:
                        return []
                    rows: dict[float, list[dict[str, Any]]] = {}
                    for token in tokens:
                        row_key = round(float(token.get("top", 0.0)), 1)
                        rows.setdefault(row_key, []).append(token)

                    built_lines: list[tuple[float, str]] = []
                    for row_key, row_tokens in sorted(rows.items(), key=lambda item: item[0]):
                        row_tokens = sorted(row_tokens, key=lambda t: float(t.get("x0", 0.0)))
                        if not row_tokens:
                            continue
                        line = (row_tokens[0].get("text") or "").strip()
                        for idx in range(1, len(row_tokens)):
                            line += self._smart_join(row_tokens[idx - 1], row_tokens[idx])
                        if line.strip():
                            built_lines.append((row_key, line.strip()))
                    return built_lines

                left_lines_keyed = build_text_from_tokens(left_line_tokens)
                right_lines_keyed = build_text_from_tokens(right_line_tokens)

                # Merge left and right column lines sorted by vertical position.
                # This preserves correct reading order for two-column headers:
                # right-column header content (BÁO CÁO title, period "(Từ...đến...)")
                # appears at the same vertical level as the left-column header
                # and must come BEFORE the body text that starts with "I." —
                # NOT after all body text as the old left_lines + right_lines did.
                all_lines_keyed = sorted(
                    left_lines_keyed + right_lines_keyed, key=lambda x: x[0]
                )
                page_text = "\n".join(line for _, line in all_lines_keyed).strip()
                if page_text:
                    pages_text.append(page_text)

                # Layout-preserving text for narrative extraction.
                # pdfplumber's extract_text(layout=True) preserves spatial
                # positioning so multi-line narrative paragraphs stay intact
                # (the word-level 2-column merge above can fragment them).
                try:
                    layout_text_page = page.extract_text(layout=True) or ""
                    if layout_text_page.strip():
                        layout_pages_text.append(layout_text_page.strip())
                except Exception:
                    # Fallback: use the same text as the word-level extraction
                    if page_text:
                        layout_pages_text.append(page_text)

                # Word-aware table extraction: pdfplumber's extract_tables() uses
                # character-level concatenation which loses inter-word spaces in
                # Word-exported PDFs.  Using find_tables() + row.cells per-cell
                # crop gives us properly spaced text while preserving row/col alignment.
                tbl_objects: list[Any] = []
                try:
                    tbl_objects = page.find_tables() or []
                except Exception as _find_exc:
                    logger.debug("find_tables() failed: %s", _find_exc)

                for tbl in tbl_objects:
                    try:
                        normalized_rows_w: list[list[str]] = []
                        for row in tbl.rows:
                            cells_text: list[str] = []
                            for cell_bbox in row.cells:
                                if cell_bbox is not None:
                                    try:
                                        # Use layout=True so pdfplumber places chars on a
                                        # spatial grid — this correctly separates Vietnamese
                                        # words that are visually spaced but have no Unicode
                                        # space character in the PDF font encoding.
                                        # extract_text(x_tol=2) without layout still misses
                                        # gaps in lowercase Vietnamese sequences.
                                        cropped = page.crop(cell_bbox)
                                        cell_text = (
                                            cropped.extract_text(layout=True) or ""
                                        ).strip()
                                        # layout=True may insert multiple spaces — collapse
                                        cell_text = re.sub(r"\s+", " ", cell_text).strip()
                                        # Fallback when layout produces empty result
                                        if not cell_text:
                                            cell_text = (
                                                cropped.extract_text(
                                                    x_tolerance=3, y_tolerance=3
                                                ) or ""
                                            ).strip()
                                    except Exception:
                                        cell_text = ""
                                else:
                                    cell_text = ""
                                cells_text.append(cell_text)
                            if any(cells_text):
                                normalized_rows_w.append(cells_text)
                        if normalized_rows_w:
                            table_stream.append(normalized_rows_w)
                    except Exception as _tbl_exc:
                        logger.warning(
                            "Word-table extraction failed (%s); falling back to raw cells",
                            _tbl_exc,
                        )
                        try:
                            raw_rows_fb = tbl.extract() or []
                            norm_fb: list[list[str]] = [
                                [str(c).strip() if c is not None else "" for c in row]
                                for row in raw_rows_fb
                                if any(c for c in row if c)
                            ]
                            if norm_fb:
                                table_stream.append(norm_fb)
                        except Exception:
                            pass

                if not tbl_objects:
                    # find_tables() returned nothing — fall back to extract_tables()
                    for table in page.extract_tables() or []:
                        if not table:
                            continue
                        normalized_rows_fb2: list[list[str]] = [
                            [str(cell).strip() if cell is not None else "" for cell in row]
                            for row in table
                            if any(cell for cell in row if cell)
                        ]
                        if normalized_rows_fb2:
                            table_stream.append(normalized_rows_fb2)

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

        # Build layout-preserving text for narrative extraction
        layout_text = "\n".join(layout_pages_text)
        layout_text = _restore_vn_word_spacing(layout_text)
        layout_text = _collapse_whitespace(layout_text) if not layout_text.strip() else layout_text

        logger.info("TABLE COUNT = %s", len(table_stream))
        logger.info("Block stage1 done: chars=%s tables=%s layout_chars=%s", len(full_text), len(table_stream), len(layout_text))
        return full_text, table_stream, layout_text

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
    def _extract_block(self, block_text: str, schema: type[BaseModel], block_name: str, timeout_seconds: float | None = None) -> BaseModel:
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
                timeout_seconds=timeout_seconds,
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
        """Extract header fields using deterministic regex only — no LLM call.

        qwen3:8b (thinking model) takes 90-170s per call even with think=False
        because instructor cannot pass Ollama-specific options through the
        OpenAI-compat SDK.  All header fields can be extracted with regex at
        near-zero latency with equal or better accuracy.
        """
        self.emit("block_stage3_header_agent")
        max_lines = self.tpl.header_max_lines
        first_n = "\n".join([line for line in header_text.splitlines() if line.strip()][:max_lines])

        # Normalize spaced slash-dates: "21 / 03 / 2026" → "21/03/2026"
        text_norm = re.sub(r"(\d{1,2})\s*/\s*(\d{2})\s*/\s*(\d{4})", r"\1/\2/\3", first_n)

        # ── ngay_bao_cao ───────────────────────────────────────────────
        ngay_bao_cao = ""
        date_match = self.tpl.date_long_form_re.search(text_norm)
        if date_match:
            ngay_bao_cao = f"{int(date_match.group(1)):02d}/{int(date_match.group(2)):02d}/{date_match.group(3)}"
        if not ngay_bao_cao:
            period_markers = self.tpl.date_period_markers
            for line in text_norm.splitlines():
                if any(marker in line for marker in period_markers):
                    continue
                # Also skip lines that start with "Từ" followed by a digit
                # (period time-range lines like "Từ 07h30' ngày 20/03/2026")
                if re.match(r"^\(?Từ\s+\d", line, re.IGNORECASE):
                    continue
                m = self.tpl.date_short_form_re.search(line)
                if m:
                    parts = m.group(1).split("/")
                    ngay_bao_cao = f"{int(parts[0]):02d}/{parts[1]}/{parts[2]}"
                    break

        # ── so_bao_cao ────────────────────────────────────────────────
        so_bao_cao = ""
        m = self.tpl.report_number_primary_re.search(first_n)
        if m:
            raw = re.sub(r"\s*/\s*", "/", m.group(1).strip())
            so_bao_cao = re.sub(r"\s+", "", raw)
        if not so_bao_cao:
            m2 = self.tpl.report_number_fallback_re.search(first_n)
            if m2:
                so_bao_cao = re.sub(r"\s+", "", m2.group(1).strip())

        # ── don_vi_bao_cao ───────────────────────────────────────────
        don_vi_bao_cao = ""
        for pat in self.tpl.unit_patterns:
            m = pat.search(first_n)
            if m:
                don_vi_bao_cao = m.group(0).strip()
                break

        # ── thoi_gian_tu_den ──────────────────────────────────────────
        thoi_gian_tu_den = ""
        # Look for pattern: "Từ ... đến ..." spread across 1-2 lines
        # First try single-line match
        tu_den_m = re.search(
            r"(?:Từ\s+\d[^\n]{3,60}(?:đến|\u2013|-)[^\n]{3,40})",
            first_n, re.IGNORECASE
        )
        if tu_den_m:
            thoi_gian_tu_den = tu_den_m.group(0).strip()
        else:
            # Fallback: join all header lines into one string and retry
            # (handles case where pdfplumber splits "Từ...đến..." across lines)
            single_line_header = " ".join(
                line.strip() for line in first_n.splitlines() if line.strip()
            )
            tu_den_m2 = re.search(
                r"Từ\s+\d.{3,80}(?:đến|\u2013|-)\s+\d.{3,40}",
                single_line_header, re.IGNORECASE
            )
            if tu_den_m2:
                thoi_gian_tu_den = tu_den_m2.group(0).strip()
            else:
                # Last resort: grab any line containing a date range hint
                for line in first_n.splitlines():
                    if re.search(r"Từ\s+\d", line, re.IGNORECASE):
                        thoi_gian_tu_den = line.strip().lstrip("(").rstrip(")")
                        break

        header = BlockHeader(
            so_bao_cao=so_bao_cao,
            ngay_bao_cao=ngay_bao_cao,
            thoi_gian_tu_den=thoi_gian_tu_den,
            don_vi_bao_cao=don_vi_bao_cao,
        )
        logger.info(
            "Header extracted (regex-only): so_bao_cao=%r ngay=%r don_vi=%r tu_den=%r",
            so_bao_cao, ngay_bao_cao, don_vi_bao_cao, thoi_gian_tu_den,
        )
        return header

    @trace_step("block_stage3_narrative_agent")
    def _extract_narrative(self, narrative_text: str, layout_text: str = "") -> BlockNghiepVu:
        """Extract narrative counts using deterministic regex only — no LLM call.

        Delegates directly to _parse_phan_nghiep_vu_fallback which already uses
        the template regex patterns and produces correct results.  The LLM call
        here added 90-170s latency with no accuracy gain.
        """
        self.emit("block_stage3_narrative_agent")
        return self._parse_phan_nghiep_vu_fallback(narrative_text, layout_text=layout_text)

    def _parse_phan_nghiep_vu_fallback(self, text: str, layout_text: str = "") -> BlockNghiepVu:
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

        # ── chi_tiet_cnch: extract from "3. Tình hình cứu nạn" subsection ──
        # Keyword-scanning all lines captures garbled content from other sections
        # (right-column header text). Instead extract the CNCH subsection directly.
        # Prefer layout_text (from page.extract_text(layout=True)) which preserves
        # spatial reading order and keeps narrative paragraphs intact, avoiding
        # fragmentation from the word-level 2-column merge.
        cnch_source = layout_text if layout_text.strip() else joined
        chi_tiet_cnch = ""
        cnch_sub_m = re.search(
            r'3\.\s*Tình\s*hình\s*(?:công\s*tác\s*)?cứu\s*nạn',
            cnch_source, re.IGNORECASE
        )
        if cnch_sub_m:
            start = cnch_sub_m.start()
            # End at next numbered item "4. " or roman section "II."
            next_m = re.search(r'\n4\.\s|\nII[\.\s]|\nIII[\.\s]', cnch_source[start:])
            end = start + (next_m.start() if next_m else min(len(cnch_source) - start, 1500))
            chi_tiet_cnch = cnch_source[start:end].strip()
        else:
            # Fallback: keyword line scan
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
            # Fix pdfplumber spacing artifacts in Vietnamese text
            clean_noi_dung = _restore_vn_word_spacing(clean_noi_dung)
            clean_noi_dung = _collapse_whitespace(clean_noi_dung)
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
                    # STT cell may be empty (merged with row above) — check by column position
                    stt_cell = cleaned[col_stt].strip() if col_stt < len(cleaned) else ""
                    if re.match(r"^\d{1,3}$", stt_cell):
                        stt = stt_cell
                    else:
                        continue
                else:
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
                # Fix pdfplumber spacing artifacts in Vietnamese text
                noi_dung = _restore_vn_word_spacing(noi_dung)
                noi_dung = _collapse_whitespace(noi_dung)

                if not noi_dung:
                    continue

                if stt in seen:
                    continue
                seen.add(stt)
                items.append(ChiTieu(stt=stt, noi_dung=noi_dung, ket_qua=ket_qua))

        # Post-process: inject computed rows that fall on PDF page breaks.
        # STT 33 (Kiểm tra đột xuất) = STT 31 (tổng) - STT 32 (định kỳ) when missing.
        items = _inject_computed_bang_thong_ke_rows(items)

        return BlockBangThongKe(danh_sach_chi_tieu=items)

    def _apply_cnch_fallback(
        self, narrative: BlockNghiepVu, items: list[ChiTieu]
    ) -> BlockNghiepVu:
        """Derive tong_so_vu_cnch from bang_thong_ke rows when LLM missed it.

        This is the same logic as BlockBusinessWorkflow.build_final_payload(),
        consolidated here so the web pipeline (orchestrator) and the CLI script
        both produce identical output.
        """
        if narrative.tong_so_vu_cnch:
            return narrative  # LLM already got it
        cnch_patterns = tuple(self.tpl.cnch_fallback_patterns)
        for item in items:
            nd = item.noi_dung or ""
            nd_norm = unicodedata.normalize("NFD", nd.upper())
            nd_norm = re.sub(
                r"[^\w]", "",
                "".join(ch for ch in nd_norm if unicodedata.category(ch) != "Mn"),
            )
            if any(pat in nd_norm for pat in cnch_patterns) and item.ket_qua:
                narrative.tong_so_vu_cnch = item.ket_qua
                self.metrics.inc("cnch_fallback_applied")
                logger.info(
                    "CNCH fallback applied: tong_so_vu_cnch=%s from noi_dung=%r",
                    item.ket_qua, nd,
                )
                break
        return narrative

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

            # Fix pdfplumber spacing artifacts in Vietnamese text
            noi_dung = _restore_vn_word_spacing(noi_dung)
            noi_dung = _collapse_whitespace(noi_dung)

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

    # ------------------------------------------------------------------
    # Narrative array extraction — uses a second LLM call with
    # LLMVanXuoiOutput to pull structured arrays (danh_sach_cnch,
    # danh_sach_phuong_tien_hu_hong) that BlockNghiepVu cannot capture
    # because its schema is flat numeric fields only.
    # Falls back to regex when the LLM call fails.
    # ------------------------------------------------------------------

    @trace_step("block_extract_narrative_arrays")
    def _extract_narrative_arrays(
        self,
        narrative_text: str,
        business_data: dict[str, Any],
        chi_tiet_cnch: str = "",
    ) -> tuple[list[CNCHItem], list[PhuongTienHuHongItem], list[CongVanItem]]:
        """Extract arrays from narrative using regex + optional LLM call.

        When chi_tiet_cnch is provided (the pre-extracted CNCH subsection text),
        a focused LLM call with CNCHListOutput schema is attempted first.  This
        is fast because the input is short (one subsection, ~500 chars) and the
        schema is minimal.  Falls back to regex when the LLM call fails or when
        chi_tiet_cnch is empty.
        Return (danh_sach_cnch, danh_sach_phuong_tien_hu_hong, danh_sach_cong_van_tham_muu).
        """
        self.emit("block_extract_narrative_arrays")

        cnch_list: list[CNCHItem] = []
        # pt_hu_hong and cong_van are built later in their own sections below

        # ── Dedicated LLM call for danh_sach_cnch ─────────────────────────
        # Use the focused CNCH subsection text (section 3 only) so the model
        # receives a short, targeted input — avoids context overflow and gives
        # better accuracy than sending the full narrative.
        if chi_tiet_cnch.strip():
            # Normalize OCR artifacts before LLM and regex (same as Stage-2 path)
            cnch_norm = re.sub(r"\s+", " ", chi_tiet_cnch).strip()

            cnch_prompt = (
                "Bạn là công cụ trích xuất dữ liệu có cấu trúc từ báo cáo nghiệp vụ PCCC Việt Nam.\n"
                "Nhiệm vụ: đọc đoạn văn bản dưới đây và trả về danh sách các vụ CNCH.\n\n"
                "QUY TẮC BẮT BUỘC:\n"
                "1. Mỗi vụ PHẢI có đủ 8 trường sau — không được bỏ sót trường nào.\n"
                "2. Nếu thông tin không có trong văn bản, trả về chuỗi rỗng \"\".\n"
                "3. Không thêm trường ngoài schema, không giải thích, chỉ JSON.\n\n"
                "SCHEMA MỖI VỤ:\n"
                "{\n"
                "  \"stt\": <số thứ tự, integer>,\n"
                "  \"thoi_gian\": \"HH:MM ngày dd/mm/yyyy\",        // ví dụ: \"16:33 ngày 20/03/2026\"\n"
                "  \"ngay_xay_ra\": \"dd/mm/yyyy\",                  // ví dụ: \"20/03/2026\"\n"
                "  \"dia_diem\": \"<địa chỉ đầy đủ nơi xảy ra>\",\n"
                "  \"noi_dung_tin_bao\": \"<loại sự cố>\",            // ví dụ: \"người dân nhảy sông\"\n"
                "  \"luc_luong_tham_gia\": \"<lực lượng + phương tiện>\", // ví dụ: \"01 xe phương tiện, 06 CBCS\"\n"
                "  \"ket_qua_xu_ly\": \"<kết quả / tình trạng xử lý>\",\n"
                "  \"thong_tin_nan_nhan\": \"<họ tên, năm sinh, địa chỉ thường trú>\"\n"
                "}\n\n"
                "Nếu không có vụ nào, trả về: {\"items\": []}"
            )
            try:
                self.metrics.inc("llm_calls")
                result: CNCHListOutput = self.extractor.extract(
                    messages=[
                        {"role": "system", "content": cnch_prompt},
                        {"role": "user", "content": cnch_norm},
                    ],
                    response_model=CNCHListOutput,
                    model=self.model,
                    temperature=0.0,
                    timeout_seconds=120.0,
                )
                if result.items:
                    # Re-number stt sequentially; LLM sometimes outputs 0 or duplicates
                    for i, item in enumerate(result.items, 1):
                        item.stt = i
                        self._regex_fill_cnch_fields(item, cnch_norm)
                    cnch_list = result.items
                    self.metrics.inc("cnch_llm_extracted")
                    logger.info(
                        "CNCH LLM extraction: %s incident(s) extracted", len(cnch_list)
                    )
            except Exception as exc:
                self.metrics.inc("cnch_llm_fallback")
                logger.warning(
                    "CNCH LLM extraction failed (%s); falling back to regex/business-rules",
                    exc,
                )

        # ── Convert business-rules narrative incidents → CNCHItem ──
        # Only run when LLM extraction did not already produce results.
        # Only use incidents from narrative source (have time/location).
        # Stat-table incidents only have a count, no detail.
        biz_incidents = (business_data or {}).get("data", {}).get("incidents", []) if not cnch_list else []
        for idx, inc in enumerate(biz_incidents, 1):
            if not isinstance(inc, dict):
                continue
            if inc.get("nguon") == "bang_thong_ke":
                # No time/location detail from stat table → skip for now
                continue
            try:
                cnch_list.append(
                    CNCHItem(
                        stt=idx,
                        ngay_xay_ra=inc.get("ngay_xay_ra", ""),
                        thoi_gian=inc.get("thoi_gian", ""),
                        mo_ta=inc.get("mo_ta", ""),
                        dia_diem=inc.get("dia_diem", ""),
                    )
                )
            except Exception as exc:
                logger.warning("CNCHItem creation failed for incident %s: %s", idx, exc)

        # ── Fallback: search narrative_text directly for time patterns ──
        # Business rules only extract from section-separated text; if layout
        # reconstruction puts content in wrong sections, we may miss incidents.
        if not cnch_list and narrative_text:
            joined_for_cnch = re.sub(r'\s+', ' ', narrative_text)
            time_re = self.tpl.incident_time_re
            loc_re = self.tpl.incident_location_re
            ctx_chars = self.tpl.incident_context_chars
            loc_max = self.tpl.incident_location_max_chars
            desc_re = self.tpl.incident_description_re
            for m in time_re.finditer(joined_for_cnch):
                thoi_gian = f"{int(m.group(1)):02d}:{m.group(2)} ngày {m.group(3)}"
                context = joined_for_cnch[m.start(): m.start() + ctx_chars]
                loc_m = loc_re.search(context)
                dia_diem = (
                    re.sub(r'\s+', ' ', loc_m.group(1)).strip()[:loc_max] if loc_m else ""
                )
                mo_ta_m = desc_re.search(context)
                mo_ta = re.sub(r'\s+', ' ', mo_ta_m.group(0)).strip() if mo_ta_m else ""
                try:
                    cnch_list.append(
                        CNCHItem(
                            stt=len(cnch_list) + 1,
                            thoi_gian=thoi_gian,
                            dia_diem=dia_diem,
                            mo_ta=mo_ta,
                        )
                    )
                except Exception as exc:
                    logger.warning("Direct CNCH extraction CNCHItem failed: %s", exc)

        # ── Regex: phương tiện hư hỏng — parse into PhuongTienHuHongItem ──────
        # Normalize plate numbers: "61 A-003.52" → "61A-003.52", "61 CD-002.85" → "61CD-002.85"
        _plate_re = re.compile(r'\b(\d{2})\s+([A-Z]{1,2})-(\d{3}\.\d{2})\b')

        def _parse_vehicle_part(raw: str) -> PhuongTienHuHongItem:
            """Parse a vehicle string into bien_so + tinh_trang."""
            # Normalize excess whitespace
            clean = re.sub(r'\s+', ' ', raw).strip()
            # Normalize plate spacing: "61 A-003.52" → "61A-003.52"
            clean = _plate_re.sub(r'\1\2-\3', clean)
            # Extract plate number (bien_so) — everything up to and including plate
            plate_m = re.search(r'\d{2}[A-Z]{1,2}-\d{3}\.\d{2}', clean)
            if plate_m:
                # bien_so = everything up to end of plate
                bien_so = clean[:plate_m.end()].strip()
                # Strip leading "xe/Xe " prefix — Word template already writes "Xe {{ xe.bien_so }}"
                bien_so = re.sub(r'^[Xx]e\s+', '', bien_so)
                tinh_trang = clean[plate_m.end():].strip().lstrip(',').strip()
            else:
                bien_so = clean
                tinh_trang = ""
            # Balance unmatched opening parentheses (e.g. PDF splits "hết kiểm định (chờ thanh lý)")
            if tinh_trang.count('(') > tinh_trang.count(')'):
                tinh_trang += ')'
            return PhuongTienHuHongItem(bien_so=bien_so, tinh_trang=tinh_trang)

        pt_hu_hong: list[PhuongTienHuHongItem] = []
        if narrative_text:
            # Join lines so "Xe X...\như hỏng" (split across lines) becomes one line
            joined_narrative = " ".join(line for line in narrative_text.splitlines() if line.strip())
            # Find the full damaged-vehicles sentence
            vehicle_sentence_m = re.search(
                r'[Xx]e\s+.{5,400}(?:hư hỏng|hỏng|hết kiểm định|chờ thanh lý|đang sửa)',
                joined_narrative,
                re.IGNORECASE,
            )
            if vehicle_sentence_m:
                sentence = vehicle_sentence_m.group(0)
                # Split at: comma-xe, digit/dot-then-xe (plate end), or "và xe"
                parts = re.split(
                    r'[,;]\s*(?=[Xx]e\b)|(?<=[.\d])\s+(?=[Xx]e\b)|\bvà\s+(?=[Xx]e\b)',
                    sentence,
                )
                for part in parts:
                    part = part.strip().strip(',').strip()
                    if part and re.search(r'\d{2}[A-Z]{1,2}[-]\d{3}|xe|phương tiện', part, re.IGNORECASE):
                        pt_hu_hong.append(_parse_vehicle_part(part))
            # Fallback: generic vehicle pattern
            if not pt_hu_hong:
                for m in re.finditer(
                    r'(?:xe|phương tiện|máy bơm|máy cắt)[^.]{3,80}(?:hư hỏng|hỏng|hết kiểm định)',
                    joined_narrative,
                    re.IGNORECASE,
                ):
                    pt_hu_hong.append(_parse_vehicle_part(m.group(0).strip()))

        # ── Regex: công văn tham mưu → CongVanItem ───────────────────
        cong_van: list[CongVanItem] = []
        if narrative_text:
            for m in re.finditer(
                r"(?:Công văn|CV|Tờ trình)\s*(?:số\s*)?([\d/]+[^\n]{0,80})",
                narrative_text,
                re.IGNORECASE,
            ):
                full = m.group(0).strip()
                so_m = re.match(r"(?:Công văn|CV|Tờ trình)\s*(?:số\s*)?([\d/\-A-Z]+)", full, re.IGNORECASE)
                so_ky_hieu = so_m.group(1).strip() if so_m else ""
                noi_dung = full[so_m.end():].strip().lstrip(':').strip() if so_m else full
                cong_van.append(CongVanItem(so_ky_hieu=so_ky_hieu, noi_dung=noi_dung))

        return cnch_list, pt_hu_hong, cong_van

    # ------------------------------------------------------------------
    # Stage 2 — LLM enrichment (called asynchronously from Celery)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # CNCH field-level regex fallback
    # ------------------------------------------------------------------

    def _regex_fill_cnch_fields(self, item: CNCHItem, text: str) -> None:
        """Fill empty CNCHItem fields from chi_tiet_cnch text using regex.

        Patterns are read from table.cnch_fill_patterns in the YAML template
        (pccc.yaml).  Applied after LLM extraction to recover fields the model
        left blank — the source text is identical so all data is present.
        """
        # Collapse ALL whitespace (newlines, repeated spaces, PDF padding) to a
        # single space so patterns don't need to account for layout artifacts.
        flat = re.sub(r"\s+", " ", text).strip()

        for field in ("noi_dung_tin_bao", "luc_luong_tham_gia", "thong_tin_nan_nhan", "ket_qua_xu_ly", "ngay_xay_ra"):
            if getattr(item, field):
                continue  # already populated — skip
            for pat in self.tpl.cnch_fill_patterns(field):
                m = pat.search(flat)
                if m:
                    setattr(item, field, re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",."))
                    break

        # Fallback: derive ngay_xay_ra from thoi_gian if still empty
        # thoi_gian is typically "16:33 ngày 20/03/2026" — extract the date part
        if not item.ngay_xay_ra and item.thoi_gian:
            m = re.search(r"(\d{1,2}/\d{2}/\d{4})", item.thoi_gian)
            if m:
                item.ngay_xay_ra = m.group(1)

    def _llm_enrich_cnch(self, chi_tiet_cnch: str) -> list[CNCHItem]:
        """Run the CNCHListOutput LLM call and return enriched CNCHItem list.

        This is the ONLY LLM call in the block pipeline.  It must be called
        from the enrichment worker (Stage 2), never from the synchronous
        extraction path (Stage 1).

        After the LLM call, any fields still empty are filled by
        _regex_fill_cnch_fields() so critical CNCH data is never lost.

        Returns an empty list when chi_tiet_cnch is blank or when the call
        fails, so the caller can fall back to the Stage-1 regex results.
        """
        if not chi_tiet_cnch.strip():
            return []

        # Normalize OCR artifacts before sending to LLM and regex.
        # Collapsing whitespace removes multi-space padding, hard newlines and
        # layout gaps that cause the model to miss multi-line field values.
        normalized_text = re.sub(r"\s+", " ", chi_tiet_cnch).strip()

        cnch_prompt = (
            "Bạn là công cụ trích xuất dữ liệu có cấu trúc từ báo cáo nghiệp vụ PCCC Việt Nam.\n"
            "Nhiệm vụ: đọc đoạn văn bản dưới đây và trả về danh sách các vụ CNCH.\n\n"
            "QUY TẮC BẮT BUỘC:\n"
            "1. Mỗi vụ PHẢI có đủ 8 trường sau — không được bỏ sót trường nào.\n"
            "2. Nếu thông tin không có trong văn bản, trả về chuỗi rỗng \"\".\n"
            "3. Không thêm trường ngoài schema, không giải thích, chỉ JSON.\n\n"
            "SCHEMA MỖI VỤ:\n"
            "{\n"
            "  \"stt\": <số thứ tự, integer>,\n"
            "  \"thoi_gian\": \"HH:MM ngày dd/mm/yyyy\",        // ví dụ: \"16:33 ngày 20/03/2026\"\n"
            "  \"ngay_xay_ra\": \"dd/mm/yyyy\",                  // ví dụ: \"20/03/2026\"\n"
            "  \"dia_diem\": \"<địa chỉ đầy đủ nơi xảy ra>\",\n"
            "  \"noi_dung_tin_bao\": \"<loại sự cố>\",            // ví dụ: \"người dân nhảy sông\"\n"
            "  \"luc_luong_tham_gia\": \"<lực lượng + phương tiện>\", // ví dụ: \"01 xe phương tiện, 06 CBCS\"\n"
            "  \"ket_qua_xu_ly\": \"<kết quả / tình trạng xử lý>\",\n"
            "  \"thong_tin_nan_nhan\": \"<họ tên, năm sinh, địa chỉ thường trú>\"\n"
            "}\n\n"
            "Nếu không có vụ nào, trả về: {\"items\": []}"
        )
        try:
            self.metrics.inc("llm_calls")
            result: CNCHListOutput = self.extractor.extract(
                messages=[
                    {"role": "system", "content": cnch_prompt},
                    {"role": "user", "content": normalized_text},
                ],
                response_model=CNCHListOutput,
                model=self.model,
                temperature=0.0,
                timeout_seconds=120.0,
            )
            if result.items:
                for i, item in enumerate(result.items, 1):
                    item.stt = i
                    # Fill any fields the LLM left blank using deterministic regex
                    self._regex_fill_cnch_fields(item, normalized_text)
                self.metrics.inc("cnch_llm_extracted")
                logger.info(
                    "CNCH LLM enrichment: %s incident(s) extracted", len(result.items)
                )
                return result.items
        except Exception as exc:
            self.metrics.inc("cnch_llm_fallback")
            logger.warning(
                "CNCH LLM enrichment failed (%s); attempting regex-only enrichment", exc
            )

        # ── Regex-only fallback: build one CNCHItem entirely from chi_tiet_cnch ──
        # This path runs when the LLM call fails or returns [].
        # normalized_text already collapsed to single spaces above.
        flat = normalized_text

        # Check whether there is any incident content at all
        marker_patterns = self.tpl.cnch_fill_patterns("incident_marker")
        incident_markers = any(p.search(flat) for p in marker_patterns) if marker_patterns else re.search(
            r"\bxảy ra\b|\bsự cố\b", flat, re.IGNORECASE
        )
        if not incident_markers:
            return []

        # Try to extract thoi_gian (e.g. "lúc 16 giờ 33 phút ngày 20/03/2026")
        thoi_gian = ""
        ngay_xay_ra = ""
        for time_pat in self.tpl.cnch_fill_patterns("incident_time"):
            time_m = time_pat.search(flat)
            if time_m:
                thoi_gian = f"{int(time_m.group(1)):02d}:{time_m.group(2)} ngày {time_m.group(3)}"
                ngay_xay_ra = time_m.group(3)
                break

        # dia_diem — text after "xảy ra tại địa chỉ:" or "tại địa chỉ:"
        dia_diem = ""
        for loc_pat in self.tpl.cnch_fill_patterns("incident_location"):
            dia_diem_m = loc_pat.search(flat)
            if dia_diem_m:
                dia_diem = re.sub(r"\s+", " ", dia_diem_m.group(1)).strip()
                break

        fallback_item = CNCHItem(
            stt=1,
            thoi_gian=thoi_gian,
            ngay_xay_ra=ngay_xay_ra,
            dia_diem=dia_diem,
        )
        self._regex_fill_cnch_fields(fallback_item, chi_tiet_cnch)

        # Only return an item if we extracted something meaningful
        has_data = any([
            fallback_item.thoi_gian,
            fallback_item.dia_diem,
            fallback_item.noi_dung_tin_bao,
        ])
        if has_data:
            logger.info("CNCH regex-only fallback: 1 incident extracted from chi_tiet_cnch")
            self.metrics.inc("cnch_regex_fallback")
            return [fallback_item]
        return []

    # ------------------------------------------------------------------
    # Stage 1 — deterministic extraction (NO LLM call)
    # ------------------------------------------------------------------

    def run_stage1_from_bytes(self, pdf_bytes: bytes, filename: str) -> PipelineResult:
        """Run Stage 1: fully deterministic extraction without any LLM call.

        Identical to run_from_bytes() except:
        - _extract_narrative_arrays is called with chi_tiet_cnch="" so the
          LLM branch is skipped and only regex + business-rules fallbacks run.
        - phan_nghiep_vu_data.chi_tiet_cnch is returned in result.chi_tiet_cnch
          so the async enrichment task (Stage 2) can run the LLM call later
          without re-parsing the PDF.

        The returned PipelineResult has status="ok" and is immediately usable
        for review/export.  Documents remain usable when the LLM service is off.
        """
        del filename
        try:
            with self.metrics.timer("stage1_layout"):
                reconstructed_text, table_stream, layout_text = self._rebuild_layout(pdf_bytes)

            with self.metrics.timer("stage2_detect"):
                blocks = self._detect_blocks(reconstructed_text)

            with self.metrics.timer("stage3_extract"):
                header_data = self._extract_header(blocks["header"])
                header_data = self._enforce_schema(header_data, blocks["header"])
                phan_nghiep_vu_data = self._extract_narrative(blocks["phan_nghiep_vu"], layout_text=layout_text)
                bang_data_wrapper = self._extract_table(table_stream, blocks["bang_thong_ke"])
                phan_nghiep_vu_data = self._apply_cnch_fallback(
                    phan_nghiep_vu_data, bang_data_wrapper.danh_sach_chi_tieu
                )

            with self.metrics.timer("stage6_business"):
                business_data = self._run_business_rules(
                    reconstructed_text, table_stream, header_data
                )

            # Stage 1 narrative arrays — regex + business-rules ONLY (no LLM)
            with self.metrics.timer("stage_narrative_arrays"):
                narrative_for_arrays = layout_text if layout_text.strip() else blocks["phan_nghiep_vu"]
                cnch_list, pt_hu_hong, cong_van = self._extract_narrative_arrays(
                    narrative_for_arrays,
                    business_data,
                    chi_tiet_cnch="",  # intentionally empty → skips LLM call
                )
                if not phan_nghiep_vu_data.tong_xe_hu_hong and pt_hu_hong:
                    phan_nghiep_vu_data.tong_xe_hu_hong = len(pt_hu_hong)
                if not phan_nghiep_vu_data.tong_cong_van and cong_van:
                    phan_nghiep_vu_data.tong_cong_van = len(cong_van)

            _stt_map = {
                str(item.stt).strip(): item.ket_qua
                for item in bang_data_wrapper.danh_sach_chi_tieu
                if item.stt
            }
            for narrative_field, stt_key in [
                ("tong_so_vu_chay", "2"),
                ("tong_so_vu_no", "8"),
                ("tong_so_vu_cnch", "14"),
            ]:
                table_val = _stt_map.get(stt_key)
                if table_val is not None:
                    narrative_val = getattr(phan_nghiep_vu_data, narrative_field, 0)
                    if narrative_val != table_val:
                        logger.info(
                            "Sanity fix: %s narrative=%s → table stt_%s=%s",
                            narrative_field, narrative_val, stt_key, table_val,
                        )
                        setattr(phan_nghiep_vu_data, narrative_field, table_val)

            final_output = BlockExtractionOutput(
                header=header_data,
                phan_I_va_II_chi_tiet_nghiep_vu=phan_nghiep_vu_data,
                bang_thong_ke=bang_data_wrapper.danh_sach_chi_tieu,
                danh_sach_cnch=cnch_list,
                danh_sach_phuong_tien_hu_hong=pt_hu_hong,
                danh_sach_cong_van_tham_muu=cong_van,
            )

            self._validate_output(final_output)
            self.metrics.inc("pipeline_success")
            global_metrics.merge(self.metrics)

            return PipelineResult(
                status="ok",
                attempts=1,
                output=final_output,
                errors=[],
                business_data=business_data,
                metrics=self.metrics.to_dict(),
                # Carry the CNCH subsection text for Stage-2 LLM enrichment
                chi_tiet_cnch=phan_nghiep_vu_data.chi_tiet_cnch or "",
            )
        except Exception as exc:
            logger.error("Stage-1 block extraction failed: %s", exc)
            self.metrics.inc("pipeline_failure")
            global_metrics.merge(self.metrics)
            return PipelineResult(
                status="failed",
                attempts=1,
                errors=[str(exc)],
                metrics=self.metrics.to_dict(),
            )

    def run_from_bytes(self, pdf_bytes: bytes, filename: str) -> PipelineResult:
        del filename
        try:
            with self.metrics.timer("stage1_layout"):
                reconstructed_text, table_stream, layout_text = self._rebuild_layout(pdf_bytes)

            with self.metrics.timer("stage2_detect"):
                blocks = self._detect_blocks(reconstructed_text)

            with self.metrics.timer("stage3_extract"):
                header_data = self._extract_header(blocks["header"])
                header_data = self._enforce_schema(header_data, blocks["header"])
                phan_nghiep_vu_data = self._extract_narrative(blocks["phan_nghiep_vu"], layout_text=layout_text)
                bang_data_wrapper = self._extract_table(table_stream, blocks["bang_thong_ke"])
                # CNCH fallback: if LLM missed tong_so_vu_cnch, derive it from
                # the statistical table (same logic as BlockBusinessWorkflow.build_final_payload)
                phan_nghiep_vu_data = self._apply_cnch_fallback(
                    phan_nghiep_vu_data, bang_data_wrapper.danh_sach_chi_tieu
                )

            with self.metrics.timer("stage6_business"):
                # Stage 6 — business rules (testdoc flow integration)
                business_data = self._run_business_rules(
                    reconstructed_text, table_stream, header_data
                )

            # ── Extract arrays from narrative (LLM + regex fallback) ─────
            # Use layout_text for narrative array extraction when available,
            # as it preserves spatial reading order for incident details.
            with self.metrics.timer("stage_narrative_arrays"):
                narrative_for_arrays = layout_text if layout_text.strip() else blocks["phan_nghiep_vu"]
                cnch_list, pt_hu_hong, cong_van = self._extract_narrative_arrays(
                    narrative_for_arrays,
                    business_data,
                    chi_tiet_cnch=phan_nghiep_vu_data.chi_tiet_cnch,
                )
                # Derive tong_xe_hu_hong from list length if LLM missed it
                if not phan_nghiep_vu_data.tong_xe_hu_hong and pt_hu_hong:
                    phan_nghiep_vu_data.tong_xe_hu_hong = len(pt_hu_hong)
                # Derive tong_cong_van from list length if LLM missed it
                if not phan_nghiep_vu_data.tong_cong_van and cong_van:
                    phan_nghiep_vu_data.tong_cong_van = len(cong_van)

            # ── Sanity-check narrative counts against the stat table ──────
            # The stat table (bang_thong_ke) is the authoritative source for
            # counts like tong_so_vu_chay, tong_so_vu_no; narrative regex can
            # overcount if it matches unrelated numbers in the document text.
            _stt_map = {
                str(item.stt).strip(): item.ket_qua
                for item in bang_data_wrapper.danh_sach_chi_tieu
                if item.stt
            }
            for narrative_field, stt_key in [
                ("tong_so_vu_chay", "2"),
                ("tong_so_vu_no", "8"),
                ("tong_so_vu_cnch", "14"),
            ]:
                table_val = _stt_map.get(stt_key)
                if table_val is not None:
                    narrative_val = getattr(phan_nghiep_vu_data, narrative_field, 0)
                    if narrative_val != table_val:
                        logger.info(
                            "Sanity fix: %s narrative=%s → table stt_%s=%s",
                            narrative_field, narrative_val, stt_key, table_val,
                        )
                        setattr(phan_nghiep_vu_data, narrative_field, table_val)

            final_output = BlockExtractionOutput(
                header=header_data,
                phan_I_va_II_chi_tiet_nghiep_vu=phan_nghiep_vu_data,
                bang_thong_ke=bang_data_wrapper.danh_sach_chi_tieu,
                danh_sach_cnch=cnch_list,
                danh_sach_phuong_tien_hu_hong=pt_hu_hong,
                danh_sach_cong_van_tham_muu=cong_van,
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
