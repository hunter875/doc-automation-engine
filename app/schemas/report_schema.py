"""Schemas for Report Calendar and Weekly Report APIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class CalendarResponse(BaseModel):
    dates_with_reports: list[date] = Field(default_factory=list)


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
