"""Template routers for Engine 2 extraction."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
from app.models.user import User
from app.schemas.extraction_schema import (
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.template_manager import TemplateManager

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

    try:
        import uuid as _uuid

        from app.services.doc_service import s3_client

        s3_key = f"word_templates/{_uuid.uuid4()}/{file.filename}"
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=s3_key,
            Body=content,
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        result["word_template_s3_key"] = s3_key
        logger.info("Saved word template to S3: %s", s3_key)
    except Exception as exc:
        logger.warning("Failed to save word template to S3: %s", exc)
        result["word_template_s3_key"] = None

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
    manager = TemplateManager(db)
    return manager.create_template(
        tenant_id=ctx.tenant_id,
        user_id=str(ctx.user.id),
        name=body.name,
        schema_definition=body.schema_definition.model_dump(),
        description=body.description,
        aggregation_rules=body.aggregation_rules.model_dump() if body.aggregation_rules else None,
        word_template_s3_key=body.word_template_s3_key,
    )


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
    role: Annotated[None, Depends(RoleChecker("owner"))],
    db: Session = Depends(get_db),
):
    TemplateManager(db).delete_template(template_id, ctx.tenant_id)
