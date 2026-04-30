"""Deterministic Google Sheets → canonical extraction contract pipeline."""

from __future__ import annotations

from functools import lru_cache
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from app.core.exceptions import ProcessingError
from app.engines.extraction.schemas import (
    BlockExtractionOutput,
    BlockHeader,
    BlockNghiepVu,
    CNCHItem,
    ChiTieu,
    ChiVienItem,
    CongVanItem,
    PhuongTienHuHongItem,
    PipelineResult,
    TuyenTruyenOnline,
    VuChayItem,
)

from app.engines.extraction.sheet_pipeline import (
    _build_output_custom,
    _build_output_custom_header,
)
from app.engines.extraction.mapping.normalizer import normalize_unicode_text


EXPECTED_TOP_LEVEL_KEYS = {
    "header",
    "phan_I_va_II_chi_tiet_nghiep_vu",
    "bang_thong_ke",
    "danh_sach_cnch",
    "danh_sach_phuong_tien_hu_hong",
    "danh_sach_cong_van_tham_muu",
    "danh_sach_cong_tac_khac",
    # NEW: from Excel sheets chuyên biệt
    "danh_sach_chi_vien",
    "danh_sach_chay",
    "danh_sach_sclq",
    "tuyen_truyen_online",
}


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return default

    text = str(value).strip()
    if not text:
        return default

    cleaned = text.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except Exception:
        return default


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _get_first(data: dict[str, Any], aliases: list[str], default: Any = "") -> Any:
    normalized = {str(k).strip().lower(): v for k, v in data.items()}
    for key in aliases:
        lookup = key.strip().lower()
        if lookup in normalized:
            return normalized[lookup]
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip() == ""


def _normalize_key(value: str) -> str:
    """Normalize a key for space-separated matching with diacritics removal."""
    t = unicodedata.normalize("NFC", str(value or "")).strip().lower()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[_\s]+", " ", t).strip()


def _extract_core(sheet_data: dict[str, Any] | None) -> dict[str, Any]:
    raw = sheet_data or {}
    core = raw
    if isinstance(raw, dict):
        nested_data = raw.get("data") if isinstance(raw.get("data"), dict) else None
        if nested_data:
            core = nested_data
    return core if isinstance(core, dict) else {}


