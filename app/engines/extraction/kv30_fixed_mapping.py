"""Hardcoded fixed-column mapping for KV30 daily report Excel/Google Sheets.

This module is the SOLE source of truth for KV30 column layout.
No YAML schema loading, no alias matching, no SheetExtractionPipeline.

KV30 workbook structure:
  BC NGÀY:
    row 0 = merged group headers (visual, not data)
    row 1 = data row (no header row needed for fixed mapping)
    data_start_row = 1
  Detail sheets (CNCH, VỤ CHÁY THỐNG KÊ, CHI VIỆN, SCLQ):
    row 0 = title
    row 1 = column headers (visual, not used for mapping)
    row 2+ = data
    data_start_row = 2
"""

from __future__ import annotations

import re
from typing import Any

from app.engines.extraction.schemas import (
    BlockExtractionOutput,
    BlockHeader,
    BlockNghiepVu,
    ChiTieu,
    CNCHItem,
    ChiVienItem,
    SCLQItem,
    TuyenTruyenOnline,
    VuChayItem,
)

# ─────────────────────────────────────────────────────────────────
# Workbook-level helpers
# ─────────────────────────────────────────────────────────────────


def is_kv30_worksheet(worksheet: str) -> bool:
    return worksheet in {
        "BC NGÀY",
        "BC NGAY",
        "CNCH",
        "VỤ CHÁY THỐNG KÊ",
        "VU CHAY THONG KE",
        "CHI VIỆN",
        "CHI VIEN",
        "SCLQ ĐẾN PCCC&CNCH",
        "SCLQ DEN PCCC&CNCH",
    }


def is_kv30_config(cfg: dict) -> bool:
    schema = cfg.get("schema_path", "")
    return "kv30" in schema.lower()


def get_kv30_data_start_row(worksheet: str, cfg: dict | None = None) -> int:
    if worksheet in {"BC NGÀY", "BC NGAY"}:
        return 1  # data starts at row 1 (index 1)
    return 2  # detail sheets: title at 0, header at 1, data at 2


# ─────────────────────────────────────────────────────────────────
# Cell helpers
# ─────────────────────────────────────────────────────────────────


def _cell(row: list[Any], idx: int, default: Any = None) -> Any:
    if idx < 0:
        return default
    if idx >= len(row):
        return default
    val = row[idx]
    if val is None:
        return default
    return val


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return default
        return int(value)
    s = str(value).strip().replace(",", "").replace(".", "")
    if not s or s == "-":
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return default
        return float(value)
    s = str(value).strip().replace(",", "").replace(".", "")
    if not s or s == "-":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (int, float)) and (value != value or value == 0):
        return True
    return False


def _is_row_blank(row: list[Any]) -> bool:
    if not row:
        return True
    return all(_is_blank(v) for v in row)


# ─────────────────────────────────────────────────────────────────
# Date / time helpers (cutoff 07:30)
# ─────────────────────────────────────────────────────────────────


_HOUR_MINUTE_RE = re.compile(
    r"(\d{1,2})\s*(?:giờ?|gio)\s*(\d{1,2})?\s*(?:phút?|phut)?\s*(?:ngày|ngay|$|\s)",
    re.IGNORECASE,
)


