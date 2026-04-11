"""Document API endpoints."""

import logging
from typing import Annotated, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    TenantContext,
    get_tenant_context,
    require_admin,
    require_viewer,
)
from app.core.exceptions import (
    DocumentNotFoundError,
    FileValidationError,
    S3Error,
)
from app.infrastructure.db.session import get_db
from app.domain.models.document import DocumentStatus
from app.domain.models.tenant import UserTenantRole
from app.schemas.doc_schema import (
    DocumentResponse,
    DocumentUpdate,
    PaginatedDocuments,
    UploadResponse,
)
from app.application.doc_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document",
    description="Upload a document for processing. Requires admin role.",
)
async def upload_document(
    file: UploadFile = File(...),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Upload a document for RAG processing.

    Args:
        file: Uploaded file
        tags: Optional comma-separated tags
        ctx: Tenant context
        _: Admin role check
        db: Database session

    Returns:
        Upload response with document info

    Raises:
        HTTPException: If upload fails
    """
    doc_service = DocumentService(db)

    # Read file content
    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        document = doc_service.create_document(
            tenant_id=ctx.tenant_id,
            owner_id=str(ctx.user.id),
            filename=file.filename,
            file_content=content,
            tags=tag_list,
        )

        return UploadResponse(
            id=str(document.id),
            file_name=document.file_name,
            file_size_bytes=document.file_size_bytes,
            status=document.status,
            mime_type=document.mime_type,
            tags=document.tags or [],
            created_at=document.created_at,
            message="Document uploaded successfully. Processing started.",
        )

    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except S3Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store document",
        )


@router.get(
    "",
    response_model=PaginatedDocuments,
    summary="List documents",
    description="List documents with pagination and filters.",
)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """List documents with pagination.

    Args:
        page: Page number
        page_size: Items per page
        status: Filter by status
        tag: Filter by tag
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        Paginated list of documents
    """
    doc_service = DocumentService(db)

    # Parse status enum
    doc_status = None
    if status:
        try:
            doc_status = DocumentStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}",
            )

    return doc_service.list_documents(
        tenant_id=ctx.tenant_id,
        page=page,
        page_size=page_size,
        status=doc_status,
        tag=tag,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document",
    description="Get document details by ID.",
)
def get_document(
    document_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Get document by ID.

    Args:
        document_id: Document UUID
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        Document details

    Raises:
        HTTPException: If document not found
    """
    doc_service = DocumentService(db)

    try:
        document = doc_service.get_document(document_id, ctx.tenant_id)
        return DocumentResponse.model_validate(document)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {document_id}",
        )


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Update document",
    description="Update document metadata. Requires admin role.",
)
def update_document(
    document_id: str,
    update_data: DocumentUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update document metadata.

    Args:
        document_id: Document UUID
        update_data: Update data
        ctx: Tenant context
        _: Admin role check
        db: Database session

    Returns:
        Updated document

    Raises:
        HTTPException: If document not found
    """
    doc_service = DocumentService(db)

    try:
        document = doc_service.update_document(
            document_id=document_id,
            tenant_id=ctx.tenant_id,
            update_data=update_data,
        )
        return DocumentResponse.model_validate(document)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {document_id}",
        )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document",
    description="Delete document and associated data. Requires admin role.",
)
def delete_document(
    document_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete document.

    Args:
        document_id: Document UUID
        ctx: Tenant context
        _: Admin role check
        db: Database session

    Raises:
        HTTPException: If document not found
    """
    doc_service = DocumentService(db)

    try:
        doc_service.delete_document(document_id, ctx.tenant_id)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {document_id}",
        )


@router.get(
    "/{document_id}/download",
    summary="Download document",
    description="Download original document file.",
)
def download_document(
    document_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Download document file.

    Args:
        document_id: Document UUID
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        Streaming file response

    Raises:
        HTTPException: If document not found
    """
    doc_service = DocumentService(db)

    try:
        content, filename, mime_type = doc_service.get_document_content(
            document_id, ctx.tenant_id
        )

        return StreamingResponse(
            iter([content]),
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {document_id}",
        )
    except S3Error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document",
        )


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentResponse,
    summary="Reprocess document",
    description="Re-trigger document processing. Requires admin role.",
)
def reprocess_document(
    document_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reprocess a document.

    Args:
        document_id: Document UUID
        ctx: Tenant context
        _: Admin role check
        db: Database session

    Returns:
        Document with updated status

    Raises:
        HTTPException: If document not found
    """
    doc_service = DocumentService(db)

    try:
        document = doc_service.get_document(document_id, ctx.tenant_id)

        # Reset status and re-queue
        document = doc_service.update_document_status(
            document_id=document_id,
            status=DocumentStatus.PENDING,
        )

        return DocumentResponse.model_validate(document)

    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {document_id}",
        )


@router.get(
    "/stats/summary",
    summary="Get document stats",
    description="Get document statistics for tenant.",
)
def get_stats(
    ctx: TenantContext = Depends(get_tenant_context),
    _: UserTenantRole = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Get document statistics.

    Args:
        ctx: Tenant context
        _: Viewer role check
        db: Database session

    Returns:
        Statistics dictionary
    """
    doc_service = DocumentService(db)
    return doc_service.get_tenant_stats(ctx.tenant_id)
