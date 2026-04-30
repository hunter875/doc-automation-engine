"""
verify_snapshot_custom_schema.py
=================================
End-to-end validation script for snapshot ingestion using worksheet-specific schemas.

Proves:
  1. DailyReportBuilder can load all 4 schema_path configs.
  2. SheetExtractionPipeline custom-schema mode is used (no global sheet_mapping.yaml).
  3. sheet_mapping.yaml is NOT loaded in custom schema mode.
  4. extracted_data contains all 11 required top-level sections.
  5. report_date is correctly extracted from header.ngay_bao_cao.
  6. validation_report is produced.
  7. BlockExtractionOutput schema validation passes.

Usage (from repo root):
    docker exec rag-api python scripts/verify_snapshot_custom_schema.py
    # or locally:
    python scripts/verify_snapshot_custom_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
CONTAINER_ROOT = REPO_ROOT / "app"

def _schema_path(name: str) -> str:
    """Return absolute path to a schema YAML file.

    Host (repo at /path/to/repo/):
      repo_root = .../doc-automation-engine-main (2)/doc-automation-engine-main
      container_root = repo_root / "app"  → points to repo's app/ dir
      schemas are at: repo_root / "app" / "domain" / "templates"

    Docker (repo mounted at /app/):
      repo_root = /app
      container_root = /app/app  → the /app/app dir inside container
      schemas are at: /app/app/domain/templates
    """
    base = CONTAINER_ROOT if CONTAINER_ROOT.is_dir() else REPO_ROOT
    return str(base / "domain" / "templates" / name)

# ── import AFTER path setup ────────────────────────────────────────────────────
from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.schemas import BlockExtractionOutput
import app.engines.extraction.sheet_pipeline as _sp

# ── GUARD: prove sheet_mapping.yaml is NOT loaded in custom schema mode ──────
_original_load = _sp._load_sheet_mapping
_sheet_mapping_called = False

def _guarded_load():
    global _sheet_mapping_called
    _sheet_mapping_called = True
    raise AssertionError(
        "FATAL: _load_sheet_mapping() was called — "
        "custom schema mode must NOT touch global sheet_mapping.yaml"
    )

_sp._load_sheet_mapping = _guarded_load

# ── worksheet configs (real schema paths) ─────────────────────────────────────
worksheet_configs = [
    {
        "worksheet": "BC NGÀY",
        "schema_path": _schema_path("bc_ngay_schema.yaml"),
        "target_section": "header",
    },
    {
        "worksheet": "CNCH",
        "schema_path": _schema_path("cnch_schema.yaml"),
        "target_section": "danh_sach_cnch",
    },
    {
        "worksheet": "VỤ CHÁY THỐNG KÊ",
        "schema_path": _schema_path("vu_chay_schema.yaml"),
        "target_section": "danh_sach_chay",
    },
    {
        "worksheet": "CHI VIỆN",
        "schema_path": _schema_path("chi_vien_schema.yaml"),
        "target_section": "danh_sach_chi_vien",
    },
]

# ── mock worksheet rows (list of lists, as returned by Google Sheets API) ────
sheet_data: dict[str, list[list]] = {
    "BC NGÀY": [
        # header row
        ["ngày", "tháng", "Số báo cáo", "thời gian từ đến", "đơn vị báo cáo"],
        # data rows
        [1, 4, "BC-01", "01/04/2026 - 20/04/2026", "Đội PCCC&CNCH Quận 1"],
    ],
    "CNCH": [
        ["STT", "Ngày xảy ra sự cố", "Thời gian đến", "Địa điểm", "Loại hình CNCH",
         "Thiệt hại về người", "Số người cứu được"],
        [1, "01/04/2026", "10:00", "Phường 1, Quận 1", "Cứu nạn giao thông", 0, 2],
        [2, "05/04/2026", "14:30", "Phường 3, Quận 3", "Cứu hộ va chạm", 0, 1],
    ],
    "VỤ CHÁY THỐNG KÊ": [
        ["STT", "NGÀY XẢY RA VỤ CHÁY", "THỜI GIAN", "VỤ CHÁY",
         "ĐỊA ĐIỂM", "NGUYÊN NHÂN", "THIỆT HẠI VỀ NGƯỜI",
         "THIỆT HẠI TÀI SẢN", "THỜI GIAN KHỐNG CHẾ",
         "THỜI GIAN DẬP TẮT", "SỐ LƯỢNG XE", "CHỈ HUY"],
        [1, "03/04/2026", "08:30", "Cháy quán cơm", "Quận 5",
         "Chập điện", "0", "5.000.000", "09:00", "09:20", 2, "Thiếu tá A"],
    ],
    "CHI VIỆN": [
        ["STT", "NGÀY XẢY RA", "ĐỊA ĐIỂM", "KHU VỰC QUẢN LÝ",
         "SỐ LƯỢNG XE", "THỜI GIAN ĐI", "THỜI GIAN VỀ",
         "CHỈ HUY CHỮA CHÁY", "Ghi chú"],
        [1, "03/04/2026", "Quận 5", "KV-5", 3, "08:00", "10:30",
         "Thiếu tá B", "Chi viện chữa cháy"],
    ],
}

# ── run ──────────────────────────────────────────────────────────────────────
template = SimpleNamespace(google_sheet_configs=worksheet_configs)

builder = DailyReportBuilder(
    template=template,
    sheet_data=sheet_data,
    worksheet_configs=worksheet_configs,
)

report = builder.build()
validation_summary = builder.get_validation_summary()

# ── assertion helpers ────────────────────────────────────────────────────────
errors: list[str] = []

def check(condition: bool, msg: str) -> None:
    if not condition:
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  PASS: {msg}")

# ── V1: DailyReportBuilder loaded all 4 schema paths ───────────────────────
print("\n[V1] Schema path loading")
for cfg in worksheet_configs:
    p = Path(cfg["schema_path"])
    check(p.is_file(), f"  schema file exists: {p.name}")
# check that _CUSTOM_MAPPING_CACHE was populated (proof of schema loading)
from app.engines.extraction.daily_report_builder import _CUSTOM_MAPPING_CACHE
for cfg in worksheet_configs:
    cached = cfg["schema_path"] in _CUSTOM_MAPPING_CACHE
    check(cached, f"  schema cached: {Path(cfg['schema_path']).name}")

# ── V2: sheet_mapping.yaml NOT loaded in custom schema mode ─────────────────
print("\n[V2] sheet_mapping.yaml isolation")
check(not _sheet_mapping_called,
      "_load_sheet_mapping() was NOT called — custom schema mode is isolated")

# ── V3: extract report_date ─────────────────────────────────────────────────
print("\n[V3] Report date extraction")
report_date = getattr(report, "_report_date", None) or builder._report_date
check(bool(report_date), f"  report_date extracted: {report_date}")
check(report_date == "01/04/2026",
      f"  report_date correct (01/04/2026): got {report_date!r}")

# ── V4: all required sections present ───────────────────────────────────────
print("\n[V4] Required top-level sections in extracted_data")
payload = report.model_dump(mode="json")
REQUIRED = {
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
}
missing = REQUIRED - set(payload.keys())
extra = set(payload.keys()) - REQUIRED
check(not missing, f"  no missing sections: {sorted(missing)}")
check(not extra, f"  no extra sections: {sorted(extra)}")

# ── V5: section contents ─────────────────────────────────────────────────────
print("\n[V5] Section contents")
check(payload["header"]["ngay_bao_cao"] == "01/04/2026",
      f"  header.ngay_bao_cao populated: {payload['header']['ngay_bao_cao']!r}")
check(len(payload["danh_sach_cnch"]) == 2,
      f"  danh_sach_cnch has 2 items: got {len(payload['danh_sach_cnch'])}")
check(len(payload["danh_sach_chay"]) == 1,
      f"  danh_sach_chay has 1 item: got {len(payload['danh_sach_chay'])}")
check(len(payload["danh_sach_chi_vien"]) == 1,
      f"  danh_sach_chi_vien has 1 item: got {len(payload['danh_sach_chi_vien'])}")
check(payload["danh_sach_chay"][0]["dia_diem"] == "Quận 5",
      f"  chay item dia_diem: {payload['danh_sach_chay'][0].get('dia_diem')!r}")
check(payload["danh_sach_chi_vien"][0]["khu_vuc_quan_ly"] == "KV-5",
      f"  chi_vien item khu_vuc_quan_ly: {payload['danh_sach_chi_vien'][0].get('khu_vuc_quan_ly')!r}")

# ── V6: BlockExtractionOutput schema validation ───────────────────────────────
print("\n[V6] BlockExtractionOutput Pydantic validation")
try:
    BlockExtractionOutput.model_validate(payload)
    print("  PASS: BlockExtractionOutput.model_validate() passed")
except Exception as ex:
    errors.append(f"BlockExtractionOutput validation failed: {ex}")
    print(f"  FAIL: BlockExtractionOutput validation failed: {ex}")

# ── V7: validation_report produced ───────────────────────────────────────────
print("\n[V7] validation_report (get_validation_summary)")
check(isinstance(validation_summary, dict), "  validation_summary is a dict")
check("total_rows" in validation_summary, "  has 'total_rows'")
check("valid_rows" in validation_summary, "  has 'valid_rows'")
check("report_date" in validation_summary, "  has 'report_date'")
check("worksheets_processed" in validation_summary, "  has 'worksheets_processed'")
print(f"  validation_summary keys: {sorted(validation_summary.keys())}")
print(f"  rows: total={validation_summary.get('total_rows')}, "
      f"valid={validation_summary.get('valid_rows')}, "
      f"report_date={validation_summary.get('report_date')}")

# ── summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"RESULT: FAILED — {len(errors)} assertion(s) failed")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("RESULT: ALL CHECKS PASSED")
    print("\nSummary:")
    print(f"  - 4 schema files loaded via DailyReportBuilder")
    print(f"  - sheet_mapping.yaml NOT loaded in custom-schema mode")
    print(f"  - report_date: {report_date}")
    print(f"  - 11/11 required sections present in extracted_data JSONB")
    print(f"  - BlockExtractionOutput schema validation: OK")
    print(f"  - validation_report produced: OK")
    sys.exit(0)
