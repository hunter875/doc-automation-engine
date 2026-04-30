"""Exactly reproduce CHECKPOINT E/F to find where so_bao_cao also fails."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    _normalize_key, _resolve_field_value, _load_custom_mapping, _extract_core,
    _build_output_custom_header,
)
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data

SCHEMA = "/app/app/domain/templates/bc_ngay_schema.yaml"
schema = load_schema(SCHEMA)
mapping = _load_custom_mapping(SCHEMA)

# Simulate full doc_data (snake_case field names → None/values)
doc_data = {
    'ngay_bao_cao_day': '1',
    'ngay_bao_cao_month': '4',
    'so_bao_cao': 'BC-01',
    'thoi_gian_tu_den': '01/04/2026 - 20/04/2026',
    'don_vi_bao_cao': 'Đội PCCC',
}

core = _extract_core({"data": doc_data})
core_norm = {_normalize_key(k): v for k, v in core.items()}

# Check what each alias normalizes to vs what keys exist
header_spec = mapping.get("header", {})

def check_field(field_name):
    spec = header_spec.get(field_name, {})
    aliases = spec.get("aliases", spec) if isinstance(spec, dict) else spec
    print(f"\n--- {field_name} ---")
    print(f"  aliases: {aliases}")
    for a in aliases:
        lookup = _normalize_key(a)
        in_core = lookup in core_norm
        print(f"  '{a}' -> normalize_key='{lookup}' -> in core_norm: {in_core}")
    result = _resolve_field_value(core_norm, aliases)
    print(f"  _resolve_field_value => {result!r}")

check_field("ngay_bao_cao_day")
check_field("ngay_bao_cao_month")
check_field("so_bao_cao")
check_field("thoi_gian_tu_den")
check_field("don_vi_bao_cao")

print("\n=== _build_output_custom_header ===")
header = _build_output_custom_header(core, mapping)
print(f"header.ngay_bao_cao = {header.ngay_bao_cao!r}")
print(f"header.so_bao_cao  = {header.so_bao_cao!r}")
print(f"header.thoi_gian_tu_den = {header.thoi_gian_tu_den!r}")
print(f"header.don_vi_bao_cao = {header.don_vi_bao_cao!r}")
