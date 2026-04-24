"""Thin CLI runner — delegates to block mode pipeline + business rules.

All business logic lives in app/business/.
All pipeline logic lives in app/services/block_extraction_pipeline.py.
This file only handles: CLI entry, DB persistence, JSON output.
"""

import json
import os
import sqlite3
import sys

# Ensure project root is on sys.path when running from scripts/
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.engines.extraction.block_workflow import BlockBusinessWorkflow

# ==========================================================
# CONFIG
# ==========================================================

DB_PATH = os.path.join(_project_root, "extracted.db")
OUTPUT_PATH = os.path.join(_project_root, "full_output.json")


# ==========================================================
# DATABASE
# ==========================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        raw_text TEXT,
        structured_text TEXT,
        json_output TEXT
    )
    """)
    conn.commit()
    conn.close()


def save_to_db(filename, raw_text, structured, json_out):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO documents(filename, raw_text, structured_text, json_output) VALUES (?, ?, ?, ?)",
        (filename, raw_text, structured, json_out),
    )
    conn.commit()
    conn.close()


# ==========================================================
# PIPELINE (block mode)
# ==========================================================

def run_pipeline(pdf_path):
    init_db()

    print("STEP 1 — Block Mode Pipeline (layout → detect → extract → enforce → validate)")
    workflow = BlockBusinessWorkflow()

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    result = workflow.run_from_bytes(pdf_bytes, pdf_path)

    print("STEP 2 — Build Final Payload")
    final = workflow.build_final_payload(pdf_path, result)

    print("STEP 3 — Save Output")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)

    raw = json.dumps(final, ensure_ascii=False)
    save_to_db(pdf_path, raw, raw, raw)

    print(f"DONE — status={result['status']}, business_errors={result['business_data'].get('errors', [])}")


# ==========================================================
# RUN
# ==========================================================

if __name__ == "__main__":
    run_pipeline("input.pdf")