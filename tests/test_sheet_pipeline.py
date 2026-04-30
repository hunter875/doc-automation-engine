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


def test_sheet_pipeline_custom_schema_does_not_use_global_mapping(tmp_path, monkeypatch) -> None:
    def _boom():
        raise AssertionError("_load_sheet_mapping should not be called in custom schema mode")

    monkeypatch.setattr("app.engines.extraction.sheet_pipeline._load_sheet_mapping", _boom)

    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(
        """sheet_mapping:
  header:
    fields:
      so_bao_cao: [so_bao_cao]
""",
        encoding="utf-8",
    )

    pipeline = SheetExtractionPipeline()
    result = pipeline.run({"data": {"so_bao_cao": "01/BC"}}, schema_path=str(schema_path))

    assert result.status == "ok"
    assert result.output is not None
    payload = result.output.model_dump()
    assert payload["header"]["so_bao_cao"] == "01/BC"


def test_sheet_pipeline_legacy_mode_uses_global_mapping(monkeypatch) -> None:
    called = {"value": False}

    def _fake():
        called["value"] = True
        return {}

    monkeypatch.setattr("app.engines.extraction.sheet_pipeline._load_sheet_mapping", _fake)

    pipeline = SheetExtractionPipeline()
    result = pipeline.run({"header": {"report_no": "01/BC"}})

    assert result.status == "ok"
    assert called["value"] is True


def test_kv30_bc_ngay_schema(tmp_path) -> None:
    """Test BC NGÀY KV30 template with header fields and nghiep_vu."""
    schema_path = tmp_path / "bc_ngay_kv30.yaml"
    schema_path.write_text(
        """sheet_mapping:
  header:
    fields:
      ngay_bao_cao_day:
        aliases: ["NGÀY", "ngày", "Ngay"]
        type: integer
      ngay_bao_cao_month:
        aliases: ["THÁNG", "tháng", "Thang"]
        type: integer
  nghiep_vu:
    fields:
      tong_so_vu_chay:
        aliases: ["VỤ CHÁY THỐNG KÊ", "VỤ CHÁY", "vu_chay"]
        type: integer
      tong_chi_vien:
        aliases: ["CHI VIỆN", "chi_vien"]
        type: integer
""",
        encoding="utf-8",
    )

    pipeline = SheetExtractionPipeline()
    result = pipeline.run(
        {
            "data": {
                "NGÀY": 29,
                "THÁNG": 4,
                "VỤ CHÁY THỐNG KÊ": 5,
                "CHI VIỆN": 3,
            }
        },
        schema_path=str(schema_path),
    )

    assert result.status == "ok"
    assert result.output is not None
    payload = result.output.model_dump()
    assert payload["header"]["ngay_bao_cao"] == "29/04/2026"  # year default 2026
    assert payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_so_vu_chay"] == 5
    assert payload["phan_I_va_II_chi_tiet_nghiep_vu"]["tong_chi_vien"] == 3


def test_kv30_chi_vien_schema(tmp_path) -> None:
    """Test CHI VIỆN KV30 template with danh_sach_chi_vien.fields."""
    schema_path = tmp_path / "chi_vien_kv30.yaml"
    schema_path.write_text(
        """sheet_mapping:
  danh_sach_chi_vien:
    fields:
      stt:
        aliases: ["STT", "stt"]
        type: integer
      ngay:
        aliases: ["VỤ CHÁY NGÀY", "Vụ cháy ngày", "NGÀY"]
        type: string
      dia_diem:
        aliases: ["ĐỊA ĐIỂM", "Dia diem"]
        type: string
      khu_vuc_quan_ly:
        aliases: ["KHU VỰC QUẢN LÝ", "Khu vực quản lý", "KHU VỰC"]
        type: string
      so_luong_xe:
        aliases: ["SỐ LƯỢNG XE", "Số lượng xe", "SỐ XE"]
        type: integer
      thoi_gian_di:
        aliases: ["THỜI GIAN ĐI", "Thời gian đi"]
        type: string
      thoi_gian_ve:
        aliases: ["THỜI GIAN VỀ", "Thời gian về"]
        type: string
      chi_huy_chua_chay:
        aliases: ["CHỈ HUY CHỮA CHÁY", "Chỉ huy chữa cháy", "CHỈ HUY"]
        type: string
      ghi_chu:
        aliases: ["GHI CHÚ", "Ghi chú"]
        type: string
""",
        encoding="utf-8",
    )

    pipeline = SheetExtractionPipeline()
    result = pipeline.run(
        {
            "danh_sach_chi_vien": [
                {
                    "STT": 1,
                    "NGÀY": "29/04",
                    "ĐỊA ĐIỂM": "Phường A",
                    "KHU VỰC": "KV1",
                    "SỐ LƯỢNG XE": 2,
                    "CHỈ HUY": "Cảnh sát viên A",
                }
            ]
        },
        schema_path=str(schema_path),
    )

    assert result.status == "ok"
    assert result.output is not None
    payload = result.output.model_dump()
    assert len(payload["danh_sach_chi_vien"]) == 1
    item = payload["danh_sach_chi_vien"][0]
    assert item["stt"] == 1
    assert item["ngay"] == "29/04"
    assert item["dia_diem"] == "Phường A"
    assert item["khu_vuc_quan_ly"] == "KV1"
    assert item["so_luong_xe"] == 2
    assert item["chi_huy_chua_chay"] == "Cảnh sát viên A"


