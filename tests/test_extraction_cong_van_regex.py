from app.engines.extraction.block_pipeline import BlockExtractionPipeline, _inject_computed_bang_thong_ke_rows
from app.engines.extraction.schemas import ChiTieu


def test_extract_cong_van_items_includes_bao_cao_and_ke_hoach() -> None:
    narrative_text = (
        "Công văn số 12/CV ngày 04/04/2026 về việc chỉ đạo A; "
        "Báo cáo số 34/BC ngày 04/04/2026 kết quả thực hiện B; "
        "Kế hoạch số 56/KH ngày 04/04/2026 triển khai C. "
        "1. Công tác khác: Nội dung khác"
    )

    items = BlockExtractionPipeline._extract_cong_van_items_from_text(narrative_text)

    assert [item.so_ky_hieu for item in items] == ["12/CV", "34/BC", "56/KH"]
    assert all(not item.noi_dung.lower().startswith("ngày") for item in items)


def test_extract_cong_van_items_repairs_split_suffix_in_code() -> None:
    narrative_text = (
        "Công văn số 75/KV 30 ngày 06/04/2026 về việc phối hợp lực lượng xử lý sự cố. "
        "1. Công tác khác: Không"
    )

    items = BlockExtractionPipeline._extract_cong_van_items_from_text(narrative_text)

    assert len(items) == 1
    assert items[0].so_ky_hieu == "75/KV30"
    assert items[0].noi_dung.startswith("về việc phối hợp lực lượng")


def test_extract_cong_van_items_supports_cv_abbreviation_without_so() -> None:
    narrative_text = (
        "CV 88/TT ngày 07/04/2026 về việc đôn đốc thực hiện nhiệm vụ; "
        "2. Công tác khác: Không"
    )

    items = BlockExtractionPipeline._extract_cong_van_items_from_text(narrative_text)

    assert len(items) == 1
    assert items[0].so_ky_hieu == "88/TT"
    assert items[0].noi_dung.startswith("về việc đôn đốc")


def test_extract_cong_van_items_splits_period_dash_ke_hoach_entry() -> None:
    narrative_text = (
        "Báo cáo số 213/BC-KV30 ngày 05/4/2026 kết quả A; "
        "Báo cáo số 214/BC-KV30 ngày 05/4/2026 kết quả B; "
        "Báo cáo số 215/BC-KV30 ngày 05/4/2026 kết quả C. - "
        "Kế hoạch số 39/KH-KV 30 ngày 05/4/2026 triển khai D. "
        "1. Công tác khác: Không"
    )

    items = BlockExtractionPipeline._extract_cong_van_items_from_text(narrative_text)

    assert [item.so_ky_hieu for item in items] == [
        "213/BC-KV30",
        "214/BC-KV30",
        "215/BC-KV30",
        "39/KH-KV30",
    ]
    assert items[3].noi_dung.startswith("triển khai D")


def test_extract_tham_muu_block_ignores_non_tham_muu_plan_mentions() -> None:
    narrative_text = (
        "1. Công tác đảm bảo an ninh chính trị, an toàn PCCC: Không. "
        "2. Công tác tham mưu: Báo cáo số 213/BC-KV30 ngày 05/4/2026 kết quả A; "
        "Báo cáo số 214/BC-KV30 ngày 05/4/2026 kết quả B; "
        "Báo cáo số 215/BC-KV30 ngày 05/4/2026 kết quả C. - "
        "Kế hoạch số 39/KH-KV 30 ngày 05/4/2026 triển khai D. "
        "3. Công tác kiểm tra PCCC: Không. "
        "12. Công tác khác: thực hiện theo kế hoạch số 13/KH-KV 30 ngày 06/02/2026."
    )

    block = BlockExtractionPipeline._extract_tham_muu_block_text(narrative_text)
    items = BlockExtractionPipeline._extract_cong_van_items_from_text(block)

    assert len(items) == 4
    assert [item.so_ky_hieu for item in items] == [
        "213/BC-KV30",
        "214/BC-KV30",
        "215/BC-KV30",
        "39/KH-KV30",
    ]


