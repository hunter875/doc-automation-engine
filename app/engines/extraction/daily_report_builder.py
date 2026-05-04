"""Deterministic Google Sheets → canonical extraction contract pipeline."""

from __future__ import annotations

from functools import lru_cache
import logging
import re
import unicodedata
from typing import Any

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

from app.engines.extraction.kv30_fixed_mapping import (  # noqa: E402,F401
    get_kv30_data_start_row,
    get_kv30_item_report_date_key,
    is_kv30_config,
    is_kv30_worksheet,
    kv30_extract_master_date_key,
    map_kv30_cnch_row,
    map_kv30_chi_vien_row,
    map_kv30_detail_row,
    map_kv30_master_row,
    map_kv30_sclq_row,
    map_kv30_vu_chay_row,
)
from app.engines.extraction.kv30_business_mapping import (
    build_kv30_bang_thong_ke,
    build_kv30_word_context,
)
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline
from app.engines.extraction.mapping.normalizer import normalize_unicode_text, normalize_header_key
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.schema_resolver import SchemaResolver
from app.engines.extraction.mapping.mapper import map_row_to_document_data
from app.engines.extraction.validation.row_validator import build_validation_model, validate_row

logger = logging.getLogger(__name__)


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


def _row_looks_like_data(row: list[Any]) -> bool:
    """Return True if the majority of non-empty cells look like numbers or dates."""
    total = 0
    numeric_or_date = 0

    for cell in row:
        if cell is None:
            continue
        s = str(cell).strip()
        if not s:
            continue

        total += 1
        s2 = s.replace(".0", "")
        if s2.isdigit():
            numeric_or_date += 1
            continue

        if "/" in s:
            parts = s.split("/")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                numeric_or_date += 1

    return total > 0 and numeric_or_date / total > 0.5


def _normalize_key(value: str) -> str:
    """Normalize a key for space-separated matching. Delegates to normalize_header_key."""
    return normalize_header_key(str(value))


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
    return SchemaResolver.load_sheet_mapping()




def _load_custom_mapping(schema_path: str) -> dict[str, Any]:
    return SchemaResolver.get_sheet_mapping(schema_path)


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
            # Fallback: look up the first alias from the nghiep_vu section.
            # stt_map["field"] values are snake_case schema names (e.g. "tong_so_vu_chay")
            # but flat_data keys are normalized column headers (e.g. "vu chay thong ke").
            # The nghiep_vu section maps field names to their aliases, so we use
            # the first alias as the fallback lookup key in flat_data.
            nghiep_vu_section = mapping.get("nghiep_vu", {})
            if isinstance(nghiep_vu_section, dict):
                field_spec = nghiep_vu_section.get(field_name)
                if isinstance(field_spec, dict):
                    aliases = field_spec.get("aliases", [])
                    if aliases and isinstance(aliases, list):
                        first_alias_norm = _normalize_key(aliases[0])
                        raw_value = flat_data.get(first_alias_norm)
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


def _parse_rows_from_sheet(sheet_rows: list[list]) -> tuple[list[str], list[list[str]]]:
    """Strip empty rows; return (header_row, data_rows)."""
    non_empty = [row for row in sheet_rows if any(str(c).strip() for c in row)]
    if not non_empty:
        return [], []
    return non_empty[0], non_empty[1:]


