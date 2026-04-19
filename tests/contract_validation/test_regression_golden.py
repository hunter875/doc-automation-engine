from __future__ import annotations

import json
from pathlib import Path

from tests.contract_validation.validators.schema_contract import build_contract_snapshot



def test_regression_golden_snapshot(project_root: Path, sample_payload: dict) -> None:
    expected_path = project_root / "tests" / "contract_validation" / "golden" / "jsonoutput_canonical.expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    actual = build_contract_snapshot(sample_payload)
    assert actual == expected



def test_regression_sample_has_no_known_violations(sample_payload: dict) -> None:
    from tests.contract_validation.validators.invariants import validate_invariants

    violations = sorted(validate_invariants(sample_payload))

    unexpected = {
        "formula_mismatch:stt55!=sum(stt56..stt61)",
        "missing_stt:60",
        "text_hygiene:cong_tac_an_ninh_has_prefix",
    }
    assert not unexpected.intersection(set(violations))
