"""Tests for DailyReportBuilder core logic (mixing, report date extraction, validation summary)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.core.exceptions import ProcessingError
from app.engines.extraction.schemas import PipelineResult
from app.engines.extraction.schemas import (
    BlockHeader,
    BlockNghiepVu,
    CNCHItem,
    BlockExtractionOutput,
    ChiTieu,
    BlockBangThongKe,
    PhuongTienHuHongItem,
    CongVanItem,
    ChiVienItem,
    VuChayItem,
    SCLQItem,
    TuyenTruyenOnline,
)


class FakeTemplate:
    """Minimal template stub for DailyReportBuilder."""
    def __init__(self):
        self.schema_definition = {}
        self.aggregation_rules = {}
        self.name = "Test"
        self.version = 1


def _empty_report() -> BlockExtractionOutput:
    """Helper to create a fully valid empty report."""
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


@pytest.fixture
def simple_template():
    return FakeTemplate()


@pytest.fixture
def monkey_template():
    """Template fixture for monkeypatch patching of module-level helpers."""
    return FakeTemplate()


def test_create_empty_report_has_all_sections(simple_template):
    builder = DailyReportBuilder(
        template=simple_template,
        sheet_data={},
        worksheet_configs=[],
    )
    report = builder._create_empty_report()

    assert isinstance(report, BlockExtractionOutput)
    # Check that all expected sections exist and are empty/zero
    assert report.header == BlockHeader()
    assert report.phan_I_va_II_chi_tiet_nghiep_vu == BlockNghiepVu()
    assert report.bang_thong_ke == []
    assert report.danh_sach_cnch == []
    assert report.danh_sach_phuong_tien_hu_hong == []
    assert report.danh_sach_cong_van_tham_muu == []
    assert report.danh_sach_cong_tac_khac == []
    assert report.danh_sach_chi_vien == []
    assert report.danh_sach_chay == []
    assert report.danh_sach_sclq == []
    assert report.tuyen_truyen_online == TuyenTruyenOnline()


def test_merge_section_header_overwrites_empty(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    report = _empty_report()
    # partial header with non-empty ngay_bao_cao
    partial = BlockExtractionOutput(
        header=BlockHeader(ngay_bao_cao="26/04/2026"),
        phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
    )

    builder._merge_section(report, partial, "header")

    assert report.header.ngay_bao_cao == "26/04/2026"


def test_merge_section_header_does_not_overwrite_nonempty_with_empty(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    report = _empty_report()
    report.header.ngay_bao_cao = "existing"
    partial = BlockExtractionOutput(
        header=BlockHeader(ngay_bao_cao=""),
        phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
    )

    builder._merge_section(report, partial, "header")

    # Should keep existing non-empty value
    assert report.header.ngay_bao_cao == "existing"


def test_merge_section_list_extends(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    report = _empty_report()
    # Pre-populate cnch list with one item
    report.danh_sach_cnch = [CNCHItem(stt=1, noi_dung="A")]
    partial = BlockExtractionOutput(
        danh_sach_cnch=[CNCHItem(stt=2, noi_dung="B")],
        header=BlockHeader(),
        phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
    )

    builder._merge_section(report, partial, "danh_sach_cnch")

    assert len(report.danh_sach_cnch) == 2
    assert report.danh_sach_cnch[0].stt == 1
    assert report.danh_sach_cnch[1].stt == 2


def test_merge_section_phan_ichiep_vu_overwrite_nonempty(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    report = _empty_report()
    # Set a field in phan_I_va_II_chi_tiet_nghiep_vu
    report.phan_I_va_II_chi_tiet_nghiep_vu.tong_so_vu_chay = 10
    # Partial has zero for that field (non-empty? 0 is considered numeric, but our condition: value not in (None, "", 0) or current in (None, "", 0))
    # According to code: if value not in (None, "", 0) or (current in (None, "", 0)) -> set.
    # Here partial.tong_so_vu_chay = 0, which is in (None, "", 0). So condition fails and current stays.
    partial = BlockExtractionOutput(
        phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(tong_so_vu_chay=0),
        header=BlockHeader(),
    )
    builder._merge_section(report, partial, "phan_I_va_II_chi_tiet_nghiep_vu")
    assert report.phan_I_va_II_chi_tiet_nghiep_vu.tong_so_vu_chay == 10  # unchanged

    # Now partial with non-zero > should overwrite
    partial2 = BlockExtractionOutput(
        phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(tong_so_vu_chay=5),
        header=BlockHeader(),
    )
    builder._merge_section(report, partial2, "phan_I_va_II_chi_tiet_nghiep_vu")
    assert report.phan_I_va_II_chi_tiet_nghiep_vu.tong_so_vu_chay == 5


def test_extract_report_date_from_header(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    report = _empty_report()
    report.header.ngay_bao_cao = "26/04/2026"
    assert builder._extract_report_date(report) == "26/04/2026"


def test_extract_report_date_returns_none_if_missing(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    report = _empty_report()
    report.header.ngay_bao_cao = ""
    assert builder._extract_report_date(report) is None


def test_build_validation_summary_counts(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    # Simulate row entries with required keys
    builder._row_entries = [
        {"worksheet": "Sheet1", "row_index": 1, "validation": MagicMock(is_valid=True)},
        {"worksheet": "Sheet1", "row_index": 2, "validation": MagicMock(is_valid=True)},
        {"worksheet": "Sheet1", "row_index": 3, "validation": MagicMock(is_valid=False)},
    ]
    summary = builder._build_validation_summary()
    assert summary["total_rows"] == 3
    assert summary["valid_rows"] == 2
    assert summary["invalid_rows_count"] == 1
    assert "warnings" in summary


def test_merge_section_unknown_target_does_nothing(simple_template):
    builder = DailyReportBuilder(simple_template, {}, [])
    report = _empty_report()
    partial = BlockExtractionOutput(
        header=BlockHeader(),
        phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
    )
    # Should not raise
    builder._merge_section(report, partial, "unknown_section")


def test_build_requires_schema_path_in_config(simple_template):
    builder = DailyReportBuilder(
        template=simple_template,
        sheet_data={"WS1": [["ngay_bao_cao"], ["20/04/2026"]]},
        worksheet_configs=[{"worksheet": "WS1", "target_section": "header"}],
    )

    with pytest.raises(ProcessingError):
        builder.build()


def test_snapshot_build_returns_valid_report(monkeypatch: pytest.MonkeyPatch, simple_template):
    sheet_data = {"WS1": [["ngay_bao_cao"], ["20/04/2026"]]}
    worksheet_configs = [
        {"worksheet": "WS1", "schema_path": "/tmp/schema.yaml", "target_section": "header"}
    ]

    import app.engines.extraction.daily_report_builder as drb_mod

    # Mock load_schema to return a proper schema-like object with fields
    class _Schema:
        all_aliases = {"ngay_bao_cao"}
        fields = []  # Add empty fields to satisfy attribute checks

    monkeypatch.setattr(
        "app.engines.extraction.daily_report_builder.load_schema",
        lambda *_: type("S", (), {"fields": []})(),
    )
    monkeypatch.setattr(
        "app.engines.extraction.mapping.header_detector.detect_header_row",
        lambda *_args, **_kwargs: (0, ["ngay_bao_cao"]),
    )

    def _map_row_to_document_data(row_dict, schema):
        return {"ngay_bao_cao": row_dict.get("ngay_bao_cao")}, 1, 1, set()

    # Patch map_row_to_document_data in the module where it's used
    monkeypatch.setattr(drb_mod, "map_row_to_document_data", _map_row_to_document_data)
    monkeypatch.setattr(
        "app.engines.extraction.mapping.mapper.map_row_to_document_data",
        _map_row_to_document_data,
    )

    monkeypatch.setattr(
        "app.engines.extraction.daily_report_builder.build_validation_model",
        lambda *_: object(),
    )

    from app.engines.extraction.validation.row_validator import RowValidationResult

    monkeypatch.setattr(
        "app.engines.extraction.daily_report_builder.validate_row",
        lambda *_args, **_kwargs: RowValidationResult(
            is_valid=True,
            normalized_data={"ngay_bao_cao": "20/04/2026"},
            errors=[],
            confidence={},
        ),
    )

    class _DummyPipeline:
        def run(self, *_args, **_kwargs):
            report = _empty_report()
            report.header.ngay_bao_cao = "20/04/2026"
            return PipelineResult(
                status="ok",
                attempts=1,
                output=report,
                errors=[],
                chi_tiet_cnch="",
            )

    monkeypatch.setattr(
        "app.engines.extraction.daily_report_builder.SheetExtractionPipeline",
        _DummyPipeline,
    )

    builder = DailyReportBuilder(
        template=simple_template,
        sheet_data=sheet_data,
        worksheet_configs=worksheet_configs,
    )

    report = builder.build()

    assert isinstance(report, BlockExtractionOutput)
    assert report._report_date == "20/04/2026"


# ─── Tests for multi-date ingestion ────────────────────────────────────────

def test_make_date_key_valid(simple_template):
    """Valid day/month pairs produce a correct DD/MM string."""
    builder = DailyReportBuilder(simple_template, {}, [])

    assert builder._make_date_key("1", "4") == "01/04"
    assert builder._make_date_key("10", "12") == "10/12"
    assert builder._make_date_key(5, 2) == "05/02"
    assert builder._make_date_key("  7 ", "  3 ") == "07/03"


def test_make_date_key_invalid(simple_template):
    """Invalid day/month values return None."""
    builder = DailyReportBuilder(simple_template, {}, [])

    assert builder._make_date_key(None, "4") is None
    assert builder._make_date_key("1", None) is None
    assert builder._make_date_key("", "") is None
    assert builder._make_date_key("abc", "4") is None
    assert builder._make_date_key("1", "13") is None  # month out of range
    assert builder._make_date_key("0", "4") is None   # day 0


def test_find_date_columns_returns_indices(simple_template):
    """Returns correct column indices for NGÀY and THÁNG headers."""
    builder = DailyReportBuilder(simple_template, {}, [])
    header_row = ["STT", "NGÀY", "THÁNG", "NỘI DUNG"]

    # Patch _load_custom_mapping to return a known schema
    import app.engines.extraction.daily_report_builder as drb_mod
    original = drb_mod._load_custom_mapping
    drb_mod._load_custom_mapping = lambda path: {
        "sheet_mapping": {
            "header": {
                "ngay_bao_cao_day": {"aliases": ["NGÀY"]},
                "ngay_bao_cao_month": {"aliases": ["THÁNG"]},
            }
        }
    }
    try:
        day_col, month_col = builder._find_date_columns(header_row, "/fake/schema.yaml")
        assert day_col == 1
        assert month_col == 2
    finally:
        drb_mod._load_custom_mapping = original


def test_find_date_columns_not_found(simple_template):
    """Returns (-1, -1) when date columns are not in header."""
    builder = DailyReportBuilder(simple_template, {}, [])
    header_row = ["STT", "NỘI DUNG", "KẾT QUẢ"]

    import app.engines.extraction.daily_report_builder as drb_mod
    original = drb_mod._load_custom_mapping
    drb_mod._load_custom_mapping = lambda path: {
        "sheet_mapping": {
            "header": {
                "ngay_bao_cao_day": {"aliases": ["NGÀY"]},
                "ngay_bao_cao_month": {"aliases": ["THÁNG"]},
            }
        }
    }
    try:
        day_col, month_col = builder._find_date_columns(header_row, "/fake/schema.yaml")
        assert day_col == -1
        assert month_col == -1
    finally:
        drb_mod._load_custom_mapping = original


def test_build_all_by_date_returns_multiple_reports(monkeypatch: pytest.MonkeyPatch, simple_template):
    """build_all_by_date groups rows by date and returns one report per date."""
    # Sheet with 3 rows across 2 different dates
    sheet_data = {
        "BC NGÀY": [
            ["NGÀY", "THÁNG", "VỤ CHÁY THỐNG KÊ"],
            ["1", "4", "2"],   # 01/04
            ["2", "4", "1"],   # 02/04
            ["3", "4", "3"],   # 03/04
        ]
    }
    worksheet_configs = [
        {"worksheet": "BC NGÀY", "schema_path": "/tmp/bc_ngay.yaml", "target_section": "header"}
    ]

    import app.engines.extraction.daily_report_builder as drb_mod

    # Mock the internal pipeline to return an empty report with a set ngay_bao_cao
    class _DummyPipeline:
        def run(self, *_args, **_kwargs):
            report = _empty_report()
            return PipelineResult(
                status="ok",
                attempts=1,
                output=report,
                errors=[],
                chi_tiet_cnch="",
            )

    monkeypatch.setattr(drb_mod, "SheetExtractionPipeline", _DummyPipeline)
    monkeypatch.setattr(drb_mod, "load_schema", lambda p: type("S", (), {"fields": []})())
    monkeypatch.setattr(drb_mod, "build_validation_model", lambda *_: None)
    monkeypatch.setattr(drb_mod, "validate_row", lambda *_: None)
    monkeypatch.setattr(
        drb_mod, "map_row_to_document_data",
        lambda row_dict, schema: ({}, 1, 1, set()),
    )

    builder = DailyReportBuilder(simple_template, sheet_data, worksheet_configs)
    date_reports = builder.build_all_by_date()

    assert len(date_reports) == 3
    assert "01/04" in date_reports
    assert "02/04" in date_reports
    assert "03/04" in date_reports

    # Each report has its _report_date set
    for date_key, report in date_reports.items():
        assert report._report_date == date_key


def test_build_all_by_date_falls_back_to_single_date(monkeypatch: pytest.MonkeyPatch, simple_template):
    """If no date columns are found, falls back to single-date build."""
    sheet_data = {
        "BC NGÀY": [
            ["NGÀY", "THÁNG"],
            ["", ""],  # empty date — will not group
        ]
    }
    worksheet_configs = [
        {"worksheet": "BC NGÀY", "schema_path": "/tmp/bc_ngay.yaml", "target_section": "header"}
    ]

    import app.engines.extraction.daily_report_builder as drb_mod

    class _DummyPipeline:
        def run(self, *_args, **_kwargs):
            report = _empty_report()
            return PipelineResult(status="ok", attempts=1, output=report, errors=[], chi_tiet_cnch="")

    monkeypatch.setattr(drb_mod, "SheetExtractionPipeline", _DummyPipeline)
    monkeypatch.setattr(drb_mod, "load_schema", lambda p: type("S", (), {"fields": []})())
    monkeypatch.setattr(drb_mod, "build_validation_model", lambda *_: None)
    monkeypatch.setattr(drb_mod, "validate_row", lambda *_: None)
    monkeypatch.setattr(
        drb_mod, "map_row_to_document_data",
        lambda row_dict, schema: ({}, 1, 1, set()),
    )

    builder = DailyReportBuilder(simple_template, sheet_data, worksheet_configs)
    date_reports = builder.build_all_by_date()

    # Falls back to legacy build, returns single "unknown" date
    assert len(date_reports) == 1
    assert "" in date_reports


def test_build_all_by_date_sorts_by_date(monkey_template, monkeypatch: pytest.MonkeyPatch):
    """Date reports are sorted ascending by date string."""
    sheet_data = {
        "BC NGÀY": [
            ["NGÀY", "THÁNG", "VỤ CHÁY THỐNG KÊ"],
            ["15", "4", "2"],
            ["1", "4", "1"],
            ["10", "4", "3"],
        ]
    }
    worksheet_configs = [
        {"worksheet": "BC NGÀY", "schema_path": "/tmp/bc_ngay.yaml", "target_section": "header"}
    ]

    import app.engines.extraction.daily_report_builder as drb_mod

    class _DummyPipeline:
        def run(self, *_args, **_kwargs):
            report = _empty_report()
            return PipelineResult(status="ok", attempts=1, output=report, errors=[], chi_tiet_cnch="")

    monkeypatch.setattr(drb_mod, "SheetExtractionPipeline", _DummyPipeline)
    monkeypatch.setattr(drb_mod, "load_schema", lambda p: type("S", (), {"fields": []})())
    monkeypatch.setattr(drb_mod, "build_validation_model", lambda *_: None)
    monkeypatch.setattr(drb_mod, "validate_row", lambda *_: None)
    monkeypatch.setattr(
        drb_mod, "map_row_to_document_data",
        lambda row_dict, schema: ({}, 1, 1, set()),
    )

    builder = DailyReportBuilder(monkey_template, sheet_data, worksheet_configs)
    date_reports = builder.build_all_by_date()

    dates = list(date_reports.keys())
    assert dates == sorted(dates)


def test_build_all_by_date_merges_non_date_worksheets(
    monkeypatch: pytest.MonkeyPatch, simple_template
):
    """Non-date worksheets (CNCH, VỤ CHÁY) are merged into every date report."""
    sheet_data = {
        "BC NGÀY": [
            ["NGÀY", "THÁNG", "VỤ CHÁY THỐNG KÊ"],
            ["1", "4", "2"],   # 01/04
            ["2", "4", "1"],   # 02/04
        ],
        "CNCH": [
            ["STT", "NGÀY XẢY RA"],
            ["1", "01/04"],
            ["2", "02/04"],
        ],
    }
    worksheet_configs = [
        {"worksheet": "BC NGÀY", "schema_path": "/tmp/bc_ngay.yaml", "target_section": "header"},
        {"worksheet": "CNCH", "schema_path": "/tmp/cnch.yaml", "target_section": "danh_sach_cnch"},
    ]

    import app.engines.extraction.daily_report_builder as drb_mod

    # Track which reports were merged with CNCH worksheet
    merge_log: list[str] = []

    class _DummyPipeline:
        def run(self, *_args, **_kwargs):
            report = _empty_report()
            return PipelineResult(status="ok", attempts=1, output=report, errors=[], chi_tiet_cnch="")

    monkeypatch.setattr(drb_mod, "SheetExtractionPipeline", _DummyPipeline)
    monkeypatch.setattr(drb_mod, "load_schema", lambda p: type("S", (), {"fields": []})())
    monkeypatch.setattr(drb_mod, "build_validation_model", lambda *_: None)
    monkeypatch.setattr(drb_mod, "validate_row", lambda *_: None)
    monkeypatch.setattr(
        drb_mod, "map_row_to_document_data",
        lambda row_dict, schema: ({}, 1, 1, set()),
    )

    builder = DailyReportBuilder(simple_template, sheet_data, worksheet_configs)
    date_reports = builder.build_all_by_date()

    # Both dates should be present
    assert "01/04" in date_reports
    assert "02/04" in date_reports
