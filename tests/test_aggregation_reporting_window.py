from app.application.aggregation_service import _derive_reporting_window_from_rows


def test_reporting_window_prefers_ngay_bao_cao_across_rows() -> None:
    rows = [
        {"ngay_bao_cao": "01/04/2026"},
        {"header": {"ngay_bao_cao": "07/04/2026"}},
        {"ngay_bao_cao": "05/04/2026"},
    ]

    window = _derive_reporting_window_from_rows(rows)

    assert window == ("01/04/2026", "07/04/2026")


def test_reporting_window_prefers_den_ngay_for_daily_chain() -> None:
    rows = [
        {"tu_ngay": "31/3/2026", "den_ngay": "01/4/2026"},
        {"tu_ngay": "01/4/2026", "den_ngay": "02/4/2026"},
        {"tu_ngay": "06/4/2026", "den_ngay": "07/4/2026"},
    ]

    window = _derive_reporting_window_from_rows(rows)

    assert window == ("01/04/2026", "07/04/2026")


def test_reporting_window_falls_back_to_thoi_gian_tu_den_when_needed() -> None:
    rows = [
        {"header": {"thoi_gian_tu_den": "Từ 07 h 30 ngay 06/4/2026 den 07 h 30 ngay 07/4/2026"}},
        {"thoi_gian_tu_den": "Tu 07 h 30 ngay 02/4/2026 den 07 h 30 ngay 03/4/2026"},
    ]

    window = _derive_reporting_window_from_rows(rows)

    assert window == ("02/04/2026", "07/04/2026")