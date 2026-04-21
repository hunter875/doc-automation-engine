"""Job routers for Engine 2 extraction lifecycle."""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_tenant_context, require_admin, require_viewer
from app.core.config import settings
from app.infrastructure.db.session import get_db
from app.infrastructure.worker.celery_app import celery_app
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
from app.application.job_service import JobManager

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
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.application.doc_service import DocumentService
    from app.application.template_service import TemplateManager
    from app.infrastructure.worker.extraction_tasks import extract_document_task

    tpl = TemplateManager(db).get_template(template_id, ctx.tenant_id)
    mode = tpl.extraction_mode or "block"

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
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.application.template_service import TemplateManager
    tpl = TemplateManager(db).get_template(template_id, ctx.tenant_id)
    mode = tpl.extraction_mode or "block"

    max_files = settings.EXTRACTION_BATCH_MAX_FILES
    if len(files) > max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {max_files} files per batch",
        )

    from app.application.doc_service import DocumentService
    from app.infrastructure.worker.extraction_tasks import extract_document_task

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
    from app.application.doc_service import DocumentService
    from app.application.template_service import TemplateManager
    from app.infrastructure.worker.extraction_tasks import extract_document_task

    DocumentService(db).get_document(str(body.document_id), ctx.tenant_id)
    tpl = TemplateManager(db).get_template(str(body.template_id), ctx.tenant_id)
    mode = body.mode or tpl.extraction_mode or "block"

    job = JobManager(db).create_job(
        tenant_id=ctx.tenant_id,
        template_id=str(body.template_id),
        document_id=str(body.document_id),
        user_id=str(ctx.user.id),
        mode=mode,
    )
    extract_document_task.delay(str(job.id))
    return job


# ── Helper ────────────────────────────────────────────────────────────────────


def _extract_first_page_text(content: bytes) -> str:
    """Extract text from the first page for template matching."""
    try:
        import io
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if pdf.pages:
                return (pdf.pages[0].extract_text() or "").strip()
    except Exception:
        pass
    return ""


@router.post(
    "/jobs/smart-upload",
    response_model=BatchCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Smart upload: auto-detect template & mode, auto-trigger extraction",
    description=(
        "Upload one or more PDFs. The system automatically:\n"
        "1. Detects the best template via filename pattern / field coverage\n"
        "2. Uses template's extraction_mode (block by default)\n"
        "3. Creates jobs and triggers extraction immediately\n\n"
        "If template_id is provided, it overrides auto-detection."
    ),
)
async def smart_upload(
    files: list[UploadFile] = File(...),
    template_id: Optional[str] = Form(None),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.application.doc_service import DocumentService
    from app.application.template_service import TemplateManager
    from app.infrastructure.worker.extraction_tasks import extract_document_task

    max_files = settings.EXTRACTION_BATCH_MAX_FILES
    if len(files) > max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {max_files} files per batch",
        )

    batch_id = uuid.uuid4()
    doc_service = DocumentService(db)
    job_manager = JobManager(db)
    tpl_manager = TemplateManager(db)
    jobs_created: list[JobSummary] = []

    for file in files:
        try:
            content = await file.read()
            filename = file.filename or "unknown.pdf"

            # 1. Resolve template
            resolved_template_id = template_id
            resolved_tpl = None
            if not resolved_template_id:
                first_page_text = _extract_first_page_text(content)
                matched_tpl = tpl_manager.detect_template(
                    tenant_id=ctx.tenant_id,
                    filename=filename,
                    first_page_text=first_page_text,
                )
                if not matched_tpl:
                    jobs_created.append(
                        JobSummary(
                            job_id=uuid.uuid4(),
                            file_name=filename,
                            status="error: no matching template found",
                        )
                    )
                    continue
                resolved_template_id = str(matched_tpl.id)
                resolved_tpl = matched_tpl
            else:
                resolved_tpl = tpl_manager.get_template(resolved_template_id, ctx.tenant_id)

            # 2. Use template's extraction_mode — default to block
            mode = getattr(resolved_tpl, "extraction_mode", None) or "block"

            # 3. Create document + job
            document = doc_service.create_document(
                tenant_id=ctx.tenant_id,
                owner_id=str(ctx.user.id),
                filename=filename,
                file_content=content,
            )
            job = job_manager.create_job(
                tenant_id=ctx.tenant_id,
                template_id=resolved_template_id,
                document_id=str(document.id),
                user_id=str(ctx.user.id),
                batch_id=str(batch_id),
                mode=mode,
            )

            # 4. Auto-trigger extraction
            extract_document_task.delay(str(job.id))
            jobs_created.append(
                JobSummary(job_id=job.id, file_name=filename, status="pending")
            )

        except Exception as exc:
            jobs_created.append(
                JobSummary(
                    job_id=uuid.uuid4(),
                    file_name=file.filename or "unknown",
                    status=f"error: {str(exc)[:100]}",
                )
            )

    return BatchCreateResponse(
        batch_id=batch_id,
        total_files=len(files),
        jobs=jobs_created,
    )


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
    status_payload = JobManager(db).get_batch_status(batch_id, ctx.tenant_id)
    if int(status_payload.get("total") or 0) > 0:
        return status_payload

    task_result = AsyncResult(batch_id, app=celery_app)
    task_state = str(task_result.state or "PENDING").upper()

    if task_state == "SUCCESS" and isinstance(task_result.result, dict):
        summary = task_result.result
        total_rows = int(summary.get("rows_processed") or 0)
        inserted_rows = int(summary.get("rows_inserted") or 0)
        failed_rows = int(summary.get("rows_failed") or 0)
        skipped_rows = int(summary.get("rows_skipped_idempotent") or 0)
        done_rows = inserted_rows + failed_rows + skipped_rows
        progress = 100.0 if total_rows <= 0 else round(min(100.0, (done_rows / total_rows) * 100.0), 1)
        return {
            "batch_id": batch_id,
            "total": total_rows,
            "pending": 0,
            "processing": 0,
            "extracted": 0,
            "enriching": 0,
            "ready_for_review": inserted_rows,
            "approved": 0,
            "rejected": 0,
            "aggregated": 0,
            "failed": failed_rows,
            "progress_percent": progress,
        }

    if task_state in {"FAILURE", "REVOKED"}:
        return {
            "batch_id": batch_id,
            "total": 1,
            "pending": 0,
            "processing": 0,
            "extracted": 0,
            "enriching": 0,
            "ready_for_review": 0,
            "approved": 0,
            "rejected": 0,
            "aggregated": 0,
            "failed": 1,
            "progress_percent": 100.0,
        }

    return {
        "batch_id": batch_id,
        "total": 1,
        "pending": 1 if task_state in {"PENDING", "RECEIVED"} else 0,
        "processing": 1 if task_state in {"STARTED", "PROGRESS", "RETRY"} else 0,
        "extracted": 0,
        "enriching": 0,
        "ready_for_review": 0,
        "approved": 0,
        "rejected": 0,
        "aggregated": 0,
        "failed": 0,
        "progress_percent": 10.0 if task_state in {"PENDING", "RECEIVED"} else 50.0,
    }


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
    from app.infrastructure.worker.extraction_tasks import extract_document_task

    manager = JobManager(db)
    job = manager.retry_job(job_id, ctx.tenant_id)
    extract_document_task.delay(str(job.id))
    return job


