#!/usr/bin/env python3
"""Update bc_ngay_kv30_schema.yaml in container with correct aliases matching actual Google Sheet headers."""
import re

# Correct aliases based on actual Google Sheet column headers (after normalize)
# The actual column headers are (from debug_trace):
# col_0: NGÀY  -> 'ngay'
# col_1: THÁNG  -> 'thang'
# col_2: VỤ CHÁY VÀ CNCH VỤ CHÁY \nTHỐNG KÊ  -> 'vu chay va cnch vu chay thong ke'
# col_3: SCLQ ĐẾN \nPCCC&\nCNCH  -> 'sclq đen pccc& cnch'
# col_4: CHI VIỆN  -> 'chi vien'
# col_5: CNCH  -> 'cnch'
# col_6: CÔNG TÁC KIỂM TRA ĐỊNH KỲ NHÓM I  -> 'cong tac kiem tra đinh ky nhom i'
# col_7: NHÓM II  -> 'nhom ii'
# col_8: ĐỘT XUẤT NHÓM I  -> 'đot xuat nhom i'
# col_9: NHÓM II  -> 'nhom ii'
# col_10: HƯỚNG DẪN  -> 'huong dan'
# col_11: KIẾN\nNGHỊ  -> 'kien nghi'
# col_12: XỬ PHẠT  -> 'xu phat'
# col_13: TIỀN PHẠT\n(triệu đồng)  -> 'tien phat (trieu đong)'
# col_14: ĐÌNH CHỈ  -> 'đinh chi'
# col_15: PHỤC HỒI  -> 'phuc hoi'
# col_16: TUYÊN TRUYỀN PCCC TIN BÀI  -> 'tuyen truyen pccc tin bai'
# col_17: PHÓNG SỰ  -> 'phong su'
# col_18: SỐ LỚP TUYÊN TRUYỀN  -> 'so lop tuyen truyen'
# col_19: SỐ NGƯỜI THAM DỰ  -> 'so nguoi tham du'
# col_20: SỐ KHUYẾN CÁO, TỜ RƠI ĐÃ PHÁT  -> 'so khuyen cao, to roi đa phat'
# col_21: HUẤN LUYỆN PCCC SỐ LỚP HUẤN LUYỆN  -> 'huan luyen pccc so lop huan luyen'
# col_22: SỐ NGƯỜI THAM DỰ  -> 'so nguoi tham du'
# col_23: PACC&CNCH của cơ sở theo mẫu PC06 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT  -> 'pacc&cnch cua co so theo mau pc06 so pa xay dung va phe duyet'
# col_24: SỐ PA ĐƯỢC THỰC TẬP  -> 'so pa đuoc thuc tap'
# col_25: PACC&CNCH của CQ CA theo mẫu PC08 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT  -> 'pacc&cnch cua cq ca theo mau pc08 so pa xay dung va phe duyet'
# col_26: SỐ PA ĐƯỢC THỰC TẬP  -> 'so pa đuoc thuc tap'
# col_27: PA CNCH của CQ CA theo mẫu PC09 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT  -> 'pa cnch cua cq ca theo mau pc09 so pa xay dung va phe duyet'
# col_28: SỐ PA ĐƯỢC THỰC TẬP  -> 'so pa đuoc thuc tap'
# col_29: PACC&CNCH của phương tiện giao thông theo mẫu PC07 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT  -> 'pacc&cnch cua phuong tien giao thong theo mau pc07 so pa xay dung va phe duyet'
# col_30: SỐ PA ĐƯỢC THỰC TẬP  -> 'so pa đuoc thuc tap'
# col_31: Ghi chú  -> 'ghi chu'

