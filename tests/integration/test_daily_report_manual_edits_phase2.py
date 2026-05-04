"""Integration tests for Phase 2: Manual Edit for Daily Reports."""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.application.daily_report_service import DailyReportService
from app.core.exceptions import ProcessingError
from app.domain.models.daily_report_edit import DailyReportEdit
from app.domain.models.extraction_job import ExtractionJob


def make_valid_report_payload(report_date: date | None = None, **overrides):
    """Create valid BlockExtractionOutput payload."""
    ngay_bao_cao = (report_date or date(2026, 4, 1)).strftime("%d/%m/%Y")
    payload = {
        "header": {
            "so_bao_cao": "TEST",
            "ngay_bao_cao": ngay_bao_cao,
            "don_vi_bao_cao": "ĐỘI TEST",
            "thoi_gian_tu_den": "",
        },
        "bang_thong_ke": [],
        "danh_sach_cnch": [],
        "danh_sach_chay": [],
        "danh_sach_sclq": [],
        "danh_sach_chi_vien": [],
        "tuyen_truyen_online": {"so_tin_bai": 0, "so_hinh_anh": 0, "cai_app_114": 0},
        "danh_sach_cong_tac_khac": [],
        "danh_sach_cong_van_tham_muu": [],
        "danh_sach_phuong_tien_hu_hong": [],
        "phan_I_va_II_chi_tiet_nghiep_vu": {
            "tong_so_vu_chay": 0,
            "tong_so_vu_no": 0,
            "tong_sclq": 0,
            "tong_so_vu_cnch": 0,
            "quan_so_truc": 0,
            "tong_chi_vien": 0,
            "tong_cong_van": 0,
            "tong_bao_cao": 0,
            "tong_ke_hoach": 0,
            "tong_xe_hu_hong": 0,
            "tong_tin_bai": 0,
            "tong_hinh_anh": 0,
            "so_lan_cai_app_114": 0,
            "chi_tiet_cnch": "",
            "cong_tac_an_ninh": "",
        },
    }
    payload.update(overrides)
    return payload


def test_save_manual_edit_creates_row_without_mutating_job(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test that saving manual edit creates DailyReportEdit without mutating ExtractionJob.extracted_data."""
    report_date = date(2026, 4, 1)
    original_data = {"data": make_valid_report_payload(report_date)}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="test_hash",
        report_version=1,
        extracted_data=original_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()
    pg_test_session.refresh(job)

    service = DailyReportService(pg_test_session)
    edited_payload = make_valid_report_payload(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 5}
    )

    result = service.save_manual_edit(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        edited_data=edited_payload,
        reason="Manual correction",
        edited_by=test_user_pg.id,
    )

    assert result["status"] == "ok"
    assert result["has_manual_edits"] is True

    # Verify edit exists
    edit = (
        pg_test_session.query(DailyReportEdit)
        .filter(DailyReportEdit.id == uuid.UUID(result["edit_id"]))
        .first()
    )
    assert edit is not None
    assert edit.edited_data["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_chay"] == 5
    assert edit.reason == "Manual correction"
    assert edit.edited_by == test_user_pg.id

    # Verify job unchanged
    pg_test_session.refresh(job)
    assert job.extracted_data == original_data


def test_detail_default_returns_auto_when_no_edit(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_document_pg
):
    """Test that detail returns auto_sync when no manual edit exists."""
    report_date = date(2026, 4, 2)
    auto_data = {"data": make_valid_report_payload(report_date)}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="test_hash",
        report_version=1,
        extracted_data=auto_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    service = DailyReportService(pg_test_session)
    detail = service.get_report_detail(
        test_tenant_pg.id, test_template_pg.id, report_date, source="default"
    )

    assert detail["source"] == "auto_sync"
    assert detail["has_manual_edits"] is False
    assert detail["manual_edit_id"] is None
    assert "header" in detail["data"]


def test_detail_default_returns_manual_when_edit_exists(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test that detail returns manual_edit when edit exists."""
    report_date = date(2026, 4, 3)
    auto_data = {"data": make_valid_report_payload(report_date)}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="test_hash",
        report_version=1,
        extracted_data=auto_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    edited_payload = make_valid_report_payload(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 10}
    )
    edit = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edited_payload,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit)
    pg_test_session.commit()

    service = DailyReportService(pg_test_session)
    detail = service.get_report_detail(
        test_tenant_pg.id, test_template_pg.id, report_date, source="default"
    )

    assert detail["source"] == "manual_edit"
    assert detail["has_manual_edits"] is True
    assert detail["manual_edit_id"] == str(edit.id)
    assert detail["data"]["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_chay"] == 10


