"""Orchestrates deterministic Google Sheet ingestion into extraction_jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import uuid4
from typing import Any

from sqlalchemy.orm import Session

from app.application.doc_service import DocumentService
from app.engines.extraction.mapping.header_detector import detect_header_row
from app.engines.extraction.mapping.mapper import map_row_to_document_data
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.sheet_job_writer import JobWriter
from app.engines.extraction.sources.sheets_source import GoogleSheetsSource, SheetsFetchConfig
from app.engines.extraction.validation.row_validator import build_validation_model, validate_row
from app.utils.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


class RowStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class IngestionRequest:
    tenant_id: str
    user_id: str
    template_id: str
    sheet_id: str
    worksheet: str
    schema_path: str
    source_document_id: str | None = None
    range_a1: str | None = None


class GoogleSheetIngestionService:
    """Production-style deterministic ingestion service."""

    def __init__(self, db: Session):
        self.db = db
        self.metrics = PipelineMetrics()

    def _ensure_source_document(self, req: IngestionRequest, raw_rows: list[list[str]]) -> str:
        if req.source_document_id:
            return req.source_document_id

        snapshot = {
            "source": "google_sheet",
            "sheet_id": req.sheet_id,
            "worksheet": req.worksheet,
            "fetched_at": datetime.utcnow().isoformat(),
            "rows": raw_rows,
        }
        payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
        filename = f"sheet_{req.sheet_id}_{req.worksheet}.json".replace("/", "_")

        doc = DocumentService(self.db).create_document(
            tenant_id=req.tenant_id,
            owner_id=req.user_id,
            filename=filename,
            file_content=payload,
            tags=["google_sheet", "ingestion"],
        )
        return str(doc.id)

    async def ingest(self, req: IngestionRequest) -> dict[str, Any]:
        with self.metrics.timer("ingestion_total"):
            ingestion_run_id = str(uuid4())
            schema = load_schema(req.schema_path)
            model = build_validation_model(schema)

            source = GoogleSheetsSource()
            raw_rows = await asyncio.to_thread(
                source.fetch_values,
                SheetsFetchConfig(sheet_id=req.sheet_id, worksheet=req.worksheet, range_a1=req.range_a1),
            )

            if not raw_rows:
                return {
                    "status": "ok",
                    "sheet_id": req.sheet_id,
                    "worksheet": req.worksheet,
                    "rows_processed": 0,
                    "rows_failed": 0,
                    "rows_inserted": 0,
                    "rows_skipped_idempotent": 0,
                    "schema_match_rate": 0.0,
                    "validation_error_rate": 0.0,
                    "errors": [],
                    "metrics": {
                        "ingestion_run_id": ingestion_run_id,
                        "row_status_counts": {status.value: 0 for status in RowStatus},
                    },
                }

            header_idx, header = detect_header_row(raw_rows, known_aliases=schema.all_aliases)
            data_rows = raw_rows[header_idx + 1 :]

            document_id = self._ensure_source_document(req, raw_rows)
            writer = JobWriter(
                self.db,
                tenant_id=req.tenant_id,
                template_id=req.template_id,
                document_id=document_id,
                user_id=req.user_id,
                sheet_id=req.sheet_id,
                worksheet=req.worksheet,
            )

            errors: list[dict[str, Any]] = []
            rows_processed = 0
            rows_failed = 0
            rows_inserted = 0
            rows_skipped_idempotent = 0
            rows_valid = 0
            mapping_confidence_sum = 0.0
            schema_coverage_sum = 0.0
            row_status_counts = {status.value: 0 for status in RowStatus}

            async def process_one(row_index_1_based: int, row_values: list[str]) -> dict[str, Any]:
                row_dict = {header[i]: row_values[i] if i < len(row_values) else "" for i in range(len(header))}
                mapped, matched, total_fields, missing_required = map_row_to_document_data(row_dict, schema)
                validation = validate_row(
                    model=model,
                    normalized_data=mapped,
                    matched_fields=matched,
                    total_fields=total_fields,
                    missing_required=missing_required,
                )

                row_hash = JobWriter.build_row_hash(validation.normalized_data)
                row_document = {
                    "source": "google_sheet",
                    "sheet_id": req.sheet_id,
                    "worksheet": req.worksheet,
                    "row_index": row_index_1_based,
                    "ingestion_run_id": ingestion_run_id,
                    "row_hash": row_hash,
                    "data": validation.normalized_data,
                }

                source_references = {
                    "source": "google_sheet",
                    "sheet_id": req.sheet_id,
                    "worksheet": req.worksheet,
                    "row_index": row_index_1_based,
                    "schema_path": req.schema_path,
                    "ingestion_run_id": ingestion_run_id,
                    "row_hash": row_hash,
                }
                source_references["ingestion_fingerprint"] = JobWriter.build_fingerprint(row_document)
                return {
                    "row_index": row_index_1_based,
                    "row_dict": row_dict,
                    "row_document": row_document,
                    "source_references": source_references,
                    "validation": validation,
                    "matched": matched,
                    "total_fields": total_fields,
                }

            rows_to_process: list[tuple[int, list[str]]] = []
            for offset, row_values in enumerate(data_rows, start=1):
                row_index = header_idx + 1 + offset
                if not any(str(cell).strip() for cell in (row_values or [])):
                    row_status_counts[RowStatus.SKIPPED.value] += 1
                    errors.append({"row_index": row_index, "status": RowStatus.SKIPPED.value, "errors": ["empty_row"], "row": {}})
                    continue
                rows_to_process.append((row_index, row_values))

            rows_processed = len(rows_to_process)
            if rows_processed:
                self.metrics.inc("rows_processed", rows_processed)

            semaphore = asyncio.Semaphore(16)

            async def guarded_process(item: tuple[int, list[str]]) -> dict[str, Any]:
                row_index, row_values = item
                async with semaphore:
                    return await process_one(row_index, row_values)

            batch_size = 200
            for start in range(0, len(rows_to_process), batch_size):
                batch = rows_to_process[start : start + batch_size]
                prepared_rows = await asyncio.gather(*(guarded_process(item) for item in batch))

                for prepared in prepared_rows:
                    validation = prepared["validation"]
                    mapping_confidence_sum += float(validation.confidence.get("overall", 0.0))
                    schema_coverage_sum += float(validation.confidence.get("schema_match_rate", 0.0))

                    row_hash = str(prepared["source_references"].get("row_hash") or "")
                    if writer.is_duplicate(row_hash):
                        row_status_counts[RowStatus.DUPLICATE.value] += 1
                        rows_skipped_idempotent += 1
                        errors.append(
                            {
                                "row_index": prepared["row_index"],
                                "status": RowStatus.DUPLICATE.value,
                                "errors": ["duplicate_row_hash"],
                                "row": prepared["row_dict"],
                            }
                        )
                        continue

                    if not validation.is_valid:
                        row_status_counts[RowStatus.INVALID.value] += 1
                        rows_failed += 1
                        self.metrics.inc("rows_failed")
                        errors.append(
                            {
                                "row_index": prepared["row_index"],
                                "status": RowStatus.INVALID.value,
                                "errors": validation.errors,
                                "row": prepared["row_dict"],
                            }
                        )
                        continue

                    is_partial = int(prepared["matched"]) < int(prepared["total_fields"])
                    status = RowStatus.PARTIAL if is_partial else RowStatus.VALID
                    prepared["source_references"]["row_status"] = status.value
                    created, _job_id = writer.write_row(
                        row_document=prepared["row_document"],
                        confidence=validation.confidence,
                        source_references=prepared["source_references"],
                    )
                    if created:
                        rows_inserted += 1
                        rows_valid += 1
                        row_status_counts[status.value] += 1
                    else:
                        rows_skipped_idempotent += 1
                        row_status_counts[RowStatus.DUPLICATE.value] += 1
                        errors.append(
                            {
                                "row_index": prepared["row_index"],
                                "status": RowStatus.DUPLICATE.value,
                                "errors": ["duplicate_row_hash"],
                                "row": prepared["row_dict"],
                            }
                        )

            schema_match_rate = round(schema_coverage_sum / float(rows_processed or 1), 4)
            validation_error_rate = round(float(rows_failed) / float(rows_processed or 1), 4)
            mapping_confidence = round(mapping_confidence_sum / float(rows_processed or 1), 4)

            self.metrics.inc("rows_inserted", rows_inserted)
            self.metrics.inc("rows_valid", rows_valid)
            self.metrics.inc("rows_skipped_idempotent", rows_skipped_idempotent)

            log_payload = {
                "ingestion_run_id": ingestion_run_id,
                "sheet_id": req.sheet_id,
                "worksheet": req.worksheet,
                "rows_processed": rows_processed,
                "rows_valid": rows_valid,
                "rows_failed": rows_failed,
                "rows_skipped_idempotent": rows_skipped_idempotent,
                "mapping_confidence": mapping_confidence,
                "schema_coverage": schema_match_rate,
                "validation_error_rate": validation_error_rate,
                "row_status_counts": row_status_counts,
            }
            logger.info("sheet_ingestion_metrics=%s", json.dumps(log_payload, ensure_ascii=False))

            return {
                "status": "ok",
                "sheet_id": req.sheet_id,
                "worksheet": req.worksheet,
                "rows_processed": rows_processed,
                "rows_failed": rows_failed,
                "rows_inserted": rows_inserted,
                "rows_skipped_idempotent": rows_skipped_idempotent,
                "schema_match_rate": schema_match_rate,
                "validation_error_rate": validation_error_rate,
                "errors": errors[:200],
                "metrics": {
                    **self.metrics.to_dict(),
                    "ingestion_run_id": ingestion_run_id,
                    "rows_valid": rows_valid,
                    "mapping_confidence": mapping_confidence,
                    "schema_coverage": schema_match_rate,
                    "row_status_counts": row_status_counts,
                },
            }
