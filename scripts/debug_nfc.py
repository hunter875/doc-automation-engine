"""Debug remaining 2 issues."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

import unicodedata
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.sheet_pipeline import (
    _normalize_key, _resolve_field_value, _load_custom_mapping, _build_output_custom
)

# === Issue 1: ngay_bao_cao in BC_NGAY header ===
print('=== Issue 1: ngay_bao_cao ===')
schema = load_schema('/app/app/domain/templates/bc_ngay_schema.yaml')
for f in schema.fields:
    if f.name == 'ngay_bao_cao_day':
        print(f'ngay_bao_cao_day aliases: {f.aliases}')
        for a in f.aliases:
            print(f'  {a!r} NFC={unicodedata.is_normalized("NFC", a)}')

bc_mapping = _load_custom_mapping('/app/app/domain/templates/bc_ngay_schema.yaml')
bc_core = {
    'ngay_bao_cao_day': '1',
    'ngay_bao_cao_month': '4',
    'thoi_gian_tu_den': '01/04/2026 - 20/04/2026',
    'don_vi_bao_cao': 'Đội PCCC'
}

# Simulate what happens: normalize core keys
bc_core_norm = {_normalize_key(k): v for k, v in bc_core.items()}
print(f'bc_core_norm keys: {list(bc_core_norm.keys())}')

# Try resolving ngay
header_spec = bc_mapping.get('header', {})
day_spec = header_spec.get('ngay_bao_cao_day', {})
aliases = day_spec.get('aliases', day_spec) if isinstance(day_spec, dict) else day_spec
print(f'Aliases for ngay_bao_cao_day: {aliases}')
print(f'_normalize_key aliases:')
for a in aliases:
    print(f'  {a!r} -> {_normalize_key(a)!r}')
print(f'bc_core_norm keys: {list(bc_core_norm.keys())}')
result = _resolve_field_value(bc_core_norm, aliases)
print(f'_resolve_field_value result: {result!r}')

# Full build test
try:
    output = _build_output_custom(bc_core, bc_mapping, schema_path='/app/app/domain/templates/bc_ngay_schema.yaml')
    print(f'output.header.ngay_bao_cao: {output.header.ngay_bao_cao!r}')
except Exception as e:
    print(f'FAILED: {e}')

# === Issue 2: khu_vuc_quan_ly in CHI_VIEN ===
print('\n=== Issue 2: khu_vuc_quan_ly ===')
schema2 = load_schema('/app/app/domain/templates/chi_vien_schema.yaml')
for f in schema2.fields:
    if f.name == 'khu_vuc_quan_ly':
        print(f'khu_vuc_quan_ly aliases: {f.aliases}')
        for a in f.aliases:
            print(f'  {a!r} NFC={unicodedata.is_normalized("NFC", a)}')

cv_mapping = _load_custom_mapping('/app/app/domain/templates/chi_vien_schema.yaml')
cv_core = {
    'stt': 1,
    'ngay': '03/04/2026',
    'dia_diem': 'Quận 5',
    'khu_vuc_quan_ly': 'KV-5',
    'so_luong_xe': 3,
}

cv_core_norm = {_normalize_key(k): v for k, v in cv_core.items()}
print(f'cv_core_norm keys: {list(cv_core_norm.keys())}')

field_map = cv_mapping['danh_sach_chi_vien']['fields']
aliases2 = field_map.get('khu_vuc_quan_ly', [])
print(f'Aliases for khu_vuc_quan_ly: {aliases2}')
print(f'_normalize_key aliases:')
for a in aliases2:
    print(f'  {a!r} -> {_normalize_key(a)!r}')

result2 = _resolve_field_value(cv_core_norm, aliases2)
print(f'_resolve_field_value result: {result2!r}')

try:
    output2 = _build_output_custom(cv_core, cv_mapping, schema_path='/app/app/domain/templates/chi_vien_schema.yaml')
    print(f'chi_vien[0].khu_vuc_quan_ly: {output2.danh_sach_chi_vien[0].khu_vuc_quan_ly!r}')
except Exception as e:
    print(f'FAILED: {e}')
