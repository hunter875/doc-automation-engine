"""API router for Engine 2: Structured Data Extraction.

Endpoints:
  Templates:  POST/GET/PATCH/DELETE /extraction/templates
  Jobs:       POST /extraction/jobs, POST /extraction/jobs/batch,
              POST /extraction/jobs/from-document
              GET /extraction/jobs, GET /extraction/jobs/{id}
              GET /extraction/jobs/batch/{batch_id}/status
              POST /extraction/jobs/{id}/retry
  Review:     POST /extraction/review/{id}/approve
              POST /extraction/review/{id}/reject
  Aggregate:  POST /extraction/aggregate
              GET /extraction/aggregate/{id}
              GET /extraction/aggregate/{id}/export
"""

import io
import logging
import re
import uuid
import unicodedata
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import (
    RoleChecker,
    TenantContext,
    get_current_user,
    get_tenant_context,
    require_admin,
    require_viewer,
)
from app.core.config import settings
from app.db.postgres import get_db
from app.models.extraction import ExtractionJobStatus
from app.models.user import User
from app.schemas.extraction_schema import (
    AggregateRequest,
    AggregateResponse,
    AggregateListResponse,
    BatchCreateResponse,
    BatchStatusResponse,
    JobCreate,
    JobFromDocumentCreate,
    JobListResponse,
    JobResponse,
    JobSummary,
    ReviewApprove,
    ReviewReject,
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.extraction_service import ExtractionService
from app.services.aggregation_service import AggregationService, ExportService

logger = logging.getLogger(__name__)


def _build_content_disposition(filename: str) -> str:
    """Build a safe download header with UTF-8 filename support.

    Uses both legacy `filename=` (ASCII fallback) and RFC5987
    `filename*=` for Unicode names.
    """
    raw_name = re.sub(r"[\r\n\"]", "", (filename or "").strip()) or "report"

    ascii_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^\w\s\-.]", "", ascii_name).strip() or "report"

    utf8_quoted_name = quote(raw_name)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_quoted_name}"

router = APIRouter(
    prefix="/extraction",
    tags=["Extraction (Engine 2)"],
)


# ──────────────────────────────────────────────
# Word Template Scanner
# ──────────────────────────────────────────────

@router.post(
    "/templates/scan-word",
    summary="Read placeholders from Word template",
    description="Upload a .docx file and read all Jinja placeholders/loops from it. "
                "The frontend lets the user decide schema_definition and aggregation_rules manually.",
)
async def scan_word_template(
    file: UploadFile = File(...),
    use_llm: bool = True,
    current_user: User = Depends(get_current_user),
):
    """Scan a Word document for placeholders/loops and return detected holes."""
    from app.services.word_scanner import scan_word_template as do_scan

    if not file.filename or not file.filename.lower().endswith((".docx", ".doc")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ hỗ trợ file .docx",
        )

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File quá lớn (tối đa 50 MB)",
        )

    try:
        result = do_scan(content, use_llm=use_llm)
    except Exception as exc:
        logger.exception("Word scan failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Không thể đọc file Word: {exc}",
        )

    if result["stats"]["unique_variables"] == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không tìm thấy placeholder {{...}} nào trong file.",
        )

    # Save word template to S3 for later Word export
    try:
        from app.services.doc_service import s3_client
        import uuid as _uuid
        s3_key = f"word_templates/{_uuid.uuid4()}/{file.filename}"
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=s3_key,
            Body=content,
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        result["word_template_s3_key"] = s3_key
        logger.info(f"Saved word template to S3: {s3_key}")
    except Exception as exc:
        logger.warning(f"Failed to save word template to S3: {exc}")
        result["word_template_s3_key"] = None

    return result


# ──────────────────────────────────────────────
# Template Endpoints
# ──────────────────────────────────────────────

