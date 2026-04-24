from app.application.aggregation_service import _normalize_master_payload


def test_master_payload_includes_empty_arrays_and_flat_scalars():
    schema_definition = {
        "fields": [
            {"name": "ngay_xuat", "type": "number"},
            {"name": "stt_02_tong_chay", "type": "number"},
            {"name": "tong_cong_van", "type": "number"},
            {
                "name": "danh_sach_cong_van_tham_muu",
                "type": "array",
                "items": {
                    "type": "object",
                    "fields": [
                        {"name": "ten_cong_van", "type": "string"},
                    ],
                },
            },
            {
                "name": "danh_sach_phuong_tien_hu_hong",
                "type": "array",
                "items": {
                    "type": "object",
                    "fields": [
                        {"name": "bien_so", "type": "string"},
                        {"name": "tinh_trang", "type": "string"},
                    ],
                },
            },
        ]
    }
    payload = {
        "ngay_xuat": 14,
        "stt_02_tong_chay": 3,
        "tong_cong_van": 0,
        "danh_sach_phuong_tien_hu_hong": [{"bien_so": "61A-003.52", "tinh_trang": "dang cho thay phuoc"}],
    }

    normalized = _normalize_master_payload(schema_definition, payload)

    assert normalized["ngay_xuat"] == 14
    assert normalized["stt_02_tong_chay"] == 3
    assert normalized["tong_cong_van"] == 0
    assert normalized["danh_sach_cong_van_tham_muu"] == []
    assert isinstance(normalized["danh_sach_phuong_tien_hu_hong"], list)
    assert normalized["danh_sach_phuong_tien_hu_hong"][0]["bien_so"] == "61A-003.52"
