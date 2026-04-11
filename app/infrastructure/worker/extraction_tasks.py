"""Celery tasks for Engine 2: Extraction pipeline."""

import logging
from datetime import datetime, timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from billiard.exceptions import SoftTimeLimitExceeded

# Ensure celery_app is initialized so shared_task binds to correct broker
from app.infrastructure.worker.celery_app import celery_app  # noqa: F401
from app.core.config import settings
from app.core.logger import classify_error, log_debug_step
from app.infrastructure.db.session import SessionLocal
from app.domain.models.extraction_job import ExtractionJob, ExtractionJobStatus
from app.domain.workflow import JobStatus, transition_job_state
from app.utils.debug_trace import append_debug_trace

# Import models so SQLAlchemy mapper is fully configured
from app.domain.models.document import Document  # noqa: F401
from app.domain.models.tenant import Tenant, UserTenantRole  # noqa: F401
from app.domain.models.user import User  # noqa: F401

logger = logging.getLogger(__name__)


def _is_retriable_error(error: Exception) -> bool:
    """Return True only for transient errors that are worth retrying."""
    message = str(error).lower()

    non_retriable_markers = [
        "resource_exhausted",
        "quota exceeded",
        "too many requests",
        " 429 ",
        "validation error for",
        "err_schema_validation",
        "thoi_gian không đúng định dạng",
        "value error",
        "job not found",
        "extraction job",
        "template not found",
        "document not found",
        "template or document not found",
        "json_parse_error",
        "soft time limit exceeded",
    ]
    if any(marker in message for marker in non_retriable_markers):
        return False

    retriable_markers = [
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "connection refused",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "network",
    ]
    return any(marker in message for marker in retriable_markers)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=600,
    time_limit=720,
)
def extract_document_task(self, job_id: str):
    """Run the block extraction pipeline for a single job.

    Steps:
      1. Load job from DB, set status='processing'
      2. Download PDF from MinIO (via document.s3_key)
      3. Run BlockExtractionPipeline Stage 1 from in-memory bytes
      4. Save extracted JSON or manual-review metadata
      5. Update job status and processing metadata

    On failure:
      - Retry with exponential backoff (30s → 60s → 120s)
      - After max retries → status='failed'
    """
    logger.info(f"[Engine2] Starting extraction for job {job_id}")

    db = SessionLocal()

    try:
        from app.engines.extraction.orchestrator import ExtractionOrchestrator

        def emit_progress(step_name: str, trace_id: str) -> None:
            """Push real-time progress to Celery state and lightweight DB traces."""
            self.update_state(
                state="PROCESSING",
                meta={
                    "step": step_name,
                    "job_id": str(job_id),
                    "trace_id": str(trace_id),
                },
            )

            job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
            if job is None:
                return
            append_debug_trace(job, step=step_name, status="success", error_type=None)
            db.commit()

        orchestrator = ExtractionOrchestrator(db)
        job = orchestrator.run(job_id, progress_callback=emit_progress)

        logger.info(
            f"[Engine2] Extraction complete for job {job_id}: "
            f"status={job.status}, tokens={job.llm_tokens_used}"
        )

        return {
            "job_id": str(job.id),
            "status": job.status,
            "tokens_used": job.llm_tokens_used,
            "processing_time_ms": job.processing_time_ms,
        }

    except SoftTimeLimitExceeded as e:
        logger.error(f"[Engine2] Extraction timeout for job {job_id}: {e}")
        try:
            transition_job_state(
                db, job_id=job_id, to_state=JobStatus.FAILED,
                actor_type="worker", reason="soft time limit exceeded",
                allow_same=True,
            )
            job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
            if job:
                job.error_message = "Task timed out (soft_time_limit=300s)"
                job.completed_at = datetime.utcnow()
            db.commit()
        except Exception:
            pass
        raise

    except Exception as e:
        logger.error(f"[Engine2] Extraction failed for job {job_id}: {e}")
        error_type = classify_error(e) or "LOGIC_ERROR"

        try:
            failed_job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
            if failed_job is not None:
                append_debug_trace(
                    failed_job,
                    step="extract_document_task",
                    status="failed",
                    error_type=error_type,
                )
                db.commit()
        except Exception:
            db.rollback()

        log_debug_step(
            job_id=str(job_id),
            step="extract_document_task",
            status="failed",
            error=e,
            retry_count=int(getattr(self.request, "retries", 0) or 0),
            trace_id=getattr(self.request, "id", None),
        )

        # Do not retry deterministic/non-recoverable errors.
        if not _is_retriable_error(e):
            logger.warning(f"[Engine2] Non-retriable error for job {job_id}. Skipping retries.")
            try:
                transition_job_state(
                    db, job_id=job_id, to_state=JobStatus.FAILED,
                    actor_type="worker", reason=f"non-retriable: {str(e)[:200]}",
                    allow_same=True,
                )
                job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
                if job:
                    job.error_message = str(e)[:500]
                    job.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                pass
            raise

        # Try to retry
        try:
            current_retries = int(getattr(self.request, "retries", 0) or 0)
            retry_job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
            if retry_job is not None:
                retry_job.retry_count = current_retries + 1
                db.commit()

            log_debug_step(
                job_id=str(job_id),
                step="extract_document_task_retry",
                status="failed",
                error=e,
                retry_count=current_retries + 1,
                trace_id=getattr(self.request, "id", None),
            )
            self.retry(exc=e)
        except MaxRetriesExceededError:
            # Mark as failed after all retries exhausted
            try:
                transition_job_state(
                    db, job_id=job_id, to_state=JobStatus.FAILED,
                    actor_type="worker", reason=f"max retries exceeded: {str(e)[:200]}",
                    allow_same=True,
                )
                job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
                if job:
                    job.error_message = f"Max retries exceeded: {str(e)[:500]}"
                    job.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                pass
            raise

    finally:
        db.close()


@shared_task
def cleanup_stuck_extraction_jobs():
    """Mark extraction jobs stuck in 'processing' or 'enriching' as failed.

    Runs periodically via Celery Beat.
    """
    logger.info("[Engine2] Running stuck job cleanup")

    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=settings.EXTRACTION_TIMEOUT_MINUTES)

        stuck_jobs = (
            db.query(ExtractionJob)
            .filter(
                ExtractionJob.status.in_([
                    ExtractionJobStatus.PROCESSING,
                    JobStatus.ENRICHING,
                ]),
                ExtractionJob.updated_at < cutoff,
            )
            .all()
        )

        fixed = 0
        for job in stuck_jobs:
            logger.warning(f"[Engine2] Marking stuck job as failed: {job.id} (was {job.status})")
            try:
                transition_job_state(
                    db, job_id=str(job.id), to_state=JobStatus.FAILED,
                    actor_type="beat", reason=f"stuck in {job.status} for >{settings.EXTRACTION_TIMEOUT_MINUTES}min",
                )
                job.error_message = f"Processing timeout (>{settings.EXTRACTION_TIMEOUT_MINUTES}min)"
                job.completed_at = datetime.utcnow()
                fixed += 1
            except Exception as e:
                logger.error(f"[Engine2] Failed to mark stuck job {job.id}: {e}")

        db.commit()
        logger.info(f"[Engine2] Cleanup complete: {fixed} stuck jobs fixed")
        return {"stuck_jobs_fixed": fixed}

    except Exception as e:
        logger.error(f"[Engine2] Cleanup task failed: {e}")
        raise

    finally:
        db.close()
