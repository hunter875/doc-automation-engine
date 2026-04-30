"""Debug builder CNCH merge - full."""
from types import SimpleNamespace
from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.schemas import BlockExtractionOutput

cnch_path = '/app/app/domain/templates/cnch_schema.yaml'
worksheet_configs = [{'worksheet': 'CNCH', 'schema_path': cnch_path, 'target_section': 'danh_sach_cnch'}]
sheet_data = {'CNCH': [
    ['STT', 'Ngày xảy ra sự cố', 'Thời gian đến', 'Địa điểm', 'Loại hình CNCH', 'Thiệt hại về người', 'Số người cứu được'],
    [1, '01/04/2026', '10:00', 'TP', 'Loại A', 0, 2],
    [2, '05/04/2026', '14:30', 'Phường 3', 'Cứu hộ', 0, 1],
]}
template = SimpleNamespace(google_sheet_configs=worksheet_configs)

print("Instantiating builder...")
builder = DailyReportBuilder(template=template, sheet_data=sheet_data, worksheet_configs=worksheet_configs)
print("Calling build()...")
report = builder.build()
print(f"After build: report.danh_sach_cnch = {report.danh_sach_cnch}")
print(f"report.danh_sach_cnch count: {len(report.danh_sach_cnch)}")
