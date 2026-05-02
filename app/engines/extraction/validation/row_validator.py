"""Dynamic Pydantic validation generated from YAML schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError, create_model

from app.engines.extraction.mapping.schema_loader import IngestionSchema


@dataclass
class RowValidationResult:
    is_valid: bool
    normalized_data: dict[str, Any]
    errors: list[str]
    confidence: dict[str, float]


def _python_type(field_type: str):
    return {
        "string": str,
        "integer": int,
        "float": float,
        "boolean": bool,
        "date": str,
        "object": dict,
        "array": list,
    }.get(field_type, Any)


def build_validation_model(schema: IngestionSchema) -> type[BaseModel]:
    fields: dict[str, tuple[Any, Any]] = {}
    for f in schema.fields:
        py_type = _python_type(f.field_type)
        if f.required and f.default is None:
            fields[f.name] = (py_type, ...)
        else:
            fields[f.name] = (py_type | None, f.default)
    return create_model("SheetIngestionModel", **fields)  # type: ignore[arg-type]


def validate_row(
    *,
    model: type[BaseModel],
    normalized_data: dict[str, Any],
    matched_fields: int,
    total_fields: int,
    missing_required: list[str],
) -> RowValidationResult:
    errors: list[str] = []
    coerced_data = dict(normalized_data)

    try:
        validated = model.model_validate(normalized_data)
        coerced_data = validated.model_dump()
    except ValidationError as exc:
        for item in exc.errors():
            loc = ".".join(str(v) for v in item.get("loc", []))
            errors.append(f"{loc}: {item.get('msg', 'validation error')}")

    for req in missing_required:
        errors.append(f"required_missing:{req}")

    schema_match_rate = float(matched_fields) / float(total_fields or 1)

    if schema_match_rate < 0.1:
        errors.append(f"low_match_rate:{schema_match_rate:.2f}")

    validation_ok = 0.0 if errors else 1.0
    confidence_overall = round((schema_match_rate * 0.6) + (validation_ok * 0.4), 4)

    return RowValidationResult(
        is_valid=not errors,
        normalized_data=coerced_data,
        errors=errors,
        confidence={
            "schema_match_rate": round(schema_match_rate, 4),
            "validation_ok": validation_ok,
            "overall": confidence_overall,
        },
    )
