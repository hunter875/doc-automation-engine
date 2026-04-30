"""Sheet Inspector API — FastAPI router.

Provides data inspection endpoints for the Sheet Inspector dashboard.

GET  /api/v1/sheets/inspect/by-date  — month/day STT coverage grid
GET  /api/v1/sheets/inspect/issues  — missing/zero/mismatch STT fields
GET  /api/v1/sheets/inspect/mapping — column → STT mapping table
GET  /api/v1/sheets/names            — sheet names from Excel file
"""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_tenant_context, require_viewer
from app.application.sheet_inspect_service import SheetInspectService
from app.infrastructure.db.session import get_db

router = APIRouter()


# ── Response models ─────────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field


class SttCoverage(BaseModel):
    total: int = 0
    populated: int = 0
    zero: int = 0
    missing: int = 0


class NamedListSummary(BaseModel):
    cnch: int = 0
    chay: int = 0
    chi_vien: int = 0
    phuong_tien: int = 0
    cong_van: int = 0


class SheetInspectJob(BaseModel):
    id: str
    file_name: str
    status: str
    parser_used: str
    created_at: str
    stt_coverage: SttCoverage
    stt_values: dict[str, int] = Field(default_factory=dict)
    btk_rows: list[dict] = Field(default_factory=list)
    named_lists: NamedListSummary = Field(default_factory=NamedListSummary)
    has_issues: bool = False


class SheetInspectDay(BaseModel):
    date: str
    job_count: int = 0
    approved_count: int = 0
    has_issues: bool = False
    jobs: list[SheetInspectJob] = Field(default_factory=list)


class SheetIssue(BaseModel):
    stt: str
    field: str
    label: str
    date: str
    job_id: str
    file_name: str
    worksheet: str = ""  # e.g. "BC NGÀY", "VỤ CHÁY THỐNG KÊ", "CNCH", "CHI VIỆN"
    severity: str  # "missing" | "zero" | "mismatch"
    excel_value: Optional[int] = None
    system_value: int = 0
    description: str


class ColumnMappingRow(BaseModel):
    col_index: int
    col_letter: str
    col_header: str
    stt: Optional[str] = None
    field: str = ""
    status: str  # "mapped" | "unmapped" | "skipped"


# ── Endpoints ──────────────────────────────────────────────────────────────────────

@router.get(
    "/inspect/by-date",
    response_model=list[SheetInspectDay],
    status_code=status.HTTP_200_OK,
    summary="Get per-day STT inspection data for a month",
)
def inspect_by_date(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    year: int = Query(..., ge=2020, le=2100, description="Year"),
    day: Optional[int] = Query(None, ge=1, le=31, description="Specific day (optional)"),
):
    """Return all days in a month with per-job STT coverage.

    Each day contains:
      - date, job_count, approved_count, has_issues
      - jobs[]: id, file_name, status, stt_coverage, stt_values, btk_rows, named_lists
    """
    service = SheetInspectService(db)
    return service.get_month_data(tenant_id=ctx.tenant_id, month=month, year=year, day=day)


@router.get(
    "/inspect/issues",
    response_model=list[SheetIssue],
    status_code=status.HTTP_200_OK,
    summary="List missing / zero / mismatch STT fields",
)
def inspect_issues(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    document_id: Optional[uuid.UUID] = Query(None, description="Compare with raw Excel from MinIO"),
    job_id: Optional[uuid.UUID] = Query(None, description="Focus on a single job"),
    worksheet: Optional[str] = Query(
        None,
        description="Filter issues by worksheet: 'BC NGÀY', 'VỤ CHÁY THỐNG KÊ', 'CNCH', 'CHI VIỆN'. "
                     "If omitted, returns issues for all worksheets.",
    ),
):
    """Find STT fields that are missing or zero in extracted data.

    If document_id is provided, also reads the raw Excel from MinIO
    and flags mismatches between Excel cell values and system values.

    If worksheet is provided, only returns issues for that worksheet's schema.
    """
    service = SheetInspectService(db)
    return service.get_issues(
        tenant_id=ctx.tenant_id,
        month=month,
        year=year,
        document_id=document_id,
        job_id=job_id,
        worksheet=worksheet,
    )


@router.get(
    "/inspect/mapping",
    response_model=list[ColumnMappingRow],
    status_code=status.HTTP_200_OK,
    summary="Get BC NGÀY column → STT field mapping",
)
def inspect_mapping(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
):
    """Return the BC NGÀY sheet column → STT field mapping table.

    Each row describes one column (A–AH): its header, mapped STT number,
    field name, and mapping status (mapped | unmapped | skipped).
    """
    service = SheetInspectService(db)
    return service.get_mapping()


@router.get(
    "/names",
    status_code=status.HTTP_200_OK,
    summary="List sheet names from an Excel document in MinIO",
)
def get_sheet_names(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
    document_id: uuid.UUID = Query(..., description="Document UUID (must have s3_key to Excel file)"),
):
    """Download the Excel file from MinIO and return all worksheet names.

    Returns: {sheets: ["BC NGÀY", "CNCH", "CHI VIỆN", ...]} or {sheets: [], error: "..."}
    """
    service = SheetInspectService(db)
    return service.get_sheet_names(document_id=document_id)
