"""YAML schema loader for deterministic Sheets ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.exceptions import ProcessingError


@dataclass(frozen=True)
class FieldSchema:
    name: str
    aliases: list[str]
    field_type: str
    required: bool
    default: Any
    transform: str | None


@dataclass(frozen=True)
class IngestionSchema:
    fields: list[FieldSchema]

    @property
    def all_aliases(self) -> set[str]:
        output: set[str] = set()
        for field in self.fields:
            output.update(field.aliases)
        return output


ALLOWED_TYPES = {"string", "integer", "float", "boolean", "date", "object", "array"}


def _normalize_aliases(raw: Any, fallback: str) -> list[str]:
    if not isinstance(raw, list):
        return [fallback]
    aliases = [str(item).strip() for item in raw if str(item).strip()]
    return aliases or [fallback]


def load_schema(schema_path: str) -> IngestionSchema:
    path = Path(schema_path).expanduser().resolve()
    if not path.is_file():
        raise ProcessingError(message=f"Schema YAML not found: {path}")

    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    field_block = raw.get("fields")
    if not isinstance(field_block, dict) or not field_block:
        raise ProcessingError(message="Schema YAML must contain non-empty 'fields' object")

    fields: list[FieldSchema] = []
    for field_name, spec in field_block.items():
        if not isinstance(spec, dict):
            raise ProcessingError(message=f"Invalid schema for field '{field_name}'")

        field_type = str(spec.get("type", "string")).strip().lower()
        if field_type not in ALLOWED_TYPES:
            raise ProcessingError(message=f"Unsupported type '{field_type}' for field '{field_name}'")

        fields.append(
            FieldSchema(
                name=str(field_name).strip(),
                aliases=_normalize_aliases(spec.get("aliases"), str(field_name).strip()),
                field_type=field_type,
                required=bool(spec.get("required", False)),
                default=spec.get("default", None),
                transform=str(spec.get("transformation", "")).strip() or None,
            )
        )

    return IngestionSchema(fields=fields)
