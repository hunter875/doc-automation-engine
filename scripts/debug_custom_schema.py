#!/usr/bin/env python3
"""Debug custom schema loading."""
import sys
sys.path.insert(0, '/app')

from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline, _load_custom_mapping, _build_output_custom_header

# Create test schema
schema_content = """sheet_mapping:
  header:
    fields:
      so_bao_cao: [so_bao_cao]
"""

import tempfile
import os

with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    f.write(schema_content)
    schema_path = f.name

try:
    # Load custom mapping
    mapping = _load_custom_mapping(schema_path)
    print("Loaded mapping:", mapping)
    print("Type:", type(mapping))
    print("Keys:", mapping.keys() if isinstance(mapping, dict) else "N/A")

    if isinstance(mapping, dict):
        sheet_mapping = mapping.get("sheet_mapping")
        print("sheet_mapping:", sheet_mapping)
        if sheet_mapping:
            header_spec = sheet_mapping.get("header")
            print("header spec:", header_spec)

    # Test header building
    core = {"so_bao_cao": "01/BC"}
    header = _build_output_custom_header(core, mapping)
    print("\nBuilt header:", header)
    print("so_bao_cao:", header.so_bao_cao if hasattr(header, 'so_bao_cao') else "N/A")

finally:
    os.unlink(schema_path)
