"""Pydantic schemas for RAG operations."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# === Request Schemas ===


class RAGQueryRequest(BaseModel):
    """Schema for RAG query request."""

    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)
    min_score: float = Field(0.3, ge=0.0, le=1.0)
    search_type: str = Field("hybrid", pattern="^(semantic|keyword|hybrid)$")
    use_hybrid: bool = True
    include_sources: bool = True
    temperature: float = Field(0.7, ge=0, le=1)
    max_tokens: int = Field(1000, ge=100, le=4000)
    document_ids: Optional[list[UUID]] = None
    tags: Optional[list[str]] = None


class SearchRequest(BaseModel):
    """Schema for semantic search request."""

    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(10, ge=1, le=50)
    search_type: str = Field("hybrid", pattern="^(semantic|keyword|hybrid)$")
    filters: Optional[dict[str, Any]] = None
    highlight: bool = True


# === Response Schemas ===


class SourceDocument(BaseModel):
    """Schema for source document in RAG response."""

    document_id: UUID
    document_title: str
    chunk_id: str
    content: str
    relevance_score: float
    page_number: Optional[int] = None


class TokenUsage(BaseModel):
    """Schema for token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Optional[float] = None

class SearchResult(BaseModel):
    """Schema for single search result."""

    document_id: str
    document_title: Optional[str] = None
    chunk_id: str
    content: str
    score: float
    highlight: Optional[str] = None
    metadata: dict[str, Any] = {}


class RAGQueryResponse(BaseModel):
    """Schema for RAG query response."""

    answer: str
    sources: list[SearchResult] = []
    confidence_score: Optional[float] = None
    usage: Optional[dict] = None
    query_time_ms: Optional[float] = None
    processing_time_ms: Optional[int] = None


class SearchResponse(BaseModel):
    """Schema for search response."""

    results: list[SearchResult]
    total_results: int
    search_type: str
    processing_time_ms: int


class SimilarChunk(BaseModel):
    """Schema for similar chunk."""

    chunk_id: str
    document_id: UUID
    document_title: str
    content: str
    similarity_score: float


class SimilarChunksResponse(BaseModel):
    """Schema for similar chunks response."""

    source_chunk: dict[str, Any]
    similar_chunks: list[SimilarChunk]


# === Streaming Schemas ===


class StreamSourcesEvent(BaseModel):
    """SSE event for sources."""

    event: str = "sources"
    sources: list[SourceDocument]


class StreamTokenEvent(BaseModel):
    """SSE event for token."""

    event: str = "token"
    content: str


class StreamDoneEvent(BaseModel):
    """SSE event for completion."""

    event: str = "done"
    usage: TokenUsage
    processing_time_ms: int


# === Tenant Schemas (placed here to avoid circular imports) ===


class TenantCreateRequest(BaseModel):
    """Schema for tenant creation."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    settings: Optional[dict] = Field(default_factory=dict)


class TenantUpdateRequest(BaseModel):
    """Schema for tenant update."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    settings: Optional[dict] = None


class TenantInviteRequest(BaseModel):
    """Schema for inviting user to tenant."""

    email: str
    role: str = Field(..., pattern="^(admin|viewer)$")


class TenantMemberUpdateRequest(BaseModel):
    """Schema for updating member role."""

    role: str = Field(..., pattern="^(admin|viewer)$")


class TenantMemberResponse(BaseModel):
    """Schema for tenant member."""

    user_id: UUID
    email: str
    full_name: Optional[str] = None
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class TenantUsageStats(BaseModel):
    """Schema for tenant usage statistics."""

    total_documents: int
    completed_documents: int
    processing_documents: int
    failed_documents: int
    total_chunks: int
    total_tokens_used: int
    storage_used_mb: float
    estimated_cost_usd: float


class TenantResponse(BaseModel):
    """Schema for tenant response."""

    id: UUID
    name: str
    description: Optional[str] = None
    settings: Optional[dict] = {}
    billing_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantDetailResponse(TenantResponse):
    """Schema for detailed tenant response."""

    members: list[TenantMemberResponse] = []
    usage: Optional[TenantUsageStats] = None


class TenantListItem(BaseModel):
    """Schema for tenant list item."""

    id: UUID
    name: str
    role: str
    document_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    """Schema for tenant list response."""

    items: list[TenantListItem]
    total: int


class UsageBreakdown(BaseModel):
    """Schema for usage breakdown by date."""

    date: str
    embedding_tokens: int
    chat_tokens: int
    query_count: int
    cost_usd: float


class UsageSummary(BaseModel):
    """Schema for usage summary."""

    total_tokens: int
    embedding_tokens: int
    chat_tokens: int
    estimated_cost_usd: float


class TenantUsageResponse(BaseModel):
    """Schema for tenant usage response."""

    summary: UsageSummary
    breakdown: list[UsageBreakdown]


# Aliases for backward compatibility
TenantCreate = TenantCreateRequest
TenantUpdate = TenantUpdateRequest
TenantMemberAdd = TenantInviteRequest
SearchResultItem = SearchResult
