"""RAG (Retrieval-Augmented Generation) API endpoints."""

import json
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import (
    TenantContext,
    get_tenant_context,
    require_viewer,
)
from app.core.exceptions import (
    ProcessingError,
    VectorStoreError,
)
from app.db.postgres import get_db
from app.models.tenant import UserTenantRole
from app.schemas.rag_schema import (
    RAGQueryRequest,
    RAGQueryResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="RAG Query",
    description="Ask a question and get an answer based on uploaded documents.",
)
def rag_query(
    request: RAGQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Execute RAG query.

    Args:
        request: RAG query request
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        RAG query response with answer and sources

    Raises:
        HTTPException: If query fails
    """
    rag_service = RAGService(db)

    try:
        result = rag_service.query(
            question=request.question,
            tenant_id=ctx.tenant_id,
            document_ids=request.document_ids,
            top_k=request.top_k,
            min_score=request.min_score,
            use_hybrid=request.use_hybrid,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        # Convert sources to response format
        sources = [
            SearchResultItem(
                chunk_id=s.chunk_id,
                document_id=str(s.document_id),
                content=s.content,
                score=s.score,
                metadata=s.metadata,
            )
            for s in result.sources
        ]

        return RAGQueryResponse(
            answer=result.answer,
            sources=sources,
            usage=result.usage,
            query_time_ms=result.query_time_ms,
        )

    except VectorStoreError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vector store error: {str(e)}",
        )
    except ProcessingError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/query/stream",
    summary="RAG Query (Streaming)",
    description="Ask a question with streaming response.",
)
async def rag_query_stream(
    request: RAGQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Execute RAG query with streaming response.

    Args:
        request: RAG query request
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        Server-Sent Events stream

    Raises:
        HTTPException: If query fails
    """
    rag_service = RAGService(db)

    async def generate_sse():
        """Generate SSE events."""
        try:
            async for event in rag_service.query_stream(
                question=request.question,
                tenant_id=ctx.tenant_id,
                document_ids=request.document_ids,
                top_k=request.top_k,
                use_hybrid=request.use_hybrid,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                event_type = event.get("event", "message")
                data = event.get("data", "")

                if isinstance(data, (dict, list)):
                    data = json.dumps(data, ensure_ascii=False)

                yield f"event: {event_type}\ndata: {data}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic Search",
    description="Search for relevant document chunks without generating an answer.",
)
def search(
    request: SearchRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Search for relevant document chunks.

    Args:
        request: Search request
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        Search results

    Raises:
        HTTPException: If search fails
    """
    rag_service = RAGService(db)

    try:
        results = rag_service.search(
            query=request.query,
            tenant_id=ctx.tenant_id,
            document_ids=request.document_ids,
            top_k=request.top_k,
            min_score=request.min_score,
            use_hybrid=request.use_hybrid,
        )

        items = [
            SearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                content=r.content,
                score=r.score,
                metadata=r.metadata,
            )
            for r in results
        ]

        return SearchResponse(
            results=items,
            total=len(items),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get(
    "/chunks/{document_id}",
    summary="Get document chunks",
    description="Get indexed chunks for a specific document.",
)
def get_document_chunks(
    document_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Get chunks for a document.

    Args:
        document_id: Document UUID
        page: Page number
        page_size: Items per page
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        List of chunks
    """
    rag_service = RAGService(db)

    chunks = rag_service.get_document_chunks(
        document_id=document_id,
        tenant_id=ctx.tenant_id,
        page=page,
        page_size=page_size,
    )

    return {
        "document_id": document_id,
        "page": page,
        "page_size": page_size,
        "chunks": chunks,
    }
