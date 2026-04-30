#!/usr/bin/env python3
"""
Compare GRID_STTS in frontend with stt_map in bc_ngay_schema.yaml.
Run: python scripts/validate_grid_stts.py
"""
import re, sys, yaml
from pathlib import Path

FRONTEND_PATH = Path("frontend/components/extraction/sheet-inspector.tsx")
SCHEMA_PATH   = Path("app/domain/templates/bc_ngay_schema.yaml")

def extract_stt_map_keys(schema_path: Path) -> dict[str, dict]:
    with open(schema_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    stt_map = data["sheet_mapping"]["bang_thong_ke"]["stt_map"]
    return {k: v for k, v in stt_map.items()}

def extract_grid_stts(frontend_path: Path) -> list[dict]:
    content = frontend_path.read_text(encoding="utf-8")
    match = re.search(r"const GRID_STTS\s*=\s*\[([\s\S]*?)\];", content)
    if not match:
        raise ValueError("GRID_STTS not found")
    block = match.group(1)
    results = []
    for m in re.finditer(r'\{\s*stt:\s*"(\d+)"\s*,\s*label:\s*"([^"]+)"\s*,\s*desc:\s*"([^"]*)"', block):
        results.append({"stt": m.group(1), "label": m.group(2), "desc": m.group(3)})
    return results

def generate_grid_stts_ts(stt_map: dict[str, dict]) -> str:
    lines = []
    for k in sorted(stt_map.keys(), key=lambda x: int(x)):
        entry = stt_map[k]
        noi_dung = entry.get("noi_dung") or ""
        label = re.sub(r"^(I\.|II\.|III\.)?\s*", "", noi_dung)
        desc = label[:40] if label else "(header)"
        lines.append(f'  {{ stt: "{k}", label: "STT {k}", desc: "{desc}" }}')
    return "[\n" + ",\n".join(lines) + "\n]"

def safe_print(text: str):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8"))

def main():
    sys.stdout.reconfigure(encoding="utf-8")

    schema_stt_map   = extract_stt_map_keys(SCHEMA_PATH)
    frontend_entries = extract_grid_stts(FRONTEND_PATH)

    schema_keys  = set(schema_stt_map.keys())
    frontend_keys = set(e["stt"] for e in frontend_entries)

    missing_in_frontend = sorted(schema_keys - frontend_keys, key=int)
    extra_in_frontend    = sorted(frontend_keys - schema_keys, key=int)

    print("=" * 60)
    print("  GRID_STTS vs bc_ngay_schema.yaml stt_map COMPARISON")
    print("=" * 60)
    print(f"  schema stt_map count      : {len(schema_keys)}")
    print(f"  frontend GRID_STTS count : {len(frontend_keys)}")
    print(f"  missing in frontend      : {len(missing_in_frontend)} keys")
    print(f"  extra in frontend        : {len(extra_in_frontend)} keys")
    print()
    if missing_in_frontend:
        print("  MISSING in frontend:")
        for k in missing_in_frontend:
            safe_print(f"    STT {k:>3}: {schema_stt_map[k].get('noi_dung', '')}")
        print()
    if extra_in_frontend:
        print("  EXTRA in frontend (not in schema):")
        for k in extra_in_frontend:
            e = next(ee for ee in frontend_entries if ee["stt"] == k)
            safe_print(f"    STT {k:>3}: {e['desc']}")
        print()

    # Generate full replacement
    full_ts = generate_grid_stts_ts(schema_stt_map)
    print()
    print("=" * 60)
    print("  FULL GRID_STTS REPLACEMENT (copy between === markers):")
    print("=" * 60)
    print("START_GRID_STTS>>>")
    print(full_ts)
    print("<<<END_GRID_STTS")
    print()

    # Write to disk for easy pickup
    out = Path("scripts") / "grid_stts_full.ts"
    out.write_text("const GRID_STTS = " + full_ts + ";\n", encoding="utf-8")
    print(f"  Written to: {out}")

    ok = len(missing_in_frontend) == 0 and len(extra_in_frontend) == 0
    print()
    print(f"  STATUS: {'IN SYNC' if ok else 'OUT OF SYNC - update needed'}")
    return ok

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
