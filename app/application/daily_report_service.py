"""Service for reading DailyReports from snapshot ingestion jobs."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.models.extraction_job import ExtractionJob
from app.application.job_service import JobManager
from app.application.aggregation_service import AggregationService


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
