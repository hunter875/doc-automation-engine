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
            self.db.query(ExtractionJob.source_references)
            .filter(
                ExtractionJob.tenant_id == self.tenant_id,
                ExtractionJob.template_id == self.template_id,
                ExtractionJob.parser_used == "google_sheets",
            )
            .all()
        )
        found: set[str] = set()
        for (source_ref,) in rows:
            if not isinstance(source_ref, dict):
                continue
            if source_ref.get("sheet_id") != self.sheet_id or source_ref.get("worksheet") != self.worksheet:
                continue
            row_hash = source_ref.get("row_hash")
            if row_hash:
                found.add(str(row_hash))
        return found

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

        job.extracted_data = row_document
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
