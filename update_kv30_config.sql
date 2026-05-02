UPDATE extraction_templates
SET google_sheet_configs = $json$
[
  {"worksheet": "BC NGÀY", "schema_path": "bc_ngay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "target_section": "phan_I_va_II_chi_tiet_nghiep_vu"},
  {"worksheet": "CNCH", "schema_path": "cnch_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "target_section": "danh_sach_cnch"},
  {"worksheet": "CHI VIỆN", "schema_path": "chi_vien_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "target_section": "danh_sach_chi_vien"},
  {"worksheet": "VỤ CHÁY THỐNG KÊ", "schema_path": "vu_chay_kv30_schema.yaml", "range": "A1:ZZZ", "header_row": 1, "data_start_row": 2, "target_section": "danh_sach_chay"}
]
$json$::jsonb
WHERE id = 'b4f44dd1-66c0-4a6f-b036-4044139ad54e';
