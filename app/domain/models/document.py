"""Document and DocumentChunk models."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.infrastructure.db.session import Base


class Document(Base):
    """Document model for storing document metadata."""

    __tablename__ = "documents"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description = Column(Text, nullable=True)
    file_name = Column(String(255), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=True)
    mime_type = Column(String(100), nullable=True)
    s3_key = Column(String(500), nullable=True)
    checksum = Column(String(64), nullable=True, index=True)
    status = Column(
        String(50),
        default="pending",
        index=True,
    )  # pending, processing, completed, failed
    chunk_count = Column(Integer, default=0)
    embedding_model = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    tags = Column(ARRAY(String), default=[])
    uploaded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="documents")
    uploaded_by_user = relationship(
        "User",
        back_populates="documents",
        foreign_keys=[uploaded_by],
    )

    def __repr__(self) -> str:
        return f"<Document {self.file_name} ({self.status})>"

    @property
    def is_processing(self) -> bool:
        return self.status == "processing"

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"


class DocumentChunk(Base):
    """Document chunk model with vector embedding stored via pgvector."""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(255), unique=True, nullable=False, index=True)
    document_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=True)
    chunk_index = Column(Integer, default=0)
    embedding_model = Column(String(100), nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<DocumentChunk {self.chunk_id} (doc={self.document_id})>"


class DocumentStatus:
    """Document status constants."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PROCESSED = "completed"  # alias
    FAILED = "failed"
