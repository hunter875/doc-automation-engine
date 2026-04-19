from __future__ import annotations

from tests.contract_validation.validators.invariants import validate_invariants
from tests.contract_validation.validators.safety import validate_safety
from tests.contract_validation.validators.schema_contract import validate_schema_contract



def test_sample_payload_must_have_zero_contract_violations(sample_payload: dict) -> None:
    schema_errors = validate_schema_contract(sample_payload)
    invariant_errors = validate_invariants(sample_payload)
    safety_errors = validate_safety(sample_payload)

    all_errors = schema_errors + invariant_errors + safety_errors

    assert not all_errors, "Contract violations found:\n- " + "\n- ".join(all_errors)
