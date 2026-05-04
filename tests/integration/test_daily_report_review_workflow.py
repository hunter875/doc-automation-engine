"""Integration tests for Phase 3: Daily Report Review Workflow."""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.domain.models.daily_report_edit import DailyReportEdit
from app.domain.models.daily_report_review import DailyReportReview
from app.domain.models.extraction_job import ExtractionJob
from app.services.daily_report_review_service import DailyReportReviewService


def make_valid_block_output(report_date: date | None = None, **overrides):
    """Create valid BlockExtractionOutput dict."""
    ngay_bao_cao = (report_date or date(2026, 5, 1)).strftime("%d/%m/%Y")
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


def test_approve_auto_sync_creates_review_snapshot(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test approving auto_sync creates review with snapshot."""
    report_date = date(2026, 5, 1)
    auto_data = make_valid_block_output(report_date)
    wrapped_data = {"data": auto_data}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash1",
        report_version=1,
        extracted_data=wrapped_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    service = DailyReportReviewService(pg_test_session)
    result = service.approve_report(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        source="auto_sync",
        manual_edit_id=None,
        reason="Approved auto data",
        reviewed_by=test_user_pg.id,
    )

    assert result["review_status"] == "approved"
    assert result["approved_source"] == "auto_sync"

    review = (
        pg_test_session.query(DailyReportReview)
        .filter(DailyReportReview.id == uuid.UUID(result["review_id"]))
        .first()
    )
    assert review is not None
    assert review.status == "approved"
    assert review.approved_source == "auto_sync"
    assert review.approved_data == auto_data
    assert review.manual_edit_id is None

    # Verify job unchanged
    pg_test_session.refresh(job)
    assert job.extracted_data == wrapped_data


def test_approve_manual_edit_creates_review_snapshot(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test approving manual_edit creates review with edit snapshot."""
    report_date = date(2026, 5, 2)
    auto_data = make_valid_block_output(report_date)
    wrapped_data = {"data": auto_data}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash2",
        report_version=1,
        extracted_data=wrapped_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    edited_data = make_valid_block_output(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 10}
    )
    edit = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edited_data,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit)
    pg_test_session.commit()

    service = DailyReportReviewService(pg_test_session)
    result = service.approve_report(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        source="manual_edit",
        manual_edit_id=edit.id,
        reason="Approved manual edit",
        reviewed_by=test_user_pg.id,
    )

    assert result["review_status"] == "approved"
    assert result["approved_source"] == "manual_edit"

    review = (
        pg_test_session.query(DailyReportReview)
        .filter(DailyReportReview.id == uuid.UUID(result["review_id"]))
        .first()
    )
    assert review is not None
    assert review.status == "approved"
    assert review.approved_source == "manual_edit"
    assert review.approved_data == edited_data
    assert review.manual_edit_id == edit.id


def test_finalize_manual_edit_makes_detail_return_finalized_snapshot(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test finalized report returns finalized snapshot."""
    report_date = date(2026, 5, 3)
    auto_data = make_valid_block_output(report_date)
    wrapped_data = {"data": auto_data}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash3",
        report_version=1,
        extracted_data=wrapped_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    edited_data = make_valid_block_output(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 15}
    )
    edit = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edited_data,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit)
    pg_test_session.commit()

    service = DailyReportReviewService(pg_test_session)
    result = service.finalize_report(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        source="manual_edit",
        manual_edit_id=edit.id,
        reason="Finalized",
        reviewed_by=test_user_pg.id,
    )

    assert result["review_status"] == "finalized"
    assert result["is_finalized"] is True
    assert result["approved_source"] == "manual_edit"
    assert result["data"]["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_chay"] == 15

    # Get effective report
    effective = service.get_effective_report(test_tenant_pg.id, test_template_pg.id, report_date)
    assert effective["review_status"] == "finalized"
    assert effective["is_finalized"] is True
    assert effective["source"] == "manual_edit"


def test_reject_manual_edit_does_not_delete_edit(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test rejecting manual edit does not delete it."""
    report_date = date(2026, 5, 4)
    auto_data = make_valid_block_output(report_date)
    wrapped_data = {"data": auto_data}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash4",
        report_version=1,
        extracted_data=wrapped_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    edited_data = make_valid_block_output(report_date)
    edit = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edited_data,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit)
    pg_test_session.commit()

    service = DailyReportReviewService(pg_test_session)
    result = service.reject_manual_edit(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        manual_edit_id=edit.id,
        reason="Rejected",
        reviewed_by=test_user_pg.id,
    )

    # Edit still exists
    pg_test_session.refresh(edit)
    assert edit is not None

    # Review created
    review = (
        pg_test_session.query(DailyReportReview)
        .filter(DailyReportReview.manual_edit_id == edit.id)
        .first()
    )
    assert review is not None
    assert review.status == "rejected"


