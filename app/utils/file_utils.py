"""Deterministic document splitter for normalized Vietnamese administrative reports."""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


class DocumentSplitter:
    """Split normalized report text into semantic blocks without any LLM usage."""

    _SECTION_I_RE = re.compile(r"^I\.\s+TÌNH HÌNH.*", re.IGNORECASE | re.MULTILINE)
    _SECTION_III_RE = re.compile(r"^III\.\s+TỔNG\s+QUÂN\s+SỐ.*", re.IGNORECASE | re.MULTILINE)
    _SIGNATURE_RE = re.compile(r"^(Nơi\s+nhận\s*:|Noi\s+nhan\s*:)", re.IGNORECASE | re.MULTILINE)

    def split_document(self, normalized_text: str) -> list[dict]:
        """Return ordered semantic blocks as [{'block_id': str, 'content': str}]."""
        try:
            if not isinstance(normalized_text, str):
                raise TypeError("normalized_text must be a string")

            if not normalized_text.strip():
                logger.warning("DocumentSplitter received empty normalized_text")
                return []

            text = normalized_text
            blocks: list[dict] = []

            section_i_start = self._find_start(self._SECTION_I_RE, text)
            section_iii_start = self._find_start(self._SECTION_III_RE, text)
            table_start = self._find_table_start(text)

            header_end = self._first_valid_index(section_i_start, section_iii_start, table_start, default=len(text))
            self._append_block(blocks, "header", text, 0, header_end)

            if section_i_start is not None:
                nghiep_vu_end = self._first_valid_index(
                    self._gt_or_none(section_iii_start, section_i_start),
                    self._gt_or_none(table_start, section_i_start),
                    default=len(text),
                )
                self._append_block(blocks, "nghiep_vu", text, section_i_start, nghiep_vu_end)

            if section_iii_start is not None:
                quan_so_end = self._first_valid_index(
                    self._gt_or_none(table_start, section_iii_start),
                    default=len(text),
                )
                self._append_block(blocks, "quan_so", text, section_iii_start, quan_so_end)

            if table_start is not None:
                signature_start = self._find_signature_start(text, table_start)
                table_end = signature_start if signature_start is not None else len(text)
                self._append_block(blocks, "bang_thong_ke", text, table_start, table_end)

            logger.info(
                "Document split completed: section_i=%s, section_iii=%s, table=%s, blocks=%s",
                section_i_start,
                section_iii_start,
                table_start,
                [b["block_id"] for b in blocks],
            )
            return blocks

        except Exception as exc:
            logger.exception("DocumentSplitter failed: %s", exc)
            return []

    @staticmethod
    def _find_start(pattern: re.Pattern[str], text: str) -> int | None:
        match = pattern.search(text)
        return match.start() if match else None

    @staticmethod
    def _gt_or_none(value: int | None, threshold: int) -> int | None:
        if value is None:
            return None
        return value if value > threshold else None

    @staticmethod
    def _first_valid_index(*indexes: int | None, default: int) -> int:
        valid = [idx for idx in indexes if idx is not None]
        return min(valid) if valid else default

    @staticmethod
    def _append_block(blocks: list[dict], block_id: str, text: str, start: int, end: int) -> None:
        if start < 0 or end <= start:
            return
        content = text[start:end]
        if not content.strip():
            return
        blocks.append({"block_id": block_id, "content": content})

    def _find_table_start(self, text: str) -> int | None:
        """Find table start where STT appears close to DANH MUC / CHI TIEU."""
        lines = text.splitlines(keepends=True)
        if not lines:
            return None

        offsets: list[int] = []
        cursor = 0
        for line in lines:
            offsets.append(cursor)
            cursor += len(line)

        for i, line in enumerate(lines):
            window = "".join(lines[i : i + 4])
            norm_window = self._normalize_for_match(window)
            norm_line = self._normalize_for_match(line)

            has_stt = "STT" in norm_line
            has_table_header = (
                "DANH MUC" in norm_window
                or "CHI TIEU" in norm_window
                or "CHI TIEU" in norm_line
                or "DANH MUC" in norm_line
            )

            if has_stt and has_table_header:
                return offsets[i]

        fallback_re = re.compile(r"^(.*\b(STT|DANH\s*M[UỤ]C|CH[ỈI]\s*TI[ÊE]U)\b.*)$", re.IGNORECASE | re.MULTILINE)
        match = fallback_re.search(text)
        return match.start() if match else None

    def _find_signature_start(self, text: str, search_from: int) -> int | None:
        match = self._SIGNATURE_RE.search(text, pos=search_from)
        return match.start() if match else None

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        text = unicodedata.normalize("NFD", text.upper())
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", text).strip()
