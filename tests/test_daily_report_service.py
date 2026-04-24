from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from app.application.daily_report_service import (
    DailyReportService,
    build_daily_dataset,
    build_daily_operational_context,
)


@dataclass
class _FakeBody:
    payload: bytes

    def read(self):
        return self.payload


def _job(
    *,
    row_hash: str | None = None,
    row_status: str | None = None,
    parser_used: str = "google_sheets",
    extracted_data: dict | None = None,
):
    source_refs = {}
    if row_hash is not None:
        source_refs["row_hash"] = row_hash
    if row_status is not None:
        source_refs["row_status"] = row_status
    return SimpleNamespace(
        id=uuid.uuid4(),
        source_references=source_refs,
        parser_used=parser_used,
        extracted_data=extracted_data if extracted_data is not None else {"x": 1},
        reviewed_data=None,
        enriched_data=None,
        final_data={"x": 1},
    )


def _op_payload(stt14: int, *, include_cnch: bool = True, include_vehicle: bool = True) -> dict:
    return {
        "bang_thong_ke": [
            {"stt": "2", "noi_dung": "Tổng số vụ cháy", "ket_qua": 1},
            {"stt": "8", "noi_dung": "Tổng số vụ nổ", "ket_qua": 0},
            {"stt": "14", "noi_dung": "Tổng số vụ CNCH", "ket_qua": stt14},
        ],
        "danh_sach_cnch": (
            [
                {
                    "ngay_xay_ra": "20/04/2026",
                    "thoi_gian": "09:30",
                    "dia_diem": "P1",
                    "noi_dung_tin_bao": "CNCH A",
                }
            ]
            if include_cnch
            else []
        ),
        "danh_sach_phuong_tien_hu_hong": (
            [{"bien_so": "61A-123.45", "tinh_trang": "Hỏng nhẹ"}] if include_vehicle else []
        ),
        "danh_sach_cong_tac_khac": ["Tuần tra địa bàn"],
    }


def test_build_daily_dataset_empty_day():
    result = build_daily_dataset([])

    assert result["jobs_total"] == 0
    assert result["jobs_selected"] == 0
    assert result["duplicates_skipped"] == 0
    assert result["partial_rows"] == 0


def test_build_daily_dataset_multiple_jobs_selected():
    jobs = [_job(row_hash="h1", row_status="VALID"), _job(row_hash="h2", row_status="VALID")]

    result = build_daily_dataset(jobs)

    assert result["jobs_total"] == 2
    assert result["jobs_selected"] == 2
    assert result["duplicates_skipped"] == 0


def test_build_daily_dataset_duplicate_rerun_deduplicates_by_row_hash():
    jobs = [_job(row_hash="same", row_status="VALID"), _job(row_hash="same", row_status="VALID")]

    result = build_daily_dataset(jobs)

    assert result["jobs_total"] == 2
    assert result["jobs_selected"] == 1
    assert result["duplicates_skipped"] == 1


def test_build_daily_dataset_counts_partial_rows():
    jobs = [_job(row_hash="h1", row_status="PARTIAL"), _job(row_hash="h2", row_status="VALID")]

    result = build_daily_dataset(jobs)

    assert result["jobs_selected"] == 2
    assert result["partial_rows"] == 1
    assert result["row_status_counts"]["PARTIAL"] == 1


def test_build_daily_dataset_mixed_pdf_and_sheet():
    sheet_1 = _job(row_hash="sheet-h1", row_status="VALID", parser_used="google_sheets")
    sheet_dup = _job(row_hash="sheet-h1", row_status="VALID", parser_used="google_sheets")
    pdf_job = _job(row_hash=None, row_status=None, parser_used="pdfplumber")

    result = build_daily_dataset([sheet_1, sheet_dup, pdf_job])

    assert result["jobs_total"] == 3
    assert result["jobs_selected"] == 2
    assert result["duplicates_skipped"] == 1
    assert result["row_status_counts"]["UNKNOWN"] == 1


def test_build_daily_operational_context_computes_explicit_daily_values_from_extracted_data():
    jobs = [
        _job(row_hash="h1", row_status="VALID", extracted_data=_op_payload(2)),
        _job(row_hash="h2", row_status="VALID", extracted_data=_op_payload(1, include_cnch=False, include_vehicle=False)),
    ]

    context = build_daily_operational_context(
        jobs,
        report_date=date(2026, 4, 20),
        report_name="Daily Ops",
        report_description="desc",
    )

    assert context["total_chay_incidents"] == 2
    assert context["total_no_incidents"] == 0
    assert context["total_cnch_events"] == 3
    assert context["total_incidents"] == 5
    assert context["total_damaged_vehicles"] == 1
    assert context["stt_14_tong_cnch"] == 3
    assert len(context["daily_operational_state"]["bang_thong_ke"]) >= 3


def test_generate_daily_report_empty_day_returns_no_data(monkeypatch: pytest.MonkeyPatch):
    service = DailyReportService(db=object())
    monkeypatch.setattr(service, "_load_jobs_for_day", lambda **_: [])

    result = service.generate_daily_report(
        tenant_id="tenant-1",
        user_id="user-1",
        template_id=str(uuid.uuid4()),
        report_date=date(2026, 4, 20),
    )

    assert result["status"] == "no_data"
    assert result["report_id"] is None


def test_generate_daily_report_created(monkeypatch: pytest.MonkeyPatch):
    from app.application import daily_report_service as module

    jobs = [
        _job(row_hash="h1", row_status="VALID", extracted_data=_op_payload(2)),
        _job(row_hash="h2", row_status="PARTIAL", extracted_data=_op_payload(1)),
    ]

    class _FakeDB:
        def add(self, obj):
            self.obj = obj

        def commit(self):
            return None

        def refresh(self, obj):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    service = DailyReportService(db=_FakeDB())
    monkeypatch.setattr(service, "_load_jobs_for_day", lambda **_: jobs)

    class _FakeTemplateMgr:
        def __init__(self, db):
            self.db = db

        def get_template(self, template_id, tenant_id):
            return SimpleNamespace(word_template_s3_key="templates/t1.docx")

    monkeypatch.setattr(module, "TemplateManager", _FakeTemplateMgr)
    monkeypatch.setattr(module.s3_client, "get_object", lambda **_: {"Body": _FakeBody(b"tpl")})

    uploaded = {}

    def _put_object(**kwargs):
        uploaded.update(kwargs)
        return {}

    monkeypatch.setattr(module.s3_client, "put_object", _put_object)

    from app.utils import word_export as word_mod
    captured_context = {}

    def _render_word_template(**kwargs):
        captured_context.update(kwargs.get("context_data") or {})
        return b"rendered"

    monkeypatch.setattr(word_mod, "render_word_template", _render_word_template)

    result = service.generate_daily_report(
        tenant_id="tenant-1",
        user_id="user-1",
        template_id=str(uuid.uuid4()),
        report_date=date(2026, 4, 20),
    )

    assert result["status"] == "created"
    assert result["jobs_total"] == 2
    assert result["jobs_selected"] == 2
    assert result["partial_rows"] == 1
    assert result["output_s3_key"].endswith(".docx")
    assert uploaded["Body"] == b"rendered"
    assert captured_context["total_cnch_events"] == 3
    assert captured_context["daily_operational_state"]["bang_thong_ke"]
