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
