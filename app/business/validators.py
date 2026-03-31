"""Business data validators — check required fields, format, range, and cross-field rules.

Thresholds and field lists are loaded from the active DocumentTemplate when
provided; otherwise sensible defaults apply.
"""

from __future__ import annotations

import re
from typing import Any

from app.business.template_loader import DocumentTemplate, get_default_template

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _validate_date(value: str, year_min: int = 2020, year_max: int = 2030) -> str | None:
    """Return an error code if *value* is not a valid dd/mm/yyyy, else None."""
    m = _DATE_RE.match((value or "").strip())
    if not m:
        return "invalid_date_format"
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12):
        return "date_month_out_of_range"
    if not (1 <= day <= 31):
        return "date_day_out_of_range"
    if not (year_min <= year <= year_max):
        return "date_year_out_of_range"
    max_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if day > max_days[month - 1]:
        return "date_day_exceeds_month"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_business(
    data: dict[str, Any],
    tpl: DocumentTemplate | None = None,
) -> list[str]:
    """Return list of error codes for missing, malformed, or inconsistent fields."""

    t = tpl or get_default_template()
    year_min, year_max = t.year_range
    max_kq = t.max_ket_qua
    cross_tol = t.cross_field_tolerance
    non_neg_fields = t.non_negative_fields
    so_bao_cao_re = t.report_number_format_re

    errors: list[str] = []

    # ── Required-field presence ──────────────────────────────────────────
    if not data.get("so_bao_cao"):
        errors.append("missing_so_bao_cao")

    if not (data.get("ngay_bao_cao") or data.get("ngay")):
        errors.append("missing_ngay")

    if not data.get("don_vi"):
        errors.append("missing_don_vi")

    # ── Format validation ────────────────────────────────────────────────

    so_bc = data.get("so_bao_cao", "")
    if so_bc and not so_bao_cao_re.match(so_bc):
        errors.append("invalid_so_bao_cao_format")

    ngay = data.get("ngay_bao_cao") or data.get("ngay") or ""
    if ngay:
        date_err = _validate_date(ngay, year_min, year_max)
        if date_err:
            errors.append(date_err)

    thoi_gian = data.get("thoi_gian_tu_den", "")
    if thoi_gian and not re.search(r"\d{1,2}/\d{2}/\d{4}", thoi_gian):
        errors.append("invalid_thoi_gian_tu_den")

    # ── Numeric range validation ─────────────────────────────────────────
    for field in non_neg_fields:
        val = data.get(field)
        if val is not None and isinstance(val, (int, float)) and val < 0:
            errors.append(f"negative_{field}")

    # ── Cross-field rules ────────────────────────────────────────────────

    incidents = data.get("incidents") or []
    stat_incidents = [i for i in incidents if i.get("nguon") == "bang_thong_ke"]

    narrative_total = (
        (data.get("tong_so_vu_chay") or 0)
        + (data.get("tong_so_vu_no") or 0)
        + (data.get("tong_so_vu_cnch") or 0)
    )
    stat_total = sum(i.get("so_luong", 0) for i in stat_incidents)

    if narrative_total > 0 and stat_total > 0 and stat_total > narrative_total * cross_tol:
        errors.append("cross_field_incident_total_mismatch")

    for item in data.get("bang_thong_ke_raw", []):
        kq = item.get("ket_qua", 0) if isinstance(item, dict) else 0
        if isinstance(kq, (int, float)) and abs(kq) > max_kq:
            errors.append("ket_qua_out_of_range")
            break

    return errors
