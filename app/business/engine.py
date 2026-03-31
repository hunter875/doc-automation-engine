"""Business rule engine — orchestrates extractors, validators, normalizers with LLM fallback."""

from __future__ import annotations

from typing import Any

from app.business.extractors import (
    extract_metadata_from_header,
    extract_summary_from_sections,
    extract_incidents_from_narrative,
    extract_incidents_from_stat_table,
    extract_incidents_from_tables,
    build_document_graph,
)
from app.business.validators import validate_business
from app.business.normalizers import normalize_business
from app.business.template_loader import DocumentTemplate


def run_business_rules(
    sections: dict[str, list[str]],
    tables: list[dict[str, Any]],
    llm_output: dict[str, Any] | None = None,
    full_text: str = "",
    tpl: DocumentTemplate | None = None,
) -> dict[str, Any]:
    """Run the full business rule chain: extract → validate → LLM fallback → normalize.

    Args:
        sections: section name → list of text lines (from segment_sections).
        tables: list of {"page": int, "rows": list} dicts.
        llm_output: optional LLM-extracted metadata used as fallback when rules miss fields.
        full_text: full reconstructed document text used as fallback for date/metadata search.

    Returns:
        {"data": {...}, "errors": [...], "confidence": float, "graph": {...}}
    """

    business: dict[str, Any] = {}

    # 1. Regex-based metadata extraction from header section
    header_text = "\n".join(sections.get("header", []))
    business.update(extract_metadata_from_header(header_text, tpl=tpl))

    # 1b. Fallback: search the full document text for metadata the header section missed
    #     (right-column lines land after the section-I anchor in the linearised stream
    #     so they are not included in sections["header"])
    if full_text:
        fallback_meta = extract_metadata_from_header(full_text, tpl=tpl)
        for key, value in fallback_meta.items():
            if not business.get(key) and value:
                business[key] = value

    # 2. Summary extraction from narrative sections
    business.update(extract_summary_from_sections(sections, tpl=tpl))

    # 3. Incident extraction — structured tables, stat-table CNCH rows, narrative text
    incidents: list[Any] = []
    incidents.extend(extract_incidents_from_tables(tables, tpl=tpl))        # structured incident table (Địa điểm/Nguyên nhân cols)
    incidents.extend(extract_incidents_from_stat_table(tables, tpl=tpl))    # statistical table CNCH/tai-nan rows with ket_qua > 0
    incidents.extend(extract_incidents_from_narrative(sections, tpl=tpl))   # narrative time+location patterns
    business["incidents"] = incidents

    # 4. First validation pass
    errors = validate_business(business, tpl=tpl)

    # 5. LLM fallback — merge LLM output for missing fields
    if errors and isinstance(llm_output, dict):
        for key, value in llm_output.items():
            if key != "raw" and not business.get(key) and value:
                business[key] = value
        errors = validate_business(business, tpl=tpl)

    # 6. Normalize
    business = normalize_business(business)

    # 7. Document graph
    graph = build_document_graph(sections, tables)

    return {
        "data": business,
        "errors": errors,
        "confidence": 1.0 if not errors else 0.6,
        "graph": graph,
    }
