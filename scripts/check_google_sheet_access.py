docker exec -i rag-api python - <<'PY'
import csv, io, re, unicodedata, urllib.parse
import requests

SHEET_URL = "https://docs.google.com/spreadsheets/d/1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI/edit?gid=445968624#gid=445968624"

KV30_SHEETS = [
    "BC NGÀY",
    "BC NGÀY 1",
    "CNCH",
    "CHI VIỆN",
    "VỤ CHÁY THỐNG KÊ",
    "SCLQ ĐẾN PCCC&CNCH",
]

def extract_sheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise RuntimeError("Không lấy được sheet_id từ URL")
    return m.group(1)

def extract_gid(url: str):
    m = re.search(r"(?:[?#&]gid=)(\d+)", url)
    return m.group(1) if m else None

def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()

def public_csv_url(sheet_id: str, worksheet: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={urllib.parse.quote(worksheet)}"
    )

def to_int(x):
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return int(float(s.replace(",", ".")))
    except Exception:
        return None

def parse_date_key(row):
    if not row:
        return None

    c0 = str(row[0]).strip() if len(row) > 0 else ""
    c1 = str(row[1]).strip() if len(row) > 1 else ""

    n0 = norm(c0)
    if any(x in n0 for x in ["thang dau nam", "tong", "tong cong", "luy ke"]):
        return None

    m = re.match(r"^\s*(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s*$", c0)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{d:02d}/{mo:02d}"

    d, mo = to_int(c0), to_int(c1)
    if d is not None and mo is not None and 1 <= d <= 31 and 1 <= mo <= 12:
        return f"{d:02d}/{mo:02d}"

    return None

def check_public_csv(sheet_id: str, worksheet: str):
    url = public_csv_url(sheet_id, worksheet)
    try:
        r = requests.get(url, timeout=20)
    except Exception as e:
        return False, f"REQUEST_ERROR: {e}", [], url

    text_head = r.text[:500].lower()
    if r.status_code != 200:
        return False, f"HTTP_{r.status_code}: {r.text[:200]}", [], url

    if "<html" in text_head or "sign in" in text_head or "google accounts" in text_head:
        return False, "HTML_LOGIN_OR_NOT_PUBLIC", [], url

    try:
        rows = list(csv.reader(io.StringIO(r.text)))
    except Exception as e:
        return False, f"CSV_PARSE_ERROR: {e}", [], url

    if not rows:
        return False, "EMPTY_CSV", [], url

    return True, f"OK rows={len(rows)} content_type={r.headers.get('content-type')}", rows, url

sheet_id = extract_sheet_id(SHEET_URL)
gid = extract_gid(SHEET_URL)

print("=== INPUT ===")
print("sheet_id:", sheet_id)
print("gid:", gid or "(none)")
print()

any_public = False
bc_valid = False

for ws in KV30_SHEETS:
    print(f"=== CHECK worksheet: {ws} ===")
    ok, msg, rows, url = check_public_csv(sheet_id, ws)
    print("url:", url)
    print("public_csv:", ok, "-", msg)

    if not ok:
        print()
        continue

    any_public = True

    print("first 5 rows:")
    for i, row in enumerate(rows[:5], start=1):
        print(f"  {i}: {row[:12]}")

    valid = []
    for i, row in enumerate(rows, start=1):
        dk = parse_date_key(row)
        if dk:
            valid.append((i, dk, row[:6]))

    print("valid_daily_row_count:", len(valid))
    if valid:
        print("valid samples:")
        for item in valid[:8]:
            print(" ", item)

    if norm(ws).startswith("bc ngay") and len(valid) >= 5:
        bc_valid = True

    print()

print("=== VERDICT ===")
print("public_access:", "YES" if any_public else "NO")
print("bc_ngay_daily_rows_detected:", "YES" if bc_valid else "NO")

if any_public and bc_valid:
    print("KẾT LUẬN: Sheet public đọc được bằng CSV fallback. Backend KHÔNG được bắt Google credentials cho mode='kv30'.")
elif any_public and not bc_valid:
    print("KẾT LUẬN: Sheet public đọc được, nhưng chưa detect được BC NGÀY daily rows. Cần xem đúng worksheet title/layout.")
else:
    print("KẾT LUẬN: Public CSV không đọc được. Check Share → Anyone with the link → Viewer, hoặc backend cần service account.")
PY