@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create extraction template",
)
def create_template(
    body: TemplateCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """Create a new extraction template with schema definition."""
    service = ExtractionService(db)
    template = service.create_template(
        tenant_id=ctx.tenant_id,
        user_id=str(ctx.user.id),
        name=body.name,
        schema_definition=body.schema_definition.model_dump(),
        description=body.description,
        aggregation_rules=body.aggregation_rules.model_dump() if body.aggregation_rules else None,
        word_template_s3_key=body.word_template_s3_key,
    )
    return template


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    summary="List extraction templates",
)
def list_templates(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    is_active: bool = Query(True),
):
    """List extraction templates for the current tenant."""
    service = ExtractionService(db)
    items, total = service.list_templates(
        tenant_id=ctx.tenant_id,
        page=page,
        per_page=per_page,
        is_active=is_active,
    )
    return TemplateListResponse(
        items=[TemplateResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Get template detail",
)
def get_template(
    template_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
):
    """Get a single extraction template."""
    service = ExtractionService(db)
    return service.get_template(template_id, ctx.tenant_id)


@router.patch(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Update template",
)
def update_template(
    template_id: str,
    body: TemplateUpdate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """Update an extraction template. Schema changes bump version."""
    service = ExtractionService(db)
    update_data = body.model_dump(exclude_unset=True)

    # Convert Pydantic models to dicts for storage
    if "schema_definition" in update_data and update_data["schema_definition"] is not None:
        update_data["schema_definition"] = body.schema_definition.model_dump()
    if "aggregation_rules" in update_data and update_data["aggregation_rules"] is not None:
        update_data["aggregation_rules"] = body.aggregation_rules.model_dump()

    return service.update_template(template_id, ctx.tenant_id, **update_data)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete template (soft)",
)
def delete_template(
    template_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(RoleChecker("owner"))],
    db: Session = Depends(get_db),
):
    """Soft-delete a template (set is_active=False)."""
    service = ExtractionService(db)
    service.delete_template(template_id, ctx.tenant_id)


