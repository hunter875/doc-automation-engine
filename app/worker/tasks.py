"""Celery background tasks."""

import logging
from datetime import datetime, timedelta

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

# Ensure celery_app is initialized so shared_task binds to correct broker
from app.worker.celery_app import celery_app  # noqa: F401
from app.core.config import settings
from app.core.exceptions import ProcessingError
from app.db.postgres import SessionLocal
from app.models.document import Document
from app.models.tenant import Tenant, UserTenantRole  # noqa: F401 - needed for SQLAlchemy mapper
from app.models.user import User  # noqa: F401 - needed for SQLAlchemy mapper
from app.services.chunking import ChunkingStrategy
from app.services.doc_service import DocumentService
from app.services.rag_service import DocumentProcessor, RAGService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_document_task(
    self,
    document_id: str,
    tenant_id: str,
    strategy: str = "recursive",
    chunk_size: int = None,
    chunk_overlap: int = None,
):
    """Process uploaded document: extract text, chunk, embed, index.

    Args:
        self: Celery task instance
        document_id: Document UUID
        tenant_id: Tenant UUID
        strategy: Chunking strategy name
        chunk_size: Override chunk size
        chunk_overlap: Override chunk overlap

    Returns:
        Task result dict
    """
    logger.info(f"Processing document {document_id} for tenant {tenant_id}")

    db = SessionLocal()

    try:
        # Get document
        doc_service = DocumentService(db)
        document = doc_service.get_document(document_id, tenant_id)

        # Update status to processing
        doc_service.update_document_status(
            document_id=document_id,
            status="processing",
        )

        # Download file content from S3
        content_bytes = doc_service.download_from_s3(document.s3_key)

        # Extract text
        text_content = DocumentProcessor.extract_text(
            content=content_bytes,
            mime_type=document.mime_type,
        )

        if not text_content or not text_content.strip():
            raise ProcessingError(
                message="No text content extracted from document",
            )

        # Parse strategy
        try:
            chunking_strategy = ChunkingStrategy(strategy)
        except ValueError:
            chunking_strategy = ChunkingStrategy.RECURSIVE

        # Process: chunk, embed, index
        rag_service = RAGService(db)
        chunk_count = rag_service.process_document(
            document_id=document_id,
            content=text_content,
            tenant_id=tenant_id,
            strategy=chunking_strategy,
            chunk_size=chunk_size or settings.CHUNK_SIZE,
            chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
        )

        # Update status to processed
        doc_service.update_document_status(
            document_id=document_id,
            status="completed",
            chunk_count=chunk_count,
        )

        logger.info(
            f"Successfully processed document {document_id}: {chunk_count} chunks"
        )

        return {
            "document_id": document_id,
            "status": "processed",
            "chunk_count": chunk_count,
        }

    except ProcessingError as e:
        logger.error(f"Processing error for document {document_id}: {e}")

        # Update status to failed
        try:
            doc_service.update_document_status(
                document_id=document_id,
                status="failed",
                error_message=str(e),
            )
        except Exception:
            pass

        raise

    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}")

        # Check if we should retry
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            # Update status to failed after max retries
            try:
                doc_service.update_document_status(
                    document_id=document_id,
                    status="failed",
                    error_message=f"Max retries exceeded: {str(e)}",
                )
            except Exception:
                pass
            raise

    finally:
        db.close()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def generate_embeddings_task(
    self,
    texts: list[str],
    document_id: str = None,
):
    """Generate embeddings for text chunks.

    Args:
        self: Celery task instance
        texts: List of text chunks
        document_id: Optional document ID for logging

    Returns:
        List of embeddings
    """
    from app.services.embedding import EmbeddingService

    logger.info(f"Generating embeddings for {len(texts)} chunks")

    try:
        embedding_service = EmbeddingService()
        embeddings, token_count = embedding_service.embed_with_token_count(texts)

        logger.info(
            f"Generated {len(embeddings)} embeddings, "
            f"total tokens: {token_count}"
        )

        return {
            "embeddings_count": len(embeddings),
            "token_count": token_count,
            "embeddings": embeddings,
        }

    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            raise


@shared_task(
    bind=True,
    max_retries=2,
)
def reindex_document_task(
    self,
    document_id: str,
    tenant_id: str,
):
    """Re-index an existing document.

    Args:
        self: Celery task instance
        document_id: Document UUID
        tenant_id: Tenant UUID

    Returns:
        Task result dict
    """
    from app.db.pgvector import delete_document_chunks

    logger.info(f"Re-indexing document {document_id}")

    db = SessionLocal()

    try:
        # Delete existing chunks from PostgreSQL
        delete_document_chunks(db, document_id, tenant_id)

        # Process document again
        result = process_document_task(
            document_id=document_id,
            tenant_id=tenant_id,
        )

        return result

    except Exception as e:
        logger.error(f"Re-index failed for document {document_id}: {e}")
        self.retry(exc=e)

    finally:
        db.close()


@shared_task
def cleanup_expired_tasks():
    """Cleanup expired task results and stale documents.

    This runs periodically via Celery Beat.
    """
    logger.info("Running cleanup task")

    db = SessionLocal()

    try:
        # Find documents stuck in PROCESSING for too long
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


@shared_task(
    bind=True,
    max_retries=1,
)
def bulk_process_documents_task(
    self,
    document_ids: list[str],
    tenant_id: str,
):
    """Process multiple documents in sequence.

    Args:
        self: Celery task instance
        document_ids: List of document UUIDs
        tenant_id: Tenant UUID

    Returns:
        Bulk processing results
    """
    logger.info(f"Bulk processing {len(document_ids)} documents")

    results = {
        "successful": [],
        "failed": [],
    }

    for doc_id in document_ids:
        try:
            result = process_document_task(
                document_id=doc_id,
                tenant_id=tenant_id,
            )
            results["successful"].append(doc_id)
        except Exception as e:
            logger.error(f"Failed to process document {doc_id}: {e}")
            results["failed"].append({
                "document_id": doc_id,
                "error": str(e),
            })

    logger.info(
        f"Bulk processing completed: "
        f"{len(results['successful'])} successful, "
        f"{len(results['failed'])} failed"
    )

    return results


@shared_task
def send_notification_task(
    user_id: str,
    notification_type: str,
    data: dict,
):
    """Send notification to user (placeholder for future implementation).

    Args:
        user_id: User UUID
        notification_type: Type of notification
        data: Notification data

    Returns:
        Notification result
    """
    logger.info(f"Sending {notification_type} notification to user {user_id}")

    # Placeholder - implement actual notification logic
    # (email, websocket, push notification, etc.)

    return {
        "user_id": user_id,
        "notification_type": notification_type,
        "status": "sent",
    }
