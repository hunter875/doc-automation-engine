"""Pydantic schemas for tenant management."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TenantCreate(BaseModel):
    """Request: create a new tenant."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class TenantUpdate(BaseModel):
    """Request: update tenant details."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class TenantResponse(BaseModel):
    """Response: tenant info."""

    id: str
    name: str
    description: Optional[str] = None
    settings: Optional[dict[str, Any]] = None
    billing_status: Optional[str] = None
    created_at: Optional[datetime] = None


class TenantMemberAdd(BaseModel):
    """Request: add a user to a tenant."""

    email: EmailStr
    role: str = Field(..., pattern="^(owner|admin|viewer)$")


class TenantMemberResponse(BaseModel):
    """Response: tenant member info."""

    user_id: str
    email: str
    full_name: Optional[str] = None
    role: str
    joined_at: Optional[datetime] = None
