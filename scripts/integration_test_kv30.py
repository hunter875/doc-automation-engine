#!/usr/bin/env python3
"""Integration test with real Google Sheets KV30 template."""

import json
import re
import sys
from urllib.request import urlopen
from typing import Any

# Add app to path
sys.path.insert(0, '/app')

from app.engines.extraction.daily_report_builder import DailyReportBuilder
from app.engines.extraction.sources.sheets_source import GoogleSheetsSource, SheetsFetchConfig


def fetch_sheet_metadata(sheet_id: str) -> list[dict[str, Any]]:
    """Fetch worksheet names and gids from public Google Sheet HTML."""
    edit_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    try:
        with urlopen(edit_url, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Failed to fetch sheet HTML: {e}")
        return []

    # Find the sheets JSON in the HTML (window.ss_r or Spreadsheet config)
    sheets_data = []
    # Pattern 1: window.ss_r = {...}
    m = re.search(r'window\.ss_r\s*=\s*({.*?});', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            sheets = data.get('sheets', [])
            for s in sheets:
                props = s.get('properties', {})
                sheets_data.append({
                    'title': props.get('title'),
                    'sheetId': props.get('sheetId'),
                    'index': props.get('index'),
                })
        except Exception as e:
            print(f"Failed to parse ss_r JSON: {e}")
    else:
        # Pattern 2: Look for sheets in the embedded JSON
        m = re.search(r'([^"]*"sheets"\s*:\s*\[[^\]]*\][^"]*)', html)
        if m:
            # Try to extract using simpler approach: find all sheet titles in the HTML
            # Often sheet names appear in class="sheet-name" or similar
            titles = re.findall(r'<div[^>]*class="[^"]*sheet-name[^"]*"[^>]*>([^<]+)</div>', html)
            if titles:
                for idx, title in enumerate(titles):
                    sheets_data.append({
                        'title': title.strip(),
                        'sheetId': idx + 1,  # guess
                        'index': idx,
                    })

    return sheets_data


def infer_schema_path(worksheet_title: str) -> str | None:
    """Infer which KV30 schema to use based on worksheet name."""
    title = worksheet_title.lower()
    if 'bc ngày' in title or 'bc ngay' in title or 'báo cáo ngày' in title or 'ngày' in title:
        return '/app/app/domain/templates/bc_ngay_kv30.yaml'
    if 'chi viện' in title or 'chi vien' in title:
        return '/app/app/domain/templates/chi_vien_kv30.yaml'
    if 'cnch' in title or 'cứu nạn' in title or 'cuu nan' in title:
        return '/app/app/domain/templates/cnch_kv30.yaml'
    if 'vụ cháy' in title or 'vu chay' in title or 'cháy' in title:
        return '/app/app/domain/templates/vu_chay_kv30.yaml'
    return None


def main():
    sheet_id = "1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI"
    print(f"Fetching metadata for Google Sheet: {sheet_id}")

    sheets = fetch_sheet_metadata(sheet_id)
    if not sheets:
        print("Could not fetch sheet metadata. Sheet might be private or structure changed.")
        # Fallback: try common worksheet names
        print("Using fallback worksheet names.")
        sheets = [
            {'title': 'Sheet1', 'sheetId': 0, 'index': 0},
            {'title': 'BC NGÀY', 'sheetId': None, 'index': None},
            {'title': 'CNCH', 'sheetId': None, 'index': None},
            {'title': 'VỤ CHÁY', 'sheetId': None, 'index': None},
            {'title': 'CHI VIỆN', 'sheetId': None, 'index': None},
        ]

    print(f"Found {len(sheets)} worksheets:")
    for s in sheets:
        print(f"  - {s['title']}")

    # Build worksheet configs with inferred schemas
    worksheet_configs = []
    for s in sheets:
        schema_path = infer_schema_path(s['title'])
        if schema_path:
            worksheet_configs.append({
                'worksheet': s['title'],
                'schema_path': schema_path,
                'target_section': 'header',  # will be mapped based on schema
            })
            print(f"Mapping worksheet '{s['title']}' -> schema '{schema_path}'")
        else:
            print(f"Skipping worksheet '{s['title']}' (no matching schema)")

    if not worksheet_configs:
        print("No worksheets matched any schema. Exiting.")
        return

    # Fetch data using GoogleSheetsSource (public fallback)
    print("\nFetching sheet data...")
    sheets_source = GoogleSheetsSource()

    sheet_data = {}
    for cfg in worksheet_configs:
        ws = cfg['worksheet']
        try:
            rows = sheets_source.fetch_values(
                SheetsFetchConfig(
                    sheet_id=sheet_id,
                    worksheet=ws,
                    range_a1=None,
                )
            )
            sheet_data[ws] = rows
            print(f"Fetched {len(rows)} rows from '{ws}'")
        except Exception as e:
            print(f"Failed to fetch '{ws}': {e}")

    if not sheet_data:
        print("No data fetched. Exiting.")
        return

    # Create a dummy template with google_sheet_configs
    class DummyTemplate:
        google_sheet_configs = worksheet_configs
        schema_definition = {}
        aggregation_rules = {}
        name = "KV30 Integration Test"
        version = 1

    template = DummyTemplate()

    # DEBUG: Print actual data from BC NGÀY sheet to see column headers
    if 'BC NGÀY' in sheet_data:
        print("\n=== BC NGÀY raw data (first 5 rows) ===")
        for i, row in enumerate(sheet_data['BC NGÀY'][:5]):
            print(f"Row {i}: {row}")
        print("=== End of debug ===\n")

    # Run DailyReportBuilder
    print("\nRunning DailyReportBuilder...")
    builder = DailyReportBuilder(
        template=template,
        sheet_data=sheet_data,
        worksheet_configs=worksheet_configs,
    )

    try:
        date_reports = builder.build_all_by_date()
        print(f"\n✅ Successfully built {len(date_reports)} date report(s).")
        for date_key, report in date_reports.items():
            print(f"\n=== Report for date: {date_key} ===")
            print(f"  Header: so_bao_cao={report.header.so_bao_cao}, ngay_bao_cao={report.header.ngay_bao_cao}")
            print(f"  Nghiep vu: tong_so_vu_chay={report.phan_I_va_II_chi_tiet_nghiep_vu.tong_so_vu_chay}, tong_so_vu_cnch={report.phan_I_va_II_chi_tiet_nghiep_vu.tong_so_vu_cnch}")
            print(f"  Bang thong ke: {len(report.bang_thong_ke)} rows")
            print(f"  Danh sach CNCH: {len(report.danh_sach_cnch)} rows")
            print(f"  Danh sach Vu chay: {len(report.danh_sach_chay)} rows")
            print(f"  Danh sach Chi vien: {len(report.danh_sach_chi_vien)} rows")
    except Exception as e:
        print(f"❌ Error building reports: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n✅ Integration test completed.")


if __name__ == "__main__":
    main()
