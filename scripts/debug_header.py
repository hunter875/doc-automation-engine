"""Trace _build_output_custom_header."""
import sys
sys.path.insert(0, '/app')

import openpyxl

# Clear caches
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
from app.engines.extraction.daily_report_builder import _CUSTOM_MAPPING_CACHE as DRB_CACHE
_CUSTOM_MAPPING_CACHE.clear()
DRB_CACHE.clear()

from app.engines.extraction.mapping.normalizer import normalize_unicode_text
from app.engines.extraction.sheet_pipeline import _build_output_custom_header, _normalize_key, _load_custom_mapping

EXCEL_PATH = "/app/1.xlsx"
wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
ws = wb["BC NGÀY"]
rows = []
for row in ws.iter_rows(values_only=True):
    if any(cell is not None for cell in row):
        rows.append(list(row))

# Build row dict for first data row (row 3)
sub_header = rows[1]
row = rows[3]
row_dict = {}
for col_idx in range(len(sub_header)):
    if col_idx < len(sub_header) and sub_header[col_idx] is None:
        if col_idx < len(rows[0]) and col_idx < len(row):
            header_name = str(rows[0][col_idx]).strip()
            row_dict[normalize_unicode_text(header_name)] = row[col_idx]
    else:
        if col_idx < len(row):
            header_name = str(sub_header[col_idx]).strip()
            row_dict[normalize_unicode_text(header_name)] = row[col_idx]

print("=== row_dict ===")
for k, v in row_dict.items():
    print(f"  {k!r}: {v!r}")

# Load mapping and simulate _build_output_custom_header
schema_path = "/app/app/domain/templates/bc_ngay_kv30_schema.yaml"
mapping = _load_custom_mapping(schema_path)
sheet_mapping = mapping.get("sheet_mapping") if isinstance(mapping, dict) else mapping

# Show what _build_output_custom_header would see
core_norm = {_normalize_key(k): v for k, v in row_dict.items()}
print("\n=== core_norm (after normalize_key) ===")
for k, v in core_norm.items():
    print(f"  {k!r}: {v!r}")

# Check ngay and thang in core_norm
print(f"\n'ngay' in core_norm: {'ngay' in core_norm}")
print(f"'ngay_bao_cao_day' in core_norm: {'ngay_bao_cao_day' in core_norm}")
print(f"core_norm.get('ngay'): {core_norm.get('ngay')!r}")

# Simulate _build_output_custom_header logic
header_spec = sheet_mapping.get("header", {})
print(f"\n=== header_spec keys ===")
print(list(header_spec.keys()) if isinstance(header_spec, dict) else header_spec)

# Try to build BlockHeader
header = _build_output_custom_header(row_dict, mapping, year=2026)
print(f"\n=== Result ===")
print(f"ngay_bao_cao = {header.ngay_bao_cao!r}")
print(f"so_bao_cao = {header.so_bao_cao!r}")
