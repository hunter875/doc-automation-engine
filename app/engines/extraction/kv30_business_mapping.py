"""KV30 business mapping: BC NGÀY columns → STT 1-61 + Word template variables."""

from typing import Any

# BC NGÀY source column indices (0-based)
KV30_BC_NGAY_COLS = {
    "day": 0,
    "month": 1,
    "tong_so_vu_chay": 2,
    "tong_sclq": 3,
    "tong_chi_vien": 4,
    "tong_so_vu_cnch": 5,
    "kiem_tra_dinh_ky_nhom_1": 6,
    "kiem_tra_dinh_ky_nhom_2": 7,
    "kiem_tra_dot_xuat_nhom_1": 8,
    "kiem_tra_dot_xuat_nhom_2": 9,
    "huong_dan": 10,
    "kien_nghi": 11,
    "xu_phat": 12,
    "tien_phat": 13,
    "dinh_chi": 14,
    "phuc_hoi": 15,
    "tin_bai": 16,
    "phong_su": 17,
    "tuyen_truyen_lop": 18,
    "tuyen_truyen_nguoi": 19,
    "khuyen_cao_to_roi": 20,
    "huan_luyen_lop": 21,
    "huan_luyen_nguoi": 22,
    "tong_lop_tuyen_truyen_huan_luyen": 23,
    "tong_nguoi_tuyen_truyen_huan_luyen": 24,
    "pa_pc06_xay_dung": 25,
    "pa_pc06_thuc_tap": 26,
    "pa_pc08_xay_dung": 27,
    "pa_pc08_thuc_tap": 28,
    "pa_pc09_xay_dung": 29,
    "pa_pc09_thuc_tap": 30,
    "pa_pc07_xay_dung": 31,
    "pa_pc07_thuc_tap": 32,
    "ghi_chu": 33,
}

# STT definitions: stt → (noi_dung, is_header)
KV30_STT_DEFS = {
    1: ("I. TÌNH HÌNH CHÁY, NỔ, CỨU NẠN, CỨU HỘ", True),
    2: ("Tổng số vụ cháy", False),
    3: ("Số người chết", False),
    4: ("Số người bị thương", False),
    5: ("Số người được cứu", False),
    6: ("Thiệt hại tài sản (triệu đồng)", False),
    7: ("Tài sản cứu được (triệu đồng)", False),
    8: ("Tổng số vụ nổ", False),
    9: ("Số người chết", False),
    10: ("Số người bị thương", False),
    11: ("Số người được cứu", False),
    12: ("Thiệt hại tài sản (triệu đồng)", False),
    13: ("Tài sản cứu được (triệu đồng)", False),
    14: ("Tổng số vụ CNCH", False),
    15: ("Số người được cứu", False),
    16: ("Cứu trực tiếp", False),
    17: ("Hướng dẫn tự thoát", False),
    18: ("Số thi thể", False),
    19: ("Tài sản cứu được (triệu đồng)", False),
    20: ("II. CÔNG TÁC TUYÊN TRUYỀN, PHỔ BIẾN PHÁP LUẬT VỀ PCCC", True),
    21: ("1. Tuyên truyền trên các phương tiện thông tin đại chúng", True),
    22: ("a) Tuyên truyền trên mạng xã hội", True),
    23: ("Tin bài", False),
    24: ("Hình ảnh", False),
    25: ("Video", False),
    26: ("b) Tuyên truyền trực tiếp", True),
    27: ("Số cuộc", False),
    28: ("Số người tham dự", False),
    29: ("Số khuyến cáo, tờ rơi đã phát", False),
    30: ("III. CÔNG TÁC KIỂM TRA, HƯỚNG DẪN VỀ PCCC", True),
    31: ("Tổng số cơ sở kiểm tra", False),
    32: ("Kiểm tra định kỳ", False),
    33: ("Kiểm tra đột xuất", False),
    34: ("Số vi phạm phát hiện", False),
    35: ("Tổng số xử phạt", False),
    36: ("Cảnh cáo", False),
    37: ("Tạm đình chỉ", False),
    38: ("Đình chỉ", False),
    39: ("Phạt tiền mặt", False),
    40: ("Số tiền phạt (triệu đồng)", False),
    41: ("IV. CÔNG TÁC XÂY DỰNG, THẨM DUYỆT, NGHIỆM THU PHƯƠNG ÁN", True),
    42: ("1. Phương án chữa cháy cơ sở (PC06)", True),
    43: ("Số PA được thẩm duyệt", False),
    44: ("Số PA được thực tập", False),
    45: ("2. Phương án chữa cháy phương tiện giao thông (PC07)", True),
    46: ("Số PA được thẩm duyệt", False),
    47: ("Số PA được thực tập", False),
    48: ("3. Phương án chữa cháy cơ quan cấp cao (PC08)", True),
    49: ("Số PA được thẩm duyệt", False),
    50: ("Số PA được thực tập", False),
    51: ("4. Phương án CNCH cơ quan cấp cao (PC09)", True),
    52: ("Số PA được thẩm duyệt", False),
    53: ("Số PA được thực tập", False),
    54: ("V. HUẤN LUYỆN NGHIỆP VỤ THƯỜNG XUYÊN", True),
    55: ("Tổng số CBCS tham gia", False),
    56: ("Chỉ huy phòng", False),
    57: ("Chỉ huy đội", False),
    58: ("Cán bộ tiểu đội", False),
    59: ("Chiến sỹ", False),
    60: ("Lái xe", False),
    61: ("Lái tàu", False),
}


