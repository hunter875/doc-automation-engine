from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.engines.extraction.mapping.schema_loader import FieldSchema, IngestionSchema
from app.engines.extraction.sheet_ingestion_service import GoogleSheetIngestionService
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
