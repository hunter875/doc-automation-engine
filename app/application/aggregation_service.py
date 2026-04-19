"""Aggregation & Export service for Engine 2.

Handles the Reduce phase: merge N extraction JSONs → 1 report.
Uses Pandas for computation. AI is NOT involved in this step.
"""

import io
import itertools
import logging
import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.domain.models.extraction_job import (
    AggregationReport,
    ExtractionJob,
    ExtractionJobStatus,
    ExtractionTemplate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# STT number → Word-template named-field mapping
# Derived from worđoclayout.txt (the authoritative Word template field list).
# ---------------------------------------------------------------------------
WORD_STT_MAP: dict[int, str] = {
    2: "stt_02_tong_chay",
    3: "stt_03_chay_chet",
    4: "stt_04_chay_thuong",
    5: "stt_05_chay_cuu_nguoi",
    6: "stt_06_chay_thiet_hai",
    7: "stt_07_chay_cuu_tai_san",
    8: "stt_08_tong_no",
    9: "stt_09_no_chet",
    10: "stt_10_no_thuong",
    11: "stt_11_no_cuu_nguoi",
    12: "stt_12_no_thiet_hai",
    13: "stt_13_no_cuu_tai_san",
    14: "stt_14_tong_cnch",
    15: "stt_15_cnch_cuu_nguoi",
    16: "stt_16_cnch_truc_tiep",
    17: "stt_17_cnch_tu_thoat",
    18: "stt_18_cnch_thi_the",
    19: "stt_19_cnch_cuu_tai_san",
    22: "stt_22_tt_mxh_tong",
    23: "stt_23_tt_mxh_tin_bai",
    24: "stt_24_tt_mxh_hinh_anh",
    25: "stt_25_tt_mxh_video",
    27: "stt_27_tt_so_cuoc",
    28: "stt_28_tt_so_nguoi",
    29: "stt_29_tt_to_roi",
    31: "stt_31_kiem_tra_tong",
    32: "stt_32_kiem_tra_dinh_ky",
    33: "stt_33_kiem_tra_dot_xuat",
    34: "stt_34_vi_pham_phat_hien",
    35: "stt_35_xu_phat_tong",
    36: "stt_36_xu_phat_canh_cao",
    37: "stt_37_xu_phat_tam_dinh_chi",
    38: "stt_38_xu_phat_dinh_chi",
    39: "stt_39_xu_phat_tien_mat",
    40: "stt_40_xu_phat_tien",
    43: "stt_43_pa_co_so_duyet",
    44: "stt_44_pa_co_so_thuc_tap",
    46: "stt_46_pa_giao_thong_duyet",
    47: "stt_47_pa_giao_thong_thuc_tap",
    49: "stt_49_pa_cong_an_duyet",
    50: "stt_50_pa_cong_an_thuc_tap",
    52: "stt_52_pa_cnch_ca_duyet",
    53: "stt_53_pa_cnch_ca_thuc_tap",
    55: "stt_55_hl_tong_cbcs",
    56: "stt_56_hl_chi_huy_phong",
    57: "stt_57_hl_chi_huy_doi",
    58: "stt_58_hl_can_bo_tieu_doi",
    59: "stt_59_hl_chien_sy",
    60: "stt_60_hl_lai_xe",
    61: "stt_61_hl_lai_tau",
}

STT_DISPLAY_LABELS: dict[int, str] = {
    15: "Số người cứu được (=STT 16+STT 17)",
    32: "Kiểm tra định kỳ",
    33: "Kiểm tra đột xuất theo chuyên đề",
    35: "Tổng số cơ sở bị xử phạt VPHC về PCCC (=STT 36+…+STT 39)",
    55: "Tổng số CBCS tham gia huấn luyện (=STT 56+…+STT 61)",
    60: "Lái xe CC và CNCH",
}

WORD_STT_REVERSE_MAP: dict[str, int] = {field_name: stt for stt, field_name in WORD_STT_MAP.items()}

# ---------------------------------------------------------------------------
# Block-output → Word template field expansion helpers
# ---------------------------------------------------------------------------

def _expand_header_subfields(context: dict[str, Any]) -> None:
    """Flatten BlockHeader nested dict and parse date parts into top-level keys.

    Handles:
      • header.{so_bao_cao, ngay_bao_cao, thoi_gian_tu_den, don_vi_bao_cao}
        → promoted to top-level (setdefault so existing values win)
      • header.ngay_bao_cao  (DD/MM/YYYY)
        → ngay_xuat, thang_xuat, nam_xuat
      • header.thoi_gian_tu_den  ("… ngày DD/MM/YYYY đến DD/MM/YYYY")
        → tu_ngay, den_ngay
    """
    header = context.get("header")
    if not isinstance(header, dict):
        return

    for k, v in header.items():
        context.setdefault(k, v)

    # Parse ngay_bao_cao → ngay_xuat / thang_xuat / nam_xuat 
    ngay = str(header.get("ngay_bao_cao") or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", ngay)
    if m:
        # Overwrite if current value is falsy (empty string from _normalize_master_payload)
        if not context.get("ngay_xuat"):
            context["ngay_xuat"] = m.group(1)
        if not context.get("thang_xuat"):
            context["thang_xuat"] = m.group(2)
        if not context.get("nam_xuat"):
            context["nam_xuat"] = m.group(3)

    # Parse thoi_gian_tu_den → tu_ngay, den_ngay
    # Typical formats: "07h30' ngày 01/03/2026 đến 31/03/2026"
    #                  "01/03/2026 - 31/03/2026"
    tu_den_raw = str(header.get("thoi_gian_tu_den") or "").strip()
    if tu_den_raw:
        dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", tu_den_raw)
        if len(dates) >= 2:
            if not context.get("tu_ngay"):
                context["tu_ngay"] = dates[0]
            if not context.get("den_ngay"):
                context["den_ngay"] = dates[1]
        elif len(dates) == 1:
            if not context.get("tu_ngay"):
                context["tu_ngay"] = dates[0]


def _expand_nghiep_vu_subfields(context: dict[str, Any]) -> None:
    """Flatten BlockNghiepVu nested dict into top-level keys.

    Tries both the block-pipeline key and the hybrid-pipeline key.
    """
    for nghiep_vu_key in ("phan_I_va_II_chi_tiet_nghiep_vu", "narrative"):
        nghiep_vu = context.get(nghiep_vu_key)
        if isinstance(nghiep_vu, dict):
            for k, v in nghiep_vu.items():
                context.setdefault(k, v)
            break

    # tong_su_co: computed = chay + no + cnch (silently skip if any missing)
    if not context.get("tong_su_co"):
        try:
            context["tong_su_co"] = (
                int(context.get("tong_so_vu_chay") or 0)
                + int(context.get("tong_so_vu_no") or 0)
                + int(context.get("tong_so_vu_cnch") or 0)
            )
        except (TypeError, ValueError):
            pass


def _expand_bang_thong_ke_fields(context: dict[str, Any]) -> None:
    """Fan out bang_thong_ke list into semantic named keys only.

    For each ``{stt, noi_dung, ket_qua}`` entry:
      • Creates ONLY the semantic named key (e.g. ``stt_02_tong_chay``)
        via WORD_STT_MAP lookup.
      • Generic ``stt_{N:02d}`` keys are NOT created — they have no semantic
        meaning and break aggregation (you cannot SUM stt_14 without knowing
        what it represents).

    ``setdefault`` is used so aggregation-rule results take priority.
    """
    btk = context.get("bang_thong_ke")
    if not isinstance(btk, list):
        return

    word_stt_map: dict[int, str] = context.pop("_word_stt_map", None) or WORD_STT_MAP

    for item in btk:
        if not isinstance(item, dict):
            continue
        stt_raw = str(item.get("stt", "")).strip()
        if not stt_raw:
            continue
        try:
            stt_num = int(stt_raw)
        except ValueError:
            continue
        ket_qua = item.get("ket_qua", 0)
        if ket_qua is None:
            ket_qua = 0

        if stt_num in word_stt_map:
            context.setdefault(word_stt_map[stt_num], ket_qua)


def flatten_block_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Add flat Word-template keys alongside nested block extraction output.

    Original nested keys (``header``, ``phan_I_va_II_chi_tiet_nghiep_vu``,
    ``bang_thong_ke``) are preserved so the review UI can still render them.
    Flat keys (``ngay_xuat``, ``stt_02_tong_chay``, ``tong_so_vu_chay``, …)
    are added via ``setdefault`` so that both simple SUM aggregation and
    Word template rendering work without extra transformation.
    """
    if not isinstance(payload, dict):
        return payload
    # Only run on block-pipeline outputs
    if "header" not in payload and "bang_thong_ke" not in payload:
        return payload

    flat = dict(payload)
    _expand_header_subfields(flat)
    _expand_nghiep_vu_subfields(flat)
    _expand_bang_thong_ke_fields(flat)
    return flat


def build_word_export_context(
    aggregated_data: dict[str, Any],
    *,
    record_index: int | None = None,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a clean DTO for Word rendering from aggregation payload.

    Export layer should receive a template-ready context only, without touching
    internal aggregation keys.
    """
    strip_keys = {"_source_records", "_flat_records", "_metadata", "metrics"}
    payload = aggregated_data or {}

    records = payload.get("records", [])
    safe_records = records if isinstance(records, list) else []

    context: dict[str, Any] = {
        "records": safe_records,
    }

    selected_record: dict[str, Any] = {}
    selected_index = int(record_index or 0)
    if safe_records:
        if 0 <= selected_index < len(safe_records) and isinstance(safe_records[selected_index], dict):
            selected_record = dict(safe_records[selected_index])
        elif isinstance(safe_records[0], dict):
            selected_record = dict(safe_records[0])
            selected_index = 0

    context["record"] = selected_record
    context["record_index"] = selected_index

    if selected_record:
        context.update(selected_record)

    for key, value in payload.items():
        if key in strip_keys or key.startswith("_") or key == "records":
            continue
        # setdefault: selected_record values take priority over aggregated_data
        # (aggregated_data may contain empty-string defaults from _normalize_master_payload)
        context.setdefault(key, value)

    if extra_context:
        context.update(extra_context)

    # ── Block-output flattening (safe no-op for non-block payloads) ──────────
    _expand_header_subfields(context)
    _expand_nghiep_vu_subfields(context)
    _expand_bang_thong_ke_fields(context)

    # ── Normalise legacy vehicle list: strings → {bien_so, tinh_trang} dicts ─
    _normalize_phuong_tien_list(context)

    return context


def _normalize_phuong_tien_list(context: dict[str, Any]) -> None:
    """Convert danh_sach_phuong_tien_hu_hong to list-of-dicts in-place.

    Handles two legacy formats stored in old DB reports:
      • list of plain strings  ("Xe chữa cháy 61A-003.52")
      • list of dicts with "Xe "-prefixed bien_so

    After normalisation every item is {"bien_so": ..., "tinh_trang": ...}
    and bien_so no longer carries a leading "xe/Xe " token because the Word
    template already writes the static "Xe" before the variable.
    """
    vehicles = context.get("danh_sach_phuong_tien_hu_hong")
    if not isinstance(vehicles, list):
        return

    _pt_plate = re.compile(r'(\d{2})\s*([A-Z]{1,2})\s*[-]\s*(\d{3}\.\d{2})', re.IGNORECASE)

    def _parse_pt(raw: str) -> dict:
        clean = re.sub(r'\s+', ' ', raw.strip())
        clean = _pt_plate.sub(r'\1\2-\3', clean)  # normalise plate spacing
        bien_so = re.sub(r'^\s*[Xx]e\s+', '', clean)
        plate_m = _pt_plate.search(bien_so)
        if plate_m:
            tinh_trang = bien_so[plate_m.end():].strip().lstrip(',').strip()
            bien_so = bien_so[:plate_m.end()].strip()
        else:
            tinh_trang = ""
        return {"bien_so": bien_so, "tinh_trang": tinh_trang}

    normalised = []
    for item in vehicles:
        if isinstance(item, str):
            normalised.append(_parse_pt(item))
        elif isinstance(item, dict):
            bien_so = str(item.get("bien_so", "")).strip()
            tinh_trang = str(item.get("tinh_trang", "")).strip()
            # If tinh_trang is already set, just strip Xe prefix from bien_so
            if tinh_trang:
                bien_so = re.sub(r'^\s*[Xx]e\s+', '', bien_so)
                normalised.append({"bien_so": bien_so, "tinh_trang": tinh_trang})
            else:
                # tinh_trang empty → re-parse bien_so to split plate from condition
                normalised.append(_parse_pt(bien_so))
        else:
            normalised.append({"bien_so": str(item), "tinh_trang": ""})

    context["danh_sach_phuong_tien_hu_hong"] = normalised


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None so JSONB INSERT doesn't crash."""
    import math
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    # numpy scalar types
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer)):
            v = obj.item()
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return v
    except ImportError:
        pass
    return obj


