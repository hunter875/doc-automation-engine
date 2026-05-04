"""Schemas for Report Calendar and Weekly Report APIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class CalendarDayResponse(BaseModel):
    date: str
    has_data: bool = True
    job_id: str | None = None
    version: int | None = None
    status: str | None = None
    validation_status: str | None = None
    warning_count: int = 0
    error_count: int = 0
    has_manual_edits: bool = False
    manual_edit_id: str | None = None
    review_status: str | None = None
    source_displayed_by_default: str | None = None
    is_finalized: bool = False
    has_conflict: bool = False
    approved_source: str | None = None


class CalendarResponse(BaseModel):
    dates_with_reports: list[date] = Field(default_factory=list)
    days: list[CalendarDayResponse] = Field(default_factory=list)


class DailyReportEditRequest(BaseModel):
    data: dict[str, Any]
    reason: str | None = None


class DailyReportDetailResponse(BaseModel):
    date: str
    job_id: str
    version: int | None = None
    source: str
    has_manual_edits: bool
    manual_edit_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    validation_report: dict[str, Any] = Field(default_factory=dict)
    review_status: str | None = None
    is_finalized: bool = False
    review_id: str | None = None
    approved_source: str | None = None
    has_conflict: bool = False


class DailyReportResponse(BaseModel):
    report_date: date
    data_sources: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class WeeklyReportCreateRequest(BaseModel):
    week_start: date


class WeeklyReportResponse(BaseModel):
    id: str
    week_start: date
    week_end: date
    generated_at: datetime
    report_payload: dict[str, Any] = Field(default_factory=dict)
    sources_used: list[str] = Field(default_factory=list)


class DailyReportReviewRequest(BaseModel):
    source: str  # "auto_sync" or "manual_edit"
    manual_edit_id: str | None = None
    reason: str | None = None


class DailyReportRejectRequest(BaseModel):
    manual_edit_id: str
    reason: str | None = None


class DailyReportDiffResponse(BaseModel):
    report_date: str
    base_source: str
    compare_source: str
    changes: list[dict[str, Any]] = Field(default_factory=list)
