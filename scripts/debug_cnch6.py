"""Trace builder's _process_worksheet_with_schema calls."""
import types
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline, _normalize_key

# Monkey-patch with print
_orig = DailyReportBuilder._process_worksheet_with_schema

def patched(self, report, worksheet, schema_path, cfg):
    print(f'[TRACER] worksheet={worksheet}')
    rows = self.sheet_data.get(worksheet, [])
    print(f'[TRACER] rows={len(rows)}')
    if not rows:
        return
    header_row = rows[0]
    for row_idx, row in enumerate(rows[1:], start=1):
        row_dict = {}
        for col_idx, header_val in enumerate(header_row):
            if col_idx < len(row):
                row_dict[str(header_val).strip()] = row[col_idx]
        print(f'[TRACER] row {row_idx}: {row_dict}')

        # Pass raw row_dict (not normalized) - mapper normalizes internally
        from app.engines.extraction.mapping.schema_loader import load_schema
        from app.engines.extraction.mapping.mapper import map_row_to_document_data
        try:
            ingestion_schema = load_schema(schema_path)
        except Exception as e:
            print(f'[TRACER] load_schema failed: {e}')
            return

        doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)
        print(f'[TRACER] doc_data non-None: {dict((k,v) for k,v in doc_data.items() if v is not None)}')
        print(f'[TRACER] matched: {m}/{t}')

        sheet_payload = {'data': doc_data}
        pipeline_result = self._pipeline.run(sheet_payload, schema_path=schema_path)
        print(f'[TRACER] pipeline status={pipeline_result.status} errors={pipeline_result.errors}')
        if pipeline_result.status != 'ok' or pipeline_result.output is None:
            print('[TRACER] pipeline failed, skipping merge')
            continue

        partial = pipeline_result.output
        print(f'[TRACER] partial.danh_sach_cnch={partial.danh_sach_cnch}')
        target = cfg.get('target_section')
        if target and target != 'header':
            if hasattr(report, target):
                self._merge_section(report, partial, target)
                print(f'[TRACER] merged, report.danh_sach_cnch={getattr(report, target)}')
        else:
            from app.engines.extraction.daily_report_builder import _SECTION_ATTRS
            for attr in _SECTION_ATTRS:
                self._merge_section(report, partial, attr)
            print(f'[TRACER] merged all, report.danh_sach_cnch={report.danh_sach_cnch}')

DailyReportBuilder._process_worksheet_with_schema = patched

worksheet_configs = [
    {'worksheet': 'CNCH', 'schema_path': '/app/app/domain/templates/cnch_schema.yaml', 'target_section': 'danh_sach_cnch'},
]
sheet_data = {
    'CNCH': [
        ['STT', 'Ngay xay ra', 'Thoi gian', 'Dia diem', 'Loai hinh', 'Thiet hai', 'So nguoi'],
        [1, '01/04/2026', '10:00', 'TP', 'Loai A', 0, 2],
        [2, '05/04/2026', '14:30', 'Phuong 3', 'Cuu ho', 0, 1],
    ]
}
template = types.SimpleNamespace(google_sheet_configs=worksheet_configs)
builder = DailyReportBuilder(template=template, sheet_data=sheet_data, worksheet_configs=worksheet_configs)
report = builder.build()
print('Final: danh_sach_cnch =', report.danh_sach_cnch)
print('Count:', len(report.danh_sach_cnch))
