from app.application.aggregation_service import (
    _derive_missing_additive_stt_fields,
    _sync_derived_stt_fields_to_bang_thong_ke,
)


def test_derives_stt32_from_stt31_minus_stt33() -> None:
    row = {
        "stt_31_kiem_tra_tong": 7,
        "stt_33_kiem_tra_dot_xuat": 0,
    }

    _derive_missing_additive_stt_fields(row)

    assert row["stt_32_kiem_tra_dinh_ky"] == 7


def test_derives_stt60_from_stt55_and_other_parts() -> None:
    row = {
        "stt_55_hl_tong_cbcs": 27,
        "stt_56_hl_chi_huy_phong": 0,
        "stt_57_hl_chi_huy_doi": 1,
        "stt_58_hl_can_bo_tieu_doi": 4,
        "stt_59_hl_chien_sy": 18,
        "stt_61_hl_lai_tau": 0,
    }

    _derive_missing_additive_stt_fields(row)

    assert row["stt_60_hl_lai_xe"] == 4


def test_derives_total_when_all_parts_exist() -> None:
    row = {
        "stt_36_xu_phat_canh_cao": 1,
        "stt_37_xu_phat_tam_dinh_chi": 2,
        "stt_38_xu_phat_dinh_chi": 3,
        "stt_39_xu_phat_tien_mat": 4,
    }

    _derive_missing_additive_stt_fields(row)

    assert row["stt_35_xu_phat_tong"] == 10


def test_syncs_derived_stt32_back_to_bang_thong_ke() -> None:
    row = {
        "bang_thong_ke": [
            {"stt": "31", "ket_qua": 12, "noi_dung": "Số cơ sở được kiểm an toàn PCCC"},
            {"stt": "33", "ket_qua": 1, "noi_dung": "Kiểm tra đột xuất theo chuyên đề"},
        ],
        "stt_31_kiem_tra_tong": 12,
        "stt_33_kiem_tra_dot_xuat": 1,
    }

    _derive_missing_additive_stt_fields(row)
    _sync_derived_stt_fields_to_bang_thong_ke(row)

    by_stt = {str(item["stt"]): int(item.get("ket_qua") or 0) for item in row["bang_thong_ke"]}
    assert by_stt["32"] == 11