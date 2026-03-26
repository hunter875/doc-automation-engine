"""Execution orchestrator for extraction jobs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ProcessingError
from app.models.document import Document
from app.services.doc_service import s3_client
from app.services.block_extraction_pipeline import BlockExtractionPipeline
from app.services.extractor_strategies import OllamaInstructorExtractor
from app.services.hybrid_extraction_pipeline import HybridExtractionPipeline
from app.services.job_manager import JobManager
from app.services.rule_engine import RuleEngine, build_default_hybrid_rule_engine

logger = logging.getLogger(__name__)


class ExtractionOrchestrator:
    """Orchestrate storage + pipeline execution, then delegate persistence to JobManager."""

    def __init__(
        self,
        db: Session,
        *,
        job_manager: JobManager | None = None,
        pipeline_factory: Callable[[], HybridExtractionPipeline] | None = None,
        rule_engine: RuleEngine | None = None,
    ) -> None:
        self.db = db
        self.job_manager = job_manager or JobManager(db)
        self.rule_engine = rule_engine or build_default_hybrid_rule_engine()
        self.pipeline_factory = pipeline_factory or self._build_default_pipeline

    def _build_default_pipeline(self) -> HybridExtractionPipeline:
        """Build extraction pipeline using configured backend."""
        # Get extraction mode from job if available, otherwise use config
        extraction_mode = getattr(self, 'extraction_mode', 'standard')
        pipeline_job_id = getattr(self, 'current_job_id', None)
        pipeline_progress_callback = getattr(self, 'progress_callback', None)
        
        if settings.EXTRACTION_BACKEND.lower() == "gemini":
            from app.services.extractor_strategies import GeminiExtractor, GeminiVisionExtractor
            
            # Use vision extractor for vision mode, standard for others
            if extraction_mode == "vision":
                extractor = GeminiVisionExtractor(api_key=settings.GEMINI_API_KEY)
            else:
                extractor = GeminiExtractor(api_key=settings.GEMINI_API_KEY)
            
            model = settings.GEMINI_CHAT_MODEL or settings.GEMINI_FLASH_MODEL
        else:
            # Default to Ollama
            extractor = OllamaInstructorExtractor(
                base_url=settings.OLLAMA_BASE_URL,
                api_key=settings.OLLAMA_API_KEY,
            )
            model = settings.OLLAMA_MODEL

        if extraction_mode == "block":
            return BlockExtractionPipeline(
                job_id=pipeline_job_id,
                progress_callback=pipeline_progress_callback,
                model=model,
                temperature=0.0,
            )
        
        return HybridExtractionPipeline(
            job_id=pipeline_job_id,
            progress_callback=pipeline_progress_callback,
            model=model,
            temperature=0.0,
            extractor=extractor,
            rule_engine=self.rule_engine,
            extraction_mode=extraction_mode,
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
            self.extraction_mode = job.extraction_mode or "standard"
            pipeline = self.pipeline_factory()
            result = pipeline.run_from_bytes(file_bytes, document.file_name)
            elapsed_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)

            saved_job = self.job_manager.persist_pipeline_result(
                job=job,
                result=result,
                llm_model=settings.GEMINI_CHAT_MODEL if settings.EXTRACTION_BACKEND.lower() == "gemini" else settings.OLLAMA_MODEL,
                processing_time_ms=elapsed_ms,
            )

            logger.info(
                "Extraction orchestrator completed job %s: status=%s, attempts=%s, processing_time_ms=%s",
                job_id,
                saved_job.status,
                result.attempts,
                elapsed_ms,
            )
            return saved_job

        except Exception as exc:
            logger.error("Extraction orchestrator failed for job %s: %s", job_id, exc)
            self.job_manager.mark_failed_exception(job, exc)
            raise
