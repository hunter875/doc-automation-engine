"""Debug CNCH thiet_hai via patched _build_output_custom in container."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

import types
from app.engines.extraction.sheet_pipeline import (
    SheetExtractionPipeline, _normalize_key, _resolve_field_value,
    _load_custom_mapping, _extract_core, _build_output_custom
)

# Patch _build_output_custom to add debug prints
orig = _build_output_custom

def patched(core, mapping, schema_path=""):
    from app.engines.extraction.schemas import CNCHItem

    sheet_mapping = mapping.get("sheet_mapping", mapping)
    field_types = {}
    try:
        from app.engines.extraction.mapping.schema_loader import load_schema
        schema = load_schema(schema_path)
        field_types = {f.name: f.field_type for f in schema.fields}
        print(f'[PATCHED] field_types: {field_types}')
    except Exception as e:
        print(f'[PATCHED] load_schema failed: {e}')

    cnch_spec = sheet_mapping.get("danh_sach_cnch")
    if cnch_spec:
        field_map = cnch_spec.get("fields", cnch_spec)
        core_norm = {_normalize_key(k): v for k, v in core.items()}
        print(f'[PATCHED] core_norm: {core_norm}')

        for field_name, aliases_raw in field_map.items():
            if field_name in ("stt_map", "fields"):
                continue
            aliases = aliases_raw if isinstance(aliases_raw, list) else []
            val = _resolve_field_value(core_norm, aliases)
            print(f'[PATCHED] field={field_name!r} aliases={aliases} val={val!r}')

            if val is not None:
                ft = field_types.get(field_name, "string")
                print(f'[PATCHED]   field_type={ft!r}')
                from app.engines.extraction.sheet_pipeline import _coerce_value
                coerced = _coerce_value(val, ft)
                print(f'[PATCHED]   coerced={coerced!r}')

    return orig(core, mapping, schema_path)

import app.engines.extraction.sheet_pipeline as sp
sp._build_output_custom = patched

# Now run the full pipeline
pipeline = SheetExtractionPipeline()
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
result = pipeline.run(sheet_data, schema_path=schema_path)
print('status:', result.status)
print('errors:', result.errors)
if result.output:
    print('danh_sach_cnch:', result.output.danh_sach_cnch)
