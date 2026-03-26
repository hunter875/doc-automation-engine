"""Block-based extraction pipeline running in parallel with hybrid pipeline."""

from __future__ import annotations

import io
import logging
import re

from pydantic import BaseModel

from app.core.config import settings
from app.schemas.hybrid_extraction_schema import (
    BlockBangThongKe,
    BlockExtractionOutput,
    BlockHeader,
    BlockPhanI,
)
from app.services.extractor_strategies import OllamaInstructorExtractor
from app.services.hybrid_extraction_pipeline import PipelineResult

logger = logging.getLogger(__name__)


class BlockExtractionPipeline:
    """Split-by-block extraction using `layout=True` OCR text layout."""

    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        self.model = model or settings.OLLAMA_MODEL
        self.temperature = temperature
        self.extractor = OllamaInstructorExtractor(
            base_url=settings.OLLAMA_BASE_URL,
            api_key=settings.OLLAMA_API_KEY,
            timeout_seconds=settings.OLLAMA_TIMEOUT_SECONDS,
            log_raw_pre_validate=settings.OLLAMA_LOG_RAW_PRE_VALIDATE,
            raw_preview_chars=settings.OLLAMA_RAW_PREVIEW_CHARS,
        )

    def _split_into_blocks(self, pdf_bytes: bytes) -> dict[str, str]:
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
        blocks = {"header": "", "phan_I": "", "bang_thong_ke": ""}

        header_match = re.search(
            r"(.*?)(?=I\.\s*TÌNH\s*HÌNH\s*CHÁY,?\s*NỔ)",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if header_match:
            blocks["header"] = header_match.group(1).strip()

        phan1_match = re.search(
            r"(I\.\s*TÌNH\s*HÌNH\s*CHÁY.*?)(?=II\.|BIỂU\s*MẪU\s*THỐNG\s*KÊ)",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if phan1_match:
            blocks["phan_I"] = phan1_match.group(1).strip()

        bang_match = re.search(
            r"(BIỂU\s*MẪU\s*THỐNG\s*KÊ.*)",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if bang_match:
            lines = [line.strip() for line in bang_match.group(1).splitlines() if line.strip()]
            blocks["bang_thong_ke"] = "\n".join(lines)

        return blocks

    def _extract_block(self, block_text: str, schema: type[BaseModel], block_name: str) -> BaseModel:
        if not block_text:
            return schema()

        messages = [
            {
                "role": "system",
                "content": (
                    "Mày là chuyên gia bóc tách dữ liệu PCCC. "
                    f"Trích xuất chính xác theo schema JSON cho phần {block_name}. "
                    "Nếu thiếu dữ liệu thì trả giá trị mặc định theo schema."
                ),
            },
            {"role": "user", "content": block_text},
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
            phan_i_data = self._extract_block(blocks["phan_I"], BlockPhanI, "Phần I")
            bang_data = self._extract_block(blocks["bang_thong_ke"], BlockBangThongKe, "Bảng thống kê")

            final_output = BlockExtractionOutput(
                header=header_data,
                phan_I=phan_i_data,
                bang_thong_ke=bang_data,
            )

            return PipelineResult(status="ok", attempts=1, output=final_output)
        except Exception as exc:
            logger.error("Block extraction pipeline failed: %s", exc)
            return PipelineResult(status="failed", attempts=1, errors=[str(exc)])
