"""Test KV30 business mapping: BC NGÀY → STT 1-61 + Word context."""

import pytest
from app.engines.extraction.kv30_business_mapping import (
    build_kv30_bang_thong_ke,
    build_kv30_word_context,
    KV30_STT_DEFS,
)


class TestKV30BangThongKe:
    """Test full STT 1-61 bang_thong_ke generation."""

    def test_build_bang_thong_ke_structure(self):
        """Verify bang_thong_ke contains all 61 STT rows."""
        master_data = {
            "tong_so_vu_chay": 2,
            "tong_so_vu_cnch": 1,
            "tong_chi_vien": 3,
            "kiem_tra_dinh_ky_nhom_1": 10,
            "kiem_tra_dinh_ky_nhom_2": 5,
            "kiem_tra_dot_xuat_nhom_1": 2,
            "kiem_tra_dot_xuat_nhom_2": 1,
            "huong_dan": 50,
            "kien_nghi": 3,
            "xu_phat": 2,
            "tien_phat": 5.5,
            "dinh_chi": 1,
            "tin_bai": 10,
            "phong_su": 2,
            "tuyen_truyen_lop": 5,
            "tuyen_truyen_nguoi": 200,
            "khuyen_cao_to_roi": 100,
            "pa_pc06_xay_dung": 8,
            "pa_pc06_thuc_tap": 6,
            "pa_pc07_xay_dung": 3,
            "pa_pc07_thuc_tap": 2,
            "pa_pc08_xay_dung": 1,
            "pa_pc08_thuc_tap": 1,
            "pa_pc09_xay_dung": 1,
            "pa_pc09_thuc_tap": 0,
        }
        detail_items = {
            "danh_sach_chay": [],
            "danh_sach_cnch": [{"so_nguoi_cuu": 2}],
        }
        defaults = {}

        result = build_kv30_bang_thong_ke(master_data, detail_items, defaults)

        assert len(result) == 61
        assert all("stt" in row and "noi_dung" in row and "ket_qua" in row for row in result)

        # Check header rows
        assert result[0]["stt"] == "1"
        assert "TÌNH HÌNH CHÁY" in result[0]["noi_dung"]
        assert result[19]["stt"] == "20"
        assert "TUYÊN TRUYỀN" in result[19]["noi_dung"]

    def test_fire_section_mapping(self):
        """Test STT 2-7 fire statistics."""
        master_data = {"tong_so_vu_chay": 3}
        detail_items = {
            "danh_sach_chay": [
                {"thiet_hai_tai_san": 100.5, "tai_san_cuu": 50.0},
                {"thiet_hai_tai_san": 200.0, "tai_san_cuu": 75.5},
            ],
            "danh_sach_cnch": [],
        }
        defaults = {}

        result = build_kv30_bang_thong_ke(master_data, detail_items, defaults)

        stt_02 = next(r for r in result if r["stt"] == "2")
        assert stt_02["ket_qua"] == 3

        stt_06 = next(r for r in result if r["stt"] == "6")
        assert stt_06["ket_qua"] == 300.5

        stt_07 = next(r for r in result if r["stt"] == "7")
        assert stt_07["ket_qua"] == 125.5

    def test_cnch_section_mapping(self):
        """Test STT 14-19 CNCH statistics."""
        master_data = {"tong_so_vu_cnch": 2}
        detail_items = {
            "danh_sach_chay": [],
            "danh_sach_cnch": [
                {"so_nguoi_cuu": 3},
                {"so_nguoi_cuu": 1},
            ],
        }
        defaults = {}

        result = build_kv30_bang_thong_ke(master_data, detail_items, defaults)

        stt_14 = next(r for r in result if r["stt"] == "14")
        assert stt_14["ket_qua"] == 2

        stt_15 = next(r for r in result if r["stt"] == "15")
        assert stt_15["ket_qua"] == 4

        stt_16 = next(r for r in result if r["stt"] == "16")
        assert stt_16["ket_qua"] == 4

    def test_inspection_section_formulas(self):
        """Test STT 31-33 inspection totals with formulas."""
        master_data = {
            "kiem_tra_dinh_ky_nhom_1": 12,
            "kiem_tra_dinh_ky_nhom_2": 8,
            "kiem_tra_dot_xuat_nhom_1": 3,
            "kiem_tra_dot_xuat_nhom_2": 2,
        }
        detail_items = {"danh_sach_chay": [], "danh_sach_cnch": []}
        defaults = {}

        result = build_kv30_bang_thong_ke(master_data, detail_items, defaults)

        stt_31 = next(r for r in result if r["stt"] == "31")
        assert stt_31["ket_qua"] == 25  # 12+8+3+2

        stt_32 = next(r for r in result if r["stt"] == "32")
        assert stt_32["ket_qua"] == 20  # 12+8

        stt_33 = next(r for r in result if r["stt"] == "33")
        assert stt_33["ket_qua"] == 5  # 3+2

    def test_penalty_section_formulas(self):
        """Test STT 35-40 penalty statistics."""
        master_data = {
            "kien_nghi": 10,
            "xu_phat": 5,
            "dinh_chi": 2,
            "tien_phat": 15.5,
        }
        detail_items = {"danh_sach_chay": [], "danh_sach_cnch": []}
        defaults = {}

        result = build_kv30_bang_thong_ke(master_data, detail_items, defaults)

        stt_34 = next(r for r in result if r["stt"] == "34")
        assert stt_34["ket_qua"] == 10

        stt_35 = next(r for r in result if r["stt"] == "35")
        assert stt_35["ket_qua"] == 7  # 0+0+2+5

        stt_38 = next(r for r in result if r["stt"] == "38")
        assert stt_38["ket_qua"] == 2

        stt_39 = next(r for r in result if r["stt"] == "39")
        assert stt_39["ket_qua"] == 5

        stt_40 = next(r for r in result if r["stt"] == "40")
        assert stt_40["ket_qua"] == 15.5

    def test_plan_section_mapping(self):
        """Test STT 43-53 plan statistics."""
        master_data = {
            "pa_pc06_xay_dung": 10,
            "pa_pc06_thuc_tap": 8,
            "pa_pc07_xay_dung": 5,
            "pa_pc07_thuc_tap": 4,
            "pa_pc08_xay_dung": 2,
            "pa_pc08_thuc_tap": 1,
            "pa_pc09_xay_dung": 3,
            "pa_pc09_thuc_tap": 2,
        }
        detail_items = {"danh_sach_chay": [], "danh_sach_cnch": []}
        defaults = {}

        result = build_kv30_bang_thong_ke(master_data, detail_items, defaults)

        stt_43 = next(r for r in result if r["stt"] == "43")
        assert stt_43["ket_qua"] == 10

        stt_44 = next(r for r in result if r["stt"] == "44")
        assert stt_44["ket_qua"] == 8

        stt_46 = next(r for r in result if r["stt"] == "46")
        assert stt_46["ket_qua"] == 5

        stt_49 = next(r for r in result if r["stt"] == "49")
        assert stt_49["ket_qua"] == 2

        stt_52 = next(r for r in result if r["stt"] == "52")
        assert stt_52["ket_qua"] == 3

    def test_training_section_with_defaults(self):
        """Test STT 55-61 training with defaults."""
        master_data = {}
        detail_items = {"danh_sach_chay": [], "danh_sach_cnch": []}
        defaults = {
            "stt_56_hl_chi_huy_phong": 2,
            "stt_57_hl_chi_huy_doi": 5,
            "stt_58_hl_can_bo_tieu_doi": 10,
            "stt_59_hl_chien_sy": 50,
            "stt_60_hl_lai_xe": 8,
            "stt_61_hl_lai_tau": 3,
        }

        result = build_kv30_bang_thong_ke(master_data, detail_items, defaults)

        stt_55 = next(r for r in result if r["stt"] == "55")
        assert stt_55["ket_qua"] == 78  # 2+5+10+50+8+3

        stt_56 = next(r for r in result if r["stt"] == "56")
        assert stt_56["ket_qua"] == 2


