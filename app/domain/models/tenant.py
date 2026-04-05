"""Tenant model for multi-tenancy support."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.session import Base


class Tenant(Base):
    """Tenant model representing a workspace/organization."""

    __tablename__ = "tenants"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    settings = Column(JSON, nullable=True, default=dict)
    billing_status = Column(String(50), default="active")  # active, suspended, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user_roles = relationship(
        "UserTenantRole",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    documents = relationship(
        "Document",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    usage_logs = relationship(
        "TenantUsageLog",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.name}>"


class UserTenantRole(Base):
    """Junction table for user-tenant relationship with roles."""

    __tablename__ = "user_tenant_roles"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(50), nullable=False)  # owner, admin, viewer
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships - using string references to avoid circular imports
    user = relationship("User", back_populates="tenant_roles", foreign_keys=[user_id])
    tenant = relationship("Tenant", back_populates="user_roles", foreign_keys=[tenant_id])

    def __repr__(self) -> str:
        return f"<UserTenantRole user={self.user_id} tenant={self.tenant_id} role={self.role}>"


class TenantUsageLog(Base):
    """Usage logs for tracking token consumption per tenant."""

    __tablename__ = "tenant_usage_logs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    operation_type = Column(String(50), nullable=False)  # embedding, chat, search
    model_name = Column(String(100), nullable=True)
    prompt_tokens = Column(String, default="0")
    completion_tokens = Column(String, default="0")
    total_tokens = Column(String, default="0")
    cost_usd = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="usage_logs")
    user = relationship("User", back_populates="usage_logs")

    def __repr__(self) -> str:
        return f"<TenantUsageLog tenant={self.tenant_id} op={self.operation_type}>"
