"""Execution orchestrator for extraction jobs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ProcessingError
from app.domain.models.document import Document
from app.application.doc_service import s3_client
from app.engines.extraction.block_pipeline import BlockExtractionPipeline
from app.application.job_service import JobManager

logger = logging.getLogger(__name__)


class ExtractionOrchestrator:
    """Orchestrate storage + pipeline execution, then delegate persistence to JobManager."""

    def __init__(
        self,
        db: Session,
        *,
        job_manager: JobManager | None = None,
        pipeline_factory: Callable[[], BlockExtractionPipeline] | None = None,
    ) -> None:
        self.db = db
        self.job_manager = job_manager or JobManager(db)
        self.pipeline_factory = pipeline_factory or self._build_default_pipeline

    def _build_default_pipeline(self) -> BlockExtractionPipeline:
        """Build the block extraction pipeline."""
        return BlockExtractionPipeline(
            model=settings.OLLAMA_MODEL,
            temperature=0.0,
        )

    def run(self, job_id: str, progress_callback: Callable[[str, str], None] | None = None):
        """Execute extraction for one job_id and persist final status/result."""
        self.current_job_id = str(job_id)
        self.progress_callback = progress_callback
        job = self.job_manager.get_job_for_processing(job_id)
        self.job_manager.set_processing(job, parser_used="pdfplumber")

        try:
            document = self.db.query(Document).filter(Document.id == job.document_id).first()
            if not document:
                raise ProcessingError(message="Document not found")

            logger.info("Downloading document %s from S3", document.s3_key)
            response = s3_client.get_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=document.s3_key,
            )
            file_bytes = response["Body"].read()

            started_at = datetime.utcnow()
            pipeline = self._build_default_pipeline()

            result = pipeline.run_stage1_from_bytes(file_bytes, document.file_name)
            elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)

            saved_job = self.job_manager.persist_stage1_result(
                job=job,
                result=result,
                llm_model=settings.OLLAMA_MODEL,
                processing_time_ms=elapsed_ms,
            )

            # Dispatch enrichment task if Stage 1 transitioned to ENRICHING
            from app.domain.workflow import JobStatus
            if saved_job.status == JobStatus.ENRICHING:
                from app.infrastructure.worker.enrichment_tasks import enrich_job_task
                enrich_job_task.apply_async(
                    args=[str(saved_job.id)],
                    queue="enrichment",
                )
                logger.info("Enrichment task dispatched for job %s", job_id)

            logger.info(
                "Extraction orchestrator completed job %s: status=%s, attempts=%s, processing_time_ms=%s",
                job_id,
                saved_job.status,
                getattr(result, "attempts", 1),
                elapsed_ms,
            )
            return saved_job

        except Exception as exc:
            logger.error("Extraction orchestrator failed for job %s: %s", job_id, exc)
            self.job_manager.mark_failed_exception(job, exc)
            raise

