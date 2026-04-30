"""Debug builder BC_NGAY processing with full trace."""
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
    {
        "worksheet": "CNCH",
        "schema_path": "/app/app/domain/templates/cnch_schema.yaml",
        "target_section": "danh_sach_cnch",
    },
    {
        "worksheet": "VỤ CHÁY THỐNG KÊ",
        "schema_path": "/app/app/domain/templates/vu_chay_schema.yaml",
        "target_section": "danh_sach_chay",
    },
    {
        "worksheet": "CHI VIỆN",
        "schema_path": "/app/app/domain/templates/chi_vien_schema.yaml",
        "target_section": "danh_sach_chi_vien",
    },
]

sheet_data = {
    "BC NGÀY": [
        ["ngày", "tháng", "Số báo cáo", "thời gian từ đến", "đơn vị báo cáo"],
        [1, 4, "BC-01", "01/04/2026 - 20/04/2026", "Đội PCCC&CNCH Quận 1"],
    ],
    "CNCH": [
        ["STT", "Ngày xảy ra sự cố", "Thời gian đến", "Địa điểm", "Loại hình CNCH",
         "Thiệt hại về người", "Số người cứu được"],
        [1, "01/04/2026", "10:00", "Phường 1, Quận 1", "Cứu nạn giao thông", 0, 2],
        [2, "05/04/2026", "14:30", "Phường 3, Quận 3", "Cứu hộ va chạm", 0, 1],
    ],
    "VỤ CHÁY THỐNG KÊ": [
        ["STT", "NGÀY XẢY RA VỤ CHÁY", "THỜI GIAN", "VỤ CHÁY",
         "ĐỊA ĐIỂM", "NGUYÊN NHÂN", "THIỆT HẠI VỀ NGƯỜI",
         "THIỆT HẠI TÀI SẢN", "THỜI GIAN KHỐNG CHẾ",
         "THỜI GIAN DẬP TẮT", "SỐ LƯỢNG XE", "CHỈ HUY"],
        [1, "03/04/2026", "08:30", "Cháy quán cơm", "Quận 5",
         "Chập điện", "0", "5.000.000", "09:00", "09:20", 2, "Thiếu tá A"],
    ],
    "CHI VIỆN": [
        ["STT", "NGÀY XẢY RA", "ĐỊA ĐIỂM", "KHU VỰC QUẢN LÝ",
         "SỐ LƯỢNG XE", "THỜI GIAN ĐI", "THỜI GIAN VỀ",
         "CHỈ HUY CHỮA CHÁY", "Ghi chú"],
        [1, "03/04/2026", "Quận 5", "KV-5", 3, "08:00", "10:30",
         "Thiếu tá B", "Chi viện chữa cháy"],
    ],
}

template = types.SimpleNamespace(google_sheet_configs=worksheet_configs)
builder = DailyReportBuilder(template=template, sheet_data=sheet_data, worksheet_configs=worksheet_configs)

# Manually trace each worksheet
for cfg in worksheet_configs:
    worksheet = cfg['worksheet']
    schema_path = cfg['schema_path']
    print(f'\n=== Worksheet: {worksheet} ===')
    rows = builder.sheet_data.get(worksheet, [])
    if not rows:
        print('  No rows')
        continue
    header_row = rows[0]
    row = rows[1]
    row_dict = {}
    for col_idx, header_val in enumerate(header_row):
        if col_idx < len(row):
            row_dict[str(header_val).strip()] = row[col_idx]
    print(f'  row_dict: {row_dict}')

    from app.engines.extraction.mapping.schema_loader import load_schema
    from app.engines.extraction.mapping.mapper import map_row_to_document_data

    ingestion_schema = load_schema(schema_path)
    doc_data, m, t, miss = map_row_to_document_data(row_dict, ingestion_schema)
    print(f'  doc_data non-None: {dict((k,v) for k,v in doc_data.items() if v is not None)}')
    print(f'  matched: {m}/{t}')

    sheet_payload = {'data': doc_data}
    pipeline_result = builder._pipeline.run(sheet_payload, schema_path=schema_path)
    print(f'  pipeline status={pipeline_result.status} errors={pipeline_result.errors}')
    if pipeline_result.output:
        partial = pipeline_result.output
        print(f'  partial.header: ngay={partial.header.ngay_bao_cao!r} so={partial.header.so_bao_cao!r}')
        print(f'  partial.cnch={len(partial.danh_sach_cnch)} chay={len(partial.danh_sach_chay)} chi_vien={len(partial.danh_sach_chi_vien)}')
        if partial.danh_sach_cnch:
            print(f'  partial.cnch[0].dia_diem={partial.danh_sach_cnch[0].dia_diem!r}')
        if partial.danh_sach_chay:
            print(f'  partial.chay[0].dia_diem={partial.danh_sach_chay[0].dia_diem!r}')
        if partial.danh_sach_chi_vien:
            print(f'  partial.chi_vien[0].khu_vuc={partial.danh_sach_chi_vien[0].khu_vuc_quan_ly!r}')
    else:
        print('  NO OUTPUT')

# Now build and check
report = builder.build()
print(f'\nFinal report:')
print(f'  header.ngay_bao_cao: {report.header.ngay_bao_cao!r}')
print(f'  header.so_bao_cao: {report.header.so_bao_cao!r}')
print(f'  danh_sach_cnch count: {len(report.danh_sach_cnch)}')
print(f'  danh_sach_chay count: {len(report.danh_sach_chay)}')
print(f'  danh_sach_chi_vien count: {len(report.danh_sach_chi_vien)}')
if report.danh_sach_chi_vien:
    print(f'  chi_vien[0].khu_vuc_quan_ly: {report.danh_sach_chi_vien[0].khu_vuc_quan_ly!r}')
