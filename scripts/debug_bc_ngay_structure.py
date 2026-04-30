"""Debug cấu trúc chi tiết của sheet BC NGÀY trong 1.xlsx"""
import sys
sys.path.insert(0, '/app')

import openpyxl

EXCEL_PATH = "/app/1.xlsx"

def read_sheet_detail(path, sheet_name):
    """Đọc chi tiết 1 sheet."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name]
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        rows.append((i, list(row)))
    return rows

def main():
    rows = read_sheet_detail(EXCEL_PATH, "BC NGÀY")
    print(f"Tổng số rows: {len(rows)}")
    
    # In 10 rows đầu tiên với tất cả columns
    print("\n=== BC NGÀY - 10 rows đầu ===")
    for i, row in rows[:10]:
        # Filter None values
        non_none = [(j, v) for j, v in enumerate(row) if v is not None]
        print(f"Row {i}: {non_none}")
    
    # In tất cả non-None values của row 0 và 1 (headers)
    print("\n=== HEADER ROW 0 ===")
    row0 = rows[0][1]
    for j, v in enumerate(row0):
        if v is not None:
            print(f"  Col {j}: {repr(v)}")
    
    print("\n=== HEADER ROW 1 ===")
    row1 = rows[1][1]
    for j, v in enumerate(row1):
        if v is not None:
            print(f"  Col {j}: {repr(v)}")
    
    print("\n=== HEADER ROW 2 ===")
    row2 = rows[2][1]
    for j, v in enumerate(row2):
        if v is not None:
            print(f"  Col {j}: {repr(v)}")
    
    # In data rows (từ row 3 trở đi)
    print("\n=== DATA ROWS (3-10) ===")
    for i, row in rows[3:11]:
        non_none = [(j, v) for j, v in enumerate(row) if v is not None]
        print(f"Row {i}: {non_none}")

if __name__ == "__main__":
    main()
