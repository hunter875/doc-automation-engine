"""Business field extractors — regex-based deterministic extraction from structured data.

All document-specific patterns are loaded from the active DocumentTemplate.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.domain.templates.template_loader import DocumentTemplate, get_default_template


def _get_tpl(tpl: DocumentTemplate | None) -> DocumentTemplate:
    return tpl or get_default_template()


def extract_metadata_from_header(
    header_text: str,
    tpl: DocumentTemplate | None = None,
) -> dict[str, str]:
    """Extract so_bao_cao, ngay_bao_cao, don_vi from header text using template regex."""

    t = _get_tpl(tpl)
    data: dict[str, str] = {}

    # Report number
    m = t.report_number_primary_re.search(header_text)
    if m:
        raw = m.group(1).strip()
        raw = re.sub(r"\s*/\s*", "/", raw)
        raw = re.sub(r"\s+", "", raw)
        data["so_bao_cao"] = raw
    else:
        m2 = t.report_number_fallback_re.search(header_text)
        if m2:
            data["so_bao_cao"] = re.sub(r"\s+", "", m2.group(1).strip())

    # Normalize spaced slash-dates
    text_norm = re.sub(r"(\d{1,2})\s*/\s*(\d{2})\s*/\s*(\d{4})", r"\1/\2/\3", header_text)

    # 1st: long-form date
    m = t.date_long_form_re.search(text_norm)
    if m:
        data["ngay_bao_cao"] = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    else:
        # 2nd: short-form date — skip period lines
        period_markers = t.date_period_markers
        for line in text_norm.splitlines():
            if any(marker in line for marker in period_markers):
                continue
            m2 = t.date_short_form_re.search(line)
            if m2:
                parts = m2.group(1).split("/")
                data["ngay_bao_cao"] = f"{int(parts[0]):02d}/{parts[1]}/{parts[2]}"
                break

    # Unit / don_vi
    for pat in t.unit_patterns:
        m = pat.search(header_text)
        if m:
            data["don_vi"] = m.group(0).strip()
            break

    return data


def extract_summary_from_sections(
    sections: dict[str, list[str]],
    tpl: DocumentTemplate | None = None,
) -> dict[str, str]:
    """Extract summary text from sections matching the template keyword."""

    t = _get_tpl(tpl)
    kw = t.summary_section_keyword.upper()
    max_lines = t.summary_max_lines

    for name, content in sections.items():
        if kw in name.upper():
            return {"summary_text": " ".join(content[:max_lines])}

    return {}


def extract_incidents_from_narrative(
    sections: dict[str, list[str]],
    tpl: DocumentTemplate | None = None,
) -> list[dict[str, str]]:
    """Extract CNCH incident details (time + location) from narrative text."""

    t = _get_tpl(tpl)
    kw = t.summary_section_keyword.upper()
    ctx_chars = t.incident_context_chars
    loc_max = t.incident_location_max_chars
    time_re = t.incident_time_re
    loc_re = t.incident_location_re
    desc_re = t.incident_description_re

    incidents: list[dict[str, str]] = []

    for name, lines in sections.items():
        if kw not in name.upper():
            continue

        text = re.sub(r"(\d{1,2})\s*/\s*(\d{2})\s*/\s*(\d{4})", r"\1/\2/\3", "\n".join(lines))

        for m in time_re.finditer(text):
            thoi_gian = f"{int(m.group(1)):02d}:{m.group(2)} ngày {m.group(3)}"
            context = text[m.start(): m.start() + ctx_chars]

            dia_diem_m = loc_re.search(context)
            dia_diem = re.sub(r"\s+", " ", dia_diem_m.group(1)).strip()[:loc_max] if dia_diem_m else ""

            mo_ta_m = desc_re.search(context)
            mo_ta = re.sub(r"\s+", " ", mo_ta_m.group(0)).strip() if mo_ta_m else ""

            incidents.append({
                "thoi_gian": thoi_gian,
                "dia_diem": dia_diem,
                "mo_ta": mo_ta,
                "nguon": "narrative",
            })

    return incidents


def extract_incidents_from_stat_table(
    tables: list[dict[str, Any]],
    tpl: DocumentTemplate | None = None,
) -> list[dict[str, Any]]:
    """Extract CNCH / tai-nan count rows from the statistical reporting table."""

    t = _get_tpl(tpl)
    patterns_all = t.incident_row_patterns_spaced + t.incident_row_patterns_compact
    incidents: list[dict[str, Any]] = []

    def _ascii_upper(text: str) -> str:
        n = unicodedata.normalize("NFD", text.upper())
        n = "".join(ch for ch in n if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", n).strip()

    for table in tables:
        for row in table.get("rows", []):
            if not row or len(row) < 2:
                continue

            match_text = " ".join(str(c or "") for c in row[:2])
            noi_dung_raw = str(row[1] if len(row) > 1 else row[0] or "").strip()
            norm = _ascii_upper(match_text)
            norm_compact = re.sub(r"[\s\W]", "", norm)

            ket_qua_raw = str(row[2]).strip() if len(row) > 2 else ""
            try:
                ket_qua = int(ket_qua_raw) if ket_qua_raw.lstrip("-").isdigit() else 0
            except Exception:
                ket_qua = 0

            matched = any(pat in norm for pat in patterns_all) or any(
                re.sub(r"\W", "", pat) in norm_compact for pat in patterns_all
            )
            if matched and ket_qua > 0:
                incidents.append({
                    "noi_dung": noi_dung_raw.strip(),
                    "so_luong": ket_qua,
                    "nguon": "bang_thong_ke",
                })

    return incidents


def extract_incidents_from_tables(
    tables: list[dict[str, Any]],
    tpl: DocumentTemplate | None = None,
) -> list[dict[str, str]]:
    """Extract incident rows from structured tables with dynamic header detection."""

    t = _get_tpl(tpl)
    target_headers = t.structured_incident_headers
    incidents: list[dict[str, str]] = []

    for table in tables:
        rows = table.get("rows", [])
        if not rows or len(rows) < 2:
            continue

        header = " ".join(c or "" for c in rows[0])

        if all(h in header for h in target_headers):
            for r in rows[1:]:
                incidents.append({
                    "dia_diem": r[1] if len(r) > 1 else "",
                    "nguyen_nhan": r[2] if len(r) > 2 else "",
                    "thiet_hai": r[3] if len(r) > 3 else "",
                })

    return incidents


def build_document_graph(sections: dict[str, Any], tables: list[Any]) -> dict[str, Any]:
    """Build a lightweight document structure graph."""

    return {
        "sections": list(sections.keys()),
        "table_count": len(tables),
    }
