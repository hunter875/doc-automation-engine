"""Debug BC NGÀY schema and column detection."""
import sys
sys.path.insert(0, '/app')

import openpyxl
import yaml
from pathlib import Path

EXCEL_PATH = "/app/1.xlsx"
SCHEMA_PATH = "/app/app/domain/templates/bc_ngay_schema.yaml"

def _normalize_key(value: str) -> str:
    """Normalize a key for space-separated matching with diacritics removal."""
    import unicodedata
    import re
    t = unicodedata.normalize("NFC", str(value or "")).strip().lower()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[_\s]+", " ", t).strip()

def load_schema(schema_path: str) -> dict:
    """Load YAML schema."""
    path = Path(schema_path)
    if not path.exists():
        print(f"Schema file not found: {schema_path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main():
    # Load schema
    schema = load_schema(SCHEMA_PATH)
    print(f"Schema loaded: {SCHEMA_PATH}")
    print(f"Schema keys: {list(schema.keys())}")
    
    # Read BC NGÀY
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb["BC NGÀY"]
    rows = list(ws.iter_rows(values_only=True))
    
    print(f"\nTotal rows: {len(rows)}")
    header_row = rows[0]
    
    # Build header_norm map
    header_norm = {}
    for idx, h in enumerate(header_row):
        if h is not None:
            norm = _normalize_key(str(h))
            header_norm[norm] = idx
    
    print(f"\n=== Normalized header map ===")
    for k, v in sorted(header_norm.items()):
        print(f"  '{k}': {v}")
    
    # Check what schema expects
    sheet_mapping = schema.get("sheet_mapping", {})
    header_spec = sheet_mapping.get("header", {})
    
    print(f"\n=== Schema expects ===")
    day_col = -1
    month_col = -1
    for field_name, spec in header_spec.items():
        aliases = []
        if isinstance(spec, dict):
            aliases = spec.get("aliases", [])
        print(f"  {field_name}: aliases={aliases}")
        
        # Check if any alias matches
        found = False
        for alias in aliases + [field_name]:
            norm = _normalize_key(str(alias))
            if norm in header_norm:
                print(f"    -> MATCHES col {header_norm[norm]}")
                if field_name == "ngay_bao_cao_day":
                    day_col = header_norm[norm]
                elif field_name == "ngay_bao_cao_month":
                    month_col = header_norm[norm]
                found = True
                break
        if not found:
            print(f"    -> NO MATCH")
    
    print(f"\n=== Date columns detected ===")
    print(f"  day_col = {day_col}")
    print(f"  month_col = {month_col}")
    
    # Check sample data
    print(f"\n=== Sample data (rows 3-6) ===")
    for i in range(3, min(7, len(rows))):
        row = rows[i]
        day_val = row[day_col] if day_col >= 0 and day_col < len(row) else "N/A"
        month_val = row[month_col] if month_col >= 0 and month_col < len(row) else "N/A"
        print(f"Row {i}: day={day_val}, month={month_val}")

if __name__ == "__main__":
    main()