# ──────────────────────────────────────────────
# Job Endpoints
# ──────────────────────────────────────────────

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
    """Upload a PDF and create an extraction job.

    Modes:
      - standard: Docling (GPU) → Gemini Flash (best for tables/layouts)
      - vision: Gemini Pro native PDF (best for scanned/blurry docs)
      - fast: pdfplumber (CPU) → Gemini Flash (best for text-only PDFs)

    Returns 202 Accepted with job_id for polling.
    """
    if mode not in ("standard", "vision", "fast"):
        raise HTTPException(status_code=400, detail="mode must be: standard, vision, or fast")

    from app.services.doc_service import DocumentService

    # 1. Read file
    content = await file.read()

    # 2. Validate + upload via existing DocumentService
    doc_service = DocumentService(db)
    document = doc_service.create_document(
        tenant_id=ctx.tenant_id,
        owner_id=str(ctx.user.id),
        filename=file.filename,
        file_content=content,
    )

    # 3. Create extraction job
    ext_service = ExtractionService(db)
    job = ext_service.create_job(
        tenant_id=ctx.tenant_id,
        template_id=template_id,
        document_id=str(document.id),
        user_id=str(ctx.user.id),
        mode=mode,
    )

    # 4. Dispatch Celery task
    from app.worker.extraction_tasks import extract_document_task

    extract_document_task.delay(str(job.id))

    logger.info(f"Extraction job {job.id} queued for document {document.file_name}")

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
    """Upload multiple PDFs and create extraction jobs for each.

    Max 20 files per batch. Supports modes: standard, vision, fast.
    """
    if mode not in ("standard", "vision", "fast"):
        raise HTTPException(status_code=400, detail="mode must be: standard, vision, or fast")

    from app.services.doc_service import DocumentService

    max_files = settings.EXTRACTION_BATCH_MAX_FILES
    if len(files) > max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {max_files} files per batch",
        )

    batch_id = uuid.uuid4()
    doc_service = DocumentService(db)
    ext_service = ExtractionService(db)
    jobs_created: list[JobSummary] = []

    from app.worker.extraction_tasks import extract_document_task

    for file in files:
        try:
            content = await file.read()

            document = doc_service.create_document(
                tenant_id=ctx.tenant_id,
                owner_id=str(ctx.user.id),
                filename=file.filename,
                file_content=content,
            )

            job = ext_service.create_job(
                tenant_id=ctx.tenant_id,
                template_id=template_id,
                document_id=str(document.id),
                user_id=str(ctx.user.id),
                batch_id=str(batch_id),
                mode=mode,
            )

            extract_document_task.delay(str(job.id))

            jobs_created.append(
                JobSummary(job_id=job.id, file_name=file.filename, status="pending")
            )

        except Exception as e:
            logger.error(f"Failed to process file {file.filename}: {e}")
            jobs_created.append(
                JobSummary(
                    job_id=uuid.uuid4(),
                    file_name=file.filename,
                    status=f"error: {str(e)[:100]}",
                )
            )

    return BatchCreateResponse(
        batch_id=batch_id,
        total_files=len(files),
        jobs=jobs_created,
    )


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
    """Create an extraction job from an already-uploaded document (no re-upload)."""
    from app.services.doc_service import DocumentService

    # Verify document exists
    doc_service = DocumentService(db)
    doc_service.get_document(str(body.document_id), ctx.tenant_id)

    ext_service = ExtractionService(db)
    job = ext_service.create_job(
        tenant_id=ctx.tenant_id,
        template_id=str(body.template_id),
        document_id=str(body.document_id),
        user_id=str(ctx.user.id),
        mode=body.mode,
    )

    from app.worker.extraction_tasks import extract_document_task

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
    """List extraction jobs with optional filters."""
    service = ExtractionService(db)
    items, total = service.list_jobs(
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
    """Get aggregated status for all jobs in a batch."""
    service = ExtractionService(db)
    return service.get_batch_status(batch_id, ctx.tenant_id)


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
    """Get extraction job details. Use for polling status."""
    service = ExtractionService(db)
    return service.get_job(job_id, ctx.tenant_id)


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
    """Delete an extraction job after it reaches a terminal status."""
    service = ExtractionService(db)
    service.delete_job(job_id, ctx.tenant_id)


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
    """Retry a failed or rejected extraction job."""
    service = ExtractionService(db)
    job = service.retry_job(job_id, ctx.tenant_id)

    from app.worker.extraction_tasks import extract_document_task

    extract_document_task.delay(str(job.id))

    return job


# ──────────────────────────────────────────────
# Review Endpoints
# ──────────────────────────────────────────────

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
    """Approve an extracted job, optionally with corrected data."""
    service = ExtractionService(db)
    return service.approve_job(
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
    """Reject an extraction result with notes."""
    service = ExtractionService(db)
    return service.reject_job(
        job_id=job_id,
        tenant_id=ctx.tenant_id,
        reviewer_id=str(ctx.user.id),
        notes=body.notes,
    )


# ──────────────────────────────────────────────
# Aggregation & Export Endpoints
# ──────────────────────────────────────────────

@router.post(
    "/aggregate",
    response_model=AggregateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Aggregate approved jobs into report",
)
def create_aggregate(
    body: AggregateRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """Aggregate multiple approved extraction jobs into a summary report."""
    service = AggregationService(db)
    report = service.aggregate(
        template_id=str(body.template_id),
        job_ids=[str(j) for j in body.job_ids],
        tenant_id=ctx.tenant_id,
        report_name=body.report_name,
        user_id=str(ctx.user.id),
        description=body.description,
    )
    return report


@router.get(
    "/aggregate",
    response_model=AggregateListResponse,
    summary="List aggregation reports",
)
def list_reports(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    template_id: Optional[str] = Query(None),
):
    """List aggregation reports."""
    service = AggregationService(db)
    items, total = service.list_reports(
        tenant_id=ctx.tenant_id,
        page=page,
        per_page=per_page,
        template_id=template_id,
    )
    return AggregateListResponse(
        items=[AggregateResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/aggregate/{report_id}",
    response_model=AggregateResponse,
    summary="Get report detail",
)
def get_report(
    report_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
):
    """Get an aggregation report."""
    service = AggregationService(db)
    return service.get_report(report_id, ctx.tenant_id)


@router.delete(
    "/aggregate/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete aggregation report",
)
def delete_report(
    report_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    """Delete an aggregation report."""
    service = AggregationService(db)
    service.delete_report(report_id, ctx.tenant_id)


@router.get(
    "/aggregate/{report_id}/export",
    summary="Export report as Excel/CSV/JSON/Word",
)
def export_report(
    report_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
    format: str = Query("excel", pattern=r"^(excel|csv|json|word)$"),
):
    """Export aggregation report in various formats.

    For Word export: requires a Word template to be uploaded first via
    POST /extraction/aggregate/{report_id}/word-template
    """
    from app.models.extraction import ExtractionJob

    agg_service = AggregationService(db)
    report = agg_service.get_report(report_id, ctx.tenant_id)

    if format == "json":
        return report.aggregated_data

    # Load detail jobs for Excel
    jobs = None
    if format == "excel" and report.job_ids:
        jobs = (
            db.query(ExtractionJob)
            .filter(ExtractionJob.id.in_(report.job_ids))
            .all()
        )

    export_svc = ExportService()

    if format == "excel":
        buffer = export_svc.to_excel(report, jobs=jobs)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": _build_content_disposition(f"{report.name}.xlsx")
            },
        )
    elif format == "csv":
        buffer = export_svc.to_csv(report)
        return StreamingResponse(
            buffer,
            media_type="text/csv",
            headers={
                "Content-Disposition": _build_content_disposition(f"{report.name}.csv")
            },
        )
    elif format == "word":
        return _export_word(report, ctx, db)


# ──────────────────────────────────────────────
# Word Template Export (Bước 4)
# ──────────────────────────────────────────────

@router.post(
    "/aggregate/{report_id}/export-word",
    summary="Export report to Word using uploaded template",
    description="Upload a .docx template with {{...}} Jinja2 placeholders. "
                "The aggregated data will be injected into the template. "
                "Supports loops: {% for item in records %}...{% endfor %}",
)
async def export_report_word(
    report_id: str,
    file: UploadFile = File(..., alias="file"),
    record_index: int = Form(0),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Upload a Word template and immediately render it with the report's aggregated data.

    The template should contain Jinja2 placeholders like:
      - {{ten_don_vi}} for simple fields
      - {% for row in records %}{{row.field}}{% endfor %} for table loops
      - {{total_so_vu | number_vn}} for Vietnamese number formatting
      - {{ngay_bao_cao | date_vn}} for Vietnamese date formatting
    """
    from app.services.word_export import render_aggregation_to_word

    if not file.filename or not file.filename.lower().endswith((".docx", ".doc")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ hỗ trợ file .docx",
        )

    template_bytes = await file.read()
    if len(template_bytes) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File quá lớn (tối đa 50 MB)",
        )

    agg_service = AggregationService(db)
    report = agg_service.get_report(report_id, ctx.tenant_id)

    # Build extra context
    extra_context = {
        "report_name": report.name,
        "report_description": report.description or "",
        "total_jobs": report.total_jobs,
        "approved_jobs": report.approved_jobs,
    }

    try:
        rendered_bytes = render_aggregation_to_word(
            template_bytes=template_bytes,
            aggregated_data=report.aggregated_data,
            extra_context=extra_context,
            record_index=record_index,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    output_filename = f"{report.name or 'report'}.docx"

    return StreamingResponse(
        io.BytesIO(rendered_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": _build_content_disposition(output_filename)
        },
    )


def _export_word(report, ctx, db):
    """Helper for format=word query param — returns error since template upload is needed."""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Word export requires uploading a template. "
               "Use POST /extraction/aggregate/{report_id}/export-word with a .docx file.",
    )


@router.get(
    "/aggregate/{report_id}/export-word-auto",
    summary="Export report to Word using the saved template",
    description="Uses the Word template that was originally scanned when creating the "
                "extraction template. No upload needed.",
)
def export_report_word_auto(
    report_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Export report to Word using the template's saved .docx file from S3."""
    from app.services.word_export import render_aggregation_to_word
    from app.services.doc_service import s3_client

    agg_service = AggregationService(db)
    report = agg_service.get_report(report_id, ctx.tenant_id)

    # Find the extraction template used for this report
    service = ExtractionService(db)
    template = service.get_template(str(report.template_id), ctx.tenant_id)

    if not template.word_template_s3_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mẫu trích xuất này chưa có file Word template. "
                   "Hãy tạo mẫu bằng cách quét file Word (.docx) trước.",
        )

    # Download template from S3
    try:
        s3_resp = s3_client.get_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=template.word_template_s3_key,
        )
        template_bytes = s3_resp["Body"].read()
    except Exception as exc:
        logger.error(f"Failed to download word template from S3: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không tải được file Word template từ S3: {exc}",
        )

    extra_context = {
        "report_name": report.name,
        "report_description": report.description or "",
        "total_jobs": report.total_jobs,
        "approved_jobs": report.approved_jobs,
    }

    try:
        rendered_bytes = render_aggregation_to_word(
            template_bytes=template_bytes,
            aggregated_data=report.aggregated_data,
            extra_context=extra_context,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    output_filename = f"{report.name or 'report'}.docx"

    return StreamingResponse(
        io.BytesIO(rendered_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": _build_content_disposition(output_filename)
        },
    )
