"""API endpoint to ingest Google Sheets deterministically into extraction_jobs."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from celery.result import AsyncResult
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_tenant_context, require_admin
from app.infrastructure.db.session import get_db
from app.infrastructure.worker.celery_app import celery_app
from app.infrastructure.worker.extraction_tasks import ingest_google_sheet_task
from app.engines.extraction.sheet_ingestion_service import GoogleSheetIngestionService, IngestionRequest
from app.engines.extraction.sources.sheets_source import GoogleSheetsSource
from app.domain.models.extraction_job import ExtractionTemplate
from app.schemas.extraction_schema import (
    GoogleSheetIngestionEnqueueResponse,
    GoogleSheetIngestionRequest,
    GoogleSheetIngestionSummary,
    GoogleSheetIngestionTaskStatus,
)
from app.core.exceptions import ProcessingError
import logging
import asyncio
import unicodedata

logger = logging.getLogger(__name__)

router = APIRouter()

GOOGLE_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")

# KV30 known worksheet titles (try these first before metadata discovery)
KV30_KNOWN_TITLES = {
    "master": ["BC NGÀY", "BC NGAY"],
    "cnch": ["CNCH"],
    "chi_vien": ["CHI VIỆN", "CHI VIEN"],
    "vu_chay": ["VỤ CHÁY THỐNG KÊ", "VU CHAY THONG KE"],
    "sclq": ["SCLQ ĐẾN PCCC&CNCH", "SCLQ DEN PCCC&CNCH"],
}

def _normalize_worksheet_name(name: str) -> str:
    """Normalize worksheet name: lowercase, strip, remove diacritics, collapse spaces."""
    name = name.strip().lower()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = " ".join(name.split())
    return name

def _match_role(name: str) -> str | None:
    """Match worksheet name to a KV30 role."""
    n = _normalize_worksheet_name(name)
    if "bc" in n and "ngay" in n:
        return "master"
    if "cnch" in n:
        return "cnch"
    if "chi" in n and "vien" in n:
        return "chi_vien"
    if ("vu" in n and "chay" in n) or ("chay" in n and "thong" in n and "ke" in n):
        return "vu_chay"
    if "sclq" in n or ("pccc" in n):
        return "sclq"
    return None

def build_kv30_configs(selected_worksheets: dict[str, str]) -> list[dict]:
    """Build KV30 configs from selected worksheet titles."""
    return [
        {"worksheet": selected_worksheets["master"], "schema_path": "bc_ngay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 0, "data_start_row": 1, "role": "master", "target_section": None},
        {"worksheet": selected_worksheets["cnch"], "schema_path": "cnch_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_cnch"},
        {"worksheet": selected_worksheets["vu_chay"], "schema_path": "vu_chay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_chay"},
        {"worksheet": selected_worksheets["chi_vien"], "schema_path": "chi_vien_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_chi_vien"},
        {"worksheet": selected_worksheets["sclq"], "schema_path": "sclq_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_sclq"},
    ]

async def resolve_kv30_worksheets(sheet_id: str, gid_hint: str | None = None) -> dict[str, str]:
    """
    Resolve KV30 worksheet titles. Strategy:
    1. Try known titles first (no metadata needed)
    2. If gid_hint provided, try to resolve it as fallback/hint
    3. Return selected titles for each role
    """
    # Start with known titles
    selected: dict[str, str] = {}
    for role, candidates in KV30_KNOWN_TITLES.items():
        selected[role] = candidates[0]  # Use first known title as default

    # If gid_hint provided, try to resolve and use as hint (optional enhancement)
    if gid_hint:
        source = GoogleSheetsSource()
        try:
            gid_title = await asyncio.to_thread(source.get_worksheet_title_by_gid, sheet_id, gid_hint)
            gid_role = _match_role(gid_title)
            if gid_role and gid_role in selected:
                selected[gid_role] = gid_title
                logger.info("[KV30] GID %s resolved to '%s' (role=%s), using as hint", gid_hint, gid_title, gid_role)
            else:
                logger.info("[KV30] GID %s resolved to '%s' but not a KV30 role, ignoring", gid_hint, gid_title)
        except ProcessingError as e:
            logger.warning("[KV30] GID resolution failed (non-blocking): %s", e)

    logger.info("[KV30] Selected worksheets: %s", selected)
    return selected

# KV30 hardcoded worksheet configs for daily report sync
KV30_WORKSHEET_CONFIGS = [
    {"worksheet": "BC NGAY", "schema_path": "bc_ngay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 0, "data_start_row": 1, "role": "master", "target_section": None},
    {"worksheet": "CNCH", "schema_path": "cnch_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_cnch"},
    {"worksheet": "VU CHAY THONG KE", "schema_path": "vu_chay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_chay"},
    {"worksheet": "CHI VIEN", "schema_path": "chi_vien_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_chi_vien"},
    {"worksheet": "SCLQ DEN PCCC&CNCH", "schema_path": "sclq_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_sclq"},
]


def _normalize_configs(configs: list | None) -> list[dict] | None:
    if not configs:
        return None
    normalized: list[dict] = []
    for cfg in configs:
        if hasattr(cfg, "model_dump"):
            normalized.append(cfg.model_dump())
        elif isinstance(cfg, dict):
            normalized.append(cfg)
        else:
            raise HTTPException(
                status_code=400,
                detail="Each worksheet config must be an object with worksheet/schema_path",
            )
    return normalized


def _normalize_sheet_id(sheet_id_or_url: str | None) -> str | None:
    if not sheet_id_or_url:
        return None
    raw = str(sheet_id_or_url).strip()
    match = GOOGLE_SHEET_ID_RE.search(raw)
    if match:
        return match.group(1)
    return raw


def resolve_google_sheet_ingestion_configs(body: GoogleSheetIngestionRequest, template: ExtractionTemplate) -> list[dict]:
    """
    Resolve worksheet configurations for ingestion.
    - If body.mode == "kv30": return KV30 hardcoded configs (ignores template and body worksheet/schema).
    - Else (generic mode):
        - If body.configs provided: use them.
        - Else: try template.google_sheet_configs.
        - Else: fallback to legacy single-field (body.worksheet/schema_path or template's).
    """
    # KV30 mode: ignore template configs, return hardcoded set
    if body.mode == "kv30":
        return KV30_WORKSHEET_CONFIGS

    # Generic mode
    if body.configs:
        return _normalize_configs(body.configs)

    template_configs = template.google_sheet_configs
    if template_configs:
        return _normalize_configs(template_configs)

    # Legacy single-field config
    worksheet = body.worksheet or template.google_sheet_worksheet
    schema_path = body.schema_path or template.google_sheet_schema_path
    if not worksheet or not schema_path:
        raise HTTPException(
            status_code=400,
            detail="Worksheet name and schema path required (provide in request or configure in template, or use google_sheet_configs)"
        )
    range_a1 = body.range_a1 or template.google_sheet_range or "A1:ZZZ"
    return [{"worksheet": worksheet, "schema_path": schema_path, "range": range_a1}]


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
    # Fetch template to check for stored config
    template = db.query(ExtractionTemplate).filter(
        ExtractionTemplate.id == body.template_id,
        ExtractionTemplate.tenant_id == ctx.tenant_id,
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Resolve Sheet ID (explicit > template)
    sheet_id = _normalize_sheet_id(body.sheet_id or template.google_sheet_id)
    if not sheet_id:
        raise HTTPException(status_code=400, detail="Sheet ID required (provide in request or configure in template)")

    # Resolve worksheet configurations based on mode
    if body.mode == "kv30":
        # KV30 mode: use known titles + optional gid hint
        selected_worksheets = await resolve_kv30_worksheets(sheet_id, body.worksheet_gid)
        configs = build_kv30_configs(selected_worksheets)
    else:
        configs = resolve_google_sheet_ingestion_configs(body, template)

    # Validate configs structure (each must have worksheet and schema_path)
    for cfg in configs:
        if not cfg.get("worksheet") or not cfg.get("schema_path"):
            raise HTTPException(status_code=400, detail="Each worksheet config must have 'worksheet' and 'schema_path'")

    # Build task payload
    task_payload = {
        "tenant_id": ctx.tenant_id,
        "user_id": str(ctx.user.id),
        "template_id": str(body.template_id),
        "sheet_id": sheet_id,
        "configs": configs,
    }
    # For backward compatibility, also include first config's fields at top-level (not used by new service but harmless)
    first_cfg = configs[0]
    task_payload.setdefault("worksheet", first_cfg["worksheet"])
    task_payload.setdefault("schema_path", first_cfg["schema_path"])
    if "range" in first_cfg:
        task_payload["range_a1"] = first_cfg["range"]

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
    response_model_exclude_none=True,
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
    response_model_exclude_none=True,
    summary="Ingest Google Sheet deterministically (sync fallback)",
)
async def ingest_google_sheet_sync(
    body: GoogleSheetIngestionRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    # Fetch template to check for stored config
    template = db.query(ExtractionTemplate).filter(
        ExtractionTemplate.id == body.template_id,
        ExtractionTemplate.tenant_id == ctx.tenant_id,
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Resolve Sheet ID
    sheet_id = _normalize_sheet_id(body.sheet_id or template.google_sheet_id)
    if not sheet_id:
        raise HTTPException(status_code=400, detail="Sheet ID required")

    # Resolve worksheet configurations based on mode
    if body.mode == "kv30":
        selected_worksheets = await resolve_kv30_worksheets(sheet_id, body.worksheet_gid)
        configs = [
            {"worksheet": selected_worksheets["master"], "schema_path": "bc_ngay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 0, "data_start_row": 1, "role": "master", "target_section": None},
            {"worksheet": selected_worksheets["cnch"], "schema_path": "cnch_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_cnch"},
            {"worksheet": selected_worksheets["vu_chay"], "schema_path": "vu_chay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_chay"},
            {"worksheet": selected_worksheets["chi_vien"], "schema_path": "chi_vien_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_chi_vien"},
            {"worksheet": selected_worksheets["sclq"], "schema_path": "sclq_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "role": "detail", "target_section": "danh_sach_sclq"},
        ]
    else:
        configs = resolve_google_sheet_ingestion_configs(body, template)

    # Validate configs structure
    for cfg in configs:
        if not cfg.get("worksheet") or not cfg.get("schema_path"):
            raise HTTPException(status_code=400, detail="Each worksheet config must have 'worksheet' and 'schema_path'")

    service = GoogleSheetIngestionService(db)
    return await service.ingest(
        IngestionRequest(
            tenant_id=ctx.tenant_id,
            user_id=str(ctx.user.id),
            template_id=str(body.template_id),
            sheet_id=sheet_id,
            worksheet=configs[0]["worksheet"],  # for single compatibility, use first worksheet
            schema_path=configs[0]["schema_path"],
            source_document_id=str(body.source_document_id) if body.source_document_id else None,
            range_a1=configs[0].get("range"),
            configs=configs if len(configs) > 1 else None,  # only pass configs if multiple
        )
    )
