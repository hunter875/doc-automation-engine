"""Word template scanner — extract placeholders and infer schema.

Upload a .docx file containing {{placeholder}} markers.
This module:
  1. Scans all paragraphs, tables, headers/footers for {{...}} patterns.
  2. Tracks which placeholders appear INSIDE a Word table → marks as array+object.
  3. Uses simple heuristics to infer field types (string/number/boolean/array).
  4. For array fields that sit inside a Word table, extracts column headers as
     sub-fields (object schema) — no LLM needed for structured tables.
  5. Calls Gemini Flash via LLM to refine ambiguous array items into typed object
     sub-schemas when the table column headers are available.
  6. Generates aggregation rules:
       • number  → SUM
       • array   → CONCAT
  7. Returns a SchemaDefinition-compatible JSON + aggregation_rules.
"""

import io
import json
import logging
import re
from typing import Any

from docx import Document as DocxDocument

logger = logging.getLogger(__name__)

# Regex to find {{variable_name}} placeholders
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# ── Type-inference keyword lists ──────────────────────────────

NUMBER_KEYWORDS = [
    "so_", "tong_", "so ", "tong ", "amount", "total", "price", "quantity",
    "qty", "count", "sl_", "percent", "rate", "cost", "revenue", "fee",
    "value", "age", "year", "month", "day", "area", "weight",
    # Vietnamese (NFC)
    "số", "tổng", "giá", "phần_trăm", "tỷ_lệ", "chi_phí", "doanh_thu",
    "phí", "giá_trị", "tuổi", "năm", "tháng", "ngày", "diện_tích",
    "khối_lượng",
]

ARRAY_KEYWORDS = [
    "danh_sach", "danh_ds", "list_", "_list", "items_", "_items",
    "bang_", "_bang", "table_", "_table", "rows_", "_rows", "records_",
    "chi_tiet", "details_", "_details", "entries_", "hang_muc",
    # Vietnamese
    "danh_sách", "bảng", "chi_tiết", "hạng_mục", "dòng",
]

BOOLEAN_KEYWORDS = [
    "is_", "has_", "co_", "da_", "approved", "active", "enabled",
    "verified", "confirmed",
    # Vietnamese
    "có_", "đã_", "xac_nhan", "xác_nhận",
]

# Gemini type → label used in descriptions for sub-fields
_SUBFIELD_TYPE_HINTS = {
    "id": "string",
    "ma_": "string",
    "ten_": "string",
    "name_": "string",
    "loai_": "string",
    "type_": "string",
    "dia_chi": "string",
    "address": "string",
    "mo_ta": "string",
    "description": "string",
    "ghi_chu": "string",
    "note": "string",
    "ngay_": "string",
    "date_": "string",
    "thoi_gian": "string",
    "time_": "string",
    "so_": "number",
    "tong_": "number",
    "amount_": "number",
    "count_": "number",
    "price_": "number",
    "qty_": "number",
}


# ── Helpers ────────────────────────────────────────────────────

def _infer_type(var_name: str, context: str) -> str:
    name_lower = var_name.lower()
    ctx_lower = context.lower()

    for kw in BOOLEAN_KEYWORDS:
        if name_lower.startswith(kw) or kw in name_lower:
            return "boolean"
    for kw in ARRAY_KEYWORDS:
        if kw in name_lower or kw in ctx_lower:
            return "array"
    for kw in NUMBER_KEYWORDS:
        if kw in name_lower or kw in ctx_lower:
            return "number"
    return "string"


def _infer_subfield_type(col_name: str) -> str:
    col_lower = col_name.lower()
    for prefix, t in _SUBFIELD_TYPE_HINTS.items():
        if col_lower.startswith(prefix) or prefix.rstrip("_") in col_lower:
            return t
    return "string"


def _infer_description(var_name: str, context: str) -> str:
    readable = var_name.replace("_", " ").strip().title()
    if context.strip():
        lines = [ln.strip() for ln in context.split("\n") if ln.strip() and "{{" not in ln]
        if lines:
            return f"{readable} — từ: \"{lines[0][:80]}\""
    return readable


