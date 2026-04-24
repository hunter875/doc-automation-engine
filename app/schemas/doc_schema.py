"""Pydantic schemas for documents."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# === Request Schemas ===


class DocumentCreateRequest(BaseModel):
    """Schema for document upload metadata."""

    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    tags: Optional[list[str]] = Field(default_factory=list, max_length=20)


class DocumentUpdateRequest(BaseModel):
    """Schema for document metadata update."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    tags: Optional[list[str]] = Field(None, max_length=20)


class DocumentListParams(BaseModel):
    """Schema for document list query parameters."""

    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)
    status: Optional[str] = Field(None, pattern="^(pending|processing|completed|failed)$")
    search: Optional[str] = Field(None, max_length=255)
    tags: Optional[list[str]] = None
    sort_by: str = Field("created_at", pattern="^(created_at|title|status)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


# === Response Schemas ===


class DocumentResponse(BaseModel):
    """Schema for document response."""

    id: UUID
    tenant_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    file_name: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    status: str
    chunk_count: int = 0
    embedding_model: Optional[str] = None
    tags: list[str] = []
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    """Schema for detailed document response."""

    s3_key: Optional[str] = None
    error_message: Optional[str] = None
    uploaded_by: Optional[UUID] = None


class DocumentStatusResponse(BaseModel):
    """Schema for document processing status."""

    document_id: UUID
    status: str
    progress: Optional[dict] = None
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None


class PaginationMeta(BaseModel):
    """Schema for pagination metadata."""

    total: int
    page: int
    limit: int
    pages: int
    has_next: bool
    has_prev: bool


class DocumentListResponse(BaseModel):
    """Schema for paginated document list."""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DocumentUploadResponse(BaseModel):
    """Schema for document upload response."""

    id: UUID
    status: str
    file_name: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    tags: list[str] = []
    created_at: datetime
    message: str = "Document is being processed. Check status in a few minutes."

    model_config = {"from_attributes": True}


# Aliases for backward compatibility
DocumentCreate = DocumentCreateRequest
DocumentUpdate = DocumentUpdateRequest
PaginatedDocuments = DocumentListResponse
UploadResponse = DocumentUploadResponse
