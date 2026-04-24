"""Excel KV30 end-to-end pipeline: Excel file → BlockExtractionOutput.

Orchestrates ExcelKV30Reader → SheetExtractionPipeline to produce
the canonical BlockExtractionOutput from a KV30 Excel workbook.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from app.engines.extraction.excel_kv30_reader import ExcelKV30Reader
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline, PipelineResult

logger = logging.getLogger(__name__)


class ExcelExtractionPipeline:
    """End-to-end Excel KV30 → BlockExtractionOutput.

    Takes either a file path or raw bytes of the KV30 Excel workbook and
    produces a fully-populated BlockExtractionOutput by:
      1. Reading BC NGÀY sheet to extract a daily row
      2. Reading CNCH, CHI VIỆN, VỤ CHÁY THỐNG KÊ sheets
      3. Normalizing all data via SheetExtractionPipeline
      4. Mapping to BlockExtractionOutput schema

    Args:
        excel_path: Path to the .xlsx file on disk.
        excel_bytes: Raw bytes of the .xlsx file (alternative to path).
        day: Ngày to extract (1-31).
        month: Tháng (1-12 or string).
        year: Năm (default 2026).
        header_overrides: Optional dict to override header fields
                         (so_bao_cao, ngay_bao_cao, thoi_gian_tu_den, don_vi_bao_cao).
    """

    def __init__(
        self,
        excel_path: Path | str | None = None,
        excel_bytes: bytes | None = None,
        *,
        day: int,
        month: int | str,
        year: int = 2026,
        header_overrides: dict[str, str] | None = None,
    ) -> None:
        self.reader = ExcelKV30Reader(excel_path=excel_path, excel_bytes=excel_bytes)
        self.sheet_pipeline = SheetExtractionPipeline()
        self.day = day
        self.month = int(str(month).strip()) if isinstance(month, str) else month
        self.year = year
        self.header_overrides = header_overrides or {}

    def run(self) -> PipelineResult:
        """Run the full pipeline and return PipelineResult."""
        try:
            # Normalize Excel data → pipeline dict
            normalized = self.reader.normalize_for_pipeline(
                day=self.day, month=self.month, year=self.year
            )

            # Inject header overrides
            if self.header_overrides:
                header = normalized.get("header") or {}
                header.update(self.header_overrides)
                normalized["header"] = header

            # Run through SheetExtractionPipeline
            output = self.sheet_pipeline.run(normalized)

            # Log metrics
            if output.output:
                btk_count = len(output.output.bang_thong_ke)
                cnch_count = len(output.output.danh_sach_cnch)
                cv_count = len(output.output.danh_sach_cong_van_tham_muu)
                logger.info(
                    "ExcelExtractionPipeline done: bang_thong_ke=%s rows, cnch=%s, chi_vien=%s, chay=%s",
                    btk_count,
                    cnch_count,
                    len(output.output.danh_sach_chi_vien),
                    len(output.output.danh_sach_chay),
                )

            return output

        except Exception as exc:
            logger.error("ExcelExtractionPipeline failed: %s", exc)
            return PipelineResult(
                status="failed",
                attempts=1,
                output=None,
                errors=[str(exc)],
                chi_tiet_cnch="",
            )