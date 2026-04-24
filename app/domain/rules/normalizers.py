"""Business data normalizers — clean and standardize extracted values."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


# ---------------------------------------------------------------------------
# Text cleaning helpers
# ---------------------------------------------------------------------------

def _restore_vn_word_spacing(text: str) -> str:
    """Insert missing spaces in Vietnamese text concatenated by pdfplumber.

    Handles: lowercase→uppercase ("cháyTổng" → "cháy Tổng"),
    letter→digit ("cháy3" → "cháy 3"), digit→letter ("3Tổng" → "3 Tổng"),
    punctuation→letter ("cháy,Nổ" → "cháy, Nổ").
    """
    if not text:
        return text
    # lowercase Vietnamese → uppercase (word boundary)
    text = re.sub(
        r"([a-zàáạảãăắằẵặẳâấầẫậẩđèéẹẻẽêếềễệểìíịỉĩòóọỏõôốồỗộổơớờỡợởùúụủũưứừữựửỳýỵỷỹ])"
        r"([A-ZÀÁẠẢÃĂẮẰẴẶẲÂẤẦẪẬẨĐÈÉẸẺẼÊẾỀỄỆỂÌÍỊỈĨÒÓỌỎÕÔỐỒỖỘỔƠỚỜỠỢỞÙÚỤỦŨƯỨỪỮỰỬỲÝỴỶỸ])",
        r"\1 \2",
        text,
    )
    # letter ↔ digit boundaries
    text = re.sub(r"([A-Za-zÀ-ỹ])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([A-Za-zÀ-ỹ])", r"\1 \2", text)
    # punctuation (.,;:) followed by non-space, non-digit → add space
    text = re.sub(r"([.,;:)])([^\s\d).,;:])", r"\1 \2", text)
    # opening paren stuck to previous word: "word(" → "word ("
    text = re.sub(r"([A-Za-zÀ-ỹ])\(", r"\1 (", text)
    return text


def _collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space and strip."""
    return re.sub(r"\s+", " ", text).strip() if text else ""


def _clean_date(value: str) -> str:
    """Normalize a dd/mm/yyyy date string: fix spaced slashes, strip noise."""
    if not value:
        return value
    # "21 / 03 / 2026" → "21/03/2026"
    value = re.sub(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", r"\1/\2/\3", value)
    # Zero-pad day/month: "1/3/2026" → "01/03/2026"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value.strip())
    if m:
        value = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    return value.strip()


def _clean_thoi_gian_tu_den(value: str) -> str:
    """Normalize the reporting-period string."""
    if not value:
        return value
    # Fix spaced slashes inside dates
    value = re.sub(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", r"\1/\2/\3", value)
    return _collapse_whitespace(value)


def _clean_chi_tiet_cnch(value: str) -> str:
    """Clean CNCH incident detail text: restore spacing, trim."""
    if not value:
        return value
    value = _restore_vn_word_spacing(value)
    value = _collapse_whitespace(value)
    return value


def _clean_noi_dung(value: str) -> str:
    """Clean a statistical-table noi_dung cell: restore spacing, strip junk."""
    if not value:
        return value
    value = _restore_vn_word_spacing(value)
    value = _collapse_whitespace(value)
    # Strip leading/trailing punctuation leftovers
    value = value.strip(" .:-")
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_business(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize whitespace, formatting, and spacing in all business fields."""

    normalized = dict(data)

    # ── Metadata fields ──────────────────────────────────────────────────
    if normalized.get("so_bao_cao"):
        normalized["so_bao_cao"] = re.sub(r"\s+", "", normalized["so_bao_cao"])

    if normalized.get("don_vi"):
        normalized["don_vi"] = _collapse_whitespace(normalized["don_vi"])

    if normalized.get("summary_text"):
        text = _restore_vn_word_spacing(normalized["summary_text"])
        normalized["summary_text"] = _collapse_whitespace(text)

    # ── Date / period fields ─────────────────────────────────────────────
    if normalized.get("ngay_bao_cao"):
        normalized["ngay_bao_cao"] = _clean_date(normalized["ngay_bao_cao"])

    if normalized.get("ngay"):
        normalized["ngay"] = _clean_date(normalized["ngay"])

    if normalized.get("thoi_gian_tu_den"):
        normalized["thoi_gian_tu_den"] = _clean_thoi_gian_tu_den(normalized["thoi_gian_tu_den"])

    # ── Narrative fields ─────────────────────────────────────────────────
    if normalized.get("chi_tiet_cnch"):
        normalized["chi_tiet_cnch"] = _clean_chi_tiet_cnch(normalized["chi_tiet_cnch"])
    # ── Bang thong ke noi_dung cells ────────────────────────────────
    btk = normalized.get("bang_thong_ke")
    if isinstance(btk, list):
        for btk_item in btk:
            if not isinstance(btk_item, dict):
                continue
            if btk_item.get("noi_dung"):
                btk_item["noi_dung"] = _clean_noi_dung(btk_item["noi_dung"])
    # ── Incidents ────────────────────────────────────────────────────────
    incidents = normalized.get("incidents")
    if isinstance(incidents, list):
        for inc in incidents:
            if not isinstance(inc, dict):
                continue
            if inc.get("noi_dung"):
                inc["noi_dung"] = _clean_noi_dung(inc["noi_dung"])
            if inc.get("dia_diem"):
                inc["dia_diem"] = _collapse_whitespace(
                    _restore_vn_word_spacing(inc["dia_diem"])
                )
            if inc.get("mo_ta"):
                inc["mo_ta"] = _collapse_whitespace(
                    _restore_vn_word_spacing(inc["mo_ta"])
                )

    return normalized
