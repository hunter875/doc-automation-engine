# Doc Automation Engine

Há»‡ thá»‘ng tá»± Ä‘á»™ng bÃ³c tÃ¡ch dá»¯ liá»‡u cÃ³ cáº¥u trÃºc tá»« bÃ¡o cÃ¡o PCCC ngÃ y (PDF), tá»•ng há»£p N bÃ¡o cÃ¡o thÃ nh 1 bÃ¡o cÃ¡o tuáº§n, vÃ  xuáº¥t file Word theo template.

## Tá»•ng quan

```
PDF (bÃ¡o cÃ¡o ngÃ y)
    â”‚
    â–¼
[Stage 1] BlockExtractionPipeline â€” pdfplumber + regex (khÃ´ng LLM, ~vÃ i giÃ¢y)
    â”‚
    â–¼
[Stage 2] enrich_job_task â€” Ollama LLM async (chá»‰ trÃ­ch CNCH, optional)
    â”‚
    â–¼
Human Review (approve / reject / edit)
    â”‚
    â–¼
AggregationService â€” Pandas map-reduce (SUM / CONCAT / LAST)
    â”‚
    â–¼
Word Export â€” docxtpl + Jinja2 â†’ .docx
```

**Äiá»ƒm quan trá»ng:** LLM khÃ´ng náº±m trÃªn critical path. Táº¯t Ollama hoÃ n toÃ n â†’ há»‡ thá»‘ng váº«n extract, review vÃ  aggregate bÃ¬nh thÆ°á»ng.

---

## Tech Stack

| Layer | CÃ´ng nghá»‡ |
|---|---|
| API | FastAPI + Pydantic v2 |
| Task queue | Celery + Redis |
| Database | PostgreSQL + JSONB (SQLAlchemy) |
| Object storage | MinIO (S3-compatible) |
| PDF parsing | pdfplumber |
| LLM (optional) | Ollama (`qwen2.5:7b-instruct`) via Instructor |
| Word export | docxtpl + Jinja2 |
| UI | Next.js frontend + Streamlit legacy profile |
| Container | Docker Compose |

---

## Cáº¥u trÃºc dá»± Ã¡n

```
app/
â”œâ”€â”€ main.py                        # FastAPI app
â”œâ”€â”€ api/v1/                        # Routers: auth, document, extraction, jobs, templates, tenant, aggregation
â”œâ”€â”€ application/                   # Services: job, doc, auth, aggregation, extraction, review, template
â”œâ”€â”€ core/                          # Config, exceptions, security, logging, tracing
â”œâ”€â”€ domain/
â”‚   â”œâ”€â”€ models/                    # SQLAlchemy models: ExtractionJob, Document, Tenant, User
â”‚   â”œâ”€â”€ rules/                     # RuleEngine, validation rules, extractors, normalizers
â”‚   â”œâ”€â”€ templates/pccc.yaml        # â˜… Táº¥t cáº£ regex/pattern nghiá»‡p vá»¥ â€” khÃ´ng hardcode trong code
â”‚   â””â”€â”€ workflow.py                # State machine: JobStatus + transition_job_state()
â”œâ”€â”€ engines/extraction/
â”‚   â”œâ”€â”€ block_pipeline.py          # â˜… Stage 1 deterministic pipeline (khÃ´ng LLM)
â”‚   â”œâ”€â”€ orchestrator.py            # Dispatch Stage 1 â†’ Stage 2
â”‚   â””â”€â”€ schemas.py                 # BlockExtractionOutput, CNCHItem, PipelineResult
â”œâ”€â”€ infrastructure/
â”‚   â”œâ”€â”€ db/                        # Session, base, migrations
â”‚   â”œâ”€â”€ llm/                       # Ollama extractor
â”‚   â”œâ”€â”€ storage/                   # MinIO client
â”‚   â””â”€â”€ worker/
â”‚       â”œâ”€â”€ celery_app.py          # 4 queues: extraction, enrichment, default, document_processing
â”‚       â”œâ”€â”€ enrichment_tasks.py    # â˜… Stage 2 LLM enrichment (Celery task)
â”‚       â””â”€â”€ operator_tasks.py      # FileOperator (hot-folder) + BatchCloser
â”œâ”€â”€ schemas/                       # Pydantic request/response schemas
â””â”€â”€ utils/                         # word_export, pdf_utils, file_utils, metrics
docs/
â”œâ”€â”€ SYSTEM_OVERVIEW.md
â”œâ”€â”€ DATA_CONTRACT.md
â”œâ”€â”€ engine2_technical_spec.md
â”œâ”€â”€ API_REFERENCE.md
â””â”€â”€ OPERATIONS.md
tests/                             # pytest, 60% coverage minimum
frontend/                          # Next.js UI
ui/                                # Streamlit UI (legacy profile)
scripts/                           # Migration scripts
```

