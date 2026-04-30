"""Debug builder CNCH merge."""
from types import SimpleNamespace
from app.engines.extraction.schemas import BlockExtractionOutput, BlockHeader, BlockNghiepVu, TuyenTruyenOnline
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline, _normalize_key
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data

cnch_path = '/app/app/domain/templates/cnch_schema.yaml'
worksheet_configs = [{'worksheet': 'CNCH', 'schema_path': cnch_path, 'target_section': 'danh_sach_cnch'}]
sheet_data = {'CNCH': [
    ['STT', 'Ngày xảy ra sự cố', 'Thời gian đến', 'Địa điểm', 'Loại hình CNCH', 'Thiệt hại về người', 'Số người cứu được'],
    [1, '01/04/2026', '10:00', 'TP', 'Loại A', 0, 2],
    [2, '05/04/2026', '14:30', 'Phường 3', 'Cứu hộ', 0, 1],
]}
template = SimpleNamespace(google_sheet_configs=worksheet_configs)

# Instantiate builder but don't call build() — trace manually
from app.engines.extraction.daily_report_builder import DailyReportBuilder

# Monkey-patch _process_worksheet_with_schema to add debug
original_process = DailyReportBuilder._process_worksheet_with_schema

def debug_process(self, report, worksheet, schema_path, cfg):
    print(f"[DEBUG] Processing worksheet={worksheet}, schema_path={schema_path}")
    print(f"[DEBUG] target_section={cfg.get('target_section')}")

    # Manually do what the builder does
    rows = self.sheet_data.get(worksheet, [])
    print(f"[DEBUG] rows count: {len(rows)}")
    if not rows:
        print("[DEBUG] No rows, returning")
        return

    schema = load_schema(schema_path)
    pipeline = SheetExtractionPipeline()
    header_row = rows[0]
    print(f"[DEBUG] header: {header_row}")

    for row_idx, row in enumerate(rows[1:], start=1):
        row_dict = {str(h).strip(): v for h, v in zip(header_row, row)}
        normalized_row = {_normalize_key(k): v for k, v in row_dict.items()}
        doc_data, m, t, miss = map_row_to_document_data(normalized_row, schema)
        print(f"[DEBUG] Row {row_idx}: matched={m}/{t}")

        result = pipeline.run({'data': doc_data}, schema_path=schema_path)
        print(f"[DEBUG] Row {row_idx}: pipeline status={result.status}, errors={result.errors}")
        if result.output:
            cnch = result.output.danh_sach_cnch
            print(f"[DEBUG] Row {row_idx}: pipeline cnch items = {cnch}")
            print(f"[DEBUG] hasattr(report, 'danh_sach_cnch') = {hasattr(report, 'danh_sach_cnch')}")
            print(f"[DEBUG] report.danh_sach_cnch before merge: {report.danh_sach_cnch}")

            target = cfg.get('target_section')
            if target:
                self._merge_section(report, result.output, target)
                print(f"[DEBUG] After merge: report.danh_sach_cnch = {report.danh_sach_cnch}")

DailyReportBuilder._process_worksheet_with_schema = debug_process

builder = DailyReportBuilder(template=template, sheet_data=sheet_data, worksheet_configs=worksheet_configs)
report = builder.build()
print(f"\nFinal: report.danh_sach_cnch = {report.danh_sach_cnch}")
