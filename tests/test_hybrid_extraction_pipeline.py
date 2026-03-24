from __future__ import annotations

import json
from pathlib import Path

from app.schemas.hybrid_extraction_schema import CNCHItem, HybridExtractionOutput
from app.services.hybrid_extraction_pipeline import (
    HybridExtractionPipeline,
    IngestedDocument,
    IngestedPage,
)
from app.services.rule_engine import build_default_hybrid_rule_engine


def _sample_ingested() -> IngestedDocument:
    table_rows = [
        ["STT", "DANH MỤC", "KẾT QUẢ", "GHI CHÚ"],
        ["14", "3. Tổng số vụ tai nạn, sự cố", "01", None],
        ["15", "Số người bị nạn", "02", ""],
    ]
    text_blob = (
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Báo cáo nhanh\n"
        "Địa điểm xảy ra,\n"
        "Quận 1, TP.HCM\n"
        "Dòng này bị ngắt\n"
        "vẫn phải nối\n"
        "Diễn biến chính;\n"
        "Dòng này giữ nguyên\n"
        "nối lại cho đúng.\n"
        "Nơi nhận:\n"
        "PC07\n"
        "Lưu: VT, HSCT.\n"
        "KT. ĐỘI TRƯỞNG\n"
        "PHÓ ĐỘI TRƯỞNG\n"
    )
    return IngestedDocument(
        text_stream=text_blob,
        table_stream=[table_rows],
        pages=[
            IngestedPage(
                page_number=1,
                text=text_blob,
                tables=[table_rows],
            )
        ]
    )


def test_normalization_cleans_noise_without_table_flattening() -> None:
    pipeline = HybridExtractionPipeline(inference_func=lambda *_: HybridExtractionOutput())
    normalized = pipeline.stage2_normalize(_sample_ingested())

    assert "CỘNG HÒA XÃ HỘI" not in normalized.cleaned_text
    assert "Nơi nhận:" not in normalized.cleaned_text
    assert "PC07" not in normalized.cleaned_text
    assert "Lưu: VT" not in normalized.cleaned_text
    assert "KT. ĐỘI TRƯỞNG" not in normalized.cleaned_text
    assert "PHÓ ĐỘI TRƯỞNG" not in normalized.cleaned_text

    assert "Địa điểm xảy ra, Quận 1, TP.HCM" in normalized.cleaned_text
    assert "Dòng này bị ngắt vẫn phải nối" in normalized.cleaned_text
    assert "Diễn biến chính;\nDòng này giữ nguyên" in normalized.cleaned_text

    assert normalized.clean_payload.startswith(
        "Dưới đây là thông tin báo cáo PCCC đã được chuẩn hóa. Tuyệt đối không tự suy diễn số liệu."
    )
    assert "Chỉ tiêu: 3. Tổng số vụ tai nạn, sự cố - Kết quả: 01" not in normalized.clean_payload


def test_retry_then_success(tmp_path: Path) -> None:
    pdf_path = tmp_path / "retry_success.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class RetryThenSuccessPipeline(HybridExtractionPipeline):
        def __init__(self) -> None:
            super().__init__(max_retries=3, rule_engine=build_default_hybrid_rule_engine())
            self.calls = 0

        def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:  # noqa: ARG002
            return _sample_ingested()

        def stage3_infer(self, normalized, validation_errors=None):  # noqa: ANN001, ARG002
            self.calls += 1
            if self.calls == 1:
                return HybridExtractionOutput.model_construct(
                    ngay_bao_cao="18/03/2026",
                    stt_14_tong_cnch=2,
                    tong_xe_hu_hong=0,
                    danh_sach_phuong_tien_hu_hong=[],
                    danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026", mo_ta="A")],
                )
            return HybridExtractionOutput(
                ngay_bao_cao="18/03/2026",
                stt_14_tong_cnch=1,
                tong_xe_hu_hong=0,
                danh_sach_phuong_tien_hu_hong=[],
                danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026", mo_ta="A")],
            )

    pipeline = RetryThenSuccessPipeline()
    result = pipeline.run(pdf_path)

    assert result.status == "ok"
    assert result.attempts == 2
    assert result.output is not None
    assert pipeline.calls == 2


