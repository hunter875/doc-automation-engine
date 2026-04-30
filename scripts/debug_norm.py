"""Debug mapper vs builder normalization mismatch."""
import sys
sys.path.insert(0, '/app')

from app.engines.extraction.mapping.schema_loader import load_schema, _normalize_aliases
from app.engines.extraction.daily_report_builder import _normalize_key

SCHEMA_PATH = "/app/app/domain/templates/bc_ngay_schema.yaml"

def main():
    print("=== Schema fields and aliases ===")
    schema = load_schema(SCHEMA_PATH)
    for field in schema.fields:
        print(f"\n  Field: {field.name}")
        print(f"    aliases: {field.aliases}")
        for alias in field.aliases:
            norm = _normalize_aliases([alias], alias)[0]
            print(f"      '{alias}' -> '{norm}'")
    
    print("\n=== Testing header matching ===")
    # Test header "NGÀY"
    header = "NGÀY"
    header_norm = _normalize_key(header)
    print(f"  Header '{header}' -> builder norm: '{header_norm}'")
    
    # Check if it matches any alias
    for field in schema.fields:
        for alias in field.aliases:
            alias_norm = _normalize_aliases([alias], alias)[0]
            if header_norm == alias_norm:
                print(f"  MATCH: '{header_norm}' == '{alias_norm}' (field: {field.name})")
    
    # What the mapper sees
    print("\n=== What mapper sees ===")
    from app.engines.extraction.mapping.mapper import _normalize_key as mapper_norm
    print(f"  Header '{header}' -> mapper norm: '{mapper_norm(header)}'")
    
    # Compare
    print("\n=== COMPARISON ===")
    print(f"  Builder norm:  '{_normalize_key(header)}'")
    print(f"  Mapper norm:   '{mapper_norm(header)}'")
    print(f"  Match: {header_norm == mapper_norm(header)}")

if __name__ == "__main__":
    main()
