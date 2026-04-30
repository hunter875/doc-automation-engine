"""
Test script: Multi-date sheet ingestion output validation.

Tests the full pipeline from sheet_data → build_all_by_date() → per-date reports.

Usage:
    docker exec rag-api python scripts/test_multi_date_ingestion.py

Or locally (if dependencies installed):
    python scripts/test_multi_date_ingestion.py
"""
import sys
import types
import json
from pathlib import Path

# Clear all schema/mapping caches to pick up latest YAML changes
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
from app.engines.extraction.daily_report_builder import _CUSTOM_MAPPING_CACHE as DRB_CACHE
_CUSTOM_MAPPING_CACHE.clear()
DRB_CACHE.clear()

# Clear the sheet_pipeline _load_sheet_mapping LRU cache too
from app.engines.extraction import sheet_pipeline
if hasattr(sheet_pipeline._load_sheet_mapping, 'cache_clear'):
    sheet_pipeline._load_sheet_mapping.cache_clear()

from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.schemas import BlockExtractionOutput

# ── Test Data: Simulate "THỐNG KÊ CÔNG TÁC NGÀY PC KV30 2026.xlsx" ──────────
# Each row = 1 day's report. BC NGÀY sheet has NGÀY + THÁNG columns.
# CNCH sheet has incidents with per-row dates.

TEMPLATE_CONFIGS = [
    {
        "worksheet": "BC NGÀY",
        "schema_path": "/app/app/domain/templates/bc_ngay_kv30_schema.yaml",
        "target_section": "header",
    },
    {
        "worksheet": "CNCH",
        "schema_path": "/app/app/domain/templates/cnch_kv30_schema.yaml",
        "target_section": "danh_sach_cnch",
    },
]

# BC NGÀY: 5 days of data (April 1-5)
BC_NGAY_SHEET = [
    # Header row
    ["NGÀY", "THÁNG", "Số báo cáo", "VỤ CHÁY THỐNG KÊ", "SCLQ PCCC&CNCH",
     "TIN BÀI, PHÓNG SỰ", "KIỂM TRA ĐỊNH KỲ NHÓM I", "KIỂM TRA ĐỊNH KỲ NHÓM II"],
    # Day 1: 01/04
    ["1",  "4",  "BC-01",  "2", "3", "5", "10", "2"],
    # Day 2: 02/04
    ["2",  "4",  "BC-02",  "1", "4", "3", "8",  "1"],
    # Day 3: 03/04
    ["3",  "4",  "BC-03",  "0", "2", "6", "12", "3"],
    # Day 4: 04/04
    ["4",  "4",  "BC-04",  "3", "1", "4", "9",  "2"],
    # Day 5: 05/04
    ["5",  "4",  "BC-05",  "1", "5", "7", "11", "4"],
]

# CNCH sheet: incidents on various days
CNCH_SHEET = [
    ["STT", "NGÀY XẢY RA", "THỜI GIAN", "ĐỊA ĐIỂM", "NỘI DUNG TIN BÁO"],
    ["1", "01/04", "08:30", "Quận 1", "Cháy cửa hàng"],
    ["2", "02/04", "14:00", "Quận 3", "Cháy chung cư"],
    ["3", "03/04", "09:15", "Quận 5", "Sự cố gas"],
]

SHEET_DATA = {
    "BC NGÀY": BC_NGAY_SHEET,
    "CNCH": CNCH_SHEET,
}

template = types.SimpleNamespace(google_sheet_configs=TEMPLATE_CONFIGS)


# ── Helper ────────────────────────────────────────────────────────────────────

