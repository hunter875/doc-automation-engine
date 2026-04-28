# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tech Stack

- **Backend**: FastAPI + Pydantic v2 + SQLAlchemy
- **Task Queue**: Celery + Redis
- **Database**: PostgreSQL + JSONB (with pgvector extension)
- **Object Storage**: MinIO (S3-compatible)
- **LLM**: Ollama (qwen2.5:7b-instruct or gemini) via Instructor
- **Frontend**: Next.js 14 + React + Tailwind CSS + Radix UI
- **Document Processing**: pdfplumber, docxtpl, Jinja2
- **Container**: Docker Compose

## Project Architecture

### High-Level Data Flow

```
PDF Report (Daily)
    │
    ▼
[Stage 1] BlockExtractionPipeline (pdfplumber + regex, deterministic, no LLM)
    │
    ▼
[Stage 2] Enrichment (optional Ollama LLM for CNCH extraction) - async via Celery
    │
    ▼
Human Review (approve/reject/edit)
    │
    ▼
AggregationService (Pandas map-reduce: SUM/CONCAT/LAST across N reports)
    │
    ▼
Word Export (docxtpl + Jinja2 → .docx)
```

**Key architectural principle**: LLM is NOT on the critical path. The system can extract, review, and aggregate completely without Ollama. LLM enrichment is an optional async enhancement.

### Directory Structure

```
app/
├── main.py                      # FastAPI app, 33 endpoints
├── api/v1/                      # Routers: auth, document, extraction, jobs, templates, tenant, aggregation, sheets, ingestion, reports
├── application/                 # Services (use case layer): job, doc, auth, aggregation, extraction, review, template
├── core/                        # Config, exceptions, security, logging, tracing
├── domain/
│   ├── models/                  # SQLAlchemy models: ExtractionJob, Document, Tenant, User
│   ├── rules/                   # RuleEngine, validation rules, extractors, normalizers
│   ├── templates/pccc.yaml      # ★ All business regex/patterns - NOT hardcoded in code
│   └── workflow.py              # State machine: JobStatus + transition_job_state()
├── engines/extraction/
│   ├── block_pipeline.py        # ★ Stage 1 deterministic pipeline (no LLM)
│   ├── orchestrator.py          # Dispatch Stage 1 → Stage 2
│   ├── sheet_pipeline.py        # Google Sheets ingestion pipeline
│   └── schemas.py               # Data schemas for extraction outputs
├── infrastructure/
│   ├── db/                      # Session, base, migrations
│   ├── llm/                     # Ollama/Gemini clients
│   ├── storage/                 # MinIO S3 client
│   └── worker/
│       ├── celery_app.py        # 4 queues: extraction, enrichment, default, document_processing
│       ├── enrichment_tasks.py  # ★ Stage 2 LLM enrichment (Celery task)
│       ├── extraction_tasks.py  # Stage 1 extraction tasks
│       └── operator_tasks.py    # FileOperator (hot-folder) + BatchCloser
├── schemas/                     # Pydantic request/response schemas
└── utils/                       # word_export, pdf_utils, file_utils, metrics
frontend/                        # Next.js 14 React frontend
tests/                           # pytest with 60% coverage minimum
docs/                            # SYSTEM_OVERVIEW.md, DATA_CONTRACT.md, API_REFERENCE.md, OPERATIONS.md
```

### Critical Invariants

- **GoogleSheetIngestionService MUST NOT call any LLM** - pure data transformation only
- **SheetExtractionPipeline MUST NOT fetch Google Sheets API** - receives data via `sheet_data` param
- **extract_document_task must pass** `source_type="sheet"` + `sheet_data` when `parser_used == "google_sheets"`
- **row_hash idempotency scope**: `(tenant_id, template_id, sheet_id, worksheet)` - duplicate detection
- **Database**: PostgreSQL JSONB. Use GIN indexes for `extracted_data`, `reviewed_data`, `schema_definition`.
- **Never migrate columns without running** `migrate_add_enrichment_columns.py` pattern first

## Common Development Tasks

### Start Development Environment (Docker Compose)

```bash
# Copy environment template
cp .env.example .env

# Build and start all services
docker compose up -d --build

# Check status
docker compose ps

# View logs (all services)
docker compose logs -f

# View logs for specific service
docker compose logs -f api
docker compose logs -f celery-extraction-worker
```

Services:
- **API**: http://localhost:8000 (Swagger: http://localhost:8000/docs)
- **Frontend**: http://localhost:3000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **MinIO**: http://localhost:9001 (credentials: minioadmin/minioadmin)
- **Flower (Celery monitoring)**: http://localhost:5555

### Rebuild After Code Changes

When modifying Python code (especially Celery workers), rebuild the affected containers:

