from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.engines.extraction.mapping.schema_loader import FieldSchema, IngestionSchema
from app.engines.extraction.sheet_ingestion_service import GoogleSheetIngestionService, IngestionRequest
from app.engines.extraction.validation.row_validator import RowValidationResult


@dataclass
class _DummyModel:
    pass


class _FakeWriter:
    seen_hashes: set[str] = set()

    def __init__(self, *args, **kwargs) -> None:
        pass

    @staticmethod
    def build_fingerprint(source_doc):
        return f"fp:{source_doc.get('row_index')}"

    @staticmethod
    def build_row_hash(data_payload):
        return str(sorted(data_payload.items()))

    def is_duplicate(self, row_hash: str) -> bool:
        return row_hash in self.seen_hashes

    def write_row(self, *, row_document, confidence, source_references):
        row_hash = str(source_references.get("row_hash") or "")
        if row_hash in self.seen_hashes:
            return False, None
        self.seen_hashes.add(row_hash)
        return True, "job-1"


@pytest.fixture
def _schema() -> IngestionSchema:
    return IngestionSchema(
        fields=[
            FieldSchema(
                name="ngay_bao_cao",
                aliases=["Ngày báo cáo", "ngay_bao_cao"],
                field_type="string",
                required=True,
                default=None,
                transform=None,
            ),
            FieldSchema(
                name="tong_so_vu",
                aliases=["Tổng số vụ", "tong_so_vu"],
                field_type="integer",
                required=False,
                default=0,
                transform=None,
            ),
        ]
    )


@pytest.fixture(autouse=True)
def _reset_hashes():
    _FakeWriter.seen_hashes = set()


def _patch_common(monkeypatch: pytest.MonkeyPatch, rows, schema: IngestionSchema):
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.load_schema", lambda *_: schema)
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.build_validation_model", lambda *_: _DummyModel())

    def _fake_validate_row(*, model, normalized_data, matched_fields, total_fields, missing_required):
        errors = [f"required_missing:{name}" for name in missing_required]
        return RowValidationResult(
            is_valid=not errors,
            normalized_data=normalized_data,
            errors=errors,
            confidence={
                "schema_match_rate": round(float(matched_fields) / float(total_fields or 1), 4),
                "validation_ok": 0.0 if errors else 1.0,
                "overall": 0.2 if errors else 0.9,
            },
        )

    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.validate_row", _fake_validate_row)
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.JobWriter", _FakeWriter)
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.GoogleSheetsSource.fetch_values", lambda *_args, **_kwargs: rows)


def _req():
    from app.engines.extraction.sheet_ingestion_service import IngestionRequest

    return IngestionRequest(
        tenant_id="tenant-1",
        user_id="user-1",
        template_id="tpl-1",
        sheet_id="sheet-1",
        worksheet="WS",
        schema_path="/tmp/schema.yaml",
        source_document_id="doc-1",
    )


@pytest.mark.asyncio
async def test_header_changed_detected(monkeypatch: pytest.MonkeyPatch, _schema: IngestionSchema):
    rows = [
        ["meta", "meta"],
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", "3"],
    ]
    _patch_common(monkeypatch, rows, _schema)

    service = GoogleSheetIngestionService(db=object())
    summary = await service.ingest(_req())

    assert summary["rows_processed"] == 1
    assert summary["rows_inserted"] == 1
    assert summary["metrics"]["row_status_counts"]["VALID"] == 1


@pytest.mark.asyncio
async def test_missing_required_column_invalid(monkeypatch: pytest.MonkeyPatch, _schema: IngestionSchema):
    rows = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["", "3"],
    ]
    _patch_common(monkeypatch, rows, _schema)

    service = GoogleSheetIngestionService(db=object())
    summary = await service.ingest(_req())

    assert summary["rows_failed"] == 1
    assert summary["metrics"]["row_status_counts"]["INVALID"] == 1
    assert any(item.get("status") == "INVALID" for item in summary["errors"])