def _row_to_dict(header: list[str], row: list[str]) -> dict[str, str]:
    return {
        normalize_header_key(str(h).strip()): str(v).strip()
        for h, v in zip(header, row)
        if str(h).strip()
    }


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
        # Validate: if target_section is set, schema_path is required
        for cfg in self.worksheet_configs:
            if cfg.get("target_section") and not cfg.get("schema_path"):
                raise ProcessingError("schema_path is required when target_section is specified")

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
        report._report_date = self._report_date
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
            return {"": report}  # Use empty string key for fallback

        master_ws = date_config["worksheet"]
        master_schema = date_config["schema_path"]
        master_cfg = date_config

        # ── Step 2: Parse rows from master worksheet ─────────────────────────────
        rows = self.sheet_data.get(master_ws, [])
        if not rows or len(rows) < 2:
            # Not enough rows to build any report
            report = self._create_empty_report()
            return {"": report}

        # ── Step 2a: Parse header indices from config (deterministic) ─────────────────
        # If config provides header_row/data_start_row, use them exactly.
        # KV30 BC NGÀY: header_row=1, data_start_row=2
        has_header_cfg = "header_row" in master_cfg
        has_data_cfg = "data_start_row" in master_cfg
        if has_header_cfg or has_data_cfg:
            if not has_header_cfg or not has_data_cfg:
                raise ProcessingError(
                    message=f"Missing header_row/data_start_row config for worksheet '{master_ws}'."
                )
            cfg_header_row = master_cfg.get("header_row")
            cfg_data_start = master_cfg.get("data_start_row")
            header_row_idx = cfg_header_row
            data_start = cfg_data_start
            if not (0 <= header_row_idx < len(rows) and 0 <= data_start < len(rows)):
                raise ProcessingError(
                    message=f"Invalid header_row/data_start_row config for worksheet '{master_ws}'. "
                            f"header_row={cfg_header_row}, data_start_row={cfg_data_start}, "
                            f"available_rows={len(rows)}."
                )
        else:
            # Schema-driven: use row 0 as fallback, will be replaced by schema field names
            cfg_header_row = master_cfg.get("header_row", -1)
            cfg_data_start = master_cfg.get("data_start_row", 1)
            if cfg_header_row == -1:
                header_row_idx = 0
                data_start = cfg_data_start
            elif 0 <= cfg_header_row < len(rows) and 0 <= cfg_data_start < len(rows):
                header_row_idx = cfg_header_row
                data_start = cfg_data_start
            else:
                raise ProcessingError(
                    message=f"Invalid header_row/data_start_row config for worksheet '{master_ws}'. "
                            f"header_row={cfg_header_row}, data_start_row={cfg_data_start}, "
                            f"available_rows={len(rows)}."
                )

        # ── Step 2b: Detect date columns from header row (only for generic path) ───
        day_col_idx, month_col_idx = -1, -1
        if not (master_ws in {"BC NGÀY", "BC NGAY"} and is_kv30_config(master_cfg)):
            header_row = rows[header_row_idx]
            day_col_idx, month_col_idx = self._find_date_columns(header_row, master_schema)

        # ── Step 3: Group rows by date ──────────────────────────────────────────
        date_groups: dict[str, list[int]] = {}  # "DD/MM" -> [row_indices]

        if master_ws in {"BC NGÀY", "BC NGAY"} and is_kv30_config(master_cfg):
            # KV30 fixed path: use fixed column indices (0=day, 1=month)
            # IMPORTANT: Scan ALL rows (not just from data_start) because KV30 sheets
            # may have summary/header rows interspersed. Let kv30_extract_master_date_key
            # filter out non-data rows.
            for row_idx, row in enumerate(rows):
                dk = kv30_extract_master_date_key(row)
                if dk:
                    date_groups.setdefault(dk, []).append(row_idx)
        else:
            # Generic path: detect date columns from header row
            for row_idx, row in enumerate(rows[data_start:], start=data_start):
                day_raw = row[day_col_idx] if day_col_idx >= 0 and day_col_idx < len(row) else None
                month_raw = row[month_col_idx] if month_col_idx >= 0 and month_col_idx < len(row) else None
                date_key = self._make_date_key(day_raw, month_raw)
                if date_key:
                    date_groups.setdefault(date_key, []).append(row_idx)

        if not date_groups:
            if master_ws in {"BC NGÀY", "BC NGAY"} and is_kv30_config(master_cfg):
                # KV30: no valid daily rows found (maybe only summary/header rows)
                logger.warning(
                    "KV30 BC NGAY: no valid daily date rows found after filtering. "
                    "First 10 rows for diagnosis: %s",
                    rows[:10],
                )
                return {}  # No date reports; service will return ok with empty jobs
            # Generic mode: fall back to single date with all rows
            report = self.build()
            return {"": report}

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
                header_row_idx=header_row_idx,
                data_start=data_start,
            )

            # 4b: Merge non-date worksheets (they carry their own date fields per row)
            for cfg in self.worksheet_configs:
                ws = cfg.get("worksheet", "")
                if ws == master_ws:
                    continue
                schema_path = cfg.get("schema_path")
                if is_kv30_worksheet(ws):
                    self._process_worksheet_kv30_detail(
                        date_report, ws, cfg, only_date=date_key,
                    )
                elif schema_path:
                    # Generic: only process rows matching the date_key
                    self._process_worksheet_with_schema(
                        date_report,
                        ws,
                        schema_path,
                        cfg,
                        only_date=date_key,
                    )

            # 4c: Apply KV30 business mapping if this is a KV30 report
            if master_ws in {"BC NGÀY", "BC NGAY"} and is_kv30_config(master_cfg):
                # Extract master data from phan_I_va_II section
                master_data = date_report.phan_I_va_II_chi_tiet_nghiep_vu.model_dump() if date_report.phan_I_va_II_chi_tiet_nghiep_vu else {}

                # Collect detail items
                detail_items = {
                    "danh_sach_chay": [item.model_dump() if hasattr(item, "model_dump") else item for item in date_report.danh_sach_chay],
                    "danh_sach_cnch": [item.model_dump() if hasattr(item, "model_dump") else item for item in date_report.danh_sach_cnch],
                    "danh_sach_chi_vien": [item.model_dump() if hasattr(item, "model_dump") else item for item in date_report.danh_sach_chi_vien],
                    "danh_sach_sclq": [item.model_dump() if hasattr(item, "model_dump") else item for item in date_report.danh_sach_sclq],
                }

                # Build full STT 1-61 bang_thong_ke
                defaults = {}  # TODO: load from config/template if needed
                bang_thong_ke = build_kv30_bang_thong_ke(master_data, detail_items, defaults)
                date_report.bang_thong_ke = bang_thong_ke

                logger.info(
                    "[KV30_BUSINESS] Applied business mapping for date=%s: bang_thong_ke_count=%d",
                    date_key, len(bang_thong_ke),
                )

            # 4d: Attach report_date to the output for ingestion service
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
        rows: list[list[str]] = []
        if self.worksheet_configs:
            ws_name = self.worksheet_configs[0].get("worksheet", "")
            rows = self.sheet_data.get(ws_name, [])

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

    def _normalize_date_to_date(self, value: Any, date_key_hint: str | None = None, default_year: int = 2026) -> date | None:
        """Normalize a date-like cell to a Python date object.

        Supported:
        - datetime/date objects
        - Excel serial number > 31, base date 1899-12-30
        - Google/JS Date string: "Date(2026,3,9)" means 09/04/2026 (month zero-based)
        - String formats: "%d/%m/%Y", "%d/%m/%y", "%d/%m", "%Y-%m-%d"
        - Numeric 1..31 + date_key_hint="DD/MM" treats as day-of-month of hint month/year
        """
        from datetime import date, datetime, timedelta
        import re

        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value).strip()
        if not text:
            return None

        # Google/JS-style Date(year, monthIndex, day) — month is zero-based
        m = re.match(r"^Date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)$", text)
        if m:
            y = int(m.group(1))
            month_raw = int(m.group(2))
            d = int(m.group(3))
            if 0 <= month_raw <= 11:
                month = month_raw + 1
            else:
                return None
            try:
                return date(y, month, d)
            except ValueError:
                return None

        # Numeric / excel serial / day-of-month
        if isinstance(value, (int, float)) or text.replace(".0", "").isdigit():
            try:
                n = int(float(text))
                # 1..31 with hint: treat as day-of-month
                if 1 <= n <= 31 and date_key_hint:
                    # Extract month/year from hint "DD/MM" or "DD/MM/YYYY"
                    parts = str(date_key_hint).split("/")
                    if len(parts) >= 2:
                        hint_month = int(parts[1])
                        hint_year = int(parts[2]) if len(parts) >= 3 else default_year
                        try:
                            return date(hint_year, hint_month, n)
                        except ValueError:
                            pass
                # Excel serial date
                if n > 31:
                    return date(1899, 12, 30) + timedelta(days=n)
            except Exception:
                pass

        # String formats
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d/%m", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                if dt.year == 1900:
                    dt = dt.replace(year=default_year)
                return dt.date()
            except ValueError:
                continue

        return None

    def _normalize_date_to_ddmm(self, value: Any, date_key_hint: str | None = None) -> str | None:
        """Normalize a date-like cell to DD/MM string."""
        d = self._normalize_date_to_date(value, date_key_hint=date_key_hint)
        if d:
            return f"{d.day:02d}/{d.month:02d}"
        return None

    def _parse_vietnamese_time(self, value: Any) -> tuple[int, int] | None:
        """Parse Vietnamese time strings.

        Supported formats:
        - "17 giờ 20 phút" / "16 giờ 33 phút"
        - "22 giờ 36 phút" / "02 giờ 55 phút" / "05 giờ 40 phút"
        - "15:10" / "15 giờ"
        - Multiline text (takes first match)
        """
        import re

        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None

        # Handle multiline: take first non-empty line
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # "17 giờ 20 phút" / "16 giờ 33 phút"
            m = re.match(r"(\d{1,2})\s*giờ(?:\s*(\d{1,2})\s*phút?)?", line)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                return (hour, minute)

            # "15:10" format
            m = re.match(r"(\d{1,2}):(\d{1,2})", line)
            if m:
                return (int(m.group(1)), int(m.group(2)))

            # "15 giờ" only
            m = re.match(r"(\d{1,2})\s*giờ\s*$", line)
            if m:
                return (int(m.group(1)), 0)

        return None

    def _compute_report_date_key(self, event_date_value: Any, event_time_value: Any = None, date_key_hint: str | None = None) -> str | None:
        """Compute the report date key (DD/MM) given event date and time.

        Logic:
        - Parse event_date to a date object
        - Parse event_time; if >= 07:30, report_date = event_date + 1 day
        - Otherwise, report_date = event_date
        """
        from datetime import timedelta

        event_date = self._normalize_date_to_date(event_date_value, date_key_hint=date_key_hint)
        if not event_date:
            return None

        event_time = self._parse_vietnamese_time(event_time_value)

        CUTOFF = (7, 30)  # 07:30

        if event_time:
            if event_time >= CUTOFF:
                report_date = event_date + timedelta(days=1)
            else:
                report_date = event_date
        else:
            report_date = event_date

        return f"{report_date.day:02d}/{report_date.month:02d}"

    def _row_matches_date(self, row_dict: dict[str, Any], date_key: str) -> bool:
        """
        date_key format: DD/MM, e.g. '01/04'.
        Match incident/event rows from CNCH, VU CHAY, CHI VIEN to the report date.
        Uses _compute_report_date_key with event date + event time for cutoff logic.
        """
        matched_any_date_col = False

        event_date_value, event_time_value = self._get_event_date_and_time(row_dict)

        if event_date_value is not None:
            matched_any_date_col = True
            report_date_key = self._compute_report_date_key(
                event_date_value,
                event_time_value,
                date_key_hint=date_key,
            )

            print(
                f"[DEBUG] _row_matches_date: event_date={event_date_value} "
                f"event_time={event_time_value} report_date_key={report_date_key} "
                f"only_date={date_key}"
            )

            if report_date_key == date_key:
                return True

        if not matched_any_date_col:
            print(
                f"[WARN] _row_matches_date: no date column found "
                f"date_key={date_key} row_keys={list(row_dict.keys())[:20]}"
            )

        return False

    def _debug_available_dates_for_worksheet(
        self,
        worksheet: str,
        rows: list[list],
        header: list[str],
        data_start: int,
    ) -> None:
        """Print all available dates in a detail worksheet for debugging."""
        available = []

        for idx, row in enumerate(rows[data_start:], start=data_start):
            if not row:
                continue

            row_dict = _row_to_dict(header, row)

            for key, value in row_dict.items():
                norm_key = _normalize_key(str(key))
                if not self._is_date_column_key(norm_key):
                    continue

                available.append(
                    {
                        "row_idx": idx,
                        "key": key,
                        "raw": str(value),
                        "normalized": self._normalize_date_to_ddmm(value),
                    }
                )
                break  # only first date column per row

        print(f"[DATEDBG] worksheet={worksheet} available_dates={available}")

    def _is_date_column_key(self, norm_key: str) -> bool:
        norm_key = _normalize_key(str(norm_key))

        return norm_key in {
            "ngay",
            "ngay xay ra",
            "ngay xay ra su co",
            "ngay xay ra vu chay",
            "vu chay ngay",
        }

    def _is_main_time_column_key(self, norm_key: str) -> bool:
        """Check if the normalized key is a main time column for report period calculation.

        Used for 07:30 cutoff to determine whether the event happened before or after
        the shift boundary. Must cover time columns from all detail schemas:
        - CNCH: "Thời gian đến" → "thoi gian den"
        - CHI VIỆN: "THỜI GIAN ĐI" → "thoi gian di"
        - VỤ CHÁY: "THỜI GIAN" → "thoi gian"
        """
        norm_key = _normalize_key(str(norm_key))

        return norm_key in {
            "thoi gian",
            "thoi gian den",
            "thoi gian di",
        }

    def _get_event_date_and_time(self, row_dict: dict[str, Any]) -> tuple[Any, Any]:
        """Extract event date and main time from a row dict.

        Returns (event_date_value, event_time_value) where:
        - event_date_value: raw value from the first date column found
        - event_time_value: raw value from the first main time column found
        """
        event_date_value = None
        event_time_value = None

        for key, value in row_dict.items():
            norm_key = _normalize_key(str(key))

            if event_date_value is None and self._is_date_column_key(norm_key):
                event_date_value = value

            if event_time_value is None and self._is_main_time_column_key(norm_key):
                event_time_value = value

            if event_date_value is not None and event_time_value is not None:
                break

        return event_date_value, event_time_value

    def _build_report_for_date(
        self,
        worksheet: str,
        schema_path: str,
        cfg: dict,
        row_indices: list[int],
        header_row_idx: int = 1,
        data_start: int = 2,
    ) -> "BlockExtractionOutput":
        """
        Build a single BlockExtractionOutput for a specific date group,
        processing only the rows at ``row_indices``.
        """
        # ── KV30 hardcoded path ────────────────────────────────────────────────
        if worksheet == "BC NGÀY" and is_kv30_config(cfg):
            return self._build_report_kv30_master(worksheet, schema_path, cfg, row_indices)

        # ── Generic path ─────────────────────────────────────────────────────────
        rows = self.sheet_data.get(worksheet, [])
        print(f"[DEBUG] _build_report_for_date: worksheet={worksheet} total_rows={len(rows)} row_indices={row_indices}")
        logger.debug(
            "_build_report_for_date worksheet=%s target_section=%s header_row=%s data_start=%s",
            worksheet,
            cfg.get("target_section"),
            cfg.get("header_row"),
            cfg.get("data_start_row"),
        )
        if len(rows) < 2:
            print(f"[DEBUG] not enough rows (<2), returning empty")
            return self._create_empty_report()

        # Use the header row that was detected in build_all_by_date().
        # For KV30 merged-header sheets: header_row_idx=0, row0=merged group names,
        # row1=FIRST DATA ROW (has NGÀY=1.0, THÁNG=3.0 as values, not headers).
        # For simple sheets: header_row_idx=1, data starts at row2.
        sub_header = rows[header_row_idx]
        # combined row provides column names where sub_header cell is None (merged cells).
        # For KV30 merged-header: row1 is data, NOT sub-header — skip combined logic.
        combined = None if header_row_idx == 0 else rows[1]

        # If config says header_row=1 but that row looks like data (numeric/date),
        # it is actually a data row, not a header. Correct it.
        if 0 <= header_row_idx < len(rows) and _row_looks_like_data(rows[header_row_idx]):
            logger.warning(
                "Detected header_row points to data row; correcting header_row_idx/data_start. "
                "worksheet=%s old_header_row=%s old_data_start=%s row_preview=%s",
                worksheet,
                header_row_idx,
                data_start,
                rows[header_row_idx][:10],
            )
            header_row_idx = 0
            data_start = 1
            sub_header = rows[header_row_idx]
            combined = rows[1] if header_row_idx == 1 else None

        print("[HDRDBG] worksheet=", worksheet)
        print("[HDRDBG] header_row_idx=", header_row_idx, "data_start=", data_start)
        print("[HDRDBG] rows_len=", len(rows))
        print("[HDRDBG] rows[0][:20]=", rows[0][:20] if len(rows) > 0 else None)
        print("[HDRDBG] rows[1][:20]=", rows[1][:20] if len(rows) > 1 else None)
        print("[HDRDBG] rows[2][:20]=", rows[2][:20] if len(rows) > 2 else None)
        print("[HDRDBG] rows[3][:20]=", rows[3][:20] if len(rows) > 3 else None)
        print("[HDRDBG] sub_header[:20]=", sub_header[:20] if sub_header else None)
        print("[HDRDBG] combined[:20]=", combined[:20] if combined else None)

        try:
            ingestion_schema = load_schema(schema_path)
            print(f"[DEBUG] schema_loaded fields_count={len(ingestion_schema.fields)}")
        except Exception as e:
            print(f"[DEBUG] schema_load_failed: {e}")
            raise ProcessingError(
                message=f"SCHEMA_NOT_FOUND: Cannot load schema at '{schema_path}'. "
                        f"Ensure schema file exists at that path or in app/domain/templates/. "
                        f"Original error: {e}"
            ) from e

        try:
            validation_model = build_validation_model(ingestion_schema)
        except Exception:
            validation_model = None

        # If the sub_header has no meaningful text (no real column names), the sheet
        # has no header row — use schema field names instead.
        has_meaningful_headers = False
        if sub_header:
            for cell in sub_header:
                if cell and str(cell).strip():
                    has_meaningful_headers = True
                    break
        if not has_meaningful_headers:
            field_names = [f.name for f in ingestion_schema.fields]
            sub_header = field_names
            combined = None  # no merged row to fall back on
            data_start = header_row_idx + 1  # data starts after header row
            print(f"[DEBUG] _build_report_for_date: no header row, using schema field names, data_start={data_start}")

        report = self._create_empty_report()
        valid_rows_count = 0
        skip_reasons: dict[str, int] = {}

        for row_idx in row_indices:
            if row_idx < 1 or row_idx >= len(rows):
                print(f"[DEBUG] row_idx={row_idx} OUT_OF_RANGE, skipping")
                continue
            row = rows[row_idx]

            row_dict: dict[str, Any] = {}
            for col_idx in range(len(sub_header)):
                # KV30 merged column: sub_header cell is None, use rows[0] for header name
                # Only apply when sub_header[col_idx] is None (not for normal detail sheets)
                if col_idx < len(sub_header) and sub_header[col_idx] is None:
                    if col_idx < len(rows[0]) and col_idx < len(row):
                        header_name = str(rows[0][col_idx]).strip()
                        row_dict[normalize_header_key(header_name)] = row[col_idx]
                else:
                    # Normal column — use sub_header name and row data
                    if col_idx < len(row):
                        header_name = str(sub_header[col_idx]).strip()
                        row_dict[normalize_header_key(header_name)] = row[col_idx]
                        if combined is not None and col_idx < len(combined):
                            combined_name = str(combined[col_idx]).strip()
                            if combined_name:
                                merged_name = f"{combined_name} {header_name}".strip()
                                row_dict[normalize_header_key(merged_name)] = row[col_idx]

            if not row_dict or all(_is_blank(value) for value in row_dict.values()):
                skip_reasons["blank_row"] = skip_reasons.get("blank_row", 0) + 1
                logger.debug(
                    "Skipping row due to blank row_dict worksheet=%s row_idx=%s reason=%s",
                    worksheet,
                    row_idx,
                    "blank_row",
                )
                continue

            print(f"[DEBUG] row_idx={row_idx} row_dict_keys={list(row_dict.keys())[:10]}")
            logger.debug(
                "row_dict worksheet=%s keys=%s",
                worksheet,
                list(row_dict.keys())[:20],
            )
            doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)
            print(f"[DEBUG] row_idx={row_idx} doc_data={doc_data} matched={m}/{t} missing={miss}")

            none_fields = [k for k, v in doc_data.items() if v is None]
            logger.debug(
                "[DEBUG] row_idx=%s none_fields=%s",
                row_idx,
                none_fields,
            )

            if m == 0:
                skip_reasons["mapping_zero_match"] = skip_reasons.get("mapping_zero_match", 0) + 1
                logger.error(
                    "MAPPING_ZERO_MATCH worksheet=%s row_idx=%s schema_path=%s row_dict_keys=%s matched=%s total=%s",
                    worksheet,
                    row_idx,
                    schema_path,
                    list(row_dict.keys())[:20],
                    m,
                    t,
                )
                continue

            if validation_model is not None:
                result = validate_row(
                    model=validation_model,
                    normalized_data=doc_data,
                    matched_fields=m,
                    total_fields=t,
                    missing_required=miss,
                )
                print(f"[DEBUG] row_idx={row_idx} validation is_valid={result.is_valid if result else None}")
            else:
                result = None

            self._row_entries.append(
                {"worksheet": worksheet, "row_index": row_idx + 1, "validation": result}
            )

            if result is not None and not result.is_valid:
                is_master = cfg.get("role") == "master" or worksheet in {"BC NGÀY", "BC NGAY"}
                match_rate = float(m) / float(t or 1)
                logger.warning(
                    "worksheet.row.validation_failed worksheet=%s row_idx=%s matched=%s total=%s errors=%s",
                    worksheet,
                    row_idx,
                    m,
                    t,
                    result.errors if result else None,
                )
                if m == 0:
                    skip_reasons["mapping_zero_match"] = skip_reasons.get("mapping_zero_match", 0) + 1
                    continue
                if (not is_master) and match_rate < 0.5:
                    skip_reasons["validation_failed"] = skip_reasons.get("validation_failed", 0) + 1
                    continue
                if is_master and match_rate >= 0.5:
                    skip_reasons["validation_warning"] = skip_reasons.get("validation_warning", 0) + 1
                else:
                    skip_reasons["validation_failed"] = skip_reasons.get("validation_failed", 0) + 1
                    continue

            pipeline_input = self._make_pipeline_input(row_dict, cfg)
            target_section = cfg.get("target_section")
            print(f"[PIPE_IN] target_section={target_section} pipeline_input_keys={list(pipeline_input.keys())}")
            if target_section == "danh_sach_cnch":
                print(f"[PIPE_IN] danh_sach_cnch check: {list(pipeline_input.keys())} = {pipeline_input}")
            logger.debug(
                "pipeline_input worksheet=%s keys=%s",
                worksheet,
                list(pipeline_input.keys())[:10],
            )
            print(f"[DEBUG] row_idx={row_idx} calling pipeline.run with schema_path={schema_path}")
            pipeline_result = self._pipeline.run(pipeline_input, schema_path=schema_path)
            print(f"[DEBUG] row_idx={row_idx} pipeline_status={pipeline_result.status} errors={pipeline_result.errors}")
            if pipeline_result.status != "ok" or pipeline_result.output is None:
                skip_reasons["pipeline_failed"] = skip_reasons.get("pipeline_failed", 0) + 1
                print(f"[DEBUG] row_idx={row_idx} SKIPPED: pipeline failed or output None")
                continue

            partial = pipeline_result.output
            if self._is_partial_output_empty(partial):
                skip_reasons["pipeline_empty"] = skip_reasons.get("pipeline_empty", 0) + 1
                logger.error(
                    "Pipeline returned ok but empty output; skipping row. worksheet=%s row_idx=%s",
                    worksheet,
                    row_idx,
                )
                continue

            target_section = cfg.get("target_section")
            if target_section and not self._partial_has_target_data(partial, target_section):
                skip_reasons["target_section_empty"] = skip_reasons.get("target_section_empty", 0) + 1
                logger.warning(
                    "Pipeline returned ok but target section empty; skipping row. worksheet=%s row_idx=%s target_section=%s",
                    worksheet,
                    row_idx,
                    target_section,
                )
                continue

            valid_rows_count += 1
            partial = pipeline_result.output
            print(f"[DEBUG] row_idx={row_idx} partial output: header.ngay={partial.header.ngay_bao_cao}, btk_count={len(partial.bang_thong_ke)}, cnch_count={len(partial.danh_sach_cnch)}")
            # Always merge all sections from every worksheet's output
            for attr in _SECTION_ATTRS:
                self._merge_section(report, partial, attr)

        print(f"[DEBUG] _build_report_for_date END: worksheet={worksheet} valid_rows_count={valid_rows_count} skip_reasons={skip_reasons}")
        return report

    # ──────────────────────────────────────────────────────────────────────────
    # KV30 hardcoded build methods (no YAML, no pipeline)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_report_kv30_master(
        self,
        worksheet: str,
        schema_path: str,
        cfg: dict,
        row_indices: list[int],
    ) -> BlockExtractionOutput:
        """Build BC NGÀY master report using fixed KV30 column mapping."""
        rows = self.sheet_data.get(worksheet, [])
        report = self._create_empty_report()
        valid_rows_count = 0

        for row_idx in row_indices:
            if row_idx < 0 or row_idx >= len(rows):
                continue
            row = rows[row_idx]
            partial = map_kv30_master_row(row)
            if partial is None:
                continue
            valid_rows_count += 1
            # Merge all sections from partial
            for attr in _SECTION_ATTRS:
                self._merge_section(report, partial, attr)

        return report

    def _process_worksheet_kv30_detail(
        self,
        report: BlockExtractionOutput,
        worksheet: str,
        cfg: dict,
        only_date: str | None = None,
    ) -> None:
        """Build detail items using fixed KV30 column mapping (no YAML/pipeline)."""
        rows = self.sheet_data.get(worksheet, [])
        data_start = get_kv30_data_start_row(worksheet, cfg)
        rows_valid = 0
        sclq_ctx: dict = {}
        skip_reasons = {
            "mapping_empty": 0,
            "date_mismatch": 0,
            "unknown_target_section": 0,
        }

        logger.info(
            "[KV30_DETAIL] Processing worksheet=%s only_date=%s total_rows=%d data_start=%d",
            worksheet, only_date, len(rows), data_start,
        )

        # Preview first 5 data rows
        for preview_idx in range(data_start, min(data_start + 5, len(rows))):
            if preview_idx < len(rows):
                logger.info("[KV30_DETAIL] worksheet=%s row[%d]=%s", worksheet, preview_idx, rows[preview_idx][:10])

        for row_idx, row in enumerate(rows[data_start:], start=data_start):
            mapped = map_kv30_detail_row(worksheet, row)
            if mapped is None:
                skip_reasons["mapping_empty"] += 1
                if row_idx < data_start + 3:
                    logger.info("[KV30_DETAIL] row_idx=%d mapped=None row_preview=%s", row_idx, row[:5])
                continue
            target_section, item = mapped

            if target_section == "danh_sach_sclq":
                # SCLQ needs continuation context
                item, sclq_ctx = map_kv30_sclq_row(row, sclq_ctx)
                if item is None:
                    skip_reasons["mapping_empty"] += 1
                    continue

            report_date_key = get_kv30_item_report_date_key(worksheet, item)
            if row_idx < data_start + 3:
                logger.info(
                    "[KV30_DETAIL] row_idx=%d target_section=%s report_date_key=%s only_date=%s item_preview=%s",
                    row_idx, target_section, report_date_key, only_date, str(item)[:100],
                )

            if only_date and report_date_key != only_date:
                skip_reasons["date_mismatch"] += 1
                continue

            target_list = getattr(report, target_section, None)
            if target_list is None:
                skip_reasons["unknown_target_section"] += 1
                logger.warning("[KV30_DETAIL] Unknown target_section=%s for worksheet=%s", target_section, worksheet)
                continue

            rows_valid += 1
            target_list.append(item)

        logger.info(
            "[KV30_DETAIL] Finished worksheet=%s only_date=%s rows_valid=%d skip_reasons=%s",
            worksheet, only_date, rows_valid, skip_reasons,
        )

    def _merge_kv30_detail_item(
        self,
        report: BlockExtractionOutput,
        target_section: str,
        item: Any,
    ) -> None:
        """Append a detail item to the correct list on the report."""
        if target_section == "danh_sach_cnch":
            report.danh_sach_cnch.append(item)
        elif target_section == "danh_sach_chi_vien":
            report.danh_sach_chi_vien.append(item)
        elif target_section == "danh_sach_chay":
            report.danh_sach_chay.append(item)
        elif target_section == "danh_sach_sclq":
            report.danh_sach_sclq.append(item)

    def _process_worksheet_with_schema(
        self,
        report: BlockExtractionOutput,
        worksheet: str,
        schema_path: str,
        cfg: dict,
        only_date: str | None = None,
    ) -> None:
        from app.engines.extraction import sheet_ingestion_service

        rows = self.sheet_data.get(worksheet, [])
        print(f"[DEBUG] worksheet={worksheet} rows_fetched={len(rows)}")
        if not rows:
            return

        try:
            ingestion_schema = load_schema(schema_path)
            print(f"[DEBUG] schema_loaded fields_count={len(ingestion_schema.fields)}")
        except Exception as e:
            print(f"[DEBUG] schema_load_failed: {e}")
            raise ProcessingError(
                message=f"SCHEMA_NOT_FOUND: Cannot load schema at '{schema_path}'. "
                        f"Ensure schema file exists at that path or in app/domain/templates/. "
                        f"Original error: {e}"
            ) from e

        try:
            validation_model = build_validation_model(ingestion_schema)
        except Exception:
            validation_model = None

        # Determine header row and data start (respect explicit config when provided)
        if len(rows) < 2:
            print(f"[DEBUG] not enough rows (<2)")
            return

        header_row_cfg = cfg.get("header_row")
        if header_row_cfg == -1:
            field_names = [f.name for f in ingestion_schema.fields]
            sub_header = field_names
            combined = None
            data_start = int(cfg.get("data_start_row", 1))
            header_row_idx = header_row_cfg
            print(f"[DEBUG] header_row=-1 using schema field names as headers: {field_names[:5]}...")
        else:
            has_header_cfg = "header_row" in cfg
            has_data_cfg = "data_start_row" in cfg
            if has_header_cfg or has_data_cfg:
                if not has_header_cfg or not has_data_cfg:
                    raise ProcessingError(
                        message=f"Missing header_row/data_start_row config for worksheet '{worksheet}'."
                    )
                header_row_idx = cfg.get("header_row")
                data_start = cfg.get("data_start_row")
                if not (0 <= header_row_idx < len(rows) and 0 <= data_start < len(rows)):
                    raise ProcessingError(
                        message=f"Invalid header_row/data_start_row config for worksheet '{worksheet}'. "
                                f"header_row={header_row_idx}, data_start_row={data_start}, "
                                f"available_rows={len(rows)}."
                    )
            else:
                data_start = 2  # default: row0=merged, row1=sub-header, data starts at row2
                header_row_idx = 1  # sub-header row index

                # Heuristic: if rows[1] looks like data (mostly numeric/date), then rows[0] is header
                if len(rows) >= 2:
                    row1 = rows[1]
                    numeric_count = 0
                    total_cells = 0
                    for cell in row1:
                        if cell is None:
                            continue
                        s = str(cell).strip()
                        if not s:
                            continue
                        total_cells += 1
                        if s.isdigit():
                            numeric_count += 1
                        elif s.count('/') >= 2:
                            parts = s.split('/')
                            if parts[0].isdigit() and parts[1].isdigit():
                                numeric_count += 1
                    if total_cells > 0 and numeric_count / total_cells > 0.5:
                        data_start = 1
                        header_row_idx = 0

            # Check if the detected header row is actually meaningful.
            # CNCH sheet has NO header row — Google Sheets returns raw data from row 1.
            # If the candidate header row has no recognizable column names, use schema field names.
            sub_header = rows[header_row_idx]
            has_meaningful_headers = False
            if sub_header:
                for cell in sub_header:
                    if cell and str(cell).strip():
                        has_meaningful_headers = True
                        break
            if not has_meaningful_headers:
                # Sheet has no header row — build virtual headers from schema field names
                field_names = [f.name for f in ingestion_schema.fields]
                sub_header = field_names
                data_start = 1  # data starts at row 1 (0-indexed: rows[1])
                print(f"[DEBUG] No header row found — using schema field names as headers: {field_names[:5]}...")

            # Detail sheets must not combine row 0 title into headers.
            combined = None if cfg.get("role") == "detail" else (rows[0] if header_row_idx == 1 else None)

        print(f"[DEBUG] header_row_idx={header_row_idx} data_start={data_start}")
        logger.debug(
            "worksheet=%s target_section=%s header_row=%s data_start=%s",
            worksheet,
            cfg.get("target_section"),
            header_row_idx,
            data_start,
        )
        print(f"[DEBUG] sub_header={sub_header[:5]}...")  # first 5 columns

        # Debug available dates for detail worksheets
        detail_sections = {"danh_sach_cnch", "danh_sach_chi_vien", "danh_sach_chay", "danh_sach_sclq"}
        if cfg.get("target_section") in detail_sections:
            self._debug_available_dates_for_worksheet(
                worksheet=worksheet,
                rows=rows,
                header=sub_header,
                data_start=data_start,
            )

        rows_processed = 0
        rows_valid = 0
        skip_reasons: dict[str, int] = {}

        for row_idx, row in enumerate(rows[data_start:], start=data_start):
            rows_processed += 1
            # Build full row dict ONCE per row
            row_dict: dict[str, Any] = {}
            for col_idx in range(len(sub_header)):
                # KV30 merged column: sub_header cell is None, use combined row for header name
                # Only apply when combined is explicitly set (not for detail sheets with None)
                if combined is not None and sub_header[col_idx] is None:
                    if col_idx < len(combined):
                        header_name = str(combined[col_idx]).strip()
                        row_dict[normalize_header_key(header_name)] = row[col_idx]
                else:
                    if col_idx < len(row):
                        header_name = str(sub_header[col_idx]).strip()
                        row_dict[normalize_header_key(header_name)] = row[col_idx]
                        if combined is not None and col_idx < len(combined):
                            combined_name = str(combined[col_idx]).strip()
                            if combined_name:
                                merged_name = f"{combined_name} {header_name}".strip()
                                row_dict[normalize_header_key(merged_name)] = row[col_idx]

            if not row_dict or all(_is_blank(value) for value in row_dict.values()):
                skip_reasons["blank_row"] = skip_reasons.get("blank_row", 0) + 1
                logger.debug(
                    "Skipping row due to blank row_dict worksheet=%s row_idx=%s reason=%s",
                    worksheet,
                    row_idx,
                    "blank_row",
                )
                continue

            if only_date and not self._row_matches_date(row_dict, only_date):
                # Collect only primary date columns for debug (not thoi_gian*)
                date_keys = {
                    k: str(v)
                    for k, v in row_dict.items()
                    if self._is_date_column_key(_normalize_key(str(k)))
                }

                logger.debug(
                    "Skipping row due to date mismatch worksheet=%s row_idx=%s only_date=%s date_keys=%s row_dict_keys=%s",
                    worksheet,
                    row_idx,
                    only_date,
                    date_keys,
                    list(row_dict.keys())[:20],
                )
                skip_reasons["date_mismatch"] = skip_reasons.get("date_mismatch", 0) + 1
                print(
                    f"[DEBUG] worksheet={worksheet} row_idx={row_idx} "
                    f"SKIPPED: date mismatch only_date={only_date} date_keys={date_keys}"
                )
                continue

            print(f"[DEBUG] worksheet={worksheet} row_idx={row_idx} row_dict_keys={list(row_dict.keys())[:10]}")
            logger.debug(
                "[DEBUG] worksheet=%s row_idx=%s row_dict_keys=%s",
                worksheet,
                row_idx,
                list(row_dict.keys())[:20],
            )
            doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)
            none_fields = [k for k, v in doc_data.items() if v is None]
            print(f"[DEBUG] worksheet={worksheet} row_idx={row_idx} doc_data={doc_data} matched={m}/{t} none_fields={none_fields}")
            logger.debug(
                "[DEBUG] worksheet=%s row_idx=%s doc_data=%s matched=%s/%s none_fields=%s",
                worksheet,
                row_idx,
                doc_data,
                m,
                t,
                none_fields,
            )

            if validation_model is not None:
                result = validate_row(
                    model=validation_model,
                    normalized_data=doc_data,
                    matched_fields=m,
                    total_fields=t,
                    missing_required=miss,
                )
                print(f"[DEBUG] worksheet={worksheet} row_idx={row_idx} validation is_valid={result.is_valid if result else None} errors={result.errors if result else None}")
                logger.debug(
                    "[DEBUG] worksheet=%s row_idx=%s validation is_valid=%s errors=%s",
                    worksheet,
                    row_idx,
                    result.is_valid if result else None,
                    result.errors if result else None,
                )
            else:
                result = None

            self._row_entries.append(
                {"worksheet": worksheet, "row_index": row_idx + 1, "validation": result}
            )

            if result is not None and not result.is_valid:
                is_master = cfg.get("role") == "master" or worksheet in {"BC NGÀY", "BC NGAY"}
                match_rate = float(m) / float(t or 1)
                logger.warning(
                    "worksheet.row.validation_failed worksheet=%s row_idx=%s matched=%s total=%s errors=%s",
                    worksheet,
                    row_idx,
                    m,
                    t,
                    result.errors if result else None,
                )
                if m == 0:
                    skip_reasons["mapping_zero_match"] = skip_reasons.get("mapping_zero_match", 0) + 1
                    continue
                if (not is_master) and match_rate < 0.5:
                    skip_reasons["validation_failed"] = skip_reasons.get("validation_failed", 0) + 1
                    continue
                if is_master and match_rate >= 0.5:
                    skip_reasons["validation_warning"] = skip_reasons.get("validation_warning", 0) + 1
                else:
                    skip_reasons["validation_failed"] = skip_reasons.get("validation_failed", 0) + 1
                    continue

            pipeline_input = self._make_pipeline_input(row_dict, cfg)
            target_section = cfg.get("target_section")
            print(f"[PIPE_IN] target_section={target_section} pipeline_input_keys={list(pipeline_input.keys())}")
            if target_section == "danh_sach_cnch":
                print(f"[PIPE_IN] danh_sach_cnch check: {list(pipeline_input.keys())} = {pipeline_input}")
            logger.debug(
                "pipeline_input worksheet=%s keys=%s",
                worksheet,
                list(pipeline_input.keys())[:10],
            )
            print(f"[DEBUG] worksheet={worksheet} row_idx={row_idx} calling pipeline.run with schema_path={schema_path}")
            pipeline_result = self._pipeline.run(pipeline_input, schema_path=schema_path)
            print(f"[DEBUG] worksheet={worksheet} row_idx={row_idx} pipeline_status={pipeline_result.status} errors={pipeline_result.errors}")
            if pipeline_result.status != "ok" or pipeline_result.output is None:
                skip_reasons["pipeline_failed"] = skip_reasons.get("pipeline_failed", 0) + 1
                print(f"[DEBUG] worksheet={worksheet} row_idx={row_idx} SKIPPED: pipeline failed or output None")
                continue

            # Guard: không tăng rows_valid khi output rỗng
            partial = pipeline_result.output
            if self._is_partial_output_empty(partial):
                skip_reasons["pipeline_empty"] = skip_reasons.get("pipeline_empty", 0) + 1
                print(f"[WARN] worksheet={worksheet} row_idx={row_idx} SKIPPED: pipeline ok but output empty")
                continue
            target_section = cfg.get("target_section")
            if target_section and not self._partial_has_target_data(partial, target_section):
                skip_reasons["target_section_empty"] = skip_reasons.get("target_section_empty", 0) + 1
                print(f"[WARN] worksheet={worksheet} row_idx={row_idx} SKIPPED: pipeline ok but target_section={target_section} empty")
                continue

            rows_valid += 1
            partial = pipeline_result.output
            print(f"[DEBUG] worksheet={worksheet} row_idx={row_idx} partial output: header={partial.header}, btk_count={len(partial.bang_thong_ke)}, cnch_count={len(partial.danh_sach_cnch)}")
            # Always merge all sections from every worksheet's output
            for attr in _SECTION_ATTRS:
                self._merge_section(report, partial, attr)

        print(f"[DEBUG] worksheet={worksheet} only_date={only_date} rows_processed={rows_processed} rows_valid={rows_valid} skip_reasons={skip_reasons}")

    def _make_pipeline_input(self, row_dict: dict[str, Any], cfg: dict) -> dict[str, Any]:
        target_section = cfg.get("target_section")
        if target_section in LIST_TARGET_SECTIONS:
            return {target_section: [row_dict]}
        return row_dict

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

    def _is_partial_output_empty(self, partial: "BlockExtractionOutput") -> bool:
        """Return True if the pipeline output has no meaningful data."""
        if partial is None:
            return True

        # header without meaningful fields
        h = partial.header
        header_empty = not (h.so_bao_cao or h.ngay_bao_cao or h.thoi_gian_tu_den or h.don_vi_bao_cao)

        # bang_thong_ke empty
        btk_empty = len(partial.bang_thong_ke) == 0

        # all list sections empty
        lists_empty = (
            len(partial.danh_sach_cnch) == 0
            and len(partial.danh_sach_chay) == 0
            and len(partial.danh_sach_chi_vien) == 0
            and len(partial.danh_sach_sclq) == 0
            and len(partial.danh_sach_phuong_tien_hu_hong) == 0
            and len(partial.danh_sach_cong_van_tham_muu) == 0
            and len(partial.danh_sach_cong_tac_khac) == 0
        )

        # phan_I numeric/text fields empty
        nv = partial.phan_I_va_II_chi_tiet_nghiep_vu
        nghiep_vu_empty = (
            getattr(nv, "tong_so_vu_chay", 0) in (None, 0)
            and getattr(nv, "tong_so_vu_cnch", 0) in (None, 0)
            and getattr(nv, "tong_sclq", 0) in (None, 0)
            and getattr(nv, "quan_so_truc", 0) in (None, 0)
        )

        # tuyen_truyen_online all zero
        tto = partial.tuyen_truyen_online
        online_empty = (
            getattr(tto, "so_tin_bai", 0) in (None, 0)
            and getattr(tto, "so_hinh_anh", 0) in (None, 0)
            and getattr(tto, "cai_app_114", 0) in (None, 0)
        )

        return header_empty and btk_empty and lists_empty and nghiep_vu_empty and online_empty

    def _partial_has_target_data(self, partial: "BlockExtractionOutput", target_section: str) -> bool:
        """Return True if the partial output has data for the given target_section."""
        if not target_section:
            return True

        value = getattr(partial, target_section, None)
        if value is None:
            return False

        if isinstance(value, list):
            return len(value) > 0
        return bool(value)

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

LIST_TARGET_SECTIONS = {
    "danh_sach_cnch",
    "danh_sach_chay",
    "danh_sach_chi_vien",
    "danh_sach_sclq",
    "danh_sach_phuong_tien_hu_hong",
    "danh_sach_cong_van_tham_muu",
    "danh_sach_cong_tac_khac",
}


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

