"""Celery tasks for Engine 2: Extraction pipeline."""

import logging
from datetime import datetime, timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from billiard.exceptions import SoftTimeLimitExceeded

# Ensure celery_app is initialized so shared_task binds to correct broker
from app.worker.celery_app import celery_app  # noqa: F401
from app.core.config import settings
from app.db.postgres import SessionLocal
from app.models.extraction import ExtractionJob, ExtractionJobStatus

# Import models so SQLAlchemy mapper is fully configured
from app.models.document import Document  # noqa: F401
from app.models.tenant import Tenant, UserTenantRole  # noqa: F401
from app.models.user import User  # noqa: F401

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
    soft_time_limit=300,
    time_limit=360,
)
def extract_document_task(self, job_id: str):
    """Run the Hybrid extraction pipeline for a single job.

    Steps:
      1. Load job from DB, set status='processing'
      2. Download PDF from MinIO (via document.s3_key)
    3. Run HybridExtractionPipeline from in-memory bytes
    4. Save extracted JSON or manual-review metadata
    5. Update job status and processing metadata

    On failure:
      - Retry with exponential backoff (30s → 60s → 120s)
      - After max retries → status='failed'
    """
    logger.info(f"[Engine2] Starting extraction for job {job_id}")

    db = SessionLocal()

    try:
        from app.services.extraction_orchestrator import ExtractionOrchestrator

        orchestrator = ExtractionOrchestrator(db)
        job = orchestrator.run(job_id)

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
            job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
            if job and job.status != ExtractionJobStatus.FAILED:
                job.status = ExtractionJobStatus.FAILED
                job.error_message = "Task timed out (soft_time_limit=300s)"
                job.completed_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        raise

    except Exception as e:
        logger.error(f"[Engine2] Extraction failed for job {job_id}: {e}")

        # Do not retry deterministic/non-recoverable errors.
        if not _is_retriable_error(e):
            logger.warning(f"[Engine2] Non-retriable error for job {job_id}. Skipping retries.")
            try:
                job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
                if job and job.status != ExtractionJobStatus.FAILED:
                    job.status = ExtractionJobStatus.FAILED
                    job.error_message = str(e)[:500]
                    job.completed_at = datetime.utcnow()
                    job.updated_at = datetime.utcnow()
                    db.commit()
            except Exception:
                pass
            raise

        # Try to retry
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            # Mark as failed after all retries exhausted
            try:
                job = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
                if job and job.status != ExtractionJobStatus.FAILED:
                    job.status = ExtractionJobStatus.FAILED
                    job.error_message = f"Max retries exceeded: {str(e)[:500]}"
                    job.completed_at = datetime.utcnow()
                    job.updated_at = datetime.utcnow()
                    db.commit()
            except Exception:
                pass
            raise

    finally:
        db.close()


@shared_task
def cleanup_stuck_extraction_jobs():
    """Mark extraction jobs stuck in 'processing' > 30 min as failed.

    Runs periodically via Celery Beat.
    """
    logger.info("[Engine2] Running stuck job cleanup")

    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=settings.EXTRACTION_TIMEOUT_MINUTES)

        stuck_jobs = (
            db.query(ExtractionJob)
            .filter(
                ExtractionJob.status == ExtractionJobStatus.PROCESSING,
                ExtractionJob.updated_at < cutoff,
            )
            .all()
        )

        for job in stuck_jobs:
            logger.warning(f"[Engine2] Marking stuck extraction job as failed: {job.id}")
            job.status = ExtractionJobStatus.FAILED
            job.error_message = f"Processing timeout (>{settings.EXTRACTION_TIMEOUT_MINUTES}min)"
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()

        db.commit()

        logger.info(f"[Engine2] Cleanup complete: {len(stuck_jobs)} stuck jobs fixed")

        return {"stuck_jobs_fixed": len(stuck_jobs)}

    except Exception as e:
        logger.error(f"[Engine2] Cleanup task failed: {e}")
        raise

    finally:
        db.close()
