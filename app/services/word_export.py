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
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)

MAX_DOCX_MEMBER_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES = 120 * 1024 * 1024
MAX_DOCX_ENTRIES = 2000
MAX_DOCX_COMPRESSION_RATIO = 150
MAX_TEMPLATE_INPUT_BYTES = 50 * 1024 * 1024


# ── Template pre-processing: fix common tag mistakes ──────────

def _fix_jinja_tags_in_docx(template_bytes: bytes) -> bytes:
    """
    Pre-process a .docx template to fix Jinja2 tag issues.

    Key fix: {%p if/else/endif/for/endfor %} tags that are INLINE within a paragraph
    (i.e. mixed with other text) must be converted to {% ... %} — because docxtpl
    only supports {%p %} when the tag occupies its own standalone paragraph.

    Also fixes: missing spaces in block tags → {%endif%} → {% endif %}
    """
    entries = _safe_read_docx_entries(template_bytes)

    for arcname, data in list(entries.items()):
        if not arcname.endswith(".xml"):
            continue
        entries[arcname] = _fix_jinja_tags_in_xml(data)

    out_buffer = io.BytesIO()
    with zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
        for arcname, data in entries.items():
            zout.writestr(arcname, data)
    return out_buffer.getvalue()


def _safe_read_docx_entries(template_bytes: bytes) -> dict[str, bytes]:
    """Read docx zip entries with strict anti-zip-bomb limits."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(template_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid Word template: malformed zip archive") from exc

    with zin:
        infos = zin.infolist()
        if len(infos) > MAX_DOCX_ENTRIES:
            raise ValueError("Invalid Word template: too many zip entries")

        total_uncompressed = 0
        entries: dict[str, bytes] = {}

        for info in infos:
            if info.is_dir():
                continue

            if info.file_size > MAX_DOCX_MEMBER_UNCOMPRESSED_BYTES:
                raise ValueError(
                    "Invalid Word template: zip entry exceeds maximum allowed uncompressed size"
                )

            total_uncompressed += info.file_size
            if total_uncompressed > MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES:
                raise ValueError(
                    "Invalid Word template: total uncompressed size exceeds safe threshold"
                )

            compressed_size = max(info.compress_size, 1)
            compression_ratio = info.file_size / compressed_size
            if compression_ratio > MAX_DOCX_COMPRESSION_RATIO:
                raise ValueError("Invalid Word template: suspicious compression ratio detected")

            entries[info.filename] = zin.read(info.filename)

        return entries


def _xml_local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _normalize_jinja_text(text: str) -> str:
    fixed = text

    fixed = re.sub(
        r"\{%-?\s*p\s+([^%]+?)\s*-?%\}",
        r"{% \1 %}",
        fixed,
    )
    fixed = re.sub(
        r"\{%-?\s*tr\s+((?:for\b|endfor)[^%]*?)\s*-?%\}",
        r"{% \1 %}",
        fixed,
    )
    fixed = re.sub(
        r"\{%-?\s*(end(?:if|for|while|macro|call|block|raw)|else)\s*-?%\}",
        r"{% \1 %}",
        fixed,
    )
    return fixed


def _fix_jinja_tags_in_xml(xml_bytes: bytes) -> bytes:
    """Fix Jinja tags by parsing XML nodes instead of raw-regex on XML text."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return xml_bytes

    changed = False

    for paragraph in root.iter():
        if _xml_local_name(paragraph.tag) != "p":
            continue

        text_nodes = [node for node in paragraph.iter() if _xml_local_name(node.tag) == "t"]
        if not text_nodes:
            continue

        merged_text = "".join(node.text or "" for node in text_nodes)
        if not merged_text:
            continue

        fixed_text = _normalize_jinja_text(merged_text)
        if fixed_text == merged_text:
            continue

        text_nodes[0].text = fixed_text
        for node in text_nodes[1:]:
            node.text = ""
        changed = True

    if not changed:
        return xml_bytes

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


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
    if len(template_bytes or b"") > MAX_TEMPLATE_INPUT_BYTES:
        raise ValueError("Invalid Word template: file size exceeds maximum allowed limit")

    try:
        # Pre-process template to fix common Jinja2 tag errors
        template_bytes = _fix_jinja_tags_in_docx(template_bytes)
        doc = DocxTemplate(io.BytesIO(template_bytes))
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid Word template: {e}") from e

    # Register custom Jinja2 filters
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
        err_msg = str(e)
        logger.error(f"Word template rendering failed: {e}")
        # Give more helpful hints for common Jinja2 errors
        if "unknown tag" in err_msg.lower():
            tag = re.search(r"'(\w+)'", err_msg)
            tag_name = tag.group(1) if tag else "unknown"
            raise ValueError(
                f"Template rendering error: Tag '{tag_name}' không hợp lệ trong file Word template. "
                f"Hãy kiểm tra cú pháp Jinja2: dùng {{% if %}}, {{% endif %}}, {{% for %}}, {{% endfor %}}. "
                f"Lưu ý: Word có thể tự tách tag thành nhiều phần — hãy dùng 'Paste as plain text' khi gõ tag."
            ) from e
        raise ValueError(f"Template rendering error: {e}") from e

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

    This function is now a pure renderer. The caller should pass a clean
    context/DTO (already prepared by aggregation layer).

    Args:
        template_bytes: Raw .docx template bytes
        aggregated_data: Clean context data for Word rendering
        extra_context: Optional additional variables (report name, user info, etc.)
        record_index: Deprecated. Kept only for backward compatibility.

    Returns:
        Rendered .docx as bytes
    """
    context: dict[str, Any] = dict(aggregated_data or {})
    if record_index is not None and "record_index" not in context:
        context["record_index"] = int(record_index)

    if extra_context:
        context.update(extra_context)

    return render_word_template(template_bytes, context)
