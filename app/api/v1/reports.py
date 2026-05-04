"""Report Calendar and Weekly Report API controller."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_tenant_context, require_admin, require_viewer
from app.application.daily_report_service import DailyReportService
from app.application.report_service import CalendarService, ReportService, WeeklyReportAggregator
from app.infrastructure.db.session import get_db
from app.schemas.report_schema import (
    CalendarResponse,
    DailyReportDetailResponse,
    DailyReportDiffResponse,
    DailyReportEditRequest,
    DailyReportRejectRequest,
    DailyReportReviewRequest,
    DailyReportResponse,
    WeeklyReportCreateRequest,
    WeeklyReportResponse,
)
from app.services.daily_report_review_service import DailyReportReviewService

router = APIRouter()


class ReportController:
    """HTTP controller facade for report calendar module."""

    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx
        self.calendar_service = CalendarService(db)
        self.report_service = ReportService(db)
        self.daily_service = DailyReportService(db)
        self.review_service = DailyReportReviewService(db)
        self.weekly_aggregator = WeeklyReportAggregator(db)

    def get_calendar(self, with_metadata: bool = False) -> dict:
        if with_metadata:
            return self.calendar_service.get_calendar_dates_with_metadata(self.ctx.tenant_id)
        return self.calendar_service.get_calendar_dates(self.ctx.tenant_id)

    def get_daily(self, report_date: date, template_id: str, source: str = "default") -> dict:
        from uuid import UUID
        if source != "default":
            return self.daily_service.get_report_detail(
                UUID(self.ctx.tenant_id), UUID(template_id), report_date, source
            )
        return self.review_service.get_effective_report(
            UUID(self.ctx.tenant_id), UUID(template_id), report_date
        )

    def approve_daily_report(self, report_date: date, template_id: str, body: DailyReportReviewRequest) -> dict:
        from uuid import UUID
        user_id = getattr(self.ctx.user, "id", None)
        return self.review_service.approve_report(
            tenant_id=UUID(self.ctx.tenant_id),
            template_id=UUID(template_id),
            report_date=report_date,
            source=body.source,
            manual_edit_id=UUID(body.manual_edit_id) if body.manual_edit_id else None,
            reason=body.reason,
            reviewed_by=UUID(str(user_id)) if user_id else None,
        )

    def reject_daily_report(self, report_date: date, template_id: str, body: DailyReportRejectRequest) -> dict:
        from uuid import UUID
        user_id = getattr(self.ctx.user, "id", None)
        return self.review_service.reject_manual_edit(
            tenant_id=UUID(self.ctx.tenant_id),
            template_id=UUID(template_id),
            report_date=report_date,
            manual_edit_id=UUID(body.manual_edit_id),
            reason=body.reason,
            reviewed_by=UUID(str(user_id)) if user_id else None,
        )

    def finalize_daily_report(self, report_date: date, template_id: str, body: DailyReportReviewRequest) -> dict:
        from uuid import UUID
        user_id = getattr(self.ctx.user, "id", None)
        return self.review_service.finalize_report(
            tenant_id=UUID(self.ctx.tenant_id),
            template_id=UUID(template_id),
            report_date=report_date,
            source=body.source,
            manual_edit_id=UUID(body.manual_edit_id) if body.manual_edit_id else None,
            reason=body.reason,
            reviewed_by=UUID(str(user_id)) if user_id else None,
        )

    def get_daily_diff(self, report_date: date, template_id: str) -> dict:
        from uuid import UUID
        return self.review_service.get_report_diff(
            UUID(self.ctx.tenant_id), UUID(template_id), report_date
        )

    def save_daily_edit(self, report_date: date, template_id: str, body: DailyReportEditRequest) -> dict:
        from uuid import UUID
        user_id = getattr(self.ctx.user, "id", None)
        return self.daily_service.save_manual_edit(
            tenant_id=UUID(self.ctx.tenant_id),
            template_id=UUID(template_id),
            report_date=report_date,
            edited_data=body.data,
            reason=body.reason,
            edited_by=UUID(user_id) if user_id else None,
        )

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
    with_metadata: bool = Query(False, description="Include manual edit metadata"),
):
    controller = ReportController(db, ctx)
    return controller.get_calendar(with_metadata=with_metadata)


@router.get("/daily", response_model=DailyReportDetailResponse)
def get_daily_report(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
    date: date = Query(..., description="Business report date (YYYY-MM-DD)"),
    template_id: str = Query(..., description="Template ID"),
    source: str = Query("default", description="Data source: default|auto|manual"),
):
    controller = ReportController(db, ctx)
    return controller.get_daily(date, template_id, source)


@router.patch("/daily", status_code=status.HTTP_200_OK)
def save_daily_report_edit(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
    body: DailyReportEditRequest = ...,
    date: date = Query(..., description="Business report date (YYYY-MM-DD)"),
    template_id: str = Query(..., description="Template ID"),
):
    controller = ReportController(db, ctx)
    return controller.save_daily_edit(date, template_id, body)


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
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
    week_start: date = Query(..., description="Week start date (Monday, YYYY-MM-DD)"),
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


@router.post("/daily/approve", status_code=status.HTTP_200_OK)
def approve_daily_report(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
    body: DailyReportReviewRequest = ...,
    date: date = Query(..., description="Business report date (YYYY-MM-DD)"),
    template_id: str = Query(..., description="Template ID"),
):
    controller = ReportController(db, ctx)
    return controller.approve_daily_report(date, template_id, body)


@router.post("/daily/reject", status_code=status.HTTP_200_OK)
def reject_daily_report(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
    body: DailyReportRejectRequest = ...,
    date: date = Query(..., description="Business report date (YYYY-MM-DD)"),
    template_id: str = Query(..., description="Template ID"),
):
    controller = ReportController(db, ctx)
    return controller.reject_daily_report(date, template_id, body)


@router.post("/daily/finalize", status_code=status.HTTP_200_OK)
def finalize_daily_report(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_admin),
    db: Session = Depends(get_db),
    body: DailyReportReviewRequest = ...,
    date: date = Query(..., description="Business report date (YYYY-MM-DD)"),
    template_id: str = Query(..., description="Template ID"),
):
    controller = ReportController(db, ctx)
    return controller.finalize_daily_report(date, template_id, body)


@router.get("/daily/diff", response_model=DailyReportDiffResponse)
def get_daily_report_diff(
    ctx: TenantContext = Depends(get_tenant_context),
    role: None = Depends(require_viewer),
    db: Session = Depends(get_db),
    date: date = Query(..., description="Business report date (YYYY-MM-DD)"),
    template_id: str = Query(..., description="Template ID"),
):
    controller = ReportController(db, ctx)
    return controller.get_daily_diff(date, template_id)
