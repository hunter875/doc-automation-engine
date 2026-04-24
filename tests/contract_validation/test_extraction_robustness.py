from __future__ import annotations

from app.domain.rules.engine import run_business_rules
from app.domain.rules.extractors import extract_metadata_from_header
from app.domain.rules.validation_rules import validate_business

from tests.contract_validation.fixtures.payload_factory import with_ocr_noise



def test_robustness_extra_whitespace_header_parse(contract_template) -> None:
    header_text = "Số :   201/BC-KV30\n\nThành phố Hồ Chí Minh, ngày 01 / 04 / 2026\nĐỘI CC&CNCH KHU VỰC 30"
    meta = extract_metadata_from_header(header_text, tpl=contract_template)

    assert meta.get("so_bao_cao") == "201/BC-KV30"
    assert meta.get("ngay_bao_cao") == "01/04/2026"



def test_robustness_reordered_sections_still_returns_controlled_state(contract_template) -> None:
    sections = {
        "II.": ["Kết quả công tác..."],
        "header": ["Số: 201/BC-KV30", "ngày 01/04/2026", "ĐỘI CC&CNCH KHU VỰC 30"],
        "I.": ["Tình hình cháy: Không"],
    }
    tables = []

    out = run_business_rules(sections, tables, llm_output=None, full_text="\n".join(sum(sections.values(), [])), tpl=contract_template)

    assert isinstance(out, dict)
    assert "data" in out
    assert "errors" in out



def test_robustness_ocr_noise_returns_explicit_errors(contract_template) -> None:
    noisy_header = with_ocr_noise("Số: 201/BC-KV30\nngày 01/04/2026\nĐỘI CC&CNCH KHU VỰC 30")
    data = extract_metadata_from_header(noisy_header, tpl=contract_template)

    errors = validate_business(data, tpl=contract_template)
    assert errors, "Noisy extraction must not silently pass with empty critical fields"



def test_robustness_partial_text_loss_is_not_silent(contract_template) -> None:
    sections = {"header": ["Số:"], "I.": [""], "II.": [""]}
    tables = []

    out = run_business_rules(sections, tables, llm_output=None, full_text="Số:", tpl=contract_template)
    assert out["errors"], "Partial-loss input must surface explicit validation errors"



def test_robustness_duplicate_entries_trigger_violation(payload_factory) -> None:
    payload = payload_factory()
    payload["danh_sach_cnch"].append(payload["danh_sach_cnch"][0].copy())

    from tests.contract_validation.validators.invariants import validate_invariants

    violations = validate_invariants(payload)
    assert any(v.startswith("duplicate_incident_signature:") for v in violations)