def test_detail_source_auto_returns_auto_even_with_edit(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test that source=auto returns auto_sync even when manual edit exists."""
    report_date = date(2026, 4, 4)
    auto_data = {"data": make_valid_report_payload(report_date)}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="test_hash",
        report_version=1,
        extracted_data=auto_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    edited_payload = make_valid_report_payload(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 15}
    )
    edit = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edited_payload,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit)
    pg_test_session.commit()

    service = DailyReportService(pg_test_session)
    detail = service.get_report_detail(
        test_tenant_pg.id, test_template_pg.id, report_date, source="auto"
    )

    assert detail["source"] == "auto_sync"
    assert detail["has_manual_edits"] is True
    assert "header" in detail["data"]


def test_detail_source_manual_404_when_no_edit(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_document_pg
):
    """Test that source=manual raises error when no manual edit exists."""
    report_date = date(2026, 4, 5)
    auto_data = {"data": make_valid_report_payload(report_date)}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="test_hash",
        report_version=1,
        extracted_data=auto_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    service = DailyReportService(pg_test_session)
    with pytest.raises(ProcessingError, match="No manual edit found"):
        service.get_report_detail(
            test_tenant_pg.id, test_template_pg.id, report_date, source="manual"
        )


def test_patch_validates_edited_data(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_document_pg
):
    """Test that PATCH validates edited_data and rejects invalid payloads."""
    report_date = date(2026, 4, 6)
    auto_data = {"data": make_valid_report_payload(report_date)}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="test_hash",
        report_version=1,
        extracted_data=auto_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    service = DailyReportService(pg_test_session)
    invalid_payload = {"invalid": "structure"}

    with pytest.raises(ProcessingError, match="Invalid edited_data"):
        service.save_manual_edit(
            tenant_id=test_tenant_pg.id,
            template_id=test_template_pg.id,
            report_date=report_date,
            edited_data=invalid_payload,
        )

    # Verify no edit was created
    edits = pg_test_session.query(DailyReportEdit).filter(
        DailyReportEdit.tenant_id == test_tenant_pg.id,
        DailyReportEdit.report_date == report_date,
    ).all()
    assert len(edits) == 0


def test_calendar_marks_manual_edit(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test that calendar includes manual edit metadata."""
    from app.application.report_service import CalendarService

    date1 = date(2026, 4, 7)
    date2 = date(2026, 4, 8)

    job1 = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=date1,
        parser_used="google_sheets",
        sheet_revision_hash="hash1",
        report_version=1,
        extracted_data={"data": make_valid_report_payload(date1)},
        status="ready_for_review",
    )
    job2 = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=date2,
        parser_used="google_sheets",
        sheet_revision_hash="hash2",
        report_version=1,
        extracted_data={"data": make_valid_report_payload(date2)},
        status="ready_for_review",
    )
    pg_test_session.add_all([job1, job2])
    pg_test_session.commit()

    # Add manual edit for date1 only
    edit = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=date1,
        extraction_job_id=job1.id,
        edited_data=make_valid_report_payload(date1),
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit)
    pg_test_session.commit()

    service = CalendarService(pg_test_session)
    calendar = service.get_calendar_dates_with_metadata(str(test_tenant_pg.id))

    days = calendar["days"]
    day1 = next((d for d in days if d["date"] == date1.isoformat()), None)
    day2 = next((d for d in days if d["date"] == date2.isoformat()), None)

    assert day1 is not None
    assert day1["has_manual_edits"] is True
    assert day1["review_status"] == "manual_edited"
    assert day1["source_displayed_by_default"] == "manual_edit"

    assert day2 is not None
    assert day2["has_manual_edits"] is False
    assert day2["review_status"] == "auto_synced"
    assert day2["source_displayed_by_default"] == "auto_sync"


def test_calendar_does_not_return_data(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_document_pg
):
    """Test that calendar response excludes full data/extracted_data/edited_data fields."""
    from app.application.report_service import CalendarService

    report_date = date(2026, 4, 9)
    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash",
        report_version=1,
        extracted_data={"data": make_valid_report_payload(report_date)},
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    service = CalendarService(pg_test_session)
    calendar = service.get_calendar_dates_with_metadata(str(test_tenant_pg.id))

    for day in calendar["days"]:
        assert "data" not in day
        assert "extracted_data" not in day
        assert "edited_data" not in day
