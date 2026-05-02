"""Integration tests for KV30 GoogleSheetIngestionService.

Tests the complete flow:
  GoogleSheetsSource (mocked)
    -> DailyReportBuilder (hardcoded KV30 mapping)
    -> GoogleSheetIngestionService
    -> real ExtractionJob records in PostgreSQL

No real Google Sheets API, no real S3.
Uses PostgreSQL test DB via pg_test_session fixture.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.domain.models.extraction_job import ExtractionJob
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.sheet_ingestion_service import GoogleSheetIngestionService, IngestionRequest

# ────────────────────────────────────────────────────────────────
# KV30 fixture data (matching test_kv30_excel_daily_report_builder.py)
# ────────────────────────────────────────────────────────────────

def _bc_ngay_rows() -> list[list[Any]]:
    rows = [
        [
            "NGAY", "THANG",
            "VU CHAY VA CNCH\nVU CHAY\nTHONG KE",
            "SCLQ DEN\nPCCC&\nCNCH",
            "CHI VIEN",
            "CNCH",
            "CONG TAC KIEM TRA DINH KY NHOM I", "NHOM II",
            "DOT XUAT NHOM I", "NHOM II",
            "HUONG DAN", "KIEN\nNGHI", "XU PHAT", "TIEN PHAT\n(trieu dong)", "DINH CHI", "PHUC HOI",
            "TUYEN TRUYEN PCCC TIN BAI", "PHONG SU",
            "SO LOP TUYEN TRUYEN", "SO NGUOI THAM DU", "SO KHUYEN CAO, TO ROI DA PHAT",
            "HUAN LUYEN PCCC SO LOP HUAN LUYEN", "SO NGUOI THAM DU",
            "TONG TUYEN TRUYEN/HUAN LUYEN SO LOP", "SO NGUOI THAM DU",
            "PACC&CNCH co so theo mau PC06 SO PA XAY DUNG VA PHE DUYET", "SO PA DUOC THUC TAP",
            "PACC&CNCH co quan cap cao theo mau PC08 SO PA XAY DUNG VA PHE DUYET", "SO PA DUOC THUC TAP",
            "PA CNCH co quan cap cao theo mau PC09 SO PA XAY DUNG VA PHE DUYET", "SO PA DUOC THUC TAP",
            "PACC&CNCH phuong tien giao thong theo mau PC07 SO PA XAY DUNG VA PHE DUYET", "SO PA DUOC THUC TAP",
            "Ghi chu",
        ],
    ]
    data = [
        [25.0, 3.0, 1.0, 0.0, 0.0, 0.0, 12.0, 2.0, 0.0, 0.0, 84.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 675.0, 0.0, 0.0, 1.0, 675.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],
        [21.0, 3.0, 0.0, 0.0, 0.0, 1.0, 8.0, 1.0, 0.0, 0.0, 45.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 340.0, 0.0, 0.0, 1.0, 340.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],
        [31.0, 3.0, 0.0, 0.0, 1.0, 0.0, 8.0, 1.0, 0.0, 0.0, 42.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 1.0, 320.0, 0.0, 0.0, 1.0, 320.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],
        [10.0, 4.0, 0.0, 0.0, 1.0, 1.0, 15.0, 3.0, 0.0, 0.0, 95.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 2.0, 890.0, 0.0, 0.0, 2.0, 890.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ""],
    ]
    for row in data:
        rows.append(row)
    return rows


def _cnch_rows() -> list[list[Any]]:
    return [
        ["CUU NAN, CUU HO"],
        ["STT", "Loai hinh CNCH", "Ngay xay ra su co", "Thoi gian den",
         "Dia diem", "Dia chi", "Chi huy CNCH", "Thiet hai ve nguoi", "So nguoi cuu duoc"],
        [1.0, "Tai nan may ket trong thiet bi", "20/03/2026", "16 gio 33 phut",
         "Cong ty TNHH che bien go Minh Tri",
         "47/1 khu pho Binh Phuoc B, phuong An Phu, thanh pho Ho Chi Minh",
         "Thieu ta Nguyen Lam Vu", "0", 0.0],
        [2.0, "Vu chay", "09/04/2026", "22 gio 36 phut",
         "Khu dan cu Phu Hung",
         "123 duong so 5, phuong Binh Chieu, thanh pho Ho Chi Minh",
         "Dai ta Tran Minh Hoang", "0", 0.0],
    ]


def _vu_chay_rows() -> list[list[Any]]:
    return [
        ["Vu chay CO Thong ke"],
        ["STT", "NGAY XAY RA VU CHAY", "VU CHAY", "THOI GIAN", "DIA DIEM",
         "PHAN LOAI", "NGUYEN NHAN", "THIET HAI VE NGUOI",
         "THIET HAI TAI SAN", "TAI SAN CUU CHUA",
         "THOI GIAN TOI DAM CHAY", "THOI GIAN KHONG CHE", "THOI GIAN DAP TAT HOAN TOAN",
         "SO LUONG XE", "CHI HUY CHUA CHAY", "GHI CHU"],
        [1.0, "24/03/2026", "Chay cua hang vat lieu xay dung", "17 gio 20 phut",
         "18/5 to 12 khu pho Tan Thang, phuong An Phu, TP. Thu Duc",
         "Chay", "Chap dien", "0", "350 trieu dong", "Khong co",
         "17 gio 25 phut", "17 gio 40 phut", "18 gio 05 phut",
         3.0, "Thieu ta Nguyen Van Minh", "Da xu ly"],
    ]


def _chi_vien_rows() -> list[list[Any]]:
    return [
        ["VU CHAY CHI VIEN"],
        ["STT", "VU CHAY NGAY", "DIA DIEM", "KHU VUC QUAN LY",
         "SO LUONG XE", "THOI GIAN DI", "THOI GIAN VE",
         "CHI HUY CHUA CHAY", "GHI CHU"],
        [1.0, "09/04/2026", "So 23/8A khu pho Tan Phuoc, phuong Tan Dong Hiep, TPHCM",
         "Doi CC&CNCH KV33", 2.0, "20 gio 29 phut", "23 gio 15 phut",
         "Thieu ta Le Minh Thanh", "Chi vien PCCC"],
        [2.0, "31/03/2026", "Khu cong nghiep Song Than 2, phuong An Binh, thanh pho Di An",
         "Doi CC&CNCH KV33", 3.0, "02 gio 48 phut", "05 gio 12 phut",
         "Dai uy Pham Van Hung", "Chi vien chua chay"],
    ]


def _sclq_rows() -> list[list[Any]]:
    return [
        ["SU CO LIEN QUAN DEN PCCC&CNCH"],
        ["STT", "VU CHAY NGAY", "DIA DIEM", "NGUYEN NHAN", "THIET HAI",
         "CHI HUY CHUA CHAY", "GHI CHU"],
        [1.0, "10/04/2026", "Khu vuc cau Rach Chien, phuong An Phu, TP. Thu Duc",
         "Chap dien", "Khong co thiet hai",
         "Dai ta Tran Minh Hoang", "Su co nho, xu ly nhanh"],
    ]


KV30_CONFIGS = [
    {
        "worksheet": "BC NGAY",
        "schema_path": "bc_ngay_kv30_schema.yaml",
        "role": "master",
        "header_row": 0,
        "data_start_row": 1,
        "target_section": None,
    },
    {
        "worksheet": "CNCH",
        "schema_path": "cnch_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_cnch",
    },
    {
        "worksheet": "VU CHAY THONG KE",
        "schema_path": "vu_chay_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_chay",
    },
    {
        "worksheet": "CHI VIEN",
        "schema_path": "chi_vien_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_chi_vien",
    },
    {
        "worksheet": "SCLQ DEN PCCC&CNCH",
        "schema_path": "sclq_kv30_schema.yaml",
        "role": "detail",
        "header_row": 1,
        "data_start_row": 2,
        "target_section": "danh_sach_sclq",
    },
]


# ────────────────────────────────────────────────────────────────
# Test helpers
# ────────────────────────────────────────────────────────────────

def _make_sheet_data() -> dict[str, list[list[Any]]]:
    return {
        "BC NGAY": _bc_ngay_rows(),
        "CNCH": _cnch_rows(),
        "VU CHAY THONG KE": _vu_chay_rows(),
        "CHI VIEN": _chi_vien_rows(),
        "SCLQ DEN PCCC&CNCH": _sclq_rows(),
    }


def _make_req(tenant_id: str, template_id: str, user_id: str, document_id: str | None = None) -> IngestionRequest:
    return IngestionRequest(
        tenant_id=tenant_id,
        user_id=user_id,
        template_id=template_id,
        sheet_id="test-sheet-id",
        worksheet="",
        schema_path="",
        source_document_id=None,  # Always let service create snapshot document
        configs=KV30_CONFIGS,
    )


# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def kv30_sheet_data():
    return _make_sheet_data()


@pytest.fixture
def mock_sheets_source(kv30_sheet_data, monkeypatch):
    from app.engines.extraction.sources.sheets_source import GoogleSheetsSource

    def _fake_fetch(self, config):
        ws = config.worksheet
        return kv30_sheet_data.get(ws, [])

    monkeypatch.setattr(GoogleSheetsSource, "fetch_values", _fake_fetch)
    return kv30_sheet_data


# Mock S3 upload so DocumentService.create_document does not fail
@pytest.fixture(autouse=True)
def mock_s3_for_tests(monkeypatch):
    """Mock S3 client for tests that create documents."""
    import boto3
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.put_object.return_value = {}
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"test")
    }
    monkeypatch.setattr("app.application.doc_service.s3_client", mock_client)
    # Also patch the module-level s3_client
    import app.application.doc_service
    monkeypatch.setattr(app.application.doc_service, "s3_client", mock_client)
    return mock_client


# ────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────

class TestKV30IngestionService:
    """Phase 1B: KV30 persistence and extracted_data structure."""

    @pytest.mark.asyncio
    async def test_ingestion_creates_one_job_per_date(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """KV30 data should produce 4 jobs: 25/03, 21/03, 31/03, 10/04."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        summary = await service.ingest(req)

        assert summary["status"] == "ok"
        assert summary["dates_created"] == 4, f"Expected 4 jobs, got {summary}"
        assert set(summary["dates"]) == {"10/04", "21/03", "25/03", "31/03"}

    @pytest.mark.asyncio
    async def test_extracted_data_wrapper_structure(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """extracted_data must have source=google_sheet, data key with BlockExtractionOutput JSON."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        jobs = pg_test_session.query(ExtractionJob).all()
        assert len(jobs) == 4

        for job in jobs:
            ed = job.extracted_data
            assert isinstance(ed, dict), f"extracted_data should be dict for job {job.id}"
            assert ed.get("source") == "google_sheet", f"Expected source=google_sheet, got {ed.get('source')}"
            assert ed.get("sheet_id") == "test-sheet-id"
            assert "date_key" in ed
            assert "data" in ed, "extracted_data must have 'data' key"
            assert "debug" in ed

    @pytest.mark.asyncio
    async def test_extracted_data_data_validates_against_block_output(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """extracted_data['data'] must validate against BlockExtractionOutput."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        jobs = pg_test_session.query(ExtractionJob).all()
        for job in jobs:
            ed = job.extracted_data
            data = ed.get("data", {})
            BlockExtractionOutput.model_validate(data)  # raises if invalid

    @pytest.mark.asyncio
    async def test_job_report_dates_match_date_keys(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """report_date column must match the date_key in extracted_data."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        jobs = pg_test_session.query(ExtractionJob).all()
        for job in jobs:
            ed = job.extracted_data
            date_key = ed["date_key"]  # e.g. "10/04"
            day, month = date_key.split("/")
            expected_year = 2026
            from datetime import date
            expected = date(expected_year, int(month), int(day))
            assert job.report_date == expected, (
                f"Job {job.id}: report_date={job.report_date} != expected {expected} (date_key={date_key})"
            )

    @pytest.mark.asyncio
    async def test_report_10_04_has_cnch_and_chi_vien_and_sclq(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """10/04 report must contain CNCH (09/04 22:36), CHI VIEN (09/04 20:29), and SCLQ (10/04)."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        job_10 = next(
            (j for j in pg_test_session.query(ExtractionJob).all()
             if j.extracted_data and j.extracted_data.get("date_key") == "10/04"),
            None,
        )
        assert job_10 is not None, "10/04 job not found"

        ed = job_10.extracted_data
        data = ed["data"]
        assert len(data["danh_sach_cnch"]) >= 1, f"Expected CNCH in 10/04, got {data['danh_sach_cnch']}"
        assert len(data["danh_sach_chi_vien"]) >= 1, f"Expected CHI VIEN in 10/04, got {data['danh_sach_chi_vien']}"
        assert len(data["danh_sach_sclq"]) >= 1, f"Expected SCLQ in 10/04, got {data['danh_sach_sclq']}"

    @pytest.mark.asyncio
    async def test_report_25_03_has_vu_chay(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """25/03 report must contain vu chay (24/03)."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        job_25 = next(
            (j for j in pg_test_session.query(ExtractionJob).all()
             if j.extracted_data and j.extracted_data.get("date_key") == "25/03"),
            None,
        )
        assert job_25 is not None, "25/03 job not found"

        ed = job_25.extracted_data
        data = ed["data"]
        assert len(data.get("danh_sach_chay", [])) >= 1, (
            f"Expected danh_sach_chay in 25/03, got {data.get('danh_sach_chay')}"
        )

    @pytest.mark.asyncio
    async def test_report_31_03_has_chi_vien(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """31/03 report must contain CHI VIEN (31/03 02:55 before cutoff)."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        job_31 = next(
            (j for j in pg_test_session.query(ExtractionJob).all()
             if j.extracted_data and j.extracted_data.get("date_key") == "31/03"),
            None,
        )
        assert job_31 is not None, "31/03 job not found"

        ed = job_31.extracted_data
        data = ed["data"]
        chi_vien_items = data.get("danh_sach_chi_vien", [])
        assert len(chi_vien_items) >= 1, (
            f"31/03 report should have CHI VIEN item (31/03 02:55 before cutoff), got {chi_vien_items}"
        )
        dates = {item.get("ngay") for item in chi_vien_items}
        assert "31/03/2026" in dates, (
            f"Expected 31/03/2026 in 31/03 report, got {dates}"
        )

    @pytest.mark.asyncio
    async def test_idempotency_same_data_no_duplicate_jobs(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """Running ingestion twice with identical data must not create duplicate jobs."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)

        first = await service.ingest(req)
        assert first["dates_created"] == 4

        second = await service.ingest(req)
        assert second["dates_created"] == 0, (
            f"Second run should create 0 jobs (duplicate), got {second['dates_created']}"
        )
        assert second["dates_duplicate"] == 4, (
            f"Second run should report 4 duplicates, got {second['dates_duplicate']}"
        )

        # Total jobs in DB should still be 4
        all_jobs = pg_test_session.query(ExtractionJob).all()
        assert len(all_jobs) == 4, (
            f"After 2 identical ingestions, expected 4 jobs total, got {len(all_jobs)}"
        )

    @pytest.mark.asyncio
    async def test_idempotency_uncontrolled_duplicates_prevented(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """Even if some jobs exist in DB, duplicate hash must prevent creating more."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)

        # Run 3 times
        await service.ingest(req)
        await service.ingest(req)
        third = await service.ingest(req)

        # All 3 runs should result in exactly 4 jobs total
        all_jobs = pg_test_session.query(ExtractionJob).all()
        assert len(all_jobs) == 4, (
            f"After 3 identical ingestions, expected exactly 4 jobs (no uncontrolled duplicates), got {len(all_jobs)}"
        )
        assert third["dates_created"] == 0
        assert third["dates_duplicate"] == 4

    @pytest.mark.asyncio
    async def test_version_bump_when_data_changes(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests, monkeypatch,
    ):
        """When data changes, same date should get a new version job (not duplicate)."""
        # First ingestion with original data
        sheet_data_original = _make_sheet_data()

        from app.engines.extraction.sources.sheets_source import GoogleSheetsSource

        def _fetch_original(self, config):
            return sheet_data_original.get(config.worksheet, [])

        monkeypatch.setattr(GoogleSheetsSource, "fetch_values", _fetch_original)

        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        first = await service.ingest(req)
        assert first["dates_created"] == 4

        # Change CNCH data: remove 09/04 entry
        sheet_data_changed = _make_sheet_data()
        # Remove row [2.0, "Vu chay", "09/04/2026", ...] from CNCH
        sheet_data_changed["CNCH"] = [
            sheet_data_changed["CNCH"][0],
            sheet_data_changed["CNCH"][1],
            sheet_data_changed["CNCH"][2],  # only 20/03 entry remains
        ]

        def _fetch_changed(self, config):
            return sheet_data_changed.get(config.worksheet, [])

        monkeypatch.setattr(GoogleSheetsSource, "fetch_values", _fetch_changed)

        second = await service.ingest(req)
        assert second["dates_created"] == 4, (
            f"Changed data should create 4 new versioned jobs, got {second}"
        )

        # Verify version numbers
        jobs = pg_test_session.query(ExtractionJob).order_by(ExtractionJob.report_version).all()
        versions_by_date = {}
        for j in jobs:
            dk = j.extracted_data["date_key"]
            versions_by_date.setdefault(dk, []).append(j.report_version)

        for dk, versions in versions_by_date.items():
            assert len(versions) == 2, (
                f"Date {dk} should have exactly 2 versions, got {versions}"
            )
            assert versions[0] == 1
            assert versions[1] == 2

    @pytest.mark.asyncio
    async def test_10_04_job_report_date_matches_09_04_cutoff(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """CHI VIEN 09/04/2026 20:29 (>=07:30) -> report 10/04, not 09/04."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        # Find 10/04 job
        job_10 = next(
            (j for j in pg_test_session.query(ExtractionJob).all()
             if j.extracted_data and j.extracted_data.get("date_key") == "10/04"),
            None,
        )
        assert job_10 is not None

        # Verify 10/04 job has CHI VIEN item from 09/04 event
        data = job_10.extracted_data["data"]
        chi_vien_items = data.get("danh_sach_chi_vien", [])
        assert len(chi_vien_items) >= 1
        dates_in_chi_vien = {item.get("ngay") for item in chi_vien_items}
        assert "09/04/2026" in dates_in_chi_vien, (
            f"Expected 09/04/2026 in CHI VIEN dates for 10/04 report, got {dates_in_chi_vien}"
        )

    @pytest.mark.asyncio
    async def test_31_03_job_has_chi_vien_before_cutoff(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """CHI VIEN 31/03/2026 02:55 (<07:30) -> report 31/03 stays same day."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        job_31 = next(
            (j for j in pg_test_session.query(ExtractionJob).all()
             if j.extracted_data and j.extracted_data.get("date_key") == "31/03"),
            None,
        )
        assert job_31 is not None

        data = job_31.extracted_data["data"]
        chi_vien_items = data.get("danh_sach_chi_vien", [])
        assert len(chi_vien_items) >= 1, (
            f"31/03 report should have CHI VIEN item (31/03 02:55 before cutoff), got {chi_vien_items}"
        )
        dates = {item.get("ngay") for item in chi_vien_items}
        assert "31/03/2026" in dates, (
            f"Expected 31/03/2026 in 31/03 report, got {dates}"
        )

    @pytest.mark.asyncio
    async def test_json_serialization_of_extracted_data(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """extracted_data must serialize to JSON without errors."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        jobs = pg_test_session.query(ExtractionJob).all()
        for job in jobs:
            ed = job.extracted_data
            json_str = json.dumps(ed, ensure_ascii=False)
            assert json_str  # not empty
            restored = json.loads(json_str)
            assert restored["source"] == "google_sheet"
            assert "data" in restored
            assert "debug" in restored

    @pytest.mark.asyncio
    async def test_status_is_extracted(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """All KV30 jobs should have status='extracted' (no manual review needed)."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        jobs = pg_test_session.query(ExtractionJob).all()
        for job in jobs:
            assert job.status == "extracted", (
                f"Job {job.id} should have status='extracted', got '{job.status}'"
            )

    @pytest.mark.asyncio
    async def test_parser_is_google_sheets(
        self, pg_test_session, test_tenant_pg, test_user_pg, test_template_pg,
        mock_sheets_source, mock_s3_for_tests,
    ):
        """All KV30 jobs should have parser_used='google_sheets'."""
        req = _make_req(
            str(test_tenant_pg.id), str(test_template_pg.id),
            str(test_user_pg.id), str(uuid.uuid4()),
        )
        service = GoogleSheetIngestionService(pg_test_session)
        await service.ingest(req)

        jobs = pg_test_session.query(ExtractionJob).all()
        for job in jobs:
            assert job.parser_used == "google_sheets", (
                f"Job {job.id} should have parser_used='google_sheets', got '{job.parser_used}'"
            )
