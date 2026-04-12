"""Extraction schemas: Pydantic output models and pipeline result dataclass."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_DATE_DDMMYYYY = "%d/%m/%Y"


class CNCHItem(BaseModel):
    """Single CNCH incident entry.

    Fields map directly to Word template loop variable ``vu.*``:
      thoi_gian           → vu.thoi_gian
      dia_diem            → vu.dia_diem
      noi_dung_tin_bao    → vu.noi_dung_tin_bao  (what was reported)
      luc_luong_tham_gia  → vu.luc_luong_tham_gia (forces/vehicles deployed)
      ket_qua_xu_ly       → vu.ket_qua_xu_ly      (outcome)
      thong_tin_nan_nhan  → vu.thong_tin_nan_nhan  (victim info)
    """

    # extra="ignore" so LLM-returned unknown keys don't cause ValidationError
    model_config = ConfigDict(extra="ignore")

    stt: int = Field(default=0, strict=True)
    ngay_xay_ra: str = Field(default="")
    thoi_gian: str = Field(default="")
    dia_diem: str = Field(default="")
    noi_dung_tin_bao: str = Field(default="", description="Nội dung tin báo / loại sự cố")
    luc_luong_tham_gia: str = Field(default="", description="Lực lượng, phương tiện xuất động")
    ket_qua_xu_ly: str = Field(default="", description="Kết quả xử lý sự cố")
    thiet_hai: str = Field(default="", description="Thiệt hại về người / tài sản")
    thong_tin_nan_nhan: str = Field(default="", description="Thông tin nạn nhân")
    # Internal use only — kept for backward compat with business-rules path
    mo_ta: str = Field(default="")

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

        # Normalize single-digit day/month to zero-padded (e.g. 2/4/2026 → 02/04/2026)
        def _zero_pad_date(m: re.Match) -> str:
            return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"
        value = re.sub(r"(\d{1,2})/(\d{1,2})/(\d{4})", _zero_pad_date, value)
        self.thoi_gian = value

        patterns = [
            r"^\d{2}/\d{2}/\d{4}$",
            r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$",
            r"^\d{2}:\d{2}\s+\d{2}/\d{2}/\d{4}$",
            r"^\d{2}:\d{2}\s+ngày\s+\d{2}/\d{2}/\d{4}$",
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

    # Smaller local models may output table-style keys (e.g. "STT").
    # Ignore unknown keys so known prose fields can still be recovered.
    model_config = ConfigDict(extra="ignore")

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
    tong_chi_vien: int = Field(default=0, description="Tổng số lượt chi viện")
    tong_cong_van: int = Field(default=0, description="Tổng số công văn tham mưu")
    tong_bao_cao: int = Field(default=0, description="Tổng số báo cáo tham mưu")
    tong_ke_hoach: int = Field(default=0, description="Tổng số kế hoạch tham mưu")
    cong_tac_an_ninh: str = Field(default="", description="Nội dung công tác an ninh trật tự")
    tong_xe_hu_hong: int = Field(default=0, description="Tổng số phương tiện hư hỏng")


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


class PhuongTienHuHongItem(BaseModel):
    """Single damaged vehicle entry.

    Fields map to Word template loop variable ``xe.*``:
      bien_so    → xe.bien_so   (license plate or vehicle ID)
      tinh_trang → xe.tinh_trang (condition: hư hỏng / hết kiểm định / đang sửa chữa)
    """

    model_config = ConfigDict(extra="ignore")

    bien_so: str = Field(default="", description="Biển số hoặc mã hiệu phương tiện")
    tinh_trang: str = Field(default="", description="Tình trạng hư hỏng / kiểm định")


class CongVanItem(BaseModel):
    """Single official document entry.

    Fields map to Word template loop variable ``cv.*``:
      so_ky_hieu → cv.so_ky_hieu  (document number)
      noi_dung   → cv.noi_dung    (document content/title)
    """

    model_config = ConfigDict(extra="ignore")

    so_ky_hieu: str = Field(default="", description="Số ký hiệu công văn")
    noi_dung: str = Field(default="", description="Nội dung / trích yếu công văn")


class CNCHListOutput(BaseModel):
    """Wrapper schema for targeted LLM extraction of CNCH incident list.

    Uses extra='ignore' so the model tolerates unknown keys from small local LLMs.
    """

    model_config = ConfigDict(extra="ignore")

    items: list[CNCHItem] = Field(
        default_factory=list,
        description="Danh sách vụ CNCH, mỗi vụ gồm thời gian, địa điểm và mô tả sự cố",
    )


class BlockExtractionOutput(BaseModel):
    header: BlockHeader
    phan_I_va_II_chi_tiet_nghiep_vu: BlockNghiepVu
    bang_thong_ke: list[ChiTieu]
    danh_sach_cnch: list[CNCHItem] = Field(default_factory=list)
    danh_sach_phuong_tien_hu_hong: list[PhuongTienHuHongItem] = Field(default_factory=list)
    danh_sach_cong_van_tham_muu: list[CongVanItem] = Field(default_factory=list)
    danh_sach_cong_tac_khac: list[str] = Field(default_factory=list)


@dataclass
class PipelineResult:
    """Final result returned by any extraction pipeline."""

    status: str
    attempts: int
    output: BaseModel | None = None
    errors: list[str] = field(default_factory=list)
    manual_review_path: str | None = None
    manual_review_metadata_path: str | None = None
    business_data: dict | None = None
    metrics: dict | None = None
    # Stage-1 carries the raw CNCH subsection text so the enrichment worker
    # can call the LLM in Stage 2 without re-running PDF extraction.
    chi_tiet_cnch: str = ""
