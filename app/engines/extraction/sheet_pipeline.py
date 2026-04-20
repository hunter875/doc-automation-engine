"""Deterministic Google Sheets → canonical extraction contract pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.engines.extraction.schemas import (
    BlockExtractionOutput,
    BlockHeader,
    BlockNghiepVu,
    CNCHItem,
    ChiTieu,
    CongVanItem,
    PhuongTienHuHongItem,
    PipelineResult,
)


EXPECTED_TOP_LEVEL_KEYS = {
    "header",
    "phan_I_va_II_chi_tiet_nghiep_vu",
    "bang_thong_ke",
    "danh_sach_cnch",
    "danh_sach_phuong_tien_hu_hong",
    "danh_sach_cong_van_tham_muu",
    "danh_sach_cong_tac_khac",
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

    required_for_60 = {"55", "56", "57", "58", "59", "61"}
    if "60" not in by_stt and required_for_60.issubset(by_stt):
        kq60 = _kq("55") - (_kq("56") + _kq("57") + _kq("58") + _kq("59") + _kq("61"))
        if kq60 >= 0:
            insertions.append(
                ChiTieu(stt="60", noi_dung="Chiến sĩ nghĩa vụ (hợp đồng lao động)", ket_qua=kq60)
            )

    merged = items + insertions
    merged.sort(key=lambda x: int(str(x.stt)) if str(x.stt).isdigit() else 9999)
    return merged


class SheetExtractionPipeline:
    """Map Google Sheets payloads into the canonical block extraction schema."""

    def normalize(self, sheet_data: dict[str, Any] | None) -> dict[str, Any]:
        raw = sheet_data or {}
        mapping = _load_sheet_mapping()

        # Runtime extraction job payload often stores business data under extracted_data.data
        # (from ingestion row_document shape).
        core = raw
        nested_data = raw.get("data") if isinstance(raw.get("data"), dict) else None
        if isinstance(nested_data, dict):
            core = nested_data

        header_raw = core.get("header")
        if not isinstance(header_raw, dict):
            # flat payload support: let alias resolver read directly from root keys
            header_raw = core if isinstance(core, dict) else {}

        nghiep_vu_raw = core.get("phan_I_va_II_chi_tiet_nghiep_vu")
        if not isinstance(nghiep_vu_raw, dict):
            nghiep_vu_raw = core.get("nghiep_vu") if isinstance(core.get("nghiep_vu"), dict) else {}
        if not isinstance(nghiep_vu_raw, dict) or not nghiep_vu_raw:
            # flat payload support for nghiệp vụ scalar fields
            nghiep_vu_raw = core if isinstance(core, dict) else {}

        btk_raw = core.get("bang_thong_ke")
        if not isinstance(btk_raw, list):
            btk_raw = core.get("chi_tieu") if isinstance(core.get("chi_tieu"), list) else []

        if not btk_raw:
            btk_raw = _build_bang_thong_ke_from_flat(mapping, core if isinstance(core, dict) else {})

        return {
            "header": header_raw,
            "nghiep_vu": nghiep_vu_raw,
            "bang_thong_ke": btk_raw,
            "danh_sach_cnch": _as_list(core.get("danh_sach_cnch")),
            "danh_sach_phuong_tien_hu_hong": _as_list(core.get("danh_sach_phuong_tien_hu_hong")),
            "danh_sach_cong_van_tham_muu": _as_list(core.get("danh_sach_cong_van_tham_muu")),
            "danh_sach_cong_tac_khac": _as_list(core.get("danh_sach_cong_tac_khac")),
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

        output = BlockExtractionOutput(
            header=header,
            phan_I_va_II_chi_tiet_nghiep_vu=nghiep_vu,
            bang_thong_ke=chi_tieu_items,
            danh_sach_cnch=cnch_items,
            danh_sach_phuong_tien_hu_hong=phuong_tien_items,
            danh_sach_cong_van_tham_muu=cong_van_items,
            danh_sach_cong_tac_khac=cong_tac_khac,
        )
        _assert_contract_or_raise(output)
        return output

    def run(self, sheet_data: dict[str, Any] | None) -> PipelineResult:
        try:
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