def test_count_cong_van_types_does_not_group_bao_cao_and_ke_hoach() -> None:
    items = BlockExtractionPipeline._extract_cong_van_items_from_text(
        "Báo cáo số 213/BC-KV30 ngày 05/4/2026 kết quả A; "
        "Báo cáo số 214/BC-KV30 ngày 05/4/2026 kết quả B; "
        "Báo cáo số 215/BC-KV30 ngày 05/4/2026 kết quả C. - "
        "Kế hoạch số 39/KH-KV 30 ngày 05/4/2026 triển khai D."
    )

    counters = BlockExtractionPipeline._count_cong_van_types(items)

    assert counters == {
        "tong_cong_van": 0,
        "tong_bao_cao": 3,
        "tong_ke_hoach": 1,
    }


def test_clean_cong_tac_an_ninh_text_removes_ccc_prefix() -> None:
    assert BlockExtractionPipeline._clean_cong_tac_an_ninh_text("CCC: Không") == "Không"


def test_parse_narrative_fallback_keeps_document_type_counters_for_0604() -> None:
    pipeline = BlockExtractionPipeline()
    text = (
        "1. Công tác đảm bảo an ninh chính trị, an toàn PCCC: CCC: Không. "
        "2. Công tác tham mưu: Trong ngày tham mưu 03 báo cáo, 01 kế hoạch, cụ thể: "
        "Báo cáo số 213/BC-KV30 ngày 05/4/2026 kết quả A; "
        "Báo cáo số 214/BC-KV30 ngày 05/4/2026 kết quả B; "
        "Báo cáo số 215/BC-KV30 ngày 05/4/2026 kết quả C. - "
        "Kế hoạch số 39/KH-KV 30 ngày 05/4/2026 triển khai D. "
        "3. Công tác kiểm tra PCCC: Không."
    )

    parsed = pipeline._parse_phan_nghiep_vu_fallback(text)

    assert parsed.tong_cong_van == 0
    assert parsed.tong_bao_cao == 3
    assert parsed.tong_ke_hoach == 1
    assert parsed.cong_tac_an_ninh.startswith("Không")


def test_inject_computed_rows_derives_stt60_from_stt55_formula() -> None:
    rows = [
        ChiTieu(stt="55", noi_dung="Tổng số CBCS tham gia huấn luyện", ket_qua=27),
        ChiTieu(stt="56", noi_dung="Chỉ huy phòng", ket_qua=0),
        ChiTieu(stt="57", noi_dung="Chỉ huy Đội", ket_qua=1),
        ChiTieu(stt="58", noi_dung="Cán bộ tiểu đội", ket_qua=4),
        ChiTieu(stt="59", noi_dung="Chiến sỹ CC và CNCH", ket_qua=18),
        ChiTieu(stt="61", noi_dung="Lái tàu CC và CNCH", ket_qua=0),
    ]

    out = _inject_computed_bang_thong_ke_rows(rows)
    by_stt = {str(item.stt): int(item.ket_qua or 0) for item in out}

    assert by_stt["60"] == 4
    assert by_stt["55"] == (
        by_stt["56"] + by_stt["57"] + by_stt["58"] + by_stt["59"] + by_stt["60"] + by_stt["61"]
    )


def test_inject_computed_rows_derives_stt32_from_stt31_and_stt33() -> None:
    rows = [
        ChiTieu(stt="31", noi_dung="Số cơ sở được kiểm an toàn PCCC", ket_qua=12),
        ChiTieu(stt="33", noi_dung="Kiểm tra đột xuất theo chuyên đề", ket_qua=1),
    ]

    out = _inject_computed_bang_thong_ke_rows(rows)
    by_stt = {str(item.stt): int(item.ket_qua or 0) for item in out}

    assert by_stt["32"] == 11
    assert by_stt["31"] == by_stt["32"] + by_stt["33"]


def test_extract_table_grid_fallback_injects_missing_stt32() -> None:
    pipeline = BlockExtractionPipeline()
    table_text = (
        "31 Số cơ sở được kiểm an toàn PCCC (=STT 31+STT 33) 8\n"
        "33 Kiểm tra đột xuất theo chuyên đề 0\n"
    )

    parsed = pipeline._extract_table(table_stream=[], table_text=table_text)
    by_stt = {str(item.stt): int(item.ket_qua or 0) for item in parsed.danh_sach_chi_tieu}

    assert by_stt["32"] == 8
    assert by_stt["31"] == by_stt["32"] + by_stt["33"]
