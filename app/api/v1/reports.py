"""Report Calendar and Weekly Report API controller."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_tenant_context, require_admin, require_viewer
from app.application.report_service import CalendarService, ReportService, WeeklyReportAggregator
from app.infrastructure.db.session import get_db
from app.schemas.report_schema import (
    CalendarResponse,
    DailyReportResponse,
    WeeklyReportCreateRequest,
    WeeklyReportResponse,
)

router = APIRouter()


class ReportController:
    """HTTP controller facade for report calendar module."""

    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx
        self.calendar_service = CalendarService(db)
        self.report_service = ReportService(db)
        self.weekly_aggregator = WeeklyReportAggregator(db)

    def get_calendar(self) -> dict:
        return self.calendar_service.get_calendar_dates(self.ctx.tenant_id)

    def get_daily(self, report_date: date) -> dict:
        return self.report_service.get_daily_report(self.ctx.tenant_id, report_date)

    def create_weekly(self, week_start: date):
        return self.weekly_aggregator.generate_weekly_report(
            tenant_id=self.ctx.tenant_id,
            week_start=week_start,
            user_id=str(self.ctx.user.id),
        )

    def get_weekly(self, week_start: date):
        return self.report_service.repository.get_weekly_report(self.ctx.tenant_id, week_start)


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar_reports(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_viewer)],
    db: Session = Depends(get_db),
):
    controller = ReportController(db, ctx)
    return controller.get_calendar()


@router.get("/daily", response_model=DailyReportResponse)
def get_daily_report(
    date: date = Query(..., description="Business report date (YYYY-MM-DD)"),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    controller = ReportController(db, ctx)
    return controller.get_daily(date)


@router.post("/weekly", response_model=WeeklyReportResponse, status_code=status.HTTP_201_CREATED)
def create_weekly_report(
    body: WeeklyReportCreateRequest,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    role: Annotated[None, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    controller = ReportController(db, ctx)
    weekly = controller.create_weekly(body.week_start)
    return {
        "id": str(weekly.id),
        "week_start": weekly.week_start,
        "week_end": weekly.week_end,
        "generated_at": weekly.generated_at,
        "report_payload": weekly.report_payload or {},
        "sources_used": weekly.sources_used or [],
    }


@router.get("/weekly", response_model=WeeklyReportResponse)
def get_weekly_report(
    week_start: date = Query(..., description="Week start date (Monday, YYYY-MM-DD)"),
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    controller = ReportController(db, ctx)
    weekly = controller.get_weekly(week_start)
    if weekly is None:
        from app.core.exceptions import ProcessingError

        raise ProcessingError(message=f"Weekly report not found for week_start={week_start.isoformat()}")

    return {
        "id": str(weekly.id),
        "week_start": weekly.week_start,
        "week_end": weekly.week_end,
        "generated_at": weekly.generated_at,
        "report_payload": weekly.report_payload or {},
        "sources_used": weekly.sources_used or [],
    }