def _to_snake_case(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    if s and s[0].isdigit():
        s = "field_" + s
    return s or "unnamed_field"


def _extract_context(full_text: str, pos: int, window: int = 120) -> str:
    return full_text[max(0, pos - window): min(len(full_text), pos + window)]


# ── Table-aware extraction ─────────────────────────────────────

def _extract_table_placeholders(doc: DocxDocument) -> dict[str, dict[str, Any]]:
    """Scan Word tables and return placeholders with their column-header context.

    For each table that contains a {{placeholder}} in a data row, we look at the
    header row (first row) to understand what columns exist.  The placeholder
    maps to an array-of-objects field whose sub-fields mirror those columns.

    Returns:
        {snake_name: {"columns": [{"name": ..., "type": ...}], "table_text": str}}
    """
    table_arrays: dict[str, dict[str, Any]] = {}

    for table in doc.tables:
        rows = table.rows
        if len(rows) < 2:
            continue

        # Collect header column names from first row
        header_cols = [_to_snake_case(cell.text.strip()) for cell in rows[0].cells if cell.text.strip()]

        # Scan every non-header cell for placeholders
        full_table_text = "\n".join(
            " | ".join(cell.text.strip() for cell in row.cells)
            for row in rows
        )

        for row in rows[1:]:
            for cell in row.cells:
                for m in PLACEHOLDER_RE.finditer(cell.text):
                    snake = _to_snake_case(m.group(1))
                    if snake not in table_arrays:
                        cols = []
                        for col_name in header_cols:
                            if not col_name:
                                continue
                            cols.append({
                                "name": col_name,
                                "type": _infer_subfield_type(col_name),
                                "description": col_name.replace("_", " ").title(),
                            })
                        table_arrays[snake] = {
                            "columns": cols,
                            "table_text": full_table_text[:400],
                        }

    return table_arrays


# ── LLM refinement (optional, best-effort) ────────────────────

def _llm_refine_array_columns(
    var_name: str,
    columns: list[dict],
    table_text: str,
) -> list[dict]:
    """Ask Gemini Flash to review/correct the inferred sub-field types.

    Fires only for array fields with ≥1 column.  Failures are silently caught
    so the scan always completes even without a valid API key.
    """
    try:
        from google import genai  # noqa: PLC0415

        from app.core.config import settings  # noqa: PLC0415

        if not settings.GEMINI_API_KEY:
            return columns

        prompt = f"""Dưới đây là một đoạn bảng từ file Word báo cáo (tiếng Việt):

{table_text}

Biến array tên: {var_name}
Các cột đã phân tích tự động:
{json.dumps(columns, ensure_ascii=False, indent=2)}

Hãy trả về JSON array các cột đã sửa lại type cho đúng.
Chỉ dùng các type: string, number, boolean.
Trả về JSON array thuần (không giải thích gì thêm).
Ví dụ: [{{"name": "loai_su_co", "type": "string", "description": "Loại sự cố"}}, ...]"""

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_FLASH_MODEL,
            contents=prompt,
        )
        text = response.text.strip()
        # Strip markdown fences if present
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        refined = json.loads(text)
        if isinstance(refined, list) and refined:
            return refined
    except Exception as exc:
        logger.debug("LLM column refinement skipped: %s", exc)
    return columns


# ── Main entry point ──────────────────────────────────────────