class TestKV30WordContext:
    """Test Word template context generation."""

    def test_word_context_structure(self):
        """Verify word context has all required keys."""
        output_dict = {
            "header": {
                "so_bao_cao": "123",
                "ngay_bao_cao": "01/04/2026",
                "don_vi_bao_cao": "KV30",
                "thoi_gian_tu_den": "07:30 ngày 31/03 đến 07:30 ngày 01/04",
            },
            "phan_I_va_II_chi_tiet_nghiep_vu": {
                "tong_so_vu_chay": 2,
                "tong_so_vu_cnch": 1,
                "tong_chi_vien": 3,
            },
            "bang_thong_ke": [],
            "danh_sach_chay": [],
            "danh_sach_cnch": [],
            "danh_sach_chi_vien": [],
            "danh_sach_sclq": [],
        }
        defaults = {}

        context = build_kv30_word_context(output_dict, defaults)

        # Header fields
        assert context["so_bao_cao"] == "123"
        assert context["ngay_bao_cao"] == "01/04/2026"

        # Narrative totals
        assert "tong_so_vu_chay" in context
        assert "tong_so_vu_cnch" in context
        assert "tong_chi_vien" in context

        # Lists
        assert "danh_sach_chay" in context
        assert "danh_sach_cnch" in context
        assert "danh_sach_su_co" in context

    def test_word_context_stt_variables(self):
        """Verify STT variables are flattened."""
        output_dict = {
            "header": {},
            "phan_I_va_II_chi_tiet_nghiep_vu": {},
            "bang_thong_ke": [
                {"stt": "2", "noi_dung": "Tổng số vụ cháy", "ket_qua": 5},
                {"stt": "14", "noi_dung": "Tổng số vụ CNCH", "ket_qua": 3},
                {"stt": "31", "noi_dung": "Tổng số cơ sở kiểm tra", "ket_qua": 25},
            ],
            "danh_sach_chay": [],
            "danh_sach_cnch": [],
            "danh_sach_chi_vien": [],
            "danh_sach_sclq": [],
        }
        defaults = {}

        context = build_kv30_word_context(output_dict, defaults)

        assert context["stt_02_tong_chay"] == 5
        assert context["stt_14_tong_cnch"] == 3
        assert context["stt_31_kiem_tra_tong"] == 25

    def test_word_context_danh_sach_su_co_alias(self):
        """Verify danh_sach_su_co maps to danh_sach_sclq."""
        output_dict = {
            "header": {},
            "phan_I_va_II_chi_tiet_nghiep_vu": {},
            "bang_thong_ke": [],
            "danh_sach_chay": [],
            "danh_sach_cnch": [],
            "danh_sach_chi_vien": [],
            "danh_sach_sclq": [{"stt": 1, "ngay": "01/04"}],
        }
        defaults = {}

        context = build_kv30_word_context(output_dict, defaults)

        assert context["danh_sach_su_co"] == output_dict["danh_sach_sclq"]
        assert len(context["danh_sach_su_co"]) == 1
