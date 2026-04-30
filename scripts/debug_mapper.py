"""Debug mapper step by step."""
import sys
sys.path.insert(0, '/app')

import openpyxl
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data
from app.engines.extraction.mapping.normalizer import normalize_unicode_text

EXCEL_PATH = "/app/1.xlsx"
SCHEMA_PATH = "/app/app/domain/templates/bc_ngay_schema.yaml"

def main():
    # Read BC NGÀY
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb["BC NGÀY"]
    rows = list(ws.iter_rows(values_only=True))
    
    header_row = rows[0]
    data_row = rows[3]  # Row 3 (index) = row 4 in Excel = Day 1, Month 3
    
    print(f"Header row (first 5): {header_row[:5]}")
    print(f"Data row (first 5): {data_row[:5]}")
    
    # Build row_dict like builder does
    row_dict = {}
    for col_idx, header_val in enumerate(header_row):
        if col_idx < len(data_row):
            row_dict[str(header_val).strip()] = data_row[col_idx]
    
    print(f"\nRow dict (first 5):")
    for i, (k, v) in enumerate(row_dict.items()):
        if i < 5:
            print(f"  '{k}': {v}")
    
    # Load schema
    schema = load_schema(SCHEMA_PATH)
    print(f"\nSchema has {len(schema.fields)} fields")
    
    # Test normalization of key
    print(f"\nNormalize key test:")
    print(f"  'NGÀY' -> '{normalize_unicode_text('NGÀY')}'")
    
    # Try map_row_to_document_data
    doc_data, matched, total, missing = map_row_to_document_data(row_dict, schema)
    
    print(f"\nMapping result:")
    print(f"  matched_fields: {matched}/{total}")
    print(f"  missing_required: {missing}")
    
    print(f"\nDoc data keys: {list(doc_data.keys())[:10]}")
    
    # Check specific fields
    for field in ['ngay_bao_cao_day', 'ngay_bao_cao_month', 'tong_so_vu_chay', 'tong_so_vu_cnch']:
        if field in doc_data:
            print(f"  {field}: {doc_data[field]}")
        else:
            print(f"  {field}: NOT IN DOC_DATA")

if __name__ == "__main__":
    main()
