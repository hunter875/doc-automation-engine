from __future__ import annotations

import re
from datetime import date
from typing import Any


_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")



def _to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return default



def _parse_date(text: str) -> date | None:
    if not isinstance(text, str):
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mth, d)
    except ValueError:
        return None



def _extract_period_range(text: str) -> tuple[date, date] | None:
    if not isinstance(text, str):
        return None
    all_dates: list[date] = []
    for dm, mm, yy in _DATE_RE.findall(text):
        try:
            all_dates.append(date(int(yy), int(mm), int(dm)))
        except ValueError:
            continue
    if len(all_dates) < 2:
        return None
    return (min(all_dates), max(all_dates))



def _build_stt_map(payload: dict[str, Any]) -> dict[str, int]:
    stt_map: dict[str, int] = {}
    for row in payload.get("bang_thong_ke") or []:
        if not isinstance(row, dict):
            continue
        stt = str(row.get("stt", "")).strip()
        if not stt:
            continue
        stt_map[stt] = _to_int(row.get("ket_qua"), 0)
    return stt_map



def _classify_documents(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"tong_cong_van": 0, "tong_bao_cao": 0, "tong_ke_hoach": 0}
    for item in items:
        if not isinstance(item, dict):
            continue
        code = re.sub(r"\s+", "", str(item.get("so_ky_hieu", "") or "")).upper()
        if re.search(r"(^|/)BC(?:[-/]|$)", code):
            counts["tong_bao_cao"] += 1
        elif re.search(r"(^|/)KH(?:[-/]|$)", code):
            counts["tong_ke_hoach"] += 1
        elif code:
            counts["tong_cong_van"] += 1
    return counts



def validate_invariants(payload: dict[str, Any]) -> list[str]:
    violations: list[str] = []

    stt_map = _build_stt_map(payload)
    nghiep_vu = payload.get("phan_I_va_II_chi_tiet_nghiep_vu") or {}
    header = payload.get("header") or {}

    required_stt = ["14", "15", "16", "17", "31", "32", "33", "35", "36", "37", "38", "39", "55", "56", "57", "58", "59", "60", "61"]
    for key in required_stt:
        if key not in stt_map:
            violations.append(f"missing_stt:{key}")

    # Formula invariants
    if stt_map.get("15", 0) != stt_map.get("16", 0) + stt_map.get("17", 0):
        violations.append("formula_mismatch:stt15!=stt16+stt17")
    if stt_map.get("31", 0) != stt_map.get("32", 0) + stt_map.get("33", 0):
        violations.append("formula_mismatch:stt31!=stt32+stt33")
    if stt_map.get("35", 0) != stt_map.get("36", 0) + stt_map.get("37", 0) + stt_map.get("38", 0) + stt_map.get("39", 0):
        violations.append("formula_mismatch:stt35!=sum(stt36..stt39)")
    if stt_map.get("55", 0) != (
        stt_map.get("56", 0)
        + stt_map.get("57", 0)
        + stt_map.get("58", 0)
        + stt_map.get("59", 0)
        + stt_map.get("60", 0)
        + stt_map.get("61", 0)
    ):
        violations.append("formula_mismatch:stt55!=sum(stt56..stt61)")

    # Root consistency with stat table summary rows
    if _to_int(nghiep_vu.get("tong_so_vu_chay")) != stt_map.get("2", 0):
        violations.append("root_mismatch:tong_so_vu_chay!=stt2")
    if _to_int(nghiep_vu.get("tong_so_vu_no")) != stt_map.get("8", 0):
        violations.append("root_mismatch:tong_so_vu_no!=stt8")
    if _to_int(nghiep_vu.get("tong_so_vu_cnch")) != stt_map.get("14", 0):
        violations.append("root_mismatch:tong_so_vu_cnch!=stt14")

    # List totals
    vehicles = payload.get("danh_sach_phuong_tien_hu_hong") or []
    if _to_int(nghiep_vu.get("tong_xe_hu_hong")) != len(vehicles):
        violations.append("count_mismatch:tong_xe_hu_hong!=len(danh_sach_phuong_tien_hu_hong)")

    docs = payload.get("danh_sach_cong_van_tham_muu") or []
    doc_counts = _classify_documents(docs)
    if _to_int(nghiep_vu.get("tong_cong_van")) != doc_counts["tong_cong_van"]:
        violations.append("count_mismatch:tong_cong_van")
    if _to_int(nghiep_vu.get("tong_bao_cao")) != doc_counts["tong_bao_cao"]:
        violations.append("count_mismatch:tong_bao_cao")
    if _to_int(nghiep_vu.get("tong_ke_hoach")) != doc_counts["tong_ke_hoach"]:
        violations.append("count_mismatch:tong_ke_hoach")

    # Date range consistency
    period = _extract_period_range(str(header.get("thoi_gian_tu_den", "")))
    report_date = _parse_date(str(header.get("ngay_bao_cao", "")))
    if period and report_date:
        if not (period[0] <= report_date <= period[1]):
            violations.append("date_mismatch:ngay_bao_cao_outside_period")

    if period:
        for idx, incident in enumerate(payload.get("danh_sach_cnch") or [], start=1):
            if not isinstance(incident, dict):
                continue
            d = _parse_date(str(incident.get("ngay_xay_ra", "")))
            if d and not (period[0] <= d <= period[1]):
                violations.append(f"date_mismatch:danh_sach_cnch[{idx}].ngay_xay_ra_outside_period")

    # Duplicate incident signatures
    seen: set[tuple[str, str, str, str]] = set()
    for idx, incident in enumerate(payload.get("danh_sach_cnch") or [], start=1):
        if not isinstance(incident, dict):
            continue
        sig = (
            str(incident.get("thoi_gian", "")).strip(),
            str(incident.get("ngay_xay_ra", "")).strip(),
            str(incident.get("dia_diem", "")).strip(),
            str(incident.get("noi_dung_tin_bao", "")).strip(),
        )
        if sig in seen and any(sig):
            violations.append(f"duplicate_incident_signature:{idx}")
        seen.add(sig)

    # Text hygiene
    an_ninh = str(nghiep_vu.get("cong_tac_an_ninh", "")).strip()
    if re.match(r"^(?:P?CCC)\s*:\s*", an_ninh, re.IGNORECASE):
        violations.append("text_hygiene:cong_tac_an_ninh_has_prefix")

    return violations
