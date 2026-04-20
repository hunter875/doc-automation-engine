from __future__ import annotations

from app.engines.extraction.sheet_pipeline import SheetExtractionPipeline


def test_sheet_pipeline_uses_yaml_aliases_for_header_and_bang_thong_ke() -> None:
    pipeline = SheetExtractionPipeline()

    result = pipeline.run(
        {
            "header": {
                "report_no": "02/BC-TEST",
                "report_date": "20/04/2026",
                "report_period": "01/04/2026 - 20/04/2026",
                "unit": "Đội CNCH Test",
            },
            "bang_thong_ke": [
                {"id": "14", "name": "Tổng số vụ CNCH", "value": "3"},
            ],
        }
    )

    assert result.status == "ok"
    assert result.output is not None

    payload = result.output.model_dump()
    assert payload["header"]["so_bao_cao"] == "02/BC-TEST"
    assert payload["header"]["ngay_bao_cao"] == "20/04/2026"
    assert payload["header"]["thoi_gian_tu_den"] == "01/04/2026 - 20/04/2026"
    assert payload["header"]["don_vi_bao_cao"] == "Đội CNCH Test"

    by_stt = {str(item["stt"]): int(item.get("ket_qua") or 0) for item in payload["bang_thong_ke"]}
    assert by_stt.get("14") == 3
    assert payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_cnch"] == 3


def test_sheet_pipeline_uses_yaml_fields_for_cnch_list() -> None:
    pipeline = SheetExtractionPipeline()

    result = pipeline.run(
        {
            "danh_sach_cnch": [
                {
                    "STT": 1,
                    "Ngày xảy ra sự cố": "20/04/2026",
                    "Thời gian đến": "09:30",
                    "Địa điểm": "Phường 1",
                    "Loại hình CNCH": "Cứu nạn giao thông",
                    "Thiệt hại về người": "0",
                    "Số người cứu được": "2",
                }
            ]
        }
    )

    assert result.status == "ok"
    assert result.output is not None
    payload = result.output.model_dump()

    assert len(payload["danh_sach_cnch"]) == 1
    item = payload["danh_sach_cnch"][0]
    assert int(item["stt"]) == 1
    assert item["ngay_xay_ra"] == "20/04/2026"
    assert item["thoi_gian"] == "09:30"
    assert item["dia_diem"] == "Phường 1"
    assert item["noi_dung_tin_bao"] == "Cứu nạn giao thông"
    assert item["thiet_hai"] == "0"
    assert item["thong_tin_nan_nhan"] == "2"


def test_sheet_pipeline_supports_ingestion_row_document_shape() -> None:
    pipeline = SheetExtractionPipeline()

    result = pipeline.run(
        {
            "source": "google_sheet",
            "sheet_id": "sheet-1",
            "worksheet": "WS",
            "row_index": 8,
            "row_hash": "abc",
            "data": {
                "report_no": "03/BC-ING",
                "report_date": "21/04/2026",
                "report_period": "20/04/2026 - 21/04/2026",
                "unit": "Đội CNCH Ingestion",
                "tong_so_vu_chay": 2,
                "tong_so_vu_no": 1,
                "tong_so_vu_cnch": 4,
            },
        }
    )

    assert result.status == "ok"
    assert result.output is not None
    payload = result.output.model_dump()

    assert payload["header"]["so_bao_cao"] == "03/BC-ING"
    assert payload["header"]["ngay_bao_cao"] == "21/04/2026"
    assert payload["header"]["thoi_gian_tu_den"] == "20/04/2026 - 21/04/2026"
    assert payload["header"]["don_vi_bao_cao"] == "Đội CNCH Ingestion"

    assert payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_chay"] == 2
    assert payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_no"] == 1
    assert payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_cnch"] == 4

    by_stt = {str(item["stt"]): int(item.get("ket_qua") or 0) for item in payload["bang_thong_ke"]}
    assert by_stt.get("2") == 2
    assert by_stt.get("8") == 1
    assert by_stt.get("14") == 4