def _safe_int(val: Any, default: int = 0) -> int:
    """Convert to int, return default if invalid."""
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert to float, return default if invalid."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _sum_detail_field(items: list[dict], field: str, default: float = 0.0) -> float:
    """Sum numeric field from detail items."""
    total = 0.0
    for item in items:
        val = item.get(field)
        total += _safe_float(val, 0.0)
    return total


def build_kv30_bang_thong_ke(master_data: dict, detail_items: dict, defaults: dict) -> list[dict]:
    """Build full STT 1-61 bang_thong_ke from BC NGÀY master + detail items.

    Args:
        master_data: Parsed BC NGÀY row with keys matching KV30_BC_NGAY_COLS
        detail_items: {"danh_sach_chay": [...], "danh_sach_cnch": [...], ...}
        defaults: {"stt_56_hl_chi_huy_phong": 0, ...} for operational values

    Returns:
        List of {"stt": str, "noi_dung": str, "ket_qua": number}
    """
    danh_sach_chay = detail_items.get("danh_sach_chay", [])
    danh_sach_cnch = detail_items.get("danh_sach_cnch", [])

    # Fire
    stt_02 = _safe_int(master_data.get("tong_so_vu_chay"))
    stt_03 = 0  # derived from danh_sach_chay.thiet_hai_nguoi if parseable
    stt_04 = 0
    stt_05 = 0
    stt_06 = _sum_detail_field(danh_sach_chay, "thiet_hai_tai_san")
    stt_07 = _sum_detail_field(danh_sach_chay, "tai_san_cuu")

    # Explosion
    stt_08 = 0
    stt_09 = 0
    stt_10 = 0
    stt_11 = 0
    stt_12 = 0
    stt_13 = 0

    # CNCH
    stt_14 = _safe_int(master_data.get("tong_so_vu_cnch"))
    stt_16 = _sum_detail_field(danh_sach_cnch, "so_nguoi_cuu")
    stt_17 = 0
    stt_15 = stt_16 + stt_17
    stt_18 = 0  # sum CNCH.thiet_hai_nguoi if numeric
    stt_19 = 0

    # Tuyên truyền
    stt_23 = _safe_int(master_data.get("tin_bai"))
    stt_24 = 0
    stt_25 = _safe_int(master_data.get("phong_su"))
    stt_27 = _safe_int(master_data.get("tuyen_truyen_lop"))
    stt_28 = _safe_int(master_data.get("tuyen_truyen_nguoi"))
    stt_29 = _safe_int(master_data.get("khuyen_cao_to_roi"))

    # Kiểm tra
    stt_32 = _safe_int(master_data.get("kiem_tra_dinh_ky_nhom_1")) + _safe_int(master_data.get("kiem_tra_dinh_ky_nhom_2"))
    stt_33 = _safe_int(master_data.get("kiem_tra_dot_xuat_nhom_1")) + _safe_int(master_data.get("kiem_tra_dot_xuat_nhom_2"))
    stt_31 = stt_32 + stt_33
    stt_34 = _safe_int(master_data.get("kien_nghi"))

    # Xử phạt
    stt_36 = 0
    stt_37 = 0
    stt_38 = _safe_int(master_data.get("dinh_chi"))
    stt_39 = _safe_int(master_data.get("xu_phat"))
    stt_35 = stt_36 + stt_37 + stt_38 + stt_39
    stt_40 = _safe_float(master_data.get("tien_phat"))

    # Phương án
    stt_43 = _safe_int(master_data.get("pa_pc06_xay_dung"))
    stt_44 = _safe_int(master_data.get("pa_pc06_thuc_tap"))
    stt_46 = _safe_int(master_data.get("pa_pc07_xay_dung"))
    stt_47 = _safe_int(master_data.get("pa_pc07_thuc_tap"))
    stt_49 = _safe_int(master_data.get("pa_pc08_xay_dung"))
    stt_50 = _safe_int(master_data.get("pa_pc08_thuc_tap"))
    stt_52 = _safe_int(master_data.get("pa_pc09_xay_dung"))
    stt_53 = _safe_int(master_data.get("pa_pc09_thuc_tap"))

    # Huấn luyện CBCS
    stt_56 = _safe_int(defaults.get("stt_56_hl_chi_huy_phong", 0))
    stt_57 = _safe_int(defaults.get("stt_57_hl_chi_huy_doi", 0))
    stt_58 = _safe_int(defaults.get("stt_58_hl_can_bo_tieu_doi", 0))
    stt_59 = _safe_int(defaults.get("stt_59_hl_chien_sy", 0))
    stt_60 = _safe_int(defaults.get("stt_60_hl_lai_xe", 0))
    stt_61 = _safe_int(defaults.get("stt_61_hl_lai_tau", 0))
    stt_55 = stt_56 + stt_57 + stt_58 + stt_59 + stt_60 + stt_61

    # Build full table
    stt_values = {
        2: stt_02, 3: stt_03, 4: stt_04, 5: stt_05, 6: stt_06, 7: stt_07,
        8: stt_08, 9: stt_09, 10: stt_10, 11: stt_11, 12: stt_12, 13: stt_13,
        14: stt_14, 15: stt_15, 16: stt_16, 17: stt_17, 18: stt_18, 19: stt_19,
        23: stt_23, 24: stt_24, 25: stt_25, 27: stt_27, 28: stt_28, 29: stt_29,
        31: stt_31, 32: stt_32, 33: stt_33, 34: stt_34, 35: stt_35, 36: stt_36,
        37: stt_37, 38: stt_38, 39: stt_39, 40: stt_40,
        43: stt_43, 44: stt_44, 46: stt_46, 47: stt_47, 49: stt_49, 50: stt_50,
        52: stt_52, 53: stt_53, 55: stt_55, 56: stt_56, 57: stt_57, 58: stt_58,
        59: stt_59, 60: stt_60, 61: stt_61,
    }

    rows = []
    for stt_num in range(1, 62):
        noi_dung, is_header = KV30_STT_DEFS[stt_num]
        ket_qua = 0 if is_header else stt_values.get(stt_num, 0)
        rows.append({"stt": str(stt_num), "noi_dung": noi_dung, "ket_qua": ket_qua})

    return rows


