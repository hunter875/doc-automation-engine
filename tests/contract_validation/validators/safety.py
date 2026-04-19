from __future__ import annotations

import re
from typing import Any



def validate_safety(payload: dict[str, Any]) -> list[str]:
    violations: list[str] = []

    nghiep_vu = payload.get("phan_I_va_II_chi_tiet_nghiep_vu") or {}
    docs = payload.get("danh_sach_cong_van_tham_muu") or []
    incidents = payload.get("danh_sach_cnch") or []

    # No hallucinated placeholder values.
    header = payload.get("header") or {}
    for field in ("so_bao_cao", "ngay_bao_cao", "don_vi_bao_cao"):
        val = str(header.get(field, "")).strip().lower()
        if val in {"unknown", "n/a", "na", "none", "null"}:
            violations.append(f"hallucination_placeholder:{field}")

    # If totals are positive, there must be source evidence in list/details.
    if int(nghiep_vu.get("tong_cong_van", 0) or 0) > 0 and not docs:
        violations.append("hallucination_total_without_evidence:tong_cong_van")
    if int(nghiep_vu.get("tong_so_vu_cnch", 0) or 0) > 0 and not incidents:
        detail = str(nghiep_vu.get("chi_tiet_cnch", "")).strip().lower()
        if "khong" in detail or "không" in detail:
            violations.append("hallucination_total_without_evidence:tong_so_vu_cnch")

    # Document items must not contain fake/empty IDs when content exists.
    for idx, item in enumerate(docs, start=1):
        if not isinstance(item, dict):
            continue
        code = str(item.get("so_ky_hieu", "")).strip()
        content = str(item.get("noi_dung", "")).strip()
        if content and not code:
            violations.append(f"invalid_document_item_missing_code:{idx}")
        if code and not re.search(r"\d", code):
            violations.append(f"invalid_document_item_code_no_digit:{idx}")

    # Missing critical fields must be explicit and catchable.
    required = [
        ("header", "so_bao_cao"),
        ("header", "ngay_bao_cao"),
        ("header", "don_vi_bao_cao"),
        ("phan_I_va_II_chi_tiet_nghiep_vu", "tong_so_vu_chay"),
        ("phan_I_va_II_chi_tiet_nghiep_vu", "tong_so_vu_no"),
        ("phan_I_va_II_chi_tiet_nghiep_vu", "tong_so_vu_cnch"),
    ]

    for root_key, field in required:
        root = payload.get(root_key)
        if not isinstance(root, dict) or field not in root:
            violations.append(f"missing_required_field:{root_key}.{field}")

    return violations
