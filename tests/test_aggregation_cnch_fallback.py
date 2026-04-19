from app.application.aggregation_service import (
    _build_cnch_detail_from_items,
    _clean_cong_tac_an_ninh_text,
    _collect_cnch_items,
    _collect_cong_tac_khac_items,
    _collect_cong_van_items,
)


def test_clean_cong_tac_an_ninh_strips_ccc_prefix() -> None:
    assert _clean_cong_tac_an_ninh_text("CCC: Không") == "Không"


def test_collect_cnch_items_deduplicates_by_core_signature() -> None:
    rows = [
        {
            "danh_sach_cnch": [
                {
                    "thoi_gian": "12:32 ngày 04/04/2026",
                    "ngay_xay_ra": "04/04/2026",
                    "dia_diem": "khu đất trống",
                    "noi_dung_tin_bao": "cháy bãi rác",
                }
            ]
        },
        {
            "danh_sach_cnch": [
                {
                    "thoi_gian": "12:32 ngày 04/04/2026",
                    "ngay_xay_ra": "04/04/2026",
                    "dia_diem": "khu đất trống",
                    "noi_dung_tin_bao": "cháy bãi rác",
                },
                {
                    "thoi_gian": "13:00 ngày 05/04/2026",
                    "ngay_xay_ra": "05/04/2026",
                    "dia_diem": "khu phố A",
                    "noi_dung_tin_bao": "cứu hộ",
                },
            ]
        },
    ]

    merged = _collect_cnch_items(rows)

    assert len(merged) == 2


def test_build_cnch_detail_from_items_mentions_count() -> None:
    text = _build_cnch_detail_from_items(
        [
            {
                "thoi_gian": "12:32 ngày 04/04/2026",
                "noi_dung_tin_bao": "cháy bãi rác",
                "dia_diem": "khu đất trống",
                "ket_qua_xu_ly": "Thiệt hại: Không.",
            },
            {
                "thoi_gian": "13:00 ngày 05/04/2026",
                "noi_dung_tin_bao": "cứu hộ",
                "dia_diem": "khu phố A",
            },
        ]
    )

    assert "Trong kỳ xảy ra 2 vụ" in text
    assert "Kết quả: Thiệt hại" not in text
    assert ".." not in text


def test_collect_cong_van_items_merges_and_deduplicates() -> None:
    rows = [
        {"danh_sach_cong_van_tham_muu": [{"so_ky_hieu": "01/CV", "noi_dung": "Noi dung A"}]},
        {
            "danh_sach_cong_van_tham_muu": [
                {"so_ky_hieu": "01/CV", "noi_dung": "Noi dung A"},
                {"so_ky_hieu": "02/CV", "noi_dung": "Noi dung B"},
            ]
        },
    ]

    merged = _collect_cong_van_items(rows)

    assert len(merged) == 2


def test_collect_cong_tac_khac_items_merges_and_deduplicates() -> None:
    rows = [
        {"danh_sach_cong_tac_khac": ["Noi dung 1", "Noi dung 2"]},
        {"danh_sach_cong_tac_khac": ["Noi dung 2", "Noi dung 3"]},
    ]

    merged = _collect_cong_tac_khac_items(rows)

    assert merged == ["Noi dung 1", "Noi dung 2", "Noi dung 3"]