def build_kv30_word_context(output: dict, defaults: dict) -> dict:
    """Build Word template context from BlockExtractionOutput + defaults.

    Args:
        output: BlockExtractionOutput.model_dump() with header, bang_thong_ke, detail lists
        defaults: Operational defaults for quan_so, xe, etc.

    Returns:
        Flat dict with all Word template variables
    """
    header = output.get("header", {})
    bang_thong_ke = output.get("bang_thong_ke", [])

    # Extract STT values
    stt_map = {int(row["stt"]): row["ket_qua"] for row in bang_thong_ke if row.get("stt", "").isdigit()}

    ctx = {
        # Header
        "so_bao_cao": header.get("so_bao_cao", ""),
        "ngay_xuat": "",
        "thang_xuat": "",
        "nam_xuat": "",
        "ngay_bao_cao": header.get("ngay_bao_cao", ""),
        "thang_bao_cao": "",
        "thoi_gian_tu_den": header.get("thoi_gian_tu_den", ""),

        # Narrative totals
        "tong_so_vu_chay": stt_map.get(2, 0),
        "tong_so_vu_no": stt_map.get(8, 0),
        "tong_so_vu_cnch": stt_map.get(14, 0),
        "tong_chi_vien": output.get("phan_I_va_II_chi_tiet_nghiep_vu", {}).get("tong_chi_vien", 0),
        "tong_bao_cao": 0,
        "tong_cong_van": 0,
        "cong_tac_an_ninh": "",

        # Detail lists
        "danh_sach_chay": output.get("danh_sach_chay", []),
        "danh_sach_cnch": output.get("danh_sach_cnch", []),
        "danh_sach_chi_vien": output.get("danh_sach_chi_vien", []),
        "danh_sach_su_co": output.get("danh_sach_sclq", []),
        "danh_sach_cong_tac_khac": output.get("danh_sach_cong_tac_khac", []),
        "danh_sach_cong_van_tham_muu": output.get("danh_sach_cong_van_tham_muu", []),
        "danh_sach_phuong_tien_hu_hong": output.get("danh_sach_phuong_tien_hu_hong", []),

        # Operational defaults
        "tong_quan_so": defaults.get("tong_quan_so", 0),
        "quan_so_bien_che": defaults.get("quan_so_bien_che", 0),
        "quan_so_csnv": defaults.get("quan_so_csnv", 0),
        "quan_so_hdld": defaults.get("quan_so_hdld", 0),
        "quan_so_truc": defaults.get("quan_so_truc", 0),
        "truc_chi_huy": defaults.get("truc_chi_huy", ""),
        "truc_ban_chien_dau": defaults.get("truc_ban_chien_dau", ""),
        "xe_chi_huy": defaults.get("xe_chi_huy", 0),
        "xe_chua_chay": defaults.get("xe_chua_chay", 0),
        "xe_bon_nuoc": defaults.get("xe_bon_nuoc", 0),
        "xe_thang": defaults.get("xe_thang", 0),
        "xe_cho_quan": defaults.get("xe_cho_quan", 0),
        "xe_cho_phuong_tien": defaults.get("xe_cho_phuong_tien", 0),
        "tinh_trang_tru_cap_nuoc": defaults.get("tinh_trang_tru_cap_nuoc", ""),
    }

    # Add all STT variables with descriptive names
    ctx.update({
        "stt_02_tong_chay": stt_map.get(2, 0),
        "stt_03_chay_chet": stt_map.get(3, 0),
        "stt_04_chay_thuong": stt_map.get(4, 0),
        "stt_05_chay_cuu_nguoi": stt_map.get(5, 0),
        "stt_06_chay_thiet_hai": stt_map.get(6, 0),
        "stt_07_chay_cuu_tai_san": stt_map.get(7, 0),
        "stt_08_tong_no": stt_map.get(8, 0),
        "stt_09_no_chet": stt_map.get(9, 0),
        "stt_10_no_thuong": stt_map.get(10, 0),
        "stt_11_no_cuu_nguoi": stt_map.get(11, 0),
        "stt_12_no_thiet_hai": stt_map.get(12, 0),
        "stt_13_no_cuu_tai_san": stt_map.get(13, 0),
        "stt_14_tong_cnch": stt_map.get(14, 0),
        "stt_15_cnch_cuu_nguoi": stt_map.get(15, 0),
        "stt_16_cnch_truc_tiep": stt_map.get(16, 0),
        "stt_17_cnch_tu_thoat": stt_map.get(17, 0),
        "stt_18_cnch_thi_the": stt_map.get(18, 0),
        "stt_19_cnch_cuu_tai_san": stt_map.get(19, 0),
        "stt_23_tt_mxh_tin_bai": stt_map.get(23, 0),
        "stt_24_tt_mxh_hinh_anh": stt_map.get(24, 0),
        "stt_25_tt_mxh_video": stt_map.get(25, 0),
        "stt_27_tt_so_cuoc": stt_map.get(27, 0),
        "stt_28_tt_so_nguoi": stt_map.get(28, 0),
        "stt_29_tt_to_roi": stt_map.get(29, 0),
        "stt_31_kiem_tra_tong": stt_map.get(31, 0),
        "stt_32_kiem_tra_dinh_ky": stt_map.get(32, 0),
        "stt_33_kiem_tra_dot_xuat": stt_map.get(33, 0),
        "stt_34_vi_pham_phat_hien": stt_map.get(34, 0),
        "stt_35_xu_phat_tong": stt_map.get(35, 0),
        "stt_36_xu_phat_canh_cao": stt_map.get(36, 0),
        "stt_37_xu_phat_tam_dinh_chi": stt_map.get(37, 0),
        "stt_38_xu_phat_dinh_chi": stt_map.get(38, 0),
        "stt_39_xu_phat_tien_mat": stt_map.get(39, 0),
        "stt_40_xu_phat_so_tien": stt_map.get(40, 0),
        "stt_43_pa_co_so_duyet": stt_map.get(43, 0),
        "stt_44_pa_co_so_thuc_tap": stt_map.get(44, 0),
        "stt_46_pa_giao_thong_duyet": stt_map.get(46, 0),
        "stt_47_pa_giao_thong_thuc_tap": stt_map.get(47, 0),
        "stt_49_pa_cong_an_duyet": stt_map.get(49, 0),
        "stt_50_pa_cong_an_thuc_tap": stt_map.get(50, 0),
        "stt_52_pa_cnch_duyet": stt_map.get(52, 0),
        "stt_53_pa_cnch_thuc_tap": stt_map.get(53, 0),
        "stt_55_hl_tong_cbcs": stt_map.get(55, 0),
        "stt_56_hl_chi_huy_phong": stt_map.get(56, 0),
        "stt_57_hl_chi_huy_doi": stt_map.get(57, 0),
        "stt_58_hl_can_bo_tieu_doi": stt_map.get(58, 0),
        "stt_59_hl_chien_sy": stt_map.get(59, 0),
        "stt_60_hl_lai_xe": stt_map.get(60, 0),
        "stt_61_hl_lai_tau": stt_map.get(61, 0),
    })

    return ctx
