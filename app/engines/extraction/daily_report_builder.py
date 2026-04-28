"""Assemble full DailyReport from multiple worksheet snapshots."""

from __future__ import annotations

from typing import Any, Dict, List

from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.validation.row_validator import (
    RowValidationResult,
    build_validation_model,
    validate_row,
)
from app.domain.models.extraction_job import ExtractionTemplate


class DailyReportBuilder:
    """Builds a complete BlockExtractionOutput from all worksheet data.

    Responsibilities:
    - Parse each worksheet according to its schema config
    - Assemble partial outputs into a single canonical report
    - Aggregate validation results across all rows
    - Ensure deterministic output
    """

    def __init__(
        self,
        template: ExtractionTemplate,
        sheet_data: Dict[str, List[List[Any]]],
        worksheet_configs: List[Dict[str, Any]],
    ) -> None:
        self.template = template
        self.sheet_data = sheet_data  # worksheet_name -> 2D array
        self.worksheet_configs = worksheet_configs
        self._row_entries: List[Dict[str, Any]] = []  # stores per-row validation & metadata
        self._warnings: List[str] = []

    def build(self) -> BlockExtractionOutput:
        """Construct the full report.

        Returns:
            Complete BlockExtractionOutput with all sections populated.

        Raises:
            ProcessingError: If report_date cannot be determined from BC NGÀY.
        """
        from app.core.exceptions import ProcessingError

        # Initialize empty report structure
        report = self._create_empty_report()

        # Process each worksheet according to its config
        for config in self.worksheet_configs:
            worksheet_name = config["worksheet"]
            schema_path = config["schema_path"]
            target_section = config["target_section"]

            # Check if worksheet exists in sheet
            if worksheet_name not in self.sheet_data:
                self._warnings.append(f"worksheet_missing:{worksheet_name}")
                continue

            rows = self.sheet_data[worksheet_name]
            if not rows:
                self._warnings.append(f"worksheet_empty:{worksheet_name}")
                continue

            # Detect header row for this worksheet
            header_idx, header = self._detect_header(rows, schema_path)
            if header_idx is None:
                self._warnings.append(f"header_not_found:{worksheet_name}")
                continue

            # Process data rows
            data_rows = rows[header_idx + 1:]
            for row_idx, row in enumerate(data_rows, start=1):
                if not any(str(cell).strip() for cell in row):
                    continue  # Skip empty rows

                # Convert row to dict
                row_dict = dict(zip(header, row))

                # Map and validate
                from app.engines.extraction.mapping.mapper import map_row_to_document_data
                from app.engines.extraction.sheet_ingestion_service import load_schema

                schema = load_schema(schema_path)
                validation_model = build_validation_model(schema)
                normalized, matched, total, missing = map_row_to_document_data(
                    row_dict, schema
                )
                validation = validate_row(
                    validation_model, normalized, matched, total, missing
                )

                # Store row-level validation + metadata
                self._row_entries.append({
                    "worksheet": worksheet_name,
                    "row_index": row_idx,
                    "row_dict": row_dict,
                    "normalized": normalized,
                    "validation": validation,
                })

                # Transform to canonical output via pipeline
                pipeline = SheetExtractionPipeline()
                result = pipeline.run(
                    {"data": normalized},  # wrapped in "data" for compatibility
                    schema_path=schema_path,
                )

                if result.status == "ok" and result.output:
                    self._merge_section(report, result.output, target_section)
                else:
                    # Pipeline failed — skip this row but keep it in validation
                    self._warnings.append(
                        f"pipeline_failed:{worksheet_name}:row{row_idx}"
                    )

        # Post-process: compute report_date from BC NGÀY if present
        report_date = self._extract_report_date(report)
        if report_date is None:
            raise ProcessingError(
                "Cannot determine report_date from BC NGÀY header"
            )

        # Attach metadata (not part of canonical output)
        report._report_date = report_date
        report._validation_summary = self._build_validation_summary()

        return report

    def _create_empty_report(self) -> BlockExtractionOutput:
        """Create an empty report with all sections initialized."""
        from app.engines.extraction.schemas import (
            BlockHeader,
            BlockNghiepVu,
            TuyenTruyenOnline,
        )

        return BlockExtractionOutput(
            header=BlockHeader(),
            phan_I_va_II_chi_tiet_nghiep_vu=BlockNghiepVu(),
            bang_thong_ke=[],
            danh_sach_cnch=[],
            danh_sach_phuong_tien_hu_hong=[],
            danh_sach_cong_van_tham_muu=[],
            danh_sach_cong_tac_khac=[],
            danh_sach_chi_vien=[],
            danh_sach_chay=[],
            tuyen_truyen_online=TuyenTruyenOnline(),
        )

    def _detect_header(
        self, rows: List[List[Any]], schema_path: str
    ) -> tuple[int | None, List[str]]:
        """Detect header row using the same logic as ingestion."""
        from app.engines.extraction.mapping.header_detector import detect_header_row
        from app.engines.extraction.sheet_ingestion_service import load_schema

        # Load schema to get known aliases
        schema = load_schema(schema_path)
        known_aliases = set(schema.all_aliases) if hasattr(schema, "all_aliases") else set()

        # Detect header
        header_idx, header_columns = detect_header_row(rows, known_aliases=known_aliases)
        return header_idx, header_columns

    def _merge_section(
        self,
        report: BlockExtractionOutput,
        partial: BlockExtractionOutput,
        target_section: str,
    ) -> None:
        """Merge a section from partial report into the full report.

        For list sections: extend the list.
        For header/nghiep_vu: update fields with non-empty values from partial.
        """
        if target_section == "header":
            # Merge header fields (overwrite non-empty)
            for field, value in partial.header.model_dump().items():
                current = getattr(report.header, field)
                if value not in (None, "", 0) or (current in (None, "", 0)):
                    setattr(report.header, field, value)

        elif target_section == "phan_I_va_II_chi_tiet_nghiep_vu":
            # Merge nghiep_vu fields (overwrite non-empty)
            for field, value in partial.phan_I_va_II_chi_tiet_nghiep_vu.model_dump().items():
                current = getattr(report.phan_I_va_II_chi_tiet_nghiep_vu, field)
                if value not in (None, "", 0) or (current in (None, "", 0)):
                    setattr(report.phan_I_va_II_chi_tiet_nghiep_vu, field, value)

        elif target_section == "bang_thong_ke":
            # Extend bang_thong_ke list
            if partial.bang_thong_ke:
                report.bang_thong_ke.extend(partial.bang_thong_ke)

        elif hasattr(report, target_section):
            # List sections: extend
            current_list = getattr(report, target_section)
            partial_list = getattr(partial, target_section)
            if isinstance(current_list, list) and isinstance(partial_list, list):
                current_list.extend(partial_list)

    def _extract_report_date(self, report: BlockExtractionOutput) -> Any:
        """Extract report_date from report.header.ngay_bao_cao.

        Returns: date string (dd/mm/yyyy) or None if not found.
        """
        ngay_bao_cao = getattr(report.header, "ngay_bao_cao", None)
        if ngay_bao_cao:
            return ngay_bao_cao
        return None

    def _build_validation_summary(self) -> Dict[str, Any]:
        """Aggregate validation results across all rows."""
        total = len(self._row_entries)
        valid = sum(1 for entry in self._row_entries if entry["validation"].is_valid)
        invalid = total - valid

        confidences = [
            float(entry["validation"].confidence.get("overall", 0.0))
            for entry in self._row_entries
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        invalid_rows = []
        for entry in self._row_entries:
            if not entry["validation"].is_valid:
                invalid_rows.append({
                    "worksheet": entry["worksheet"],
                    "row_index": entry["row_index"],
                    "errors": entry["validation"].errors,
                    "confidence": entry["validation"].confidence,
                })

        return {
            "total_rows": total,
            "valid_rows": valid,
            "invalid_rows": invalid_rows,
            "invalid_rows_count": invalid,
            "avg_confidence": avg_conf,
            "warnings": self._warnings,
        }

    def get_validation_summary(self) -> Dict[str, Any]:
        """Return the aggregated validation summary."""
        return self._validation_summary
