"""Debug remaining 2 failures: header ngay_bao_cao and chi_vien khu_vuc."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.sheet_pipeline import (
    _normalize_key, _resolve_field_value, _load_custom_mapping, _extract_core,
    _build_output_custom_header, _build_output_custom
)

# === Test 1: BC_NGAY header ===
print('=== BC_NGAY Header ===')
bc_schema = '/app/app/domain/templates/bc_ngay_schema.yaml'
bc_mapping = _load_custom_mapping(bc_schema)
bc_core = {'ngay_bao_cao_day': '1', 'ngay_bao_cao_month': '4', 'thoi_gian_tu_den': '01/04/2026 - 20/04/2026', 'don_vi_bao_cao': 'Đội PCCC'}
bc_header = _build_output_custom_header(bc_core, bc_mapping)
print(f'ngay_bao_cao: {bc_header.ngay_bao_cao!r}')
print(f'so_bao_cao: {bc_header.so_bao_cao!r}')

# Full build
try:
    output = _build_output_custom(bc_core, bc_mapping, schema_path=bc_schema)
    print(f'full output.header.ngay_bao_cao: {output.header.ngay_bao_cao!r}')
except Exception as e:
    print(f'full build FAILED: {e}')

# === Test 2: CHI_VIEN khu_vuc_quan_ly ===
print('\n=== CHI_VIEN khu_vuc_quan_ly ===')
cv_schema = '/app/app/domain/templates/chi_vien_schema.yaml'
cv_mapping = _load_custom_mapping(cv_schema)
print(f'chi_vien field_map: {cv_mapping.get("danh_sach_chi_vien")}')

# doc_data from map_row_to_document_data
cv_doc_data = {
    'stt': 1,
    'ngay': '03/04/2026',
    'dia_diem': 'Quận 5',
    'khu_vuc_quan_ly': 'KV-5',
    'so_luong_xe': 3,
    'thoi_gian_di': '08:00',
    'thoi_gian_ve': '10:30',
    'chi_huy': 'Thiếu tá B',
    'ghi_chu': 'Chi viện chữa cháy'
}

cv_core = _extract_core({'data': cv_doc_data})
print(f'cv_core: {cv_core}')
cv_core_norm = {_normalize_key(k): v for k, v in cv_core.items()}
print(f'cv_core_norm: {cv_core_norm}')

# Test resolving khu_vuc_quan_ly
field_map = cv_mapping['danh_sach_chi_vien']['fields']
aliases = field_map['khu_vuc_quan_ly']
print(f'khu_vuc aliases: {aliases}')
result = _resolve_field_value(cv_core_norm, aliases)
print(f'_resolve_field_value result: {result!r}')

# Full build
try:
    output = _build_output_custom(cv_core, cv_mapping, schema_path=cv_schema)
    print(f'chi_vien[0]: {output.danh_sach_chi_vien}')
    if output.danh_sach_chi_vien:
        print(f'khu_vuc_quan_ly: {output.danh_sach_chi_vien[0].khu_vuc_quan_ly!r}')
except Exception as e:
    print(f'full build FAILED: {e}')
