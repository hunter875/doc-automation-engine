import sys
sys.path.insert(0, '/app')
from app.engines.extraction.sources.sheets_source import GoogleSheetsSource, SheetsFetchConfig
from app.engines.extraction.mapping.normalizer import normalize_unicode_text
ss = GoogleSheetsSource()
rows = ss.fetch_values(SheetsFetchConfig(sheet_id='1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI', worksheet='BC NGÀY', range_a1=None))

header_row_idx = 0
sub_header = rows[header_row_idx]
combined = None
print('sub_header[:3]:', sub_header[:3])
print('combined:', combined)

for row_idx in [32, 33]:
    row = rows[row_idx]
    row_dict = {}
    for col_idx in range(len(sub_header)):
        if col_idx >= len(row):
            continue
        h = sub_header[col_idx]
        if combined is not None and h is None:
            if col_idx < len(combined):
                header_name = str(combined[col_idx]).strip()
                row_dict[normalize_unicode_text(header_name)] = row[col_idx]
        else:
            if h is not None:
                header_name = str(h).strip()
                row_dict[normalize_unicode_text(header_name)] = row[col_idx]
    print(f'row {row_idx} keys[:5]={list(row_dict.keys())[:5]}')
    print(f'row {row_idx} ngay={row_dict.get("ngay", "NOT FOUND")}')
    print(f'row {row_idx} thang={row_dict.get("thang", "NOT FOUND")}')
