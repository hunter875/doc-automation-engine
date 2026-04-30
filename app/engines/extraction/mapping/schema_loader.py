"""YAML schema loader for deterministic Sheets ingestion."""

from __future__ import annotations

import unicodedata
import re
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
    section: str | None = None  # top-level section in BlockExtractionOutput


@dataclass(frozen=True)
class IngestionSchema:
    fields: list[FieldSchema]

    @property
    def all_aliases(self) -> set[str]:
        output: set[str] = set()
        for field in self.fields:
            # Field name: normalize underscores to spaces and remove diacritics
            # so that worksheet column headers like "STT" and "Ngày xảy ra sự cố"
            # can be matched against field names like "stt" and "ngay_xay_ra"
            output.add(_normalize_aliases([field.name], field.name)[0])
            output.update(field.aliases)
        return output


ALLOWED_TYPES = {"string", "integer", "float", "boolean", "date", "object", "array"}


def _normalize_aliases(raw: Any, fallback: str) -> list[str]:
    if not isinstance(raw, list):
        return [fallback]

    def _norm(text: str) -> str:
        t = unicodedata.normalize("NFC", str(text or "")).strip()
        nfkd = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in nfkd if not unicodedata.combining(c))
        t = t.lower()
        return re.sub(r"\s+", " ", t)

    # Normalize to NFC, deduplicate, preserve order
    normalized = [_norm(str(item)) for item in raw if str(item).strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for a in normalized:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique if unique else [_norm(fallback)]


def _infer_field_type(field_name: str) -> str:
    name = str(field_name).strip().lower()
    integer_prefixes = (
        "tong_",
        "so_",
        "stt",
        "cai_",
        "kiem_tra_",
        "phat_",
    )
    if name.startswith(integer_prefixes):
        return "integer"
    return "string"


def _collect_sheet_mapping_fields(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping = raw.get("sheet_mapping")
    if not isinstance(mapping, dict):
        return {}

    collected: dict[str, dict[str, Any]] = {}

    def _upsert(field_name: str, aliases: list[str]) -> None:
        normalized_name = str(field_name).strip()
        if not normalized_name:
            return
        if normalized_name not in collected:
            collected[normalized_name] = {
                "type": _infer_field_type(normalized_name),
                "aliases": aliases or [normalized_name],
                "required": False,
            }
            return
        existing_aliases = set(collected[normalized_name].get("aliases", []))
        merged = list(existing_aliases.union(set(aliases or [])))
        collected[normalized_name]["aliases"] = merged or [normalized_name]

    for section_data in mapping.values():
        if not isinstance(section_data, dict):
            continue

        for key, value in section_data.items():
            if key == "stt_map":
                continue

            if key == "fields" and isinstance(value, dict):
                for sub_field_name, sub_aliases in value.items():
                    aliases = _normalize_aliases(sub_aliases, str(sub_field_name).strip())
                    _upsert(str(sub_field_name).strip(), aliases)
                continue

            if isinstance(value, dict):
                aliases = value.get("aliases")
                if isinstance(aliases, list):
                    normalized_aliases = _normalize_aliases(aliases, str(key).strip())
                    _upsert(str(key).strip(), normalized_aliases)

    return collected


def load_schema(schema_path: str) -> IngestionSchema:
    path = Path(schema_path).expanduser().resolve()
    if not path.is_file():
        raise ProcessingError(message=f"Schema YAML not found: {path}")

    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    field_block = raw.get("fields")
    if not isinstance(field_block, dict) or not field_block:
        field_block = _collect_sheet_mapping_fields(raw)
    if not isinstance(field_block, dict) or not field_block:
        raise ProcessingError(message="Schema YAML must contain non-empty 'fields' object or valid 'sheet_mapping' object")

    fields: list[FieldSchema] = []
    for field_name, spec in field_block.items():
        if not isinstance(spec, dict):
            raise ProcessingError(message=f"Invalid schema for field '{field_name}'")

        # Prefer explicit type from YAML spec; fall back to inference only when absent
        if "type" in spec:
            field_type = str(spec["type"]).strip().lower()
        else:
            field_type = _infer_field_type(str(field_name).strip())
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
                section=str(spec.get("section", "")) or None,
            )
        )

    return IngestionSchema(fields=fields)
