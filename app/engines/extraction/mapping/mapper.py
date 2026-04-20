"""Row-to-schema deterministic mapper."""

from __future__ import annotations

from typing import Any

from app.engines.extraction.mapping.normalizer import normalize_field_value, normalize_unicode_text
from app.engines.extraction.mapping.schema_loader import IngestionSchema


def _normalize_key(key: str) -> str:
    return normalize_unicode_text(key).lower()


def map_row_to_document_data(
    row: dict[str, Any],
    schema: IngestionSchema,
) -> tuple[dict[str, Any], int, int, list[str]]:
    """Map sheet row dict to normalized document data using aliases."""
    normalized_row = {_normalize_key(k): v for k, v in row.items()}

    output: dict[str, Any] = {}
    matched_fields = 0
    missing_required: list[str] = []

    for field in schema.fields:
        value = None
        found = False
        for alias in field.aliases:
            lookup = _normalize_key(alias)
            if lookup in normalized_row:
                value = normalized_row[lookup]
                found = True
                break

        normalized_value = normalize_field_value(value, field)
        if found:
            matched_fields += 1
        if field.required and normalized_value is None:
            missing_required.append(field.name)

        output[field.name] = normalized_value

    return output, matched_fields, len(schema.fields), missing_required
