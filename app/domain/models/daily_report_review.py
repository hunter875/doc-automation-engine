import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.infrastructure.db.session import Base


class DailyReportReview(Base):
    __tablename__ = "daily_report_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("extraction_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    report_date = Column(Date, nullable=False, index=True)

    extraction_job_id = Column(UUID(as_uuid=True), ForeignKey("extraction_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    manual_edit_id = Column(UUID(as_uuid=True), ForeignKey("daily_report_edits.id", ondelete="SET NULL"), nullable=True, index=True)

    status = Column(String(30), nullable=False, index=True)
    approved_data = Column(JSONB, nullable=True)
    approved_source = Column(String(20), nullable=True)  # "auto_sync" or "manual_edit"
    reason = Column(Text, nullable=True)

    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)

    base_extraction_job_id = Column(UUID(as_uuid=True), ForeignKey("extraction_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    base_extraction_hash = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    template = relationship("ExtractionTemplate")
    extraction_job = relationship("ExtractionJob", foreign_keys=[extraction_job_id])
    manual_edit = relationship("DailyReportEdit")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    base_extraction_job = relationship("ExtractionJob", foreign_keys=[base_extraction_job_id])

    __table_args__ = (
        Index("ix_daily_report_reviews_lookup", "tenant_id", "template_id", "report_date", "created_at"),
        Index("ix_daily_report_reviews_tenant_template_date_status", "tenant_id", "template_id", "report_date", "status"),
    )
