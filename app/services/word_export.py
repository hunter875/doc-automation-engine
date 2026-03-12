"""Word Template Export — Bước 4: Bơm khuôn Word (Headless Document Export).

Uses docxtpl (Jinja2 for .docx) to fill a Word template with aggregated data.
The Word template uses {{variable}} syntax in paragraphs, tables, headers/footers.

Flow:
  1. Upload a .docx template with {{...}} Jinja2 placeholders
  2. Store it in S3 under tenant's template folder
  3. When exporting, load template + aggregated JSON → render → return .docx bytes

Supports:
  - Simple variables: {{ten_don_vi}}, {{ngay_bao_cao}}
  - Loops in tables: {% for item in danh_sach_su_co %}...{% endfor %}
  - Conditional: {% if co_su_co %}...{% endif %}
  - Nested objects: {{metadata.template_name}}
  - Custom Jinja2 filters for number/date formatting
"""

import io
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)


# ── Jinja2 Filters for Vietnamese formatting ─────────────────

def _format_number_vn(value: Any) -> str:
    """Format number with Vietnamese dot-separator: 1500000 → 1.500.000"""
    if value is None:
        return "0"
    try:
        num = float(value)
        if num == int(num):
            # Integer formatting with dots
            return f"{int(num):,}".replace(",", ".")
        else:
            # Float: 2 decimal places, comma as decimal separator
            integer_part = int(num)
            decimal_part = round(num - integer_part, 2)
            formatted_int = f"{integer_part:,}".replace(",", ".")
            formatted_dec = f"{decimal_part:.2f}"[1:]  # ".50"
            return f"{formatted_int}{formatted_dec.replace('.', ',')}"
    except (ValueError, TypeError):
        return str(value)


def _format_date_vn(value: Any) -> str:
    """Format date as 'ngày DD tháng MM năm YYYY'."""
    if value is None:
        return ""
    raw = str(value).strip()

    # Try DD/MM/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if m:
        return f"ngày {m.group(1)} tháng {m.group(2)} năm {m.group(3)}"

    # Try ISO
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"ngày {m.group(3)} tháng {m.group(2)} năm {m.group(1)}"

    return raw


def _format_date_short(value: Any) -> str:
    """Format date as DD/MM/YYYY."""
    if value is None:
        return ""
    raw = str(value).strip()

    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"

    return raw


def _default_if_none(value: Any, default: str = "") -> str:
    """Return default if value is None."""
    return str(value) if value is not None else default


# ── Main export function ──────────────────────────────────────

def render_word_template(
    template_bytes: bytes,
    context_data: dict,
) -> bytes:
    """Render a .docx template with Jinja2 context data.

    Args:
        template_bytes: Raw bytes of the .docx template file
        context_data: Dict of variables to inject into the template.
                      Supports nested dicts, lists for table loops, etc.

    Returns:
        Rendered .docx file as bytes

    Raises:
        ValueError: If template is invalid or rendering fails
    """
    try:
        doc = DocxTemplate(io.BytesIO(template_bytes))
    except Exception as e:
        raise ValueError(f"Invalid Word template: {e}")

    # Register custom Jinja2 filters
    jinja_env = doc.get_docx().element  # noqa — we access the env via docxtpl
    # docxtpl exposes jinja_env on the DocxTemplate object
    if hasattr(doc, "jinja_env"):
        doc.jinja_env.filters["number_vn"] = _format_number_vn
        doc.jinja_env.filters["date_vn"] = _format_date_vn
        doc.jinja_env.filters["date_short"] = _format_date_short
        doc.jinja_env.filters["default_if_none"] = _default_if_none

    # Flatten context: move _metadata to top level for easy access
    flat_context = dict(context_data)
    if "_metadata" in flat_context:
        metadata = flat_context.pop("_metadata")
        flat_context["metadata"] = metadata

    # Add computed helpers
    flat_context["now"] = datetime.utcnow().strftime("%d/%m/%Y %H:%M")
    flat_context["today"] = datetime.utcnow().strftime("%d/%m/%Y")

    try:
        doc.render(flat_context)
    except Exception as e:
        logger.error(f"Word template rendering failed: {e}")
        raise ValueError(f"Template rendering error: {e}")

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    logger.info(
        f"Word template rendered successfully: "
        f"{len(flat_context)} context variables, "
        f"{len(buffer.getvalue())} bytes output"
    )

    return buffer.getvalue()


def render_aggregation_to_word(
    template_bytes: bytes,
    aggregated_data: dict,
    extra_context: dict | None = None,
    record_index: int | None = None,
) -> bytes:
    """Render an aggregation report into a Word template.

    Builds a CLEAN context from the single summary record only.
    Internal keys (_source_records, _flat_records, _metadata, metrics) are
    stripped — the Word template gets exactly the aggregated fields, nothing else.

    Args:
        template_bytes: Raw .docx template bytes
        aggregated_data: The aggregated_data dict from AggregationReport
        extra_context: Optional additional variables (report name, user info, etc.)
        record_index: Ignored — there is always only 1 summary record.

    Returns:
        Rendered .docx as bytes
    """
    _STRIP_KEYS = {"records", "_source_records", "_flat_records", "_metadata", "metrics"}

    # Start with the single summary record (records[0]) — the "Cục Cao"
    records = aggregated_data.get("records", [])
    if records and isinstance(records[0], dict):
        context = dict(records[0])
    else:
        context = {}

    # Also pull top-level aggregated fields that are NOT internal keys
    # (SUM/CONCAT results stored directly on aggregated_data)
    for k, v in aggregated_data.items():
        if k not in _STRIP_KEYS and not k.startswith("_"):
            context.setdefault(k, v)

    if extra_context:
        context.update(extra_context)

    return render_word_template(template_bytes, context)
