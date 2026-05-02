#!/usr/bin/env python3
"""Debug script to see actual normalized headers vs schema aliases."""
import sys
sys.path.insert(0, '/app')

from app.engines.extraction.sources.sheets_source import GoogleSheetsSource, SheetsFetchConfig
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.sheet_pipeline import _load_custom_mapping
from app.engines.extraction.mapping.normalizer import normalize_unicode_text


def main():
    sheet_id = "1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI"
    sheets_source = GoogleSheetsSource()

    rows = sheets_source.fetch_values(
        SheetsFetchConfig(sheet_id=sheet_id, worksheet="BC NGÀY", range_a1=None)
    )
    print(f"Total rows: {len(rows)}")

    # Row 0 as header
    header_row = rows[0]
    print(f"\n=== Row 0 (header) - normalized ===")
    header_norm = {}
    for i, h in enumerate(header_row):
        if h is not None:
            norm = normalize_unicode_text(str(h).strip())
            header_norm[norm] = i
            if i < 10:
                print(f"  col {i}: raw={repr(h)} -> norm={repr(norm)}")

    # Load schema and check aliases
    mapping = _load_custom_mapping("/app/app/domain/templates/bc_ngay_kv30_schema.yaml")

    print(f"\n=== Schema nghiep_vu aliases vs actual headers ===")
    nghiep_vu = mapping.get("nghiep_vu", {})

    for field_name, spec in nghiep_vu.items():
        if field_name in ('stt_map', 'fields'):
            continue
        if isinstance(spec, dict):
            aliases = spec.get('aliases', [])
        else:
            aliases = spec if isinstance(spec, list) else []
        for alias in aliases:
            norm_alias = normalize_unicode_text(str(alias))
            if norm_alias in header_norm:
                col = header_norm[norm_alias]
                print(f"  MATCH: field={field_name} alias={repr(alias)} norm={repr(norm_alias)} -> col={col}")
                break
        else:
            if aliases:
                print(f"  NO MATCH: field={field_name} aliases={[repr(a) for a in aliases[:2]]}")

    # Now build row_dict for a data row
    print(f"\n=== Building row_dict for row 32 ===")
    row = rows[32]
    row_dict = {}
    for col_idx in range(len(header_row)):
        if col_idx >= len(row):
            continue
        h = header_row[col_idx]
        if h is not None:
            header_name = str(h).strip()
            key = normalize_unicode_text(header_name)
            row_dict[key] = row[col_idx]

    print(f"row_dict keys[:10]={list(row_dict.keys())[:10]}")
    print(f"row_dict[0:3]={dict(list(row_dict.items())[:3])}")

    # Check if schema aliases match
    print(f"\n=== Checking matches ===")
    for field_name, spec in nghiep_vu.items():
        if field_name in ('stt_map', 'fields'):
            continue
        if isinstance(spec, dict):
            aliases = spec.get('aliases', [])
        else:
            aliases = spec if isinstance(spec, list) else []
        for alias in aliases:
            norm_alias = normalize_unicode_text(str(alias))
            if norm_alias in row_dict:
                val = row_dict[norm_alias]
                print(f"  field={field_name} alias={repr(alias)} -> val={val}")
                break


if __name__ == "__main__":
    main()