def assert_valid_report(report: BlockExtractionOutput, date_key: str) -> dict:
    """Validate a report and return any issues found."""
    issues = []

    # Check header date
    if not report.header.ngay_bao_cao:
        issues.append(f"[{date_key}] MISSING ngay_bao_cao")
    elif report.header.ngay_bao_cao != f"{date_key}/2026":
        issues.append(f"[{date_key}] WRONG ngay_bao_cao: got {report.header.ngay_bao_cao!r}, expected {date_key}/2026")

    # Check nghiep_vu has numeric values
    nv = report.phan_I_va_II_chi_tiet_nghiep_vu
    if nv.tong_so_vu_chay is None:
        issues.append(f"[{date_key}] tong_so_vu_chay is None (extraction failure)")

    # Check that date-specific values are non-None
    # Day 1: tong_so_vu_chay should be 2, tong_so_vu_cnch should be 3, etc.
    if date_key == "01/04":
        if nv.tong_so_vu_chay != 2:
            issues.append(f"[01/04] tong_so_vu_chay={nv.tong_so_vu_chay}, expected 2")
        if nv.tong_so_vu_cnch != 3:
            issues.append(f"[01/04] tong_so_vu_cnch={nv.tong_so_vu_cnch}, expected 3")
        if nv.tong_tin_bai != 5:
            issues.append(f"[01/04] tong_tin_bai={nv.tong_tin_bai}, expected 5")

    if date_key == "03/04":
        # Day 3 has 0 fires — this is VALID data, not an extraction failure
        if nv.tong_so_vu_chay != 0:
            issues.append(f"[03/04] tong_so_vu_chay={nv.tong_so_vu_chay}, expected 0")
        if nv.tong_so_vu_cnch != 2:
            issues.append(f"[03/04] tong_so_vu_cnch={nv.tong_so_vu_cnch}, expected 2")

    # Check bang_thong_ke is non-empty
    if not report.bang_thong_ke:
        issues.append(f"[{date_key}] bang_thong_ke is EMPTY — extraction may have failed")

    # Check top-level structure
    sections = [
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
    for sec in sections:
        if not hasattr(report, sec):
            issues.append(f"[{date_key}] MISSING section: {sec}")

    # Check _report_date is set
    if not hasattr(report, "_report_date") or report._report_date is None:
        issues.append(f"[{date_key}] _report_date is not set")
    elif report._report_date != date_key:
        issues.append(f"[{date_key}] _report_date={report._report_date!r}, expected {date_key!r}")

    # Verify model is serializable
    try:
        payload = report.model_dump(mode="json")
        if not isinstance(payload, dict):
            issues.append(f"[{date_key}] model_dump() returned non-dict: {type(payload)}")
        # Should have all expected top-level keys
        expected_keys = {
            "header", "phan_I_va_II_chi_tiet_nghiep_vu", "bang_thong_ke",
            "danh_sach_cnch", "danh_sach_phuong_tien_hu_hong",
            "danh_sach_cong_van_tham_muu", "danh_sach_cong_tac_khac",
            "danh_sach_chi_vien", "danh_sach_chay", "danh_sach_sclq",
            "tuyen_truyen_online",
        }
        actual_keys = set(payload.keys())
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        if missing:
            issues.append(f"[{date_key}] Missing sections after serialization: {missing}")
        if extra:
            issues.append(f"[{date_key}] Extra sections after serialization: {extra}")
    except Exception as e:
        issues.append(f"[{date_key}] model_dump() FAILED: {e}")

    return issues


def assert_cnch_merged(report: BlockExtractionOutput) -> list:
    """CNCH incidents should be merged into every date report."""
    issues = []

    # At least 2 CNCH incidents should be in the merged report
    # (all CNCH rows get merged into every date report)
    if len(report.danh_sach_cnch) == 0:
        issues.append("CNCH incidents NOT merged into report (expected at least 3)")

    # Verify CNCH structure
    for item in report.danh_sach_cnch:
        if not hasattr(item, "stt"):
            issues.append(f"CNCH item missing stt: {item}")
        if not hasattr(item, "ngay_xay_ra") or not item.ngay_xay_ra:
            issues.append(f"CNCH item missing ngay_xay_ra: {item}")

    return issues


# ── Run Tests ────────────────────────────────────────────────────────────────

def test_multi_date():
    print("=" * 70)
    print("TEST: Multi-Date Sheet Ingestion")
    print("=" * 70)

    print(f"\nInput: BC NGÀY sheet with {len(BC_NGAY_SHEET)-1} data rows")
    print(f"        CNCH sheet with {len(CNCH_SHEET)-1} data rows")

    builder = DailyReportBuilder(
        template=template,
        sheet_data=SHEET_DATA,
        worksheet_configs=TEMPLATE_CONFIGS,
    )

    date_reports = builder.build_all_by_date()

    print(f"\nOutput: {len(date_reports)} date report(s) generated")
    for dk in sorted(date_reports.keys()):
        print(f"  - {dk}")

    # ── Test 1: Correct number of reports ────────────────────────────────────
    print("\n--- Test 1: Correct number of reports ---")
    if len(date_reports) == 5:
        print("  PASS: 5 reports generated (01/04 through 05/04)")
    else:
        print(f"  FAIL: Expected 5, got {len(date_reports)}")
        print(f"  Reports: {sorted(date_reports.keys())}")

    # ── Test 2: All dates present and sorted ─────────────────────────────────
    print("\n--- Test 2: All expected dates present ---")
    expected_dates = {"01/04", "02/04", "03/04", "04/04", "05/04"}
    actual_dates = set(date_reports.keys())
    if actual_dates == expected_dates:
        print("  PASS: All 5 dates present")
    else:
        missing = expected_dates - actual_dates
        extra = actual_dates - expected_dates
        if missing:
            print(f"  FAIL: Missing dates: {sorted(missing)}")
        if extra:
            print(f"  FAIL: Unexpected dates: {sorted(extra)}")

    # ── Test 3: Dates sorted ascending ───────────────────────────────────────
    print("\n--- Test 3: Dates sorted ascending ---")
    dates = list(date_reports.keys())
    if dates == sorted(dates):
        print(f"  PASS: {dates}")
    else:
        print(f"  FAIL: Not sorted — {dates}")

    # ── Test 4: Each report is valid and correctly populated ─────────────────
    print("\n--- Test 4: Per-report validation ---")
    all_issues = []
    for date_key, report in sorted(date_reports.items()):
        issues = assert_valid_report(report, date_key)
        cnch_issues = assert_cnch_merged(report)
        all_issues.extend(issues)
        all_issues.extend(cnch_issues)
        status = "PASS" if not issues and not cnch_issues else "FAIL"
        print(f"  [{status}] {date_key}: ngay_bao_cao={report.header.ngay_bao_cao!r}, "
              f"tong_vu_chay={report.phan_I_va_II_chi_tiet_nghiep_vu.tong_so_vu_chay}, "
              f"tong_cnch={report.phan_I_va_II_chi_tiet_nghiep_vu.tong_so_vu_cnch}, "
              f"cnch_items={len(report.danh_sach_cnch)}, "
              f"btk_rows={len(report.bang_thong_ke)}")

    # ── Test 5: Report serialization ───────────────────────────────────────────
    print("\n--- Test 5: JSON serialization ---")
    try:
        for dk, report in sorted(date_reports.items()):
            payload = report.model_dump(mode="json")
            json_str = json.dumps(payload, ensure_ascii=False, indent=2)
            # Verify structure
            if "header" in payload and "phan_I_va_II_chi_tiet_nghiep_vu" in payload:
                print(f"  [{dk}] PASS: Serializes to valid JSON ({len(json_str)} chars)")
            else:
                print(f"  [{dk}] FAIL: Missing top-level keys in serialized output")
    except Exception as e:
        print(f"  FAIL: Serialization error: {e}")

    # ── Test 6: Backward compatibility (single date) ─────────────────────────
    print("\n--- Test 6: Backward compatibility — single date sheet ---")
    single_day_config = [
        {
            "worksheet": "BC NGÀY",
            "schema_path": "/app/app/domain/templates/bc_ngay_kv30_schema.yaml",
            "target_section": "header",
        },
    ]
    single_day_data = {
        "BC NGÀY": [
            ["NGÀY", "THÁNG", "Số báo cáo"],
            ["15", "4", "BC-15"],
        ]
    }
    single_builder = DailyReportBuilder(
        template=types.SimpleNamespace(google_sheet_configs=single_day_config),
        sheet_data=single_day_data,
        worksheet_configs=single_day_config,
    )
    single_reports = single_builder.build_all_by_date()
    if len(single_reports) == 1:
        print(f"  PASS: Single date sheet → 1 report")
        report = list(single_reports.values())[0]
        print(f"        ngay_bao_cao = {report.header.ngay_bao_cao!r}")
    else:
        print(f"  FAIL: Expected 1 report, got {len(single_reports)}")

    # ── Test 7: Empty date detection ─────────────────────────────────────────
    print("\n--- Test 7: Empty/missing date columns fallback ---")
    empty_date_data = {
        "BC NGÀY": [
            ["NGÀY", "THÁNG"],
            ["", ""],
        ]
    }
    empty_builder = DailyReportBuilder(
        template=types.SimpleNamespace(google_sheet_configs=single_day_config),
        sheet_data=empty_date_data,
        worksheet_configs=single_day_config,
    )
    empty_reports = empty_builder.build_all_by_date()
    print(f"  Empty date sheet → {len(empty_reports)} report(s) (fallback to legacy build)")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if not all_issues:
        print("ALL TESTS PASSED")
        print("=" * 70)
        return 0
    else:
        print(f"ISSUES FOUND ({len(all_issues)}):")
        for issue in all_issues:
            print(f"  - {issue}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(test_multi_date())
