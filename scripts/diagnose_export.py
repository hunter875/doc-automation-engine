"""Diagnose missing fields in Word export vs AI output."""
import json, psycopg2, os, sys

conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://raguser:ragpassword@postgres:5432/ragdb'))
cur = conn.cursor()

# 1. Get latest report's aggregated data
cur.execute("SELECT name, aggregated_data FROM aggregation_reports ORDER BY created_at DESC LIMIT 1")
row = cur.fetchone()
if not row:
    print("NO REPORT FOUND")
    sys.exit(1)

report_name, agg = row
records = agg.get("records", [])
rec = records[0] if records else {}

print(f"=== Report: {report_name} ===")
print(f"    record keys: {len(rec)}")
print()

# 2. Show non-zero fields in record
print("--- RECORD: fields with data ---")
for k in sorted(rec.keys()):
    v = rec[k]
    if v is not None and v != "" and v != 0 and v != []:
        vj = json.dumps(v, ensure_ascii=False)
        if len(vj) > 150:
            vj = vj[:150] + "..."
        print(f"  {k} = {vj}")

print()
print("--- RECORD: dicts ---")
for k in sorted(rec.keys()):
    if isinstance(rec[k], dict):
        print(f"  {k} = dict keys: {list(rec[k].keys())}")

print()
print("--- RECORD: non-empty lists ---")
for k in sorted(rec.keys()):
    if isinstance(rec[k], list) and rec[k]:
        vj = json.dumps(rec[k], ensure_ascii=False)
        if len(vj) > 200:
            vj = vj[:200] + "..."
        print(f"  {k} (len={len(rec[k])}) = {vj}")

# 3. Word template expected fields (from wordoclayout.txt)
word_fields = [
    "tu_ngay", "den_ngay", "ngay_xuat", "thang_xuat", "nam_xuat",
    "tong_chi_vien", "tong_cong_van", "tong_xe_hu_hong",
    "stt_02_tong_chay", "stt_03_chay_chet", "stt_04_chay_thuong",
    "stt_05_chay_cuu_nguoi", "stt_06_chay_thiet_hai", "stt_07_chay_cuu_tai_san",
    "stt_08_tong_no", "stt_09_no_chet", "stt_10_no_thuong",
    "stt_11_no_cuu_nguoi", "stt_12_no_thiet_hai", "stt_13_no_cuu_tai_san",
    "stt_14_tong_cnch", "stt_15_cnch_cuu_nguoi", "stt_16_cnch_truc_tiep",
    "stt_17_cnch_tu_thoat", "stt_18_cnch_thi_the", "stt_19_cnch_cuu_tai_san",
    "stt_22_tt_mxh_tong", "stt_23_tt_mxh_tin_bai", "stt_24_tt_mxh_hinh_anh",
    "stt_25_tt_mxh_video", "stt_27_tt_so_cuoc", "stt_28_tt_so_nguoi",
    "stt_29_tt_to_roi", "stt_31_kiem_tra_tong", "stt_32_kiem_tra_dinh_ky",
    "stt_33_kiem_tra_dot_xuat", "stt_34_vi_pham_phat_hien",
    "stt_35_xu_phat_tong", "stt_36_xu_phat_canh_cao",
    "stt_37_xu_phat_tam_dinh_chi", "stt_38_xu_phat_dinh_chi",
    "stt_39_xu_phat_tien_mat", "stt_40_xu_phat_tien",
    "stt_43_pa_co_so_duyet", "stt_44_pa_co_so_thuc_tap",
    "stt_46_pa_giao_thong_duyet", "stt_47_pa_giao_thong_thuc_tap",
    "stt_49_pa_cong_an_duyet", "stt_50_pa_cong_an_thuc_tap",
    "stt_52_pa_cnch_ca_duyet", "stt_53_pa_cnch_ca_thuc_tap",
    "stt_55_hl_tong_cbcs", "stt_56_hl_chi_huy_phong",
    "stt_57_hl_chi_huy_doi", "stt_58_hl_can_bo_tieu_doi",
    "stt_59_hl_chien_sy", "stt_60_hl_lai_xe", "stt_61_hl_lai_tau",
]

# Also check for narrative/detail fields the Word template needs
detail_fields = [
    "danh_sach_cnch", "danh_sach_phuong_tien_hu_hong",
    "danh_sach_cong_van_tham_muu", "chi_tiet_cnch",
    "so_bao_cao", "ngay_bao_cao", "don_vi_bao_cao", "thoi_gian_tu_den",
    "quan_so_truc", "tong_so_vu_chay", "tong_so_vu_no", "tong_so_vu_cnch",
]

print()
print("=== WORD FIELDS: MISSING from record ===")
missing = []
for f in word_fields:
    if f not in rec:
        missing.append(f)
        print(f"  MISSING: {f}")
    elif rec[f] is None:
        print(f"  NULL:    {f}")

print(f"\n  Total missing: {len(missing)} / {len(word_fields)}")

print()
print("=== DETAIL/NARRATIVE FIELDS ===")
for f in detail_fields:
    v = rec.get(f)
    if v is None:
        print(f"  MISSING: {f}")
    elif isinstance(v, list):
        print(f"  {f} = list(len={len(v)})")
    elif isinstance(v, dict):
        print(f"  {f} = dict")
    else:
        vj = json.dumps(v, ensure_ascii=False)[:100]
        print(f"  {f} = {vj}")

# 4. Now check what build_word_export_context would produce
print()
print("=== SIMULATING build_word_export_context ===")
import re

def _expand_header_subfields(context):
    header = context.get("header")
    if not isinstance(header, dict):
        return
    for k, v in header.items():
        context.setdefault(k, v)
    ngay = str(header.get("ngay_bao_cao") or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", ngay)
    if m:
        context.setdefault("ngay_xuat", m.group(1))
        context.setdefault("thang_xuat", m.group(2))
        context.setdefault("nam_xuat", m.group(3))
    tu_den_raw = str(header.get("thoi_gian_tu_den") or "").strip()
    if tu_den_raw:
        dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", tu_den_raw)
        if len(dates) >= 2:
            context.setdefault("tu_ngay", dates[0])
            context.setdefault("den_ngay", dates[1])
        elif len(dates) == 1:
            context.setdefault("tu_ngay", dates[0])

context = dict(rec)
_expand_header_subfields(context)

check_keys = ["tu_ngay", "den_ngay", "ngay_xuat", "thang_xuat", "nam_xuat",
              "so_bao_cao", "ngay_bao_cao", "don_vi_bao_cao", "thoi_gian_tu_den"]
for k in check_keys:
    v = context.get(k)
    print(f"  {k} = {json.dumps(v, ensure_ascii=False) if v else 'MISSING'}")

# 5. Check the raw extracted_data for the job
print()
print("=== JOB extracted_data: header + key fields ===")
cur.execute("SELECT extracted_data FROM extraction_jobs WHERE status = 'approved' ORDER BY updated_at DESC LIMIT 1")
job_row = cur.fetchone()
if job_row:
    ed = job_row[0]
    for k in ["header", "tu_ngay", "den_ngay", "ngay_xuat", "thang_xuat", "nam_xuat",
              "danh_sach_cnch", "danh_sach_phuong_tien_hu_hong"]:
        v = ed.get(k)
        if v is not None:
            vj = json.dumps(v, ensure_ascii=False)
            if len(vj) > 200:
                vj = vj[:200] + "..."
            print(f"  {k} = {vj}")
        else:
            print(f"  {k} = MISSING")

cur.close()
conn.close()
