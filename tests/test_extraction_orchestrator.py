from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ProcessingError
from app.engines.extraction.schemas import BlockExtractionOutput, PipelineResult
from app.engines.extraction.orchestrator import ExtractionOrchestrator


class _FakePipeline:
    def __init__(self, result: PipelineResult):
        self.result = result
        self.calls: list[tuple[bytes, str]] = []

    def run_stage1_from_bytes(self, pdf_bytes: bytes, filename: str) -> PipelineResult:
        self.calls.append((pdf_bytes, filename))
        return self.result


def _build_db_with_document(document: object | None) -> MagicMock:
    db = MagicMock()
    query = db.query.return_value
    filtered = query.filter.return_value
    filtered.first.return_value = document
    return db


def test_orchestrator_run_success(monkeypatch: pytest.MonkeyPatch) -> None:
    job = SimpleNamespace(id="job-1", document_id="doc-1")
    saved_job = SimpleNamespace(id="job-1", status="extracted")

    manager = MagicMock()
    manager.get_job_for_processing.return_value = job
    manager.persist_stage1_result.return_value = saved_job

    document = SimpleNamespace(id="doc-1", s3_key="docs/abc.pdf", file_name="abc.pdf")
    db = _build_db_with_document(document)

    monkeypatch.setattr(
        "app.engines.extraction.orchestrator.s3_client",
        SimpleNamespace(get_object=lambda **_: {"Body": SimpleNamespace(read=lambda: b"pdf-bytes")}),
    )

    pipeline = _FakePipeline(PipelineResult(status="ok", attempts=1, output=None))

    orchestrator = ExtractionOrchestrator(
        db,
        job_manager=manager,
        pipeline_factory=lambda: pipeline,
    )

    result = orchestrator.run("job-1")

    assert result is saved_job
    manager.get_job_for_processing.assert_called_once_with("job-1")
    manager.set_processing.assert_called_once_with(job, parser_used="pdfplumber")
    manager.persist_stage1_result.assert_called_once()
    assert pipeline.calls == [(b"pdf-bytes", "abc.pdf")]


def test_orchestrator_run_document_not_found_marks_failed() -> None:
    job = SimpleNamespace(id="job-2", document_id="missing-doc")
    manager = MagicMock()
    manager.get_job_for_processing.return_value = job

    db = _build_db_with_document(None)
    orchestrator = ExtractionOrchestrator(db, job_manager=manager, pipeline_factory=lambda: MagicMock())

    with pytest.raises(ProcessingError, match="Document not found"):
        orchestrator.run("job-2")

    manager.set_processing.assert_called_once_with(job, parser_used="pdfplumber")
    manager.mark_failed_exception.assert_called_once()


def test_orchestrator_run_pipeline_error_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    job = SimpleNamespace(id="job-3", document_id="doc-3")
    manager = MagicMock()
    manager.get_job_for_processing.return_value = job

    document = SimpleNamespace(id="doc-3", s3_key="docs/fail.pdf", file_name="fail.pdf")
    db = _build_db_with_document(document)

    monkeypatch.setattr(
        "app.engines.extraction.orchestrator.s3_client",
        SimpleNamespace(get_object=lambda **_: {"Body": SimpleNamespace(read=lambda: b"bad-pdf")}),
    )

    class _FailingPipeline:
        def run_stage1_from_bytes(self, pdf_bytes: bytes, filename: str) -> PipelineResult:  # noqa: ARG002
            raise RuntimeError("pipeline failed")

    orchestrator = ExtractionOrchestrator(
        db,
        job_manager=manager,
        pipeline_factory=lambda: _FailingPipeline(),
    )

    with pytest.raises(RuntimeError, match="pipeline failed"):
        orchestrator.run("job-3")

    manager.set_processing.assert_called_once_with(job, parser_used="pdfplumber")
    manager.mark_failed_exception.assert_called_once()
