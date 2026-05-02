import uuid
from sqlalchemy import Column, Date, DateTime, ForeignKey, Text, Index, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.infrastructure.db.session import Base

class DailyReportEdit(Base):
    __tablename__ = "daily_report_edits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("extraction_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    report_date = Column(Date, nullable=False, index=True)
    extraction_job_id = Column(UUID(as_uuid=True), ForeignKey("extraction_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    edited_data = Column(JSONB, nullable=False)
    reason = Column(Text, nullable=True)
    edited_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant")
    template = relationship("ExtractionTemplate")
    extraction_job = relationship("ExtractionJob")
    editor = relationship("User", foreign_keys=[edited_by])

    __table_args__ = (
        Index("ix_daily_report_edits_lookup", "tenant_id", "template_id", "report_date", "created_at"),
    )