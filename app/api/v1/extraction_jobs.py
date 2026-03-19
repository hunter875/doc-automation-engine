"""Job routers for Engine 2 extraction lifecycle."""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_tenant_context, require_admin, require_viewer
from app.core.config import settings
from app.db.postgres import get_db
from app.schemas.extraction_schema import (
    BatchCreateResponse,
    BatchStatusResponse,
    JobFromDocumentCreate,
    JobListResponse,
    JobResponse,
    JobSummary,
    ReviewApprove,
    ReviewReject,
)
from app.services.job_manager import JobManager

router = APIRouter()


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create extraction job (single file)",
)
async def create_job(
    file: UploadFile = File(...),
    template_id: str = Form(...),
    mode: str = Form("standard"),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if mode not in ("standard", "vision", "fast"):
        raise HTTPException(status_code=400, detail="mode must be: standard, vision, or fast")

    from app.services.doc_service import DocumentService
    from app.worker.extraction_tasks import extract_document_task

    content = await file.read()

    document = DocumentService(db).create_document(
        tenant_id=ctx.tenant_id,
        owner_id=str(ctx.user.id),
        filename=file.filename,
        file_content=content,
    )

    job = JobManager(db).create_job(
        tenant_id=ctx.tenant_id,
        template_id=template_id,
        document_id=str(document.id),
        user_id=str(ctx.user.id),
        mode=mode,
    )

    extract_document_task.delay(str(job.id))
    return job


@router.post(
    "/jobs/batch",
    response_model=BatchCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch upload + extraction",
)
async def create_batch_jobs(
    files: list[UploadFile] = File(...),
    template_id: str = Form(...),
    mode: str = Form("standard"),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if mode not in ("standard", "vision", "fast"):
        raise HTTPException(status_code=400, detail="mode must be: standard, vision, or fast")

    max_files = settings.EXTRACTION_BATCH_MAX_FILES
    if len(files) > max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {max_files} files per batch",
        )

    from app.services.doc_service import DocumentService
    from app.worker.extraction_tasks import extract_document_task

    batch_id = uuid.uuid4()
    doc_service = DocumentService(db)
    jobs = JobManager(db)
    jobs_created: list[JobSummary] = []

    for file in files:
        try:
            content = await file.read()
            document = doc_service.create_document(
                tenant_id=ctx.tenant_id,
                owner_id=str(ctx.user.id),
                filename=file.filename,
                file_content=content,
            )

            job = jobs.create_job(
                tenant_id=ctx.tenant_id,
                template_id=template_id,
                document_id=str(document.id),
                user_id=str(ctx.user.id),
                batch_id=str(batch_id),
                mode=mode,
            )
            extract_document_task.delay(str(job.id))
            jobs_created.append(JobSummary(job_id=job.id, file_name=file.filename, status="pending"))
        except Exception as exc:
            jobs_created.append(
                JobSummary(job_id=uuid.uuid4(), file_name=file.filename, status=f"error: {str(exc)[:100]}")
            )

    return BatchCreateResponse(batch_id=batch_id, total_files=len(files), jobs=jobs_created)


@router.post(
    "/jobs/from-document",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create job from existing document",
)
def create_job_from_document(
    body: JobFromDocumentCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    from app.services.doc_service import DocumentService
    from app.worker.extraction_tasks import extract_document_task

    DocumentService(db).get_document(str(body.document_id), ctx.tenant_id)

    job = JobManager(db).create_job(
        tenant_id=ctx.tenant_id,
        template_id=str(body.template_id),
        document_id=str(body.document_id),
        user_id=str(ctx.user.id),
        mode=body.mode,
    )
    extract_document_task.delay(str(job.id))
    return job


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List extraction jobs",
)
def list_jobs(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    job_status: Optional[str] = Query(None, alias="status"),
    template_id: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
):
    manager = JobManager(db)
    items, total = manager.list_jobs(
        tenant_id=ctx.tenant_id,
        page=page,
        per_page=per_page,
        status=job_status,
        template_id=template_id,
        batch_id=batch_id,
    )
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/jobs/batch/{batch_id}/status",
    response_model=BatchStatusResponse,
    summary="Get batch progress",
)
def get_batch_status(
    batch_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
):
    return JobManager(db).get_batch_status(batch_id, ctx.tenant_id)


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get job detail (polling endpoint)",
)
def get_job(
    job_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
):
    return JobManager(db).get_job(job_id, ctx.tenant_id)


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete finished job",
)
def delete_job(
    job_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    JobManager(db).delete_job(job_id, ctx.tenant_id)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobResponse,
    summary="Retry failed job",
)
def retry_job(
    job_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    from app.worker.extraction_tasks import extract_document_task

    manager = JobManager(db)
    job = manager.retry_job(job_id, ctx.tenant_id)
    extract_document_task.delay(str(job.id))
    return job


@router.post(
    "/review/{job_id}/approve",
    response_model=JobResponse,
    summary="Approve extraction result",
)
def approve_job(
    job_id: str,
    body: ReviewApprove,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return JobManager(db).approve_job(
        job_id=job_id,
        tenant_id=ctx.tenant_id,
        reviewer_id=str(ctx.user.id),
        reviewed_data=body.reviewed_data,
        notes=body.notes,
    )


@router.post(
    "/review/{job_id}/reject",
    response_model=JobResponse,
    summary="Reject extraction result",
)
def reject_job(
    job_id: str,
    body: ReviewReject,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return JobManager(db).reject_job(
        job_id=job_id,
        tenant_id=ctx.tenant_id,
        reviewer_id=str(ctx.user.id),
        notes=body.notes,
    )
