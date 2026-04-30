UPDATE extraction_templates SET google_sheet_configs = '[
  {"mode": null, "range": "A1:ZZZ", "worksheet": "BC NGÀY", "schema_path": "/app/app/domain/templates/bc_ngay_kv30_schema.yaml"},
  {"mode": null, "range": "A1:ZZZ", "worksheet": "CNCH", "schema_path": "/app/app/domain/templates/cnch_kv30_schema.yaml"},
  {"mode": null, "range": "A1:ZZZ", "worksheet": "CHI VIỆN", "schema_path": "/app/app/domain/templates/chi_vien_kv30_schema.yaml"},
  {"mode": null, "range": "A1:ZZZ", "worksheet": "VỤ CHÁY THỐNG KÊ", "schema_path": "/app/app/domain/templates/vu_chay_kv30_schema.yaml"}
]' WHERE id = 'fac74812-ce47-4fb0-b458-7f9ff3a9aa6b';
