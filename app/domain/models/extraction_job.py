"""Extraction models for Engine 2: AI Data Automation."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.session import Base


class ExtractionTemplate(Base):
    """Template defining which fields to extract from documents."""

    __tablename__ = "extraction_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # JSON Schema defining fields to extract — see docs/engine2_technical_spec.md §3.4
    schema_definition = Column(JSONB, nullable=False)

    # Aggregation rules for Reduce phase — see docs/engine2_technical_spec.md §7
    aggregation_rules = Column(JSONB, default=dict)

    # S3 key for the original Word template (.docx) used to create this template
    word_template_s3_key = Column(String(500), nullable=True)

    # Regex pattern to auto-match uploaded filenames to this template.
    # E.g. r"PCCC.*\d{4}" or r"BC_CHAY.*".  NULL means no auto-matching.
    filename_pattern = Column(String(500), nullable=True)

    # Extraction pipeline to use: standard (hybrid LLM), block (deterministic+enrichment), vision
    extraction_mode = Column(String(20), default="standard", nullable=False, server_default="standard")

    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True, index=True)

    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", backref="extraction_templates")
    creator = relationship("User", foreign_keys=[created_by])
    jobs = relationship(
        "ExtractionJob",
        back_populates="template",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ExtractionTemplate {self.name} v{self.version}>"


class ExtractionJobStatus:
    """Extraction job status constants.

    CANONICAL REFERENCE: app.domain.workflow.JobStatus
    This class is kept for backward compatibility with existing imports.
    All values are aliased from JobStatus.
    """
    from app.domain.workflow import JobStatus as _JS

    PENDING = _JS.PENDING
    PROCESSING = _JS.PROCESSING
    EXTRACTED = _JS.EXTRACTED
    ENRICHING = _JS.ENRICHING
    READY_FOR_REVIEW = _JS.READY_FOR_REVIEW
    FAILED = _JS.FAILED
    APPROVED = _JS.APPROVED
    REJECTED = _JS.REJECTED
    AGGREGATED = _JS.AGGREGATED

    ALL = _JS.ALL

    del _JS


class EnrichmentStatus:
    """DEPRECATED — enrichment lifecycle is now tracked via job.status.

    job.status = ENRICHING replaces enrichment_status = RUNNING.
    job.status = READY_FOR_REVIEW replaces enrichment_status IN (ENRICHED, SKIPPED, FAILED).

    The enrichment_status column is retained read-only for audit/migration.
    New code MUST NOT write to enrichment_status — use transition_job_state() instead.
    """

    # Kept for backward-compat reads and migration queries
    PENDING = "pending"
    RUNNING = "running"
    ENRICHED = "enriched"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExtractionJob(Base):
    """A single extraction job: 1 PDF × 1 template."""

    __tablename__ = "extraction_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("extraction_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Batch grouping
    batch_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Extraction mode: standard (pdfplumber+Flash), vision (Pro native PDF), block (layout-aware split pipeline)
    extraction_mode = Column(String(20), default="standard", nullable=False)

    # State machine — see app.domain.workflow.JobStatus for canonical definition.
    # PENDING → PROCESSING → EXTRACTED → ENRICHING → READY_FOR_REVIEW → APPROVED → AGGREGATED
    #               ↘ FAILED     ↘ FAILED    ↘ FAILED         ↘ REJECTED → PENDING (retry)
    status = Column(String(30), default="pending", nullable=False, index=True)

    # AI output
    extracted_data = Column(JSONB, nullable=True)
    confidence_scores = Column(JSONB, nullable=True)
    source_references = Column(JSONB, nullable=True)
    debug_traces = Column(JSONB, default=list)

    # Stage 2 — LLM enrichment (non-critical, async)
    # enriched_data stores LLM-filled fields (e.g. danh_sach_cnch with all 8 fields).
    # It NEVER overwrites extracted_data (deterministic Stage 1 output).
    enrichment_status = Column(String(20), nullable=True)   # EnrichmentStatus.*
    enriched_data = Column(JSONB, nullable=True)
    enrichment_error = Column(Text, nullable=True)
    enrichment_started_at = Column(DateTime, nullable=True)
    enrichment_completed_at = Column(DateTime, nullable=True)

    # Human review
    reviewed_data = Column(JSONB, nullable=True)
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)

    # Processing metadata
    parser_used = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    llm_tokens_used = Column(Integer, default=0)
    processing_time_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", backref="extraction_jobs")
    template = relationship("ExtractionTemplate", back_populates="jobs")
    document = relationship("Document", backref="extraction_jobs")
    creator = relationship("User", foreign_keys=[created_by], backref="created_extraction_jobs")
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:
        return f"<ExtractionJob {self.id} status={self.status}>"

    @property
    def is_done(self) -> bool:
        from app.domain.workflow import JobStatus
        return self.status in JobStatus.TERMINAL

    # Keys that enriched_data is allowed to merge into extracted_data.
    # Any other key in enriched_data is silently dropped to prevent LLM
    # output from overwriting deterministic Stage-1 fields.
    _ENRICHMENT_MERGE_ALLOWLIST = frozenset({"danh_sach_cnch"})

    @property
    def final_data(self) -> dict | None:
        """Return reviewed_data if available, else the best available extraction.

        Merge priority (highest → lowest):
          reviewed_data  (human-edited, always wins)
          enriched_data  (LLM Stage 2, allowlisted keys only)
          extracted_data (deterministic Stage 1, always present)
        """
        if self.reviewed_data:
            return self.reviewed_data
        if self.extracted_data and self.enriched_data:
            merged = dict(self.extracted_data)
            for key in self._ENRICHMENT_MERGE_ALLOWLIST:
                if key in self.enriched_data:
                    merged[key] = self.enriched_data[key]
            return merged
        return self.reviewed_data or self.extracted_data

    @property
    def file_name(self) -> str | None:
        """Human-readable source file name from linked document."""
        document = getattr(self, "document", None)
        return getattr(document, "file_name", None)

    @property
    def display_name(self) -> str:
        """Friendly job label for UI lists."""
        short_id = str(self.id)[:8] if self.id else ""
        if self.file_name:
            return f"{self.file_name} ({short_id})"
        return f"Job {short_id}"


class AggregationReport(Base):
    """Aggregated report from multiple approved extraction jobs."""

    __tablename__ = "aggregation_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("extraction_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # List of job IDs included
    job_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)

    # Aggregated result from Pandas reduce
    aggregated_data = Column(JSONB, nullable=False)

    total_jobs = Column(Integer, nullable=False)
    approved_jobs = Column(Integer, nullable=False)

    status = Column(String(20), default="draft")  # draft | finalized

    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    finalized_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", backref="aggregation_reports")
    template = relationship("ExtractionTemplate", backref="reports")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<AggregationReport {self.name} ({self.status})>"
