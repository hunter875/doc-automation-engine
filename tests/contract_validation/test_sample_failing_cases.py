from __future__ import annotations

from tests.contract_validation.fixtures.payload_factory import clone_payload
from tests.contract_validation.validators.invariants import validate_invariants
from tests.contract_validation.validators.schema_contract import validate_schema_contract
from tests.contract_validation.validators.safety import validate_safety



def test_sample_failing_case_schema_break(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["header"] = "broken"

    errors = validate_schema_contract(payload)
    assert "invalid_header_type" in errors



def test_sample_failing_case_business_break(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["bang_thong_ke"] = [
        {"stt": "15", "ket_qua": 2, "noi_dung": "x"},
        {"stt": "16", "ket_qua": 1, "noi_dung": "x"},
        {"stt": "17", "ket_qua": 3, "noi_dung": "x"},
    ]

    violations = validate_invariants(payload)
    assert "formula_mismatch:stt15!=stt16+stt17" in violations



def test_sample_failing_case_safety_break(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_cnch"] = 2
    payload["danh_sach_cnch"] = []
    payload["phan_I_va_II_chi_tiet_nghiep_vu"]["chi_tiet_cnch"] = "Khong"

    violations = validate_safety(payload)
    assert "hallucination_total_without_evidence:tong_so_vu_cnch" in violations
