# SYSTEM OVERVIEW

## 1. Purpose

Tự động hóa quy trình bóc tách dữ liệu có cấu trúc từ tài liệu PDF nghiệp vụ (báo cáo PCCC ngày), tổng hợp N báo cáo ngày thành 1 báo cáo tuần, và xuất ra file Word sử dụng template Jinja2.

## 2. Scope

**Xử lý:** Upload PDF → tách bảng/text (pdfplumber) → ép schema JSON (Ollama LLM, optional) → human review → tổng hợp (SUM/CONCAT/LAST) → xuất Word.

**Không xử lý:** Hỏi đáp tự do trên tài liệu (RAG/vector search đã bị xóa), nhận dạng hình ảnh (OCR), nhận dạng chữ viết tay, xử lý email/fax.

## 3. High-Level Architecture

```
MinIO (inbox/) → FileOperator → ExtractionJob → BlockPipeline (Stage 1, no LLM)
                                                        ↓
                                              enrich_job_task (Stage 2, Ollama async)
                                                        ↓
                                              Human Review (approve/reject)
                                                        ↓
                                           AggregationService (Pandas map-reduce)
                                                        ↓
                                           Word Export (docxtpl + Jinja2) → .docx
```

## 4. Core Components

| Component | File | Vai trò |
|---|---|---|
| **FastAPI API** | `app/main.py` | 33 HTTP endpoints, JWT auth, multi-tenant |
| **BlockExtractionPipeline** | `engines/extraction/block_pipeline.py` | Stage 1: pdfplumber + regex, không LLM |
| **enrich_job_task** | `worker/enrichment_tasks.py` | Stage 2: Ollama LLM, async, fire-and-forget |
| **ExtractionOrchestrator** | `engines/extraction/orchestrator.py` | Dispatch stage 1 → stage 2, persist results |
| **AggregationService** | `application/aggregation_service.py` | Pandas json_normalize + SUM/CONCAT/LAST |
| **Word Export** | `utils/word_export.py` | docxtpl renderer + anti zip-bomb |
| **FileOperator** | `worker/operator_tasks.py` | Poll MinIO inbox/, auto-detect template, tạo job |
| **BatchCloser** | `worker/operator_tasks.py` | Auto-close batch khi xong, trigger aggregation |
| **DocumentTemplate (YAML)** | `domain/templates/pccc.yaml` | Tất cả regex/pattern nghiệp vụ, không hardcode |
| **Celery** | `worker/celery_app.py` | 4 queues: `extraction`, `enrichment`, `default`, `document_processing` |
| **PostgreSQL** | SQLAlchemy + JSONB | Relational schema + JSONB cho extracted_data/aggregated_data |
| **MinIO** | S3-compatible | Lưu PDF gốc và Word template |
| **Streamlit UI** | `ui/streamlit_app.py` | Giao diện quản lý template, job, review, export |

## 5. Processing Flow

```
1. [Upload]     User upload PDF qua API hoặc FileOperator tự lấy từ MinIO inbox/
2. [Job]        ExtractionJob tạo với status=PENDING, đẩy vào Celery queue "extraction"
3. [Stage 1]    BlockExtractionPipeline.run_stage1_from_bytes():
                  pdfplumber → block detect → header/narrative/table regex → business rules
                  → job.status=EXTRACTED, job.enrichment_status=PENDING
4. [Stage 2]    enrich_job_task (queue "enrichment", async):
                  đọc chi_tiet_cnch → Ollama qwen2.5:7b-instruct → CNCHListOutput
                  → job.enriched_data = {"danh_sach_cnch": [...]}
                  Thất bại → enrichment_status=FAILED, job vẫn dùng được
5. [Review]     Human approve/reject qua UI hoặc API
6. [Aggregate]  Settlement gate kiểm tra tất cả enrichment settled → Pandas map-reduce
                  → AggregationReport.aggregated_data (JSONB)
7. [Export]     render_aggregation_to_word() → docxtpl + Jinja2 → file .docx stream
```

## 6. Data Authority

- **Ground truth cho schema**: `extraction_templates.schema_definition` (JSONB) — do admin định nghĩa qua scan Word hoặc nhập tay.
- **Ground truth cho dữ liệu báo cáo**: `extraction_jobs.final_data` = `reviewed_data` > `(extracted_data + enriched_data merged)` > `extracted_data`. Human review luôn thắng LLM.
- **Regex/pattern nghiệp vụ**: `app/domain/templates/pccc.yaml` — file duy nhất, không hardcode trong code.
- **LLM (Ollama)**: chỉ là optimization layer cho Stage 2 (danh sách CNCH). Mất Ollama → Stage 1 data vẫn đủ dùng.

## 7. System Characteristics

- **Two-stage extraction**: Stage 1 deterministic (không LLM, trả kết quả ngay), Stage 2 LLM async (enrichment).
- **LLM not on critical path**: Ollama chết → job vẫn EXTRACTED, aggregate vẫn chạy được.
- **Enrichment settlement gate**: Aggregate bị block khi bất kỳ job nào còn PENDING/RUNNING enrichment.
- **Multi-tenant**: mọi query đều scoped theo `tenant_id`.
- **YAML-driven patterns**: 55+ regex/pattern nằm ngoài code, trong `pccc.yaml`.
- **Hot-folder automation**: FileOperator poll MinIO inbox/ mỗi 120s, tự match template theo `filename_pattern` regex.
- **Auto-aggregation**: BatchCloser poll mỗi 180s, tự trigger aggregate khi batch hoàn tất.

## 8. Non-Goals

- Không hỏi đáp tự do trên tài liệu (no RAG, no vector search).
- Không xử lý hình ảnh hay OCR scan.
- Không hỗ trợ real-time streaming extraction.
- Không tích hợp với hệ thống bên ngoài (email, ERP, DMS).
- Không tự học hay fine-tune model từ dữ liệu người dùng.

## 9. Success Criteria

- Upload 7 PDF báo cáo PCCC ngày → 1 báo cáo tuần Word trong ≤ 10 phút (bao gồm Stage 2 LLM).
- Stage 1 trả kết quả trong ≤ 30 giây mỗi file; Stage 2 không ảnh hưởng đến thời gian Stage 1.
- Tắt Ollama hoàn toàn → hệ thống vẫn upload, extract (Stage 1), review, và aggregate bình thường.
- Word export từ template mẫu cho ra file đúng định dạng, đúng số liệu tổng hợp.
