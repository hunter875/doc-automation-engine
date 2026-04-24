from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.engines.extraction.schemas import BlockExtractionOutput


REQUIRED_TOP_LEVEL = {
    "header",
    "bang_thong_ke",
    "danh_sach_cnch",
    "danh_sach_cong_tac_khac",
    "danh_sach_cong_van_tham_muu",
    "danh_sach_phuong_tien_hu_hong",
    "phan_I_va_II_chi_tiet_nghiep_vu",
}

REQUIRED_HEADER_FIELDS = {
    "so_bao_cao",
    "ngay_bao_cao",
    "don_vi_bao_cao",
    "thoi_gian_tu_den",
}



def validate_schema_contract(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    missing_top = sorted(REQUIRED_TOP_LEVEL - set(payload.keys()))
    errors.extend([f"missing_top_level:{k}" for k in missing_top])

    header = payload.get("header")
    if not isinstance(header, dict):
        errors.append("invalid_header_type")
    else:
        missing_header = sorted(REQUIRED_HEADER_FIELDS - set(header.keys()))
        errors.extend([f"missing_header:{k}" for k in missing_header])

    if not isinstance(payload.get("bang_thong_ke"), list):
        errors.append("invalid_bang_thong_ke_type")
    if not isinstance(payload.get("danh_sach_cnch"), list):
        errors.append("invalid_danh_sach_cnch_type")
    if not isinstance(payload.get("danh_sach_cong_tac_khac"), list):
        errors.append("invalid_danh_sach_cong_tac_khac_type")
    if not isinstance(payload.get("danh_sach_cong_van_tham_muu"), list):
        errors.append("invalid_danh_sach_cong_van_tham_muu_type")
    if not isinstance(payload.get("danh_sach_phuong_tien_hu_hong"), list):
        errors.append("invalid_danh_sach_phuong_tien_hu_hong_type")
    if not isinstance(payload.get("phan_I_va_II_chi_tiet_nghiep_vu"), dict):
        errors.append("invalid_nghiep_vu_type")

    try:
        BlockExtractionOutput.model_validate(payload)
    except ValidationError as exc:
        for item in exc.errors():
            loc = ".".join(str(x) for x in item.get("loc", []))
            msg = item.get("msg", "validation error")
            errors.append(f"pydantic:{loc}:{msg}")

    return errors



def build_contract_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a stable regression snapshot from payload contract fields."""
    header = payload.get("header") or {}
    nghiep_vu = payload.get("phan_I_va_II_chi_tiet_nghiep_vu") or {}
    bang = payload.get("bang_thong_ke") or []

    stt_map: dict[str, int] = {}
    for row in bang:
        if not isinstance(row, dict):
            continue
        stt = str(row.get("stt", "")).strip()
        if not stt:
            continue
        val = row.get("ket_qua", 0)
        if isinstance(val, (int, float)):
            stt_map[stt] = int(val)

    return {
        "header": {
            "so_bao_cao": header.get("so_bao_cao", ""),
            "ngay_bao_cao": header.get("ngay_bao_cao", ""),
            "don_vi_bao_cao": header.get("don_vi_bao_cao", ""),
            "thoi_gian_tu_den": header.get("thoi_gian_tu_den", ""),
        },
        "sizes": {
            "bang_thong_ke": len(bang),
            "danh_sach_cnch": len(payload.get("danh_sach_cnch") or []),
            "danh_sach_phuong_tien_hu_hong": len(payload.get("danh_sach_phuong_tien_hu_hong") or []),
            "danh_sach_cong_van_tham_muu": len(payload.get("danh_sach_cong_van_tham_muu") or []),
            "danh_sach_cong_tac_khac": len(payload.get("danh_sach_cong_tac_khac") or []),
        },
        "key_metrics": {
            "stt_14": stt_map.get("14", 0),
            "stt_15": stt_map.get("15", 0),
            "stt_16": stt_map.get("16", 0),
            "stt_17": stt_map.get("17", 0),
            "stt_31": stt_map.get("31", 0),
            "stt_32": stt_map.get("32", 0),
            "stt_33": stt_map.get("33", 0),
            "stt_35": stt_map.get("35", 0),
            "stt_36": stt_map.get("36", 0),
            "stt_37": stt_map.get("37", 0),
            "stt_38": stt_map.get("38", 0),
            "stt_39": stt_map.get("39", 0),
            "stt_55": stt_map.get("55", 0),
            "stt_56": stt_map.get("56", 0),
            "stt_57": stt_map.get("57", 0),
            "stt_58": stt_map.get("58", 0),
            "stt_59": stt_map.get("59", 0),
            "stt_60": stt_map.get("60", 0),
            "stt_61": stt_map.get("61", 0),
            "tong_so_vu_chay": nghiep_vu.get("tong_so_vu_chay", 0),
            "tong_so_vu_no": nghiep_vu.get("tong_so_vu_no", 0),
            "tong_so_vu_cnch": nghiep_vu.get("tong_so_vu_cnch", 0),
            "tong_cong_van": nghiep_vu.get("tong_cong_van", 0),
            "tong_bao_cao": nghiep_vu.get("tong_bao_cao", 0),
            "tong_ke_hoach": nghiep_vu.get("tong_ke_hoach", 0),
            "tong_xe_hu_hong": nghiep_vu.get("tong_xe_hu_hong", 0),
            "cong_tac_an_ninh": nghiep_vu.get("cong_tac_an_ninh", ""),
        },
    }
