from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    SheetExtractionPipeline, _normalize_key, _resolve_field_value,
    _load_custom_mapping, _extract_core
)
from app.engines.extraction.mapping.schema_loader import load_schema

schema_path = '/app/app/domain/templates/cnch_schema.yaml'
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

custom_mapping = _load_custom_mapping(schema_path)
schema = load_schema(schema_path)
field_types = {f.name: f.field_type for f in schema.fields}
print('field_types:', field_types)

core = _extract_core(sheet_data)
core_norm = {_normalize_key(k): v for k, v in core.items()}
print('core_norm:', core_norm)

cnch_spec = custom_mapping['danh_sach_cnch']
field_map = cnch_spec.get('fields', cnch_spec)

from app.engines.extraction.sheet_pipeline import _coerce_value
for field_name, aliases in field_map.items():
    if field_name in ('stt_map', 'fields'):
        continue
    aliases_list = aliases if isinstance(aliases, list) else []
    val = _resolve_field_value(core_norm, aliases_list)
    ft = field_types.get(field_name, 'string')
    coerced = _coerce_value(val, ft)
    print(f'  field={field_name!r} val={val!r} ft={ft!r} coerced={coerced!r}')
