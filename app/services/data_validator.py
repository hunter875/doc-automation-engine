"""Data Validator — Pydantic-based "Chốt kiểm dịch" for LLM output.

This module sits between the AI extraction (Bước 1) and the database INSERT.
It validates, coerces, and normalises the raw JSON that the LLM spits out
so that the data stored in JSONB is *always* clean and typed correctly.

Pipeline:
  LLM raw JSON → DataValidator.validate() → clean JSON + validation_report

Features:
  1. Type Coercion:
     - "Hai vụ" → 2  (Vietnamese text → number)
     - "1,500,000" → 1500000
     - "12.5%" → 12.5
     - "đúng" / "có" → True
  2. Date Normalization:
     - "02-03-2026" → "02/03/2026"  (DD/MM/YYYY canonical)
     - "2026-03-02" → "02/03/2026"
     - "2 tháng 3 năm 2026" → "02/03/2026"
  3. Array item validation (for array-of-object schemas)
  4. Missing field detection + null-filling
  5. Validation report with warnings/auto-corrections
"""

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Vietnamese number words ──────────────────────────────────

_VN_NUMBERS = {
    "không": 0, "một": 1, "hai": 2, "ba": 3, "bốn": 4, "bon": 4,
    "năm": 5, "nam": 5, "sáu": 6, "sau": 6, "bảy": 7, "bay": 7,
    "tám": 8, "tam": 8, "chín": 9, "chin": 9, "mười": 10, "muoi": 10,
    "mười một": 11, "mười hai": 12, "mười ba": 13, "mười bốn": 14,
    "mười lăm": 15, "mười sáu": 16, "mười bảy": 17, "mười tám": 18,
    "mười chín": 19, "hai mươi": 20, "ba mươi": 30, "bốn mươi": 40,
    "năm mươi": 50, "sáu mươi": 60, "bảy mươi": 70, "tám mươi": 80,
    "chín mươi": 90, "trăm": 100, "nghìn": 1000, "ngàn": 1000,
    "triệu": 1_000_000, "tỷ": 1_000_000_000,
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_VN_BOOL_TRUE = {"đúng", "dung", "có", "co", "true", "yes", "1", "rồi", "roi", "x", "✓", "✔"}
_VN_BOOL_FALSE = {"sai", "không", "khong", "false", "no", "0", "chưa", "chua", ""}

# Date patterns
_DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    (re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$"), "dmy"),
    # YYYY-MM-DD (ISO)
    (re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$"), "ymd"),
    # YYYY/MM/DD
    (re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$"), "ymd"),
]

# Vietnamese month names
_VN_MONTHS = {
    "tháng 1": 1, "tháng 01": 1, "thang 1": 1,
    "tháng 2": 2, "tháng 02": 2, "thang 2": 2,
    "tháng 3": 3, "tháng 03": 3, "thang 3": 3,
    "tháng 4": 4, "tháng 04": 4, "thang 4": 4,
    "tháng 5": 5, "tháng 05": 5, "thang 5": 5,
    "tháng 6": 6, "tháng 06": 6, "thang 6": 6,
    "tháng 7": 7, "tháng 07": 7, "thang 7": 7,
    "tháng 8": 8, "tháng 08": 8, "thang 8": 8,
    "tháng 9": 9, "tháng 09": 9, "thang 9": 9,
    "tháng 10": 10, "thang 10": 10,
    "tháng 11": 11, "thang 11": 11,
    "tháng 12": 12, "thang 12": 12,
}


# ── Coercion helpers ─────────────────────────────────────────

def _coerce_to_number(value: Any) -> tuple[Any, str | None]:
    """Try to coerce a value to a number. Returns (result, warning_or_None)."""
    if isinstance(value, (int, float)):
        return value, None

    if value is None:
        return None, None

    raw = str(value).strip()
    if not raw:
        return None, None

    # 1. Strip common suffixes (VNĐ, đồng, %, vụ, người, etc.)
    cleaned = re.sub(
        r"\s*(VNĐ|vnđ|đồng|dong|vụ|vu|người|nguoi|cái|cai|chiếc|chiec|"
        r"km|m|kg|g|lít|lit|ha|USD|\$|€|%)\s*$",
        "", raw
    ).strip()

    # 2. Try direct parse (handles "1500000", "12.5")
    try:
        # Handle Vietnamese/European number format: 1.500.000 or 1,500,000
        # If has both dots and commas, figure out which is thousand separator
        if "," in cleaned and "." in cleaned:
            # "1,500,000.50" → US format
            if cleaned.rindex(".") > cleaned.rindex(","):
                cleaned_num = cleaned.replace(",", "")
            # "1.500.000,50" → EU/VN format
            else:
                cleaned_num = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            # Could be "1,500,000" (thousand sep) or "12,5" (decimal)
            parts = cleaned.split(",")
            if all(len(p) == 3 for p in parts[1:]):
                # thousand separator
                cleaned_num = cleaned.replace(",", "")
            else:
                # decimal
                cleaned_num = cleaned.replace(",", ".")
        elif cleaned.count(".") > 1:
            # "1.500.000" → thousand separator
            cleaned_num = cleaned.replace(".", "")
        else:
            cleaned_num = cleaned

        result = float(cleaned_num)
        # Return int if it's a whole number
        if result == int(result) and "." not in cleaned_num:
            result = int(result)
        warning = f'"{raw}" → {result}' if str(result) != raw else None
        return result, warning

    except (ValueError, TypeError):
        pass

    # 3. Try Vietnamese text numbers
    lower = cleaned.lower()
    if lower in _VN_NUMBERS:
        num = _VN_NUMBERS[lower]
        return num, f'"{raw}" → {num} (Vietnamese text)'

    # 4. Percentage: "12.5%" → 12.5
    pct_match = re.match(r"^([0-9.,]+)\s*%$", raw)
    if pct_match:
        try:
            val = float(pct_match.group(1).replace(",", "."))
            return val, f'"{raw}" → {val} (percentage)'
        except ValueError:
            pass

    # 5. Simple Vietnamese compound: "hai mươi ba" → can't easily parse all,
    #    but handle common ones
    # If we can't parse, return None with a warning
    return None, f'Cannot coerce "{raw}" to number — set null'


def _coerce_to_boolean(value: Any) -> tuple[Any, str | None]:
    """Coerce a value to boolean."""
    if isinstance(value, bool):
        return value, None
    if value is None:
        return None, None

    raw = str(value).strip().lower()
    if raw in _VN_BOOL_TRUE:
        warning = f'"{value}" → true' if not isinstance(value, bool) else None
        return True, warning
    if raw in _VN_BOOL_FALSE:
        warning = f'"{value}" → false' if not isinstance(value, bool) else None
        return False, warning

    return None, f'Cannot coerce "{value}" to boolean — set null'


def _coerce_to_date(value: Any) -> tuple[str | None, str | None]:
    """Normalize date string to DD/MM/YYYY format."""
    if value is None:
        return None, None

    raw = str(value).strip()
    if not raw:
        return None, None

    # 1. Try regex patterns
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.match(raw)
        if m:
            groups = m.groups()
            if fmt == "dmy":
                d, mo, y = int(groups[0]), int(groups[1]), int(groups[2])
            elif fmt == "ymd":
                y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                continue

            try:
                dt = datetime(y, mo, d)
                result = dt.strftime("%d/%m/%Y")
                warning = f'"{raw}" → "{result}"' if result != raw else None
                return result, warning
            except ValueError:
                continue

    # 2. Try Vietnamese date: "ngày 2 tháng 3 năm 2026"
    vn_match = re.match(
        r"(?:ngày|ngay)?\s*(\d{1,2})\s+"
        r"(?:tháng|thang)\s*(\d{1,2})\s+"
        r"(?:năm|nam)\s*(\d{4})",
        raw, re.IGNORECASE,
    )
    if vn_match:
        d, mo, y = int(vn_match.group(1)), int(vn_match.group(2)), int(vn_match.group(3))
        try:
            dt = datetime(y, mo, d)
            result = dt.strftime("%d/%m/%Y")
            return result, f'"{raw}" → "{result}" (Vietnamese date)'
        except ValueError:
            pass

    # 3. Try Python dateutil as last resort
    try:
        from dateutil import parser as dateutil_parser
        dt = dateutil_parser.parse(raw, dayfirst=True)
        result = dt.strftime("%d/%m/%Y")
        return result, f'"{raw}" → "{result}" (dateutil)'
    except Exception:
        pass

    # Can't parse — return as-is with warning
    return raw, f'Date format not recognized: "{raw}" — kept as-is'


def _is_date_field(field_name: str, description: str = "") -> bool:
    """Heuristic: check if a string field is likely a date."""
    combined = (field_name + " " + description).lower()
    date_keywords = [
        "ngay", "ngày", "date", "thoi_gian", "thời_gian", "time",
        "tu_ngay", "den_ngay", "từ_ngày", "đến_ngày", "start_date",
        "end_date", "ky_bao_cao", "kỳ_báo_cáo", "period",
        "nam_", "năm_", "thang_", "tháng_",
    ]
    return any(kw in combined for kw in date_keywords)


# ── Main DataValidator class ─────────────────────────────────

class DataValidator:
    """Validate and coerce LLM extraction output against a schema_definition.

    Usage:
        validator = DataValidator(schema_definition)
        clean_data, report = validator.validate(raw_llm_output)
        # clean_data: ready for INSERT into JSONB
        # report: dict with warnings, auto_corrections, missing_fields, extra_fields
    """

    def __init__(self, schema_definition: dict):
        """Initialize with schema_definition from ExtractionTemplate.

        Args:
            schema_definition: {"fields": [{"name": ..., "type": ..., ...}, ...]}
        """
        self.schema = schema_definition
        self.fields = {f["name"]: f for f in schema_definition.get("fields", [])}

    def validate(self, raw_data: dict | None) -> tuple[dict, dict]:
        """Validate and coerce raw LLM output.

        Args:
            raw_data: The raw extracted_data dict from LLM

        Returns:
            (clean_data, validation_report)
            clean_data: Coerced and validated dict ready for DB
            validation_report: {
                "is_valid": bool,
                "total_fields": int,
                "valid_fields": int,
                "warnings": [...],
                "auto_corrections": [...],
                "missing_fields": [...],
                "extra_fields": [...],
            }
        """
        if raw_data is None:
            raw_data = {}

        clean: dict[str, Any] = {}
        warnings: list[str] = []
        auto_corrections: list[dict] = []
        missing_fields: list[str] = []
        extra_fields: list[str] = []

        # 1. Validate each expected field
        for field_name, field_def in self.fields.items():
            field_type = field_def.get("type", "string")
            description = field_def.get("description", "")

            if field_name not in raw_data or raw_data[field_name] is None:
                missing_fields.append(field_name)
                clean[field_name] = None
                continue

            raw_value = raw_data[field_name]

            if field_type == "number":
                coerced, warning = _coerce_to_number(raw_value)
                clean[field_name] = coerced
                if warning:
                    auto_corrections.append({
                        "field": field_name,
                        "original": raw_value,
                        "coerced": coerced,
                        "note": warning,
                    })

            elif field_type == "boolean":
                coerced, warning = _coerce_to_boolean(raw_value)
                clean[field_name] = coerced
                if warning:
                    auto_corrections.append({
                        "field": field_name,
                        "original": raw_value,
                        "coerced": coerced,
                        "note": warning,
                    })

            elif field_type == "string":
                # Check if it's a date field by name/description
                if _is_date_field(field_name, description):
                    coerced, warning = _coerce_to_date(raw_value)
                    clean[field_name] = coerced
                    if warning:
                        auto_corrections.append({
                            "field": field_name,
                            "original": raw_value,
                            "coerced": coerced,
                            "note": warning,
                        })
                else:
                    # Plain string — just ensure it's a string
                    clean[field_name] = str(raw_value) if raw_value is not None else None

            elif field_type == "array":
                coerced, arr_warnings = self._validate_array(
                    field_name, field_def, raw_value
                )
                clean[field_name] = coerced
                warnings.extend(arr_warnings)

            elif field_type == "object":
                coerced, obj_warnings = self._validate_object(
                    field_name, field_def, raw_value
                )
                clean[field_name] = coerced
                warnings.extend(obj_warnings)

            else:
                # Unknown type — pass through
                clean[field_name] = raw_value
                warnings.append(f"Unknown type '{field_type}' for field '{field_name}'")

        # 2. Detect extra fields (LLM returned fields not in schema)
        for key in raw_data:
            if key not in self.fields:
                extra_fields.append(key)
                # Keep extra fields but flag them
                clean[key] = raw_data[key]

        valid_fields = len(self.fields) - len(missing_fields)
        total_fields = len(self.fields)

        report = {
            "is_valid": len(missing_fields) == 0 and len(warnings) == 0,
            "total_fields": total_fields,
            "valid_fields": valid_fields,
            "completeness_pct": round(valid_fields / total_fields * 100, 1) if total_fields > 0 else 0,
            "warnings": warnings,
            "auto_corrections": auto_corrections,
            "missing_fields": missing_fields,
            "extra_fields": extra_fields,
        }

        if auto_corrections:
            logger.info(
                f"DataValidator: {len(auto_corrections)} auto-corrections applied"
            )
        if missing_fields:
            logger.warning(
                f"DataValidator: {len(missing_fields)} missing fields: {missing_fields}"
            )

        return clean, report

    def _validate_array(
        self,
        field_name: str,
        field_def: dict,
        raw_value: Any,
    ) -> tuple[list, list[str]]:
        """Validate an array field, coercing each item if it's array-of-objects."""
        warnings: list[str] = []

        if not isinstance(raw_value, list):
            warnings.append(
                f"Field '{field_name}': expected array, got {type(raw_value).__name__} — wrapped"
            )
            raw_value = [raw_value] if raw_value is not None else []

        items_def = field_def.get("items", {})
        items_type = items_def.get("type", "string")

        if items_type == "object":
            # Array of objects — validate each row
            sub_fields = items_def.get("fields", [])
            if not sub_fields:
                return raw_value, warnings

            clean_items = []
            for i, item in enumerate(raw_value):
                if not isinstance(item, dict):
                    warnings.append(
                        f"Field '{field_name}[{i}]': expected object, got {type(item).__name__}"
                    )
                    continue

                clean_item = {}
                for sf in sub_fields:
                    sf_name = sf["name"]
                    sf_type = sf.get("type", "string")
                    sf_desc = sf.get("description", "")

                    if sf_name not in item:
                        clean_item[sf_name] = None
                        continue

                    val = item[sf_name]
                    if sf_type == "number":
                        coerced, _ = _coerce_to_number(val)
                        clean_item[sf_name] = coerced
                    elif sf_type == "boolean":
                        coerced, _ = _coerce_to_boolean(val)
                        clean_item[sf_name] = coerced
                    elif sf_type == "string" and _is_date_field(sf_name, sf_desc):
                        coerced, _ = _coerce_to_date(val)
                        clean_item[sf_name] = coerced
                    else:
                        clean_item[sf_name] = val

                # Keep any extra columns from LLM
                for k, v in item.items():
                    if k not in clean_item:
                        clean_item[k] = v

                clean_items.append(clean_item)

            return clean_items, warnings

        elif items_type == "number":
            clean_items = []
            for i, item in enumerate(raw_value):
                coerced, _ = _coerce_to_number(item)
                clean_items.append(coerced)
            return clean_items, warnings

        else:
            # Simple string array — ensure all items are strings
            return [str(x) if x is not None else None for x in raw_value], warnings

    def _validate_object(
        self,
        field_name: str,
        field_def: dict,
        raw_value: Any,
    ) -> tuple[dict, list[str]]:
        """Validate a nested object field."""
        warnings: list[str] = []

        if not isinstance(raw_value, dict):
            warnings.append(
                f"Field '{field_name}': expected object, got {type(raw_value).__name__}"
            )
            return {}, warnings

        sub_fields = field_def.get("fields", [])
        if not sub_fields:
            return raw_value, warnings

        clean_obj = {}
        for sf in sub_fields:
            sf_name = sf["name"]
            sf_type = sf.get("type", "string")
            sf_desc = sf.get("description", "")

            if sf_name not in raw_value:
                clean_obj[sf_name] = None
                continue

            val = raw_value[sf_name]
            if sf_type == "number":
                coerced, _ = _coerce_to_number(val)
                clean_obj[sf_name] = coerced
            elif sf_type == "boolean":
                coerced, _ = _coerce_to_boolean(val)
                clean_obj[sf_name] = coerced
            elif sf_type == "string" and _is_date_field(sf_name, sf_desc):
                coerced, _ = _coerce_to_date(val)
                clean_obj[sf_name] = coerced
            else:
                clean_obj[sf_name] = val

        return clean_obj, warnings
