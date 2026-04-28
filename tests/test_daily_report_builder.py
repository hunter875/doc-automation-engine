"""Tests for DailyReportBuilder core logic (mixing, report date extraction, validation summary)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.engines.extraction.daily_report_builder import DailyReportBuilder
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
