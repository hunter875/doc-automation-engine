"""Template loader — reads YAML document templates and provides typed access."""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class DocumentTemplate:
    """Typed wrapper around a YAML document template."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # ── identity ──────────────────────────────────────────────────────
    @property
    def template_id(self) -> str:
        return self._data.get("template_id", "")

    @property
    def template_name(self) -> str:
        return self._data.get("template_name", "")

    @property
    def language(self) -> str:
        return self._data.get("language", "vi")

    # ── helpers ───────────────────────────────────────────────────────
    def _get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
            if node is default:
                return default
        return node

    def _get_str(self, *keys: str, default: str = "") -> str:
        return str(self._get(*keys, default=default))

    def _get_list(self, *keys: str) -> list:
        val = self._get(*keys, default=[])
        return val if isinstance(val, list) else []

    def _get_int(self, *keys: str, default: int = 0) -> int:
        val = self._get(*keys, default=default)
        return int(val) if val is not None else default

    # ── block detection ───────────────────────────────────────────────
    @property
    def narrative_start_re(self) -> re.Pattern:
        return re.compile(self._get_str("block_detection", "narrative_start_pattern"), re.IGNORECASE)

    @property
    def narrative_start_fallback_lines(self) -> int:
        return self._get_int("block_detection", "narrative_start_fallback_lines", default=30)

    @property
    def table_anchor_re(self) -> re.Pattern:
        return re.compile(self._get_str("block_detection", "table_anchor_pattern"), re.IGNORECASE)

    @property
    def section_split_re(self) -> re.Pattern:
        return re.compile(self._get_str("block_detection", "section_split_pattern"))

    # ── prompts ───────────────────────────────────────────────────────
    def extraction_prompt(self, block_name: str) -> str:
        tpl = self._get_str("prompts", "extraction")
        return tpl.replace("{block_name}", block_name)

    def enforcer_prompt(self, field_name: str) -> str:
        tpl = self._get_str("prompts", "enforcer")
        return tpl.replace("{field_name}", field_name)

    # ── header ────────────────────────────────────────────────────────
    @property
    def header_max_lines(self) -> int:
        return self._get_int("header", "max_lines", default=30)

    @property
    def header_max_context_chars(self) -> int:
        return self._get_int("header", "max_context_chars", default=3000)

    @property
    def header_required_fields(self) -> list[str]:
        return self._get_list("header", "required_fields")

    @property
    def report_number_primary_re(self) -> re.Pattern:
        return re.compile(self._get_str("header", "report_number", "primary_pattern"), re.IGNORECASE)

    @property
    def report_number_fallback_re(self) -> re.Pattern:
        return re.compile(self._get_str("header", "report_number", "fallback_pattern"), re.IGNORECASE)

    @property
    def report_number_format_re(self) -> re.Pattern:
        return re.compile(self._get_str("header", "report_number", "format_regex"))

    @property
    def date_long_form_re(self) -> re.Pattern:
        return re.compile(self._get_str("header", "date", "long_form"), re.IGNORECASE)

    @property
    def date_short_form_re(self) -> re.Pattern:
        return re.compile(self._get_str("header", "date", "short_form"), re.IGNORECASE)

    @property
    def date_period_markers(self) -> list[str]:
        return self._get_list("header", "date", "period_markers")

    @property
    def date_skip_line_re(self) -> re.Pattern:
        return re.compile(self._get_str("header", "date", "skip_line_pattern"), re.IGNORECASE)

    @property
    def unit_patterns(self) -> list[re.Pattern]:
        return [re.compile(p) for p in self._get_list("header", "unit", "patterns")]

    # ── narrative ─────────────────────────────────────────────────────
    @property
    def summary_section_keyword(self) -> str:
        return self._get_str("narrative", "summary_section_keyword")

    @property
    def summary_max_lines(self) -> int:
        return self._get_int("narrative", "summary_max_lines", default=10)

    def narrative_count_patterns(self, field: str) -> list[str]:
        return self._get_list("narrative", "counts", field)

    @property
    def detail_keywords(self) -> list[str]:
        return self._get_list("narrative", "detail_keywords")

    @property
    def detail_max_lines(self) -> int:
        return self._get_int("narrative", "detail_max_lines", default=12)

    @property
    def incident_time_re(self) -> re.Pattern:
        return re.compile(self._get_str("narrative", "incident_time_pattern"), re.IGNORECASE)

    @property
    def incident_location_re(self) -> re.Pattern:
        return re.compile(
            self._get_str("narrative", "incident_location_pattern"),
            re.DOTALL | re.IGNORECASE,
        )

    @property
    def incident_description_re(self) -> re.Pattern:
        return re.compile(self._get_str("narrative", "incident_description_pattern"), re.IGNORECASE)

    @property
    def incident_context_chars(self) -> int:
        return self._get_int("narrative", "incident_context_chars", default=500)

    @property
    def incident_location_max_chars(self) -> int:
        return self._get_int("narrative", "incident_location_max_chars", default=200)

    # ── table ─────────────────────────────────────────────────────────
    @property
    def table_header_skip_keywords(self) -> list[str]:
        return self._get_list("table", "header_skip_keywords")

    @property
    def law_citation_tail_re(self) -> re.Pattern:
        return re.compile(self._get_str("table", "law_citation_tail"), re.IGNORECASE)

    @property
    def incident_row_patterns_spaced(self) -> list[str]:
        return self._get_list("table", "incident_row_patterns", "spaced")

    @property
    def incident_row_patterns_compact(self) -> list[str]:
        return self._get_list("table", "incident_row_patterns", "compact")

    @property
    def structured_incident_headers(self) -> list[str]:
        return self._get_list("table", "structured_incident_headers")

    @property
    def cnch_fallback_patterns(self) -> list[str]:
        return self._get_list("table", "cnch_fallback_patterns")

    # ── validation ────────────────────────────────────────────────────
    @property
    def year_range(self) -> tuple[int, int]:
        r = self._get_list("validation", "year_range")
        return (int(r[0]), int(r[1])) if len(r) == 2 else (2020, 2030)

    @property
    def max_ket_qua(self) -> int:
        return self._get_int("validation", "max_ket_qua", default=10000)

    @property
    def cross_field_tolerance(self) -> int:
        return self._get_int("validation", "cross_field_tolerance", default=3)

    @property
    def non_negative_fields(self) -> list[str]:
        return self._get_list("validation", "non_negative_fields")


# ─── Registry ─────────────────────────────────────────────────────────

@lru_cache(maxsize=32)
def load_template(template_id: str) -> DocumentTemplate:
    """Load a YAML template by id.  Cached for repeat calls."""
    yaml_path = _TEMPLATES_DIR / f"{template_id}.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"Template '{template_id}' not found at {yaml_path}")

    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    logger.info("Loaded document template '%s' v%s", template_id, data.get("version"))
    return DocumentTemplate(data)


def list_templates() -> list[dict[str, str]]:
    """Return metadata for all available templates."""
    result = []
    if not _TEMPLATES_DIR.is_dir():
        return result
    for f in sorted(_TEMPLATES_DIR.glob("*.yaml")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            result.append({
                "template_id": data.get("template_id", f.stem),
                "template_name": data.get("template_name", ""),
                "version": data.get("version", ""),
                "language": data.get("language", ""),
            })
        except Exception:
            logger.warning("Failed to read template %s", f, exc_info=True)
    return result


def get_default_template() -> DocumentTemplate:
    """Return the default (pccc) template."""
    return load_template("pccc")
