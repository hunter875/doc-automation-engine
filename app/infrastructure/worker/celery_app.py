"""Celery application configuration."""

import logging

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging(
    log_level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    log_file=settings.LOG_FILE,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT,
)

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "rag_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.infrastructure.worker.tasks",
        "app.infrastructure.worker.extraction_tasks",
        "app.infrastructure.worker.enrichment_tasks",
        "app.infrastructure.worker.operator_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    
    # Result backend settings
    result_expires=3600,  # 1 hour
    
    # Task routing
    task_routes={
        "app.infrastructure.worker.tasks.process_document_task": {"queue": "document_processing"},
        "app.infrastructure.worker.tasks.generate_embeddings_task": {"queue": "embeddings"},
        "app.infrastructure.worker.extraction_tasks.extract_document_task": {"queue": "extraction"},
        # Enrichment queue — separate worker pool, lower concurrency to bound LLM load
        "app.infrastructure.worker.enrichment_tasks.enrich_job_task": {"queue": "enrichment"},
    },
    
    # Default queue
    task_default_queue="default",
    
    # Retry settings
    task_annotations={
        "app.infrastructure.worker.tasks.process_document_task": {
            "rate_limit": "10/m",
            "max_retries": 3,
        },
        "app.infrastructure.worker.extraction_tasks.extract_document_task": {
            "rate_limit": "10/m",
            "max_retries": 3,
        },
    },
    
    # Beat scheduler (for periodic tasks)
    beat_schedule={
        "cleanup-expired-tasks": {
            "task": "app.infrastructure.worker.tasks.cleanup_expired_tasks",
            "schedule": 3600.0,  # Every hour
        },
        "cleanup-stuck-extraction-jobs": {
            "task": "app.infrastructure.worker.extraction_tasks.cleanup_stuck_extraction_jobs",
            "schedule": 1800.0,  # Every 30 minutes
        },
        "file-operator-poll-inbox": {
            "task": "app.infrastructure.worker.operator_tasks.poll_inbox",
            "schedule": float(settings.FILE_OPERATOR_POLL_SECONDS),
        },
        "batch-closer": {
            "task": "app.infrastructure.worker.operator_tasks.close_completed_batches",
            "schedule": float(settings.BATCH_CLOSER_POLL_SECONDS),
        },
    },
)


def get_celery_app() -> Celery:
    """Get Celery application instance.
    
    Returns:
        Configured Celery app
    """
    return celery_app
