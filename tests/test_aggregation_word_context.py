from app.services.aggregation_service import build_word_export_context


def test_build_word_export_context_keeps_all_records_and_selected_record() -> None:
    aggregated_data = {
        "records": [
            {"group": "A", "tong_so_vu_chay": 2},
            {"group": "B", "tong_so_vu_chay": 3},
        ],
        "tong_so_vu_chay": 5,
        "_source_records": [{"internal": True}],
        "_flat_records": [{"internal": True}],
        "_metadata": {"x": 1},
        "metrics": {"y": 2},
    }

    context = build_word_export_context(aggregated_data, record_index=1)

    assert len(context["records"]) == 2
    assert context["record"]["group"] == "B"
    assert context["record_index"] == 1
    assert context["tong_so_vu_chay"] == 5
    assert "_source_records" not in context
    assert "_flat_records" not in context
    assert "_metadata" not in context
    assert "metrics" not in context


def test_build_word_export_context_applies_extra_context_override() -> None:
    aggregated_data = {
        "records": [{"group": "A", "tong_so_vu_chay": 2}],
        "tong_so_vu_chay": 2,
    }

    context = build_word_export_context(
        aggregated_data,
        extra_context={"report_name": "Weekly", "tong_so_vu_chay": 999},
    )

    assert context["report_name"] == "Weekly"
    assert context["tong_so_vu_chay"] == 999
