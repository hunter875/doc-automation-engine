"""Report aggregation/export routers for Engine 2."""

from __future__ import annotations

import io
import re
import unicodedata
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_tenant_context, require_admin, require_viewer
from app.core.config import settings
from app.db.postgres import get_db
from app.schemas.extraction_schema import (
    AggregateListResponse,
    AggregateRequest,
    AggregateResponse,
)
from app.services.aggregation_service import AggregationService, ExportService, build_word_export_context
from app.services.template_manager import TemplateManager

router = APIRouter()


def _build_content_disposition(filename: str) -> str:
    raw_name = re.sub(r"[\r\n\"]", "", (filename or "").strip()) or "report"
    ascii_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^\w\s\-.]", "", ascii_name).strip() or "report"
    utf8_quoted_name = quote(raw_name)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_quoted_name}"


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
    return AggregationService(db).aggregate(
        template_id=str(body.template_id),
        job_ids=[str(j) for j in body.job_ids],
        tenant_id=ctx.tenant_id,
        report_name=body.report_name,
        user_id=str(ctx.user.id),
        description=body.description,
    )


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
    return AggregationService(db).get_report(report_id, ctx.tenant_id)


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
    AggregationService(db).delete_report(report_id, ctx.tenant_id)


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
    from app.models.extraction import ExtractionJob

    agg_service = AggregationService(db)
    report = agg_service.get_report(report_id, ctx.tenant_id)

    if format == "json":
        return report.aggregated_data

    jobs = None
    if format == "excel" and report.job_ids:
        jobs = db.query(ExtractionJob).filter(ExtractionJob.id.in_(report.job_ids)).all()

    export_svc = ExportService()

    if format == "excel":
        return StreamingResponse(
            export_svc.to_excel(report, jobs=jobs),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": _build_content_disposition(f"{report.name}.xlsx")},
        )
    if format == "csv":
        return StreamingResponse(
            export_svc.to_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": _build_content_disposition(f"{report.name}.csv")},
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Word export requires uploading a template. Use POST /extraction/aggregate/{report_id}/export-word.",
    )


@router.post(
    "/aggregate/{report_id}/export-word",
    summary="Export report to Word using uploaded template",
)
async def export_report_word(
    report_id: str,
    file: UploadFile = File(..., alias="file"),
    record_index: int = Form(0),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    try:
        from app.services.word_export import render_word_template
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Word export dependency is missing (`docxtpl`). "
                "Please rebuild/redeploy API image with updated requirements."
            ),
        ) from exc

    if not file.filename or not file.filename.lower().endswith((".docx", ".doc")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chỉ hỗ trợ file .docx")

    template_bytes = await file.read()
    if len(template_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File quá lớn (tối đa 50 MB)")

    report = AggregationService(db).get_report(report_id, ctx.tenant_id)
    extra_context = {
        "report_name": report.name,
        "report_description": report.description or "",
        "total_jobs": report.total_jobs,
        "approved_jobs": report.approved_jobs,
    }

    context = build_word_export_context(
        report.aggregated_data,
        record_index=record_index,
        extra_context=extra_context,
    )

    try:
        rendered_bytes = render_word_template(
            template_bytes=template_bytes,
            context_data=context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    output_filename = f"{report.name or 'report'}.docx"
    return StreamingResponse(
        io.BytesIO(rendered_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _build_content_disposition(output_filename)},
    )


@router.get(
    "/aggregate/{report_id}/export-word-auto",
    summary="Export report to Word using the saved template",
)
def export_report_word_auto(
    report_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    from app.services.doc_service import s3_client
    try:
        from app.services.word_export import render_word_template
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Word export dependency is missing (`docxtpl`). "
                "Please rebuild/redeploy API image with updated requirements."
            ),
        ) from exc

    report = AggregationService(db).get_report(report_id, ctx.tenant_id)
    template = TemplateManager(db).get_template(str(report.template_id), ctx.tenant_id)

    if not template.word_template_s3_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mẫu trích xuất này chưa có file Word template.",
        )

    try:
        s3_resp = s3_client.get_object(Bucket=settings.S3_BUCKET_NAME, Key=template.word_template_s3_key)
        template_bytes = s3_resp["Body"].read()
    except Exception as exc:
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

    context = build_word_export_context(
        report.aggregated_data,
        extra_context=extra_context,
    )

    try:
        rendered_bytes = render_word_template(
            template_bytes=template_bytes,
            context_data=context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    output_filename = f"{report.name or 'report'}.docx"
    return StreamingResponse(
        io.BytesIO(rendered_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _build_content_disposition(output_filename)},
    )
