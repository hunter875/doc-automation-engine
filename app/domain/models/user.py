"""User model for authentication and authorization."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.session import Base


class User(Base):
    """User model for storing user credentials and profile."""

    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant_roles = relationship(
        "UserTenantRole",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    documents = relationship(
        "Document",
        back_populates="uploaded_by_user",
        foreign_keys="Document.uploaded_by",
    )
    usage_logs = relationship(
        "TenantUsageLog",
        back_populates="user",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