IGNORE_KEYS = {
    "stt", "id", "index", "ghi_ch", "ghi_chu", "danh_m_c",
    "danh_muc", "tieu_de", "danh_m_c_ch_ti_u_th_ng_k",
}


def _extract_number_from_garbage(val: Any) -> Decimal:
    """Extract numeric value from noisy nested structures produced by LLM."""
    if val is None:
        return Decimal("0")

    if isinstance(val, bool):
        return Decimal("1") if val else Decimal("0")

    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))

    if isinstance(val, str):
        text = val.strip().replace(",", ".")
        if not text:
            return Decimal("0")
        try:
            return Decimal(text)
        except InvalidOperation:
            return Decimal("0")

    if isinstance(val, list):
        return sum((_extract_number_from_garbage(item) for item in val), Decimal("0"))

    if isinstance(val, dict):
        dict_sum = Decimal("0")
        for key, value in val.items():
            if str(key).lower().strip() in IGNORE_KEYS:
                continue
            dict_sum += _extract_number_from_garbage(value)
        return dict_sum

    return Decimal("0")


def _default_value_for_field(field_def: dict[str, Any]) -> Any:
    """Return a safe default render value for a schema field."""
    field_type = (field_def or {}).get("type", "string")
    if field_type == "array":
        return []
    if field_type == "number":
        return 0
    if field_type == "boolean":
        return False
    if field_type == "object":
        return {}
    return ""


