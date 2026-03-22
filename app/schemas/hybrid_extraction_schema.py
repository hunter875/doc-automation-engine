"""Pydantic schema for hybrid incident extraction output."""

from __future__ import annotations

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
        patterns = [
            r"^\d{2}/\d{2}/\d{4}$",
            r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$",
            r"^\d{2}:\d{2}\s+\d{2}/\d{2}/\d{4}$",
            r"^\d{1,2}\s*giờ\s*\d{1,2}\s*phút\s*ngày\s*\d{2}/\d{2}/\d{4}$",
        ]
        import re

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
    """Header block extracted from report prologue."""

    so_bao_cao: str = Field(default="", description="Số của báo cáo, ví dụ: 180/BC-KV30")
    ngay_bao_cao: str = Field(default="", description="Ngày lập báo cáo, format dd/mm/yyyy")


class BlockPhanI(BaseModel):
    """Narrative block for section I."""

    tinh_hinh_chay_no: str = Field(default="", description="Tóm tắt tình hình cháy nổ")
    so_vu_cnch: int = Field(default=0, ge=0, strict=True, description="Tổng số vụ cứu nạn cứu hộ")


class BlockBangThongKe(BaseModel):
    """Statistic table block extracted from report."""

    tong_so_vu_chay: int = Field(default=0, ge=0, strict=True)
    so_nguoi_chet: int = Field(default=0, ge=0, strict=True)
    tai_san_thiet_hai: int = Field(default=0, ge=0, strict=True)
    tong_so_vu_cnch: int = Field(default=0, ge=0, strict=True)


class BlockExtractionOutput(BaseModel):
    """Merged output from all block-specific extractors."""

    header: BlockHeader = Field(default_factory=BlockHeader)
    phan_I: BlockPhanI = Field(default_factory=BlockPhanI)
    bang_thong_ke: BlockBangThongKe = Field(default_factory=BlockBangThongKe)
