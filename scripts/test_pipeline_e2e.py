"""End-to-end block pipeline test — Stage 1 (sync) + Stage 2 (LLM enrichment).

Usage (from project root):
    python scripts/test_pipeline_e2e.py path/to/file.pdf [--stage1-only]

Chạy toàn bộ luồng:
    Stage 1 — BlockExtractionPipeline.run_stage1_from_bytes()
              layout → detect → extract → enforce → validate → narrative arrays
    Stage 2 — BlockExtractionPipeline._llm_enrich_cnch()
              LLM + regex fill → enriched danh_sach_cnch
    Merge   — final_data = extracted_data merged with enriched_data
    Report  — in ra từng section, highlight field rỗng

KHÔNG bao gồm: DB, Celery, export Word.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time

# ── project root on path ──────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"


def _section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")


def _ok(msg: str) -> None:
    print(f"  {GREEN}✔  {msg}{RESET}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}⚠  {msg}{RESET}")


def _err(msg: str) -> None:
    print(f"  {RED}✘  {msg}{RESET}")


def _kv(key: str, value: object) -> None:
    val_str = str(value)
    # Integers (including 0) are valid — only colour empty/None red
    is_empty = val_str in ("", "None", "[]", "{}")
    colour = RED if is_empty else GREEN
    print(f"    {key:<35} {colour}{val_str}{RESET}")


def _check_cnch_item(idx: int, item: dict) -> None:
    required = [
        "thoi_gian", "ngay_xay_ra", "dia_diem",
        "noi_dung_tin_bao", "luc_luong_tham_gia",
        "ket_qua_xu_ly", "thong_tin_nan_nhan",
    ]
    empty = [f for f in required if not (item.get(f) or "").strip()]
    tag = f"{RED}[MISSING: {', '.join(empty)}]{RESET}" if empty else f"{GREEN}[COMPLETE]{RESET}"
    print(f"\n  {BOLD}Incident #{idx}{RESET}  {tag}")
    for field in ["stt", "thoi_gian", "ngay_xay_ra", "dia_diem",
                  "noi_dung_tin_bao", "luc_luong_tham_gia",
                  "ket_qua_xu_ly", "thong_tin_nan_nhan", "mo_ta"]:
        _kv(field, item.get(field, ""))


def _dump_json(obj: object, label: str) -> None:
    print(f"\n{DIM}── {label} ──────────────────────────────────────{RESET}")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------

def run_stage1(pdf_bytes: bytes, pdf_path: str) -> dict:
    from app.engines.extraction.block_pipeline import BlockExtractionPipeline

    _section("STAGE 1 — Deterministic extraction (no LLM for main fields)")
    t0 = time.perf_counter()

    pipeline = BlockExtractionPipeline(job_id="test-e2e")

    # run_stage1_from_bytes: no CNCH LLM call, saves chi_tiet_cnch for Stage 2
    result = pipeline.run_stage1_from_bytes(pdf_bytes, os.path.basename(pdf_path))

    elapsed = time.perf_counter() - t0
    _ok(f"Stage 1 done in {elapsed:.2f}s  status={result.status}")

    if result.errors:
        for e in result.errors:
            _warn(f"Pipeline error: {e}")

    if result.output is None:
        _err("result.output is None — pipeline may have failed")
        return {}

    # Flatten to dict via doc_service logic
    data: dict = result.output.model_dump() if hasattr(result.output, "model_dump") else {}

    # Promote header sub-fields to top-level (matches aggregation payload shape)
    hdr_obj = result.output.header
    nv_obj  = result.output.phan_I_va_II_chi_tiet_nghiep_vu
    data["chi_tiet_cnch"]    = result.chi_tiet_cnch
    data["phan_I_va_II_chi_tiet_nghiep_vu"] = nv_obj.model_dump() if hasattr(nv_obj, "model_dump") else {}

    # ── Header ──────────────────────────────────────────────────────────────
    _section("HEADER")
    hdr = data.get("header", {})
    for f in ["so_bao_cao", "ngay_bao_cao", "don_vi_bao_cao", "thoi_gian_tu_den"]:
        _kv(f, hdr.get(f, ""))

    # ── Numeric counts ─────────────────────────────────────────────────────────
    _section("NUMERIC COUNTS")
    # BlockExtractionOutput nests these inside phan_I_va_II_chi_tiet_nghiep_vu
    nv = data.get("phan_I_va_II_chi_tiet_nghiep_vu") or {}
    for f in ["tong_so_vu_chay", "tong_so_vu_no", "tong_so_vu_cnch",
              "tong_xe_hu_hong", "tong_cong_van", "quan_so_truc"]:
        _kv(f, data.get(f, nv.get(f, "")))

    # ── Bang thong ke (table rows) ───────────────────────────────────────────
    _section("BẢNG THỐNG KÊ")
    rows = data.get("bang_thong_ke", [])
    if rows:
        _ok(f"{len(rows)} rows extracted")
        # spot-check a few key STT rows
        key_stts = {"2", "8", "14", "31", "32", "33", "44", "55"}
        for row in rows:
            if str(row.get("stt", "")) in key_stts:
                print(f"    STT {row.get('stt'):>3}  ket_qua={row.get('ket_qua')}  "
                      f"{(row.get('noi_dung') or '')[:60]}")
        # check if STT 33 is present
        stts = {str(r.get("stt", "")) for r in rows}
        if "33" not in stts:
            _warn("STT 33 (Kiểm tra đột xuất) is MISSING from bang_thong_ke")
        else:
            _ok("STT 33 present")
    else:
        _err("bang_thong_ke is EMPTY")

    # ── Phương tiện hư hỏng ──────────────────────────────────────────────────
    _section("PHƯƠNG TIỆN HƯ HỎNG")
    pt = data.get("danh_sach_phuong_tien_hu_hong", [])
    if pt:
        for xe in pt:
            bs = xe.get("bien_so", "")
            tt = xe.get("tinh_trang", "")
            colour = RED if not tt else GREEN
            print(f"    {bs:<40} tinh_trang={colour}{tt}{RESET}")
    else:
        _warn("danh_sach_phuong_tien_hu_hong is empty")

    # ── CNCH Stage-1 (regex only, no LLM yet) ───────────────────────────────
    _section("DANH SACH CNCH — Stage 1 (regex, no LLM)")
    cnch_s1 = data.get("danh_sach_cnch", [])
    if cnch_s1:
        for i, item in enumerate(cnch_s1, 1):
            _check_cnch_item(i, item if isinstance(item, dict) else item.model_dump())
    else:
        _warn("danh_sach_cnch is empty after Stage 1")

    # ── chi_tiet_cnch raw text ───────────────────────────────────────────────
    chi_tiet = (data.get("phan_I_va_II_chi_tiet_nghiep_vu") or {}).get("chi_tiet_cnch", "")
    _section("CHI_TIET_CNCH TEXT (input to Stage 2 LLM)")
    if chi_tiet:
        _ok(f"{len(chi_tiet)} chars")
        print(textwrap.indent(chi_tiet[:800], "    "))
    else:
        _err("chi_tiet_cnch is EMPTY — Stage 2 will be skipped")

    return data


# ---------------------------------------------------------------------------
# Stage 2 — regex fill only (no LLM, for fast offline testing)
# ---------------------------------------------------------------------------

def run_stage2_regex_only(data: dict) -> dict:
    from app.engines.extraction.block_pipeline import BlockExtractionPipeline
    from app.engines.extraction.schemas import CNCHItem

    _section("STAGE 2 — Regex fill only (no LLM)")

    chi_tiet = (
        (data.get("phan_I_va_II_chi_tiet_nghiep_vu") or {}).get("chi_tiet_cnch", "")
        or data.get("chi_tiet_cnch", "")
    ).strip()

    if not chi_tiet:
        _warn("No chi_tiet_cnch text — nothing to fill")
        return {}

    pipeline = BlockExtractionPipeline(job_id="test-regex-fill")

    # Take Stage-1 items and fill empty fields via regex only
    s1_cnch = data.get("danh_sach_cnch", [])
    if not s1_cnch:
        _warn("No Stage-1 CNCH items to fill")
        return {}

    filled = []
    for raw in s1_cnch:
        d = raw if isinstance(raw, dict) else raw.model_dump()
        item = CNCHItem(**{k: v for k, v in d.items() if k in CNCHItem.model_fields})
        pipeline._regex_fill_cnch_fields(item, chi_tiet)
        filled.append(item.model_dump())
        _check_cnch_item(len(filled), item.model_dump())

    return {"danh_sach_cnch": filled}


# ---------------------------------------------------------------------------
# Stage 2 — LLM
# ---------------------------------------------------------------------------

def run_stage2(data: dict) -> dict:
    from app.engines.extraction.block_pipeline import BlockExtractionPipeline

    _section("STAGE 2 — LLM enrichment (CNCH fields)")

    nghiep_vu = data.get("phan_I_va_II_chi_tiet_nghiep_vu") or {}
    chi_tiet = nghiep_vu.get("chi_tiet_cnch", "").strip() or data.get("chi_tiet_cnch", "").strip()

    if not chi_tiet:
        _warn("No chi_tiet_cnch text — skipping Stage 2")
        return {}

    pipeline = BlockExtractionPipeline(job_id="test-e2e-enrichment")

    t0 = time.perf_counter()
    enriched_items = pipeline._llm_enrich_cnch(chi_tiet)
    elapsed = time.perf_counter() - t0

    if enriched_items:
        _ok(f"LLM enrichment done in {elapsed:.2f}s — {len(enriched_items)} incident(s)")
        cnch_list = []
        for i, item in enumerate(enriched_items, 1):
            d = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            _check_cnch_item(i, d)
            cnch_list.append(d)
        return {"danh_sach_cnch": cnch_list}
    else:
        _warn(f"LLM enrichment returned empty list in {elapsed:.2f}s")
        return {}


# ---------------------------------------------------------------------------
# Merge + final report
# ---------------------------------------------------------------------------

def merge_and_report(stage1_data: dict, enriched_data: dict) -> dict:
    _section("MERGED FINAL DATA")

    # Same merge logic as ExtractionJob.final_data
    merged = dict(stage1_data)
    if enriched_data.get("danh_sach_cnch"):
        merged["danh_sach_cnch"] = enriched_data["danh_sach_cnch"]
        _ok(f"Using Stage-2 enriched danh_sach_cnch ({len(merged['danh_sach_cnch'])} items)")
    else:
        _warn("Using Stage-1 danh_sach_cnch (Stage 2 did not produce results)")

    # ── Final CNCH check ────────────────────────────────────────────────────
    _section("FINAL CNCH QUALITY CHECK")
    cnch_final = merged.get("danh_sach_cnch", [])
    total_fields = 0
    empty_fields = 0
    required = ["thoi_gian", "ngay_xay_ra", "dia_diem",
                "noi_dung_tin_bao", "luc_luong_tham_gia",
                "ket_qua_xu_ly", "thong_tin_nan_nhan"]
    for item in cnch_final:
        d = item if isinstance(item, dict) else item.model_dump()
        for f in required:
            total_fields += 1
            if not (d.get(f) or "").strip():
                empty_fields += 1

    if total_fields:
        pct = 100 * (total_fields - empty_fields) / total_fields
        colour = GREEN if pct >= 90 else (YELLOW if pct >= 70 else RED)
        print(f"\n  {BOLD}CNCH completeness: {colour}{pct:.0f}%{RESET}  "
              f"({total_fields - empty_fields}/{total_fields} fields filled)")
    else:
        _warn("No CNCH incidents in final data")

    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="E2E block pipeline test")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("--stage1-only", action="store_true",
                        help="Skip Stage 2 LLM enrichment")
    parser.add_argument("--regex-fill-only", action="store_true",
                        help="Run Stage-2 regex fill without LLM call (fast, offline)")
    parser.add_argument("--dump-json", action="store_true",
                        help="Print full merged JSON at the end")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"{RED}File not found: {args.pdf}{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}PDF:{RESET} {args.pdf}")

    with open(args.pdf, "rb") as fh:
        pdf_bytes = fh.read()

    # Stage 1
    stage1_data = run_stage1(pdf_bytes, args.pdf)
    if not stage1_data:
        print(f"\n{RED}Stage 1 failed — aborting{RESET}")
        sys.exit(1)

    # Stage 2
    enriched_data: dict = {}
    if args.stage1_only:
        _section("STAGE 2 SKIPPED (--stage1-only)")
    elif args.regex_fill_only:
        _section("STAGE 2 — Regex fill only (no LLM)")
        enriched_data = run_stage2_regex_only(stage1_data)
    else:
        enriched_data = run_stage2(stage1_data)

    # Merge
    final = merge_and_report(stage1_data, enriched_data)

    # Optional full JSON dump
    if args.dump_json:
        _dump_json(final, "COMPLETE MERGED OUTPUT")

    _section("DONE")
    _ok("Pipeline test completed successfully")


if __name__ == "__main__":
    main()
