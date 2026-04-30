"""Debug builder CNCH merge - with prints inside builder."""
from types import SimpleNamespace
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline, _normalize_key
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data
from app.engines.extraction.validation.row_validator import build_validation_model, validate_row

cnch_path = '/app/app/domain/templates/cnch_schema.yaml'
worksheet_configs = [{'worksheet': 'CNCH', 'schema_path': cnch_path, 'target_section': 'danh_sach_cnch'}]
sheet_data = {'CNCH': [
    ['STT', 'Ngay xay ra', 'Thoi gian', 'Dia diem', 'Loai hinh', 'Thiet hai', 'So nguoi'],
    [1, '01/04/2026', '10:00', 'TP', 'Loai A', 0, 2],
    [2, '05/04/2026', '14:30', 'Phuong 3', 'Cuu ho', 0, 1],
]}
template = SimpleNamespace(google_sheet_configs=worksheet_configs)

# Monkey-patch to add prints
DailyReportBuilder._process_worksheet_with_schema

orig = DailyReportBuilder._process_worksheet_with_schema

def patched(self, report, worksheet, schema_path, cfg):
    print('[BUILD] worksheet=' + str(worksheet))
    rows = self.sheet_data.get(worksheet, [])
    print('[BUILD] rows=' + str(len(rows)))
    if not rows:
        print('[BUILD] No rows')
        return
    try:
        ingestion_schema = load_schema(schema_path)
        print('[BUILD] schema loaded: ' + str(len(ingestion_schema.fields)) + ' fields')
    except Exception as e:
        print('[BUILD] load_schema failed: ' + str(e))
        return
    try:
        validation_model = build_validation_model(ingestion_schema)
        print('[BUILD] validation_model created ok')
    except Exception as e:
        print('[BUILD] build_validation_model failed: ' + str(e))
        validation_model = None
    header_row = rows[0]
    print('[BUILD] header_row=' + str(header_row))
    for row_idx, row in enumerate(rows[1:], start=1):
        print('[BUILD] Processing row ' + str(row_idx))
        row_dict = {}
        for col_idx, header_val in enumerate(header_row):
            if col_idx < len(row):
                row_dict[str(header_val).strip()] = row[col_idx]
        print('[BUILD] row_dict=' + str(row_dict))
        doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)
        print('[BUILD] doc_data non-None=' + str({k: v for k, v in doc_data.items() if v is not None}))
        print('[BUILD] matched=' + str(m) + '/' + str(t))
        if validation_model is not None:
            result = validate_row(
                model=validation_model,
                normalized_data=doc_data,
                matched_fields=m,
                total_fields=t,
                missing_required=miss,
            )
            print('[BUILD] validation is_valid=' + str(result.is_valid) + ' errors=' + str(result.errors))
        else:
            result = None
        if result is not None and not result.is_valid:
            print('[BUILD] SKIPPING invalid row')
            continue
        sheet_payload = {'data': doc_data}
        print('[BUILD] calling pipeline.run...')
        pipeline_result = self._pipeline.run(sheet_payload, schema_path=schema_path)
        print('[BUILD] pipeline status=' + pipeline_result.status + ' errors=' + str(pipeline_result.errors))
        if pipeline_result.status != 'ok' or pipeline_result.output is None:
            print('[BUILD] Pipeline failed, continuing')
            continue
        partial = pipeline_result.output
        print('[BUILD] partial danh_sach_cnch=' + str(partial.danh_sach_cnch))
        target = cfg.get('target_section')
        print('[BUILD] target=' + str(target))
        if target and target != 'header':
            if hasattr(report, target):
                print('[BUILD] calling _merge_section')
                self._merge_section(report, partial, target)
                print('[BUILD] after merge: report.danh_sach_cnch=' + str(report.danh_sach_cnch))
        else:
            from app.engines.extraction.daily_report_builder import _SECTION_ATTRS
            for attr in _SECTION_ATTRS:
                self._merge_section(report, partial, attr)

DailyReportBuilder._process_worksheet_with_schema = patched

builder = DailyReportBuilder(template=template, sheet_data=sheet_data, worksheet_configs=worksheet_configs)
report = builder.build()
print('Final: report.danh_sach_cnch = ' + str(report.danh_sach_cnch))
print('Count: ' + str(len(report.danh_sach_cnch)))
