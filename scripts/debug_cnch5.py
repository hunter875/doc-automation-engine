from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    SheetExtractionPipeline, _normalize_key, _resolve_field_value,
    _load_custom_mapping, _extract_core, _build_output_custom
)

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
custom_mapping = _load_custom_mapping(schema_path)
core = _extract_core(sheet_data)

# Debug: trace each field in the CNCH section
from app.engines.extraction.schemas import CNCHItem
import traceback

sheet_mapping = custom_mapping.get('sheet_mapping', custom_mapping)
fields_spec = sheet_mapping['danh_sach_cnch']
if isinstance(fields_spec, dict) and 'fields' in fields_spec:
    field_map = fields_spec['fields']
else:
    field_map = fields_spec

core_norm = {_normalize_key(k): v for k, v in core.items()}
print('core_norm keys:', list(core_norm.keys()))

item_dict = {}
for field_name, aliases_raw in field_map.items():
    if field_name in ('stt_map', 'fields'):
        continue
    aliases = aliases_raw if isinstance(aliases_raw, list) else []
    val = _resolve_field_value(core_norm, aliases)
    print(f'  field={field_name!r} aliases={aliases} val={val!r}')
    if val is not None:
        item_dict[field_name] = val

print('item_dict:', item_dict)
try:
    cnch_items = [CNCHItem(**item_dict)]
    print('CNCHItem created OK:', cnch_items)
except Exception as e:
    print('CNCHItem FAILED:', e)
    traceback.print_exc()
