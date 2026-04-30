"""Trace thiet_hai alias matching in detail."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    _normalize_key, _resolve_field_value, _load_custom_mapping, _extract_core
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

schema_path = '/app/app/domain/templates/cnch_schema.yaml'

# Load the raw YAML
custom_mapping = _load_custom_mapping(schema_path)

# Get CNCH field spec
cnch_spec = custom_mapping['danh_sach_cnch']
field_map = cnch_spec.get('fields', cnch_spec)
print('field_map for thiet_hai:', field_map.get('thiet_hai'))

# Get the core dict
core = _extract_core(sheet_data)
core_norm = {_normalize_key(k): v for k, v in core.items()}
print('core_norm:', core_norm)

# Try resolving thiet_hai
aliases = field_map['thiet_hai']
print('aliases for thiet_hai:', aliases)
result = _resolve_field_value(core_norm, aliases)
print('_resolve_field_value result:', result)

# Also check what _normalize_key does to each alias
for alias in aliases:
    norm = _normalize_key(alias)
    print(f'  _normalize_key({alias!r}) = {norm!r}')
    print(f'    in core_norm: {norm in core_norm}')
