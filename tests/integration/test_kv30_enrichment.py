"""Test KV30 enrichment: Date(...) normalization, header defaults."""

import pytest
from app.engines.extraction.kv30_enrichment import enrich_kv30_block_output, _normalize_google_sheets_datetime


class TestNormalizeGoogleSheetsDateTime:
    """Test Date(...) string normalization."""

    def test_normalize_date_with_time(self):
        """Convert Date(2026,3,9) 22:36 -> 22:36 ngày 09/04/2026."""
        result = _normalize_google_sheets_datetime("Date(2026,3,9) 22:36")
        assert result == "22:36 ngày 09/04/2026"

    def test_normalize_date_without_time(self):
        """Convert Date(2026,2,20) -> 20/03/2026."""
        result = _normalize_google_sheets_datetime("Date(2026,2,20)")
        assert result == "20/03/2026"

    def test_normalize_date_month_zero_indexed(self):
        """Month 0 = January, month 11 = December."""
        assert _normalize_google_sheets_datetime("Date(2026,0,31)") == "31/01/2026"
        assert _normalize_google_sheets_datetime("Date(2026,11,25)") == "25/12/2026"

    def test_passthrough_non_date_strings(self):
        """Non-Date(...) strings pass through unchanged."""
        assert _normalize_google_sheets_datetime("09/04/2026") == "09/04/2026"
        assert _normalize_google_sheets_datetime("22:36") == "22:36"
        assert _normalize_google_sheets_datetime("") == ""


class TestEnrichKV30BlockOutput:
    """Test read-time enrichment."""

    def test_fill_don_vi_bao_cao(self):
        """Fill header.don_vi_bao_cao if blank."""
        data = {"header": {}}
        enrich_kv30_block_output(data)
        assert data["header"]["don_vi_bao_cao"] == "ĐỘI CC&CNCH KHU VỰC 30"

    def test_preserve_existing_don_vi_bao_cao(self):
        """Do not overwrite existing don_vi_bao_cao."""
        data = {"header": {"don_vi_bao_cao": "Custom Unit"}}
        enrich_kv30_block_output(data)
        assert data["header"]["don_vi_bao_cao"] == "Custom Unit"

    def test_fill_thoi_gian_tu_den(self):
        """Fill header.thoi_gian_tu_den from report_date."""
        data = {"header": {}}
        enrich_kv30_block_output(data, report_date="10/04/2026")
        expected = "Từ 07 h 30' ngày 09/04/2026 đến 07 h 30' ngày 10/04/2026"
        assert data["header"]["thoi_gian_tu_den"] == expected

    def test_normalize_cnch_thoi_gian(self):
        """Normalize Date(...) in danh_sach_cnch.thoi_gian."""
        data = {
            "header": {},
            "danh_sach_cnch": [
                {"stt": 1, "thoi_gian": "Date(2026,3,9) 22:36", "dia_diem": "Test"},
            ],
        }
        enrich_kv30_block_output(data)
        assert data["danh_sach_cnch"][0]["thoi_gian"] == "22:36 ngày 09/04/2026"

    def test_normalize_chi_vien_ngay(self):
        """Normalize Date(...) in danh_sach_chi_vien.ngay."""
        data = {
            "header": {},
            "danh_sach_chi_vien": [
                {"stt": 1, "ngay": "Date(2026,2,31)", "dia_diem": "Test"},
            ],
        }
        enrich_kv30_block_output(data)
        assert data["danh_sach_chi_vien"][0]["ngay"] == "31/03/2026"

    def test_alias_danh_sach_su_co(self):
        """Alias danh_sach_sclq -> danh_sach_su_co."""
        data = {
            "header": {},
            "danh_sach_sclq": [{"stt": 1, "ngay": "21/03/2026"}],
        }
        enrich_kv30_block_output(data)
        assert "danh_sach_su_co" in data
        assert data["danh_sach_su_co"] == data["danh_sach_sclq"]

    def test_no_overwrite_existing_danh_sach_su_co(self):
        """Do not overwrite existing danh_sach_su_co."""
        data = {
            "header": {},
            "danh_sach_sclq": [{"stt": 1}],
            "danh_sach_su_co": [{"stt": 2}],
        }
        enrich_kv30_block_output(data)
        assert data["danh_sach_su_co"] == [{"stt": 2}]
