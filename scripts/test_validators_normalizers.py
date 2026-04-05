"""Quick smoke test for upgraded validators and normalizers."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.rules.validation_rules import validate_business
from app.domain.rules.normalizers import normalize_business

print("=== VALIDATOR TESTS ===")

# 1. Good data — no errors
d1 = {"so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "21/03/2026", "don_vi": "KV30"}
errs = validate_business(d1)
print(f"Good data: errors={errs}")
assert errs == [], f"Expected no errors, got {errs}"

# 2. Bad date format
d2 = {"so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "2025", "don_vi": "KV30"}
errs = validate_business(d2)
print(f"Bad date format: errors={errs}")
assert "invalid_date_format" in errs

# 3. Date year out of range
d3 = {"so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "21/03/1990", "don_vi": "KV30"}
errs = validate_business(d3)
print(f"Year out of range: errors={errs}")
assert "date_year_out_of_range" in errs

# 4. Bad month
d4 = {"so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "21/13/2026", "don_vi": "KV30"}
errs = validate_business(d4)
print(f"Month 13: errors={errs}")
assert "date_month_out_of_range" in errs

# 5. Day exceeds month (Feb 30)
d5 = {"so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "30/02/2026", "don_vi": "KV30"}
errs = validate_business(d5)
print(f"Feb 30: errors={errs}")
assert "date_day_exceeds_month" in errs

# 6. Negative count
d6 = {"so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "21/03/2026", "don_vi": "KV30", "tong_so_vu_chay": -1}
errs = validate_business(d6)
print(f"Negative count: errors={errs}")
assert "negative_tong_so_vu_chay" in errs

# 7. Bad so_bao_cao format
d7 = {"so_bao_cao": "GARBAGE", "ngay_bao_cao": "21/03/2026", "don_vi": "KV30"}
errs = validate_business(d7)
print(f"Bad so_bao_cao: errors={errs}")
assert "invalid_so_bao_cao_format" in errs

# 8. Cross-field mismatch
d8 = {
    "so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "21/03/2026", "don_vi": "KV30",
    "tong_so_vu_chay": 1, "tong_so_vu_no": 0, "tong_so_vu_cnch": 0,
    "incidents": [{"nguon": "bang_thong_ke", "so_luong": 100}],
}
errs = validate_business(d8)
print(f"Cross-field mismatch: errors={errs}")
assert "cross_field_incident_total_mismatch" in errs

# 9. Missing all fields
d9 = {}
errs = validate_business(d9)
print(f"Empty data: errors={errs}")
assert "missing_so_bao_cao" in errs
assert "missing_ngay" in errs
assert "missing_don_vi" in errs

# 10. Invalid thoi_gian_tu_den
d10 = {"so_bao_cao": "180/BC-KV30", "ngay_bao_cao": "21/03/2026", "don_vi": "KV30", "thoi_gian_tu_den": "no dates here"}
errs = validate_business(d10)
print(f"Bad thoi_gian: errors={errs}")
assert "invalid_thoi_gian_tu_den" in errs

print("\n=== NORMALIZER TESTS ===")

# 1. noi_dung spacing fix
d = {"incidents": [{"noi_dung": "TổngsốvụcháyNổ", "nguon": "bang_thong_ke"}]}
result = normalize_business(d)
nd = result["incidents"][0]["noi_dung"]
print(f"noi_dung fixed: '{nd}'")
assert " " in nd, f"Expected spaces in '{nd}'"

# 2. Date normalization — spaced slashes + zero-pad
d = {"ngay_bao_cao": "1 / 3 / 2026"}
result = normalize_business(d)
print(f"Date normalized: '{result['ngay_bao_cao']}'")
assert result["ngay_bao_cao"] == "01/03/2026"

# 3. chi_tiet_cnch cleanup
d = {"chi_tiet_cnch": "CNCHvụ1tạiQuận5  có  2nạnNhân"}
result = normalize_business(d)
print(f"chi_tiet_cnch: '{result['chi_tiet_cnch']}'")
assert "  " not in result["chi_tiet_cnch"], "Should not have double spaces"

# 4. thoi_gian_tu_den cleanup
d = {"thoi_gian_tu_den": "Từ ngày  01 / 03 / 2026  đến ngày  07 / 03 / 2026"}
result = normalize_business(d)
print(f"thoi_gian: '{result['thoi_gian_tu_den']}'")
assert "01/03/2026" in result["thoi_gian_tu_den"]
assert "07/03/2026" in result["thoi_gian_tu_den"]

# 5. summary_text spacing
d = {"summary_text": "TìnhhìnhcháyNổtuầnqua"}
result = normalize_business(d)
print(f"summary_text: '{result['summary_text']}'")
assert " " in result["summary_text"]

# 6. dia_diem in incidents
d = {"incidents": [{"dia_diem": "số123đườngNguyễnVănCừ  Quận5"}]}
result = normalize_business(d)
dd = result["incidents"][0]["dia_diem"]
print(f"dia_diem: '{dd}'")
assert "  " not in dd

# 7. so_bao_cao collapse
d = {"so_bao_cao": "180 / BC - KV 30"}
result = normalize_business(d)
print(f"so_bao_cao: '{result['so_bao_cao']}'")
assert " " not in result["so_bao_cao"]

print("\n=== ALL TESTS PASSED ===")
