from __future__ import annotations

import io
import zipfile

import pytest

from app.services import word_export


def _build_minimal_docx(document_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("[Content_Types].xml", "<Types></Types>")
        zout.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _read_docx_entry(docx_bytes: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        return zin.read(name).decode("utf-8")


def test_fix_jinja_tags_rebuilds_split_word_runs() -> None:
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body><w:p>"
        "<w:r><w:t>{%</w:t></w:r>"
        "<w:r><w:t>p if tong_so_vu_chay &gt; 0</w:t></w:r>"
        "<w:r><w:t>%}</w:t></w:r>"
        "</w:p></w:body></w:document>"
    )
    docx_bytes = _build_minimal_docx(xml)

    fixed = word_export._fix_jinja_tags_in_docx(docx_bytes)
    document_xml = _read_docx_entry(fixed, "word/document.xml")

    assert "{% if tong_so_vu_chay" in document_xml
    assert "%}" in document_xml
    assert "{%p" not in document_xml


def test_fix_jinja_tags_rejects_oversized_zip_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>"
    )
    docx_bytes = _build_minimal_docx(xml)

    monkeypatch.setattr(word_export, "MAX_DOCX_MEMBER_UNCOMPRESSED_BYTES", 16)

    with pytest.raises(ValueError, match="zip entry exceeds maximum allowed uncompressed size"):
        word_export._fix_jinja_tags_in_docx(docx_bytes)


def test_render_aggregation_to_word_keeps_all_records(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def _fake_render(template_bytes: bytes, context_data: dict) -> bytes:  # noqa: ARG001
        captured.update(context_data)
        return b"ok"

    monkeypatch.setattr(word_export, "render_word_template", _fake_render)

    context_payload = {
        "records": [
            {"group": "A", "tong_so_vu_chay": 2},
            {"group": "B", "tong_so_vu_chay": 3},
        ],
        "tong_so_vu_chay": 5,
        "record": {"group": "A", "tong_so_vu_chay": 2},
        "record_index": 0,
    }

    result = word_export.render_aggregation_to_word(
        template_bytes=b"dummy",
        aggregated_data=context_payload,
    )

    assert result == b"ok"
    assert "records" in captured
    assert isinstance(captured["records"], list)
    assert len(captured["records"]) == 2
    assert captured["records"][0]["group"] == "A"
    assert captured["records"][1]["group"] == "B"
    assert captured["tong_so_vu_chay"] == 5


def test_render_word_template_rejects_oversized_template(monkeypatch):
    monkeypatch.setattr("app.utils.word_export.MAX_TEMPLATE_INPUT_BYTES", 8)

    with pytest.raises(ValueError, match="file size exceeds"):
        word_export.render_word_template(b"0123456789", {})
