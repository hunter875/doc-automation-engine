"""Debug: trace exact values in pipeline."""
import sys
sys.path.insert(0, '/app')

import openpyxl

# Clear caches
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
from app.engines.extraction.daily_report_builder import _CUSTOM_MAPPING_CACHE as DRB_CACHE
_CUSTOM_MAPPING_CACHE.clear()
DRB_CACHE.clear()

from app.engines.extraction.mapping.normalizer import normalize_unicode_text
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data

EXCEL_PATH = "/app/1.xlsx"
wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
ws = wb["BC NGÀY"]
rows = []
for row in ws.iter_rows(values_only=True):
    if any(cell is not None for cell in row):
        rows.append(list(row))

# Build combined header
sub_header = rows[1]
combined = list(sub_header)
for idx, val in enumerate(rows[0]):
    if val is not None:
        combined[idx] = val

# Build row dict for first data row
row = rows[3]
row_dict = {}
for col_idx, sub_val in enumerate(sub_header):
    header_name = sub_val if sub_val is not None else None
    if combined and col_idx < len(combined) and combined[col_idx] is not None:
        header_name = combined[col_idx]
    if header_name is None or col_idx >= len(row):
        continue
    key = normalize_unicode_text(str(header_name).strip())
    row_dict[key] = row[col_idx]

print("=== Row dict (key=normalized, val=raw) ===")
for k, v in row_dict.items():
    print(f"  {k!r}: {v!r}")

# Simulate what _build_output_custom does
core = row_dict
schema_path = "/app/app/domain/templates/bc_ngay_kv30_schema.yaml"
from app.engines.extraction.sheet_pipeline import _build_output_custom_header, _normalize_key

# Simulate _build_output_custom_header
mapping = _CUSTOM_MAPPING_CACHE[schema_path] if schema_path in _CUSTOM_MAPPING_CACHE else None
if mapping is None:
    from app.engines.extraction.sheet_pipeline import _load_custom_mapping
    mapping = _load_custom_mapping(schema_path)
    _CUSTOM_MAPPING_CACHE[schema_path] = mapping

sheet_mapping = mapping.get("sheet_mapping") if isinstance(mapping, dict) else mapping
header_spec = sheet_mapping.get("header", {})

core_norm = {_normalize_key(k): v for k, v in core.items()}
print("\n=== core_norm (normalized keys) ===")
for k, v in core_norm.items():
    if v is not None:
        print(f"  {k!r}: {v!r}")

# Check day/month
day_found = None
month_found = None
for k, v in core_norm.items():
    if v is not None:
        if 'ngay' in k.lower() or k == 'ngay':
            print(f"\n  Found day candidate: {k!r} = {v!r}")
            day_found = v
        if 'thang' in k.lower() or k == 'thang':
            print(f"  Found month candidate: {k!r} = {v!r}")
            month_found = v

# What _build_output_custom_header does
print(f"\nIn _build_output_custom_header:")
print(f"  day_val would be: {day_found!r}")
print(f"  month_val would be: {month_found!r}")
print(f"  ngay_bao_cao would be: {day_found!r}/{month_found!r}/2026")
