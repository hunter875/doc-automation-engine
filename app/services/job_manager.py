"""Job lifecycle manager for Engine 2 extraction."""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.models.extraction import ExtractionJob, ExtractionJobStatus
from app.services.hybrid_extraction_pipeline import PipelineResult

logger = logging.getLogger(__name__)


class JobManager:
    """Manage extraction job lifecycle and persistence."""

    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        tenant_id: str,
        template_id: str,
        document_id: str,
        user_id: str,
        batch_id: str | None = None,
        mode: str = "standard",
    ) -> ExtractionJob:
        parser_map = {"standard": "pdfplumber", "vision": "none", "block": "pdfplumber"}
        job = ExtractionJob(
            tenant_id=tenant_id,
            template_id=template_id,
            document_id=document_id,
            batch_id=batch_id,
            extraction_mode=mode,
            parser_used=parser_map.get(mode, "pdfplumber"),
            created_by=user_id,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str, tenant_id: str) -> ExtractionJob:
        job = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.id == job_id,
                ExtractionJob.tenant_id == tenant_id,
            )
            .first()
        )
        if not job:
            raise ProcessingError(message=f"Extraction job {job_id} not found")
        return job

    def get_job_for_processing(self, job_id: str) -> ExtractionJob:
        job = self.db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
        if not job:
            raise ProcessingError(message=f"Job {job_id} not found")
        return job

    def list_jobs(
        self,
        tenant_id: str,
        page: int = 1,
        per_page: int = 50,
        status: str | None = None,
        template_id: str | None = None,
        batch_id: str | None = None,
    ) -> tuple[list[ExtractionJob], int]:
        query = self.db.query(ExtractionJob).filter(ExtractionJob.tenant_id == tenant_id)
        if status:
            query = query.filter(ExtractionJob.status == status)
        if template_id:
            query = query.filter(ExtractionJob.template_id == template_id)
        if batch_id:
            query = query.filter(ExtractionJob.batch_id == batch_id)

        total = query.count()
        items = (
            query.order_by(ExtractionJob.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return items, total

    def get_batch_status(self, batch_id: str, tenant_id: str) -> dict:
        jobs = (
            self.db.query(ExtractionJob.status, func.count(ExtractionJob.id))
            .filter(
                ExtractionJob.batch_id == batch_id,
                ExtractionJob.tenant_id == tenant_id,
            )
            .group_by(ExtractionJob.status)
            .all()
        )

        counts = {s: 0 for s in ExtractionJobStatus.ALL}
        total = 0
        for status_val, count in jobs:
            counts[status_val] = count
            total += count

        done = counts["extracted"] + counts["approved"] + counts["rejected"] + counts["failed"]
        progress = (done / total * 100) if total > 0 else 0.0

        return {
            "batch_id": batch_id,
            "total": total,
            "pending": counts["pending"],
            "processing": counts["processing"],
            "extracted": counts["extracted"],
            "approved": counts["approved"],
            "rejected": counts["rejected"],
            "failed": counts["failed"],
            "progress_percent": round(progress, 1),
        }

    def update_job_status(self, job_id: str, status: str, **kwargs) -> None:
        job = self.db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
        if not job:
            return

        job.status = status
        job.updated_at = datetime.utcnow()

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        if status in (ExtractionJobStatus.EXTRACTED, ExtractionJobStatus.FAILED):
            job.completed_at = datetime.utcnow()

        self.db.commit()

    def set_processing(self, job: ExtractionJob, parser_used: str = "pdfplumber") -> None:
        job.status = ExtractionJobStatus.PROCESSING
        job.parser_used = parser_used
        job.updated_at = datetime.utcnow()
        self.db.commit()

    def persist_pipeline_result(
        self,
        *,
        job: ExtractionJob,
        result: PipelineResult,
        llm_model: str,
        processing_time_ms: int,
    ) -> ExtractionJob:
        job.llm_model = llm_model
        job.llm_tokens_used = 0
        job.processing_time_ms = processing_time_ms

        if result.status == "ok" and result.output:
            model_payload = result.output.model_dump() if isinstance(result.output, BaseModel) else result.output
            job.extracted_data = model_payload
            job.confidence_scores = {
                "_validation_attempts": result.attempts,
                "status": "perfect_match",
            }
            job.source_references = {}
            job.status = ExtractionJobStatus.EXTRACTED
            job.error_message = None
        else:
            job.status = ExtractionJobStatus.FAILED
            job.error_message = (
                f"Hybrid extraction failed after {result.attempts} attempts. Errors: {result.errors}"
            )[:2000]
            job.extracted_data = {
                "_manual_review_path": result.manual_review_path,
                "_manual_review_metadata": result.manual_review_metadata_path,
            }
            job.confidence_scores = {
                "_validation_attempts": result.attempts,
                "status": result.status,
            }
            job.source_references = {}

        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed_exception(self, job: ExtractionJob, error: Exception) -> None:
        job.status = ExtractionJobStatus.FAILED
        job.error_message = str(error)[:2000]
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        self.db.commit()

    def approve_job(
        self,
        job_id: str,
        tenant_id: str,
        reviewer_id: str,
        reviewed_data: dict | None = None,
        notes: str | None = None,
    ) -> ExtractionJob:
        job = self.get_job(job_id, tenant_id)

        if job.status != ExtractionJobStatus.EXTRACTED:
            raise ProcessingError(
                message=f"Cannot approve job with status '{job.status}'. Must be 'extracted'."
            )

        job.status = ExtractionJobStatus.APPROVED
        job.reviewed_data = reviewed_data or job.extracted_data
        job.reviewed_by = reviewer_id
        job.reviewed_at = datetime.utcnow()
        job.review_notes = notes
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def reject_job(
        self,
        job_id: str,
        tenant_id: str,
        reviewer_id: str,
        notes: str,
    ) -> ExtractionJob:
        job = self.get_job(job_id, tenant_id)

        if job.status != ExtractionJobStatus.EXTRACTED:
            raise ProcessingError(
                message=f"Cannot reject job with status '{job.status}'. Must be 'extracted'."
            )

        job.status = ExtractionJobStatus.REJECTED
        job.reviewed_by = reviewer_id
        job.reviewed_at = datetime.utcnow()
        job.review_notes = notes
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def retry_job(self, job_id: str, tenant_id: str) -> ExtractionJob:
        job = self.get_job(job_id, tenant_id)

        if job.status not in (ExtractionJobStatus.FAILED, ExtractionJobStatus.REJECTED):
            raise ProcessingError(
                message=f"Cannot retry job with status '{job.status}'. Must be 'failed' or 'rejected'."
            )

        job.status = ExtractionJobStatus.PENDING
        job.error_message = None
        job.extracted_data = None
        job.confidence_scores = None
        job.source_references = None
        job.reviewed_data = None
        job.reviewed_by = None
        job.reviewed_at = None
        job.review_notes = None
        job.completed_at = None
        job.retry_count += 1
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def delete_job(self, job_id: str, tenant_id: str) -> None:
        job = self.get_job(job_id, tenant_id)

        if job.status in (ExtractionJobStatus.PENDING, ExtractionJobStatus.PROCESSING):
            raise ProcessingError(
                message=f"Cannot delete job with status '{job.status}'. Wait until processing finishes."
            )

        self.db.delete(job)
        self.db.commit()
