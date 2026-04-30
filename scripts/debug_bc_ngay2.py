"""Debug builder BC_NGAY row processing."""
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

import types
from app.engines.extraction.daily_report_builder import DailyReportBuilder

worksheet_configs = [
    {
        "worksheet": "BC NGÀY",
        "schema_path": "/app/app/domain/templates/bc_ngay_schema.yaml",
        "target_section": "header",
    },
]

sheet_data = {
    "BC NGÀY": [
        ["ngày", "tháng", "Số báo cáo", "thời gian từ đến", "đơn vị báo cáo"],
        [1, 4, "BC-01", "01/04/2026 - 20/04/2026", "Đội PCCC&CNCH Quận 1"],
    ],
}

template = types.SimpleNamespace(google_sheet_configs=worksheet_configs)
builder = DailyReportBuilder(template=template, sheet_data=sheet_data, worksheet_configs=worksheet_configs)
report = builder._create_empty_report()

cfg = worksheet_configs[0]
worksheet = cfg['worksheet']
schema_path = cfg['schema_path']

from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data

rows = builder.sheet_data.get(worksheet, [])
header_row = rows[0]
print('header_row:', header_row)

row = rows[1]
print('data row:', row)

row_dict = {}
for col_idx, header_val in enumerate(header_row):
    if col_idx < len(row):
        row_dict[str(header_val).strip()] = row[col_idx]
print('row_dict:', row_dict)

try:
    ingestion_schema = load_schema(schema_path)
    print('schema fields:', [(f.name, f.aliases) for f in ingestion_schema.fields])
except Exception as e:
    print('load_schema failed:', e)

doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)
print('doc_data non-None:', {k: v for k, v in doc_data.items() if v is not None})
print('matched:', m, '/', t)
print('missing:', miss)

sheet_payload = {'data': doc_data}
pipeline_result = builder._pipeline.run(sheet_payload, schema_path=schema_path)
print('pipeline status:', pipeline_result.status)
print('pipeline errors:', pipeline_result.errors)
if pipeline_result.output:
    print('output.header:', pipeline_result.output.header)
