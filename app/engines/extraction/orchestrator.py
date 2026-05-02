"""Execution orchestrator for extraction jobs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ProcessingError
from app.domain.models.document import Document
from app.application.doc_service import s3_client
from app.engines.extraction.pipeline_registry import PipelineRegistry, get_default_registry
from app.engines.extraction.schemas import BlockExtractionOutput, PipelineResult
from app.application.job_service import JobManager

logger = logging.getLogger(__name__)


class ExtractionOrchestrator:
    """Orchestrate storage + pipeline execution, then delegate persistence to JobManager.

    The orchestrator is the SINGLE entry point for all extraction execution.
    It resolves the appropriate pipeline via PipelineRegistry based on parser_used,
    executes it, and ensures the output is canonical BlockExtractionOutput.
    """

    def __init__(
        self,
        db: Session,
        *,
        job_manager: JobManager | None = None,
        pipeline_registry: PipelineRegistry | None = None,
    ) -> None:
        self.db = db
        self.job_manager = job_manager or JobManager(db)
        self.pipeline_registry = pipeline_registry or get_default_registry()

    def run(
        self,
        job_id: str,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> ExtractionJob:
        """Execute extraction for one job_id and persist final status/result.

        The orchestrator loads the job, inspects job.parser_used, resolves the
        appropriate pipeline from the registry, executes it, and persists the result.

        For Google Sheets jobs created by ingestion service, if the job already
        has extracted_data (from DailyReportBuilder), we skip the pipeline and
        directly finalize the job.
        """
        self.current_job_id = str(job_id)
        self.progress_callback = progress_callback
        job = self.job_manager.get_job_for_processing(job_id)

        # Determine parser from job.parser_used (set by ingestion or PDF upload)
        parser_used = str(job.parser_used or "").lower()
        if parser_used in {"google_sheets", "sheet"}:
            pipeline_parser = "google_sheets"
        else:
            pipeline_parser = "pdfplumber"

        # Check if this is a pre-processed sheet job from ingestion service
        is_preprocessed_sheet = (
            pipeline_parser == "google_sheets" and
            job.extracted_data and
            isinstance(job.extracted_data, dict) and
            job.extracted_data.get("header") is not None  # has extraction output
        )

        if not is_preprocessed_sheet:
            self.job_manager.set_processing(job, parser_used=pipeline_parser)
        else:
            logger.info(f"Job {job_id} is pre-processed Google Sheet, skipping pipeline execution")
            # Job already complete from ingestion; return as-is without further processing
            return job

        try:
            started_at = datetime.utcnow()

            # Resolve pipeline from registry
            pipeline_factory = self.pipeline_registry.resolve(pipeline_parser)
            pipeline = pipeline_factory()

            # Prepare pipeline inputs based on parser type
            if pipeline_parser in {"google_sheets", "sheet"}:
                # Sheet pipeline: check if job already has extracted_data from ingestion
                if job.extracted_data and isinstance(job.extracted_data, dict) and job.extracted_data.get("header"):
                    # Job was already processed by ingestion service, skip pipeline
                    logger.info(f"Job {job_id} already has extracted_data from ingestion, skipping pipeline")
                    # Create a dummy PipelineResult from existing data
                    from app.engines.extraction.schemas import PipelineResult, BlockExtractionOutput
                    try:
                        output = BlockExtractionOutput.model_validate(job.extracted_data)
                        result = PipelineResult(
                            status="ok",
                            attempts=1,
                            output=output,
                            errors=[],
                            chi_tiet_cnch="",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to validate existing extracted_data for job {job_id}: {e}")
                        # Fall through to run pipeline with default mapping
                        result = pipeline.run(job.extracted_data)
                else:
                    # Sheet pipeline: read raw sheet data from job.extracted_data
                    if not job.extracted_data:
                        raise ProcessingError(message="Sheet job missing extracted_data (raw sheet payload)")
                    result = pipeline.run(job.extracted_data)
            else:
                # PDF pipeline: download document from S3
                document = self.db.query(Document).filter(Document.id == job.document_id).first()
                if not document:
                    raise ProcessingError(message="Document not found")

                logger.info("Downloading document %s from S3", document.s3_key)
                response = s3_client.get_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=document.s3_key,
                )
                file_bytes = response["Body"].read()

                # BlockExtractionPipeline expects: run_stage1_from_bytes(file_bytes, filename)
                from app.engines.extraction.block_pipeline import BlockExtractionPipeline
                if isinstance(pipeline, BlockExtractionPipeline):
                    # Adapt BlockExtractionPipeline to the run() interface
                    result = pipeline.run_stage1_from_bytes(file_bytes, document.file_name)
                else:
                    result = pipeline.run(file_bytes, filename=document.file_name)

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

