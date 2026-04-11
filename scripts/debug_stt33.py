"""Dump raw pdfplumber table rows around STT 31-34 to find why STT 33 is missing."""
import sys
import pdfplumber
import re

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "test_input.pdf"

with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages, 1):
        tables = page.extract_tables()
        for t_idx, table in enumerate(tables):
            # Check if this table contains rows around 31-34
            has_target = any(
                any(("31" == (c or "").strip() or "32" == (c or "").strip() or
                     "33" == (c or "").strip() or "34" == (c or "").strip())
                    for c in row)
                for row in table
            )
            if not has_target:
                # Also check if joined row text contains these numbers
                for row in table:
                    joined = " ".join(c or "" for c in row)
                    if re.search(r"\b3[123]\b", joined):
                        has_target = True
                        break

            if has_target:
                print(f"\n{'='*60}")
                print(f"Page {page_num}, Table {t_idx}  ({len(table)} rows)")
                print(f"{'='*60}")
                for r_idx, row in enumerate(table):
                    joined = " ".join(c or "" for c in row)
                    if re.search(r"\b3[0-5]\b", joined) or any(
                        (c or "").strip() in ("31","32","33","34","35") for c in row
                    ):
                        print(f"  row[{r_idx:3d}] cells={len(row)}:")
                        for c_idx, cell in enumerate(row):
                            cell_repr = repr(cell)[:80] if cell else "''"
                            print(f"    [{c_idx}] {cell_repr}")