---

## Cháº¡y nhanh vá»›i Docker Compose

### 1. YÃªu cáº§u

- Docker Desktop
- Ollama cháº¡y trÃªn host (optional â€” há»‡ thá»‘ng hoáº¡t Ä‘á»™ng khÃ´ng cáº§n)

### 2. Khá»Ÿi Ä‘á»™ng

```bash
# Copy env máº«u
cp .env.example .env

# Build vÃ  start táº¥t cáº£ services
docker compose up -d --build

# Kiá»ƒm tra tráº¡ng thÃ¡i
docker compose ps
```

### 3. Services

| Container | Äá»‹a chá»‰ | Vai trÃ² |
|---|---|---|
| `rag-api` | http://localhost:8000 | FastAPI â€” API chÃ­nh |
| `frontend` | http://localhost:3000 | Next.js UI |
| `rag-streamlit` | http://localhost:8501 | Streamlit UI (legacy, cáº§n `--profile legacy`) |
| `rag-celery-extraction` | â€” | Celery worker: queue `extraction`, concurrency=1 |
| `rag-celery-enrichment` | â€” | Celery worker: queue `enrichment`, concurrency=2 |
| `rag-celery-worker` | â€” | Celery worker: queues `default`, `document_processing` |
| `rag-celery-beat` | â€” | Celery beat scheduler |
| `rag-postgres` | localhost:5432 | PostgreSQL |
| `rag-redis` | localhost:6379 | Redis (broker + result backend) |
| `rag-minio` | http://localhost:9001 | MinIO console |

### 4. Biáº¿n mÃ´i trÆ°á»ng quan trá»ng

Táº¡o file `.env` tá»« báº£ng sau:

```env
# JWT
JWT_SECRET_KEY=change-this-in-production-use-256-bit-key

# Ollama (optional)
OLLAMA_MODEL=qwen2.5:7b-instruct
EXTRACTION_BACKEND=ollama          # hoáº·c "gemini"

# Gemini (náº¿u khÃ´ng dÃ¹ng Ollama)
GEMINI_API_KEY=
GEMINI_FLASH_MODEL=gemini-2.5-flash

# PostgreSQL (máº·c Ä‘á»‹nh khá»›p docker-compose)
POSTGRES_HOST=postgres
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpassword
POSTGRES_DB=ragdb

# MinIO (máº·c Ä‘á»‹nh khá»›p docker-compose)
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-documents
```

---

## API cÆ¡ báº£n

TÃ i liá»‡u Swagger tá»± Ä‘á»™ng: **http://localhost:8000/docs**

### Luá»“ng chÃ­nh

