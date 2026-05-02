"""Report Calendar + Daily/Weekly reporting services."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.domain.models.extraction_job import ExtractionJob, WeeklyReport
from app.domain.workflow import JobStatus


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return default

    text = _to_text(value)
    if not text:
        return default

    cleaned = text.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except Exception:
        return default


def _parse_report_date(value: Any) -> date | None:
    text = _to_text(value)
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m", "%d-%m"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            # If only day/month was provided, assume current year
            if parsed.year == 1900:
                parsed = parsed.replace(year=date.today().year)
            return parsed
        except ValueError:
            continue
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _extract_report_date_from_payload(payload: dict[str, Any]) -> date | None:
    if not isinstance(payload, dict):
        return None

    direct_candidates = [
        payload.get("report_date"),
        payload.get("ngay_bao_cao"),
        _as_dict(payload.get("header")).get("ngay_bao_cao"),
    ]

    nested_data = _as_dict(payload.get("data"))
    direct_candidates.extend(
        [
            nested_data.get("report_date"),
            nested_data.get("ngay_bao_cao"),
            _as_dict(nested_data.get("header")).get("ngay_bao_cao"),
        ]
    )

    for item in direct_candidates:
        parsed = _parse_report_date(item)
        if parsed is not None:
            return parsed

    return None


def _payload_core(extracted_data: dict[str, Any]) -> dict[str, Any]:
    nested = _as_dict(extracted_data.get("data"))
    if nested:
        return nested
    return extracted_data


def _stable_signature(item: Any) -> str:
    if isinstance(item, dict):
        keys = sorted(item.keys())
        return "|".join(f"{key}:{_to_text(item.get(key))}" for key in keys)
    return _to_text(item)


def _merge_unique_items(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for item in items:
        sig = _stable_signature(item)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(item)
    return out


def _merge_bang_thong_ke_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}

    for raw in rows:
        row = _as_dict(raw)
        stt = _to_text(row.get("stt"))
        noi_dung = _to_text(row.get("noi_dung"))
        ket_qua = _to_int(row.get("ket_qua"), 0)

        if stt:
            key = f"stt:{stt}"
        elif noi_dung:
            key = f"noi_dung:{noi_dung.lower()}"
        else:
            continue

        current = by_key.get(key)
        if current is None:
            current = {"stt": stt, "noi_dung": noi_dung, "ket_qua": 0}
            by_key[key] = current

        current["stt"] = current.get("stt") or stt
        current["noi_dung"] = current.get("noi_dung") or noi_dung
        current["ket_qua"] = _to_int(current.get("ket_qua"), 0) + ket_qua

    merged = list(by_key.values())

    def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
        stt = _to_text(item.get("stt"))
        if stt.isdigit():
            return (0, f"{int(stt):04d}")
        return (1, _to_text(item.get("noi_dung")).lower())

    merged.sort(key=_sort_key)
    return merged


class ReportRepository:
    """Persistence and query layer for report calendar module."""

    _REPORTABLE_STATUSES = [
        JobStatus.READY_FOR_REVIEW,
        JobStatus.APPROVED,
        JobStatus.AGGREGATED,
    ]

    def __init__(self, db: Session):
        self.db = db

    def _candidate_jobs(self, tenant_id: str) -> list[ExtractionJob]:
        return (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.status.in_(self._REPORTABLE_STATUSES),
            )
            .all()
        )

    def list_jobs_by_report_date(self, tenant_id: str, report_date: date) -> list[ExtractionJob]:
        jobs = self._candidate_jobs(tenant_id)
        selected: list[ExtractionJob] = []
        for job in jobs:
            payload = job.extracted_data if isinstance(job.extracted_data, dict) else {}
            parsed = _extract_report_date_from_payload(payload)
            if parsed == report_date:
                selected.append(job)
        return selected

    def list_daily_report_dates(self, tenant_id: str) -> set[date]:
        jobs = self._candidate_jobs(tenant_id)
        dates: set[date] = set()
        for job in jobs:
            payload = job.extracted_data if isinstance(job.extracted_data, dict) else {}
            parsed = _extract_report_date_from_payload(payload)
            if parsed is not None:
                dates.add(parsed)
        return dates

    def get_weekly_report(self, tenant_id: str, week_start: date) -> WeeklyReport | None:
        return (
            self.db.query(WeeklyReport)
            .filter(
                WeeklyReport.tenant_id == tenant_id,
                WeeklyReport.week_start == week_start,
            )
            .first()
        )

    def list_weekly_report_starts(self, tenant_id: str) -> set[date]:
        rows = (
            self.db.query(WeeklyReport.week_start)
            .filter(WeeklyReport.tenant_id == tenant_id)
            .all()
        )
        return {week_start for (week_start,) in rows if isinstance(week_start, date)}

    def upsert_weekly_report(
        self,
        *,
        tenant_id: str,
        week_start: date,
        week_end: date,
        report_payload: dict[str, Any],
        sources_used: list[str],
        created_by: str | None,
    ) -> WeeklyReport:
        entity = self.get_weekly_report(tenant_id, week_start)
        if entity is None:
            entity = WeeklyReport(
                tenant_id=tenant_id,
                week_start=week_start,
                week_end=week_end,
                report_payload=report_payload,
                sources_used=sources_used,
                created_by=(UUID(created_by) if created_by else None),
            )
            self.db.add(entity)
        else:
            entity.week_end = week_end
            entity.report_payload = report_payload
            entity.sources_used = sources_used
            entity.generated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(entity)
        return entity


class ReportService:
    """Build canonical daily report payload by report_date."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ReportRepository(db)

    def _split_sources(self, jobs: list[ExtractionJob]) -> tuple[list[ExtractionJob], list[ExtractionJob]]:
        system_jobs: list[ExtractionJob] = []
        sheet_jobs: list[ExtractionJob] = []

        for job in jobs:
            parser_used = _to_text(job.parser_used).lower()
            if parser_used == "google_sheets":
                sheet_jobs.append(job)
            else:
                system_jobs.append(job)

        return system_jobs, sheet_jobs

    def _build_source_payload(self, jobs: list[ExtractionJob]) -> dict[str, Any]:
        bang_rows: list[dict[str, Any]] = []
        cnch_rows: list[dict[str, Any]] = []
        vehicle_rows: list[dict[str, Any]] = []
        other_rows: list[Any] = []
        summary_numeric: dict[str, int] = {}

        job_ids = [str(job.id) for job in jobs]

        for job in jobs:
            payload = job.extracted_data if isinstance(job.extracted_data, dict) else {}
            core = _payload_core(payload)

            bang_rows.extend([_as_dict(item) for item in _as_list(core.get("bang_thong_ke"))])
            cnch_rows.extend([_as_dict(item) for item in _as_list(core.get("danh_sach_cnch"))])
            vehicle_rows.extend([_as_dict(item) for item in _as_list(core.get("danh_sach_phuong_tien_hu_hong"))])
            other_rows.extend(_as_list(core.get("danh_sach_cong_tac_khac")))

            nested_nvu = _as_dict(core.get("phan_I_va_II_chi_tiet_nghiep_vu"))
            for field_name in (
                "tong_so_vu_chay",
                "tong_so_vu_no",
                "tong_so_vu_cnch",
                "tong_xe_hu_hong",
                "tong_cong_van",
                "tong_bao_cao",
                "tong_ke_hoach",
                "quan_so_truc",
                "tong_chi_vien",
            ):
                if field_name in nested_nvu:
                    summary_numeric[field_name] = summary_numeric.get(field_name, 0) + _to_int(
                        nested_nvu.get(field_name),
                        0,
                    )
                elif field_name in core:
                    summary_numeric[field_name] = summary_numeric.get(field_name, 0) + _to_int(
                        core.get(field_name),
                        0,
                    )

        merged_bang = _merge_bang_thong_ke_rows(bang_rows)

        stt_map_numeric: dict[str, int] = {}
        for row in merged_bang:
            stt = _to_text(row.get("stt"))
            if stt.isdigit():
                stt_key = f"stt_{int(stt):02d}"
                stt_map_numeric[stt_key] = _to_int(row.get("ket_qua"), 0)

        total_chay = stt_map_numeric.get("stt_02", summary_numeric.get("tong_so_vu_chay", 0))
        total_no = stt_map_numeric.get("stt_08", summary_numeric.get("tong_so_vu_no", 0))
        total_cnch = stt_map_numeric.get("stt_14", summary_numeric.get("tong_so_vu_cnch", 0))

        summary = {
            **summary_numeric,
            **stt_map_numeric,
            "total_incidents": total_chay + total_no + total_cnch,
            "total_cnch_events": total_cnch,
            "total_damaged_vehicles": len(_merge_unique_items(vehicle_rows)),
        }

        return {
            "job_ids": job_ids,
            "summary": summary,
            "details": {
                "bang_thong_ke": merged_bang,
                "danh_sach_cnch": _merge_unique_items(cnch_rows),
                "danh_sach_phuong_tien_hu_hong": _merge_unique_items(vehicle_rows),
                "danh_sach_cong_tac_khac": _merge_unique_items(other_rows),
            },
        }

    @staticmethod
    def _merge_with_priority(
        system_data: dict[str, Any],
        sheet_data: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        system_summary = _as_dict(system_data.get("summary"))
        sheet_summary = _as_dict(sheet_data.get("summary"))

        merged_summary = dict(sheet_summary)
        for key, value in system_summary.items():
            merged_summary[key] = value

        system_details = _as_dict(system_data.get("details"))
        sheet_details = _as_dict(sheet_data.get("details"))

        merged_details = {
            "bang_thong_ke": _merge_unique_items(
                _as_list(system_details.get("bang_thong_ke"))
                + _as_list(sheet_details.get("bang_thong_ke"))
            ),
            "danh_sach_cnch": _merge_unique_items(
                _as_list(system_details.get("danh_sach_cnch"))
                + _as_list(sheet_details.get("danh_sach_cnch"))
            ),
            "danh_sach_phuong_tien_hu_hong": _merge_unique_items(
                _as_list(system_details.get("danh_sach_phuong_tien_hu_hong"))
                + _as_list(sheet_details.get("danh_sach_phuong_tien_hu_hong"))
            ),
            "danh_sach_cong_tac_khac": _merge_unique_items(
                _as_list(system_details.get("danh_sach_cong_tac_khac"))
                + _as_list(sheet_details.get("danh_sach_cong_tac_khac"))
            ),
            "source_references": {
                "system_job_ids": _as_list(system_data.get("job_ids")),
                "google_sheet_job_ids": _as_list(sheet_data.get("job_ids")),
            },
        }
        return merged_summary, merged_details

    def get_daily_report(self, tenant_id: str, report_date: date) -> dict[str, Any]:
        jobs = self.repository.list_jobs_by_report_date(tenant_id, report_date)
        system_jobs, sheet_jobs = self._split_sources(jobs)

        system_payload = (
            self._build_source_payload(system_jobs)
            if system_jobs
            else {"job_ids": [], "summary": {}, "details": {}}
        )
        sheet_payload = (
            self._build_source_payload(sheet_jobs)
            if sheet_jobs
            else {"job_ids": [], "summary": {}, "details": {}}
        )

        merged_summary, merged_details = self._merge_with_priority(system_payload, sheet_payload)

        data_sources: list[str] = []
        if system_jobs:
            data_sources.append("system")
        if sheet_jobs:
            data_sources.append("google_sheet")

        return {
            "report_date": report_date,
            "data_sources": data_sources,
            "summary": merged_summary,
            "details": merged_details,
        }


class CalendarService:
    """Calendar projection service for report dates having data."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ReportRepository(db)

    def get_calendar_dates(self, tenant_id: str) -> dict[str, Any]:
        daily_dates = self.repository.list_daily_report_dates(tenant_id)
        weekly_starts = self.repository.list_weekly_report_starts(tenant_id)
        merged = sorted(daily_dates.union(weekly_starts))
        return {"dates_with_reports": merged}

    def get_calendar_dates_with_metadata(self, tenant_id: str) -> dict[str, Any]:
        """Calendar with manual edit metadata per date."""
        from app.domain.models.daily_report_edit import DailyReportEdit
        from app.domain.models.extraction_job import ExtractionJob

        daily_dates = self.repository.list_daily_report_dates(tenant_id)
        weekly_starts = self.repository.list_weekly_report_starts(tenant_id)

        # Query latest snapshot jobs for metadata
        jobs = (
            self.db.query(ExtractionJob)
            .filter(
                ExtractionJob.tenant_id == tenant_id,
                ExtractionJob.parser_used == "google_sheets",
                ExtractionJob.sheet_revision_hash.is_not(None),
            )
            .order_by(ExtractionJob.report_date, ExtractionJob.report_version.desc())
            .all()
        )

        # Build latest job per date
        latest_job: dict[date, ExtractionJob] = {}
        for job in jobs:
            d = job.report_date
            if d not in latest_job:
                latest_job[d] = job

        # Query all manual edits for this tenant
        edits = (
            self.db.query(DailyReportEdit.report_date, DailyReportEdit.id)
            .filter(DailyReportEdit.tenant_id == tenant_id)
            .order_by(DailyReportEdit.report_date, DailyReportEdit.created_at.desc())
            .all()
        )

        # Build set of dates with manual edits (latest edit per date)
        edited_dates: dict[date, str] = {}
        for report_date, edit_id in edits:
            if report_date not in edited_dates:
                edited_dates[report_date] = str(edit_id)

        # Build calendar days
        all_dates = sorted(daily_dates.union(weekly_starts))
        days = []
        for d in all_dates:
            job = latest_job.get(d)
            has_edit = d in edited_dates
            day_info = {
                "date": d.isoformat(),
                "has_data": True,
            }
            if job:
                day_info["job_id"] = str(job.id)
                day_info["version"] = job.report_version
                day_info["status"] = job.status or "auto_synced"
                day_info["validation_status"] = "ok"
                day_info["warning_count"] = 0
                day_info["error_count"] = 0
            if has_edit:
                day_info["has_manual_edits"] = True
                day_info["manual_edit_id"] = edited_dates[d]
                day_info["review_status"] = "manual_edited"
                day_info["source_displayed_by_default"] = "manual_edit"
            else:
                day_info["has_manual_edits"] = False
                day_info["review_status"] = "no_edit"
                day_info["source_displayed_by_default"] = "auto_sync"

            days.append(day_info)

        return {"days": days}


class WeeklyReportAggregator:
    """Weekly report generation with deterministic Monday→Sunday aggregation."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ReportRepository(db)
        self.report_service = ReportService(db)

    def _validate_week_start(self, week_start: date) -> None:
        if week_start.weekday() != 0:
            raise ProcessingError(message="week_start must be Monday (YYYY-MM-DD)")

    def generate_weekly_report(
        self,
        *,
        tenant_id: str,
        week_start: date,
        user_id: str | None,
    ) -> WeeklyReport:
        self._validate_week_start(week_start)
        week_end = week_start + timedelta(days=6)

        daily_reports: list[dict[str, Any]] = []
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            daily = self.report_service.get_daily_report(tenant_id, day)
            if daily.get("data_sources"):
                daily_reports.append(daily)

        weekly_summary: dict[str, int] = {}
        bang_rows: list[Any] = []
        cnch_rows: list[Any] = []
        vehicle_rows: list[Any] = []
        other_rows: list[Any] = []
        source_refs_system: list[Any] = []
        source_refs_sheet: list[Any] = []
        all_sources: set[str] = set()

        for daily in daily_reports:
            all_sources.update(_as_list(daily.get("data_sources")))
            summary = _as_dict(daily.get("summary"))
            for key, value in summary.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    weekly_summary[key] = weekly_summary.get(key, 0) + int(value)

            details = _as_dict(daily.get("details"))
            bang_rows.extend(_as_list(details.get("bang_thong_ke")))
            cnch_rows.extend(_as_list(details.get("danh_sach_cnch")))
            vehicle_rows.extend(_as_list(details.get("danh_sach_phuong_tien_hu_hong")))
            other_rows.extend(_as_list(details.get("danh_sach_cong_tac_khac")))

            refs = _as_dict(details.get("source_references"))
            source_refs_system.extend(_as_list(refs.get("system_job_ids")))
            source_refs_sheet.extend(_as_list(refs.get("google_sheet_job_ids")))

        report_payload = {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "days_included": [
                (week_start + timedelta(days=offset)).isoformat()
                for offset in range(7)
            ],
            "daily_reports_count": len(daily_reports),
            "summary": weekly_summary,
            "details": {
                "bang_thong_ke": _merge_bang_thong_ke_rows(
                    [_as_dict(item) for item in bang_rows]
                ),
                "danh_sach_cnch": _merge_unique_items(cnch_rows),
                "danh_sach_phuong_tien_hu_hong": _merge_unique_items(vehicle_rows),
                "danh_sach_cong_tac_khac": _merge_unique_items(other_rows),
                "source_references": {
                    "system_job_ids": _merge_unique_items(source_refs_system),
                    "google_sheet_job_ids": _merge_unique_items(source_refs_sheet),
                },
            },
        }

        sources_used = sorted(all_sources)
        return self.repository.upsert_weekly_report(
            tenant_id=tenant_id,
            week_start=week_start,
            week_end=week_end,
            report_payload=report_payload,
            sources_used=sources_used,
            created_by=user_id,
        )
