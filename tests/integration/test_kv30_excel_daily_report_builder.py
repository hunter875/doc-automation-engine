"""Integration tests for KV30 daily report builder with Excel fixture data.

Tests the complete flow: raw worksheet rows → DailyReportBuilder.build_all_by_date()
with realistic KV30 Excel data. No Google Sheets API calls, no real DB needed.

Fixture data is constructed in-memory from known KV30 Excel structure:
- BC NGÀY: merged headers (row0) + sub-headers (row1) + data rows (row2+)
  Each data row: [NGÀY=day, THÁNG=month, VỤ CHÁY, SCLQ, CHI VIỆN, CNCH, ...]
- CNCH: sub-header row with Vietnamese column names + data rows
- VỤ CHÁY THỐNG KÊ: same structure
- CHI VIỆN: same structure
- SCLQ ĐẾN PCCC&CNCH: same structure

Expected key events and their report date:
  - VỤ CHÁY 24/03/2026 17:20 → report 25/03 (time >= 07:30)
  - CNCH 20/03/2026 16:33 → report 21/03 (time >= 07:30)
  - CNCH 09/04/2026 22:36 → report 10/04 (time >= 07:30)
  - CHI VIỆN 09/04/2026 20:29 → report 10/04 (time >= 07:30)
  - CHI VIỆN 31/03/2026 02:55 → report 31/03 (time < 07:30)
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline
from app.engines.extraction.schemas import PipelineResult
from app.engines.extraction.schemas import (
    BlockHeader,
    BlockNghiepVu,
    CNCHItem,
    ChiTieu,
    ChiVienItem,
    TuyenTruyenOnline,
    VuChayItem,
    SCLQItem,
)


# ─────────────────────────────────────────────────────────────────
# KV30 Excel fixture data
# ─────────────────────────────────────────────────────────────────

def _make_bc_ngay_rows() -> list[list[Any]]:
    """BC NGÀY worksheet rows: merged group headers (row0) + data rows.

    Data rows: [NGÀY, THÁNG, VỤ CHÁY, SCLQ, CHI VIỆN, CNCH, KIỂM TRA..., TUYÊN TRUYỀN..., HUẤN LUYỆN..., PA...]
    """
    rows = [
        # Row 0: merged group headers
        [
            "NGÀY", "THÁNG",
            "VỤ CHÁY VÀ CNCH\nVỤ CHÁY\nTHỐNG KÊ",
            "SCLQ ĐẾN\nPCCC&\nCNCH",
            "CHI VIỆN",
            "CNCH",
            "CÔNG TÁC KIỂM TRA ĐỊNH KỲ NHÓM I", "NHÓM II",
            "ĐỘT XUẤT NHÓM I", "NHÓM II",
            "HƯỚNG DẪN", "KIẾN\nNGHỊ", "XỬ PHẠT", "TIỀN PHẠT\n(triệu đồng)", "ĐÌNH CHỈ", "PHỤC HỒI",
            "TUYÊN TRUYỀN PCCC TIN BÀI", "PHÓNG SỰ",
            "SỐ LỚP TUYÊN TRUYỀN", "SỐ NGƯỜI THAM DỰ", "SỐ KHUYẾN CÁO, TỜ RƠI ĐÃ PHÁT",
            "HUẤN LUYỆN PCCC SỐ LỚP HUẤN LUYỆN", "SỐ NGƯỜI THAM DỰ",
            "TỔNG TUYÊN TRUYỀN/HUẤN LUYỆN SỐ LỚP", "SỐ NGƯỜI THAM DỰ",
            "PACC&CNCH của cơ sở theo mẫu PC06 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "SỐ PA ĐƯỢC THỰC TẬP",
            "PACC&CNCH của CQ CA theo mẫu PC08 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "SỐ PA ĐƯỢC THỰC TẬP",
            "PA CNCH của CQ CA theo mẫu PC09 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "SỐ PA ĐƯỢC THỰC TẬP",
            "PACC&CNCH của phương tiện giao thông theo mẫu PC07 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "SỐ PA ĐƯỢC THỰC TẬP",
            "Ghi chú",
        ],
    ]
    # Data rows with realistic KV30 values
    # Each row: [day, month, vu_chay, sclq, chi_vien, cnch, kt_n1, kt_n2, dx_n1, dx_n2,
    #             huong_dan, kien_nghi, xu_phat, tien_phat, dinh_chi, phuc_hoi,
    #             tin_bai, phong_su, lop_tuyen, nguoi_tuyen, khuyen_cao,
    #             lop_huan, nguoi_huan, tong_lop, tong_nguoi,
    #             pc06_xd, pc06_tt, pc08_xd, pc08_tt, pc09_xd, pc09_tt, pc07_xd, pc07_tt, ghi_chu]
    data = [
        [25.0, 3.0, 1.0, 0.0, 0.0, 0.0, 12.0, 2.0, 0.0, 0.0, 84.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 675.0, 0.0, 0.0, 1.0, 675.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],  # row 1 → 25/03 (fire 24/03 17:20 — time < 22:00 → stays 25/03)
        [21.0, 3.0, 0.0, 0.0, 0.0, 1.0, 8.0, 1.0, 0.0, 0.0, 45.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 340.0, 0.0, 0.0, 1.0, 340.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],  # row 2 → 21/03 (CNCH 20/03 16:33)
        [31.0, 3.0, 0.0, 0.0, 1.0, 0.0, 8.0, 1.0, 0.0, 0.0, 42.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 320.0, 0.0, 0.0, 1.0, 320.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],  # row 3 → 31/03 (CHI VIỆN 31/03 02:55)
        [10.0, 4.0, 0.0, 0.0, 1.0, 1.0, 15.0, 3.0, 0.0, 0.0, 95.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 2.0, 890.0, 0.0, 0.0, 2.0, 890.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],  # row 4 → 10/04 (CNCH 09/04 22:36 + CHI VIỆN 09/04 20:29)
    ]
    for row in data:
        rows.append(row)
    return rows


def _make_cnch_rows() -> list[list[Any]]:
    """CNCH worksheet: row0=group header, row1=column headers, rows2+=data.

    Columns: STT, Loại hình CNCH, Ngày xảy ra sự cố, Thời gian đến,
             Địa điểm, Địa chỉ, Chỉ huy CNCH, Thiệt hại về người, Số người cứu được
    """
    return [
        ["CỨU NẠN, CỨU HỘ"],
        ["STT", "Loại hình CNCH", "Ngày xảy ra sự cố", "Thời gian đến",
         "Địa điểm", "Địa chỉ", "Chỉ huy CNCH", "Thiệt hại về người", "Số người cứu được"],
        [1.0, "Tai nạn máy kết trong thiết bị", "20/03/2026", "16 giờ 33 phút",
         "Công ty TNHH chế biến gỗ Minh Trí",
         "47/1 khu phố Bình Phước B, phường An Phú, thành phố Hồ Chí Minh",
         "Thiếu tá Nguyễn Lâm Vũ", "0", 0.0],
        [2.0, "Vụ cháy", "09/04/2026", "22 giờ 36 phút",
         "Khu dân cư Phú Hưng",
         "123 đường số 5, phường Bình Chiểu, thành phố Hồ Chí Minh",
         "Đại tá Trần Minh Hoàng", "0", 0.0],
    ]


def _make_vu_chay_rows() -> list[list[Any]]:
    """VỤ CHÁY THỐNG KÊ worksheet.

    Columns: STT, NGÀY XẢY RA VỤ CHÁY, VỤ CHÁY, THỜI GIAN, ĐỊA ĐIỂM,
             PHÂN LOẠI, NGUYÊN NHÂN, THIỆT HẠI VỀ NGƯỜI,
             THIỆT HẠI TÀI SẢN, TÀI SẢN CỨU CHỮA,
             THỜI GIAN TỚI ĐÁM CHÁY, THỜI GIAN KHỐNG CHẾ, THỜI GIAN DẬP TẮT HOÀN TOÀN,
             SỐ LƯỢNG XE, CHỈ HUY CHỮA CHÁY, GHI CHÚ
    """
    return [
        ["Vụ cháy CÓ Thống kê"],
        ["STT", "NGÀY XẢY RA VỤ CHÁY", "VỤ CHÁY", "THỜI GIAN", "ĐỊA ĐIỂM",
         "PHÂN LOẠI", "NGUYÊN NHÂN", "THIỆT HẠI VỀ NGƯỜI",
         "THIỆT HẠI TÀI SẢN", "TÀI SẢN CỨU CHỮA",
         "THỜI GIAN TỚI ĐÁM CHÁY", "THỜI GIAN KHỐNG CHẾ", "THỜI GIAN DẬP TẮT HOÀN TOÀN",
         "SỐ LƯỢNG XE", "CHỈ HUY CHỮA CHÁY", "GHI CHÚ"],
        [1.0, "24/03/2026", "Cháy cửa hàng vật liệu xây dựng", "17 giờ 20 phút",
         "18/5 tổ 12 khu phố Tân Thắng, phường An Phú, TP. Thủ Đức",
         "Cháy", "Chập điện", "0", "350 triệu đồng", "Không có",
         "17 giờ 25 phút", "17 giờ 40 phút", "18 giờ 05 phút",
         3.0, "Thiếu tá Nguyễn Văn Minh", "Đã xử lý"],
    ]


def _make_chi_vien_rows() -> list[list[Any]]:
    """CHI VIỆN worksheet.

    Columns: STT, VỤ CHÁY NGÀY, ĐỊA ĐIỂM, KHU VỰC QUẢN LÝ,
             SỐ LƯỢNG XE, THỜI GIAN ĐI, THỜI GIAN VỀ,
             CHỈ HUY CHỮA CHÁY, GHI CHÚ
    """
    return [
        ["VỤ CHÁY CHI VIỆN"],
        ["STT", "VỤ CHÁY NGÀY", "ĐỊA ĐIỂM", "KHU VỰC QUẢN LÝ",
         "SỐ LƯỢNG XE", "THỜI GIAN ĐI", "THỜI GIAN VỀ",
         "CHỈ HUY CHỮA CHÁY", "GHI CHÚ"],
        [1.0, "09/04/2026", "Số 23/8A khu phố Tân Phước, phường Tân Đông Hiệp, thành phố Hồ Chí Minh",
         "Đội CC&CNCH KV33", 2.0, "20 giờ 29 phút", "23 giờ 15 phút",
         "Thiếu tá Lê Minh Thành", "Chi viện PCCC"],
        [2.0, "31/03/2026", "Khu công nghiệp Sóng Thần 2, phường An Bình, thành phố Dĩ An",
         "Đội CC&CNCH KV33", 3.0, "02 giờ 48 phút", "05 giờ 12 phút",
         "Đại úy Phạm Văn Hùng", "Chi viện chữa cháy"],
    ]


def _make_sclq_rows() -> list[list[Any]]:
    """SCLQ ĐẾN PCCC&CNCH worksheet.

    Columns: STT, VỤ CHÁY NGÀY, ĐỊA ĐIỂM, NGUYÊN NHÂN, THIỆT HẠI, CHỈ HUY CHỮA CHÁY, GHI CHÚ
    """
    return [
        ["SỰ CỐ LIÊN QUAN ĐẾN PCCC&CNCH"],
        ["STT", "VỤ CHÁY NGÀY", "ĐỊA ĐIỂM", "NGUYÊN NHÂN", "THIỆT HẠI",
         "CHỈ HUY CHỮA CHÁY", "GHI CHÚ"],
        [1.0, "10/04/2026", "Khu vực cầu Rạch Chiến, phường An Phú, TP. Thủ Đức",
         "Chập điện", "Không có thiệt hại",
         "Đại tá Trần Minh Hoàng", "Sự cố nhỏ, xử lý nhanh"],
    ]


class FakeTemplate:
    """Minimal template stub for DailyReportBuilder."""
    def __init__(self):
        self.schema_definition = {}
        self.aggregation_rules = {}
        self.name = "KV30 Test"


KV30_CONFIGS = [
    {
        "worksheet": "BC NGÀY",
        "schema_path": "bc_ngay_kv30_schema.yaml",
        "role": "master",
        "header_row": 0,
        "data_start_row": 1,
        "target_section": None,
    },
    {
        "worksheet": "CNCH",
        "schema_path": "cnch_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_cnch",
    },
    {
        "worksheet": "VỤ CHÁY THỐNG KÊ",
        "schema_path": "vu_chay_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_chay",
    },
    {
        "worksheet": "CHI VIỆN",
        "schema_path": "chi_vien_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_chi_vien",
    },
    {
        "worksheet": "SCLQ ĐẾN PCCC&CNCH",
        "schema_path": "sclq_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_sclq",
    },
]


def _make_sheet_data() -> dict[str, list[list[Any]]]:
    sheet_data = {
        "BC NGÀY": _make_bc_ngay_rows(),
        "CNCH": _make_cnch_rows(),
        "VỤ CHÁY THỐNG KÊ": _make_vu_chay_rows(),
        "CHI VIỆN": _make_chi_vien_rows(),
        "SCLQ ĐẾN PCCC&CNCH": _make_sclq_rows(),
    }
    print([row[:5] for row in sheet_data["BC NGÀY"]])
    return sheet_data


# ─────────────────────────────────────────────────────────────────
# Tests: Date normalizer + 07:30 cutoff
# ─────────────────────────────────────────────────────────────────

class TestDateNormalizerAndCutoff:
    """VIỆC 1: Verify date normalizer and 07:30 cutoff logic."""

    @pytest.fixture
    def builder(self):
        return DailyReportBuilder(
            template=FakeTemplate(),
            sheet_data={},
            worksheet_configs=[],
        )

    def test_normalize_excel_serial_number(self, builder):
        """46121 = 09/04/2026 (Excel serial base 1899-12-30)."""
        result = builder._normalize_date_to_ddmm(46121)
        assert result == "09/04", f"Expected 09/04, got {result}"

    def test_normalize_google_style_date_april(self, builder):
        """Date(2026,3,9) → 09/04/2026 (month is zero-based)."""
        result = builder._normalize_date_to_ddmm("Date(2026,3,9)")
        assert result == "09/04", f"Expected 09/04, got {result}"

    def test_normalize_google_style_date_march(self, builder):
        """Date(2026,2,24) → 24/03/2026 (month is zero-based)."""
        result = builder._normalize_date_to_ddmm("Date(2026,2,24)")
        assert result == "24/03", f"Expected 24/03, got {result}"

    def test_compute_report_date_key_after_cutoff(self, builder):
        """Time >= 07:30 → event_date + 1 day."""
        assert builder._compute_report_date_key("24/03/2026", "17 giờ 20 phút") == "25/03"
        assert builder._compute_report_date_key("20/03/2026", "16 giờ 33 phút") == "21/03"
        assert builder._compute_report_date_key("09/04/2026", "22 giờ 36 phút") == "10/04"
        assert builder._compute_report_date_key("09/04/2026", "20 giờ 29 phút") == "10/04"

    def test_compute_report_date_key_before_cutoff(self, builder):
        """Time < 07:30 → event_date stays the same."""
        assert builder._compute_report_date_key("31/03/2026", "02 giờ 55 phút") == "31/03"
        assert builder._compute_report_date_key("31/03/2026", "05 giờ 40 phút") == "31/03"

    def test_compute_report_date_key_no_time(self, builder):
        """No time → event_date stays the same."""
        assert builder._compute_report_date_key("15/04/2026") == "15/04"

    def test_compute_report_date_key_time_0730_exactly(self, builder):
        """Time = 07:30 → after cutoff → +1 day."""
        assert builder._compute_report_date_key("05/04/2026", "07 giờ 30 phút") == "06/04"

    def test_compute_report_date_key_time_just_before_cutoff(self, builder):
        """Time = 07:29 → before cutoff → same day."""
        assert builder._compute_report_date_key("05/04/2026", "07 giờ 29 phút") == "05/04"


# ─────────────────────────────────────────────────────────────────
# Tests: Guard methods
# ─────────────────────────────────────────────────────────────────

class TestGuardMethods:
    """VIỆC 4: Verify _is_partial_output_empty and _partial_has_target_data."""

    @pytest.fixture
    def builder(self):
        return DailyReportBuilder(
            template=FakeTemplate(),
            sheet_data={},
            worksheet_configs=[],
        )

    def test_empty_partial_is_empty(self, builder):
        empty = BlockExtractionOutput(
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
        assert builder._is_partial_output_empty(empty) is True

    def test_partial_with_btk_not_empty(self, builder):
        partial = BlockExtractionOutput(
            header=BlockHeader(),
            phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
            bang_thong_ke=[ChiTieu(stt="1", noi_dung="Test", ket_qua=5)],
            danh_sach_cnch=[],
            danh_sach_phuong_tien_hu_hong=[],
            danh_sach_cong_van_tham_muu=[],
            danh_sach_cong_tac_khac=[],
            danh_sach_chi_vien=[],
            danh_sach_chay=[],
            danh_sach_sclq=[],
            tuyen_truyen_online=TuyenTruyenOnline(),
        )
        assert builder._is_partial_output_empty(partial) is False

    def test_partial_with_cnch_not_empty(self, builder):
        partial = BlockExtractionOutput(
            header=BlockHeader(),
            phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
            bang_thong_ke=[],
            danh_sach_cnch=[CNCHItem(stt=1)],
            danh_sach_phuong_tien_hu_hong=[],
            danh_sach_cong_van_tham_muu=[],
            danh_sach_cong_tac_khac=[],
            danh_sach_chi_vien=[],
            danh_sach_chay=[],
            danh_sach_sclq=[],
            tuyen_truyen_online=TuyenTruyenOnline(),
        )
        assert builder._is_partial_output_empty(partial) is False

    def test_partial_none_returns_empty(self, builder):
        assert builder._is_partial_output_empty(None) is True

    def test_partial_has_target_data_with_cnch(self, builder):
        partial = BlockExtractionOutput(
            header=BlockHeader(),
            phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
            bang_thong_ke=[],
            danh_sach_cnch=[CNCHItem(stt=1)],
            danh_sach_phuong_tien_hu_hong=[],
            danh_sach_cong_van_tham_muu=[],
            danh_sach_cong_tac_khac=[],
            danh_sach_chi_vien=[],
            danh_sach_chay=[],
            danh_sach_sclq=[],
            tuyen_truyen_online=TuyenTruyenOnline(),
        )
        assert builder._partial_has_target_data(partial, "danh_sach_cnch") is True
        assert builder._partial_has_target_data(partial, "danh_sach_chay") is False

    def test_partial_has_target_data_no_target_section(self, builder):
        partial = BlockExtractionOutput(
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
        # No target_section → always True
        assert builder._partial_has_target_data(partial, None) is True
        assert builder._partial_has_target_data(partial, "") is True


# ─────────────────────────────────────────────────────────────────
# Tests: Full build_all_by_date contract
# ─────────────────────────────────────────────────────────────────

class TestBuildAllByDateContract:
    """VIỆC 6: End-to-end test with KV30 Excel fixture data."""

    @pytest.fixture
    def builder(self, monkeypatch: pytest.MonkeyPatch):
        sheet_data = _make_sheet_data()
        # Capture original BEFORE patching to avoid RecursionError
        _original_run = SheetExtractionPipeline.run

        def _fake_run(self, pipeline_input, schema_path=None):
            return _original_run(self, pipeline_input, schema_path=schema_path)

        monkeypatch.setattr(SheetExtractionPipeline, "run", _fake_run)

        return DailyReportBuilder(
            template=FakeTemplate(),
            sheet_data=sheet_data,
            worksheet_configs=KV30_CONFIGS,
        )

    def test_build_all_by_date_returns_reports(self, builder):
        """Must return non-empty dict of date-keyed reports."""
        reports = builder.build_all_by_date()
        assert isinstance(reports, dict), "build_all_by_date must return a dict"
        assert len(reports) > 0, "Expected at least one date report"

    def test_report_25_03_exists(self, builder):
        """25/03 report must exist (fire from 24/03 17:20 crosses cutoff)."""
        reports = builder.build_all_by_date()
        assert "25/03" in reports, f"Expected 25/03 in {list(reports.keys())}"

    def test_report_10_04_exists(self, builder):
        """10/04 report must exist (CNCH 09/04 22:36 + CHI VIỆN 09/04 20:29 both cross cutoff)."""
        reports = builder.build_all_by_date()
        assert "10/04" in reports, f"Expected 10/04 in {list(reports.keys())}"

    def test_report_31_03_exists(self, builder):
        """31/03 report must exist (CHI VIỆN 31/03 02:55 is before cutoff, stays same day)."""
        reports = builder.build_all_by_date()
        assert "31/03" in reports, f"Expected 31/03 in {list(reports.keys())}"

    def test_report_21_03_exists(self, builder):
        """21/03 report must exist (CNCH 20/03 16:33 crosses cutoff)."""
        reports = builder.build_all_by_date()
        assert "21/03" in reports, f"Expected 21/03 in {list(reports.keys())}"

    def test_no_empty_date_key_in_reports(self, builder):
        """Regression: build_all_by_date() must not return empty-string key."""
        reports = builder.build_all_by_date()
        assert "" not in reports, (
            f"Empty date_key '' found in reports keys: {list(reports.keys())}"
        )
        # Also ensure all keys are truthy and match DD/MM pattern
        for dk in reports:
            assert dk and str(dk).strip(), f"Falsy date_key={dk!r}"
            assert "/" in str(dk), f"date_key {dk!r} does not look like DD/MM"

    def test_reports_are_valid_block_extraction_output(self, builder):
        """Each report must validate against BlockExtractionOutput schema."""
        reports = builder.build_all_by_date()
        for date_key, report in reports.items():
            try:
                BlockExtractionOutput.model_validate(report.model_dump())
            except Exception as exc:
                pytest.fail(f"Report for {date_key} failed validation: {exc}")

    def test_bang_thong_ke_has_known_labels(self, builder):
        """Known STT entries in bang_thong_ke must have non-empty noi_dung."""
        reports = builder.build_all_by_date()
        known_stt = {"22", "23", "24", "25", "26", "27", "28", "29", "31", "32", "33", "34",
                     "35", "39", "40", "43", "44", "49", "50", "52", "53", "55", "56", "57",
                     "58", "59", "60", "61"}
        found_empty = []
        for date_key, report in reports.items():
            for item in report.bang_thong_ke:
                if str(item.stt) in known_stt and not (item.noi_dung and item.noi_dung.strip()):
                    found_empty.append((date_key, item.stt, item.noi_dung))
        assert not found_empty, f"bang_thong_ke entries with empty noi_dung: {found_empty}"

    def test_report_json_serialization(self, builder):
        """Each report must serialize to JSON without errors."""
        reports = builder.build_all_by_date()
        for date_key, report in reports.items():
            try:
                json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
            except Exception as exc:
                pytest.fail(f"Report for {date_key} failed JSON serialization: {exc}")

    def test_no_google_api_called(self, monkeypatch: pytest.MonkeyPatch):
        """Verify GoogleSheetsSource is never called during test."""
        called = []

        def _raise(*args, **kwargs):
            called.append((args, kwargs))
            raise RuntimeError("Google Sheets API called - test must not use it")

        monkeypatch.setattr(
            "app.engines.extraction.sources.sheets_source.GoogleSheetsSource.fetch_values",
            _raise,
        )

        sheet_data = _make_sheet_data()
        builder = DailyReportBuilder(
            template=FakeTemplate(),
            sheet_data=sheet_data,
            worksheet_configs=KV30_CONFIGS,
        )
        # This should NOT raise because fetch_values is not called
        try:
            reports = builder.build_all_by_date()
            assert len(reports) > 0, "Expected non-empty reports"
        except RuntimeError as e:
            if "Google Sheets API called" in str(e):
                pytest.fail("GoogleSheetsSource.fetch_values was called - test must not use it")
            raise


class TestDetailSheetsRouting:
    """VIỆC 6: Verify detail sheets route to correct report dates."""

    @pytest.fixture
    def builder(self, monkeypatch: pytest.MonkeyPatch):
        sheet_data = _make_sheet_data()
        # Capture original BEFORE patching to avoid recursion
        _original_run = SheetExtractionPipeline.run

        def _fake_run(self, pipeline_input, schema_path=None):
            return _original_run(self, pipeline_input, schema_path=schema_path)

        monkeypatch.setattr(SheetExtractionPipeline, "run", _fake_run)
        return DailyReportBuilder(
            template=FakeTemplate(),
            sheet_data=sheet_data,
            worksheet_configs=KV30_CONFIGS,
        )

    def test_fire_24_03_goes_to_report_25_03(self, builder):
        """VU CHÁY 24/03/2026 17:20 → report 25/03."""
        reports = builder.build_all_by_date()
        report = reports.get("25/03")
        assert report is not None
        assert len(report.danh_sach_chay) >= 1, (
            f"Expected danh_sach_chay >= 1 in 25/03, got {len(report.danh_sach_chay)}. "
            f"Items: {report.danh_sach_chay}"
        )
        # Check that it references the fire date or time
        chay_text = json.dumps([x.model_dump() for x in report.danh_sach_chay], ensure_ascii=False)
        assert "24/03" in chay_text or "17" in chay_text, (
            f"Expected fire detail with 24/03 or 17 in danh_sach_chay: {chay_text}"
        )

    def test_cnch_20_03_1633_goes_to_report_21_03(self, builder):
        """CNCH 20/03/2026 16:33 → report 21/03."""
        reports = builder.build_all_by_date()
        report = reports.get("21/03")
        assert report is not None
        assert len(report.danh_sach_cnch) >= 1, (
            f"Expected danh_sach_cnch >= 1 in 21/03, got {len(report.danh_sach_cnch)}. "
            f"Items: {report.danh_sach_cnch}"
        )
        cnch_text = json.dumps([x.model_dump() for x in report.danh_sach_cnch], ensure_ascii=False)
        assert "20/03" in cnch_text or "16" in cnch_text, (
            f"Expected CNCH detail with 20/03 or 16 in danh_sach_cnch: {cnch_text}"
        )
        # Regression: thoi_gian must be normalized to date+time
        cnch_item = report.danh_sach_cnch[0]
        assert cnch_item.thoi_gian == "20/03/2026 16:33", (
            f"Expected thoi_gian='20/03/2026 16:33', got {cnch_item.thoi_gian!r}"
        )

    def test_cnch_09_04_2236_goes_to_report_10_04(self, builder):
        """CNCH 09/04/2026 22:36 → report 10/04."""
        reports = builder.build_all_by_date()
        report = reports.get("10/04")
        assert report is not None
        assert len(report.danh_sach_cnch) >= 1, (
            f"Expected danh_sach_cnch >= 1 in 10/04, got {len(report.danh_sach_cnch)}. "
            f"Items: {report.danh_sach_cnch}"
        )
        cnch_text = json.dumps([x.model_dump() for x in report.danh_sach_cnch], ensure_ascii=False)
        assert "09/04" in cnch_text or "22" in cnch_text, (
            f"Expected CNCH detail with 09/04 or 22 in danh_sach_cnch: {cnch_text}"
        )
        # Regression: thoi_gian must be normalized to date+time
        cnch_item = report.danh_sach_cnch[0]
        assert cnch_item.thoi_gian == "09/04/2026 22:36", (
            f"Expected thoi_gian='09/04/2026 22:36', got {cnch_item.thoi_gian!r}"
        )

    def test_chi_vien_09_04_2029_goes_to_report_10_04(self, builder):
        """CHI VIỆN 09/04/2026 20:29 → report 10/04."""
        reports = builder.build_all_by_date()
        report = reports.get("10/04")
        assert report is not None
        assert len(report.danh_sach_chi_vien) >= 1, (
            f"Expected danh_sach_chi_vien >= 1 in 10/04, got {len(report.danh_sach_chi_vien)}. "
            f"Items: {report.danh_sach_chi_vien}"
        )
        cv_text = json.dumps([x.model_dump() for x in report.danh_sach_chi_vien], ensure_ascii=False)
        assert "09/04" in cv_text or "20" in cv_text, (
            f"Expected CHI VIỆN detail with 09/04 or 20 in danh_sach_chi_vien: {cv_text}"
        )
        chi_vien_item = report.danh_sach_chi_vien[0]
        assert chi_vien_item.thoi_gian_di == "20:29", (
            f"Expected thoi_gian_di='20:29', got {chi_vien_item.thoi_gian_di!r}"
        )
        assert chi_vien_item.thoi_gian_ve == "23:15", (
            f"Expected thoi_gian_ve='23:15', got {chi_vien_item.thoi_gian_ve!r}"
        )

    def test_chi_vien_31_03_0255_goes_to_report_31_03(self, builder):
        """CHI VIỆN 31/03/2026 02:55 → report 31/03 (before cutoff, stays same day)."""
        reports = builder.build_all_by_date()
        report = reports.get("31/03")
        assert report is not None
        assert len(report.danh_sach_chi_vien) >= 1, (
            f"Expected danh_sach_chi_vien >= 1 in 31/03, got {len(report.danh_sach_chi_vien)}. "
            f"Items: {report.danh_sach_chi_vien}"
        )
        cv_text = json.dumps([x.model_dump() for x in report.danh_sach_chi_vien], ensure_ascii=False)
        assert "31/03" in cv_text or "02" in cv_text, (
            f"Expected CHI VIỆN detail with 31/03 or 02 in danh_sach_chi_vien: {cv_text}"
        )

    def test_sclq_10_04_in_report_10_04(self, builder):
        """SCLQ ĐẾN PCCC&CNCH row with date 10/04 → report 10/04."""
        reports = builder.build_all_by_date()
        report = reports.get("10/04")
        assert report is not None
        assert len(report.danh_sach_sclq) >= 1, (
            f"Expected danh_sach_sclq >= 1 in 10/04, got {len(report.danh_sach_sclq)}. "
            f"Items: {[x.model_dump() for x in report.danh_sach_sclq]}"
        )


class TestSCLQBuilder:
    """VIỆC 5: Verify SCLQ items are built by the pipeline."""

    def test_sclq_builder_in_pipeline(self):
        """SCLQItem schema must be constructible with SCLQ ĐẾN data."""
        item = SCLQItem(
            stt=1,
            ngay="10/04/2026",
            dia_diem="Khu vực cầu Rạch Chiến",
            nguyen_nhan="Chập điện",
            thiet_hai="Không có",
            chi_huy="Đại tá Trần Minh Hoàng",
            ghi_chu="Sự cố nhỏ",
        )
        assert item.ngay == "10/04/2026"
        assert item.dia_diem == "Khu vực cầu Rạch Chiến"
        assert item.nguyen_nhan == "Chập điện"
