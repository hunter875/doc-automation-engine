# Hybrid Extraction Pipeline (pdfplumber + Python + LLM)

Pipeline mới nằm ở `app/services/hybrid_extraction_pipeline.py`, chia thành 4 chặng:

1. **Ingest**: Dùng `pdfplumber` tách 2 luồng độc lập (text + table).
2. **Normalization**:
   - Dọn text theo regex: nếu cuối dòng không phải `.` hoặc `:` thì nối dòng bằng khoảng trắng.
   - Bỏ các dòng nhiễu như `Nơi nhận:` và `KT. ĐỘI TRƯỞNG`.
   - Ép phẳng bảng thành dòng `Chỉ tiêu: Giá trị`.
3. **Inference**: Dùng `instructor` + `Pydantic` (`HybridExtractionOutput`) để ép output JSON từ Ollama (`qwen2.5:7b`), `temperature=0`.
4. **Validation & Retry**:
   - Check `stt_14_tong_cnch == len(danh_sach_cnch)`.
   - Check date format `dd/mm/yyyy`.
   - Sai logic thì retry tối đa `HYBRID_MAX_RETRIES` lần; quá giới hạn thì move file sang `HYBRID_MANUAL_REVIEW_DIR` (mặc định `Needs_Manual_Review`).

## Chạy nhanh

```bash
python -m app.services.hybrid_extraction_runner /path/to/file.pdf
```

## Biến môi trường

- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_API_KEY` (default: `ollama`)
- `OLLAMA_MODEL` (default: `qwen2.5:7b`)
- `HYBRID_MAX_RETRIES` (default: `3`)
- `HYBRID_MANUAL_REVIEW_DIR` (default: `Needs_Manual_Review`)

## Test

```bash
pytest -q tests/test_hybrid_extraction_pipeline.py
```