def _parse_gi_phut(text: str) -> tuple[int, int]:
    """Return (hour, minute) from normalized or Vietnamese time string.

    Handles:
    - "16:33"
    - "20/03/2026 16:33"
    - "16:33 20/03/2026"
    - "16 giờ 33 phút"
    - "16 gio 33 phut"
    - "16h33"
    """
    s = str(text).strip()

    # Match HH:MM anywhere in string
    m = re.search(r"\b(\d{1,2})\s*:\s*(\d{2})\b", s)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h, mm

    # Match Vietnamese time (with or without diacritics)
    m = re.search(r"\b(\d{1,2})\s*(?:giờ|gio|h)\s*(\d{1,2})?\s*(?:phút|phut)?\b", s, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else 0
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h, mm

    return -1, -1


def _is_after_0730(time_str: str) -> bool:
    """Return True if time >= 07:30."""
    if not time_str:
        return False

    s = str(time_str).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
    else:
        h, mm = _parse_gi_phut(s)

    if h < 0:
        return False
    return h > 7 or (h == 7 and mm >= 30)


def _date_plus_one(ddmm: str) -> str:
    """Add 1 day to DD/MM date string (ignoring year)."""
    m = re.match(r"(\d{1,2})/(\d{1,2})", ddmm.strip())
    if not m:
        return ddmm
    day, month = int(m.group(1)), int(m.group(2))
    days_in_month = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
                     7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    day += 1
    if day > days_in_month.get(month, 31):
        day = 1
        month += 1
        if month > 12:
            month = 1
    return f"{day:02d}/{month:02d}"


def _compute_report_date(event_date: str, event_time: str) -> str:
    """Apply 07:30 cutoff to event date/time.

    - event_date: DD/MM/YYYY or DD/MM
    - event_time: Vietnamese time string like '17 giờ 20 phút' or ''

    Returns DD/MM report key.
    """
    date_part = event_date[:10] if len(event_date) >= 10 else event_date
    if len(date_part) < 6:
        return date_part
    ddmm = date_part[:5]  # "DD/MM"
    if event_time and _is_after_0730(event_time):
        return _date_plus_one(ddmm)
    return ddmm


# ─────────────────────────────────────────────────────────────────
# KV30 BC NGÀY fixed columns
# ─────────────────────────────────────────────────────────────────
#
# Index  Name
# 0      ngay_bao_cao_day
# 1      ngay_bao_cao_month
# 2      tong_so_vu_chay
# 3      tong_sclq
# 4      tong_chi_vien
# 5      tong_so_vu_cnch
# 6      kiem_tra_dinh_ky_n1
# 7      kiem_tra_dinh_ky_n2
# 8      kiem_tra_dot_xuat_n1
# 9      kiem_tra_dot_xuat_n2
# 10     huong_dan
# 11     kien_nghi
# 12     xu_phat
# 13     tien_phat
# 14     tam_dinh_chi
# 15     phuc_hoi
# 16     tong_tin_bai      (TUYÊN TRUYỀN PCCC TIN BÀI)
# 17     tong_hinh_anh      (PHÓNG SỰ → counted as tong_hinh_anh)
# 18     tuyen_truyen_lop
# 19     tuyen_truyen_nguoi
# 20     khuyen_cao
# 21     huan_luyen_lop
# 22     huan_luyen_nguoi
# 23     tong_tuyen_truyen_huan_luyen_lop  (TỔNG)
# 24     tong_tuyen_truyen_huan_luyen_nguoi (TỔNG)
# 25     pa_pc06_xd
# 26     pa_pc06_tt
# 27     pa_pc08_xd
# 28     pa_pc08_tt
# 29     pa_pc09_xd
# 30     pa_pc09_tt
# 31     pa_pc07_xd
# 32     pa_pc07_tt
# 33     ghi_chu

_BC_NGAY_COL = {
    "day": 0,
    "month": 1,
    "tong_so_vu_chay": 2,
    "tong_sclq": 3,
    "tong_chi_vien": 4,
    "tong_so_vu_cnch": 5,
    "kiem_tra_dinh_ky_n1": 6,
    "kiem_tra_dinh_ky_n2": 7,
    "kiem_tra_dot_xuat_n1": 8,
    "kiem_tra_dot_xuat_n2": 9,
    "huong_dan": 10,
    "kien_nghi": 11,
    "xu_phat": 12,
    "tien_phat": 13,
    "tam_dinh_chi": 14,
    "phuc_hoi": 15,
    "tong_tin_bai": 16,
    "tong_hinh_anh": 17,
    "tuyen_truyen_lop": 18,
    "tuyen_truyen_nguoi": 19,
    "khuyen_cao": 20,
    "huan_luyen_lop": 21,
    "huan_luyen_nguoi": 22,
    "tong_tuyen_truyen_huan_luyen_lop": 23,
    "tong_tuyen_truyen_huan_luyen_nguoi": 24,
    "pa_pc06_xd": 25,
    "pa_pc06_tt": 26,
    "pa_pc08_xd": 27,
    "pa_pc08_tt": 28,
    "pa_pc09_xd": 29,
    "pa_pc09_tt": 30,
    "pa_pc07_xd": 31,
    "pa_pc07_tt": 32,
    "ghi_chu": 33,
}

_YEAR = 2026


# ─────────────────────────────────────────────────────────────────
# bang_thong_ke STT → (noi_dung, field_name)
# ─────────────────────────────────────────────────────────────────

KV30_BTK_STT_MAP: dict[str, tuple[str, str | None]] = {
    # Numeric sections
    "2":  ("Tổng số vụ cháy", "tong_so_vu_chay"),
    "3":  ("Tổng số SCLQ đến PCCC&CNCH", "tong_sclq"),
    "4":  ("Tổng số vụ CNCH", "tong_so_vu_cnch"),
    "5":  ("Tổng số vụ chi viện", "tong_chi_vien"),
    "6":  ("Kiểm tra định kỳ nhóm I", "kiem_tra_dinh_ky_n1"),
    "7":  ("Kiểm tra định kỳ nhóm II", "kiem_tra_dinh_ky_n2"),
    "8":  ("Kiểm tra đột xuất nhóm I", "kiem_tra_dot_xuat_n1"),
    "9":  ("Kiểm tra đột xuất nhóm II", "kiem_tra_dot_xuat_n2"),
    "10": ("Hướng dẫn", "huong_dan"),
    "11": ("Kiến nghị", "kien_nghi"),
    "12": ("Xử phạt", "xu_phat"),
    "13": ("Tiền phạt (triệu đồng)", "tien_phat"),
    "14": ("Đình chỉ", "tam_dinh_chi"),
    "15": ("Phục hồi", "phuc_hoi"),
    # STT 16–21 not in KV30 BC NGÀY fixture
    "22": ("Tin bài đăng tải", "tong_tin_bai"),
    "23": ("Hình ảnh đăng tải", "tong_hinh_anh"),
    "24": ("Số lượt cài app 114", None),  # no column in fixture
    "25": ("Số lớp tuyên truyền", "tuyen_truyen_lop"),
    "26": ("Số người tham dự tuyên truyền", "tuyen_truyen_nguoi"),
    "27": ("Số khuyến cáo, tờ rơi phát", "khuyen_cao"),
    "28": ("Số lớp huấn luyện PCCC", "huan_luyen_lop"),
    "29": ("Số người tham dự huấn luyện", "huan_luyen_nguoi"),
    "31": ("PACC&CNCH cơ sở theo mẫu PC06 (Số PA xây dựng)", "pa_pc06_xd"),
    "32": ("PACC&CNCH cơ sở theo mẫu PC06 (Số PA được thực tập)", "pa_pc06_tt"),
    "33": ("PACC&CNCH cơ quan, cấp cao theo mẫu PC08 (Số PA xây dựng)", "pa_pc08_xd"),
    "34": ("PACC&CNCH cơ quan, cấp cao theo mẫu PC08 (Số PA được thực tập)", "pa_pc08_tt"),
    "35": ("PA CNCH cơ quan, cấp cao theo mẫu PC09 (Số PA xây dựng)", "pa_pc09_xd"),
    "39": ("PA CNCH cơ quan, cấp cao theo mẫu PC09 (Số PA được thực tập)", "pa_pc09_tt"),
    "40": ("PACC&CNCH phương tiện giao thông theo mẫu PC07 (Số PA xây dựng)", "pa_pc07_xd"),
    "43": ("PACC&CNCH phương tiện giao thông theo mẫu PC07 (Số PA được thực tập)", "pa_pc07_tt"),
    "44": ("Số PA PCCC tổng hợp xây dựng", "pa_pc06_xd"),
    "49": ("Ghi chú", "ghi_chu"),
}


def _col(flat: list[Any], key: str) -> Any:
    idx = _BC_NGAY_COL[key]
    return _cell(flat, idx, 0 if key not in ("ghi_chu",) else "")


def build_kv30_bang_thong_ke(flat: list[Any]) -> list[ChiTieu]:
    """Build bang_thong_ke from fixed-column flat BC NGÀY row."""
    items: list[ChiTieu] = []
    seen_stt: set[str] = set()

    for stt_str, (noi_dung, field_name) in KV30_BTK_STT_MAP.items():
        # Prevent duplicate STT labels
        if stt_str in seen_stt:
            continue
        seen_stt.add(stt_str)

        if field_name:
            val = _col(flat, field_name)
            if isinstance(val, str):
                ket_qua = _to_int(val, 0)
            else:
                ket_qua = _to_int(val, 0)
        else:
            ket_qua = 0
        items.append(ChiTieu(stt=stt_str, noi_dung=noi_dung, ket_qua=ket_qua))

    return items


# ─────────────────────────────────────────────────────────────────
# map_kv30_master_row
# ─────────────────────────────────────────────────────────────────


def map_kv30_master_row(row: list[Any], year: int = _YEAR) -> BlockExtractionOutput | None:
    """Map BC NGÀY data row (fixed columns) → BlockExtractionOutput.

    Returns None if the row is blank or missing day/month.
    """
    if _is_row_blank(row):
        return None

    day = _to_int(_cell(row, _BC_NGAY_COL["day"]), 0)
    month = _to_int(_cell(row, _BC_NGAY_COL["month"]), 0)
    if day == 0 or month == 0:
        return None

    ngay_bao_cao = f"{day:02d}/{month:02d}/{year}"

    # ── BlockHeader ──────────────────────────────────────────────
    header = BlockHeader(
        so_bao_cao="",
        ngay_bao_cao=ngay_bao_cao,
        thoi_gian_tu_den="",
        don_vi_bao_cao="",
    )

    # ── BlockNghiepVu ───────────────────────────────────────────
    nghiep_vu = BlockNghiepVu(
        tong_so_vu_chay=_to_int(_col(row, "tong_so_vu_chay")),
        tong_so_vu_no=0,
        tong_sclq=_to_int(_col(row, "tong_sclq")),
        tong_so_vu_cnch=_to_int(_col(row, "tong_so_vu_cnch")),
        chi_tiet_cnch="",
        quan_so_truc=0,
        tong_chi_vien=_to_int(_col(row, "tong_chi_vien")),
        tong_cong_van=0,
        tong_bao_cao=0,
        tong_ke_hoach=0,
        cong_tac_an_ninh="",
        tong_xe_hu_hong=0,
        tong_tin_bai=_to_int(_col(row, "tong_tin_bai")),
        tong_hinh_anh=_to_int(_col(row, "tong_hinh_anh")),
        so_lan_cai_app_114=0,
    )

    # ── TuyenTruyenOnline ───────────────────────────────────────
    tuyen_truyen = TuyenTruyenOnline(
        so_tin_bai=_to_int(_col(row, "tong_tin_bai")),
        so_hinh_anh=_to_int(_col(row, "tong_hinh_anh")),
        cai_app_114=0,
    )

    # ── bang_thong_ke ────────────────────────────────────────────
    btk = build_kv30_bang_thong_ke(row)

    return BlockExtractionOutput(
        header=header,
        phan_I_va_II_chi_tiet_nghiep_vu=nghiep_vu,
        bang_thong_ke=btk,
        danh_sach_cnch=[],
        danh_sach_phuong_tien_hu_hong=[],
        danh_sach_cong_van_tham_muu=[],
        danh_sach_cong_tac_khac=[],
        danh_sach_chi_vien=[],
        danh_sach_chay=[],
        danh_sach_sclq=[],
        tuyen_truyen_online=tuyen_truyen,
    )


# ─────────────────────────────────────────────────────────────────
# KV30 detail columns
# ─────────────────────────────────────────────────────────────────

# CNCH columns (0-based index from column headers row):
# 0=STT, 1=Loại hình CNCH, 2=Ngày xảy ra sự cố, 3=Thời gian đến,
# 4=Địa điểm, 5=Địa chỉ, 6=Chỉ huy CNCH, 7=Thiệt hại về người, 8=Số người cứu được
_CNCH_COL = {"stt": 0, "loai_hinh": 1, "ngay": 2, "thoi_gian": 3,
             "dia_diem": 4, "dia_chi": 5, "chi_huy": 6, "thiet_hai": 7, "so_nguoi_cuu": 8}


def _normalize_time(value: Any) -> str | None:
    """Normalize various time representations to HH:MM or pass through.

    Handles:
    - None / "": return None
    - datetime.time / datetime.datetime: return "HH:MM"
    - "16:33" / "6:33": return "16:33" / "06:33"
    - "16 giờ 33 phút" / "03 giờ 24 ": return "16:33" / "03:24"
    - "21 giờ 30 phút": return "21:30"
    - "05 giờ 40 phút": return "05:40"
    - "16 gio 33 phut" / "03 gio 24 ": return "16:33" / "03:24"
    - "21 gio 30 phut": return "21:30"
    - "05 gio 40 phut": return "05:40"
    - "06h15" / "06 h 15": return "06:15"
    - Invalid strings: return as-is (let Pydantic catch it)
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # Already HH:MM
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"

    # Vietnamese with diacritics: "16 giờ 33 phút" or "03 giờ 24 "
    m = re.match(r"(\d{1,2})\s*giờ?\s*(\d{1,2})?\s*phút?\s*(?:ngày|$|\s)", s, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else 0
        return f"{h:02d}:{mm:02d}"

    # Vietnamese WITHOUT diacritics: "16 gio 33 phut" or "03 gio 24 "
    m = re.match(r"(\d{1,2})\s*gio\s*(\d{1,2})?\s*phut?\s*(?:ngay|$|\s)", s, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else 0
        return f"{h:02d}:{mm:02d}"

    # Vietnamese: "06h15" or "06 h 15"
    m = re.match(r"(\d{1,2})\s*[hH]\s*(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"

    return s


def _combine_kv30_date_time(date_str: Any, time_str: Any) -> str | None:
    """Combine date and time into canonical string.

    - date_str: '20/03/2026' or '20/03' or ''
    - time_str: '16:33' or '16 giờ 33 phút' or None/''
    Returns:
    - '20/03/2026 16:33' if both present
    - '20/03/2026' if only date
    - '16:33' if only time (fallback)
    - None if nothing valid
    """
    d = _to_text(date_str)
    t = _normalize_time(time_str)

    # Normalize date to dd/mm/yyyy
    date_part = ""
    if d and d.strip():
        m = re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{4})?)?", d.strip())
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else 2026
            date_part = f"{day:02d}/{month:02d}/{year}"
        else:
            date_part = d.strip()

    if date_part and t:
        return f"{date_part} {t}"
    if date_part:
        return date_part
    if t:
        return t
    return None


def map_kv30_cnch_row(row: list[Any]) -> CNCHItem | None:
    """Map CNCH data row (fixed columns) → CNCHItem or None if blank/no date."""
    if _is_row_blank(row):
        return None
    ngay = _to_text(_cell(row, _CNCH_COL["ngay"]))
    if not ngay.strip():
        return None
    payload = {
        "stt": _to_int(_cell(row, _CNCH_COL["stt"])),
        "ngay_xay_ra": ngay,
        "thoi_gian": _combine_kv30_date_time(_cell(row, _CNCH_COL["ngay"]), _cell(row, _CNCH_COL["thoi_gian"])),
        "dia_diem": _to_text(_cell(row, _CNCH_COL["dia_diem"])),
        "noi_dung_tin_bao": _to_text(_cell(row, _CNCH_COL["loai_hinh"])),
        "luc_luong_tham_gia": "",
        "ket_qua_xu_ly": "",
        "thiet_hai": _to_text(_cell(row, _CNCH_COL["thiet_hai"])),
        "thong_tin_nan_nhan": "",
        "chi_huy": _to_text(_cell(row, _CNCH_COL["chi_huy"])),
        "so_nguoi_cuu": _to_int(_cell(row, _CNCH_COL["so_nguoi_cuu"])),
        "mo_ta": "",
    }
    return CNCHItem(**payload)



# CHI VIỆN columns:
# 0=STT, 1=VỤ CHÁY NGÀY, 2=ĐỊA ĐIỂM, 3=KHU VỰC QUẢN LÝ,
# 4=SỐ LƯỢNG XE, 5=THỜI GIAN ĐI, 6=THỜI GIAN VỀ,
# 7=CHỈ HUY CHỮA CHÁY, 8=GHI CHÚ
_CV_COL = {"stt": 0, "ngay": 1, "dia_diem": 2, "khu_vuc": 3,
           "so_xe": 4, "thoi_gian_di": 5, "thoi_gian_ve": 6,
           "chi_huy": 7, "ghi_chu": 8}


def map_kv30_chi_vien_row(row: list[Any]) -> ChiVienItem | None:
    """Map CHI VIỆN data row (fixed columns) → ChiVienItem or None if blank/no date."""
    if _is_row_blank(row):
        return None
    ngay = _to_text(_cell(row, _CV_COL["ngay"]))
    if not ngay.strip():
        return None
    return ChiVienItem(
        stt=_to_int(_cell(row, _CV_COL["stt"])),
        ngay=ngay,
        dia_diem=_to_text(_cell(row, _CV_COL["dia_diem"])),
        khu_vuc_quan_ly=_to_text(_cell(row, _CV_COL["khu_vuc"])),
        so_luong_xe=_to_int(_cell(row, _CV_COL["so_xe"])),
        thoi_gian_di=_normalize_time(_cell(row, _CV_COL["thoi_gian_di"])),
        thoi_gian_ve=_normalize_time(_cell(row, _CV_COL["thoi_gian_ve"])),
        chi_huy=_to_text(_cell(row, _CV_COL["chi_huy"])),
        chi_huy_chua_chay=_to_text(_cell(row, _CV_COL["chi_huy"])),
        ghi_chu=_to_text(_cell(row, _CV_COL["ghi_chu"])),
    )


# VỤ CHÁY THỐNG KÊ columns:
# 0=STT, 1=NGÀY XẢY RA, 2=VỤ CHÁY (tên), 3=THỜI GIAN,
# 4=ĐỊA ĐIỂM, 5=PHÂN LOẠI, 6=NGUYÊN NHÂN, 7=THIỆT HẠI VỀ NGƯỜI,
# 8=THIỆT HẠI TÀI SẢN, 9=TÀI SẢN CỨU CHỮA,
# 10=THỜI GIAN TỚI, 11=THỜI GIAN KHỐNG CHẾ, 12=THỜI GIAN DẬP TẮT,
# 13=SỐ LƯỢNG XE, 14=CHỈ HUY, 15=GHI CHÚ
_VC_COL = {"stt": 0, "ngay": 1, "ten_vu_chay": 2, "thoi_gian": 3,
           "dia_diem": 4, "phan_loai": 5, "nguyen_nhan": 6,
           "thiet_hai_nguoi": 7, "thiet_hai_tai_san": 8, "tai_san_cuu": 9,
           "thoi_gian_toi": 10, "thoi_gian_khong_che": 11, "thoi_gian_dap_tat": 12,
           "so_xe": 13, "chi_huy": 14, "ghi_chu": 15}


def map_kv30_vu_chay_row(row: list[Any]) -> VuChayItem | None:
    """Map VỤ CHÁY data row (fixed columns) → VuChayItem or None if blank/no date."""
    if _is_row_blank(row):
        return None
    ngay = _to_text(_cell(row, _VC_COL["ngay"]))
    if not ngay.strip():
        return None
    return VuChayItem(
        stt=_to_int(_cell(row, _VC_COL["stt"])),
        ngay_xay_ra=ngay,
        thoi_gian=_normalize_time(_cell(row, _VC_COL["thoi_gian"])),
        ten_vu_chay=_to_text(_cell(row, _VC_COL["ten_vu_chay"])),
        dia_diem=_to_text(_cell(row, _VC_COL["dia_diem"])),
        nguyen_nhan=_to_text(_cell(row, _VC_COL["nguyen_nhan"])),
        phan_loai=_to_text(_cell(row, _VC_COL["phan_loai"])),
        thiet_hai_nguoi=_to_text(_cell(row, _VC_COL["thiet_hai_nguoi"])),
        thiet_hai_tai_san=_to_text(_cell(row, _VC_COL["thiet_hai_tai_san"])),
        tai_san_cuu=_to_text(_cell(row, _VC_COL["tai_san_cuu"])),
        thoi_gian_toi=_normalize_time(_cell(row, _VC_COL["thoi_gian_toi"])),
        thoi_gian_khong_che=_normalize_time(_cell(row, _VC_COL["thoi_gian_khong_che"])),
        thoi_gian_dap_tat=_normalize_time(_cell(row, _VC_COL["thoi_gian_dap_tat"])),
        so_luong_xe=_to_int(_cell(row, _VC_COL["so_xe"])),
        chi_huy=_to_text(_cell(row, _VC_COL["chi_huy"])),
        ghi_chu=_to_text(_cell(row, _VC_COL["ghi_chu"])),
    )


# SCLQ ĐẾN PCCC&CNCH columns:
# 0=STT, 1=NGÀY, 2=ĐỊA ĐIỂM, 3=NGUYÊN NHÂN,
# 4=THIỆT HẠI, 5=CHỈ HUY, 6=GHI CHÚ
_SCLQ_COL = {"stt": 0, "ngay": 1, "dia_diem": 2,
             "nguyen_nhan": 3, "thiet_hai": 4, "chi_huy": 5, "ghi_chu": 6}


def map_kv30_sclq_row(
    row: list[Any],
    previous_context: dict | None,
) -> tuple[SCLQItem | None, dict]:
    """Map SCLQ data row (fixed columns) → (SCLQItem or None, updated context).

    Continuation rows (blank STT and date) inherit from previous_context.
    Returns (item, updated_context).
    """
    if _is_row_blank(row):
        return None, previous_context or {}

    stt_raw = _cell(row, _SCLQ_COL["stt"])
    ngay_raw = _cell(row, _SCLQ_COL["ngay"])

    stt = _to_int(stt_raw)
    ngay = _to_text(ngay_raw)

    if stt == 0 and not ngay.strip():
        # Continuation row — inherit from previous_context
        ctx = previous_context or {}
        if not ctx:
            return None, {}
        item = SCLQItem(
            stt=ctx.get("stt", 0),
            ngay=ctx.get("ngay", ""),
            dia_diem=ctx.get("dia_diem", ""),
            nguyen_nhan=_to_text(_cell(row, _SCLQ_COL["nguyen_nhan"])),
            thiet_hai=_to_text(_cell(row, _SCLQ_COL["thiet_hai"])),
            chi_huy=ctx.get("chi_huy", ""),
            ghi_chu=_to_text(_cell(row, _SCLQ_COL["ghi_chu"])),
        )
        return item, ctx

    # Normal row
    item = SCLQItem(
        stt=stt,
        ngay=ngay,
        dia_diem=_to_text(_cell(row, _SCLQ_COL["dia_diem"])),
        nguyen_nhan=_to_text(_cell(row, _SCLQ_COL["nguyen_nhan"])),
        thiet_hai=_to_text(_cell(row, _SCLQ_COL["thiet_hai"])),
        chi_huy=_to_text(_cell(row, _SCLQ_COL["chi_huy"])),
        ghi_chu=_to_text(_cell(row, _SCLQ_COL["ghi_chu"])),
    )
    ctx = {
        "stt": stt,
        "ngay": ngay,
        "dia_diem": _to_text(_cell(row, _SCLQ_COL["dia_diem"])),
        "chi_huy": _to_text(_cell(row, _SCLQ_COL["chi_huy"])),
    }
    return item, ctx


# ─────────────────────────────────────────────────────────────────
# map_kv30_detail_row — factory dispatcher
# ─────────────────────────────────────────────────────────────────


def map_kv30_detail_row(
    worksheet: str,
    row: list[Any],
) -> tuple[str, Any] | None:
    """Map a KV30 detail sheet row → (target_section, Pydantic item).

    Returns None if the row is blank or has no date.
    """
    if worksheet in {"CNCH"}:
        item = map_kv30_cnch_row(row)
        if item is None:
            return None
        return "danh_sach_cnch", item

    if worksheet in {"CHI VIỆN", "CHI VIEN"}:
        item = map_kv30_chi_vien_row(row)
        if item is None:
            return None
        return "danh_sach_chi_vien", item

    if worksheet in {"VỤ CHÁY THỐNG KÊ", "VU CHAY THONG KE"}:
        item = map_kv30_vu_chay_row(row)
        if item is None:
            return None
        return "danh_sach_chay", item

    if worksheet in {"SCLQ ĐẾN PCCC&CNCH", "SCLQ DEN PCCC&CNCH"}:
        item, _ = map_kv30_sclq_row(row, None)
        if item is None:
            return None
        return "danh_sach_sclq", item

    return None


# ─────────────────────────────────────────────────────────────────
# Date key for detail items
# ─────────────────────────────────────────────────────────────────


def get_kv30_item_report_date_key(worksheet: str, item: Any) -> str | None:
    """Compute the report date key (DD/MM) for a detail item.

    Uses 07:30 cutoff: event_date + 1 day if event_time >= 07:30.
    Returns None if no date available.
    """
    if isinstance(item, CNCHItem):
        return _compute_report_date(item.ngay_xay_ra, item.thoi_gian)

    if isinstance(item, ChiVienItem):
        # CHI VIỆN: use thoi_gian_di as event time
        return _compute_report_date(item.ngay, item.thoi_gian_di)

    if isinstance(item, VuChayItem):
        return _compute_report_date(item.ngay_xay_ra, item.thoi_gian)

    if isinstance(item, SCLQItem):
        # SCLQ has no time → report date = event date
        return _compute_report_date(item.ngay, "")

    return None


# ─────────────────────────────────────────────────────────────────
# KV30 date row extraction (for build_all_by_date grouping)
# ─────────────────────────────────────────────────────────────────


def kv30_extract_master_date_key(row: list[Any]) -> str | None:
    """Extract DD/MM date key from BC NGÀY row.

    Returns None if row is blank or missing day/month.
    """
    if _is_row_blank(row):
        return None
    day = _to_int(_cell(row, _BC_NGAY_COL["day"]), 0)
    month = _to_int(_cell(row, _BC_NGAY_COL["month"]), 0)
    if day == 0 or month == 0:
        return None
    return f"{day:02d}/{month:02d}"
