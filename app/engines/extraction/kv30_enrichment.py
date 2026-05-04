"""KV30 read-time enrichment: normalize Date(...) strings, fill header defaults."""

import re
from datetime import datetime, timedelta
from typing import Any


def _normalize_google_sheets_datetime(value: str) -> str:
    """Convert 'Date(2026,3,9) 22:36' -> '22:36 ngày 09/04/2026'.

    Google Sheets Date format has 0-indexed month (0=Jan, 11=Dec).
    """
    if not isinstance(value, str) or not value.startswith("Date("):
        return value

    # Extract: Date(year,month,day) time
    match = re.match(r"Date\((\d+),(\d+),(\d+)\)\s*(.+)?", value)
    if not match:
        return value

    year = int(match.group(1))
    month = int(match.group(2)) + 1  # Convert 0-indexed to 1-indexed
    day = int(match.group(3))
    time_part = match.group(4).strip() if match.group(4) else ""

    if time_part:
        return f"{time_part} ngày {day:02d}/{month:02d}/{year:04d}"
    return f"{day:02d}/{month:02d}/{year:04d}"


def _parse_report_date(date_str: str) -> datetime | None:
    """Parse DD/MM/YYYY to datetime."""
    if not date_str:
        return None
    try:
        parts = date_str.split("/")
        if len(parts) == 3:
            return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
        elif len(parts) == 2:
            return datetime(2026, int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        pass
    return None


def enrich_kv30_block_output(data: dict, report_date: str | None = None, defaults: dict | None = None) -> dict:
    """Enrich KV30 BlockExtractionOutput for display/export.

    - Fill header.don_vi_bao_cao if blank
    - Fill header.thoi_gian_tu_den if blank
    - Normalize Date(...) strings in detail items
    - Alias danh_sach_sclq -> danh_sach_su_co

    Args:
        data: BlockExtractionOutput.model_dump()
        report_date: DD/MM/YYYY or DD/MM
        defaults: Optional config overrides

    Returns:
        Enriched data dict (mutates in place)
    """
    defaults = defaults or {}
    header = data.setdefault("header", {})

    # Fill don_vi_bao_cao
    if not header.get("don_vi_bao_cao"):
        header["don_vi_bao_cao"] = defaults.get("don_vi_bao_cao", "ĐỘI CC&CNCH KHU VỰC 30")

    # Fill thoi_gian_tu_den
    if not header.get("thoi_gian_tu_den") and report_date:
        dt = _parse_report_date(report_date)
        if dt:
            prev_dt = dt - timedelta(days=1)
            header["thoi_gian_tu_den"] = (
                f"Từ 07 h 30' ngày {prev_dt.day:02d}/{prev_dt.month:02d}/{prev_dt.year:04d} "
                f"đến 07 h 30' ngày {dt.day:02d}/{dt.month:02d}/{dt.year:04d}"
            )

    # Normalize Date(...) in detail items
    for section in ["danh_sach_cnch", "danh_sach_chi_vien", "danh_sach_chay", "danh_sach_sclq"]:
        items = data.get(section, [])
        for item in items:
            if not isinstance(item, dict):
                continue
            for key, val in item.items():
                if isinstance(val, str) and "Date(" in val:
                    item[key] = _normalize_google_sheets_datetime(val)

    # Alias danh_sach_sclq -> danh_sach_su_co
    if "danh_sach_sclq" in data and "danh_sach_su_co" not in data:
        data["danh_sach_su_co"] = data["danh_sach_sclq"]

    return data
