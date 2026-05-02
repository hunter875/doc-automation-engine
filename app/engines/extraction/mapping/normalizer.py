"""Deterministic value normalization utilities."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from app.engines.extraction.mapping.schema_loader import FieldSchema


def normalize_unicode_text(value: Any) -> str:
    """Normalize text: NFC, remove diacritics, collapse spaces."""
    t = unicodedata.normalize("NFC", str(value or "")).strip()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).lower()


def normalize_header_key(value: str) -> str:
    """Normalize a sheet column header key: strip diacritics, collapse spaces, lowercase.

    This is the SINGLE source of truth for normalizing header keys across the pipeline.
    MUST produce consistent output for both row_dict keys (built via normalize_unicode_text)
    and schema aliases. Uses explicit replacement for Vietnamese letters that NFKD+combining
    strip does not handle (đ/Đ/ơ/Ơ/ư/Ư).
    """
    text = str(value or "").strip()
    # Explicit Vietnamese special-letter → ASCII mapping (covers đ/Đ/ơ/Ơ/ư/Ư)
    _VN_MAP = {
        "đ": "d", "Đ": "D",
        "ơ": "o", "Ơ": "O",
        "ư": "u", "Ư": "U",
    }
    for vn, asc in _VN_MAP.items():
        text = text.replace(vn, asc)
    # Now NFKD + strip remaining combining characters (handles à/â/á/ả/ạ, etc.)
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Collapse underscores/spaces, lowercase
    return re.sub(r"[_\s]+", " ", text).strip().lower()


def parse_date_ddmmyyyy(value: str) -> str | None:
    text = normalize_unicode_text(value)
    if not text:
        return None

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def coerce_int(value: Any) -> int | None:
    text = normalize_unicode_text(value)
    if not text:
        return None
    cleaned = text.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def coerce_float(value: Any) -> float | None:
    text = normalize_unicode_text(value)
    if not text:
        return None
    cleaned = text.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def coerce_bool(value: Any) -> bool | None:
    text = normalize_unicode_text(value).lower()
    if not text:
        return None
    if text in {"true", "1", "yes", "y", "có", "co", "đúng", "dung"}:
        return True
    if text in {"false", "0", "no", "n", "không", "khong", "sai"}:
        return False
    return None


def apply_transform(value: Any, rule: str | None) -> Any:
    if rule is None:
        return value
    if value is None:
        return None

    if rule == "lowercase":
        return normalize_unicode_text(value).lower()
    if rule == "uppercase":
        return normalize_unicode_text(value).upper()
    if rule == "strip_non_digit":
        return re.sub(r"\D+", "", normalize_unicode_text(value))
    return value


def normalize_field_value(raw_value: Any, field: FieldSchema) -> Any:
    """Normalize a raw cell value according to schema field type."""
    # Handle numeric types BEFORE string conversion — critical for Excel numeric cells
    # where float 0.0/1.0 must NOT be stringified to "0.0"/"1.0" and mangled by
    # the diacritics-stripping pipeline.
    if isinstance(raw_value, float):
        if field.field_type in ("integer", "int"):
            return int(raw_value)
        if field.field_type in ("float", "double"):
            return float(raw_value)
        return raw_value
    if isinstance(raw_value, int) and field.field_type in ("integer", "int"):
        return int(raw_value)

    # String normalization path for text/date/array fields
    text = normalize_unicode_text(raw_value)
    if text == "":
        raw_normalized: Any = None
    else:
        raw_normalized = text

    if field.field_type == "string":
        value = raw_normalized if raw_normalized is None else str(raw_normalized)
    elif field.field_type == "integer":
        value = coerce_int(raw_normalized)
    elif field.field_type == "float":
        value = coerce_float(raw_normalized)
    elif field.field_type == "boolean":
        value = coerce_bool(raw_normalized)
    elif field.field_type == "date":
        value = parse_date_ddmmyyyy(str(raw_normalized or ""))
    elif field.field_type == "array":
        if raw_normalized is None:
            value = None
        elif isinstance(raw_value, list):
            value = raw_value
        else:
            value = [item.strip() for item in str(raw_normalized).split(";") if item.strip()]
    elif field.field_type == "object":
        value = raw_value if isinstance(raw_value, dict) else None
    else:
        value = raw_normalized

    value = apply_transform(value, field.transform)

    if value is None and field.default is not None:
        return field.default
    return value