@pytest.mark.asyncio
async def test_merged_cells_result_in_partial(monkeypatch: pytest.MonkeyPatch, _schema: IngestionSchema):
    rows = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", ""],
    ]
    _patch_common(monkeypatch, rows, _schema)

    service = GoogleSheetIngestionService(db=object())
    summary = await service.ingest(_req())

    assert summary["rows_inserted"] == 1
    assert summary["metrics"]["row_status_counts"]["PARTIAL"] == 1


@pytest.mark.asyncio
async def test_duplicate_ingestion_safe_rerun(monkeypatch: pytest.MonkeyPatch, _schema: IngestionSchema):
    rows = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", "3"],
    ]
    _patch_common(monkeypatch, rows, _schema)

    service = GoogleSheetIngestionService(db=object())
    first = await service.ingest(_req())
    second = await service.ingest(_req())

    assert first["rows_inserted"] == 1
    assert second["rows_inserted"] == 0
    assert second["rows_skipped_idempotent"] == 1
    assert second["metrics"]["row_status_counts"]["DUPLICATE"] == 1


@pytest.mark.asyncio
async def test_partial_row_status(monkeypatch: pytest.MonkeyPatch, _schema: IngestionSchema):
    rows = [
        ["Ngày báo cáo", "Cột không map"],
        ["20/04/2026", "abc"],
    ]
    _patch_common(monkeypatch, rows, _schema)

    service = GoogleSheetIngestionService(db=object())
    summary = await service.ingest(_req())

    assert summary["rows_inserted"] == 1
    assert summary["metrics"]["row_status_counts"]["PARTIAL"] == 1


@pytest.mark.asyncio
async def test_empty_sheet(monkeypatch: pytest.MonkeyPatch, _schema: IngestionSchema):
    _patch_common(monkeypatch, [], _schema)

    service = GoogleSheetIngestionService(db=object())
    summary = await service.ingest(_req())

    assert summary["rows_processed"] == 0
    assert summary["rows_failed"] == 0
    assert summary["rows_inserted"] == 0


# ────────────────────────────────────────────────────────────
# Multi-worksheet ingestion tests
# ────────────────────────────────────────────────────────────

@pytest.fixture
def _multi_schema() -> IngestionSchema:
    """Schema used for both worksheets in multi-worksheet tests."""
    return IngestionSchema(
        fields=[
            FieldSchema(
                name="ngay_bao_cao",
                aliases=["Ngày báo cáo", "ngay_bao_cao"],
                field_type="string",
                required=True,
                default=None,
                transform=None,
            ),
            FieldSchema(
                name="tong_so_vu",
                aliases=["Tổng số vụ", "tong_so_vu"],
                field_type="integer",
                required=False,
                default=0,
                transform=None,
            ),
        ]
    )


def _patch_multi_worksheet(monkeypatch: pytest.MonkeyPatch, rows_by_worksheet: dict[str, list[list[str]]], schema: IngestionSchema):
    """Patch fetch_values to return different rows based on worksheet name."""
    def _fake_fetch(config):
        ws = config.worksheet
        return rows_by_worksheet.get(ws, [])
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.load_schema", lambda *_: schema)
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.build_validation_model", lambda *_: _DummyModel())
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.validate_row", lambda **kw: RowValidationResult(
        is_valid=True,
        normalized_data=kw["normalized_data"],
        errors=[],
        confidence={"schema_match_rate": 1.0, "validation_ok": 1.0, "overall": 0.9},
    ))
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.JobWriter", _FakeWriter)
    monkeypatch.setattr("app.engines.extraction.sheet_ingestion_service.GoogleSheetsSource.fetch_values", _fake_fetch)


