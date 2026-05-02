-- KV30 worksheet config theo spec Phase 1
-- BC NGÀY: header_row=0 (merged group header), data_start_row=3
-- Detail sheets: header_row=1, data_start_row=2
-- Thêm SCLQ worksheet

UPDATE extraction_templates
SET google_sheet_configs = $json$
[
  {
    "worksheet": "BC NGÀY",
    "schema_path": "bc_ngay_kv30_schema.yaml",
    "range": "A1:AH64",
    "role": "master",
    "header_row": 0,
    "data_start_row": 3,
    "target_section": null
  },
  {
    "worksheet": "CNCH",
    "schema_path": "cnch_kv30_schema.yaml",
    "range": "A1:I11",
    "role": "detail",
    "header_row": 1,
    "data_start_row": 2,
    "target_section": "danh_sach_cnch"
  },
  {
    "worksheet": "VỤ CHÁY THỐNG KÊ",
    "schema_path": "vu_chay_kv30_schema.yaml",
    "range": "A1:P7",
    "role": "detail",
    "header_row": 1,
    "data_start_row": 2,
    "target_section": "danh_sach_chay"
  },
  {
    "worksheet": "CHI VIỆN",
    "schema_path": "chi_vien_kv30_schema.yaml",
    "range": "A1:I8",
    "role": "detail",
    "header_row": 1,
    "data_start_row": 2,
    "target_section": "danh_sach_chi_vien"
  },
  {
    "worksheet": "SCLQ ĐẾN PCCC&CNCH",
    "schema_path": "sclq_kv30_schema.yaml",
    "range": "A1:H98",
    "role": "detail",
    "header_row": 1,
    "data_start_row": 2,
    "target_section": "danh_sach_sclq"
  }
]
$json$::jsonb
WHERE id = 'b4f44dd1-66c0-4a6f-b036-4044139ad54e';
