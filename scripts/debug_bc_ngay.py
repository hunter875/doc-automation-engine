"""Debug builder processing BC_NGAY worksheet."""
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

# Create empty report using the builder's internal method
report = builder._create_empty_report()

# Call processor
cfg = worksheet_configs[0]
print('Processing worksheet:', cfg['worksheet'])
print('sheet_data keys:', list(builder.sheet_data.keys()))
print('cfg worksheet:', repr(cfg['worksheet']))
print('sheet_data[cfg[worksheet]]:', builder.sheet_data.get(cfg['worksheet']))

builder._process_worksheet_with_schema(report, cfg['worksheet'], cfg['schema_path'], cfg)
print('After processing:')
print('  header.ngay_bao_cao:', repr(report.header.ngay_bao_cao))
print('  header.so_bao_cao:', repr(report.header.so_bao_cao))
print('  header.don_vi_bao_cao:', repr(report.header.don_vi_bao_cao))
