"""Add _is_partial_output_empty and _partial_has_target_data to daily_report_builder.py"""
import re

with open('app/engines/extraction/daily_report_builder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the line with _partial_is_empty and add new methods before _create_empty_report
marker = '    def _create_empty_report(self) -> BlockExtractionOutput:'

new_methods = '''    def _is_partial_output_empty(self, partial: "BlockExtractionOutput") -> bool:
        """Return True if the pipeline output has no meaningful data."""
        if partial is None:
            return True

        # header without meaningful fields
        h = partial.header
        header_empty = not (h.so_bao_cao or h.ngay_bao_cao or h.thoi_gian_tu_den or h.don_vi_bao_cao)

        # bang_thong_ke empty
        btk_empty = len(partial.bang_thong_ke) == 0

        # all list sections empty
        lists_empty = (
            len(partial.danh_sach_cnch) == 0
            and len(partial.danh_sach_chay) == 0
            and len(partial.danh_sach_chi_vien) == 0
            and len(partial.danh_sach_sclq) == 0
            and len(partial.danh_sach_phuong_tien_hu_hong) == 0
            and len(partial.danh_sach_cong_van_tham_muu) == 0
            and len(partial.danh_sach_cong_tac_khac) == 0
        )

        # phan_I numeric/text fields empty
        nv = partial.phan_I_va_II_chi_tiet_nghiep_vu
        nghiep_vu_empty = (
            (getattr(nv, "tong_so_vu_chay", 0) in (None, 0)
            and (getattr(nv, "tong_so_vu_cnch", 0) in (None, 0))
            and (getattr(nv, "tong_sclq", 0) in (None, 0))
            and (getattr(nv, "quan_so_truc", 0) in (None, 0))
        )

        # tuyen_truyen_online all zero
        tto = partial.tuyen_truyen_online
        online_empty = (
            (getattr(tuyen, "so_tin_bai", 0) in (None, 0)
            and (getattr(tuyen, "so_hinh_anh", 0) in (None, 0))
            and (getattr(tuyen, "cai_app_114", 0) in (None, 0))
        )

        return header_empty and btk_empty and lists_empty and nghiep_vu_empty and online_empty

    def _partial_has_target_data(self, partial: "BlockExtractionOutput", target_section: str) -> bool:
        """Return True if the partial output has data for the given target_section."""
        if not target_section:
            return True

        value = getattr(partial, target_section, None)
        if value is None:
            return False

        if isinstance(value, list):
            return len(value) > 0
        return bool(value)

    def _create_empty_report(self) -> BlockExtractionOutput:'''

# Replace the marker with new methods + marker
content = content.replace(marker, new_methods)

with open('app/engines/extraction/daily_report_builder.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added _is_partial_output_empty and _partial_has_target_data")
