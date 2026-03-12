"""Pydantic schemas for authentication."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# === Request Schemas ===


class UserRegisterRequest(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLoginRequest(BaseModel):
    """Schema for user login (used with OAuth2PasswordRequestForm)."""

    email: EmailStr
    password: str


class TokenRefreshRequest(BaseModel):
    """Schema for token refresh."""

    refresh_token: str


class PasswordChangeRequest(BaseModel):
    """Schema for password change."""

    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# === Response Schemas ===


class TokenResponse(BaseModel):
    """Schema for token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Schema for user response."""

    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserTenantInfo(BaseModel):
    """Schema for user's tenant information."""

    tenant_id: UUID
    tenant_name: str
    role: str

    model_config = {"from_attributes": True}


class UserWithTenantsResponse(BaseModel):
    """Schema for user response with tenant information."""

    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    tenants: list[UserTenantInfo] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


# Aliases for backward compatibility
LoginRequest = UserLoginRequest
RegisterRequest = UserRegisterRequest
TokenRefreshRequest = TokenRefreshRequest
