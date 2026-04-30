"""Debug CNCH processing in DailyReportBuilder."""
from types import SimpleNamespace
from app.engines.extraction.schemas import BlockExtractionOutput
from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline, _normalize_key
from app.engines.extraction.mapping.schema_loader import load_schema
from app.engines.extraction.mapping.mapper import map_row_to_document_data

cnch_path = '/app/app/domain/templates/cnch_schema.yaml'
schema = load_schema(cnch_path)

rows = [
    ['STT', 'Ngày xảy ra sự cố', 'Thời gian đến', 'Địa điểm', 'Loại hình CNCH', 'Thiệt hại về người', 'Số người cứu được'],
    [1, '01/04/2026', '10:00', 'TP', 'Loại A', 0, 2],
    [2, '05/04/2026', '14:30', 'Phường 3', 'Cứu hộ', 0, 1],
]

pipeline = SheetExtractionPipeline()
header_row = rows[0]

print("Header row:", header_row)
print()

for row_idx, row in enumerate(rows[1:], start=1):
    row_dict = {str(h).strip(): v for h, v in zip(header_row, row)}
    normalized_row = {_normalize_key(k): v for k, v in row_dict.items()}
    print(f"Row {row_idx}: normalized_row =", normalized_row)
    
    doc_data, m, t, miss = map_row_to_document_data(normalized_row, schema)
    print(f"  doc_data (non-None):", {k: v for k, v in doc_data.items() if v is not None})
    print(f"  matched: {m}/{t}")
    
    result = pipeline.run({'data': doc_data}, schema_path=cnch_path)
    print(f"  status: {result.status}")
    if result.errors:
        print(f"  errors: {result.errors}")
    if result.output:
        print(f"  cnch items: {result.output.danh_sach_cnch}")
    print()

print("BlockExtractionOutput fields:")
for f in BlockExtractionOutput.model_fields:
    print(f"  {f}")
