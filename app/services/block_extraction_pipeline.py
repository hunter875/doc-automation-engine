"""Block-based extraction pipeline running in parallel with hybrid pipeline."""

from __future__ import annotations

import io
import logging
import re
from uuid import uuid4
from typing import Any, Callable

from pydantic import BaseModel

from app.core.config import settings
from app.core.tracing import trace_step
from app.schemas.hybrid_extraction_schema import (
    BlockBangThongKe,
    BlockExtractionOutput,
    BlockHeader,
    BlockNghiepVu,
)
from app.services.extractor_strategies import OllamaInstructorExtractor
from app.services.hybrid_extraction_pipeline import PipelineResult

logger = logging.getLogger(__name__)


class BlockExtractionPipeline:
    """Split-by-block extraction using `layout=True` OCR text layout."""

    def __init__(
        self,
        job_id: str | None = None,
        progress_callback: Callable[[str, str], Any] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.job_id = job_id
        self.trace_id = str(uuid4())
        self.retry_count = 0
        self.progress_callback = progress_callback
        self.model = model or settings.OLLAMA_MODEL
        self.temperature = temperature
        self.extractor = OllamaInstructorExtractor(
            base_url=settings.OLLAMA_BASE_URL,
            api_key=settings.OLLAMA_API_KEY,
            timeout_seconds=settings.OLLAMA_TIMEOUT_SECONDS,
            log_raw_pre_validate=settings.OLLAMA_LOG_RAW_PRE_VALIDATE,
            raw_preview_chars=settings.OLLAMA_RAW_PREVIEW_CHARS,
        )

    def emit(self, step_name: str) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(step_name, self.trace_id)
        except Exception:
            logger.warning("progress_callback failed for step '%s'", step_name, exc_info=True)

    @trace_step("block_split_into_blocks")
    def _split_into_blocks(self, pdf_bytes: bytes) -> dict[str, str]:
        self.emit("block_split_into_blocks")
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("pdfplumber is not installed") from exc

        full_text: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=True) or ""
                full_text.append(text)

        content = "\n".join(full_text)
        blocks = {"header": "", "phan_nghiep_vu": "", "bang_thong_ke": ""}

        # 1. Cắt Header
        header_match = re.search(
            r"(.*?)(?=I\.\s*TÌNH\s*HÌNH\s*CHÁY,?\s*NỔ)",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if header_match:
            blocks["header"] = header_match.group(1).strip()

        # 2. Cắt Phần I & II (Cú lai tạp: Kéo thẳng đến tận BIỂU MẪU THỐNG KÊ)
        phan_nghiep_vu_match = re.search(
            r"(I\.\s*TÌNH\s*HÌNH\s*CHÁY.*?)(?=BIỂU\s*MẪU\s*THỐNG\s*KÊ)",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if phan_nghiep_vu_match:
            blocks["phan_nghiep_vu"] = phan_nghiep_vu_match.group(1).strip()

        # 3. Cắt Bảng Thống Kê
        bang_match = re.search(
            r"(BIỂU\s*MẪU\s*THỐNG\s*KÊ.*)",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if bang_match:
            lines = [line.strip() for line in bang_match.group(1).splitlines() if line.strip()]
            blocks["bang_thong_ke"] = "\n".join(lines)

        return blocks

    @trace_step("block_extract_block")
    def _extract_block(self, block_text: str, schema: type[BaseModel], block_name: str) -> BaseModel:
        self.emit(f"block_extract_{block_name}")
        if not block_text:
            return schema()

        messages = [
            {
                "role": "system",
                "content": (
                    "Mày là chuyên gia bóc tách dữ liệu PCCC. "
                    f"Trích xuất chính xác theo schema JSON cho phần {block_name}. "
                    "Tuyệt đối không suy đoán. Nếu thiếu dữ liệu thì trả giá trị mặc định theo schema."
                ),
            },
            {"role": "user", "content": f"Dữ liệu {block_name}:\n{block_text}"},
        ]

        return self.extractor.extract(
            messages=messages,
            response_model=schema,
            model=self.model,
            temperature=self.temperature,
        )

    def run_from_bytes(self, pdf_bytes: bytes, filename: str) -> PipelineResult:
        del filename
        try:
            blocks = self._split_into_blocks(pdf_bytes)

            header_data = self._extract_block(blocks["header"], BlockHeader, "Header")
            phan_nghiep_vu_data = self._extract_block(blocks["phan_nghiep_vu"], BlockNghiepVu, "Phần Nghiệp Vụ")

            # Vét cạn qua mảng động
            bang_data_wrapper = self._extract_block(blocks["bang_thong_ke"], BlockBangThongKe, "Bảng thống kê")

            # Cú chốt: Đập phẳng cái mảng danh_sach_chi_tieu ra ngoài
            final_output = BlockExtractionOutput(
                header=header_data,
                phan_I_va_II_chi_tiet_nghiep_vu=phan_nghiep_vu_data,
                bang_thong_ke=bang_data_wrapper.danh_sach_chi_tieu,
            )

            return PipelineResult(status="ok", attempts=1, output=final_output)
        except Exception as exc:
            logger.error("Block extraction pipeline failed: %s", exc)
            return PipelineResult(status="failed", attempts=1, errors=[str(exc)])
