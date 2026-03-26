"""Pydantic schema for hybrid incident extraction output."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

_DATE_DDMMYYYY = "%d/%m/%Y"


class CNCHItem(BaseModel):
    """Single CNCH incident entry."""

    model_config = ConfigDict(extra="forbid")

    stt: int = Field(default=0, strict=True)
    ngay_xay_ra: str = Field(default="")
    thoi_gian: str = Field(default="")
    mo_ta: str = Field(default="")
    dia_diem: str = Field(default="")

    @model_validator(mode="after")
    def validate_time_format(self) -> "CNCHItem":
        if not self.thoi_gian:
            return self

        value = self.thoi_gian.strip()

        # Normalize common Vietnamese short time format from LLM, e.g. "07h30" -> "07:30".
        hm_match = re.match(r"^(\d{1,2})\s*[hH]\s*(\d{2})$", value)
        if hm_match:
            hh = hm_match.group(1).zfill(2)
            mm = hm_match.group(2)
            value = f"{hh}:{mm}"
            self.thoi_gian = value

        patterns = [
            r"^\d{2}/\d{2}/\d{4}$",
            r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$",
            r"^\d{2}:\d{2}\s+\d{2}/\d{2}/\d{4}$",
            r"^\d{2}:\d{2}$",
            r"^\d{1,2}\s*giờ\s*\d{1,2}\s*phút\s*ngày\s*\d{2}/\d{2}/\d{4}$",
        ]

        if not any(re.match(pattern, value, flags=re.IGNORECASE) for pattern in patterns):
            raise ValueError(
                "thoi_gian không đúng định dạng nghiệp vụ (dd/mm/yyyy, dd/mm/yyyy HH:MM, HH:MM dd/mm/yyyy, hoặc 'HH giờ MM phút ngày dd/mm/yyyy')"
            )
        return self


class HybridExtractionOutput(BaseModel):
    """Structured output constrained by instructor + Pydantic."""

    model_config = ConfigDict(extra="forbid")

    ngay_bao_cao: str = Field(default="")
    tu_ngay: str = Field(default="")
    den_ngay: str = Field(default="")
    tong_quan_su_co: str = Field(default="")
    stt_14_tong_cnch: int = Field(default=0, ge=0, strict=True)
    tong_xe_hu_hong: int = Field(default=0, ge=0, strict=True)
    danh_sach_cnch: list[CNCHItem] = Field(default_factory=list)
    danh_sach_phuong_tien_hu_hong: list[str] = Field(default_factory=list)


class LLMVanXuoiOutput(BaseModel):
    """Mini schema for prose-only extraction in Stage 3."""

    model_config = ConfigDict(extra="forbid")

    ngay_bao_cao: str | None = Field(
        default=None,
        description="Ngày báo cáo (dd/mm/yyyy) nếu có trong văn bản",
    )
    tu_ngay: str | None = Field(
        default=None,
        description="Mốc thời gian bắt đầu kỳ báo cáo (dd/mm/yyyy)",
    )
    den_ngay: str | None = Field(
        default=None,
        description="Mốc thời gian kết thúc kỳ báo cáo (dd/mm/yyyy)",
    )
    tong_quan_su_co: str | None = Field(
        default=None,
        description="Tóm tắt diễn biến sự cố trong phần văn xuôi",
    )
    danh_sach_cnch: list[CNCHItem] | None = Field(
        default=None,
        description="Danh sách vụ CNCH trích xuất từ phần văn xuôi",
    )
    danh_sach_phuong_tien_hu_hong: list[str] | None = Field(
        default=None,
        description="Danh sách phương tiện hư hỏng nêu trong phần văn xuôi",
    )


class BlockHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    so_bao_cao: str = Field(default="")
    ngay_bao_cao: str = Field(default="")
    thoi_gian_tu_den: str = Field(default="")
    don_vi_bao_cao: str = Field(default="")


class BlockNghiepVu(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tong_so_vu_chay: int = Field(default=0)
    tong_so_vu_no: int = Field(default=0)
    tong_so_vu_cnch: int = Field(default=0)
    chi_tiet_cnch: str = Field(default="")
    quan_so_truc: int = Field(default=0)


class ChiTieu(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stt: str = Field(description="Số thứ tự, ví dụ: 2, 14, 31, 55")
    noi_dung: str = Field(description="Tên chỉ tiêu thống kê")
    ket_qua: int = Field(default=0)


class BlockBangThongKe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    danh_sach_chi_tieu: list[ChiTieu] = Field(
        default_factory=list,
        description="Danh sách vét cạn tất cả các dòng có chứa số liệu thống kê trong bảng",
    )


class BlockExtractionOutput(BaseModel):
    header: BlockHeader
    phan_I_va_II_chi_tiet_nghiep_vu: BlockNghiepVu
    bang_thong_ke: list[ChiTieu]
