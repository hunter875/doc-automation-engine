"""Debug ngay_bao_cao building."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    _normalize_key, _resolve_field_value, _load_custom_mapping, _build_output_custom_header, _build_output_custom
)

bc_mapping = _load_custom_mapping('/app/app/domain/templates/bc_ngay_schema.yaml')

# Simulate core from map_row_to_document_data
bc_core = {
    'ngay_bao_cao_day': '1',
    'ngay_bao_cao_month': '4',
    'thoi_gian_tu_den': '01/04/2026 - 20/04/2026',
    'don_vi_bao_cao': 'Đội PCCC'
}

print('=== _build_output_custom_header ===')
header = _build_output_custom_header(bc_core, bc_mapping)
print(f'ngay_bao_cao: {header.ngay_bao_cao!r}')
print(f'so_bao_cao: {header.so_bao_cao!r}')
print(f'don_vi_bao_cao: {header.don_vi_bao_cao!r}')

print('\n=== Full _build_output_custom ===')
try:
    output = _build_output_custom(bc_core, bc_mapping, schema_path='/app/app/domain/templates/bc_ngay_schema.yaml')
    print(f'output.header.ngay_bao_cao: {output.header.ngay_bao_cao!r}')
except Exception as e:
    print(f'FAILED: {e}')

# Also test with actual doc_data format (from map_row_to_document_data)
print('\n=== With snake_case doc_data keys ===')
bc_core2 = {
    'ngay_bao_cao_day': '1',
    'ngay_bao_cao_month': '4',
}
output2 = _build_output_custom(bc_core2, bc_mapping, schema_path='/app/app/domain/templates/bc_ngay_schema.yaml')
print(f'output2.header.ngay_bao_cao: {output2.header.ngay_bao_cao!r}')

# Check what _extract_core does with snake_case keys
from app.engines.extraction.sheet_pipeline import _extract_core
test_data = {'data': bc_core2}
extracted = _extract_core(test_data)
print(f'_extract_core result: {extracted}')
