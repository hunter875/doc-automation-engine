"""Service for reading DailyReports from snapshot ingestion jobs."""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.domain.models.daily_report_edit import DailyReportEdit
from app.domain.models.extraction_job import ExtractionJob
from app.application.job_service import JobManager
from app.application.aggregation_service import AggregationService
from app.engines.extraction.schemas import BlockExtractionOutput


class DailyReportService:
    """Service for reading DailyReports from snapshot ingestion jobs."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.job_manager = JobManager(db)
        self.aggregation_service = AggregationService(db)

    def get_report(
        self,
        tenant_id: str,
        template_id: str,
        report_date: date,
    ) -> Optional[dict]:
        """Get the latest daily report for the given template and date.

        Strategy:
        1. Try snapshot job (sheet_revision_hash IS NOT NULL)
        2. Fall back to aggregating legacy row-level jobs
        """
        # Try snapshot job first
        snapshot_job = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.template_id == template_id,
                ExtractionJob.report_date == report_date,
                ExtractionJob.parser_used == "google_sheets",
                ExtractionJob.sheet_revision_hash.is_not(None),
            )
            .order_by(ExtractionJob.report_version.desc())
            .first()
        )

        if snapshot_job and snapshot_job.extracted_data:
            return snapshot_job.extracted_data

        # Fallback: aggregate legacy row-level jobs
        legacy_jobs = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.template_id == template_id,
                ExtractionJob.parser_used == "google_sheets",
                ExtractionJob.sheet_revision_hash.is_(None),
                ExtractionJob.created_at >= report_date,
                ExtractionJob.created_at < date(report_date.year, report_date.month, report_date.day + 1),
            )
            .all()
        )

        if legacy_jobs:
            job_ids = [str(job.id) for job in legacy_jobs]
            aggregated = self.aggregation_service.aggregate_data_only(
                template_id=template_id,
                job_ids=job_ids,
                tenant_id=tenant_id,
            )
            return aggregated

        return None

    def get_latest_snapshot_version(
        self,
        tenant_id: str,
        template_id: str,
        report_date: date,
    ) -> Optional[ExtractionJob]:
        """Get the latest snapshot job."""
        return (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.template_id == template_id,
                ExtractionJob.report_date == report_date,
                ExtractionJob.parser_used == "google_sheets",
                ExtractionJob.sheet_revision_hash.is_not(None),
            )
            .order_by(ExtractionJob.report_version.desc())
            .first()
        )

    def get_report_history(
        self,
        tenant_id: str,
        template_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """Get all snapshot reports within date range."""
        jobs = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.template_id == template_id,
                ExtractionJob.report_date >= start_date,
                ExtractionJob.report_date <= end_date,
                ExtractionJob.parser_used == "google_sheets",
                ExtractionJob.sheet_revision_hash.is_not(None),
            )
            .order_by(ExtractionJob.report_date.desc(), ExtractionJob.report_version.desc())
            .all()
        )

        return [
            {
                "job_id": job.id,
                "report_date": job.report_date,
                "report_version": job.report_version,
                "created_at": job.created_at,
                "validation_summary": job.validation_report,
                "sheet_revision_hash": job.sheet_revision_hash,
            }
            for job in jobs
        ]

    def _unwrap_extracted_data(self, extracted_data: dict) -> dict:
        """Extract BlockExtractionOutput from wrapper if present."""
        if isinstance(extracted_data, dict) and isinstance(extracted_data.get("data"), dict):
            nested = extracted_data["data"]
            if "header" in nested:
                return nested
        return extracted_data

    def get_latest_manual_edit(
        self, tenant_id: UUID, template_id: UUID, report_date: date
    ) -> Optional[DailyReportEdit]:
        """Get latest manual edit for given date."""
        return (
            self.db.query(DailyReportEdit)
            .filter(
                DailyReportEdit.tenant_id == tenant_id,
                DailyReportEdit.template_id == template_id,
                DailyReportEdit.report_date == report_date,
            )
            .order_by(DailyReportEdit.created_at.desc(), DailyReportEdit.id.desc())
            .first()
        )

    def get_report_detail(
        self, tenant_id: UUID, template_id: UUID, report_date: date, source: str = "default"
    ) -> dict:
        """Get report detail with manual edit support.

        source: "default" (manual if exists else auto), "auto" (force auto), "manual" (force manual, 404 if none)
        """
        snapshot_job = self.get_latest_snapshot_version(str(tenant_id), str(template_id), report_date)
        if not snapshot_job:
            raise ProcessingError(message=f"No extraction job found for date {report_date.isoformat()}")

        latest_edit = self.get_latest_manual_edit(tenant_id, template_id, report_date)

        if source == "manual":
            if not latest_edit:
                raise ProcessingError(message=f"No manual edit found for date {report_date.isoformat()}")
            data = latest_edit.edited_data
            response_source = "manual_edit"
        elif source == "auto":
            data = self._unwrap_extracted_data(snapshot_job.extracted_data)
            response_source = "auto_sync"
        else:  # default
            if latest_edit:
                data = latest_edit.edited_data
                response_source = "manual_edit"
            else:
                data = self._unwrap_extracted_data(snapshot_job.extracted_data)
                response_source = "auto_sync"

        return {
            "date": report_date.isoformat(),
            "job_id": str(snapshot_job.id),
            "version": snapshot_job.report_version,
            "source": response_source,
            "has_manual_edits": bool(latest_edit),
            "manual_edit_id": str(latest_edit.id) if latest_edit else None,
            "data": data,
            "validation_report": snapshot_job.validation_report or {},
        }

    def save_manual_edit(
        self,
        tenant_id: UUID,
        template_id: UUID,
        report_date: date,
        edited_data: dict,
        reason: str | None = None,
        edited_by: UUID | None = None,
    ) -> dict:
        """Save manual edit without mutating ExtractionJob.extracted_data."""
        snapshot_job = self.get_latest_snapshot_version(str(tenant_id), str(template_id), report_date)
        if not snapshot_job:
            raise ProcessingError(message=f"No extraction job found for date {report_date.isoformat()}")

        # Validate edited_data
        try:
            BlockExtractionOutput.model_validate(edited_data)
        except Exception as e:
            raise ProcessingError(message=f"Invalid edited_data: {e}")

        # Create edit record
        edit = DailyReportEdit(
            tenant_id=tenant_id,
            template_id=template_id,
            report_date=report_date,
            extraction_job_id=snapshot_job.id,
            edited_data=edited_data,
            reason=reason,
            edited_by=edited_by,
        )
        self.db.add(edit)
        self.db.commit()
        self.db.refresh(edit)

        return {
            "status": "ok",
            "date": report_date.isoformat(),
            "job_id": str(snapshot_job.id),
            "edit_id": str(edit.id),
            "has_manual_edits": True,
        }