```bash
# 1. ÄÄƒng nháº­p
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin1234!"}' | jq .access_token

# 2. Upload PDF + táº¡o job extraction (má»™t lá»‡nh)
curl -s -X POST http://localhost:8000/api/v1/extraction/jobs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  -F "file=@./report.pdf;type=application/pdf" \
  -F "template_id=<TEMPLATE_ID>" \
  -F "mode=block"

# 3. Kiá»ƒm tra tráº¡ng thÃ¡i job
curl -s http://localhost:8000/api/v1/extraction/jobs/<JOB_ID> \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>"

# 4. Aggregate N jobs Ä‘Ã£ approved
curl -s -X POST http://localhost:8000/api/v1/aggregation/reports \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  -H "Content-Type: application/json" \
  -d '{"job_ids":["<JOB_1>","<JOB_2>"],"name":"BÃ¡o cÃ¡o tuáº§n"}'

# 5. Xuáº¥t Word
curl -s -X GET http://localhost:8000/api/v1/aggregation/reports/<REPORT_ID>/word \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  --output report.docx
```

---

## Extracted Data Schema

`extracted_data` trong DB luÃ´n lÃ  **canonical nested JSON** vá»›i 7 top-level key:

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

Flat key (`stt_02_tong_chay`, `tu_ngay`, ...) chá»‰ tá»“n táº¡i **in-memory** táº¡i bÆ°á»›c aggregation vÃ  trong `aggregated_data`. KhÃ´ng bao giá» lÆ°u vÃ o `extracted_data`.

---

## Data Priority Chain

```
reviewed_data  >  (extracted_data + enriched_data[danh_sach_cnch])  >  extracted_data
     â–²                        â–²                       â–²
  Human edit             Stage 1 regex           Stage 2 Ollama LLM
  (always wins)          (always present)        (optional, async)
```

---

## Celery Workers

Khi sá»­a code, pháº£i rebuild **táº¥t cáº£** Celery workers (extraction cháº¡y trong worker, khÃ´ng pháº£i API):

```bash
docker compose build api celery-extraction-worker celery-enrichment-worker celery-worker celery-beat
docker compose up -d api celery-extraction-worker celery-enrichment-worker celery-worker celery-beat
```

| Worker | Queue | Concurrency | Vai trÃ² |
|---|---|---|---|
| `rag-celery-extraction` | `extraction` | 1 | Cháº¡y Stage 1 pdfplumber pipeline |
| `rag-celery-enrichment` | `enrichment` | 2 | Cháº¡y Stage 2 Ollama LLM (CNCH) |
| `rag-celery-worker` | `default`, `document_processing` | 4 | FileOperator, BatchCloser, misc |
| `rag-celery-beat` | â€” | â€” | Scheduler: cleanup stuck jobs, auto-aggregate |

---

## Hot-folder Automation

Äáº·t PDF vÃ o MinIO `inbox/` â†’ FileOperator tá»± Ä‘á»™ng:
1. PhÃ¡t hiá»‡n file má»›i má»—i 120 giÃ¢y
2. Match template theo `filename_pattern` regex
3. Táº¡o ExtractionJob vÃ  dispatch vÃ o queue `extraction`
4. BatchCloser tá»± trigger aggregate khi táº¥t cáº£ job trong batch hoÃ n táº¥t (poll má»—i 180s)

---

## Cháº¡y tests

```bash
# Trong container
docker exec rag-api pytest tests/ -v

# Local (cáº§n Ä‘á»§ env)
pytest tests/ -v --tb=short

# Coverage
pytest tests/ --cov=app --cov-report=term-missing
```

---

## TÃ i liá»‡u ká»¹ thuáº­t

| File | Ná»™i dung |
|---|---|
| [docs/SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md) | Kiáº¿n trÃºc tá»•ng quan, data authority, success criteria |
| [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | Schema chi tiáº¿t, write isolation rules, failure handling |
| [docs/engine2_technical_spec.md](docs/engine2_technical_spec.md) | Two-stage pipeline, enrichment settlement gate, aggregation |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Táº¥t cáº£ 33 endpoints, request/response format |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Váº­n hÃ nh, monitoring, troubleshooting |
