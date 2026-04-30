"""Minimal reproduction of BC NGAY ngay_bao_cao bug."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    _normalize_key, _resolve_field_value, _load_custom_mapping,
    _extract_core, _build_output_custom, _build_output_custom_header,
)
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data

SCHEMA = "/app/app/domain/templates/bc_ngay_schema.yaml"

# === Fake worksheet data (matches what Google Sheets returns) ===
worksheet_headers = ["ngày", "tháng", "Số báo cáo", "thời gian từ đến", "đơn vị báo cáo"]
worksheet_row    = [1, 4, "BC-01", "01/04/2026 - 20/04/2026", "Đội PCCC&CNCH Quận 1"]

# CHECKPOINT A: raw row_dict
row_dict = {}
for col_idx, header_val in enumerate(worksheet_headers):
    if col_idx < len(worksheet_row):
        row_dict[str(header_val).strip()] = worksheet_row[col_idx]
print(f"[A] row_dict = {row_dict}")

# === Load schema ===
schema = load_schema(SCHEMA)
mapping = _load_custom_mapping(SCHEMA)

# CHECKPOINT B: normalized doc_data after map_row_to_document_data
doc_data, m, t, miss = map_row_to_document_data(row_dict, schema)
print(f"[B] doc_data non-None = {{k: v for k, v in doc_data.items() if v is not None}}")
print(f"[B] matched = {m}/{t}")

# CHECKPOINT C: header mapping spec for ngay_bao_cao_day/month
header_spec = mapping.get("header", {})
day_spec   = header_spec.get("ngay_bao_cao_day", {})
month_spec = header_spec.get("ngay_bao_cao_month", {})
day_aliases   = day_spec.get("aliases", day_spec) if isinstance(day_spec, dict) else day_spec
month_aliases = month_spec.get("aliases", month_spec) if isinstance(month_spec, dict) else month_spec
print(f"[C] ngay_bao_cao_day aliases   = {day_aliases}")
print(f"[C] ngay_bao_cao_month aliases = {month_aliases}")

# Build core (this is what gets passed to _build_output_custom_header)
core = _extract_core({"data": doc_data})
print(f"[C] core = {core}")

core_norm = {_normalize_key(k): v for k, v in core.items()}
print(f"[C] core_norm keys = {list(core_norm.keys())}")

# CHECKPOINT D: resolve ngay_bao_cao_day
day_val = _resolve_field_value(core_norm, "ngay_bao_cao_day", day_aliases)
print(f"[D] _resolve_field_value(ngay_bao_cao_day) = {day_val!r}")

# CHECKPOINT E: resolve ngay_bao_cao_month
month_val = _resolve_field_value(core_norm, "ngay_bao_cao_month", month_aliases)
print(f"[E] _resolve_field_value(ngay_bao_cao_month) = {month_val!r}")

# CHECKPOINT F: _build_output_custom_header result
header = _build_output_custom_header(core, mapping)
print(f"[F] header.ngay_bao_cao = {header.ngay_bao_cao!r}")
print(f"[F] header.so_bao_cao  = {header.so_bao_cao!r}")

# CHECKPOINT G: full _build_output_custom result
output = _build_output_custom(core, mapping, schema_path=SCHEMA)
print(f"[G] output.header.ngay_bao_cao = {output.header.ngay_bao_cao!r}")
print()
print(f"EXPECTED: ngay_bao_cao = '01/04/2026'")
print(f"GOT:      ngay_bao_cao = {output.header.ngay_bao_cao!r}")
if output.header.ngay_bao_cao == "01/04/2026":
    print("PASS")
else:
    print("FAIL — value lost somewhere above")