@pytest.mark.asyncio
async def test_multi_worksheet_ingestion(monkeypatch: pytest.MonkeyPatch, _multi_schema: IngestionSchema):
    """Test that multiple worksheets are ingested sequentially and results aggregated."""
    rows_bc = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", "5"],
    ]
    rows_cnch = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", "3"],
    ]
    rows_by_ws = {"BC NGÀY": rows_bc, "CNCH": rows_cnch}
    _patch_multi_worksheet(monkeypatch, rows_by_ws, _multi_schema)

    service = GoogleSheetIngestionService(db=object())
    req = IngestionRequest(
        tenant_id="tenant-1",
        user_id="user-1",
        template_id="tpl-1",
        sheet_id="sheet-1",
        worksheet="",  # not used in multi-mode
        schema_path="/tmp/schema.yaml",
        configs=[
            {"worksheet": "BC NGÀY", "schema_path": "/tmp/schema.yaml", "range": "A1:ZZZ"},
            {"worksheet": "CNCH", "schema_path": "/tmp/schema.yaml", "range": "A1:ZZZ"},
        ],
    )
    summary = await service.ingest(req)

    assert summary["rows_processed"] == 2
    assert summary["rows_inserted"] == 2
    assert summary["rows_failed"] == 0
    assert summary["worksheet"] == "multiple: BC NGÀY, CNCH"
    # Weighted schema_match_rate should be 1.0 (both worksheets had perfect match)
    assert summary["schema_match_rate"] == 1.0


@pytest.mark.asyncio
async def test_auto_convert_legacy_template(monkeypatch: pytest.MonkeyPatch, _schema: IngestionSchema):
    """Test that single-field config (legacy) still works when configs is None."""
    rows = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", "3"],
    ]
    _patch_common(monkeypatch, rows, _schema)

    service = GoogleSheetIngestionService(db=object())
    req = IngestionRequest(
        tenant_id="tenant-1",
        user_id="user-1",
        template_id="tpl-1",
        sheet_id="sheet-1",
        worksheet="WS1",  # legacy single worksheet
        schema_path="/tmp/schema.yaml",
    )
    summary = await service.ingest(req)

    assert summary["rows_processed"] == 1
    assert summary["rows_inserted"] == 1
    assert summary["worksheet"] == "WS1"


@pytest.mark.asyncio
async def test_multi_worksheet_idempotency_across_different_worksheets(monkeypatch: pytest.MonkeyPatch, _multi_schema: IngestionSchema):
    """Test that same data in different worksheets produces distinct row_hashes (different worksheet context)."""
    rows = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", "5"],
    ]
    # Same rows for both worksheets
    rows_by_ws = {"WS1": rows, "WS2": rows}
    _patch_multi_worksheet(monkeypatch, rows_by_ws, _multi_schema)

    service = GoogleSheetIngestionService(db=object())
    req = IngestionRequest(
        tenant_id="tenant-1",
        user_id="user-1",
        template_id="tpl-1",
        sheet_id="sheet-1",
        worksheet="",
        schema_path="/tmp/schema.yaml",
        configs=[
            {"worksheet": "WS1", "schema_path": "/tmp/schema.yaml", "range": "A1:ZZZ"},
            {"worksheet": "WS2", "schema_path": "/tmp/schema.yaml", "range": "A1:ZZZ"},
        ],
    )
    summary = await service.ingest(req)

    # Both rows should be inserted because they have different worksheet in source_references
    assert summary["rows_inserted"] == 2
    assert summary["rows_skipped_idempotent"] == 0


@pytest.mark.asyncio
async def test_invalid_config_missing_worksheet_or_schema(monkeypatch: pytest.MonkeyPatch, _multi_schema: IngestionSchema):
    """Test that configs missing required fields are skipped."""
    rows = [
        ["Ngày báo cáo", "Tổng số vụ"],
        ["20/04/2026", "1"],
    ]
    rows_by_ws = {"VALID": rows}
    _patch_multi_worksheet(monkeypatch, rows_by_ws, _multi_schema)

    service = GoogleSheetIngestionService(db=object())
    req = IngestionRequest(
        tenant_id="tenant-1",
        user_id="user-1",
        template_id="tpl-1",
        sheet_id="sheet-1",
        worksheet="",
        schema_path="",
        configs=[
            {"worksheet": "", "schema_path": "/tmp/schema.yaml", "range": "A1:ZZZ"},  # missing worksheet
            {"worksheet": "VALID", "schema_path": "/tmp/schema.yaml", "range": "A1:ZZZ"},
            {"worksheet": "MISSING_SCHEMA", "schema_path": "", "range": "A1:ZZZ"},  # missing schema_path
        ],
    )
    summary = await service.ingest(req)

    # Only VALID worksheet should be processed
    assert summary["rows_processed"] == 1
    assert summary["rows_inserted"] == 1
    assert summary["worksheet"] == "multiple: VALID"

