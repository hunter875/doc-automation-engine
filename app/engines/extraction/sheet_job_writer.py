"""Write validated sheet rows into extraction_jobs (JSONB) deterministically."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.application.job_service import JobManager
from app.domain.models.extraction_job import ExtractionJob
from app.domain.workflow import JobStatus, transition_job_state
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline


class JobWriter:
    """Persist validated row documents into `extraction_jobs` with idempotency."""

    def __init__(
        self,
        db: Session,
        *,
        tenant_id: str,
        template_id: str,
        document_id: str,
        user_id: str,
        sheet_id: str,
        worksheet: str,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.template_id = template_id
        self.document_id = document_id
        self.user_id = user_id
        self.sheet_id = sheet_id
        self.worksheet = worksheet
        self.job_manager = JobManager(db)
        self._existing_row_hashes = self._load_existing_row_hashes()

    def _load_existing_row_hashes(self) -> set[str]:
        rows = (
            self.db.query(ExtractionJob.source_references["row_hash"].astext)
            .filter(
                ExtractionJob.tenant_id == self.tenant_id,
                ExtractionJob.template_id == self.template_id,
                ExtractionJob.parser_used == "google_sheets",
                ExtractionJob.source_references["sheet_id"].astext == self.sheet_id,
                ExtractionJob.source_references["worksheet"].astext == self.worksheet,
            )
            .all()
        )
        return {str(row_hash) for (row_hash,) in rows if row_hash}

    @staticmethod
    def build_fingerprint(source_doc: dict[str, Any]) -> str:
        packed = json.dumps(source_doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(packed.encode("utf-8")).hexdigest()

    @staticmethod
    def build_row_hash(data_payload: dict[str, Any]) -> str:
        packed = json.dumps(data_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(packed.encode("utf-8")).hexdigest()

    def is_duplicate(self, row_hash: str) -> bool:
        return bool(row_hash and row_hash in self._existing_row_hashes)

    def write_row(
        self,
        *,
        row_document: dict[str, Any],
        confidence: dict[str, Any],
        source_references: dict[str, Any],
    ) -> tuple[bool, str | None]:
        row_hash = str(source_references.get("row_hash") or "")
        if row_hash and row_hash in self._existing_row_hashes:
            return False, None

        job = self.job_manager.create_job(
            tenant_id=self.tenant_id,
            template_id=self.template_id,
            document_id=self.document_id,
            user_id=self.user_id,
            mode="block",
        )

        transition_job_state(
            self.db,
            job_id=str(job.id),
            to_state=JobStatus.PROCESSING,
            actor_type="api",
            actor_id=self.user_id,
            reason="google sheet ingestion processing",
        )

        pipeline_result = SheetExtractionPipeline().run(
            row_document,
            schema_path=source_references.get("schema_path")
        )
        if pipeline_result.status == "ok" and pipeline_result.output is not None:
            canonical_payload: dict[str, Any] = pipeline_result.output.model_dump()
        else:
            canonical_payload = row_document
            source_references["sheet_pipeline_status"] = "failed"
            source_references["sheet_pipeline_errors"] = pipeline_result.errors

        job.extracted_data = canonical_payload
        job.confidence_scores = confidence
        job.source_references = source_references
        job.parser_used = "google_sheets"
        job.llm_model = "deterministic-sheet-v2"
        job.llm_tokens_used = 0
        job.processing_time_ms = 0
        job.error_message = None

        transition_job_state(
            self.db,
            job_id=str(job.id),
            to_state=JobStatus.EXTRACTED,
            actor_type="api",
            actor_id=self.user_id,
            reason="google sheet row normalized and validated",
        )
        transition_job_state(
            self.db,
            job_id=str(job.id),
            to_state=JobStatus.READY_FOR_REVIEW,
            actor_type="api",
            actor_id=self.user_id,
            reason="no enrichment required for sheet ingestion",
        )

        job.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)

        if row_hash:
            self._existing_row_hashes.add(row_hash)

        return True, str(job.id)