def test_move_to_manual_review_after_max_retries(tmp_path: Path) -> None:
    pdf_path = tmp_path / "always_fail.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    manual_dir = tmp_path / "Needs_Manual_Review"

    class AlwaysInvalidPipeline(HybridExtractionPipeline):
        def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:  # noqa: ARG002
            return _sample_ingested()

        def stage3_infer(self, normalized, validation_errors=None):  # noqa: ANN001, ARG002
            return HybridExtractionOutput.model_construct(
                ngay_bao_cao="18-03-2026",
                stt_14_tong_cnch=5,
                tong_xe_hu_hong=0,
                danh_sach_phuong_tien_hu_hong=[],
                danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026", mo_ta="A")],
            )

    pipeline = AlwaysInvalidPipeline(
        max_retries=3,
        manual_review_dir=manual_dir,
        rule_engine=build_default_hybrid_rule_engine(),
    )
    result = pipeline.run(pdf_path)

    assert result.status == "needs_manual_review"
    assert result.attempts == 3
    assert result.manual_review_path is not None
    assert (manual_dir / "always_fail.pdf").exists()
    assert not pdf_path.exists()


def test_ingest_zero_data_scan_pdf_is_rejected(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan_like.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class EmptyTextPipeline(HybridExtractionPipeline):
        def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:  # noqa: ARG002
            return IngestedDocument(text_stream="", table_stream=[], pages=[])

    pipeline = EmptyTextPipeline()
    result = pipeline.run(pdf_path)

    assert result.status == "failed"
    assert result.attempts == 0
    assert result.errors
    assert "ERR_STAGE_INGEST" in result.errors[0]
    assert "Phát hiện PDF dạng Scan" in result.errors[0]


def test_stage3_system_prompt_is_strict_and_deterministic() -> None:
    pipeline = HybridExtractionPipeline(inference_func=lambda *_: HybridExtractionOutput())
    prompt = pipeline._build_stage3_system_prompt()

    assert "Chỉ trích xuất từ văn bản được cung cấp" in prompt
    assert "Tuyệt đối không suy đoán" in prompt
    assert "điền 0 với số" in prompt
    assert "mảng rỗng []" in prompt
    assert "chuỗi rỗng ''" in prompt
    assert "không dư key, không thiếu key" in prompt


def test_stage3_messages_include_clean_payload_anchor() -> None:
    pipeline = HybridExtractionPipeline(inference_func=lambda *_: HybridExtractionOutput())
    normalized = pipeline.stage2_normalize(_sample_ingested())

    user_prompt = pipeline._build_prompt(normalized, None)
    messages = pipeline._build_inference_messages(user_prompt)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Dưới đây là thông tin báo cáo PCCC đã được chuẩn hóa" in messages[1]["content"]


def test_stage4_rule_engine_rejects_cross_rule_mismatch() -> None:
    pipeline = HybridExtractionPipeline(rule_engine=build_default_hybrid_rule_engine())
    output = HybridExtractionOutput(
        ngay_bao_cao="18/03/2026",
        stt_14_tong_cnch=2,
        danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026")],
        tong_xe_hu_hong=0,
        danh_sach_phuong_tien_hu_hong=[],
    )

    errors = pipeline.stage4_validate(output)
    assert "ERR_CNCH_COUNT_MISMATCH" in errors


def test_stage4_manual_review_writes_sidecar_json(tmp_path: Path) -> None:
    pdf_path = tmp_path / "always_invalid.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    manual_dir = tmp_path / "Needs_Manual_Review"

    class AlwaysInvalidPipeline(HybridExtractionPipeline):
        def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:  # noqa: ARG002
            return _sample_ingested()

        def stage3_infer(self, normalized, validation_errors=None):  # noqa: ANN001, ARG002
            return HybridExtractionOutput.model_construct(
                ngay_bao_cao="18/03/2026",
                stt_14_tong_cnch=2,
                tong_xe_hu_hong=0,
                danh_sach_phuong_tien_hu_hong=[],
                danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026")],
            )

    pipeline = AlwaysInvalidPipeline(
        max_retries=2,
        manual_review_dir=manual_dir,
        rule_engine=build_default_hybrid_rule_engine(),
    )
    result = pipeline.run(pdf_path)

    assert result.status == "needs_manual_review"
    assert result.manual_review_path is not None
    assert result.manual_review_metadata_path is not None

    sidecar = Path(result.manual_review_metadata_path)
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["invalid_output"] is not None
    assert payload["errors"]


def test_stage4_commit_callback_called_on_success(tmp_path: Path) -> None:
    pdf_path = tmp_path / "commit_success.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    committed = {"called": False, "value": None}

    def _commit(output: HybridExtractionOutput) -> None:
        committed["called"] = True
        committed["value"] = output.stt_14_tong_cnch

    class SuccessPipeline(HybridExtractionPipeline):
        def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:  # noqa: ARG002
            return _sample_ingested()

        def stage3_infer(self, normalized, validation_errors=None):  # noqa: ANN001, ARG002
            return HybridExtractionOutput(
                ngay_bao_cao="18/03/2026",
                stt_14_tong_cnch=1,
                danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026")],
                tong_xe_hu_hong=0,
                danh_sach_phuong_tien_hu_hong=[],
            )

    pipeline = SuccessPipeline(
        commit_func=_commit,
        rule_engine=build_default_hybrid_rule_engine(),
    )
    result = pipeline.run(pdf_path)

    assert result.status == "ok"
    assert committed["called"] is True
    assert committed["value"] == 1


def test_run_from_bytes_success() -> None:
    class SuccessPipeline(HybridExtractionPipeline):
        def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:  # noqa: ARG002
            return _sample_ingested()

        def stage3_infer(self, normalized, validation_errors=None):  # noqa: ANN001, ARG002
            return HybridExtractionOutput(
                ngay_bao_cao="18/03/2026",
                stt_14_tong_cnch=1,
                danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026")],
                tong_xe_hu_hong=0,
                danh_sach_phuong_tien_hu_hong=[],
            )

    pipeline = SuccessPipeline(rule_engine=build_default_hybrid_rule_engine())
    result = pipeline.run_from_bytes(b"%PDF-1.4 fake", "from_s3.pdf")

    assert result.status == "ok"
    assert result.attempts == 1
    assert result.output is not None


def test_run_from_bytes_moves_to_manual_review(tmp_path: Path) -> None:
    manual_dir = tmp_path / "Needs_Manual_Review"

    class AlwaysInvalidPipeline(HybridExtractionPipeline):
        def stage1_ingest(self, pdf_bytes: bytes) -> IngestedDocument:  # noqa: ARG002
            return _sample_ingested()

        def stage3_infer(self, normalized, validation_errors=None):  # noqa: ANN001, ARG002
            return HybridExtractionOutput.model_construct(
                ngay_bao_cao="18/03/2026",
                stt_14_tong_cnch=2,
                tong_xe_hu_hong=0,
                danh_sach_phuong_tien_hu_hong=[],
                danh_sach_cnch=[CNCHItem(ngay_xay_ra="18/03/2026")],
            )

    pipeline = AlwaysInvalidPipeline(
        max_retries=2,
        manual_review_dir=manual_dir,
        rule_engine=build_default_hybrid_rule_engine(),
    )
    result = pipeline.run_from_bytes(b"%PDF-1.4 fake", "memory_fail.pdf")

    assert result.status == "needs_manual_review"
    assert result.manual_review_path is not None
    assert result.manual_review_metadata_path is not None
    assert (manual_dir / "memory_fail.pdf").exists()
