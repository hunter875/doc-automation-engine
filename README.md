# Doc Automation Engine

Hệ thống tự động bóc tách dữ liệu có cấu trúc từ báo cáo PCCC ngày (PDF), tổng hợp N báo cáo thành 1 báo cáo tuần, và xuất file Word theo template.

## Tổng quan

```
PDF (báo cáo ngày)
    │
    ▼
[Stage 1] BlockExtractionPipeline — pdfplumber + regex (không LLM, ~vài giây)
    │
    ▼
[Stage 2] enrich_job_task — Ollama LLM async (chỉ trích CNCH, optional)
    │
    ▼
Human Review (approve / reject / edit)
    │
    ▼
AggregationService — Pandas map-reduce (SUM / CONCAT / LAST)
    │
    ▼
Word Export — docxtpl + Jinja2 → .docx
```

**Điểm quan trọng:** LLM không nằm trên critical path. Tắt Ollama hoàn toàn → hệ thống vẫn extract, review và aggregate bình thường.

---

## Tech Stack

| Layer | Công nghệ |
|---|---|
| API | FastAPI + Pydantic v2 |
| Task queue | Celery + Redis |
| Database | PostgreSQL + JSONB (SQLAlchemy) |
| Object storage | MinIO (S3-compatible) |
| PDF parsing | pdfplumber |
| LLM (optional) | Ollama (`qwen2.5:7b-instruct`) via Instructor |
| Word export | docxtpl + Jinja2 |
| UI | Streamlit (legacy) |
| Container | Docker Compose |

---

## Cấu trúc dự án

```
app/
├── main.py                        # FastAPI app, 33 endpoints
├── api/v1/                        # Routers: auth, document, extraction, jobs, templates, tenant, aggregation
├── application/                   # Services: job, doc, auth, aggregation, extraction, review, template
├── core/                          # Config, exceptions, security, logging, tracing
├── domain/
│   ├── models/                    # SQLAlchemy models: ExtractionJob, Document, Tenant, User
│   ├── rules/                     # RuleEngine, validation rules, extractors, normalizers
│   ├── templates/pccc.yaml        # ★ Tất cả regex/pattern nghiệp vụ — không hardcode trong code
│   └── workflow.py                # State machine: JobStatus + transition_job_state()
├── engines/extraction/
│   ├── block_pipeline.py          # ★ Stage 1 deterministic pipeline (không LLM)
│   ├── orchestrator.py            # Dispatch Stage 1 → Stage 2
│   └── schemas.py                 # BlockExtractionOutput, CNCHItem, PipelineResult
├── infrastructure/
│   ├── db/                        # Session, base, migrations
│   ├── llm/                       # Ollama extractor
│   ├── storage/                   # MinIO client
│   └── worker/
│       ├── celery_app.py          # 4 queues: extraction, enrichment, default, document_processing
│       ├── enrichment_tasks.py    # ★ Stage 2 LLM enrichment (Celery task)
│       └── operator_tasks.py      # FileOperator (hot-folder) + BatchCloser
├── schemas/                       # Pydantic request/response schemas
└── utils/                         # word_export, pdf_utils, file_utils, metrics
docs/
├── SYSTEM_OVERVIEW.md
├── DATA_CONTRACT.md
├── engine2_technical_spec.md
├── API_REFERENCE.md
└── OPERATIONS.md
tests/                             # pytest, 60% coverage minimum
ui/                                # Streamlit UI (legacy)
scripts/                           # Migration scripts
```

---

## Chạy nhanh với Docker Compose

### 1. Yêu cầu

- Docker Desktop
- Ollama chạy trên host (optional — hệ thống hoạt động không cần)

### 2. Khởi động

```bash
# Copy env mẫu
cp .env.example .env

# Build và start tất cả services
docker compose up -d --build

# Kiểm tra trạng thái
docker compose ps
```

### 3. Services

| Container | Địa chỉ | Vai trò |
|---|---|---|
| `rag-api` | http://localhost:8000 | FastAPI — API chính |
| `rag-streamlit` | http://localhost:8501 | Streamlit UI (legacy, cần `--profile legacy`) |
| `rag-celery-extraction` | — | Celery worker: queue `extraction`, concurrency=1 |
| `rag-celery-enrichment` | — | Celery worker: queue `enrichment`, concurrency=2 |
| `rag-celery-worker` | — | Celery worker: queues `default`, `document_processing` |
| `rag-celery-beat` | — | Celery beat scheduler |
| `rag-postgres` | localhost:5432 | PostgreSQL |
| `rag-redis` | localhost:6379 | Redis (broker + result backend) |
| `rag-minio` | http://localhost:9001 | MinIO console |

### 4. Biến môi trường quan trọng

Tạo file `.env` từ bảng sau:

