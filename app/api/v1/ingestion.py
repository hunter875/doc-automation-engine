"""API endpoint to ingest Google Sheets deterministically into extraction_jobs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from celery.result import AsyncResult
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_tenant_context, require_admin
from app.infrastructure.db.session import get_db
from app.infrastructure.worker.celery_app import celery_app
from app.infrastructure.worker.extraction_tasks import ingest_google_sheet_task
from app.engines.extraction.sheet_ingestion_service import GoogleSheetIngestionService, IngestionRequest
from app.schemas.extraction_schema import (
    GoogleSheetIngestionEnqueueResponse,
    GoogleSheetIngestionRequest,
    GoogleSheetIngestionSummary,
    GoogleSheetIngestionTaskStatus,
)

router = APIRouter()


@router.post(
    "/jobs/ingest/google-sheet",
    response_model=GoogleSheetIngestionEnqueueResponse,
    summary="Enqueue Google Sheet ingestion",
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_google_sheet(
    body: GoogleSheetIngestionRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    response: Response,
    db: Session = Depends(get_db),
):
    task_payload = {
        "tenant_id": ctx.tenant_id,
        "user_id": str(ctx.user.id),
        "template_id": str(body.template_id),
        "sheet_id": body.sheet_id,
        "worksheet": body.worksheet,
        "schema_path": body.schema_path,
        "source_document_id": str(body.source_document_id) if body.source_document_id else None,
        "range_a1": body.range_a1,
    }
    task = ingest_google_sheet_task.delay(task_payload)
    poll_url = f"/api/v1/extraction/jobs/ingest/google-sheet/{task.id}"
    response.headers["Location"] = poll_url
    return GoogleSheetIngestionEnqueueResponse(
        status="accepted",
        batch_id=str(task.id),
        task_id=str(task.id),
        poll_url=poll_url,
    )


@router.get(
    "/jobs/ingest/google-sheet/{task_id}",
    response_model=GoogleSheetIngestionTaskStatus,
    summary="Get Google Sheet ingestion task status",
)
def get_ingestion_status(
    task_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
):
    result = AsyncResult(task_id, app=celery_app)
    state = str(result.state or "PENDING").upper()

    if state == "SUCCESS":
        payload = result.result if isinstance(result.result, dict) else {}
        return GoogleSheetIngestionTaskStatus(
            task_id=task_id,
            state=state,
            status="completed",
            summary=GoogleSheetIngestionSummary.model_validate(payload),
        )

    if state in {"FAILURE", "REVOKED"}:
        return GoogleSheetIngestionTaskStatus(
            task_id=task_id,
            state=state,
            status="failed",
            error=str(result.result),
        )

    return GoogleSheetIngestionTaskStatus(
        task_id=task_id,
        state=state,
        status="running" if state in {"STARTED", "PROGRESS", "RETRY"} else "queued",
    )


@router.post(
    "/jobs/ingest/google-sheet/sync",
    response_model=GoogleSheetIngestionSummary,
    summary="Ingest Google Sheet deterministically (sync fallback)",
)
async def ingest_google_sheet_sync(
    body: GoogleSheetIngestionRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    service = GoogleSheetIngestionService(db)
    return await service.ingest(
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
