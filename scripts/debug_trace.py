#!/usr/bin/env python3
"""Full trace of _build_report_for_date for BC NGÀY."""
import sys
sys.path.insert(0, '/app')

from app.engines.extraction.sources.sheets_source import GoogleSheetsSource, SheetsFetchConfig
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data
from app.engines.extraction.mapping.normalizer import normalize_unicode_text

sheet_id = '1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI'
sheets_source = GoogleSheetsSource()
rows = sheets_source.fetch_values(SheetsFetchConfig(sheet_id=sheet_id, worksheet='BC NGÀY', range_a1=None))
print(f"Total rows: {len(rows)}")

schema = load_schema('bc_ngay_kv30_schema.yaml')

# Simulate what _build_report_for_date does for header_row_idx=0
header_row_idx = 0
sub_header = rows[header_row_idx]
combined = None  # header_row_idx == 0

print(f"\n=== Header simulation ===")
print(f"header_row_idx={header_row_idx}")
print(f"sub_header[0:3]={sub_header[0:3]}")

# Test: is sub_header[col_idx] None for any column?
none_cols = [i for i, v in enumerate(sub_header) if v is None]
print(f"None columns in sub_header: {none_cols}")

# Build row_dict for row 32 (first data group)
row_idx = 32
row = rows[row_idx]
row_dict = {}
for col_idx in range(len(sub_header)):
    if col_idx >= len(row):
        continue
    header_val = sub_header[col_idx]
    if combined is not None and header_val is None:
        if col_idx < len(combined):
            header_name = str(combined[col_idx]).strip()
            row_dict[normalize_unicode_text(header_name)] = row[col_idx]
    else:
        if header_val is not None:
            header_name = str(header_val).strip()
            row_dict[normalize_unicode_text(header_name)] = row[col_idx]

print(f"\nrow_dict keys[:5]={list(row_dict.keys())[:5]}")
print(f"row_dict['ngay']={row_dict.get('ngay', 'NOT FOUND')}")

# Now map to schema
doc_data, m, t, miss = map_row_to_document_data(row_dict, schema)
print(f"\nmap_row_to_document_data result:")
print(f"  matched={m}/{t}")
print(f"  doc_data['ngay_bao_cao_day']={doc_data.get('ngay_bao_cao_day')}")
print(f"  doc_data['tong_so_vu_chay']={doc_data.get('tong_so_vu_chay')}")
print(f"  doc_data['tong_chi_vien']={doc_data.get('tong_chi_vien')}")
print(f"  doc_data['tong_so_vu_cnch']={doc_data.get('tong_so_vu_cnch')}")

# What aliases is tong_so_vu_chay checking?
nv_section = {'tong_so_vu_chay': {'aliases': ['VU CHÁY THỐNG KÊ', 'Vụ cháy thống kê']}}
for alias in ['VU CHÁY THỐNG KÊ', 'Vụ cháy thống kê']:
    norm = normalize_unicode_text(alias)
    found = norm in row_dict
    print(f"  Check alias {repr(alias)} norm={repr(norm)} in row_dict: {found}")

# What keys are in row_dict that match 'vụ cháy'?
vu_chay_keys = [k for k in row_dict if 'vu chay' in k or 'chay' in k]
print(f"\n  Keys in row_dict containing 'vu chay' or 'chay': {vu_chay_keys}")