def scan_word_template(file_bytes: bytes, use_llm: bool = True) -> dict[str, Any]:
    """Scan a .docx file and extract placeholder variables with inferred schema.

    Args:
        file_bytes: Raw bytes of the .docx file
        use_llm: If True, calls Gemini Flash to refine array sub-field types.

    Returns:
        {
          variables:          list of variable dicts with inferred metadata
          schema_definition:  ready SchemaDefinition JSON
          aggregation_rules:  suggested rules (SUM for numbers, CONCAT for arrays)
          stats:              scan statistics
        }
    """
    doc = DocxDocument(io.BytesIO(file_bytes))

    # ── Step 1: Table-aware scan → detect array-of-object placeholders ────
    table_arrays = _extract_table_placeholders(doc)

    # ── Step 2: Full-text scan for ALL placeholders ────────────────────────
    all_text_parts: list[str] = []

    for para in doc.paragraphs:
        if para.text.strip():
            all_text_parts.append(para.text)

    for table in doc.tables:
        for row in table.rows:
            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_texts:
                all_text_parts.append(" | ".join(row_texts))

    for section in doc.sections:
        for hf in [section.header, section.footer]:
            if hf:
                for para in hf.paragraphs:
                    if para.text.strip():
                        all_text_parts.append(para.text)

    full_text = "\n".join(all_text_parts)

    found: dict[str, dict[str, Any]] = {}
    for match in PLACEHOLDER_RE.finditer(full_text):
        raw_name = match.group(1)
        snake_name = _to_snake_case(raw_name)

        if snake_name in found:
            found[snake_name]["occurrences"] += 1
            continue

        context = _extract_context(full_text, match.start())

        # Force array type if placeholder lives inside a table
        if snake_name in table_arrays:
            field_type = "array"
        else:
            field_type = _infer_type(snake_name, context)

        found[snake_name] = {
            "name": snake_name,
            "original_name": raw_name,
            "type": field_type,
            "description": _infer_description(raw_name, context),
            "context_snippet": context.strip()[:200],
            "occurrences": 1,
        }

    variables = list(found.values())

    # ── Step 3: Build schema_definition ───────────────────────────────────
    fields: list[dict[str, Any]] = []
    for var in variables:
        field: dict[str, Any] = {
            "name": var["name"],
            "type": var["type"],
            "description": var["description"],
        }

        if var["type"] == "array":
            tbl = table_arrays.get(var["name"])
            if tbl and tbl["columns"]:
                # FIX lỗ hổng 2: array-of-object with real column sub-fields
                cols = tbl["columns"]
                if use_llm:
                    cols = _llm_refine_array_columns(
                        var["name"], cols, tbl["table_text"]
                    )
                field["items"] = {
                    "type": "object",
                    "description": f"Một hàng trong bảng {var['name']}",
                    "fields": cols,
                }
            else:
                # Fallback: flat string array (no table structure found)
                field["items"] = {"type": "string", "description": "Phần tử"}

        fields.append(field)

    schema_definition = {"fields": fields}

    # ── Step 4: Build aggregation rules ───────────────────────────────────
    # Rules:
    #   number → SUM  (cộng dồn số nguyên)
    #   array  → CONCAT  (nối mảng các ngày lại)
    #   string → LAST  (lấy giá trị của bản ghi cuối — tên đơn vị, người ký, v.v.)
    #
    # CRITICAL: output_field == source_field (KHÔNG thêm prefix total_/all_)
    # Word template dùng {{tong_so_vu_chay}} → output_field phải là tong_so_vu_chay
    agg_rules: list[dict[str, Any]] = []
    for var in variables:
        label_base = var["description"].split("—")[0].strip()
        if var["type"] == "number":
            agg_rules.append({
                "output_field": var["name"],   # giữ nguyên tên — khớp với {{biến}} trong Word
                "source_field": var["name"],
                "method": "SUM",
                "label": f"Tổng {label_base}",
            })
        elif var["type"] == "array":
            agg_rules.append({
                "output_field": var["name"],   # giữ nguyên tên
                "source_field": var["name"],
                "method": "CONCAT",
                "label": f"Tổng hợp {label_base}",
            })
        elif var["type"] == "string":
            # Chuỗi: lấy giá trị của bản ghi cuối (tên đơn vị, người ký, kỳ báo cáo...)
            agg_rules.append({
                "output_field": var["name"],   # giữ nguyên tên
                "source_field": var["name"],
                "method": "LAST",
                "label": label_base,
            })

    aggregation_rules = {"rules": agg_rules} if agg_rules else None

    return {
        "variables": variables,
        "schema_definition": schema_definition,
        "aggregation_rules": aggregation_rules,
        "stats": {
            "total_placeholders": sum(v["occurrences"] for v in variables),
            "unique_variables": len(variables),
            "array_with_object_schema": sum(
                1 for v in variables
                if v["type"] == "array" and v["name"] in table_arrays
            ),
            "paragraphs_scanned": len(doc.paragraphs),
            "tables_scanned": len(doc.tables),
        },
    }
