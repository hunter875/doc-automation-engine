from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    SheetExtractionPipeline, _normalize_key, _resolve_field_value,
    _load_custom_mapping, _extract_core
)

# Simulate what the builder does
sheet_data = {
    'data': {
        'stt': 1,
        'ngay_xay_ra': '01/04/2026',
        'thoi_gian': '10:00',
        'dia_diem': 'TP',
        'loai_hinh': 'Loai A',
        'thiet_hai': 0,
        'so_nguoi': 2
    }
}
pipeline = SheetExtractionPipeline()

schema_path = '/app/app/domain/templates/cnch_schema.yaml'
custom_mapping = _load_custom_mapping(schema_path)
sm_keys = list(custom_mapping.get('sheet_mapping', custom_mapping).keys())
print('custom_mapping keys:', sm_keys)

# Get the core dict from sheet_data
core = _extract_core(sheet_data)
print('core:', core)

# Check what _normalize_key does to column names
print('_normalize_key("Ngay xay ra"):', repr(_normalize_key('Ngay xay ra')))
print('_normalize_key("thoi_gian"):', repr(_normalize_key('thoi_gian')))

# Test _resolve_field_value
core_norm = {_normalize_key(k): v for k, v in core.items()}
print('core_norm:', core_norm)

# Test resolving for ngay_xay_ra
aliases = ['Ngày xảy ra sự cố', 'ngay_xay_ra']
print('aliases for ngay_xay_ra:', aliases)
result = _resolve_field_value(core_norm, aliases)
print('_resolve_field_value result:', result)

# Now run the pipeline
result2 = pipeline.run(sheet_data, schema_path=schema_path)
print('pipeline status:', result2.status)
print('pipeline errors:', result2.errors)
if result2.output:
    print('danh_sach_cnch:', result2.output.danh_sach_cnch)
