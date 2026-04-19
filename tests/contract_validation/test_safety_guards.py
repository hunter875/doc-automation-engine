from __future__ import annotations

from tests.contract_validation.fixtures.payload_factory import clone_payload, remove_path
from tests.contract_validation.validators.safety import validate_safety



def test_safety_no_hallucinated_placeholder_values(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["header"]["so_bao_cao"] = "unknown"

    violations = validate_safety(payload)
    assert "hallucination_placeholder:so_bao_cao" in violations



def test_safety_totals_without_evidence_are_flagged(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_cong_van"] = 2
    payload["danh_sach_cong_van_tham_muu"] = []

    violations = validate_safety(payload)
    assert "hallucination_total_without_evidence:tong_cong_van" in violations



def test_safety_missing_data_is_flagged_not_fabricated(sample_payload: dict) -> None:
    payload = remove_path(sample_payload, "header", "ngay_bao_cao")

    violations = validate_safety(payload)
    assert "missing_required_field:header.ngay_bao_cao" in violations



def test_safety_document_item_requires_valid_code(sample_payload: dict) -> None:
    payload = clone_payload(sample_payload)
    payload["danh_sach_cong_van_tham_muu"] = [{"so_ky_hieu": "", "noi_dung": "Noi dung"}]

    violations = validate_safety(payload)
    assert "invalid_document_item_missing_code:1" in violations
