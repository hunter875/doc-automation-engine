"""Orchestrates deterministic Google Sheet ingestion into extraction_jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
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
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.sources.sheets_source import GoogleSheetsSource, SheetsFetchConfig
from app.utils.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


def _parse_date_key(date_key: str) -> date:
    """Parse date_key string like '01/04' or '01/04/2026' into a date object."""
    for fmt in ("%d/%m/%Y", "%d/%m"):
        try:
            parsed = datetime.strptime(date_key, fmt).date()
            if parsed.year == 1900:
                parsed = parsed.replace(year=date.today().year)
            return parsed
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date_key: {date_key!r}")


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
        # Always create a new snapshot document for tests/production consistency
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
            template = TemplateManager(self.db).get_template(
                req.template_id, tenant_id=req.tenant_id
            )

            # Resolve worksheet configs: prioritize request-provided configs (KV30 mode),
            # otherwise fall back to template's google_sheet_configs
            worksheet_configs: list[dict] = []
            if req.configs:
                worksheet_configs = req.configs
            elif template.google_sheet_configs and isinstance(template.google_sheet_configs, list):
                worksheet_configs = template.google_sheet_configs
            else:
                raise ProcessingError(
                    "Template must have google_sheet_configs list for snapshot ingestion, or provide configs in request"
                )

            # Validate all schema files exist BEFORE fetching sheet data (fail fast)
            from app.engines.extraction.mapping.schema_loader import load_schema
            for cfg in worksheet_configs:
                schema_path = cfg.get("schema_path")
                if not schema_path:
                    continue
                try:
                    load_schema(schema_path)
                except ProcessingError as e:
                    raise ProcessingError(
                        message=f"SCHEMA_NOT_FOUND: Schema file '{schema_path}' configured for "
                                f"worksheet '{cfg.get('worksheet')}' cannot be loaded. "
                                f"Ensure the file exists at that path or in app/domain/templates/. "
                                f"Original error: {e}"
                    ) from e

            # Fetch all worksheets in parallel
            from app.engines.extraction.sources.sheets_source import (
                GoogleSheetsSource,
                SheetsFetchConfig,
            )

            source = GoogleSheetsSource()

            # List all available worksheets for discovery
            all_worksheet_names: list[str] = []
            try:
                all_worksheet_names = await asyncio.to_thread(
                    source.list_worksheets,
                    req.sheet_id,
                )
                logger.info(
                    "[Ingestion] Discovered worksheets in sheet_id=%s: %s",
                    req.sheet_id,
                    all_worksheet_names,
                )
            except Exception as e:
                logger.warning(
                    "[Ingestion] Failed to list worksheets (will use config only): %s",
                    e,
                )

            worksheet_data: dict[str, list[list[str]]] = {}
            fetch_tasks = []
            for cfg in worksheet_configs:
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

            # Log fetched worksheets for debugging
            logger.info(
                "[Ingestion] Fetched worksheets from sheet_id=%s: %s",
                req.sheet_id,
                {ws: len(rows) for ws, rows in worksheet_data.items()},
            )

            # Build per-date reports
            resolver_debug = None
            try:
                # For KV30 mode: auto-resolve the correct master worksheet
                is_kv30_mode = any("kv30" in cfg.get("schema_path", "").lower() for cfg in worksheet_configs)
                if is_kv30_mode:
                    from app.engines.extraction.worksheet_resolver import resolve_daily_worksheet, DAILY_RESOLVER_VERSION

                    logger.info(
                        "[Ingestion] KV30 mode detected. DAILY_RESOLVER_VERSION=%s | Invoking worksheet resolver...",
                        DAILY_RESOLVER_VERSION,
                    )

                    master_cfg_original = worksheet_configs[0]  # first config is master
                    master_ws_original = master_cfg_original["worksheet"]

                    try:
                        resolved_ws, resolver_debug = resolve_daily_worksheet(
                            preferred_worksheet=master_ws_original,
                            worksheet_data=worksheet_data,
                            all_worksheet_names=all_worksheet_names,
                        )
                        if resolved_ws != master_ws_original:
                            logger.warning(
                                "[Ingestion] ⚠️ Auto-resolved master worksheet from '%s' to '%s' | resolver_debug=%s",
                                master_ws_original,
                                resolved_ws,
                                resolver_debug,
                            )
                            # Update config with resolved worksheet
                            worksheet_configs = [dict(cfg) for cfg in worksheet_configs]
                            worksheet_configs[0]["worksheet"] = resolved_ws
                        else:
                            logger.info(
                                "[Ingestion] ✅ Using preferred worksheet '%s' (no fallback needed)",
                                master_ws_original,
                            )
                    except ValueError as e:
                        # No valid worksheet found
                        logger.error(
                            "[Ingestion] ❌ Resolver failed to find valid worksheet: %s",
                            e,
                        )
                        raise ProcessingError(message=str(e)) from e

                builder = DailyReportBuilder(
                    template=template,
                    sheet_data=worksheet_data,
                    worksheet_configs=worksheet_configs,
                )
                date_reports = builder.build_all_by_date()
            except ProcessingError as e:
                logger.error(
                    "[Ingestion] DailyReportBuilder.build_all_by_date failed: %s",
                    e,
                    exc_info=True,
                )
                error_response = {
                    "status": "error",
                    "sheet_id": req.sheet_id,
                    "error": f"Failed to build date reports: {e}",
                    "rows_processed": 0,
                    "rows_inserted": 0,
                    "metrics": {**metrics.to_dict(), "ingestion_run_id": ingestion_run_id},
                    "ingestion_mode": "snapshot",
                }
                if resolver_debug:
                    error_response["resolver_debug"] = resolver_debug
                return error_response

            if not date_reports:
                return {
                    "status": "ok",
                    "sheet_id": req.sheet_id,
                    "jobs": [],
                    "dates": [],
                    "dates_created": 0,
                    "dates_duplicate": 0,
                    "dates_skipped_no_data": 0,
                    "rows_processed": 0,
                    "rows_failed": 0,
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
                if not date_key or not str(date_key).strip():
                    raise ValueError(
                        "DailyReportBuilder returned an empty date_key. "
                        "This indicates invalid grouping or bad sheet input."
                    )
                report_date_val = _parse_date_key(date_key)

                # Per-date revision hash (hash of date_key + master worksheet content)
                per_date_hash = SheetRevisionHasher.compute_hash(
                    worksheet_data, date_key=date_key
                )

                # Duplicate check: same tenant + template + report_date + per_date_hash
                dup_stmt = select(ExtractionJob).where(
                    and_(
                        ExtractionJob.tenant_id == req.tenant_id,
                        ExtractionJob.template_id == req.template_id,
                        ExtractionJob.report_date == report_date_val,
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
                        ExtractionJob.report_date == report_date_val,
                    )
                ).order_by(ExtractionJob.report_version.desc())
                latest = self.db.execute(version_stmt).first()
                next_version = (latest[0].report_version or 0) + 1 if latest else 1

                # Previous version for supersedes link
                supersedes_job_id = latest[0].id if latest else None

                # Guard: skip job creation if report has no meaningful data.
                # This prevents silent data-loss from propagating to the database.
                nghiep_vu = report.phan_I_va_II_chi_tiet_nghiep_vu
                has_metrics = (
                    len(report.bang_thong_ke) > 0
                    or (getattr(nghiep_vu, "tong_so_vu_chay", 0) not in (None, 0))
                    or (getattr(nghiep_vu, "tong_so_vu_cnch", 0) not in (None, 0))
                    or (getattr(nghiep_vu, "tong_sclq", 0) not in (None, 0))
                )
                if not has_metrics:
                    logger.warning(
                        "No meaningful data extracted for date=%s tenant=%s template=%s — skipping job creation",
                        date_key, req.tenant_id, req.template_id,
                    )
                    jobs_created.append({
                        "date": date_key,
                        "job_id": None,
                        "status": "skipped_no_data",
                        "version": next_version,
                    })
                    continue

                final_report = BlockExtractionOutput.model_validate(report.model_dump())
                final_json = final_report.model_dump(mode="json")
                extracted_payload = {
                    "source": "google_sheet",
                    "sheet_id": req.sheet_id,
                    "date_key": date_key,
                    "data": final_json,
                    "debug": {
                        "schema_paths": [cfg.get("schema_path") for cfg in worksheet_configs if cfg.get("schema_path")],
                        "worksheet_summaries": builder.get_validation_summary(),
                        "ingestion_run_id": ingestion_run_id,
                    },
                }

                job = ExtractionJob(
                    tenant_id=req.tenant_id,
                    template_id=req.template_id,
                    document_id=document_id,
                    extraction_mode="block",
                    status="extracted",
                    extracted_data=extracted_payload,
                    parser_used="google_sheets",
                    sheet_revision_hash=per_date_hash,
                    report_date=report_date_val,
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
                "dates_skipped_no_data": sum(1 for j in jobs_created if j["status"] == "skipped_no_data"),
                "metrics": {
                    **metrics.to_dict(),
                    "ingestion_run_id": ingestion_run_id,
                },
                "ingestion_mode": "snapshot",
            }

    async def ingest(self, req: IngestionRequest) -> dict[str, Any]:
        """Orchestrate ingestion based on configuration and feature flag."""
        return await self._ingest_snapshot(req)
