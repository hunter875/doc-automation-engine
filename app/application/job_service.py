"""Job lifecycle manager for Engine 2 extraction."""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.domain.models.extraction_job import ExtractionJob, ExtractionJobStatus, EnrichmentStatus
from app.domain.workflow import JobStatus, transition_job_state
from app.engines.extraction.hybrid_pipeline import PipelineResult
from app.application.aggregation_service import flatten_block_output

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

        done = (
            counts.get("ready_for_review", 0) + counts.get("approved", 0)
            + counts.get("rejected", 0) + counts.get("aggregated", 0) + counts.get("failed", 0)
        )
        progress = (done / total * 100) if total > 0 else 0.0

        return {
            "batch_id": batch_id,
            "total": total,
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "extracted": counts.get("extracted", 0),
            "enriching": counts.get("enriching", 0),
            "ready_for_review": counts.get("ready_for_review", 0),
            "approved": counts.get("approved", 0),
            "rejected": counts.get("rejected", 0),
            "aggregated": counts.get("aggregated", 0),
            "failed": counts.get("failed", 0),
            "progress_percent": round(progress, 1),
        }

    def update_job_status(self, job_id: str, status: str, **kwargs) -> None:
        """DEPRECATED — use transition_job_state() instead.

        Kept temporarily for callers not yet migrated.
        """
        job = transition_job_state(
            self.db,
            job_id=job_id,
            to_state=status,
            actor_type="system",
            reason="legacy update_job_status call",
            allow_same=True,
        )

        for key, value in kwargs.items():
            if hasattr(job, key) and key != "status":
                setattr(job, key, value)

        self.db.flush()

    def set_processing(self, job: ExtractionJob, parser_used: str = "pdfplumber") -> None:
        transition_job_state(
            self.db,
            job_id=str(job.id),
            to_state=JobStatus.PROCESSING,
            actor_type="worker",
            reason="extraction started",
        )
        job.parser_used = parser_used
        self.db.flush()

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
            model_payload = flatten_block_output(model_payload)
            job.extracted_data = model_payload
            job.confidence_scores = {
                "_validation_attempts": result.attempts,
                "status": "perfect_match",
            }
            job.source_references = {}
            job.error_message = None

            # PROCESSING → EXTRACTED
            transition_job_state(
                self.db,
                job_id=str(job.id),
                to_state=JobStatus.EXTRACTED,
                actor_type="worker",
                reason="hybrid/gemini pipeline succeeded",
            )
            # Hybrid/Gemini mode: no enrichment, go straight to READY_FOR_REVIEW
            transition_job_state(
                self.db,
                job_id=str(job.id),
                to_state=JobStatus.READY_FOR_REVIEW,
                actor_type="system",
                reason="no enrichment needed (hybrid/gemini mode)",
            )
        else:
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

            transition_job_state(
                self.db,
                job_id=str(job.id),
                to_state=JobStatus.FAILED,
                actor_type="worker",
                reason=f"pipeline failed: {result.errors}",
            )

        job.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

    # ------------------------------------------------------------------
    # Two-stage persistence helpers
    # ------------------------------------------------------------------

    def persist_stage1_result(
        self,
        *,
        job: ExtractionJob,
        result: PipelineResult,
        llm_model: str,
        processing_time_ms: int,
    ) -> ExtractionJob:
        """Persist Stage-1 deterministic result.

        Transitions: PROCESSING → EXTRACTED → ENRICHING (if CNCH text) or READY_FOR_REVIEW.
        """
        job.llm_model = llm_model
        job.llm_tokens_used = 0
        job.processing_time_ms = processing_time_ms

        if result.status == "ok" and result.output:
            model_payload = result.output.model_dump() if isinstance(result.output, BaseModel) else result.output
            model_payload = flatten_block_output(model_payload)
            job.extracted_data = model_payload
            job.confidence_scores = {
                "_validation_attempts": result.attempts,
                "status": "stage1_complete",
            }
            job.source_references = {}
            job.error_message = None

            # PROCESSING → EXTRACTED
            transition_job_state(
                self.db,
                job_id=str(job.id),
                to_state=JobStatus.EXTRACTED,
                actor_type="worker",
                reason="stage1 deterministic extraction succeeded",
            )

            # EXTRACTED → ENRICHING or READY_FOR_REVIEW
            if result.chi_tiet_cnch:
                transition_job_state(
                    self.db,
                    job_id=str(job.id),
                    to_state=JobStatus.ENRICHING,
                    actor_type="system",
                    reason="CNCH text found, dispatching enrichment",
                )
                # Keep enrichment_status for audit trail (deprecated, read-only)
                job.enrichment_status = EnrichmentStatus.PENDING
            else:
                transition_job_state(
                    self.db,
                    job_id=str(job.id),
                    to_state=JobStatus.READY_FOR_REVIEW,
                    actor_type="system",
                    reason="no CNCH text, enrichment skipped",
                )
                job.enrichment_status = EnrichmentStatus.SKIPPED
        else:
            job.error_message = (
                f"Stage-1 extraction failed after {result.attempts} attempts. Errors: {result.errors}"
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
            job.enrichment_status = EnrichmentStatus.SKIPPED

            transition_job_state(
                self.db,
                job_id=str(job.id),
                to_state=JobStatus.FAILED,
                actor_type="worker",
                reason=f"stage1 failed: {result.errors}",
            )

        job.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

    def persist_enrichment_result(
        self,
        *,
        job_id: str,
        enriched_cnch: list | None,
        error: str | None = None,
    ) -> ExtractionJob:
        """Persist Stage-2 LLM enrichment result.

        Writes enriched_cnch into job.enriched_data["danh_sach_cnch"].
        NEVER touches job.extracted_data.
        Transitions job: ENRICHING → READY_FOR_REVIEW.
        """
        job = (
            self.db.query(ExtractionJob)
            .filter(ExtractionJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            raise ProcessingError(message=f"Job {job_id} not found for enrichment persistence")

        # Guard: only process jobs in ENRICHING state
        if job.status != JobStatus.ENRICHING:
            logger.warning(
                "persist_enrichment_result: job %s in state %s, not ENRICHING — skipping",
                job_id, job.status,
            )
            return job

        now = datetime.utcnow()
        if error:
            job.enrichment_error = error[:2000]
            job.enrichment_status = EnrichmentStatus.FAILED
            job.enrichment_completed_at = now
        elif enriched_cnch is not None:
            serialized = []
            for item in enriched_cnch:
                if hasattr(item, "model_dump"):
                    serialized.append(item.model_dump())
                elif isinstance(item, dict):
                    serialized.append(item)
            job.enriched_data = {"danh_sach_cnch": serialized}
            job.enrichment_status = EnrichmentStatus.ENRICHED
            job.enrichment_error = None
            job.enrichment_completed_at = now
        else:
            job.enrichment_status = EnrichmentStatus.SKIPPED

        # ENRICHING → READY_FOR_REVIEW (regardless of enrichment success/failure)
        transition_job_state(
            self.db,
            job_id=job_id,
            to_state=JobStatus.READY_FOR_REVIEW,
            actor_type="worker",
            reason=f"enrichment completed: {job.enrichment_status}",
        )

        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed_exception(self, job: ExtractionJob, error: Exception) -> None:
        job.error_message = str(error)[:2000]
        try:
            transition_job_state(
                self.db,
                job_id=str(job.id),
                to_state=JobStatus.FAILED,
                actor_type="worker",
                reason=f"unhandled exception: {str(error)[:200]}",
                allow_same=True,
            )
        except ProcessingError:
            # Already failed — just update error message
            job.updated_at = datetime.utcnow()
        job.completed_at = datetime.utcnow()
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

        if job.status != JobStatus.READY_FOR_REVIEW:
            raise ProcessingError(
                message=f"Cannot approve job with status '{job.status}'. Must be 'ready_for_review'."
            )

        # Guard: if the caller sends back the failed-job placeholder dict
        def _is_placeholder(d: dict | None) -> bool:
            if not d or not isinstance(d, dict):
                return True
            keys = set(d.keys())
            return keys <= {"_manual_review_path", "_manual_review_metadata"}

        if _is_placeholder(reviewed_data):
            reviewed_data = None
        job.reviewed_data = reviewed_data or job.final_data or job.extracted_data
        job.reviewed_by = reviewer_id
        job.reviewed_at = datetime.utcnow()
        job.review_notes = notes

        transition_job_state(
            self.db,
            job_id=job_id,
            to_state=JobStatus.APPROVED,
            actor_type="api",
            actor_id=reviewer_id,
            reason=notes or "approved by reviewer",
        )

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

        if job.status != JobStatus.READY_FOR_REVIEW:
            raise ProcessingError(
                message=f"Cannot reject job with status '{job.status}'. Must be 'ready_for_review'."
            )

        job.reviewed_by = reviewer_id
        job.reviewed_at = datetime.utcnow()
        job.review_notes = notes

        transition_job_state(
            self.db,
            job_id=job_id,
            to_state=JobStatus.REJECTED,
            actor_type="api",
            actor_id=reviewer_id,
            reason=notes,
        )

        self.db.commit()
        self.db.refresh(job)
        return job

    def retry_job(self, job_id: str, tenant_id: str) -> ExtractionJob:
        job = self.get_job(job_id, tenant_id)

        if job.status not in (JobStatus.FAILED, JobStatus.REJECTED):
            raise ProcessingError(
                message=f"Cannot retry job with status '{job.status}'. Must be 'failed' or 'rejected'."
            )

        # Clear all output data from previous run
        job.error_message = None
        job.extracted_data = None
        job.confidence_scores = None
        job.source_references = None
        job.reviewed_data = None
        job.reviewed_by = None
        job.reviewed_at = None
        job.review_notes = None
        job.completed_at = None
        # Clear enrichment state from previous run
        job.enrichment_status = None
        job.enriched_data = None
        job.enrichment_error = None
        job.enrichment_started_at = None
        job.enrichment_completed_at = None
        job.retry_count += 1

        transition_job_state(
            self.db,
            job_id=job_id,
            to_state=JobStatus.PENDING,
            actor_type="api",
            reason=f"retry #{job.retry_count}",
        )

        self.db.commit()
        self.db.refresh(job)
        return job

    def delete_job(self, job_id: str, tenant_id: str) -> None:
        job = self.get_job(job_id, tenant_id)

        if job.status not in JobStatus.DELETABLE:
            raise ProcessingError(
                message=f"Cannot delete job with status '{job.status}'. Wait until processing finishes."
            )

        self.db.delete(job)
        self.db.commit()
