"""API endpoint to ingest Google Sheets deterministically into extraction_jobs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_tenant_context, require_admin
from app.infrastructure.db.session import get_db
from app.engines.extraction.sheet_ingestion_service import GoogleSheetIngestionService, IngestionRequest
from app.schemas.extraction_schema import GoogleSheetIngestionRequest, GoogleSheetIngestionSummary

router = APIRouter()


@router.post(
    "/jobs/ingest/google-sheet",
    response_model=GoogleSheetIngestionSummary,
    summary="Ingest Google Sheet deterministically",
)
async def ingest_google_sheet(
    body: GoogleSheetIngestionRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    service = GoogleSheetIngestionService(db)
    summary = await service.ingest(
        IngestionRequest(
            tenant_id=ctx.tenant_id,
            user_id=str(ctx.user.id),
            template_id=str(body.template_id),
            sheet_id=body.sheet_id,
            worksheet=body.worksheet,
            schema_path=body.schema_path,
            source_document_id=str(body.source_document_id) if body.source_document_id else None,
            range_a1=body.range_a1,
        )
    )
    return summary