def test_latest_manual_edit_does_not_override_finalized_snapshot(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test finalized snapshot is not overridden by new manual edit."""
    report_date = date(2026, 5, 5)
    auto_data = make_valid_block_output(report_date)
    wrapped_data = {"data": auto_data}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash5",
        report_version=1,
        extracted_data=wrapped_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    # Edit v1
    edit_v1_data = make_valid_block_output(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 20}
    )
    edit_v1 = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edit_v1_data,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit_v1)
    pg_test_session.commit()

    # Finalize v1
    service = DailyReportReviewService(pg_test_session)
    service.finalize_report(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        source="manual_edit",
        manual_edit_id=edit_v1.id,
        reason="Finalized v1",
        reviewed_by=test_user_pg.id,
    )

    # Edit v2 after finalization
    edit_v2_data = make_valid_block_output(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 99}
    )
    edit_v2 = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edit_v2_data,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit_v2)
    pg_test_session.commit()

    # Get effective report
    effective = service.get_effective_report(test_tenant_pg.id, test_template_pg.id, report_date)
    assert effective["review_status"] == "finalized"
    assert effective["data"]["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_chay"] == 20  # v1, not v2


def test_diff_auto_vs_manual_edit(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test diff between auto and manual edit."""
    report_date = date(2026, 5, 6)
    auto_data = make_valid_block_output(report_date)
    wrapped_data = {"data": auto_data}

    job = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash6",
        report_version=1,
        extracted_data=wrapped_data,
        status="ready_for_review",
    )
    pg_test_session.add(job)
    pg_test_session.commit()

    edited_data = make_valid_block_output(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 5}
    )
    edit = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        extraction_job_id=job.id,
        edited_data=edited_data,
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit)
    pg_test_session.commit()

    service = DailyReportReviewService(pg_test_session)
    diff_result = service.get_report_diff(test_tenant_pg.id, test_template_pg.id, report_date)

    assert diff_result["base_source"] == "auto_sync"
    assert diff_result["compare_source"] == "manual_edit"
    assert len(diff_result["changes"]) > 0

    # Find the changed field
    changed = [c for c in diff_result["changes"] if "tong_so_vu_chay" in c["path"]]
    assert len(changed) > 0
    assert changed[0]["auto_value"] == 0
    assert changed[0]["review_value"] == 5