def _normalize_master_payload(
    schema_definition: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Force payload into a docxtpl-safe shape based on template schema.

    Rules:
      - top-level scalar fields always exist
      - top-level arrays always exist and default to []
      - values remain flat for static fields
    """
    normalized = dict(payload or {})
    for field_def in schema_definition.get("fields", []):
        field_name = field_def.get("name")
        if not field_name:
            continue

        if field_name not in normalized or normalized[field_name] is None:
            normalized[field_name] = _default_value_for_field(field_def)
            continue

        if field_def.get("type") == "array":
            current = normalized.get(field_name)
            if current is None:
                normalized[field_name] = []
            elif not isinstance(current, list):
                normalized[field_name] = [current]

    return normalized


def _coerce_int_or_none(value: Any) -> int | None:
    """Parse numeric-like values to int, keep missing values as None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, Decimal)):
        try:
            return int(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def _derive_missing_additive_stt_fields(row: dict[str, Any]) -> None:
    """Fill missing STT values using additive formulas from the official template."""
    if not isinstance(row, dict):
        return

    equations: list[tuple[str, list[str]]] = [
        ("stt_15_cnch_cuu_nguoi", ["stt_16_cnch_truc_tiep", "stt_17_cnch_tu_thoat"]),
        ("stt_31_kiem_tra_tong", ["stt_32_kiem_tra_dinh_ky", "stt_33_kiem_tra_dot_xuat"]),
        (
            "stt_35_xu_phat_tong",
            [
                "stt_36_xu_phat_canh_cao",
                "stt_37_xu_phat_tam_dinh_chi",
                "stt_38_xu_phat_dinh_chi",
                "stt_39_xu_phat_tien_mat",
            ],
        ),
        (
            "stt_55_hl_tong_cbcs",
            [
                "stt_56_hl_chi_huy_phong",
                "stt_57_hl_chi_huy_doi",
                "stt_58_hl_can_bo_tieu_doi",
                "stt_59_hl_chien_sy",
                "stt_60_hl_lai_xe",
                "stt_61_hl_lai_tau",
            ],
        ),
    ]

    for total_key, part_keys in equations:
        total_val = _coerce_int_or_none(row.get(total_key))
        part_vals = [_coerce_int_or_none(row.get(k)) for k in part_keys]
        missing_parts = [idx for idx, value in enumerate(part_vals) if value is None]

        # Missing total but all parts present: total = sum(parts)
        if total_val is None and not missing_parts:
            row[total_key] = int(sum(part_vals))
            continue

        # Total present and exactly one missing part: derive that part.
        if total_val is not None and len(missing_parts) == 1:
            miss_idx = missing_parts[0]
            known_sum = sum(v for i, v in enumerate(part_vals) if i != miss_idx and v is not None)
            row[part_keys[miss_idx]] = max(0, int(total_val - known_sum))


def _sync_derived_stt_fields_to_bang_thong_ke(row: dict[str, Any]) -> None:
    """Mirror derived STT flat fields back into ``bang_thong_ke`` for UI/JSON visibility."""
    if not isinstance(row, dict):
        return

    btk = row.get("bang_thong_ke")
    if not isinstance(btk, list):
        return

    stt_map: dict[str, dict[str, Any]] = {}
    for item in btk:
        if not isinstance(item, dict):
            continue
        stt_key = str(item.get("stt", "")).strip()
        if stt_key:
            stt_map[stt_key] = item

    added = False
    for field_name, stt_num in WORD_STT_REVERSE_MAP.items():
        value = _coerce_int_or_none(row.get(field_name))
        if value is None:
            continue

        stt_key = str(stt_num)
        existing = stt_map.get(stt_key)
        if existing is not None:
            continue

        btk.append(
            {
                "stt": stt_key,
                "ket_qua": int(value),
                "noi_dung": STT_DISPLAY_LABELS.get(stt_num, f"STT {stt_key}"),
            }
        )
        stt_map[stt_key] = btk[-1]
        added = True

    if added:
        btk.sort(key=lambda item: int(str(item.get("stt", "9999")).strip()) if str(item.get("stt", "")).strip().isdigit() else 9999)


def _clean_cong_tac_an_ninh_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    cleaned = re.sub(r"^(?:pccc|ccc)\s*:\s*", "", text, flags=re.IGNORECASE).strip()
    return cleaned or text


def _strip_cnch_result_labels(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    patterns = [
        r"^(?:kết\s*quả|ket\s*qua)\s*:\s*",
        r"^(?:thiệt\s*hại|thiet\s*hai)\s*:\s*",
    ]
    for _ in range(3):
        before = cleaned
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned == before:
            break

    return cleaned.strip(" .;,:")


def _normalize_cnch_result_text(item: dict[str, Any]) -> str:
    candidates = [
        item.get("ket_qua_xu_ly"),
        item.get("mo_ta"),
        item.get("thiet_hai"),
    ]

    for raw in candidates:
        text = _strip_cnch_result_labels(str(raw or ""))
        if text:
            return re.sub(r"\s+", " ", text).strip()

    return ""


def _collect_cnch_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect and de-duplicate CNCH items from all rows."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        items = row.get("danh_sach_cnch")
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            signature = (
                str(item.get("thoi_gian") or "").strip(),
                str(item.get("ngay_xay_ra") or "").strip(),
                str(item.get("dia_diem") or "").strip(),
                str(item.get("noi_dung_tin_bao") or "").strip(),
            )
            if not any(signature):
                continue
            if signature in seen:
                continue

            seen.add(signature)
            merged.append(dict(item))

    return merged


def _collect_cong_van_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        items = row.get("danh_sach_cong_van_tham_muu")
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            signature = (
                str(item.get("so_ky_hieu") or "").strip(),
                str(item.get("noi_dung") or "").strip(),
            )
            if not any(signature):
                continue
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(dict(item))

    return merged


def _collect_cong_tac_khac_items(rows: list[dict[str, Any]]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        items = row.get("danh_sach_cong_tac_khac")
        if not isinstance(items, list):
            continue

        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            merged.append(text)

    return merged


def _sum_row_int_field(rows: list[dict[str, Any]], field_name: str) -> int:
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = _coerce_int_or_none(row.get(field_name))
        if value is not None:
            total += value
    return total


def _is_empty_cnch_detail(text: Any) -> bool:
    raw = str(text or "").strip().lower()
    if not raw:
        return True

    return "cứu nạn, cứu hộ: không" in raw


def _build_cnch_detail_from_items(items: list[dict[str, Any]]) -> str:
    count = len(items)
    lines = [f"3. Tình hình công tác cứu nạn, cứu hộ: Trong kỳ xảy ra {count} vụ."]

    for idx, item in enumerate(items, start=1):
        thoi_gian = str(item.get("thoi_gian") or "").strip()
        noi_dung = str(item.get("noi_dung_tin_bao") or "").strip()
        dia_diem = str(item.get("dia_diem") or "").strip()
        result_text = _normalize_cnch_result_text(item)

        parts = [f"3.{idx}."]
        if thoi_gian:
            parts.append(f"Vào lúc {thoi_gian}")
        if noi_dung:
            parts.append(f"nhận tin báo {noi_dung}")
        if dia_diem:
            parts.append(f"tại {dia_diem}")

        sentence = " ".join(parts).strip()
        if not sentence.endswith("."):
            sentence += "."
        if result_text:
            sentence += f" Kết quả: {result_text}."

        lines.append(sentence)

    return "\n".join(lines)


def _extract_dates_from_text(raw: Any) -> list[date]:
    """Extract DD/MM/YYYY-like dates from a text value."""
    text = str(raw or "").strip()
    if not text:
        return []

    dates: list[date] = []
    for day_s, month_s, year_s in re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", text):
        try:
            dates.append(date(int(year_s), int(month_s), int(day_s)))
        except ValueError:
            continue
    return dates


def _derive_reporting_window_from_rows(rows: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Build [tu_ngay, den_ngay] from all source rows for multi-day aggregation."""
    period_end_dates: list[date] = []
    report_dates: list[date] = []
    fallback_dates: list[date] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        header = row.get("header") if isinstance(row.get("header"), dict) else {}

        # For daily chain reports, den_ngay usually represents each report day.
        period_end_dates.extend(_extract_dates_from_text(row.get("den_ngay")))

        # Prefer explicit report dates from each row.
        report_dates.extend(_extract_dates_from_text(row.get("ngay_bao_cao")))
        report_dates.extend(_extract_dates_from_text(header.get("ngay_bao_cao")))

        # Fallback: parse any dates from interval text.
        fallback_dates.extend(_extract_dates_from_text(row.get("thoi_gian_tu_den")))
        fallback_dates.extend(_extract_dates_from_text(header.get("thoi_gian_tu_den")))

    source = period_end_dates or report_dates or fallback_dates
    if not source:
        return None

    start = min(source)
    end = max(source)
    return (f"{start.day:02d}/{start.month:02d}/{start.year:04d}", f"{end.day:02d}/{end.month:02d}/{end.year:04d}")


class AggregationService:
    """Pandas-based aggregation engine."""

    def __init__(self, db: Session):
        self.db = db

    def aggregate(
        self,
        template_id: str,
        job_ids: list[str],
        tenant_id: str,
        report_name: str,
        user_id: str,
        description: str = None,
    ) -> AggregationReport:
        """Aggregate multiple approved extraction jobs into a report.

        Args:
            template_id: Template UUID (all jobs must use same template)
            job_ids: List of approved job UUIDs
            tenant_id: Tenant UUID
            report_name: Name for the report
            user_id: Creator user UUID
            description: Optional description

        Returns:
            AggregationReport with aggregated_data
        """
        import pandas as pd

        # 1. Validate template
        template = (
            self.db.query(ExtractionTemplate)
            .filter(
                ExtractionTemplate.id == template_id,
                ExtractionTemplate.tenant_id == tenant_id,
            )
            .first()
        )
        if not template:
            raise ProcessingError(message=f"Template {template_id} not found")

        # 2. Load jobs — approved ones belonging to this tenant
        # NOTE: We do NOT filter by template_id here so that jobs created under
        # an older/different template revision can still be aggregated.
        # The selected template is used only for its aggregation rules.
        jobs = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.id.in_(job_ids),
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.status == ExtractionJobStatus.APPROVED,
            )
            .all()
        )

        if not jobs:
            # Diagnostics: are the jobs there but not approved?
            any_jobs = (
                self.db.query(ExtractionJob)
                .filter(
                    ExtractionJob.id.in_(job_ids),
                    ExtractionJob.tenant_id == tenant_id,
                )
                .all()
            )
            if any_jobs:
                statuses = sorted({str(j.status) for j in any_jobs})
                raise ProcessingError(
                    message=(
                        f"Jobs exist but are not approved yet. "
                        f"Current statuses: {', '.join(statuses)}. "
                        "Please approve the jobs in Tab 3 before aggregating."
                    )
                )
            raise ProcessingError(message="No jobs found for the given IDs under this tenant.")

        # 3. Settlement gate removed — with the workflow state machine,
        #    jobs can only reach APPROVED after enrichment has settled
        #    (ENRICHING → READY_FOR_REVIEW → APPROVED).  No extra check needed.

        # 4. Collect data using job.final_data so that:
        #    - reviewed_data (human-edited) wins unconditionally
        #    - enriched_data (LLM Stage 2) is merged on top of extracted_data
        #      when available — but only if enrichment settled (gate above)
        #    - extracted_data (deterministic Stage 1) is the fallback
        #
        #    Per-job data source is recorded in enrichment_audit for
        #    the report's _metadata so that readers can audit consistency.
        _placeholder_keys = {"_manual_review_path", "_manual_review_metadata"}
        data_rows: list[dict] = []
        enrichment_audit: list[dict] = []
        for job in jobs:
            fd = job.final_data
            # Strip reviewed_data that is just the failed-job placeholder
            if isinstance(job.reviewed_data, dict) and set(job.reviewed_data.keys()) <= _placeholder_keys:
                fd = job.extracted_data
            row = dict(fd) if isinstance(fd, dict) else fd
            if isinstance(row, dict):
                row = flatten_block_output(row)
                _derive_missing_additive_stt_fields(row)
                _sync_derived_stt_fields_to_bang_thong_ke(row)
                if "cong_tac_an_ninh" in row:
                    row["cong_tac_an_ninh"] = _clean_cong_tac_an_ninh_text(row.get("cong_tac_an_ninh"))
            if row:
                data_rows.append(row)
            # Record which data source was used for this job
            if job.reviewed_data and not (
                isinstance(job.reviewed_data, dict)
                and set(job.reviewed_data.keys()) <= _placeholder_keys
            ):
                data_source = "reviewed"
            elif job.enriched_data:
                data_source = "stage1+stage2"
            else:
                data_source = "stage1_only"
            enrichment_audit.append({
                "job_id": str(job.id),
                "enrichment_status": job.enrichment_status,
                "data_source": data_source,
            })

        if not data_rows:
            raise ProcessingError(message="No extraction data available in jobs")

        # 5. Get aggregation rules
        agg_rules = template.aggregation_rules or {}
        rules = agg_rules.get("rules", [])
        sort_by = agg_rules.get("sort_by")

        # 6. Build DataFrame using json_normalize for proper array flattening
        # This handles nested objects and arrays correctly
        try:
            df = pd.json_normalize(data_rows, sep="_")
        except Exception:
            # Fallback: basic DataFrame if json_normalize fails on complex structures
            df = pd.DataFrame(data_rows)

        # Sort if requested (best-effort, robust for mixed payloads)
        if sort_by:
            try:
                data_rows = sorted(
                    data_rows,
                    key=lambda row: (
                        _extract_number_from_garbage((row or {}).get(sort_by))
                        if isinstance(row, dict) else Decimal("0")
                    ),
                )
            except Exception as exc:
                logger.warning("Cannot sort by '%s': %s", sort_by, exc)

        # 7. Apply aggregation rules
        aggregated_data: dict[str, Any] = {}

        for rule in rules:
            output_field = rule["output_field"]
            source_field = rule["source_field"]
            method = rule.get("method", "SUM").upper()
            round_digits = rule.get("round_digits")

            try:
                if method == "CONCAT":
                    all_arrays = []
                    for row in data_rows:
                        val = row.get(source_field)
                        if isinstance(val, list):
                            all_arrays.extend(val)
                        elif val is not None:
                            all_arrays.append(val)
                    aggregated_data[output_field] = all_arrays

                elif method == "LAST":
                    val = None
                    for row in reversed(data_rows):
                        if source_field in row and row[source_field] is not None:
                            val = row[source_field]
                            break
                    aggregated_data[output_field] = val

                elif method in {"SUM", "AVG", "MAX", "MIN", "COUNT"}:
                    extracted_numbers: list[Decimal] = []
                    for row in data_rows:
                        val = row.get(source_field)
                        if val is None:
                            continue
                        if method == "COUNT":
                            extracted_numbers.append(Decimal("1"))
                        else:
                            extracted_numbers.append(_extract_number_from_garbage(val))

                    if not extracted_numbers:
                        result: Decimal | None = Decimal("0") if method != "AVG" else None
                    else:
                        if method in {"SUM", "COUNT"}:
                            result = sum(extracted_numbers)
                        elif method == "AVG":
                            result = sum(extracted_numbers) / Decimal(len(extracted_numbers))
                        elif method == "MAX":
                            result = max(extracted_numbers)
                        else:
                            result = min(extracted_numbers)

                    if result is not None:
                        if round_digits is not None:
                            result_value: Any = round(float(result), round_digits)
                        else:
                            result_value = int(result) if result == int(result) else float(result)
                    else:
                        result_value = None

                    aggregated_data[output_field] = result_value
                elif method == "BANG_THONG_KE_STT_SUM":
                    # Sum ket_qua for a specific stt row across all data_rows.
                    # Rule must include {"stt": <number>} alongside output_field.
                    stt_target = str(rule.get("stt", "")).strip()
                    total_stt = Decimal("0")
                    for data_row in data_rows:
                        btk = data_row.get("bang_thong_ke") or []
                        if not isinstance(btk, list):
                            continue
                        for btk_item in btk:
                            if not isinstance(btk_item, dict):
                                continue
                            if str(btk_item.get("stt", "")).strip() == stt_target:
                                total_stt += _extract_number_from_garbage(btk_item.get("ket_qua"))
                    stt_result = int(total_stt) if total_stt == int(total_stt) else float(total_stt)
                    aggregated_data[output_field] = stt_result
                else:
                    aggregated_data[output_field] = None
                    logger.warning(f"Unknown aggregation method '{method}'")

            except Exception as e:
                logger.error(f"Aggregation error for rule '{output_field}': {e}")
                aggregated_data[output_field] = None

        # 8. Build ONE summary record from the aggregated results.
        #    output_field == source_field (scanner giờ giữ nguyên tên)
        #    nên chỉ cần lấy aggregated_data trực tiếp, không cần set 2 key.
        summary_record: dict[str, Any] = {}
        for rule in rules:
            output_field = rule["output_field"]
            val = aggregated_data.get(output_field)
            summary_record[output_field] = val

        # Add any scalar fields from the LAST row that aren't covered by rules
        # (e.g. nguoi_ky, don_vi, etc. — static fields the Word template needs)
        # Also include dict fields like 'header' and 'phan_I_va_II_chi_tiet_nghiep_vu'
        # needed by build_word_export_context's expand helpers.
        if data_rows:
            last_row = data_rows[-1]
            rule_outputs = {r["output_field"] for r in rules}
            _passthrough_dicts = {
                "header", "phan_I_va_II_chi_tiet_nghiep_vu", "narrative",
            }
            for k, v in last_row.items():
                if k not in summary_record and k not in rule_outputs:
                    if not isinstance(v, dict) or k in _passthrough_dicts:
                        summary_record[k] = v

            # For multi-row reports, use the full reporting window instead of
            # blindly inheriting the last row's interval.
            if len(data_rows) > 1:
                window = _derive_reporting_window_from_rows(data_rows)
                if window is not None:
                    tu_ngay, den_ngay = window
                    interval = f"Từ ngày {tu_ngay} đến ngày {den_ngay}"

                    # Keep top-level convenience fields aligned with the
                    # multi-row reporting window instead of LAST-row values.
                    aggregated_data["tu_ngay"] = tu_ngay
                    aggregated_data["den_ngay"] = den_ngay
                    aggregated_data["thoi_gian_tu_den"] = interval

                    summary_record["tu_ngay"] = tu_ngay
                    summary_record["den_ngay"] = den_ngay
                    summary_record["thoi_gian_tu_den"] = interval

                    header = summary_record.get("header")
                    if isinstance(header, dict):
                        patched_header = dict(header)
                        patched_header["thoi_gian_tu_den"] = interval
                        summary_record["header"] = patched_header

                # Merge CNCH details across rows so multi-day summaries do not
                # silently inherit an empty "Khong" text from the last row.
                merged_cnch = _collect_cnch_items(data_rows)
                if merged_cnch:
                    summary_record["danh_sach_cnch"] = merged_cnch
                    aggregated_data["danh_sach_cnch"] = merged_cnch

                    if _is_empty_cnch_detail(summary_record.get("chi_tiet_cnch")):
                        detail_text = _build_cnch_detail_from_items(merged_cnch)
                        summary_record["chi_tiet_cnch"] = detail_text
                        aggregated_data["chi_tiet_cnch"] = detail_text

                        nghiep_vu = summary_record.get("phan_I_va_II_chi_tiet_nghiep_vu")
                        if isinstance(nghiep_vu, dict):
                            patched_nghiep_vu = dict(nghiep_vu)
                            patched_nghiep_vu["chi_tiet_cnch"] = detail_text
                            summary_record["phan_I_va_II_chi_tiet_nghiep_vu"] = patched_nghiep_vu

                merged_cong_van = _collect_cong_van_items(data_rows)
                merged_cong_tac_khac = _collect_cong_tac_khac_items(data_rows)
                summary_record["danh_sach_cong_van_tham_muu"] = merged_cong_van
                aggregated_data["danh_sach_cong_van_tham_muu"] = merged_cong_van
                summary_record["danh_sach_cong_tac_khac"] = merged_cong_tac_khac
                aggregated_data["danh_sach_cong_tac_khac"] = merged_cong_tac_khac

                for counter_field in ("tong_cong_van", "tong_bao_cao", "tong_ke_hoach"):
                    summed = _sum_row_int_field(data_rows, counter_field)
                    summary_record[counter_field] = summed
                    aggregated_data[counter_field] = summed

            cleaned_an_ninh = _clean_cong_tac_an_ninh_text(summary_record.get("cong_tac_an_ninh"))
            if cleaned_an_ninh:
                summary_record["cong_tac_an_ninh"] = cleaned_an_ninh
                aggregated_data["cong_tac_an_ninh"] = cleaned_an_ninh

                nghiep_vu = summary_record.get("phan_I_va_II_chi_tiet_nghiep_vu")
                if isinstance(nghiep_vu, dict):
                    patched_nghiep_vu = dict(nghiep_vu)
                    patched_nghiep_vu["cong_tac_an_ninh"] = cleaned_an_ninh
                    summary_record["phan_I_va_II_chi_tiet_nghiep_vu"] = patched_nghiep_vu

        # 7.25. Force a docxtpl-safe master payload shape from schema_definition.
        # Arrays must always exist as [], and top-level static fields stay flat.
        summary_record = _normalize_master_payload(template.schema_definition or {}, summary_record)
        normalized_top_level = _normalize_master_payload(template.schema_definition or {}, aggregated_data)
        for key, value in normalized_top_level.items():
            if key not in aggregated_data or aggregated_data.get(key) is None:
                aggregated_data[key] = value

        aggregated_data["records"] = [summary_record] if summary_record else []

        # Keep raw source rows for Excel detail sheet & debugging
        aggregated_data["_source_records"] = data_rows

        # 7.5. Include flattened view (json_normalize result) for easy export
        try:
            flat_df = pd.json_normalize(data_rows, sep="_")
            aggregated_data["_flat_records"] = flat_df.to_dict(orient="records")
        except Exception:
            aggregated_data["_flat_records"] = data_rows

        # 9. Add metadata & metrics
        # enrichment_summary counts how many jobs used each data source,
        # so readers of the report can audit whether enrichment was complete.
        enrichment_counts: dict[str, int] = {}
        for entry in enrichment_audit:
            src = entry["data_source"]
            enrichment_counts[src] = enrichment_counts.get(src, 0) + 1
        fully_enriched = enrichment_counts.get("stage1+stage2", 0)
        enrichment_partial = fully_enriched > 0 and fully_enriched < len(jobs)

        aggregated_data["_metadata"] = {
            "total_jobs": len(jobs),
            "total_data_rows": len(data_rows),
            "generated_at": datetime.utcnow().isoformat(),
            "template_name": template.name,
            "template_version": template.version,
            # Enrichment audit — tells consumers exactly what data was used
            "enrichment_summary": enrichment_counts,
            "enrichment_partial": enrichment_partial,
            "enrichment_audit": enrichment_audit,
        }
        aggregated_data["metrics"] = {
            "total_records": len(data_rows),
            "total_jobs": len(jobs),
            "rules_applied": len(rules),
        }

        # Sanitize: replace NaN/Inf (not valid in JSON/JSONB) with None
        aggregated_data = _sanitize_for_json(aggregated_data)

        # 10. Create report record
        report = AggregationReport(
            tenant_id=tenant_id,
            template_id=template_id,
            name=report_name,
            description=description,
            job_ids=[str(j.id) for j in jobs],
            aggregated_data=aggregated_data,
            total_jobs=len(job_ids),
            approved_jobs=len(jobs),
            created_by=user_id,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        logger.info(
            f"Created aggregation report '{report_name}' (id={report.id}): "
            f"{len(jobs)} jobs, {len(rules)} rules applied"
        )

        return report

    def get_report(self, report_id: str, tenant_id: str) -> AggregationReport:
        """Get a report by ID."""
        report = (
            self.db.query(AggregationReport)
            .filter(
                AggregationReport.id == report_id,
                AggregationReport.tenant_id == tenant_id,
            )
            .first()
        )
        if not report:
            raise ProcessingError(message=f"Report {report_id} not found")
        return report

    def list_reports(
        self,
        tenant_id: str,
        page: int = 1,
        per_page: int = 20,
        template_id: str = None,
    ) -> tuple[list[AggregationReport], int]:
        """List reports for a tenant."""
        query = self.db.query(AggregationReport).filter(
            AggregationReport.tenant_id == tenant_id,
        )
        if template_id:
            query = query.filter(AggregationReport.template_id == template_id)

        total = query.count()
        items = (
            query.order_by(AggregationReport.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return items, total

    def delete_report(self, report_id: str, tenant_id: str) -> None:
        """Delete an aggregation report by ID."""
        report = self.get_report(report_id, tenant_id)
        self.db.delete(report)
        self.db.commit()


# ──────────────────────────────────────────────
# Export Service
# ──────────────────────────────────────────────

class ExportService:
    """Export aggregated data to various formats."""

    @staticmethod
    def to_excel(report: AggregationReport, jobs: list[ExtractionJob] = None) -> io.BytesIO:
        """Export report to Excel (.xlsx).

        Sheet 1: Aggregated summary
        Sheet 2: Per-job detail (if jobs provided)
        """
        import pandas as pd

        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            # Sheet 1: Summary (aggregated result — the "Cục Cao")
            agg_data = report.aggregated_data or {}
            _INTERNAL = {"records", "_source_records", "_flat_records", "_metadata", "metrics"}
            summary_rows = []
            for key, value in agg_data.items():
                if key in _INTERNAL or key.startswith("_"):
                    continue
                if isinstance(value, list):
                    summary_rows.append({"Trường": key, "Giá trị": f"[{len(value)} phần tử]"})
                elif isinstance(value, dict):
                    summary_rows.append({"Trường": key, "Giá trị": str(value)})
                else:
                    summary_rows.append({"Trường": key, "Giá trị": value})

            df_summary = pd.DataFrame(summary_rows)
            df_summary.to_excel(writer, sheet_name="Tổng hợp", index=False)

            # Sheet 2: Source records (raw data from each day/document)
            source_records = agg_data.get("_source_records", [])
            if source_records:
                try:
                    flat_src = pd.json_normalize(source_records, sep="_")
                    flat_src.to_excel(writer, sheet_name="Tài liệu gốc", index=False)
                except Exception:
                    pd.DataFrame(source_records).to_excel(writer, sheet_name="Tài liệu gốc", index=False)

            # Sheet 3: Detail (per-job from DB)
            if jobs:
                detail_rows = []
                for job in jobs:
                    data = job.reviewed_data or job.extracted_data or {}
                    row = {"job_id": str(job.id), "document_id": str(job.document_id)}
                    for k, v in data.items():
                        if isinstance(v, (list, dict)):
                            row[k] = str(v)
                        else:
                            row[k] = v
                    detail_rows.append(row)

                df_detail = pd.DataFrame(detail_rows)
                df_detail.to_excel(writer, sheet_name="Detail", index=False)

            # Sheet 3: Metadata
            metadata = agg_data.get("_metadata", {})
            df_meta = pd.DataFrame([metadata])
            df_meta.to_excel(writer, sheet_name="Metadata", index=False)

        buffer.seek(0)
        return buffer

    @staticmethod
    def to_csv(report: AggregationReport) -> io.BytesIO:
        """Export aggregated data as CSV."""
        import pandas as pd

        agg_data = report.aggregated_data or {}
        rows = []
        for key, value in agg_data.items():
            if key == "_metadata":
                continue
            rows.append({"Field": key, "Value": value})

        df = pd.DataFrame(rows)
        buffer = io.BytesIO()
        df.to_csv(buffer, index=False, encoding="utf-8")
        buffer.seek(0)
        return buffer
