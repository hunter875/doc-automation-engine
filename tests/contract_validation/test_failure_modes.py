from __future__ import annotations

from app.domain.rules.engine import run_business_rules
from app.domain.rules.extractors import extract_incidents_from_stat_table
from app.domain.rules.validation_rules import validate_business
from app.engines.extraction.schemas import CNCHItem



def test_failure_mode_regex_extraction_failure_returns_errors(contract_template) -> None:
    sections = {"header": [], "I.": [], "II.": []}
    tables = []

    out = run_business_rules(sections, tables, llm_output=None, full_text="", tpl=contract_template)
    assert out["errors"]
    assert out["confidence"] < 1.0



def test_failure_mode_incomplete_llm_output_still_errors(contract_template) -> None:
    sections = {"header": [], "I.": [], "II.": []}
    tables = []
    llm_output = {"so_bao_cao": "", "ngay_bao_cao": "", "don_vi": ""}

    out = run_business_rules(sections, tables, llm_output=llm_output, full_text="", tpl=contract_template)
    assert out["errors"]



def test_failure_mode_numeric_conversion_error_is_controlled(contract_template) -> None:
    tables = [{"page": 1, "rows": [["14", "Tong so vu tai nan su co", "abc"]]}]

    incidents = extract_incidents_from_stat_table(tables, tpl=contract_template)
    assert incidents == []



def test_failure_mode_invalid_time_field_raises_explicit_validation() -> None:
    try:
        CNCHItem(thoi_gian="99-99-9999")
        raised = False
    except Exception:
        raised = True

    assert raised



def test_failure_mode_missing_required_fields_flagged(contract_template) -> None:
    errors = validate_business({"so_bao_cao": "201/BC-KV30"}, tpl=contract_template)
    assert "missing_ngay" in errors
    assert "missing_don_vi" in errors
