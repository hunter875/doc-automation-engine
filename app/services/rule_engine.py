"""Domain rule engine for extraction outputs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BaseRule(ABC):
    """Abstract validation rule for domain logic."""

    code: str

    @abstractmethod
    def validate(self, payload: BaseModel) -> str | None:
        """Return error code if invalid, otherwise None."""


class RuleEngine:
    """Composable domain validator with injectable rules."""

    def __init__(self, rules: list[BaseRule] | None = None) -> None:
        self.rules = rules or []

    def validate(self, payload: BaseModel) -> list[str]:
        errors: list[str] = []
        for rule in self.rules:
            code = rule.validate(payload)
            if code:
                errors.append(code)
        return errors


class FieldEqualsListLengthRule(BaseRule):
    """Validate integer field equals list length."""

    def __init__(self, count_field: str, list_field: str, code: str) -> None:
        self.count_field = count_field
        self.list_field = list_field
        self.code = code

    def validate(self, payload: BaseModel) -> str | None:
        count_value = getattr(payload, self.count_field, None)
        list_value = getattr(payload, self.list_field, None)
        if not isinstance(count_value, int) or not isinstance(list_value, list):
            return None
        return None if count_value == len(list_value) else self.code


class DateFormatRule(BaseRule):
    """Validate dd/mm/yyyy date format for one field."""

    def __init__(self, field_name: str, code: str) -> None:
        self.field_name = field_name
        self.code = code

    def validate(self, payload: BaseModel) -> str | None:
        value = getattr(payload, self.field_name, "")
        if not value:
            return None
        if not isinstance(value, str):
            return self.code
        try:
            datetime.strptime(value.strip(), "%d/%m/%Y")
            return None
        except ValueError:
            return self.code


class DateRangeRule(BaseRule):
    """Validate from_date <= to_date for dd/mm/yyyy fields."""

    def __init__(self, from_field: str, to_field: str, code: str = "ERR_DATE_RANGE") -> None:
        self.from_field = from_field
        self.to_field = to_field
        self.code = code

    def validate(self, payload: BaseModel) -> str | None:
        from_value = getattr(payload, self.from_field, "")
        to_value = getattr(payload, self.to_field, "")
        if not from_value or not to_value:
            return None
        if not isinstance(from_value, str) or not isinstance(to_value, str):
            return self.code

        try:
            from_date = datetime.strptime(from_value.strip(), "%d/%m/%Y")
            to_date = datetime.strptime(to_value.strip(), "%d/%m/%Y")
        except ValueError:
            return None

        return None if from_date <= to_date else self.code


class ListItemDateFormatRule(BaseRule):
    """Validate dd/mm/yyyy date format for a field inside list items."""

    def __init__(self, list_field: str, date_field: str, code_prefix: str) -> None:
        self.list_field = list_field
        self.date_field = date_field
        self.code_prefix = code_prefix
        self.code = code_prefix

    def validate(self, payload: BaseModel) -> str | None:
        items = getattr(payload, self.list_field, None)
        if not isinstance(items, list):
            return None

        for index, item in enumerate(items, start=1):
            value: Any = getattr(item, self.date_field, "") if hasattr(item, self.date_field) else ""
            if not value:
                continue
            if not isinstance(value, str):
                return f"{self.code_prefix}_{index}"
            try:
                datetime.strptime(value.strip(), "%d/%m/%Y")
            except ValueError:
                return f"{self.code_prefix}_{index}"
        return None


def build_default_hybrid_rule_engine() -> RuleEngine:
    """Build default domain rules for current hybrid extraction payload."""
    return RuleEngine(
        rules=[
            FieldEqualsListLengthRule(
                count_field="stt_14_tong_cnch",
                list_field="danh_sach_cnch",
                code="ERR_CNCH_COUNT_MISMATCH",
            ),
            FieldEqualsListLengthRule(
                count_field="tong_xe_hu_hong",
                list_field="danh_sach_phuong_tien_hu_hong",
                code="ERR_VEHICLE_DAMAGE_COUNT_MISMATCH",
            ),
            DateFormatRule(field_name="ngay_bao_cao", code="ERR_REPORT_DATE_FORMAT"),
            DateFormatRule(field_name="tu_ngay", code="ERR_FROM_DATE_FORMAT"),
            DateFormatRule(field_name="den_ngay", code="ERR_TO_DATE_FORMAT"),
            DateRangeRule(from_field="tu_ngay", to_field="den_ngay", code="ERR_DATE_RANGE"),
            ListItemDateFormatRule(
                list_field="danh_sach_cnch",
                date_field="ngay_xay_ra",
                code_prefix="ERR_CNCH_DATE_FORMAT_ITEM",
            ),
        ]
    )
