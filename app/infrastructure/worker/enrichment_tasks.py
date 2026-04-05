"""Celery tasks for Stage-2 LLM enrichment (asynchronous, dedicated queue).

Stage 1 (deterministic) runs in the `extraction` worker pool and transitions
the job to ENRICHING state via the workflow state machine.

This module runs on the `enrichment` worker pool (separate concurrency limit)
and performs the only LLM call in the block pipeline: CNCHListOutput extraction
from the chi_tiet_cnch subsection text stored in extracted_data.

On completion the job transitions ENRICHING → READY_FOR_REVIEW.
On failure the job remains fully usable via Stage-1 extracted_data.
"""

from __future__ import annotations

import logging
from datetime import datetime

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from billiard.exceptions import SoftTimeLimitExceeded

# Ensure celery_app is initialized so shared_task binds to correct broker
from app.infrastructure.worker.celery_app import celery_app  # noqa: F401
from app.infrastructure.db.session import SessionLocal
from app.domain.models.extraction_job import ExtractionJob, EnrichmentStatus
from app.domain.workflow import JobStatus, transition_job_state
from app.core.exceptions import ProcessingError

# Import models so SQLAlchemy mapper is fully configured
from app.domain.models.document import Document  # noqa: F401
from app.domain.models.tenant import Tenant, UserTenantRole  # noqa: F401
from app.domain.models.user import User  # noqa: F401

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=180,
    time_limit=240,
    queue="enrichment",
)
def enrich_job_task(self, job_id: str) -> dict:
    """Run Stage-2 LLM enrichment for a single job.

    Reads chi_tiet_cnch from job.extracted_data, calls
    BlockExtractionPipeline._llm_enrich_cnch(), and persists the result
    into job.enriched_data WITHOUT touching job.extracted_data.

    Guard: only processes jobs whose status == ENRICHING.
    Transitions: ENRICHING → READY_FOR_REVIEW (success or failure).
    """
    logger.info("[Enrichment] Starting Stage-2 enrichment for job %s", job_id)

    db = SessionLocal()
    try:
        job = (
            db.query(ExtractionJob)
            .filter(ExtractionJob.id == job_id)
            .with_for_update()
            .first()
        )
        if job is None:
            logger.error("[Enrichment] Job %s not found", job_id)
            return {"job_id": job_id, "status": "not_found"}

        # Guard: only process jobs in ENRICHING state
        if job.status != JobStatus.ENRICHING:
            logger.info(
                "[Enrichment] Job %s in state %s (not ENRICHING) — skipping",
                job_id, job.status,
            )
            return {"job_id": job_id, "status": "skipped", "reason": f"state={job.status}"}

        # Mark enrichment as running (legacy column, for audit trail)
        job.enrichment_status = EnrichmentStatus.RUNNING
        job.enrichment_started_at = datetime.utcnow()
        db.commit()

        # Retrieve the chi_tiet_cnch text saved during Stage 1
        extracted = job.extracted_data or {}
        nghiep_vu = extracted.get("phan_I_va_II_chi_tiet_nghiep_vu", {}) or {}
        chi_tiet_cnch: str = nghiep_vu.get("chi_tiet_cnch", "") or ""

        if not chi_tiet_cnch.strip():
            logger.info("[Enrichment] Job %s has no chi_tiet_cnch text — marking skipped", job_id)
            job.enrichment_status = EnrichmentStatus.SKIPPED
            job.enrichment_completed_at = datetime.utcnow()
            # ENRICHING → READY_FOR_REVIEW
            transition_job_state(
                db, job_id=job_id, to_state=JobStatus.READY_FOR_REVIEW,
                actor_type="worker", reason="enrichment skipped: empty chi_tiet_cnch",
            )
            db.commit()
            return {"job_id": job_id, "status": "skipped", "reason": "empty_chi_tiet_cnch"}

        # Build a lightweight pipeline instance (only LLM extractor is needed)
        from app.engines.extraction.block_pipeline import BlockExtractionPipeline

        pipeline = BlockExtractionPipeline(job_id=str(job_id))
        enriched_cnch = pipeline._llm_enrich_cnch(chi_tiet_cnch)

        # Persist — never overwrite extracted_data
        serialized = []
        for item in enriched_cnch:
            if hasattr(item, "model_dump"):
                serialized.append(item.model_dump())
            elif isinstance(item, dict):
                serialized.append(item)

        now = datetime.utcnow()
        if serialized:
            job.enriched_data = {"danh_sach_cnch": serialized}
            job.enrichment_status = EnrichmentStatus.ENRICHED
        else:
            # LLM returned empty list — treat as skipped (not failed)
            job.enrichment_status = EnrichmentStatus.SKIPPED

        job.enrichment_error = None
        job.enrichment_completed_at = now

        # ENRICHING → READY_FOR_REVIEW
        transition_job_state(
            db, job_id=job_id, to_state=JobStatus.READY_FOR_REVIEW,
            actor_type="worker", reason=f"enrichment completed: {job.enrichment_status}",
        )
        db.commit()

        logger.info(
            "[Enrichment] Job %s done: %s incident(s) enriched, status=%s",
            job_id, len(serialized), job.enrichment_status,
        )
        return {
            "job_id": job_id,
            "status": job.enrichment_status,
            "cnch_count": len(serialized),
        }

    except SoftTimeLimitExceeded as exc:
        logger.error("[Enrichment] Soft time limit exceeded for job %s: %s", job_id, exc)
        try:
            job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
            if job:
                job.enrichment_status = EnrichmentStatus.FAILED
                job.enrichment_error = "Enrichment task timed out (soft_time_limit=180s)"
                job.enrichment_completed_at = datetime.utcnow()
                # ENRICHING → READY_FOR_REVIEW (even on timeout, job is usable via Stage-1)
                try:
                    transition_job_state(
                        db, job_id=job_id, to_state=JobStatus.READY_FOR_REVIEW,
                        actor_type="worker", reason="enrichment timeout — falling back to stage1",
                    )
                except ProcessingError:
                    pass
                db.commit()
        except Exception:
            pass
        raise

    except Exception as exc:
        logger.error("[Enrichment] Enrichment failed for job %s: %s", job_id, exc)
        error_str = str(exc)[:2000]

        try:
            job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
            if job:
                job.enrichment_status = EnrichmentStatus.FAILED
                job.enrichment_error = error_str
                job.enrichment_completed_at = datetime.utcnow()
                # Transition to READY_FOR_REVIEW — Stage-1 data is still valid
                try:
                    transition_job_state(
                        db, job_id=job_id, to_state=JobStatus.READY_FOR_REVIEW,
                        actor_type="worker", reason=f"enrichment failed: {error_str[:200]}",
                    )
                except ProcessingError:
                    pass
                db.commit()
        except Exception:
            db.rollback()

        # Retry on transient errors (LLM timeout, network)
        transient_markers = ["timeout", "connection", "temporarily", "unavailable", "bad gateway"]
        is_transient = any(m in error_str.lower() for m in transient_markers)
        if not is_transient:
            logger.warning(
                "[Enrichment] Non-transient error for job %s — not retrying: %s", job_id, exc
            )
            return {"job_id": job_id, "status": "failed", "error": error_str}

        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error(
                "[Enrichment] Max retries exceeded for job %s. Enrichment failed.", job_id
            )
            return {"job_id": job_id, "status": "failed", "error": error_str}

    finally:
        db.close()