```env
# JWT
JWT_SECRET_KEY=change-this-in-production-use-256-bit-key

# Ollama (optional)
OLLAMA_MODEL=qwen2.5:7b-instruct
EXTRACTION_BACKEND=ollama          # hoặc "gemini"

# Gemini (nếu không dùng Ollama)
GEMINI_API_KEY=
GEMINI_FLASH_MODEL=gemini-2.5-flash

# PostgreSQL (mặc định khớp docker-compose)
POSTGRES_HOST=postgres
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpassword
POSTGRES_DB=ragdb

# MinIO (mặc định khớp docker-compose)
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-documents
```

---

## API cơ bản

Tài liệu Swagger tự động: **http://localhost:8000/docs**

### Luồng chính

```bash
# 1. Đăng nhập
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin1234!"}' | jq .access_token

# 2. Upload PDF + tạo job extraction (một lệnh)
curl -s -X POST http://localhost:8000/api/v1/extraction/jobs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  -F "file=@./report.pdf;type=application/pdf" \
  -F "template_id=<TEMPLATE_ID>" \
  -F "mode=block"

# 3. Kiểm tra trạng thái job
curl -s http://localhost:8000/api/v1/extraction/jobs/<JOB_ID> \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>"

# 4. Aggregate N jobs đã approved
curl -s -X POST http://localhost:8000/api/v1/aggregation/reports \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  -H "Content-Type: application/json" \
  -d '{"job_ids":["<JOB_1>","<JOB_2>"],"name":"Báo cáo tuần"}'

# 5. Xuất Word
curl -s -X GET http://localhost:8000/api/v1/aggregation/reports/<REPORT_ID>/word \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  --output report.docx
```

---

## Extracted Data Schema

`extracted_data` trong DB luôn là **canonical nested JSON** với 7 top-level key:

```json
{
  "header":                          { "so_bao_cao", "ngay_bao_cao", "thoi_gian_tu_den", "don_vi_bao_cao" },
  "phan_I_va_II_chi_tiet_nghiep_vu": { "tong_so_vu_chay", "tong_so_vu_cnch", "quan_so_truc", ... },
  "bang_thong_ke":                   [ { "stt", "noi_dung", "ket_qua" } ],
  "danh_sach_cnch":                  [ { "stt", "thoi_gian", "dia_diem", "noi_dung_tin_bao", ... } ],
  "danh_sach_phuong_tien_hu_hong":   [ { "bien_so", "tinh_trang" } ],
  "danh_sach_cong_van_tham_muu":     [ { "so_ky_hieu", "noi_dung" } ],
  "danh_sach_cong_tac_khac":         [ "string" ]
}
```

Flat key (`stt_02_tong_chay`, `tu_ngay`, ...) chỉ tồn tại **in-memory** tại bước aggregation và trong `aggregated_data`. Không bao giờ lưu vào `extracted_data`.

---

## Data Priority Chain

```
reviewed_data  >  (extracted_data + enriched_data[danh_sach_cnch])  >  extracted_data
     ▲                        ▲                       ▲
  Human edit             Stage 1 regex           Stage 2 Ollama LLM
  (always wins)          (always present)        (optional, async)
```

---

## Celery Workers

Khi sửa code, phải rebuild **tất cả** Celery workers (extraction chạy trong worker, không phải API):

```bash
docker compose build api celery-extraction-worker celery-enrichment-worker celery-worker celery-beat
docker compose up -d api celery-extraction-worker celery-enrichment-worker celery-worker celery-beat
```

| Worker | Queue | Concurrency | Vai trò |
|---|---|---|---|
| `rag-celery-extraction` | `extraction` | 1 | Chạy Stage 1 pdfplumber pipeline |
| `rag-celery-enrichment` | `enrichment` | 2 | Chạy Stage 2 Ollama LLM (CNCH) |
| `rag-celery-worker` | `default`, `document_processing` | 4 | FileOperator, BatchCloser, misc |
| `rag-celery-beat` | — | — | Scheduler: cleanup stuck jobs, auto-aggregate |

---

## Hot-folder Automation

Đặt PDF vào MinIO `inbox/` → FileOperator tự động:
1. Phát hiện file mới mỗi 120 giây
2. Match template theo `filename_pattern` regex
3. Tạo ExtractionJob và dispatch vào queue `extraction`
4. BatchCloser tự trigger aggregate khi tất cả job trong batch hoàn tất (poll mỗi 180s)

---

## Chạy tests

```bash
# Trong container
docker exec rag-api pytest tests/ -v

# Local (cần đủ env)
pytest tests/ -v --tb=short

# Coverage
pytest tests/ --cov=app --cov-report=term-missing
```

---

## Tài liệu kỹ thuật

| File | Nội dung |
|---|---|
| [docs/SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md) | Kiến trúc tổng quan, data authority, success criteria |
| [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | Schema chi tiết, write isolation rules, failure handling |
| [docs/engine2_technical_spec.md](docs/engine2_technical_spec.md) | Two-stage pipeline, enrichment settlement gate, aggregation |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Tất cả 33 endpoints, request/response format |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Vận hành, monitoring, troubleshooting |