@router.post(
    "/jobs/batch-block",
    status_code=status.HTTP_200_OK,
    summary="Batch block-mode extraction (in-process parallel)",
)
async def batch_block_extraction(
    files: list[UploadFile] = File(...),
    max_workers: Optional[int] = Form(None),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
):
    """Run block-mode extraction on multiple PDFs in parallel (no Celery)."""
    from app.engines.extraction.batch import BatchItem, run_batch

    max_files = settings.EXTRACTION_BATCH_MAX_FILES
    if len(files) > max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {max_files} files per batch",
        )

    items = []
    for f in files:
        content = await f.read()
        items.append(BatchItem(filename=f.filename or "unknown.pdf", pdf_bytes=content))

    result = run_batch(items, max_workers=max_workers)
    return {
        "total": result.total,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "results": result.results,
        "errors": result.errors,
        "metrics": result.metrics,
    }


@router.get(
    "/metrics",
    status_code=status.HTTP_200_OK,
    summary="Pipeline extraction metrics",
)
def get_extraction_metrics(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
):
    """Return global pipeline extraction metrics."""
    from app.utils.metrics import global_metrics
    return global_metrics.to_dict()


@router.get(
    "/jobs/by-date",
    status_code=status.HTTP_200_OK,
    summary="Get jobs grouped by date for a month — powers the calendar picker UI",
)
def get_jobs_by_date(
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    year: int = Query(..., ge=2020, le=2100, description="Year"),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Return all jobs for a given month, grouped by date.

    Each calendar day contains:
      - date: ISO date string
      - job_count: total jobs uploaded that day
      - approved_count: jobs with status approved/aggregated
      - has_issues: True if any job has extraction issues
      - jobs: list of job summaries
    """
    from datetime import date
    from calendar import monthrange
    from app.domain.models.extraction_job import ExtractionJob, ExtractionJobStatus

    tid = ctx.tenant_id
    _, last_day = monthrange(year, month)

    start = date(year, month, 1)
    end = date(year, month, last_day)

    jobs = (
        db.query(ExtractionJob)
        .filter(
            ExtractionJob.tenant_id == tid,
            ExtractionJob.created_at >= start,
            ExtractionJob.created_at <= end,
        )
        .order_by(ExtractionJob.created_at.desc())
        .all()
    )

    # Group by date string (YYYY-MM-DD)
    from collections import defaultdict
    by_date: dict[str, dict] = defaultdict(
        lambda: {
            "date": "",
            "job_count": 0,
            "approved_count": 0,
            "has_issues": False,
            "jobs": [],
        }
    )

    for job in jobs:
        if job.created_at is None:
            continue
        day_str = job.created_at.strftime("%Y-%m-%d")
        entry = by_date[day_str]
        entry["date"] = day_str
        entry["job_count"] += 1

        status = job.status or ""
        is_approved = status in (
            ExtractionJobStatus.APPROVED.value,
            ExtractionJobStatus.AGGREGATED.value,
        )
        if is_approved:
            entry["approved_count"] += 1

        # Mark issues if job has failed or has errors in extracted_data
        if status == ExtractionJobStatus.FAILED.value:
            entry["has_issues"] = True
        elif status == ExtractionJobStatus.READY_FOR_REVIEW.value:
            # Check if extracted_data has missing STTs (heuristic)
            ed = job.extracted_data or {}
            if isinstance(ed, dict):
                btk = ed.get("bang_thong_ke") or []
                if len(btk) < 20:
                    entry["has_issues"] = True

        entry["jobs"].append({
            "id": str(job.id),
            "file_name": job.file_name or job.display_name or "(no name)",
            "status": status,
            "template_id": job.template_id or "",
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })

    # Fill in all days of the month (even empty ones) for the calendar grid
    from datetime import timedelta
    result = []
    current = start
    while current <= end:
        day_str = current.strftime("%Y-%m-%d")
        entry = by_date.get(day_str)
        if entry:
            entry["date"] = day_str
            result.append(entry)
        else:
            result.append({
                "date": day_str,
                "job_count": 0,
                "approved_count": 0,
                "has_issues": False,
                "jobs": [],
            })
        current += timedelta(days=1)

    return result


@router.get(
    "/dashboard",
    status_code=status.HTTP_200_OK,
    summary="Business observability dashboard metrics",
)
def get_dashboard(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Return 6 business metrics for the admin dashboard.

    1. total_documents — documents uploaded
    2. jobs_by_status — breakdown (processing, awaiting_review, approved, failed)
    3. avg_processing_minutes — mean time from PENDING → READY_FOR_REVIEW
    4. reports_count — aggregation reports created
    5. approval_rate — approved / (approved + rejected) %
    6. recent_reports — last 5 reports (id, name, created_at, total_jobs)
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func, case, and_

    from app.domain.models.extraction_job import (
        ExtractionJob,
        ExtractionJobStatus,
        ExtractionTemplate,
        AggregationReport,
    )
    from app.domain.models.document import Document

    tid = ctx.tenant_id

    # 1. Total documents
    total_docs = (
        db.query(func.count(Document.id))
        .filter(Document.tenant_id == tid)
        .scalar()
    ) or 0

    # 2. Jobs by status
    status_counts = (
        db.query(ExtractionJob.status, func.count(ExtractionJob.id))
        .filter(ExtractionJob.tenant_id == tid)
        .group_by(ExtractionJob.status)
        .all()
    )
    sc = dict(status_counts)
    processing = sum(
        sc.get(s, 0) for s in (
            ExtractionJobStatus.PENDING,
            ExtractionJobStatus.PROCESSING,
            ExtractionJobStatus.EXTRACTED,
            ExtractionJobStatus.ENRICHING,
        )
    )
    jobs_by_status = {
        "processing": processing,
        "awaiting_review": sc.get(ExtractionJobStatus.READY_FOR_REVIEW, 0),
        "approved": sc.get(ExtractionJobStatus.APPROVED, 0),
        "aggregated": sc.get(ExtractionJobStatus.AGGREGATED, 0),
        "rejected": sc.get(ExtractionJobStatus.REJECTED, 0),
        "failed": sc.get(ExtractionJobStatus.FAILED, 0),
        "total": sum(sc.values()),
    }

    # 3. Average processing time (jobs completed in last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    avg_ms = (
        db.query(func.avg(ExtractionJob.processing_time_ms))
        .filter(
            ExtractionJob.tenant_id == tid,
            ExtractionJob.processing_time_ms.isnot(None),
            ExtractionJob.processing_time_ms > 0,
            ExtractionJob.created_at >= thirty_days_ago,
        )
        .scalar()
    )
    avg_processing_minutes = round((avg_ms or 0) / 60000, 1)

    # 4. Reports count
    reports_count = (
        db.query(func.count(AggregationReport.id))
        .filter(AggregationReport.tenant_id == tid)
        .scalar()
    ) or 0

    # 5. Approval rate
    approved_count = sc.get(ExtractionJobStatus.APPROVED, 0) + sc.get(ExtractionJobStatus.AGGREGATED, 0)
    rejected_count = sc.get(ExtractionJobStatus.REJECTED, 0)
    reviewed_total = approved_count + rejected_count
    approval_rate = round(approved_count / reviewed_total * 100, 1) if reviewed_total > 0 else 0.0

    # 6. Recent reports (last 5)
    recent_reports_q = (
        db.query(AggregationReport)
        .filter(AggregationReport.tenant_id == tid)
        .order_by(AggregationReport.created_at.desc())
        .limit(5)
        .all()
    )
    recent_reports = [
        {
            "id": str(r.id),
            "name": r.name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "total_jobs": r.total_jobs,
            "status": r.status,
        }
        for r in recent_reports_q
    ]

    return {
        "total_documents": total_docs,
        "jobs_by_status": jobs_by_status,
        "avg_processing_minutes": avg_processing_minutes,
        "reports_count": reports_count,
        "approval_rate": approval_rate,
        "recent_reports": recent_reports,
    }


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
