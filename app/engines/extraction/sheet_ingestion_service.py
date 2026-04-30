"""Orchestrates deterministic Google Sheet ingestion into extraction_jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.application.doc_service import DocumentService
from app.application.template_service import TemplateManager
from app.core.exceptions import ProcessingError
from app.domain.models.extraction_job import ExtractionJob
from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.sheet_revision_hasher import SheetRevisionHasher
from app.engines.extraction.sources.sheets_source import GoogleSheetsSource, SheetsFetchConfig
from app.utils.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


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
    configs: list[dict] | None = None  # For multi-worksheet mode: list of {worksheet, schema_path, range}


class GoogleSheetIngestionService:
    """Production-style deterministic ingestion service."""

    def __init__(self, db: Session):
        self.db = db
        self.metrics = PipelineMetrics()


    def _ensure_source_document_snapshot(
        self, req: IngestionRequest, sheet_data: dict[str, list[list[str]]]
    ) -> str:
        """Create a source document for the full sheet snapshot (if not already provided).

        Unlike row-level ingestion which stores raw rows array, this stores the full
        worksheet-organized data structure for audit purposes.
        """
        if req.source_document_id:
            return req.source_document_id

        # Build snapshot structure: {worksheet: rows}
        snapshot = {
            "source": "google_sheet_snapshot",
            "sheet_id": req.sheet_id,
            "fetched_at": datetime.utcnow().isoformat(),
            "worksheets": {ws: rows for ws, rows in sheet_data.items()},
        }
        payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
        filename = f"sheet_snapshot_{req.sheet_id}.json".replace("/", "_")

        doc = DocumentService(self.db).create_document(
            tenant_id=req.tenant_id,
            owner_id=req.user_id,
            filename=filename,
            file_content=payload,
            tags=["google_sheet", "snapshot"],
        )
        return str(doc.id)

    async def _ingest_snapshot(self, req: IngestionRequest) -> dict[str, Any]:
        """Ingest full sheet snapshot, creating one ExtractionJob per date group.

        Multi-date ingestion flow:
        1. Fetch all worksheets
        2. Group master worksheet rows by (day, month) → one report per date
        3. Merge non-date worksheets into every date report
        4. For each date: duplicate-check, version, create job

        Each date gets its own per-date revision hash so that a change to one
        day's rows only re-creates that day's job.
        """
        metrics = PipelineMetrics()
        ingestion_run_id = str(uuid4())

        with metrics.timer("ingestion_total"):
            template = (
                TemplateManager(self.db)
                .get_template(req.template_id, tenant_id=req.tenant_id)
                .raise_if_not_found()
            )

            if not template.google_sheet_configs or not isinstance(template.google_sheet_configs, list):
                raise ProcessingError(
                    "Template must have google_sheet_configs list for snapshot ingestion"
                )

            # Fetch all worksheets in parallel
            source = GoogleSheetsSource()
            worksheet_data: dict[str, list[list[str]]] = {}
            fetch_tasks = []
            for cfg in template.google_sheet_configs:
                worksheet = cfg.get("worksheet")
                if not worksheet:
                    continue
                range_a1 = cfg.get("range", "A1:ZZZ")
                fetch_tasks.append(
                    (
                        worksheet,
                        asyncio.to_thread(
                            source.fetch_values,
                            SheetsFetchConfig(
                                sheet_id=req.sheet_id,
                                worksheet=worksheet,
                                range_a1=range_a1,
                            ),
                        ),
                    )
                )

            for worksheet, fetch_task in fetch_tasks:
                rows = await fetch_task
                worksheet_data[worksheet] = rows

            # Build per-date reports
            builder = DailyReportBuilder(
                template=template,
                sheet_data=worksheet_data,
                worksheet_configs=template.google_sheet_configs,
            )

            try:
                date_reports = builder.build_all_by_date()
            except ProcessingError:
                return {
                    "status": "error",
                    "sheet_id": req.sheet_id,
                    "error": "Failed to build date reports",
                    "rows_processed": 0,
                    "rows_inserted": 0,
                    "metrics": {**metrics.to_dict(), "ingestion_run_id": ingestion_run_id},
                    "ingestion_mode": "snapshot",
                }

            if not date_reports:
                return {
                    "status": "ok",
                    "sheet_id": req.sheet_id,
                    "jobs": [],
                    "dates": [],
                    "rows_inserted": 0,
                    "message": "No date groups found in sheet",
                    "metrics": {**metrics.to_dict(), "ingestion_run_id": ingestion_run_id},
                    "ingestion_mode": "snapshot",
                }

            # One snapshot document for all dates in this run
            document_id = self._ensure_source_document_snapshot(req, worksheet_data)

            jobs_created: list[dict] = []
            total_rows_inserted = 0

            for date_key, report in sorted(date_reports.items()):
                report_date_str = date_key

                # Per-date revision hash (hash of date_key + master worksheet content)
                per_date_hash = SheetRevisionHasher.compute_hash(
                    worksheet_data, date_key=date_key
                )

                # Duplicate check: same tenant + template + report_date + per_date_hash
                dup_stmt = select(ExtractionJob).where(
                    and_(
                        ExtractionJob.tenant_id == req.tenant_id,
                        ExtractionJob.template_id == req.template_id,
                        ExtractionJob.report_date == report_date_str,
                        ExtractionJob.sheet_revision_hash == per_date_hash,
                        ExtractionJob.parser_used == "google_sheets",
                    )
                )
                existing = self.db.execute(dup_stmt).scalar_one_or_none()

                if existing:
                    jobs_created.append({
                        "date": date_key,
                        "job_id": str(existing.id),
                        "status": "duplicate",
                        "version": existing.report_version,
                    })
                    continue

                # Next version for this date
                version_stmt = select(ExtractionJob).where(
                    and_(
                        ExtractionJob.tenant_id == req.tenant_id,
                        ExtractionJob.template_id == req.template_id,
                        ExtractionJob.report_date == report_date_str,
                    )
                ).order_by(ExtractionJob.report_version.desc())
                latest = self.db.execute(version_stmt).first()
                next_version = (latest[0].report_version or 0) + 1 if latest else 1

                # Previous version for supersedes link
                supersedes_job_id = latest[0].id if latest else None

                job = ExtractionJob(
                    tenant_id=req.tenant_id,
                    template_id=req.template_id,
                    document_id=document_id,
                    extraction_mode="block",
                    status="extracted",
                    extracted_data=report.model_dump(mode="json"),
                    parser_used="google_sheets",
                    sheet_revision_hash=per_date_hash,
                    report_date=report_date_str,
                    report_version=next_version,
                    validation_report=builder.get_validation_summary(),
                    supersedes_job_id=supersedes_job_id,
                    completed_at=datetime.utcnow(),
                )
                self.db.add(job)
                self.db.commit()
                self.db.refresh(job)

                total_rows_inserted += 1
                jobs_created.append({
                    "date": date_key,
                    "job_id": str(job.id),
                    "status": "created",
                    "version": next_version,
                })

            return {
                "status": "ok",
                "sheet_id": req.sheet_id,
                "jobs": jobs_created,
                "dates": [j["date"] for j in jobs_created],
                "dates_created": sum(1 for j in jobs_created if j["status"] == "created"),
                "dates_duplicate": sum(1 for j in jobs_created if j["status"] == "duplicate"),
                "rows_inserted": total_rows_inserted,
                "metrics": {
                    **metrics.to_dict(),
                    "ingestion_run_id": ingestion_run_id,
                },
                "ingestion_mode": "snapshot",
            }

    async def ingest(self, req: IngestionRequest) -> dict[str, Any]:
        """Orchestrate ingestion based on configuration and feature flag."""
        return await self._ingest_snapshot(req)