def test_kv30_cnch_schema(tmp_path) -> None:
    """Test CNCH KV30 template with danh_sach_cnch.fields."""
    schema_path = tmp_path / "cnch_kv30.yaml"
    schema_path.write_text(
        """sheet_mapping:
  danh_sach_cnch:
    fields:
      stt:
        aliases: ["STT", "stt"]
        type: integer
      noi_dung_tin_bao:
        aliases: ["Loại hình CNCH", "LOẠI HÌNH CNCH", "loai_hinh"]
        type: string
      ngay_xay_ra:
        aliases: ["Ngày xảy ra sự cố", "NGÀY XẢY RA", "ngay"]
        type: string
      thoi_gian:
        aliases: ["Thời gian đến", "THỜI GIAN ĐẾN", "thoi_gian"]
        type: string
      dia_diem:
        aliases: ["Địa điểm", "ĐỊA ĐIỂM", "dia_diem"]
        type: string
      thiet_hai:
        aliases: ["Thiệt hại về người", "THIỆT HẠI VỀ NGƯỜI", "thiet_hai"]
        type: string
      so_nguoi_cuu:
        aliases: ["Số người cứu được", "SỐ NGƯỜI CỨU ĐƯỢC", "so_cuu"]
        type: integer
""",
        encoding="utf-8",
    )

    pipeline = SheetExtractionPipeline()
    result = pipeline.run(
        {
            "danh_sach_cnch": [
                {
                    "STT": 1,
                    "Loại hình CNCH": "Cứu nạn giao thông",
                    "Ngày xảy ra sự cố": "20/04/2026",
                    "Thời gian đến": "09:30",
                    "Địa điểm": "Phường 1",
                    "Thiệt hại về người": "0",
                    "Số người cứu được": 2,
                }
            ]
        },
        schema_path=str(schema_path),
    )

    assert result.status == "ok"
    assert result.output is not None
    payload = result.output.model_dump()
    assert len(payload["danh_sach_cnch"]) == 1
    item = payload["danh_sach_cnch"][0]
    assert int(item["stt"]) == 1
    assert item["noi_dung_tin_bao"] == "Cứu nạn giao thông"
    assert item["ngay_xay_ra"] == "20/04/2026"
    assert item["thoi_gian"] == "09:30"
    assert item["dia_diem"] == "Phường 1"
    assert item["thiet_hai"] == "0"
    assert item["so_nguoi_cuu"] == 2


def test_kv30_vu_chay_schema(tmp_path) -> None:
    """Test VỤ CHÁY KV30 template with danh_sach_chay.fields."""
    schema_path = tmp_path / "vu_chay_kv30.yaml"
    schema_path.write_text(
        """sheet_mapping:
  danh_sach_chay:
    fields:
      stt:
        aliases: ["STT", "stt"]
        type: integer
      ngay_xay_ra:
        aliases: ["NGÀY XẢY RA VỤ CHÁY", "NGÀY XẢY RA", "Ngày xảy ra vụ cháy", "Ngày xảy ra", "Ngay xay ra", "ngay"]
        type: string
      thoi_gian:
        aliases: ["THỜI GIAN", "Thời gian", "Thoi gian", "thoi_gian"]
        type: string
      ten_vu_chay:
        aliases: ["VỤ CHÁY", "Vụ cháy", "Vu chay", "ten_vu"]
        type: string
      dia_diem:
        aliases: ["ĐỊA ĐIỂM", "Địa điểm", "Dia diem", "dia_diem"]
        type: string
      nguyen_nhan:
        aliases: ["NGUYÊN NHÂN", "Nguyên nhân", "Nguyen nhan", "nguyen_nhan"]
        type: string
      thiet_hai_nguoi:
        aliases: ["THIỆT HẠI VỀ NGƯỜI", "Thiệt hại về người", "THIỆT HẠI", "Thiet hai nguoi", "Thiet hai", "thiet_hai"]
        type: string
      thoi_gian_khong_che:
        aliases: ["THỜI GIAN KHỐNG CHẾ", "Thời gian khống chế", "THỜI GIAN KHĐNG CHẾ"]
        type: string
      chi_huy:
        aliases: ["CHỈ HUY CHỮA CHÁY", "CHỈ HUY", "Chỉ huy chữa cháy", "Chi huy"]
        type: string
""",
        encoding="utf-8",
    )

    pipeline = SheetExtractionPipeline()
    result = pipeline.run(
        {
            "danh_sach_chay": [
                {
                    "STT": 1,
                    "NGÀY XẢY RA VỤ CHÁY": "29/04/2026",
                    "THỜI GIAN": "14:30",
                    "VỤ CHÁY": "Cháy nhà trọ",
                    "ĐỊA ĐIỂM": "Phường B",
                    "NGUYÊN NHÂN": "Điện chập",
                    "THIỆT HẠI VỀ NGƯỜI": "0",
                    "THỜI GIAN KHỐNG CHẾ": "15:45",
                    "CHỈ HUY": "Trung úy A",
                }
            ]
        },
        schema_path=str(schema_path),
    )

    assert result.status == "ok"
    assert result.output is not None
    payload = result.output.model_dump()
    assert len(payload["danh_sach_chay"]) == 1
    item = payload["danh_sach_chay"][0]
    assert item["stt"] == 1
    assert item["ngay_xay_ra"] == "29/04/2026"
    assert item["thoi_gian"] == "14:30"
    assert item["ten_vu_chay"] == "Cháy nhà trọ"
    assert item["dia_diem"] == "Phường B"
    assert item["nguyen_nhan"] == "Điện chập"
    assert item["thiet_hai_nguoi"] == "0"
    assert item["thoi_gian_khong_che"] == "15:45"
    assert item["chi_huy"] == "Trung úy A"