@lru_cache(maxsize=1)
def _load_sheet_mapping() -> dict[str, Any]:
    mapping_path = Path(__file__).resolve().parents[2] / "domain" / "templates" / "sheet_mapping.yaml"
    try:
        with open(mapping_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return {}
    mapping = data.get("sheet_mapping")
    return mapping if isinstance(mapping, dict) else {}


# Global cache for custom schemas (not using lru_cache because paths are dynamic)
_CUSTOM_MAPPING_CACHE: dict[str, dict[str, Any]] = {}


def _load_custom_mapping(schema_path: str) -> dict[str, Any]:
    if schema_path in _CUSTOM_MAPPING_CACHE:
        return _CUSTOM_MAPPING_CACHE[schema_path]
    path = Path(schema_path).expanduser().resolve()
    if not path.is_file():
        raise ProcessingError(message=f"Schema YAML not found: {path}")
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    mapping = raw.get("sheet_mapping")
    if not isinstance(mapping, dict):
        raise ProcessingError(message=f"Invalid schema: missing 'sheet_mapping' in {schema_path}")
    _CUSTOM_MAPPING_CACHE[schema_path] = mapping
    return mapping


def _aliases(mapping: dict[str, Any], section: str, field: str, fallback: list[str]) -> list[str]:
    section_data = mapping.get(section)
    if not isinstance(section_data, dict):
        return fallback

    # v1 format: section.field = ["alias1", "alias2", ...]
    direct = section_data.get(field)
    if isinstance(direct, list):
        values = [str(item) for item in direct if str(item).strip()]
        return values or fallback

    # v2 format: section.field.aliases = [...]
    if isinstance(direct, dict):
        nested = direct.get("aliases")
        if isinstance(nested, list):
            values = [str(item) for item in nested if str(item).strip()]
            return values or fallback

    # v2 format for list sections: section.fields.field = [...]
    fields_node = section_data.get("fields")
    if isinstance(fields_node, dict):
        from_fields = fields_node.get(field)
        if isinstance(from_fields, list):
            values = [str(item) for item in from_fields if str(item).strip()]
            return values or fallback

    return fallback


def _stt_noi_dung(mapping: dict[str, Any], stt: str) -> str:
    bang = mapping.get("bang_thong_ke")
    if not isinstance(bang, dict):
        return ""
    stt_map = bang.get("stt_map")
    if not isinstance(stt_map, dict):
        return ""
    value = stt_map.get(str(stt).strip())
    if not isinstance(value, dict):
        return ""
    return _to_text(value.get("noi_dung"))


def _build_bang_thong_ke_from_flat(
    mapping: dict[str, Any],
    flat_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build bang_thong_ke rows from flat nghiệp vụ fields using stt_map.field."""
    if not isinstance(flat_data, dict):
        return []

    bang = mapping.get("bang_thong_ke")
    if not isinstance(bang, dict):
        return []

    stt_map = bang.get("stt_map")
    if not isinstance(stt_map, dict):
        return []

    rows: list[dict[str, Any]] = []
    for stt, spec in stt_map.items():
        if not isinstance(spec, dict):
            continue
        field_name = _to_text(spec.get("field"))
        if not field_name:
            continue

        raw_value = flat_data.get(field_name)
        if _is_blank(raw_value):
            continue

        rows.append(
            {
                "stt": str(stt).strip(),
                "noi_dung": _to_text(spec.get("noi_dung")),
                "ket_qua": _to_int(raw_value, 0),
            }
        )

    return rows


def _assert_contract_or_raise(output: BlockExtractionOutput) -> None:
    payload = output.model_dump()
    top_keys = set(payload.keys())
    if top_keys != EXPECTED_TOP_LEVEL_KEYS:
        missing = sorted(EXPECTED_TOP_LEVEL_KEYS - top_keys)
        extra = sorted(top_keys - EXPECTED_TOP_LEVEL_KEYS)
        raise ValueError(f"CONTRACT_MISMATCH:missing={missing};extra={extra}")

    # strict model validation pass (raises if schema shape/type mismatches)
    BlockExtractionOutput.model_validate(payload)


def _inject_computed_bang_thong_ke_rows(items: list[ChiTieu]) -> list[ChiTieu]:
    """Inject only rows absent from Excel but computable from sibling rows.

    STT 32 = STT 31 - STT 33  (định kỳ = tổng - đột xuất)
    STT 33 = STT 31 - STT 32  (đột xuất = tổng - định kỳ)
    STT 60 is a direct input field — do NOT derive, read directly from Excel.
    """
    by_stt = {str(item.stt).strip(): item for item in items if getattr(item, "stt", None) is not None}
    insertions: list[ChiTieu] = []

    def _kq(stt: str) -> int:
        raw = getattr(by_stt.get(stt), "ket_qua", 0)
        return _to_int(raw, 0)

    if "32" not in by_stt and "31" in by_stt and "33" in by_stt:
        insertions.append(
            ChiTieu(stt="32", noi_dung="Kiểm tra định kỳ", ket_qua=max(0, _kq("31") - _kq("33")))
        )

    if "33" not in by_stt and "31" in by_stt and "32" in by_stt:
        insertions.append(
            ChiTieu(stt="33", noi_dung="Kiểm tra đột xuất theo chuyên đề", ket_qua=max(0, _kq("31") - _kq("32")))
        )

    # STT 51 = STT 52 - STT 53 (PA PC09 residual, if both present but 51 absent)
    if "51" not in by_stt and "52" in by_stt and "53" in by_stt:
        kq51 = _kq("52") - _kq("53")
        if kq51 >= 0:
            insertions.append(
                ChiTieu(stt="51", noi_dung="Phương án CNCH của CQCA thực tập khác", ket_qua=kq51)
            )

    merged = items + insertions
    merged.sort(key=lambda x: int(str(x.stt)) if str(x.stt).isdigit() else 9999)
    return merged


def _inject_online_rows(items: list[ChiTieu], online: dict[str, Any]) -> list[ChiTieu]:
    """Inject STT 22-25 (tuyên truyền online / MXH) into bang_thong_ke.

    STT 22 = so_tin_bai
    STT 23 = so_hinh_anh
    STT 24 = cai_app_114
    STT 25 = STT 22 + STT 23 (tổng online)
    """
    by_stt = {str(item.stt).strip(): item for item in items if getattr(item, "stt", None) is not None}
    insertions: list[ChiTieu] = []

    if "22" not in by_stt and online:
        so_tin_bai = _to_int(online.get("so_tin_bai", 0))
        if so_tin_bai > 0:
            insertions.append(
                ChiTieu(stt="22", noi_dung="Số tin, bài đã đăng phát", ket_qua=so_tin_bai)
            )

    if "23" not in by_stt and online:
        so_hinh_anh = _to_int(online.get("so_hinh_anh", 0))
        if so_hinh_anh > 0:
            insertions.append(
                ChiTieu(stt="23", noi_dung="Số hình ảnh được đăng tải", ket_qua=so_hinh_anh)
            )

    if "24" not in by_stt and online:
        cai_app = _to_int(online.get("cai_app_114", 0))
        if cai_app > 0:
            insertions.append(
                ChiTieu(stt="24", noi_dung="Số lượt cài đặt ứng dụng HELP 114", ket_qua=cai_app)
            )

    # STT 25 = STT 22 + STT 23 (tổng online)
    if "25" not in by_stt and "22" in by_stt and "23" in by_stt:
        so_tin = _to_int(getattr(by_stt.get("22"), "ket_qua", 0))
        so_hinh = _to_int(getattr(by_stt.get("23"), "ket_qua", 0))
        if (so_tin or so_hinh) > 0:
            insertions.append(
                ChiTieu(stt="25", noi_dung="Tổng tuyên truyền qua MXH", ket_qua=so_tin + so_hinh)
            )

    if insertions:
        items = list(items) + insertions
        items.sort(key=lambda x: int(str(x.stt)) if str(x.stt).isdigit() else 9999)
    return items


class SheetExtractionPipeline:
    """Map Google Sheets payloads into the canonical block extraction schema."""

    def normalize(self, sheet_data: dict[str, Any] | None) -> dict[str, Any]:
        raw = sheet_data or {}
        core = raw
        nested_data = raw.get("data") if isinstance(raw.get("data"), dict) else None
        if nested_data:
            core = nested_data

        header_raw = core.get("header")
        if not isinstance(header_raw, dict):
            header_raw = core if isinstance(core, dict) else {}

        nghiep_vu_raw = core.get("phan_I_va_II_chi_tiet_nghiep_vu")
        if not isinstance(nghiep_vu_raw, dict):
            nghiep_vu_raw = core.get("nghiep_vu") if isinstance(core.get("nghiep_vu"), dict) else {}
        if not isinstance(nghiep_vu_raw, dict) or not nghiep_vu_raw:
            nghiep_vu_raw = core if isinstance(core, dict) else {}

        btk_raw = core.get("bang_thong_ke")
        if not isinstance(btk_raw, list):
            btk_raw = core.get("chi_tieu") if isinstance(core.get("chi_tieu"), list) else []

        if not btk_raw:
            btk_raw = _build_bang_thong_ke_from_flat(_load_sheet_mapping(), core if isinstance(core, dict) else {})

        return {
            "_core": core,  # expose core for custom mapping
            "header": header_raw,
            "nghiep_vu": nghiep_vu_raw,
            "bang_thong_ke": btk_raw,
            "danh_sach_cnch": _as_list(core.get("danh_sach_cnch")),
            "danh_sach_phuong_tien_hu_hong": _as_list(core.get("danh_sach_phuong_tien_hu_hong")),
            "danh_sach_cong_van_tham_muu": _as_list(core.get("danh_sach_cong_van_tham_muu")),
            "danh_sach_cong_tac_khac": _as_list(core.get("danh_sach_cong_tac_khac")),
            # NEW: from Excel sheets chuyên biệt
            "danh_sach_chi_vien": _as_list(core.get("danh_sach_chi_vien")),
            "danh_sach_chay": _as_list(core.get("danh_sach_chay")),
            "tuyen_truyen_online": core.get("tuyen_truyen_online") or {},
        }

    def map_to_schema(self, normalized: dict[str, Any]) -> BlockExtractionOutput:
        mapping = _load_sheet_mapping()
        header_raw = normalized.get("header") or {}
        nghiep_vu_raw = normalized.get("nghiep_vu") or {}
        btk_raw = normalized.get("bang_thong_ke") or []

        header = BlockHeader(
            so_bao_cao=_to_text(
                _get_first(
                    header_raw,
                    _aliases(mapping, "header", "so_bao_cao", ["so_bao_cao", "số báo cáo", "so bao cao", "report_no"]),
                )
            ),
            ngay_bao_cao=_to_text(
                _get_first(
                    header_raw,
                    _aliases(mapping, "header", "ngay_bao_cao", ["ngay_bao_cao", "ngày báo cáo", "report_date"]),
                )
            ),
            thoi_gian_tu_den=_to_text(
                _get_first(
                    header_raw,
                    _aliases(mapping, "header", "thoi_gian_tu_den", ["thoi_gian_tu_den", "thời gian từ đến", "report_period"]),
                )
            ),
            don_vi_bao_cao=_to_text(
                _get_first(
                    header_raw,
                    _aliases(mapping, "header", "don_vi_bao_cao", ["don_vi_bao_cao", "đơn vị báo cáo", "unit"]),
                )
            ),
        )

        chi_tieu_items: list[ChiTieu] = []
        for row in btk_raw:
            if not isinstance(row, dict):
                continue
            stt = _to_text(_get_first(row, _aliases(mapping, "bang_thong_ke", "stt", ["stt", "STT", "id"])))
            if not stt:
                continue
            row_noi_dung = _to_text(
                _get_first(row, _aliases(mapping, "bang_thong_ke", "noi_dung", ["noi_dung", "nội dung", "name", "chi_tieu"]), "")
            )
            if not row_noi_dung:
                row_noi_dung = _stt_noi_dung(mapping, stt)
            chi_tieu_items.append(
                ChiTieu(
                    stt=stt,
                    noi_dung=row_noi_dung,
                    ket_qua=_to_int(
                        _get_first(row, _aliases(mapping, "bang_thong_ke", "ket_qua", ["ket_qua", "kết quả", "value", "so_lieu"]), 0)
                    ),
                )
            )

        chi_tieu_items = _inject_computed_bang_thong_ke_rows(chi_tieu_items)

        by_stt = {str(item.stt).strip(): item for item in chi_tieu_items}
        nghiep_vu = BlockNghiepVu(
            tong_so_vu_chay=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "tong_so_vu_chay", ["tong_so_vu_chay", "tổng số vụ cháy"]),
                    _to_int(getattr(by_stt.get("2"), "ket_qua", 0)),
                )
            ),
            tong_so_vu_no=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "tong_so_vu_no", ["tong_so_vu_no", "tổng số vụ nổ"]),
                    _to_int(getattr(by_stt.get("8"), "ket_qua", 0)),
                )
            ),
            tong_so_vu_cnch=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "tong_so_vu_cnch", ["tong_so_vu_cnch", "tổng số vụ cnch"]),
                    _to_int(getattr(by_stt.get("14"), "ket_qua", 0)),
                )
            ),
            chi_tiet_cnch=_to_text(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "chi_tiet_cnch", ["chi_tiet_cnch", "chi tiết cnch"]),
                    "",
                )
            ),
            quan_so_truc=_to_int(_get_first(nghiep_vu_raw, _aliases(mapping, "nghiep_vu", "quan_so_truc", ["quan_so_truc", "quân số trực"]), 0)),
            tong_chi_vien=_to_int(_get_first(nghiep_vu_raw, _aliases(mapping, "nghiep_vu", "tong_chi_vien", ["tong_chi_vien", "tổng chi viện"]), 0)),
            tong_cong_van=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "tong_cong_van", ["tong_cong_van", "tổng công văn"]),
                    len(normalized.get("danh_sach_cong_van_tham_muu") or []),
                )
            ),
            tong_bao_cao=_to_int(_get_first(nghiep_vu_raw, _aliases(mapping, "nghiep_vu", "tong_bao_cao", ["tong_bao_cao", "tổng báo cáo"]), 0)),
            tong_ke_hoach=_to_int(_get_first(nghiep_vu_raw, _aliases(mapping, "nghiep_vu", "tong_ke_hoach", ["tong_ke_hoach", "tổng kế hoạch"]), 0)),
            cong_tac_an_ninh=_to_text(_get_first(nghiep_vu_raw, _aliases(mapping, "nghiep_vu", "cong_tac_an_ninh", ["cong_tac_an_ninh", "công tác an ninh"]), "")),
            tong_xe_hu_hong=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "tong_xe_hu_hong", ["tong_xe_hu_hong", "tổng xe hư hỏng"]),
                    len(normalized.get("danh_sach_phuong_tien_hu_hong") or []),
                )
            ),
            # NEW: online tuyên truyền fields
            tong_tin_bai=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "tong_tin_bai", ["tong_tin_bai", "tổng tin bài", "tin bài online"]),
                    0,
                )
            ),
            tong_hinh_anh=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "tong_hinh_anh", ["tong_hinh_anh", "số hình ảnh"]),
                    0,
                )
            ),
            so_lan_cai_app_114=_to_int(
                _get_first(
                    nghiep_vu_raw,
                    _aliases(mapping, "nghiep_vu", "so_lan_cai_app_114", ["so_lan_cai_app_114", "cài app 114"]),
                    0,
                )
            ),
        )

        cnch_items: list[CNCHItem] = []
        for row in normalized.get("danh_sach_cnch") or []:
            if not isinstance(row, dict):
                continue
            cnch_items.append(
                CNCHItem(
                    stt=_to_int(_get_first(row, _aliases(mapping, "danh_sach_cnch", "stt", ["stt", "STT"]), len(cnch_items) + 1)),
                    ngay_xay_ra=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "ngay_xay_ra", ["ngay_xay_ra", "ngày xảy ra", "ngay"]))),
                    thoi_gian=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "thoi_gian", ["thoi_gian", "thời gian", "time"]))),
                    dia_diem=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "dia_diem", ["dia_diem", "địa điểm", "location"]))),
                    noi_dung_tin_bao=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "noi_dung_tin_bao", ["noi_dung_tin_bao", "nội dung tin báo", "noi_dung"]))),
                    luc_luong_tham_gia=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "luc_luong_tham_gia", ["luc_luong_tham_gia", "lực lượng tham gia"]))),
                    ket_qua_xu_ly=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "ket_qua_xu_ly", ["ket_qua_xu_ly", "kết quả xử lý"]))),
                    thiet_hai=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "thiet_hai", ["thiet_hai", "thiệt hại"]))),
                    thong_tin_nan_nhan=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "thong_tin_nan_nhan", ["thong_tin_nan_nhan", "thông tin nạn nhân"]))),
                    mo_ta=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cnch", "mo_ta", ["mo_ta", "mô tả"]), "")),
                )
            )

        phuong_tien_items: list[PhuongTienHuHongItem] = []
        for row in normalized.get("danh_sach_phuong_tien_hu_hong") or []:
            if not isinstance(row, dict):
                continue
            phuong_tien_items.append(
                PhuongTienHuHongItem(
                    bien_so=_to_text(_get_first(row, _aliases(mapping, "danh_sach_phuong_tien_hu_hong", "bien_so", ["bien_so", "biển số", "plate"]))),
                    tinh_trang=_to_text(_get_first(row, _aliases(mapping, "danh_sach_phuong_tien_hu_hong", "tinh_trang", ["tinh_trang", "tình trạng", "status"]))),
                )
            )

        cong_van_items: list[CongVanItem] = []
        for row in normalized.get("danh_sach_cong_van_tham_muu") or []:
            if not isinstance(row, dict):
                continue
            cong_van_items.append(
                CongVanItem(
                    so_ky_hieu=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cong_van_tham_muu", "so_ky_hieu", ["so_ky_hieu", "số ký hiệu", "so_hieu"]))),
                    noi_dung=_to_text(_get_first(row, _aliases(mapping, "danh_sach_cong_van_tham_muu", "noi_dung", ["noi_dung", "nội dung", "trich_yeu"]))),
                )
            )

        cong_tac_khac: list[str] = []
        for item in normalized.get("danh_sach_cong_tac_khac") or []:
            if isinstance(item, str):
                text = _to_text(item)
            elif isinstance(item, dict):
                text = _to_text(_get_first(item, _aliases(mapping, "danh_sach_cong_tac_khac", "noi_dung", ["noi_dung", "nội dung", "content"]), ""))
            else:
                text = _to_text(item)
            if text:
                cong_tac_khac.append(text)

        # Inject tuyên truyền online rows (STT 22-25) if not already present
        chi_tieu_items = _inject_online_rows(chi_tieu_items, normalized.get("tuyen_truyen_online") or {})

        # Map danh_sach_chi_vien (from sheet CHI VIỆN)
        chi_vien_items: list[ChiVienItem] = []
        for row in normalized.get("danh_sach_chi_vien") or []:
            if not isinstance(row, dict):
                continue
            chi_vien_items.append(
                ChiVienItem(
                    stt=_to_int(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "stt", ["STT", "stt"]), 0)),
                    ngay=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "ngay", ["NGÀY", "Ngày", "ngay"]))),
                    dia_diem=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "dia_diem", ["ĐỊA ĐIỂM", "dia_diem"]))),
                    khu_vuc_quan_ly=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "khu_vuc_quan_ly", ["KHU VỰC QUẢN LÝ", "khu_vuc"]))),
                    so_luong_xe=_to_int(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "so_luong_xe", ["SỐ LƯỢNG XE", "so_xe"]), 0)),
                    thoi_gian_di=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "thoi_gian_di", ["THỜI GIAN ĐI", "thoi_gian_di"]))),
                    thoi_gian_ve=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "thoi_gian_ve", ["THỜI GIAN VỀ", "thoi_gian_ve"]))),
                    chi_huy_chua_chay=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "chi_huy", ["CHỈ HUY", "chi_huy"]))),
                    ghi_chu=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chi_vien", "ghi_chu", ["Ghi chú", "ghi_chu"]))),
                )
            )

        # Map danh_sach_chay (from sheet VỤ CHÁY THỐNG KÊ)
        chay_items: list[VuChayItem] = []
        for row in normalized.get("danh_sach_chay") or []:
            if not isinstance(row, dict):
                continue
            chay_items.append(
                VuChayItem(
                    stt=_to_int(_get_first(row, _aliases(mapping, "danh_sach_chay", "stt", ["STT", "stt"]), 0)),
                    ngay_xay_ra=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "ngay_xay_ra", ["NGÀY", "ngay"]))),
                    thoi_gian=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "thoi_gian", ["THỜI GIAN", "thoi_gian"]))),
                    ten_vu_chay=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "ten_vu_chay", ["VỤ CHÁY", "ten_vu"]))),
                    dia_diem=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "dia_diem", ["ĐỊA ĐIỂM", "dia_diem"]))),
                    nguyen_nhan=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "nguyen_nhan", ["NGUYÊN NHÂN", "nguyen_nhan"]))),
                    thiet_hai_nguoi=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "thiet_hai_nguoi", ["THIỆT HẠI VỀ NGƯỜI", "thiet_hai"]))),
                    thiet_hai_tai_san=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "thiet_hai_tai_san", ["THIỆT HẠI TÀI SẢN", "tai_san"]))),
                    thoi_gian_khong_che=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "thoi_gian_khong_che", ["THỜI GIAN KHỐNG CHẾ"]))),
                    thoi_gian_dap_tat=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "thoi_gian_dap_tat", ["THỜI GIAN DẬP TẮT"]))),
                    so_luong_xe=_to_int(_get_first(row, _aliases(mapping, "danh_sach_chay", "so_luong_xe", ["SỐ LƯỢNG XE"]), 0)),
                    chi_huy=_to_text(_get_first(row, _aliases(mapping, "danh_sach_chay", "chi_huy", ["CHỈ HUY"]))),
                )
            )

        # Build TuyenTruyenOnline from nghiep_vu_raw
        online_dict = normalized.get("tuyen_truyen_online") or {}
        tuyen_truyen_online = TuyenTruyenOnline(
            so_tin_bai=_to_int(online_dict.get("so_tin_bai", 0)),
            so_hinh_anh=_to_int(online_dict.get("so_hinh_anh", 0)),
            cai_app_114=_to_int(online_dict.get("cai_app_114", 0)),
        )

        output = BlockExtractionOutput(
            header=header,
            phan_I_va_II_chi_tiet_nghiep_vu=nghiep_vu,
            bang_thong_ke=chi_tieu_items,
            danh_sach_cnch=cnch_items,
            danh_sach_phuong_tien_hu_hong=phuong_tien_items,
            danh_sach_cong_van_tham_muu=cong_van_items,
            danh_sach_cong_tac_khac=cong_tac_khac,
            # NEW:
            danh_sach_chi_vien=chi_vien_items,
            danh_sach_chay=chay_items,
            tuyen_truyen_online=tuyen_truyen_online,
        )
        _assert_contract_or_raise(output)
        return output

    def run(self, sheet_data: dict[str, Any] | None, schema_path: str | None = None) -> PipelineResult:
        try:
            if schema_path:
                core = _extract_core(sheet_data)
                custom_mapping = _load_custom_mapping(schema_path)
                output = _build_output_custom(core, custom_mapping, schema_path=schema_path)
            else:
                normalized = self.normalize(sheet_data)
                output = self.map_to_schema(normalized)
            return PipelineResult(
                status="ok",
                attempts=1,
                output=output,
                errors=[],
                chi_tiet_cnch="",
            )
        except Exception as exc:
            return PipelineResult(
                status="failed",
                attempts=1,
                output=None,
                errors=[str(exc)],
                chi_tiet_cnch="",
            )


# ─── Worksheet → row-level processing helpers ─────────────────────────────────

def _parse_rows_from_sheet(sheet_rows: list[list]) -> tuple[list[str], list[list[str]]]:
    """Strip empty rows; return (header_row, data_rows)."""
    non_empty = [row for row in sheet_rows if any(str(c).strip() for c in row)]
    if not non_empty:
        return [], []
    return non_empty[0], non_empty[1:]


def _row_to_dict(header: list[str], row: list[str]) -> dict[str, str]:
    return {str(h).strip(): str(v).strip() for h, v in zip(header, row)}


# ─── DailyReportBuilder ──────────────────────────────────────────────────────

class DailyReportBuilder:
    """
    Orchestrates multi-worksheet snapshot ingestion into a single BlockExtractionOutput.

    For each worksheet config that has a ``schema_path``, the pipeline:
      1. Reads rows from ``sheet_data[worksheet]``
      2. Maps each row → dict via the YAML schema (alias resolution)
      3. Validates each row
      4. Feeds the validated row dicts into SheetExtractionPipeline
         (bypassing the global ``sheet_mapping.yaml``)
      5. Merges the per-worksheet BlockExtractionOutput into the composite report

    Worksheets without a ``schema_path`` are silently skipped (legacy mode).

    Multi-date mode: when a worksheet contains multiple date groups (e.g. 30 days
    of data in one sheet), build_all_by_date() groups rows by date and returns
    one BlockExtractionOutput per date, each merged with the non-date worksheets
    (VỤ CHÁY, CNCH, CHI VIỆN).
    """

    def __init__(
        self,
        template: Any,  # duck-typed; only .google_sheet_configs is needed
        sheet_data: dict[str, list[list[str]]],
        worksheet_configs: list[dict],
    ) -> None:
        self.template = template
        self.sheet_data = sheet_data
        self.worksheet_configs = worksheet_configs
        self._pipeline = SheetExtractionPipeline()
        # Runtime artifacts for validation summary
        self._row_entries: list[dict] = []
        self._report_date: str | None = None

    # ── public API ──────────────────────────────────────────────────────────

    def build(self) -> "BlockExtractionOutput":
        """Process all configured worksheets; return composite report."""
        report = self._create_empty_report()

        for cfg in self.worksheet_configs:
            worksheet = cfg.get("worksheet")
            schema_path = cfg.get("schema_path")
            if not worksheet or worksheet not in self.sheet_data:
                continue

            if schema_path:
                self._process_worksheet_with_schema(report, worksheet, schema_path, cfg)
            # else: silently skip; legacy behaviour

        self._report_date = self._extract_report_date(report)
        return report

    def build_all_by_date(self) -> dict[str, "BlockExtractionOutput"]:
        """
        Group rows by (day, month) date extracted from the BC NGÀY worksheet
        and return one BlockExtractionOutput per date.

        Non-date worksheets (VỤ CHÁY, CNCH, CHI VIỆN, etc.) are merged into
        every date report since their rows are already date-tagged.

        Returns a dict: { "DD/MM": BlockExtractionOutput, ... }
        Sorted by date string ascending.
        """
        # ── Step 1: Identify the primary (date-carrying) worksheet config ──────────
        date_config: dict | None = None
        for cfg in self.worksheet_configs:
            if cfg.get("worksheet") and cfg.get("schema_path"):
                date_config = cfg
                break  # First config with schema_path is the BC NGÀY master

        if not date_config:
            # No date-capable config — fall back to legacy single-date build
            report = self.build()
            return {report.header.ngay_bao_cao or "unknown": report}

        master_ws = date_config["worksheet"]
        master_schema = date_config["schema_path"]
        master_cfg = date_config

        # ── Step 2: Parse rows from master worksheet ─────────────────────────────
        rows = self.sheet_data.get(master_ws, [])
        if not rows or len(rows) < 2:
            # Not enough rows to build any report
            report = self._create_empty_report()
            return {"": report}

        header_row = rows[1]
        day_col_idx, month_col_idx = self._find_date_columns(header_row, master_schema)

        # ── Step 3: Group rows by date ──────────────────────────────────────────
        date_groups: dict[str, list[int]] = {}  # "DD/MM" -> [row_indices]
        # Data rows start from index 2 (row 2 in Excel = first data row)
        for row_idx, row in enumerate(rows[2:], start=2):
            day_raw = row[day_col_idx] if day_col_idx >= 0 and day_col_idx < len(row) else None
            month_raw = row[month_col_idx] if month_col_idx >= 0 and month_col_idx < len(row) else None
            date_key = self._make_date_key(day_raw, month_raw)
            if date_key:
                date_groups.setdefault(date_key, []).append(row_idx)

        if not date_groups:
            # No date found — fall back to single date with all rows
            report = self.build()
            return {report.header.ngay_bao_cao or "unknown": report}

        # ── Step 4: Build one report per date group ───────────────────────────────
        results: dict[str, "BlockExtractionOutput"] = {}

        for date_key in sorted(date_groups.keys()):
            row_indices = date_groups[date_key]
            self._row_entries.clear()  # reset per-date to keep validation_summary clean

            # 4a: Build date-specific report from master worksheet
            date_report = self._build_report_for_date(
                worksheet=master_ws,
                schema_path=master_schema,
                cfg=master_cfg,
                row_indices=row_indices,
            )

            # 4b: Merge non-date worksheets (they carry their own date fields per row)
            for cfg in self.worksheet_configs:
                ws = cfg.get("worksheet", "")
                if ws == master_ws:
                    continue
                schema_path = cfg.get("schema_path")
                if schema_path:
                    # Non-master: process ALL rows (no date grouping)
                    self._process_worksheet_with_schema(date_report, ws, schema_path, cfg)

            # 4c: Attach report_date to the output for ingestion service
            date_report._report_date = date_key
            results[date_key] = date_report

        return results

    def get_validation_summary(self) -> dict:
        """Return row-level validation summary."""
        return self._build_validation_summary()

    # ── private helpers ─────────────────────────────────────────────────────

    def _find_date_columns(self, header_row: list, schema_path: str) -> tuple[int, int]:
        """
        Return (day_col_index, month_col_index) for NGÀY and THÁNG columns.
        Returns (-1, -1) if not found.

        KV30 files have 3 header rows (group → sub-header → sub-header), where
        NGÀY/THÁNG live in row 0 and the actual data column names live in row 1.
        We look across all rows[0..N] for NGÀY/THÁNG.
        """
        rows = self.sheet_data.get(self.worksheet_configs[0].get("worksheet", ""), [])

        day_candidates = {"ngay", "ngày"}
        month_candidates = {"thang", "tháng"}

        for row_offset, header_candidate in enumerate(rows):
            if not header_candidate:
                continue
            header_norm: dict[str, int] = {}
            for idx, h in enumerate(header_candidate):
                norm = _normalize_key(str(h))
                header_norm[norm] = idx

            day_col = -1
            month_col = -1
            found_day = False
            found_month = False

            for norm_key, col_idx in header_norm.items():
                if not found_day and norm_key in day_candidates:
                    day_col = col_idx
                    found_day = True
                if not found_month and norm_key in month_candidates:
                    month_col = col_idx
                    found_month = True
                if found_day and found_month:
                    break

            if found_day and found_month:
                return day_col, month_col

        # Fallback: look in header_row using schema aliases
        header_norm: dict[str, int] = {}
        for idx, h in enumerate(header_row):
            norm = _normalize_key(str(h))
            header_norm[norm] = idx

        mapping = _load_custom_mapping(schema_path)
        sheet_mapping = mapping.get("sheet_mapping", mapping) if isinstance(mapping, dict) else {}
        header_spec = sheet_mapping.get("header", {})

        day_col = -1
        month_col = -1

        for field_name, spec in header_spec.items():
            aliases: list[str] = []
            if isinstance(spec, dict):
                aliases = spec.get("aliases", [])
            elif isinstance(spec, list):
                aliases = spec
            for alias_candidate in [field_name] + aliases:
                norm = _normalize_key(str(alias_candidate))
                if norm in header_norm:
                    if field_name == "ngay_bao_cao_day":
                        day_col = header_norm[norm]
                    elif field_name == "ngay_bao_cao_month":
                        month_col = header_norm[norm]
                    break

        return day_col, month_col

    def _make_date_key(self, day_raw: Any, month_raw: Any) -> str | None:
        """Build a DD/MM string from raw day and month values, or None if invalid."""
        try:
            day_str = str(day_raw or "").strip().replace(".0", "")
            month_str = str(month_raw or "").strip().replace(".0", "")
            day_int = int(day_str) if day_str else 0
            month_int = int(month_str) if month_str else 0
            if 1 <= day_int <= 31 and 1 <= month_int <= 12:
                return f"{day_int:02d}/{month_int:02d}"
        except (ValueError, TypeError):
            pass
        return None

    def _build_report_for_date(
        self,
        worksheet: str,
        schema_path: str,
        cfg: dict,
        row_indices: list[int],
    ) -> "BlockExtractionOutput":
        """
        Build a single BlockExtractionOutput for a specific date group,
        processing only the rows at ``row_indices``.
        """
        from app.engines.extraction.mapping.schema_loader import load_schema
        from app.engines.extraction.mapping.mapper import map_row_to_document_data
        from app.engines.extraction.validation.row_validator import (
            build_validation_model,
            validate_row,
        )

        rows = self.sheet_data.get(worksheet, [])
        if len(rows) < 2:
            return self._create_empty_report()

        # Row 0 = group headers (merged), Row 1 = sub-headers (actual column names)
        # For KV30 files, NGÀY/THÁNG may be in row 0 while data names are in row 1.
        # Use sub-header row (rows[1]) as primary header, but pull date values from
        # the combined row that _find_date_columns built (or row 0).
        sub_header = rows[1]
        combined = getattr(self, "_combined_header_row", None)

        try:
            ingestion_schema = load_schema(schema_path)
        except Exception:
            return self._create_empty_report()

        try:
            validation_model = build_validation_model(ingestion_schema)
        except Exception:
            validation_model = None

        report = self._create_empty_report()

        for row_idx in row_indices:
            if row_idx < 1 or row_idx >= len(rows):
                continue
            row = rows[row_idx]

            row_dict: dict[str, Any] = {}
            for col_idx in range(len(sub_header)):
                # KV30 format: NGÀY/THÁNG columns have None in rows[1] (sub-header row).
                # For those columns, use rows[0] as both header name AND data source.
                # For all other columns, use rows[1] as header name and row[col_idx] as data.
                if col_idx < len(sub_header) and sub_header[col_idx] is None:
                    # Date/merge column — use rows[0] for header name and data
                    if col_idx < len(rows[0]) and col_idx < len(row):
                        header_name = str(rows[0][col_idx]).strip()
                        row_dict[normalize_unicode_text(header_name)] = row[col_idx]
                else:
                    # Normal column — use sub_header name and row data
                    if col_idx < len(row):
                        header_name = str(sub_header[col_idx]).strip()
                        row_dict[normalize_unicode_text(header_name)] = row[col_idx]

            doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)

            if validation_model is not None:
                result = validate_row(
                    model=validation_model,
                    normalized_data=doc_data,
                    matched_fields=m,
                    total_fields=t,
                    missing_required=miss,
                )
            else:
                result = None

            self._row_entries.append(
                {"worksheet": worksheet, "row_index": row_idx + 1, "validation": result}
            )

            if result is not None and not result.is_valid:
                continue

            sheet_payload = {"data": doc_data}
            pipeline_result = self._pipeline.run(sheet_payload, schema_path=schema_path)
            if pipeline_result.status != "ok" or pipeline_result.output is None:
                continue

            partial = pipeline_result.output
            # Always merge all sections from every worksheet's output
            for attr in _SECTION_ATTRS:
                self._merge_section(report, partial, attr)

        return report

    def _process_worksheet_with_schema(
        self,
        report: BlockExtractionOutput,
        worksheet: str,
        schema_path: str,
        cfg: dict,
    ) -> None:
        from app.engines.extraction.mapping.schema_loader import load_schema
        from app.engines.extraction.mapping.mapper import map_row_to_document_data
        from app.engines.extraction.validation.row_validator import (
            build_validation_model,
            validate_row,
        )

        rows = self.sheet_data.get(worksheet, [])
        if not rows:
            return

        try:
            ingestion_schema = load_schema(schema_path)
        except Exception:
            return

        try:
            validation_model = build_validation_model(ingestion_schema)
        except Exception:
            validation_model = None

        # Row 0 = group headers (merged), Row 1 = sub-headers (actual column names), Row 2+ = data
        if len(rows) < 2:
            return
        header_row = rows[1]
        for row_idx, row in enumerate(rows[2:], start=2):
            # Build row dict: raw header → raw value
            # Note: keep raw keys (e.g. "Ngày xảy ra sự cố") because map_row_to_document_data
            # normalizes its input keys internally using _normalize_key, which will
            # convert them to the canonical form matching the schema aliases.
            row_dict: dict[str, Any] = {}
            for col_idx, header_val in enumerate(header_row):
                if header_val is not None and col_idx < len(row):
                    row_dict[str(header_val).strip()] = row[col_idx]

            matched, total, missing = 0, len(ingestion_schema.fields), []

            doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)
            matched, total, missing = m, t, miss

            if validation_model is not None:
                result = validate_row(
                    model=validation_model,
                    normalized_data=doc_data,
                    matched_fields=matched,
                    total_fields=total,
                    missing_required=missing,
                )
            else:
                result = None

            self._row_entries.append(
                {"worksheet": worksheet, "row_index": row_idx + 1, "validation": result}
            )

            if result is not None and not result.is_valid:
                continue

            sheet_payload = {"data": doc_data}
            pipeline_result = self._pipeline.run(sheet_payload, schema_path=schema_path)
            if pipeline_result.status != "ok" or pipeline_result.output is None:
                continue

            partial = pipeline_result.output
            # Always merge all sections from every worksheet's output
            for attr in _SECTION_ATTRS:
                self._merge_section(report, partial, attr)

    def _merge_section(self, report: BlockExtractionOutput, partial: BlockExtractionOutput, attr: str) -> None:
        if not hasattr(report, attr):
            return  # Unknown section — no-op, matching existing test expectation
        current = getattr(report, attr)
        incoming = getattr(partial, attr)

        if attr in _HEADER_ATTRS:
            # Header: non-empty incoming wins
            for field in _HEADER_ATTRS[attr]:
                cur_val = getattr(current, field, None)
                inc_val = getattr(incoming, field, None)
                if not cur_val and inc_val:
                    setattr(current, field, inc_val)
        elif attr in _LIST_ATTRS:
            # List sections: extend
            if isinstance(incoming, list):
                current.extend(incoming)
        elif attr == "phan_I_va_II_chi_tiet_nghiep_vu":
            # Numeric fields: non-zero incoming wins; non-empty string wins
            for field in _NGHIEP_VU_NUMERIC:
                cur = getattr(current, field, 0)
                inc = getattr(incoming, field, None)
                if inc not in (None, "", 0):
                    setattr(current, field, inc)
            for field in _NGHIEP_VU_STRING:
                cur = getattr(current, field, "")
                inc = getattr(incoming, field, "")
                if inc and not cur:
                    setattr(current, field, inc)
        elif attr == "tuyen_truyen_online":
            # Online: non-zero wins
            for field in ("so_tin_bai", "so_hinh_anh", "cai_app_114"):
                cur = getattr(current, field, 0)
                inc = getattr(incoming, field, None)
                if inc and inc > 0 and cur == 0:
                    setattr(current, field, inc)
        elif attr in ("bang_thong_ke",):
            # bang_thong_ke: extend by STT, no duplicates
            existing_stt = {str(it.stt).strip() for it in current}
            for item in incoming:
                stt = str(getattr(item, "stt", "")).strip()
                if stt and stt not in existing_stt:
                    current.append(item)
                    existing_stt.add(stt)

    def _create_empty_report(self) -> BlockExtractionOutput:
        return BlockExtractionOutput(
            header=BlockHeader(),
            phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
            bang_thong_ke=[],
            danh_sach_cnch=[],
            danh_sach_phuong_tien_hu_hong=[],
            danh_sach_cong_van_tham_muu=[],
            danh_sach_cong_tac_khac=[],
            danh_sach_chi_vien=[],
            danh_sach_chay=[],
            danh_sach_sclq=[],
            tuyen_truyen_online=TuyenTruyenOnline(),
        )

    def _extract_report_date(self, report: BlockExtractionOutput) -> str | None:
        date = report.header.ngay_bao_cao
        return date if date else None

    def _build_validation_summary(self) -> dict:
        total = len(self._row_entries)
        valid = sum(1 for e in self._row_entries if e.get("validation") and e["validation"].is_valid)
        invalid = sum(1 for e in self._row_entries if e.get("validation") and not e["validation"].is_valid)

        # Warn about worksheets with no rows processed
        worksheets = {e["worksheet"] for e in self._row_entries}
        missing_ws = [
            cfg["worksheet"]
            for cfg in self.worksheet_configs
            if cfg.get("schema_path") and cfg["worksheet"] not in worksheets
        ]

        return {
            "total_rows": total,
            "valid_rows": valid,
            "invalid_rows_count": invalid,
            "worksheets_processed": list(worksheets),
            "worksheets_missing": missing_ws,
            "report_date": self._report_date,
            "warnings": [
                f"Worksheet '{ws}' configured but produced no rows" for ws in missing_ws
            ],
        }


# ─── Section metadata ───────────────────────────────────────────────────────

_HEADER_ATTRS = {
    "header": {"so_bao_cao", "ngay_bao_cao", "thoi_gian_tu_den", "don_vi_bao_cao"},
}

_LIST_ATTRS = {
    "danh_sach_cnch",
    "danh_sach_phuong_tien_hu_hong",
    "danh_sach_cong_van_tham_muu",
    "danh_sach_cong_tac_khac",
    "danh_sach_chi_vien",
    "danh_sach_chay",
    "danh_sach_sclq",
    # bang_thong_ke is handled specially via STT-dedup; excluded here
}

_SECTION_ATTRS = [
    "header",
    "phan_I_va_II_chi_tiet_nghiep_vu",
    "bang_thong_ke",
    "danh_sach_cnch",
    "danh_sach_phuong_tien_hu_hong",
    "danh_sach_cong_van_tham_muu",
    "danh_sach_cong_tac_khac",
    "danh_sach_chi_vien",
    "danh_sach_chay",
    "danh_sach_sclq",
    "tuyen_truyen_online",
]

_NGHIEP_VU_NUMERIC = {
    "tong_so_vu_chay",
    "tong_so_vu_no",
    "tong_sclq",
    "tong_so_vu_cnch",
    "quan_so_truc",
    "tong_chi_vien",
    "tong_cong_van",
    "tong_bao_cao",
    "tong_ke_hoach",
    "tong_xe_hu_hong",
    "tong_tin_bai",
    "tong_hinh_anh",
    "so_lan_cai_app_114",
}

_NGHIEP_VU_STRING = {"chi_tiet_cnch", "cong_tac_an_ninh"}