UPDATED_SCHEMA = """# Schema cho sheet "BC NGÀY" - THỐNG KÊ CÔNG TÁC NGÀY PC KV30 2026
# Row 0 = group headers (merged), Row 1 = sub-headers (actual column names), Row 2+ = data
# Updated aliases to match actual Google Sheet column headers exactly

sheet_mapping:
  header:
    ngay_bao_cao_day:
      aliases: ["NGÀY", "ngày", "Ngày", "ngay"]
      type: integer
      required: false
    ngay_bao_cao_month:
      aliases: ["THÁNG", "tháng", "Tháng", "thang"]
      type: integer
      required: false

  nghiep_vu:
    # Vụ cháy / SCLQ / Chi viện / CNCH (4 cột đầu tiên)
    tong_so_vu_chay:
      aliases: ["VỤ CHÁY VÀ CNCH VỤ CHÁY \\nTHỐNG KÊ", "VỤ CHÁY THỐNG KÊ", "Vụ cháy thống kê", "VỤ CHÁY CÓ THỐNG KÊ", "VỤ CHÁY VÀ CNCH", "Vụ cháy và CNCH"]
      type: integer
      required: false
    tong_sclq:
      aliases: ["SCLQ ĐẾN \\nPCCC&\\nCNCH", "SỰ CỐ LIÊN QUAN ĐẾN PCCC&CNCH", "SCLQ ĐẾN PCCC&CNCH", "SỰ CỐ LIÊN QUAN ĐẾN PCCC & CNCH", "SCLQ Đến PCCC&CNCH"]
      type: integer
      required: false
    tong_chi_vien:
      aliases: ["VỤ CHÁY CHI VIỆN", "CHI VIỆN", "Chi viện"]
      type: integer
      required: false
    tong_so_vu_cnch:
      aliases: ["CNCH", "Cnch"]
      type: integer
      required: false

    # Kiểm tra nhóm I+II — actual headers have "NHÓM II" for both kiếm tra and đột xuất!
    kiem_tra_dinh_ky_n1:
      aliases: ["CÔNG TÁC KIỂM TRA ĐỊNH KỲ NHÓM I", "NHÓM I ĐỊNH KỲ", "ĐỊNH KỲ NHÓM I", "NHÓM I"]
      type: integer
      required: false
    kiem_tra_dinh_ky_n2:
      aliases: ["NHÓM II ĐỊNH KỲ", "ĐỊNH KỲ NHÓM II", "NHÓM II ĐỊNH KỲ", "NHÓM II"]
      type: integer
      required: false
    kiem_tra_dot_xuat_n1:
      aliases: ["ĐỘT XUẤT NHÓM I", "NHÓM I ĐỘT XUẤT"]
      type: integer
      required: false
    kiem_tra_dot_xuat_n2:
      aliases: ["NHÓM II ĐỘT XUẤT", "ĐỘT XUẤT NHÓM II", "NHÓM II ĐỘT XUẤT"]
      type: integer
      required: false

    # Tuyên truyền / Huấn luyện / Kiến nghị / Xử phạt
    huong_dan:
      aliases: ["HƯỚNG DẪN"]
      type: integer
      required: false
    kien_nghi:
      aliases: ["KIẾN\\nNGHỊ", "KIẾN NGHỊ", "KIẾN\\nNGHỊ "]
      type: integer
      required: false
    xu_phat:
      aliases: ["XỬ PHẠT"]
      type: integer
      required: false
    tien_phat:
      aliases: ["TIỀN PHẠT\\n(triệu đồng)", "TIỀN PHẠT\\n(triệu đồng) ", "TIỀN PHẠT (triệu đồng)", "TIỀN PHẠT"]
      type: string
      required: false
    tam_dinh_chi:
      aliases: ["ĐÌNH CHỈ"]
      type: integer
      required: false
    phuc_hoi:
      aliases: ["PHỤC HỒI"]
      type: integer
      required: false

    # Tuyên truyền online
    tong_tin_bai:
      aliases: ["TUYÊN TRUYỀN PCCC TIN BÀI", "TIN BÀI", "TIN BÀI, PHÓNG SỰ"]
      type: integer
      required: false
    tong_hinh_anh:
      aliases: ["PHÓNG SỰ", "TỔNG HÌNH ẢNH"]
      type: integer
      required: false
    so_lan_cai_app_114:
      aliases: ["CÀI APP HELP 114", "SỐ LƯỢT CÀI APP 114", "APP 114"]
      type: integer
      required: false
    tuyen_truyen_lop:
      aliases: ["SỐ LỚP TUYÊN TRUYỀN", "SỐ LỚP TUYÊN TRUYỀN ", "SĐ LỚP TUYÊN TRUYỀN"]
      type: integer
      required: false
    tuyen_truyen_nguoi:
      aliases: ["SỐ NGƯỜI THAM DỰ", "SỐ NGƯỜI THAM DỰ TUYÊN TRUYỀN", "SỐ NGƯỜI THAM DỰ ", "SỐ NGƯỜI THAM DỰ HUẤN LUYỆN"]
      type: integer
      required: false
    khuyen_cao:
      aliases: ["SỐ KHUYẾN CÁO, TỜ RƠI ĐÃ PHÁT", "SỐ KHUYẾN CÁO, TỜ RƠI ĐÃ PHÁT ", "SỐ KHUYẾN CÁO", "SĐ KHUYẾN CÁO, TỜ RƠI ĐÃ PHÁT", "sđ khuyen cao, to roi đa phat"]
      type: integer
      required: false

    # Huấn luyện
    huan_luyen_lop:
      aliases: ["HUẤN LUYỆN PCCC SỐ LỚP HUẤN LUYỆN", "SỐ LỚP HUẤN LUYỆN", "SỐ LỚP", "SĐ LỚP", "SỐ LỚP HUẤN LUYỆN "]
      type: integer
      required: false
    huan_luyen_nguoi:
      aliases: ["SỐ NGƯỜI THAM DỰ", "SỐ NGƯỜI THAM DỰ HUẤN LUYỆN", "SỐ NGƯỜI THAM DỰ HUẤN LUYỆN "]
      type: integer
      required: false

    # PC06 (PACC cơ sở)
    pa_pc06_xd:
      aliases: ["PACC&CNCH của cơ sở theo mẫu PC06 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "PACC&CNCH của cơ sở theo mẫu PC06 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT ", "SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "SĐ PA XÂY DỰNG VÀ PHÊ DUYỆT PC06"]
      type: integer
      required: false
    pa_pc06_tt:
      aliases: ["SỐ PA ĐƯỢC THỰC TẬP", "SỐ PA ĐƯỢC THỰC TẬP ", "SỐ PA ĐƯỢC THỰC TẬP PC06"]
      type: integer
      required: false

    # PC08 (PACC CQCA)
    pa_pc08_xd:
      aliases: ["PACC&CNCH của CQ CA theo mẫu PC08 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "PACC&CNCH của CQ CA theo mẫu PC08 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT ", "SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT PC08"]
      type: integer
      required: false
    pa_pc08_tt:
      aliases: ["SỐ PA ĐƯỢC THỰC TẬP", "SỐ PA ĐƯỢC THỰC TẬP "]
      type: integer
      required: false

    # PC09 (CNCH CQCA)
    pa_pc09_xd:
      aliases: ["PA CNCH của CQ CA theo mẫu PC09 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "PA CNCH của CQ CA theo mẫu PC09 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT ", "SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT PC09"]
      type: integer
      required: false
    pa_pc09_tt:
      aliases: ["SỐ PA ĐƯỢC THỰC TẬP", "SỐ PA ĐƯỢC THỰC TẬP "]
      type: integer
      required: false

    # PC07 (PACC phương tiện)
    pa_pc07_xd:
      aliases: ["PACC&CNCH của phương tiện giao thông theo mẫu PC07 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT", "PACC&CNCH của phương tiện giao thông theo mẫu PC07 SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT ", "SỐ PA XÂY DỰNG VÀ PHÊ DUYỆT PC07"]
      type: integer
      required: false
    pa_pc07_tt:
      aliases: ["SỐ PA ĐƯỢC THỰC TẬP", "SỐ PA ĐƯỢC THỰC TẬP "]
      type: integer
      required: false

  bang_thong_ke:
    fields:
      stt: ["STT", "stt"]
      noi_dung: ["nội dung", "noi_dung"]
      ket_qua: ["kết quả", "ket_qua"]
    stt_map:
      "2": {noi_dung: "1. Tổng số vụ cháy", field: "tong_so_vu_chay"}
      "3": {noi_dung: "2. Tổng số SCLQ đến PCCC&CNCH", field: "tong_sclq"}
      "4": {noi_dung: "3. Tổng số CNCH", field: "tong_so_vu_cnch"}
      "20": {noi_dung: "II. KẾT QUẢ CÔNG TÁC PCCC VÀ CNCH", field: null}
      "21": {noi_dung: "1. Tuyên truyền về PCCC và CNCH", field: null}
      "22": {noi_dung: "Tin bài phóng sự đăng tải", field: "tong_tin_bai"}
      "23": {noi_dung: "Hình ảnh đăng tải", field: "tong_hinh_anh"}
      "24": {noi_dung: "Số lượt cài app HELP 114", field: "so_lan_cai_app_114"}
      "25": {noi_dung: "1.2 Tuyên truyền trực tiếp tại cơ sở", field: null}
      "26": {noi_dung: "Số cuộc tuyên truyền", field: "tuyen_truyen_lop"}
      "27": {noi_dung: "Số người tham dự", field: "tuyen_truyen_nguoi"}
      "28": {noi_dung: "Số khuyến cáo tờ rơi đã phát", field: "khuyen_cao"}
      "31": {noi_dung: "Số cơ sở được kiểm tra", field: null}
      "32": {noi_dung: "Kiểm tra định kỳ nhóm I", field: "kiem_tra_dinh_ky_n1"}
      "33": {noi_dung: "Kiểm tra định kỳ nhóm II", field: "kiem_tra_dinh_ky_n2"}
      "34": {noi_dung: "Kiểm tra đột xuất nhóm I", field: "kiem_tra_dot_xuat_n1"}
      "35": {noi_dung: "Kiểm tra đột xuất nhóm II", field: "kiem_tra_dot_xuat_n2"}
      "41": {noi_dung: "Số cơ sở bị xử phạt", field: "xu_phat"}
      "42": {noi_dung: "Số tiền phạt thu được (triệu đồng)", field: "tien_phat"}
      "43": {noi_dung: "Đình chỉ hoạt động", field: "tam_dinh_chi"}
      "44": {noi_dung: "Phục hồi", field: "phuc_hoi"}
      "51": {noi_dung: "Số lớp huấn luyện", field: "huan_luyen_lop"}
      "52": {noi_dung: "Số người tham dự huấn luyện", field: "huan_luyen_nguoi"}
      "61": {noi_dung: "PA PC06 xây dựng và phê duyệt", field: "pa_pc06_xd"}
      "62": {noi_dung: "PA PC06 thực tập", field: "pa_pc06_tt"}
      "63": {noi_dung: "PA PC08 xây dựng và phê duyệt", field: "pa_pc08_xd"}
      "64": {noi_dung: "PA PC08 thực tập", field: "pa_pc08_tt"}
      "65": {noi_dung: "PA PC09 xây dựng và phê duyệt", field: "pa_pc09_xd"}
      "66": {noi_dung: "PA PC09 thực tập", field: "pa_pc09_tt"}
      "67": {noi_dung: "PA PC07 xây dựng và phê duyệt", field: "pa_pc07_xd"}
      "68": {noi_dung: "PA PC07 thực tập", field: "pa_pc07_tt"}
"""

SCHEMA_PATH = "/app/app/domain/templates/bc_ngay_kv30_schema.yaml"

with open(SCHEMA_PATH, "w", encoding="utf-8") as f:
    f.write(UPDATED_SCHEMA)

print(f"Updated schema written to {SCHEMA_PATH}")
