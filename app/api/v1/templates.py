"""Template routers for Engine 2 extraction."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import (
    RoleChecker,
    TenantContext,
    get_current_user,
    get_tenant_context,
    require_admin,
    require_viewer,
)
from app.core.config import settings
from app.infrastructure.db.session import get_db
from app.domain.models.user import User
from app.schemas.extraction_schema import (
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.application.template_service import TemplateManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/templates/scan-word",
    summary="Read placeholders from Word template",
    description="Upload a .docx file and read all Jinja placeholders/loops from it.",
)
async def scan_word_template(
    file: UploadFile = File(...),
    use_llm: bool = True,
    current_user: User = Depends(get_current_user),
):
    from app.utils.word_scanner import scan_word_template as do_scan

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

    try:
        import uuid as _uuid

        from app.application.doc_service import s3_client

        s3_key = f"word_templates/{_uuid.uuid4()}/{file.filename}"
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=s3_key,
            Body=content,
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        result["word_template_s3_key"] = s3_key
        logger.info(
            "SCAN_WORD_SAVED | key=%s bucket=%s filename=%s",
            s3_key, settings.S3_BUCKET_NAME, file.filename,
        )
    except Exception as exc:
        # Do NOT silently return None here. A scan result without an S3 key is
        # unusable — the user would create a template that always fails on export.
        logger.error(
            "SCAN_WORD_S3_UPLOAD_FAILED | bucket=%s filename=%s error=%s",
            settings.S3_BUCKET_NAME, file.filename, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"File Word đã được đọc thành công nhưng không thể lưu vào S3 "
                f"(bucket={settings.S3_BUCKET_NAME}). "
                f"Kiểm tra kết nối MinIO và thử lại. Chi tiết: {exc}"
            ),
        )

    return result


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
    # Log incoming request for debugging
    logger.info(
        f"CREATE_TEMPLATE: name='{body.name}', "
        f"schema_fields={len(body.schema_definition.fields) if body.schema_definition else 0}, "
        f"extraction_mode='{body.extraction_mode}'"
    )
    if body.schema_definition:
        for field in body.schema_definition.fields:
            logger.debug(f"  Field: name='{field.name}', type='{field.type}', required={field.required}")

    try:
        manager = TemplateManager(db)

        # If using new multi-worksheet config, populate legacy fields from first config for backward compatibility
        google_sheet_worksheet = body.google_sheet_worksheet
        google_sheet_schema_path = body.google_sheet_schema_path
        google_sheet_range = body.google_sheet_range
        if body.google_sheet_configs and len(body.google_sheet_configs) > 0:
            first_cfg = body.google_sheet_configs[0]
            google_sheet_worksheet = first_cfg.worksheet or google_sheet_worksheet
            google_sheet_schema_path = first_cfg.schema_path or google_sheet_schema_path
            google_sheet_range = first_cfg.range or google_sheet_range
        google_sheet_configs = (
            [cfg.model_dump() for cfg in body.google_sheet_configs]
            if body.google_sheet_configs
            else None
        )

        result = manager.create_template(
            tenant_id=ctx.tenant_id,
            user_id=str(ctx.user.id),
            name=body.name,
            schema_definition=body.schema_definition.model_dump(),
            description=body.description,
            aggregation_rules=body.aggregation_rules.model_dump() if body.aggregation_rules else None,
            word_template_s3_key=body.word_template_s3_key,
            filename_pattern=body.filename_pattern,
            extraction_mode=body.extraction_mode,
            google_sheet_id=body.google_sheet_id,
            google_sheet_worksheet=google_sheet_worksheet,
            google_sheet_range=google_sheet_range,
            google_sheet_schema_path=google_sheet_schema_path,
            google_sheet_configs=google_sheet_configs,
            aggregation_group=body.aggregation_group,
        )
        logger.info(f"CREATE_TEMPLATE_SUCCESS: template_id={result.id}, name='{result.name}'")
        return result
    except Exception as e:
        logger.error(f"CREATE_TEMPLATE_FAILED: name='{body.name}' error={type(e).__name__}: {e}")
        raise


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
    manager = TemplateManager(db)
    items, total = manager.list_templates(
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
    return TemplateManager(db).get_template(template_id, ctx.tenant_id)


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
    manager = TemplateManager(db)
    update_data = body.model_dump(exclude_unset=True)

    if "schema_definition" in update_data and update_data["schema_definition"] is not None:
        update_data["schema_definition"] = body.schema_definition.model_dump()
    if "aggregation_rules" in update_data and update_data["aggregation_rules"] is not None:
        update_data["aggregation_rules"] = body.aggregation_rules.model_dump()

    return manager.update_template(template_id, ctx.tenant_id, **update_data)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete template (soft)",
)
def delete_template(
    template_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    TemplateManager(db).delete_template(template_id, ctx.tenant_id)