```bash
# Rebuild all (safe but slower)
docker compose build api celery-extraction-worker celery-enrichment-worker celery-worker celery-beat
docker compose up -d api celery-extraction-worker celery-enrichment-worker celery-worker celery-beat

# Quick restart of API only (no rebuild needed for most changes)
docker compose restart api
```

### Run Tests

```bash
# Inside container (recommended - has all dependencies)
docker exec rag-api pytest tests/ -v

# Run specific test file
docker exec rag-api pytest tests/test_extraction_orchestrator.py -v

# Run specific test function
docker exec rag-api pytest tests/test_extraction_orchestrator.py::test_orchestrator_success -v

# Run with coverage
docker exec rag-api pytest tests/ --cov=app --cov-report=term-missing

# Run locally (requires .env and dependencies)
pytest tests/ -v --tb=short
```

### Frontend Development

```bash
cd frontend

# Install dependencies (first time)
npm install --legacy-peer-deps

# Development server
npm run dev

# Build for production
npm run build

# Lint
npm run lint

# Start production server
npm start
```

### Database Migrations

```bash
# Create a new migration (Alembic - if using)
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

**Note**: New columns require the `migrate_add_enrichment_columns.py` pattern - never add columns directly without following this pattern.

### Code Quality

```bash
# Lint Python (if configured)
ruff check app/

# Format Python
black app/

# Type check
mypy app/
```

### Hot-folder Automation

Place PDFs into MinIO `inbox/` bucket:
1. FileOperator polls every 120 seconds
2. Matches template via `filename_pattern` regex
3. Creates ExtractionJob and dispatches to `extraction` queue
4. BatchCloser auto-triggers aggregation when batch completes (polls every 180s)

## Key Workflows

### API Extraction Flow

```bash
# 1. Login
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin1234!"}' | jq .access_token

# 2. Upload PDF + create extraction job
curl -s -X POST http://localhost:8000/api/v1/extraction/jobs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  -F "file=@./report.pdf;type=application/pdf" \
  -F "template_id=<TEMPLATE_ID>" \
  -F "mode=block"

# 3. Check job status
curl -s http://localhost:8000/api/v1/extraction/jobs/<JOB_ID> \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>"

# 4. Aggregate N approved jobs
curl -s -X POST http://localhost:8000/api/v1/aggregation/reports \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  -H "Content-Type: application/json" \
  -d '{"job_ids":["<JOB_1>","<JOB_2>"],"name":"Weekly Report"}'

# 5. Export Word
curl -s -X GET http://localhost:8000/api/v1/aggregation/reports/<REPORT_ID>/word \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  --output report.docx
```

### Google Sheets Integration

Use the sheets API endpoints to ingest data from Google Sheets:

```bash
# Create sheet ingestion job
curl -s -X POST http://localhost:8000/api/v1/sheets/ingest \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: <TENANT_ID>" \
  -H "Content-Type: application/json" \
  -d '{"sheet_id":"<SHEET_ID>","template_id":"<TEMPLATE_ID>","worksheet_name":"Sheet1"}'
```

## Data Schema

### Extraction Output Structure

`extracted_data` in DB is **canonical nested JSON** with 7 top-level keys:

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

### Data Priority Chain

```
reviewed_data  >  (extracted_data + enriched_data[danh_sach_cnch])  >  extracted_data
     ▲                        ▲                       ▲
  Human edit             Stage 1 regex           Stage 2 Ollama LLM
  (always wins)          (always present)        (optional, async)
```

## Important Notes

- **All business patterns/regex** live in `app/domain/templates/pccc.yaml` - never hardcode in Python
- **Stage 1 (block_pipeline)** is deterministic and does NOT use LLM
- **Stage 2 (enrichment)** is async via Celery and uses Ollama Instructor for structured extraction
- **Celery workers must be rebuilt** after code changes: `docker compose build celery-extraction-worker celery-enrichment-worker`
- **Template YAML changes** require reloading - either restart API or use the admin reload endpoint
- **MinIO bucket** is auto-created on first startup (`minio-init` service)
- **Flower monitoring** available at http://localhost:5555 (enable with `docker compose --profile debug up flower`)

## Testing Strategy

- Unit tests for services, rules, extractors
- Integration tests for API endpoints
- Contract validation tests for data schemas
- Coverage target: 60% minimum

Run tests inside container: `docker exec rag-api pytest tests/ -v`

## Configuration

Key environment variables in `.env`:
- `EXTRACTION_BACKEND`: `ollama` (default) or `gemini`
- `OLLAMA_MODEL`: model name (default: `qwen3:8b`)
- `OLLAMA_BASE_URL`: host where Ollama runs (default: `http://host.docker.internal:11434`)
- `FILE_OPERATOR_ENABLED`: hot-folder automation (default: `true`)
- `BATCH_CLOSER_AUTO_AGGREGATE`: auto-aggregate when batch completes (default: `true`)

See `.env.example` for full list.
