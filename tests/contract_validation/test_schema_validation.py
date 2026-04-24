from __future__ import annotations

from app.engines.extraction.schemas import BlockExtractionOutput

from tests.contract_validation.fixtures.payload_factory import clone_payload, remove_path
from tests.contract_validation.validators.schema_contract import validate_schema_contract



def test_schema_required_fields_exist(sample_payload: dict) -> None:
    errors = validate_schema_contract(sample_payload)
    assert not [e for e in errors if e.startswith("missing_")], errors



def test_schema_types_and_nested_structure(sample_payload: dict) -> None:
    parsed = BlockExtractionOutput.model_validate(sample_payload)
    assert parsed.header.so_bao_cao
    assert isinstance(parsed.bang_thong_ke, list)
    assert isinstance(parsed.danh_sach_cnch, list)
    assert isinstance(parsed.danh_sach_cong_tac_khac, list)
    assert isinstance(parsed.danh_sach_phuong_tien_hu_hong, list)



def test_schema_optional_empty_arrays_allowed(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["danh_sach_cong_van_tham_muu"] = []
    payload["danh_sach_cong_tac_khac"] = []

    errors = validate_schema_contract(payload)
    assert not [e for e in errors if e.startswith("invalid_")], errors



def test_schema_missing_nested_field_is_reported(sample_payload: dict) -> None:
    payload = remove_path(sample_payload, "header", "ngay_bao_cao")
    errors = validate_schema_contract(payload)
    assert "missing_header:ngay_bao_cao" in errors



def test_schema_invalid_collection_type_is_reported(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["bang_thong_ke"] = {"stt": "2"}

    errors = validate_schema_contract(payload)
    assert "invalid_bang_thong_ke_type" in errors
