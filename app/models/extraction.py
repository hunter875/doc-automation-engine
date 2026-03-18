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

from app.db.postgres import Base


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
    """Extraction job status constants."""

    PENDING = "pending"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    FAILED = "failed"
    APPROVED = "approved"
    REJECTED = "rejected"

    ALL = [PENDING, PROCESSING, EXTRACTED, FAILED, APPROVED, REJECTED]


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

    # Extraction mode: standard (Docling+Flash), vision (Pro native PDF), fast (pdfplumber+Flash)
    extraction_mode = Column(String(20), default="standard", nullable=False)

    # State machine: pending → processing → extracted → approved
    #                                     ↘ failed      ↘ rejected
    status = Column(String(20), default="pending", nullable=False, index=True)

    # AI output
    extracted_data = Column(JSONB, nullable=True)
    confidence_scores = Column(JSONB, nullable=True)
    source_references = Column(JSONB, nullable=True)

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
        return self.status in (
            ExtractionJobStatus.EXTRACTED,
            ExtractionJobStatus.APPROVED,
        )

    @property
    def final_data(self) -> dict | None:
        """Return reviewed_data if available, else extracted_data."""
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