def test_conflict_detected_when_new_extraction_job_after_finalization(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test conflict detection when new job appears after finalization."""
    report_date = date(2026, 5, 7)
    auto_data_v1 = make_valid_block_output(report_date)
    wrapped_v1 = {"data": auto_data_v1}

    job_v1 = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash7a",
        report_version=1,
        extracted_data=wrapped_v1,
        status="ready_for_review",
    )
    pg_test_session.add(job_v1)
    pg_test_session.commit()

    # Finalize based on job_v1
    service = DailyReportReviewService(pg_test_session)
    service.finalize_report(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=report_date,
        source="auto_sync",
        manual_edit_id=None,
        reason="Finalized v1",
        reviewed_by=test_user_pg.id,
    )

    # New job v2 with different hash
    auto_data_v2 = make_valid_block_output(
        report_date,
        phan_I_va_II_chi_tiet_nghiep_vu={"tong_so_vu_chay": 100}
    )
    wrapped_v2 = {"data": auto_data_v2}
    job_v2 = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=report_date,
        parser_used="google_sheets",
        sheet_revision_hash="hash7b",
        report_version=2,
        extracted_data=wrapped_v2,
        status="ready_for_review",
    )
    pg_test_session.add(job_v2)
    pg_test_session.commit()

    # Detect conflict
    has_conflict = service.detect_report_conflict(test_tenant_pg.id, test_template_pg.id, report_date)
    assert has_conflict is True

    # Mark conflict
    service.mark_conflict_if_needed(test_tenant_pg.id, test_template_pg.id, report_date)

    # After marking, effective report should show conflict
    effective = service.get_effective_report(test_tenant_pg.id, test_template_pg.id, report_date)
    assert effective["review_status"] == "conflict_detected"
    assert effective["has_conflict"] is True


def test_calendar_metadata_for_finalized_and_conflict(
    pg_test_session: Session, test_tenant_pg, test_template_pg, test_user_pg, test_document_pg
):
    """Test calendar metadata for finalized, conflict, and manual_edited states."""
    from app.application.report_service import CalendarService

    date_a = date(2026, 5, 10)
    date_b = date(2026, 5, 11)
    date_c = date(2026, 5, 12)

    # Date A: finalized
    job_a = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=date_a,
        parser_used="google_sheets",
        sheet_revision_hash="hashA",
        report_version=1,
        extracted_data={"data": make_valid_block_output(date_a)},
        status="ready_for_review",
    )
    pg_test_session.add(job_a)
    pg_test_session.commit()

    review_service = DailyReportReviewService(pg_test_session)
    review_service.finalize_report(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=date_a,
        source="auto_sync",
        manual_edit_id=None,
        reason="Finalized A",
        reviewed_by=test_user_pg.id,
    )

    # Date B: conflict_detected
    job_b1 = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=date_b,
        parser_used="google_sheets",
        sheet_revision_hash="hashB1",
        report_version=1,
        extracted_data={"data": make_valid_block_output(date_b)},
        status="ready_for_review",
    )
    pg_test_session.add(job_b1)
    pg_test_session.commit()

    review_service.finalize_report(
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=date_b,
        source="auto_sync",
        manual_edit_id=None,
        reason="Finalized B",
        reviewed_by=test_user_pg.id,
    )

    job_b2 = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=date_b,
        parser_used="google_sheets",
        sheet_revision_hash="hashB2",
        report_version=2,
        extracted_data={"data": make_valid_block_output(date_b)},
        status="ready_for_review",
    )
    pg_test_session.add(job_b2)
    pg_test_session.commit()

    review_service.mark_conflict_if_needed(test_tenant_pg.id, test_template_pg.id, date_b)

    # Date C: manual_edited only
    job_c = ExtractionJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        document_id=test_document_pg.id,
        report_date=date_c,
        parser_used="google_sheets",
        sheet_revision_hash="hashC",
        report_version=1,
        extracted_data={"data": make_valid_block_output(date_c)},
        status="ready_for_review",
    )
    pg_test_session.add(job_c)
    pg_test_session.commit()

    edit_c = DailyReportEdit(
        id=uuid.uuid4(),
        tenant_id=test_tenant_pg.id,
        template_id=test_template_pg.id,
        report_date=date_c,
        extraction_job_id=job_c.id,
        edited_data=make_valid_block_output(date_c),
        edited_by=test_user_pg.id,
    )
    pg_test_session.add(edit_c)
    pg_test_session.commit()

    # Verify date_b effective report shows conflict
    effective_b = review_service.get_effective_report(test_tenant_pg.id, test_template_pg.id, date_b)
    assert effective_b["review_status"] == "conflict_detected", f"Expected conflict_detected, got {effective_b['review_status']}"

    # Get calendar
    calendar_service = CalendarService(pg_test_session)
    calendar = calendar_service.get_calendar_dates_with_metadata(str(test_tenant_pg.id))

    days_map = {d["date"]: d for d in calendar["days"]}

    day_a = days_map.get(date_a.isoformat())
    assert day_a is not None
    assert day_a["review_status"] == "finalized"
    assert day_a["is_finalized"] is True

    day_b = days_map.get(date_b.isoformat())
    assert day_b is not None
    assert day_b["review_status"] == "conflict_detected"
    assert day_b.get("has_conflict") is True

    day_c = days_map.get(date_c.isoformat())
    assert day_c is not None
    assert day_c["review_status"] == "manual_edited"
    assert day_c["has_manual_edits"] is True
