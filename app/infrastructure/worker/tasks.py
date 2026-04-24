"""Celery background tasks."""

import logging
from datetime import datetime, timedelta

from celery import shared_task

# Ensure celery_app is initialized so shared_task binds to correct broker
from app.infrastructure.worker.celery_app import celery_app  # noqa: F401
from app.infrastructure.db.session import SessionLocal
from app.domain.models.document import Document

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_tasks():
    """Cleanup stale documents stuck in PROCESSING state.

    This runs periodically via Celery Beat.
    """
    logger.info("Running cleanup task")

    db = SessionLocal()

    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=2)

        stuck_documents = (
            db.query(Document)
            .filter(
                Document.status == "processing",
                Document.created_at < cutoff_time,
            )
            .all()
        )

        for doc in stuck_documents:
            logger.warning(f"Marking stuck document as failed: {doc.id}")
            doc.status = "failed"
            doc.processed_at = datetime.utcnow()

        db.commit()

        logger.info(f"Cleanup completed: {len(stuck_documents)} stuck documents fixed")

        return {
            "stuck_documents_fixed": len(stuck_documents),
        }

    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        raise

    finally:
        db.close()


@shared_task
def send_notification_task(
    user_id: str,
    notification_type: str,
    data: dict,
):
    """Send notification to user (placeholder for future implementation)."""
    logger.info(f"Sending {notification_type} notification to user {user_id}")

    return {
        "user_id": user_id,
        "notification_type": notification_type,
        "status": "sent",
    }
