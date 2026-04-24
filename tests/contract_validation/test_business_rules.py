from __future__ import annotations

from tests.contract_validation.fixtures.payload_factory import clone_payload
from tests.contract_validation.validators.invariants import validate_invariants



def test_invariants_detect_formula_violation_when_stt60_missing(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["bang_thong_ke"] = [row for row in payload.get("bang_thong_ke", []) if str(row.get("stt", "")).strip() != "60"]

    violations = validate_invariants(payload)
    assert "formula_mismatch:stt55!=sum(stt56..stt61)" in violations



def test_invariants_detect_text_hygiene_prefix(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["phan_I_va_II_chi_tiet_nghiep_vu"]["cong_tac_an_ninh"] = "CCC: Không"

    violations = validate_invariants(payload)
    assert "text_hygiene:cong_tac_an_ninh_has_prefix" in violations



def test_invariants_pass_after_manual_repair(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)

    # Repair known sample defects for deterministic pass expectation.
    payload["phan_I_va_II_chi_tiet_nghiep_vu"]["cong_tac_an_ninh"] = "Khong"
    payload["bang_thong_ke"].append({"stt": "60", "ket_qua": 4, "noi_dung": "Lai xe"})

    violations = validate_invariants(payload)
    assert "formula_mismatch:stt55!=sum(stt56..stt61)" not in violations
    assert "text_hygiene:cong_tac_an_ninh_has_prefix" not in violations



def test_invariants_detect_document_total_mismatch(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_cong_van"] = 3

    violations = validate_invariants(payload)
    assert "count_mismatch:tong_cong_van" in violations
