# 🤖 doc-automation-engine

> **Production-Ready Document Automation Platform** — hệ thống tự động hoá tài liệu doanh nghiệp kết hợp **Engine 1 (RAG — hỏi đáp thông minh)** và **Engine 2 (AI Data Extraction — bóc tách dữ liệu có cấu trúc)**, multi-tenant, bảo mật tuyệt đối.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+%20pgvector-blue.svg)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-5.x-green.svg)](https://docs.celeryq.dev/)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

---

## 📑 Mục Lục

- [Tổng Quan](#-tổng-quan)
- [Kiến Trúc Hệ Thống](#-kiến-trúc-hệ-thống)
- [Tech Stack](#-tech-stack)
- [Cài Đặt & Chạy](#-cài-đặt--chạy)
- [Quickstart](#-quickstart)
- [Cấu Trúc Source Code](#-cấu-trúc-source-code)
- [API Reference — Engine 1 (RAG)](#-api-reference--engine-1-rag)
- [API Reference — Engine 2 (Data Extraction)](#-api-reference--engine-2-data-extraction)
- [Engine 2: Pipeline 4 Bước](#-engine-2-pipeline-4-bước)
- [Database Schema](#-database-schema)
- [Bảo Mật](#-bảo-mật)
- [Deployment](#-deployment)
- [Testing](#-testing)
- [Contributing](#-contributing)

---

## 🎯 Tổng Quan

**`hunter875/doc-automation-engine`** là nền tảng xử lý tài liệu toàn diện cho doanh nghiệp, gồm 2 engine độc lập nhưng dùng chung hạ tầng:

| Engine | Mô tả | Use-case |
|--------|-------|----------|
| ⚡ **Engine 1 — RAG** | Upload tài liệu → Embed → Hybrid Search (pgvector + BM25) → LLM trả lời | Hỏi đáp tự do trên khối tài liệu nội bộ |
| 🔬 **Engine 2 — Data Extraction** | Upload PDF/Word → AI bóc tách JSON theo schema → Validate → Aggregate → Export Word | Tổng hợp báo cáo định kỳ tự động (PCCC, tài chính, vận hành...) |

### 3 Trụ Cột Cốt Lõi

| Trụ Cột | Mô Tả |
|---------|-------|
| 🔒 **Multi-Tenant Isolation** | Dữ liệu của Tenant A không thể rò rỉ sang Tenant B ở mọi cấp độ (API, DB, Vector) |
| ⚡ **Async & Resilient** | Xử lý file nặng không làm treo API (Celery worker). Retry tự động, cleanup stuck jobs |
| 🧩 **Template-Driven** | Mọi pattern/regex/threshold đều nằm trong YAML template — zero hardcode |

---

## 🏗 Kiến Trúc Hệ Thống

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            INTERNET                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      NGINX (Reverse Proxy + SSL)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
        ┌─────────────┐ ┌─────────────┐ ┌──────────────────────┐
        │  FastAPI    │ │  FastAPI    │ │  Celery Workers      │
        │  Instance 1 │ │  Instance 2 │ │  (document_processing│
        └─────────────┘ └─────────────┘ │   embeddings         │
                │               │       │   extraction)        │
                └───────────────┘       └──────────────────────┘
                        │                         │
        ┌───────────────┼─────────────────────────┘
        │               │
        ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ PostgreSQL  │ │    Redis    │ │   MinIO/S3  │
│ + pgvector  │ │(Queue/Cache)│ │ (Raw Files) │
│ (Metadata + │ └─────────────┘ └─────────────┘
│  Vectors)   │
└─────────────┘
        │
        ▼
┌─────────────────────────────────┐
│  Gemini API  /  Ollama (local)  │
│  (Embedding & Extraction)       │
└─────────────────────────────────┘
```

### Engine 1 — RAG Pipeline

```
INGESTION:
  Upload File → Validate → Extract Text → Chunking → Celery Queue
       ↓
  Worker: Embed (Gemini) → Store in pgvector → Update status in DB

QUERY:
  User Question → Embed Query → Hybrid Search (pgvector k-NN + BM25)
       → Rerank Results → LLM Generate → Response + Sources
```

### Engine 2 — Data Extraction Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ENGINE 2 PIPELINE                                     │
│                                                                              │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ BƯỚC 1   │    │   BƯỚC 2     │    │   BƯỚC 3     │    │    BƯỚC 4     │  │
│  │ AI       │    │  Validation  │    │ Aggregation  │    │  Word Export  │  │
│  │ Extract  │───→│  Layer       │───→│ Map-Reduce   │───→│  (docxtpl)   │  │
│  │          │    │  (Pydantic)  │    │  (Pandas)    │    │              │  │
│  └──────────┘    └──────────────┘    └──────────────┘    └───────────────┘  │
│       │                │                    │                    │            │
│   Raw JSON         Clean JSON          Aggregated           .docx file      │
│   (có lỗi)        (đã ép kiểu)          JSON              (hoàn chỉnh)     │
│                                                                              │
│                    ┌──────────┐                                              │
│                    │  HUMAN   │ ← Approve / Reject / Edit                   │
│                    │  REVIEW  │                                              │
│                    └──────────┘                                              │
│                    (giữa Bước 2 & 3)                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠 Tech Stack

| Component | Technology | Ghi chú |
|-----------|------------|---------|
| **API Framework** | FastAPI | Async I/O, Auto OpenAPI docs |
| **Relational DB** | PostgreSQL 15+ | Metadata, RBAC, JSONB, GIN index |
| **Vector Store** | pgvector (ext.) | k-NN search tích hợp ngay trong PostgreSQL |
| **Object Storage** | MinIO / AWS S3 | Raw document files |
| **Message Broker** | Redis + Celery | 4 queues: default, document_processing, embeddings, extraction |
| **LLM / Embedding** | Gemini API + Ollama | Gemini cho RAG; Ollama (qwen2.5/qwen3) cho extraction |
| **Extraction Schema** | Instructor + Pydantic | Ép LLM output đúng JSON schema |
| **Document Parse** | pdfplumber | PDF text + table extraction |
| **Word Export** | docxtpl (Jinja2) | Render .docx template |
| **Scheduler** | Celery Beat | Periodic cleanup stuck jobs |

### Python Dependencies chính

```
fastapi              # Web framework
uvicorn[standard]    # ASGI server
sqlalchemy           # ORM
psycopg2-binary      # PostgreSQL driver
pgvector             # pgvector Python client
alembic              # DB migrations
pydantic-settings    # Settings management
redis                # Redis client
celery               # Task queue
minio                # S3-compatible storage client
pdfplumber           # PDF parsing
python-docx          # Word file handling
docxtpl              # Word template rendering (Jinja2)
instructor           # Structured LLM output
google-generativeai  # Gemini API
passlib[bcrypt]      # Password hashing
python-jose[cryptography]  # JWT
```

---

## ⚡ Cài Đặt & Chạy

### Prerequisites

- Python 3.10+
- Docker & Docker Compose v2
- (Tuỳ chọn) Ollama chạy local nếu dùng extraction backend = `ollama`
- Gemini API Key nếu dùng extraction backend = `gemini`

### 1. Clone Repository

```bash
git clone https://github.com/hunter875/doc-automation-engine.git
cd doc-automation-engine
```

### 2. Cấu Hình Environment Variables

```bash
cp .env.example .env
# Mở .env và điền các giá trị cần thiết
```

**Nội dung `.env` quan trọng:**

```bash
# ── Application ──────────────────────────────────────────
APP_NAME="doc-automation-engine"   # Tên hiển thị (display name, có thể chứa dấu gạch ngang)
APP_ENV=production          # development | production
DEBUG=false
SECRET_KEY="change-this-to-a-long-random-256-bit-string"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ── PostgreSQL ───────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpassword
POSTGRES_DB=ragdb

# ── Redis ────────────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379

# ── MinIO / S3 ───────────────────────────────────────────
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-documents
MINIO_SECURE=false

# ── Gemini API (cho RAG embedding + chat) ────────────────
GEMINI_API_KEY=your-gemini-api-key
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_CHAT_MODEL=gemini-2.0-flash
GEMINI_FLASH_MODEL=gemini-2.5-flash

# ── Ollama (cho Data Extraction) ─────────────────────────
EXTRACTION_BACKEND=ollama          # ollama | gemini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_TIMEOUT_SECONDS=300

# ── Extraction settings ───────────────────────────────────
EXTRACTION_BATCH_MAX_FILES=20
HYBRID_MAX_RETRIES=3
EXTRACTION_TIMEOUT_MINUTES=30

# ── Logging ──────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_FILE=app.log
```

> ⚠️ **Security note**: Đổi `SECRET_KEY` thành chuỗi ngẫu nhiên 256-bit trước khi deploy production. Không commit file `.env` thật lên git.

### 3. Khởi Động Services (Docker Compose)

```bash
# Build và start toàn bộ services
docker-compose up --build -d

# Kiểm tra status
docker-compose ps

# Xem logs API
docker-compose logs -f api

# Stop
docker compose down
```

**Services được khởi động:**

| Service | Port | Mô tả |
|---------|------|-------|
| `api` | 8000 | FastAPI application |
| `celery-worker` | — | Worker (4 queues) |
| `celery-beat` | — | Scheduler (cleanup stuck jobs) |
| `postgres` | 5432 | PostgreSQL 15 + pgvector |
| `redis` | 6379 | Redis 7 |
| `minio` | 9000 / 9001 | MinIO object storage |
| `flower` (optional) | 5555 | Celery monitoring (profile: debug) |

### 4. Database Migration

DB tables được tự động tạo khi khởi động API (via `Base.metadata.create_all`). Nếu dùng Alembic:

```bash
# Khởi tạo Alembic (chỉ làm 1 lần)
alembic init alembic

# Generate migration từ models
alembic revision --autogenerate -m "initial schema"

# Apply migration
alembic upgrade head

# Kiểm tra version hiện tại
alembic current
```

### 5. Cài đặt Local (không Docker)

```bash
# Tạo virtual environment
python -m venv venv
source venv/bin/activate       # Linux/Mac
# venv\Scripts\activate        # Windows

# Cài dependencies
pip install -r requirements.txt

# Start API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery Worker (terminal riêng)
celery -A app.worker.celery_app worker --loglevel=info \
  --concurrency=4 -Q default,document_processing,embeddings,extraction

# Start Celery Beat (terminal riêng)
celery -A app.worker.celery_app beat --loglevel=info
```

---

## 🚀 Quickstart

### Engine 1 — RAG: Upload & Query

```bash
export BASE="http://localhost:8000"
export TOKEN="<jwt_token_từ_login>"
export TENANT="<tenant_uuid>"

# 1. Upload tài liệu
curl -X POST "$BASE/api/v1/tenants/$TENANT/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@noi_quy_cong_ty.pdf" \
  -F "title=Nội quy công ty 2026"
# Response 202: {"id": "uuid", "status": "processing", ...}

# 2. Hỏi đáp (sau khi processing xong)
curl -X POST "$BASE/api/v1/tenants/$TENANT/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Chính sách nghỉ phép của công ty?",
    "top_k": 5,
    "search_type": "hybrid"
  }'
```

### Engine 2 — Data Extraction: PDF → Word Report

```bash
# 1. Quét Word mẫu để tạo template
curl -X POST "$BASE/api/v1/extraction/templates/scan-word" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@bao_cao_mau.docx" -F "use_llm=true"

# 2. Tạo extraction template từ kết quả scan
curl -X POST "$BASE/api/v1/extraction/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT" \
  -H "Content-Type: application/json" \
  -d '{"name":"Báo cáo PCCC Ngày","schema_definition":{...},"aggregation_rules":{...}}'

# 3. Upload batch PDF (max 20 files)
curl -X POST "$BASE/api/v1/extraction/jobs/batch" \
  -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  -F "template_id=$TEMPLATE_ID" \
  -F "files=@ngay1.pdf" -F "files=@ngay2.pdf" -F "files=@ngay3.pdf"
# → {"batch_id":"...", "total_files":3, "jobs":[...]}

# 4. Poll batch status
curl "$BASE/api/v1/extraction/jobs/batch/$BATCH_ID/status" \
  -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT"
# → {"total":3,"extracted":3,"progress_percent":100.0}

# 5. Approve từng job
curl -X POST "$BASE/api/v1/extraction/review/$JOB_ID/approve" \
  -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  -H "Content-Type: application/json" -d '{"notes":"OK"}'

# 6. Aggregate → tạo báo cáo tổng hợp
curl -X POST "$BASE/api/v1/extraction/aggregate" \
  -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  -H "Content-Type: application/json" \
  -d '{"template_id":"$TEMPLATE_ID","job_ids":["job1","job2","job3"],"report_name":"PCCC Tuần 10"}'

# 7. Export Word
curl -X POST "$BASE/api/v1/extraction/aggregate/$REPORT_ID/export-word" \
  -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
  -F "file=@bao_cao_tuan_template.docx" --output bao_cao_tuan_10.docx
```

---

## 📁 Cấu Trúc Source Code

```
doc-automation-engine/
├── app/
│   ├── main.py                          # FastAPI entry point, routers, lifespan
│   ├── api/
│   │   ├── dependencies.py              # Shared deps (auth, db session, tenant)
│   │   └── v1/
│   │       ├── auth.py                  # Đăng ký / Đăng nhập / Me
│   │       ├── tenant.py                # Tenant CRUD + member management
│   │       ├── document.py              # Document upload/list/delete
│   │       ├── rag.py                   # RAG query + semantic search
│   │       ├── extraction_templates.py  # Template CRUD + Word scanner
│   │       ├── extraction_jobs.py       # Job lifecycle + review + batch + metrics
│   │       ├── extraction_reports.py    # Aggregate + export endpoints
│   │       └── extraction.py            # Compatibility router
│   ├── business/
│   │   ├── engine.py                    # Orchestrate extractors → validators
│   │   ├── extractors.py                # Regex-based deterministic extraction
│   │   ├── validators.py                # Business rule validation (template-driven)
│   │   ├── normalizers.py               # Vietnamese word spacing + date normalization
│   │   └── template_loader.py           # DocumentTemplate wrapper + YAML registry + lru_cache
│   ├── core/
│   │   ├── config.py                    # Settings (Pydantic BaseSettings)
│   │   ├── security.py                  # JWT, bcrypt, RBAC
│   │   ├── exceptions.py                # Custom exceptions
│   │   ├── logging.py                   # Structured JSON logging
│   │   ├── metrics.py                   # PipelineMetrics + GlobalMetrics
│   │   └── tracing.py                   # Request tracing
│   ├── db/
│   │   ├── postgres.py                  # SQLAlchemy engine + session
│   │   └── pgvector.py                  # pgvector extension setup + vector index
│   ├── models/
│   │   ├── user.py                      # User model
│   │   ├── tenant.py                    # Tenant + UserTenantRole models
│   │   ├── document.py                  # Document model
│   │   └── extraction.py                # ExtractionTemplate / Job / AggregationReport
│   ├── schemas/
│   │   ├── extraction_schema.py         # Request/Response Pydantic models (Engine 2)
│   │   └── hybrid_extraction_schema.py  # HybridExtractionOutput + sub-models
│   ├── services/
│   │   ├── auth_service.py              # Authentication logic
│   │   ├── doc_service.py               # Document processing (parse + chunk + embed)
│   │   ├── rag_service.py               # RAG pipeline
│   │   ├── chunking.py                  # Text chunking strategies
│   │   ├── embedding.py                 # Gemini embedding service
│   │   ├── extraction_orchestrator.py   # Worker: S3 → pipeline → persist
│   │   ├── hybrid_extraction_pipeline.py # Standard extraction (pdfplumber + Ollama)
│   │   ├── block_extraction_pipeline.py  # 6-stage block pipeline
│   │   ├── block_business_workflow.py    # Block mode orchestrator
│   │   ├── batch_extraction.py           # Batch parallel (ThreadPoolExecutor)
│   │   ├── extractor_strategies.py       # LLM backends (Ollama/Gemini/OpenAI)
│   │   ├── data_validator.py             # Type coercion + normalization
│   │   ├── rule_engine.py                # Domain validation rules (injectable)
│   │   ├── template_manager.py           # Template domain service
│   │   ├── job_manager.py                # Job lifecycle service
│   │   ├── aggregation_service.py        # Aggregation + export context
│   │   ├── word_scanner.py               # Word template scanner
│   │   └── word_export.py                # Secure docxtpl renderer
│   ├── templates/
│   │   └── pccc.yaml                     # YAML template PCCC (55+ externalized patterns)
│   └── worker/
│       ├── celery_app.py                 # Celery configuration + task routes
│       └── extraction_tasks.py           # Tasks: extract_document + cleanup_stuck_jobs
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_auth_service.py
│   ├── test_chunking.py
│   ├── test_config.py
│   ├── test_doc_service.py
│   ├── test_embedding.py
│   ├── test_extraction_orchestrator.py
│   ├── test_hybrid_extraction_pipeline.py
│   ├── test_security.py
│   ├── test_word_export.py
│   ├── test_word_scanner.py
│   ├── test_aggregation_payload_shape.py
│   └── test_aggregation_word_context.py
├── docs/
│   ├── engine2_technical_spec.md         # Tài liệu kỹ thuật chi tiết Engine 2
│   ├── API_REFERENCE.md
│   ├── DEPLOYMENT.md
│   ├── DEVELOPMENT.md
│   ├── HYBRID_EXTRACTION.md
│   └── TECHNICAL.md
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 📚 API Reference — Engine 1 (RAG)

### Base URL

```
Development: http://localhost:8000
API Docs:    http://localhost:8000/docs   (Swagger UI)
             http://localhost:8000/redoc  (ReDoc)
```

### Authentication

Tất cả API (trừ `/auth/*`) yêu cầu JWT Bearer token:

```
Authorization: Bearer <access_token>
```

Hầu hết Tenant endpoints cần thêm:

```
X-Tenant-ID: <tenant_uuid>
```

---

### 🔐 Auth Endpoints

#### `POST /api/v1/auth/register` — Đăng ký user mới

```json
// Request
{ "email": "user@example.com", "password": "SecurePass123!", "full_name": "Nguyen Van A" }

// Response 201
{ "id": "uuid", "email": "user@example.com", "full_name": "Nguyen Van A", "created_at": "..." }
```

#### `POST /api/v1/auth/login` — Đăng nhập

```json
// Request
{ "email": "user@example.com", "password": "SecurePass123!" }

// Response 200
{ "access_token": "eyJhbGci...", "token_type": "bearer", "expires_in": 86400 }
```

#### `GET /api/v1/auth/me` — Thông tin user hiện tại

```json
// Response 200
{
  "id": "uuid", "email": "user@example.com",
  "tenants": [{ "tenant_id": "uuid", "tenant_name": "Company ABC", "role": "admin" }]
}
```

---

### 🏢 Tenant Endpoints

| Method | Path | Role | Mô tả |
|--------|------|------|-------|
| `POST` | `/api/v1/tenants` | Authenticated | Tạo tenant mới (user tạo = `owner`) |
| `GET` | `/api/v1/tenants/{tenant_id}` | viewer | Chi tiết tenant + members |
| `POST` | `/api/v1/tenants/{tenant_id}/invite` | admin/owner | Mời thêm member |

**Roles:**
- `owner` — Toàn quyền
- `admin` — Quản lý documents, invite members
- `viewer` — Chỉ đọc và query

---

### 📄 Document Endpoints

| Method | Path | Role | Mô tả |
|--------|------|------|-------|
| `POST` | `/api/v1/tenants/{tenant_id}/documents` | admin | Upload document (PDF/DOCX/TXT, max 10MB) |
| `GET` | `/api/v1/tenants/{tenant_id}/documents` | viewer | Liệt kê documents (paginated) |
| `GET` | `/api/v1/tenants/{tenant_id}/documents/{doc_id}` | viewer | Chi tiết document |
| `DELETE` | `/api/v1/tenants/{tenant_id}/documents/{doc_id}` | admin | Xóa document |

**Upload response 202:**
```json
{
  "id": "uuid", "title": "Company Policy 2026",
  "status": "processing",
  "message": "Document đang được xử lý. Kiểm tra status sau vài phút."
}
```

Document status flow: `processing` → `completed` / `failed`

---

### 🤖 RAG Query Endpoints

#### `POST /api/v1/tenants/{tenant_id}/query` — Hỏi đáp RAG

```json
// Request
{
  "question": "Chính sách nghỉ phép của công ty?",
  "top_k": 5,
  "search_type": "hybrid",
  "include_sources": true,
  "temperature": 0.7
}

// Response 200
{
  "answer": "Theo chính sách công ty, nhân viên chính thức được nghỉ phép 12 ngày/năm...",
  "sources": [
    {
      "document_id": "uuid",
      "document_title": "Company Policy 2026",
      "chunk_id": "chunk_23",
      "content": "Điều 15: Chế độ nghỉ phép năm...",
      "relevance_score": 0.92
    }
  ],
  "usage": { "prompt_tokens": 1250, "completion_tokens": 320, "total_tokens": 1570 },
  "processing_time_ms": 2340
}
```

#### `POST /api/v1/tenants/{tenant_id}/search` — Semantic Search (không LLM)

```json
// Request
{ "query": "chính sách nghỉ phép", "top_k": 10, "search_type": "hybrid" }
```

---

### ❌ Error Responses

```json
{
  "error": "PERMISSION_DENIED",
  "message": "Bạn không có quyền truy cập tenant này",
  "details": { "required_role": "viewer" }
}
```

| HTTP | Code | Mô tả |
|------|------|-------|
| 400 | `VALIDATION_ERROR` | Request không hợp lệ |
| 401 | `UNAUTHORIZED` | Token missing / expired |
| 403 | `PERMISSION_DENIED` | Không đủ role |
| 404 | `NOT_FOUND` | Resource không tồn tại |
| 413 | `FILE_TOO_LARGE` | File vượt 10MB |
| 415 | `UNSUPPORTED_FILE_TYPE` | MIME type không hỗ trợ |
| 422 | `ValidationError` | Pydantic validation error |
| 500 | `InternalError` | Lỗi server |

---

## 🔬 API Reference — Engine 2 (Data Extraction)

**Router prefix:** `/api/v1/extraction`  
**Yêu cầu header:** `X-Tenant-ID: <tenant_uuid>`

### Templates

| Method | Path | Role | Status | Mô tả |
|--------|------|------|--------|-------|
| `POST` | `/templates/scan-word` | viewer | 200 | Upload .docx → auto-infer schema |
| `POST` | `/templates` | admin | 201 | Tạo template mới |
| `GET` | `/templates` | viewer | 200 | List templates (paginated) |
| `GET` | `/templates/{id}` | viewer | 200 | Chi tiết template |
| `PATCH` | `/templates/{id}` | admin | 200 | Sửa template (schema change → version++) |
| `DELETE` | `/templates/{id}` | owner | 204 | Soft delete |

**Scan Word response:**
```json
{
  "variables": [{"name": "so_vu", "type": "number", "occurrences": 3}],
  "schema_definition": {"fields": [...]},
  "aggregation_rules": {"rules": [...]},
  "stats": {"unique_variables": 12, "tables_scanned": 3}
}
```

### Jobs

| Method | Path | Role | Status | Mô tả |
|--------|------|------|--------|-------|
| `POST` | `/jobs` | admin | 202 | Upload 1 PDF → Celery job |
| `POST` | `/jobs/batch` | admin | 202 | Upload N PDFs (max 20) → N Celery jobs |
| `POST` | `/jobs/batch-block` | admin | 200 | Batch block-mode in-process (ThreadPoolExecutor) |
| `POST` | `/jobs/from-document` | admin | 202 | Tạo job từ document đã upload |
| `GET` | `/jobs` | viewer | 200 | List jobs (filter: status, template_id, batch_id) |
| `GET` | `/jobs/{job_id}` | viewer | 200 | Polling — xem status + extracted_data |
| `GET` | `/jobs/batch/{batch_id}/status` | viewer | 200 | Batch progress |
| `GET` | `/metrics` | viewer | 200 | Global pipeline metrics (counters + timers) |
| `POST` | `/jobs/{job_id}/retry` | admin | 200 | Retry failed/rejected job |
| `DELETE` | `/jobs/{job_id}` | admin | 204 | Xóa job |

**Job status flow:**
```
PENDING → PROCESSING → EXTRACTED → APPROVED
                    ↘ FAILED      ↘ REJECTED
```

**Batch-block response:**
```json
{
  "total": 3, "succeeded": 3, "failed": 0,
  "results": [{"filename": "ngay1.pdf", "status": "success", ...}],
  "errors": [],
  "metrics": {
    "counters": {"batch_total": 3, "pipeline_success": 3},
    "timers_ms": {"stage1_layout": 1234.5, "stage3_extract": 8901.2}
  }
}
```

### Review

| Method | Path | Role | Mô tả |
|--------|------|------|-------|
| `POST` | `/review/{job_id}/approve` | admin | Approve (+ optional `reviewed_data`) |
| `POST` | `/review/{job_id}/reject` | admin | Reject (required `notes`) |

### Aggregation & Export

| Method | Path | Role | Status | Mô tả |
|--------|------|------|--------|-------|
| `POST` | `/aggregate` | admin | 201 | Gom N approved jobs → 1 report |
| `GET` | `/aggregate` | viewer | 200 | List reports |
| `GET` | `/aggregate/{id}` | viewer | 200 | Chi tiết report |
| `DELETE` | `/aggregate/{id}` | admin | 204 | Xóa report |
| `GET` | `/aggregate/{id}/export` | viewer | 200 | Export Excel/CSV/JSON (`?format=excel`) |
| `POST` | `/aggregate/{id}/export-word` | viewer | 200 | Upload .docx template → render → download |
| `GET` | `/aggregate/{id}/export-word-auto` | viewer | 200 | Dùng template đã lưu S3 để render |

---

## 🔄 Engine 2: Pipeline 4 Bước

### Luồng chi tiết

```
1. User upload PDF + chọn Template
       ↓
2. Celery worker nhận task `extract_document`
       ↓
3. [Bước 1] Worker tải file từ S3 → run_from_bytes()
  ├── Parse text + table bằng pdfplumber
  ├── Normalize text/bảng theo YAML business rules
  └── Toàn bộ xử lý trong RAM (không ghi file tạm)
     ↓
4. [Bước 1] Inference qua Ollama + Instructor + Pydantic
  ├── Model: settings.OLLAMA_MODEL (vd: qwen2.5:7b)
  ├── Output ép kiểu theo HybridExtractionOutput
  └── RuleEngine check logic domain (count, date format, v.v.)
     ↓
5. [Bước 2] Retry / Manual-review
  ├── Retry tối đa HYBRID_MAX_RETRIES (mặc định 3)
  ├── Quá số retry → ghi metadata manual review
  └── Persist trạng thái vào extraction_jobs (JSONB)
       ↓
6. INSERT clean_data → extraction_jobs.extracted_data (JSONB)
       ↓
7. [Human Review] Approve / Reject / Edit → reviewed_data
       ↓
8. [Bước 3] N approved jobs → AggregationService.aggregate()
   ├── pd.json_normalize() đập phẳng nested JSON
   ├── Apply rules: SUM, AVG, COUNT, CONCAT, LAST
   └── Output: aggregated_data + records + _metadata
       ↓
9. [Bước 4] Upload Word template + aggregated_data
   ├── docxtpl render Jinja2 placeholders
   ├── Filters: number_vn, date_vn, date_short
   └── Download file .docx hoàn chỉnh
```

### Bước 2: Validation Layer — Type Coercion

`DataValidator` tự động ép kiểu dữ liệu LLM trả về:

| Input (LLM trả ra) | Output (sau validate) | Ghi chú |
|---|---|---|
| `"Hai vụ"` | `2` | Vietnamese text → number (hỗ trợ: không, một, hai, ba...mười, trăm, nghìn, triệu, tỷ) |
| `"1.500.000"` | `1500000` | VN thousand separator |
| `"1.500.000,50"` | `1500000.5` | VN decimal format |
| `"02-03-2026"` | `"02/03/2026"` | Normalize → DD/MM/YYYY |
| `"ngày 2 tháng 3 năm 2026"` | `"02/03/2026"` | Vietnamese date text |
| `"đúng"` / `"có"` / `"✓"` | `true` | Vietnamese boolean |
| `"sai"` / `"không"` | `false` | Vietnamese boolean |

**Validation report:**
```json
{
  "is_valid": true,
  "total_fields": 6, "valid_fields": 5, "completeness_pct": 83.3,
  "auto_corrections": [
    {"field": "so_vu", "original": "Hai vụ", "coerced": 2, "note": "\"Hai vụ\" → 2"},
    {"field": "ngay_bao_cao", "original": "02-03-2026", "coerced": "02/03/2026"}
  ],
  "missing_fields": ["dia_chi_cu_the"]
}
```

### Bước 3: Aggregation Methods

| Method | Mô tả | Ví dụ |
|--------|-------|-------|
| `SUM` | Cộng tổng | `so_vu` ngày 1 + ngày 2 + ngày 3 |
| `AVG` | Trung bình | `nhiet_do` trung bình tuần |
| `MAX` / `MIN` | Cực trị | Giá trị lớn/nhỏ nhất |
| `COUNT` | Đếm | Tổng số báo cáo |
| `CONCAT` | Nối mảng | Gộp `danh_sach_su_co` 7 ngày → 1 list |
| `LAST` | Giá trị cuối | `ten_nguoi_ky` bản ghi cuối |

**Aggregation rules format:**
```json
{
  "rules": [
    {"output_field": "tong_so_vu", "source_field": "so_vu", "method": "SUM"},
    {"output_field": "tat_ca_su_co", "source_field": "danh_sach_su_co", "method": "CONCAT"},
    {"output_field": "nguoi_ky", "source_field": "ten_nguoi_ky", "method": "LAST"}
  ],
  "sort_by": "ngay_bao_cao"
}
```

### Bước 4: Word Template Syntax

```
# Biến đơn giản
{{ten_don_vi}}         → "Phòng PCCC Quận 1"
{{tong_so_vu}}         → 45
{{today}}              → "31/03/2026"   (auto-inject)
{{now}}                → "31/03/2026 08:30"

# Custom Jinja2 filters
{{tong_so_vu | number_vn}}              → "1.500.000"
{{ngay_bao_cao | date_vn}}              → "ngày 10 tháng 03 năm 2026"
{{val | date_short}}                    → "10/03/2026"
{{val | default_if_none("N/A")}}        → "N/A" nếu val là None

# Loop bảng (trong Word Table)
{% for row in records %}
{{row.loai_su_co}} | {{row.so_nguoi}} | {{row.ngay_xay_ra}}
{% endfor %}

# Điều kiện
{% if tong_so_vu > 0 %}Có {{tong_so_vu}} sự cố{% else %}Không có sự cố{% endif %}
```

### Ví dụ End-to-End: 7 Báo cáo PCCC → 1 Báo cáo Tuần

**Kết quả file Word sau export:**
```
bao_cao_tuan_10.docx
├── {{ten_don_vi}}     → "Phòng PCCC Quận 1"
├── {{tong_so_vu}}     → 45 (SUM 7 ngày)
├── {{ngay_bao_cao}}   → "ngày 10 tháng 03 năm 2026"
├── Bảng sự cố         → 45 hàng (CONCAT 7 ngày)
└── {{nguoi_ky}}       → "Đại tá Nguyễn Văn A" (LAST)
```

### Observability: Pipeline Metrics

```bash
# GET /api/v1/extraction/metrics
{
  "counters": {
    "llm_calls": 150,
    "pipeline_success": 42,
    "pipeline_failure": 3,
    "dynamic_col_detected": 38,
    "schema_enforcer_reask": 5
  },
  "timers_ms": {
    "stage1_layout": 1234.5,
    "stage2_detect": 456.7,
    "stage3_extract": 8901.2,
    "stage6_business": 234.5
  }
}
```

---

## 🗄 Database Schema

### PostgreSQL Core Tables

```sql
-- Tenants
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    billing_status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- RBAC Junction Table
CREATE TABLE user_tenant_roles (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,   -- owner | admin | viewer
    UNIQUE(user_id, tenant_id)
);

-- Documents (RAG)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    s3_key VARCHAR(500),
    status VARCHAR(50) DEFAULT 'processing',
    chunk_count INTEGER DEFAULT 0,
    embedding_model VARCHAR(100),
    tags TEXT[],
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_documents_status ON documents(status);
```

### Engine 2: Extraction Tables (PostgreSQL JSONB)

```sql
-- Extraction Templates
CREATE TABLE extraction_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    schema_definition JSONB NOT NULL,    -- Fields cần bóc tách
    aggregation_rules JSONB DEFAULT '{}', -- SUM/CONCAT/AVG rules
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_extraction_templates_schema_gin ON extraction_templates USING GIN (schema_definition);

-- Extraction Jobs
CREATE TABLE extraction_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES extraction_templates(id),
    document_id UUID NOT NULL REFERENCES documents(id),
    batch_id UUID,
    extraction_mode VARCHAR(20) DEFAULT 'standard',
    status VARCHAR(20) DEFAULT 'pending',  -- pending|processing|extracted|approved|failed|rejected
    extracted_data JSONB,                  -- AI output (đã qua Validation)
    confidence_scores JSONB,               -- _validation_report + attempts
    reviewed_data JSONB,                   -- Human-reviewed data
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMP,
    llm_model VARCHAR(100),
    processing_time_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_extraction_jobs_extracted_data_gin ON extraction_jobs USING GIN (extracted_data);
CREATE INDEX idx_extraction_jobs_reviewed_data_gin  ON extraction_jobs USING GIN (reviewed_data);

-- Aggregation Reports
CREATE TABLE aggregation_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES extraction_templates(id),
    name VARCHAR(255) NOT NULL,
    job_ids UUID[] NOT NULL,
    aggregated_data JSONB NOT NULL,
    total_jobs INTEGER NOT NULL,
    approved_jobs INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',   -- draft | finalized
    created_at TIMESTAMP DEFAULT NOW(),
    finalized_at TIMESTAMP
);
```

---

## 🔐 Bảo Mật

### Authentication Flow

```
User Login → bcrypt verify password → Issue JWT (HS256)
API Request → Decode JWT → Extract user_id → Check user_tenant_roles → Allow/403
```

### JWT Token

```python
# Payload chỉ chứa user_id (không có sensitive data)
{"sub": "user_uuid", "exp": 1708684800, "iat": 1708682000}
```

### RBAC Check

```python
async def check_tenant_permission(user_id, tenant_id, required_role):
    # Query user_tenant_roles, kiểm tra hierarchy: owner > admin > viewer
    # Return 403 nếu không đủ quyền
```

### File Upload Security

| Check | Phương pháp |
|-------|------------|
| Size Limit | 10MB (config `MAX_FILE_SIZE_MB`) |
| MIME Type | Magic bytes verification (không tin extension) |
| Anti zip-bomb (Word) | Giới hạn: entry ≤ 50MB, tổng giải nén ≤ 120MB, max entries = 2000, compression ratio ≤ 150x |

### Data Isolation

- **API**: `tenant_id` lấy từ `X-Tenant-ID` header, validate với `user_tenant_roles`
- **Database**: Mọi query đều có `WHERE tenant_id = :tenant_id`
- **pgvector**: Filter metadata `tenant_id` trước mọi k-NN search

### Security Headers (Nginx Production)

```nginx
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
```

---

## 🚀 Deployment

### Docker Compose (Development / Staging)

```bash
# Start
docker-compose up --build -d

# Scale API instances
docker-compose up --scale api=3 -d

# Enable Celery Flower monitoring (port 5555)
docker-compose --profile debug up -d
```

### Production (AWS / VPS)

```
Internet → Nginx (SSL) → FastAPI instances
                       → Celery Workers
                             │
               PostgreSQL (Private) + Redis (Private) + S3/MinIO
```

**Production environment checklist:**

- [ ] `DEBUG=false`
- [ ] `SECRET_KEY` là chuỗi ngẫu nhiên 256-bit (không dùng default)
- [ ] `CORS_ORIGINS` chỉ domain frontend thực tế
- [ ] PostgreSQL + Redis chạy trên Private Subnet (không expose public)
- [ ] Nginx với SSL/TLS (Let's Encrypt)
- [ ] Celery Beat chạy liên tục (cleanup stuck jobs mỗi 30 phút)
- [ ] Log rotation cấu hình (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`)

**Nginx config SSL:**

```nginx
server {
    listen 443 ssl http2;
    server_name api.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

### Health Check Endpoints

```bash
# Liveness
GET /health
# → {"status": "healthy", "version": "1.0.0"}

# Readiness (kiểm tra DB + pgvector)
GET /health/ready
# → {"status": "ready", "checks": {"database": "connected", "pgvector": "connected"}}
```

---

## 🧪 Testing

```bash
# Cài test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# Chạy toàn bộ tests
pytest

# Chạy với coverage report
pytest --cov=app --cov-report=html
# → htmlcov/index.html

# Chạy test file cụ thể
pytest tests/test_hybrid_extraction_pipeline.py -v
pytest tests/test_word_export.py -v
pytest tests/test_aggregation_word_context.py -v
```

**Test coverage chính:**

| File | Covers |
|------|--------|
| `test_api.py` | Auth + Tenant + Document endpoints |
| `test_hybrid_extraction_pipeline.py` | Engine 2 extraction pipeline |
| `test_word_export.py` | docxtpl renderer + anti zip-bomb |
| `test_word_scanner.py` | Word template scanner + schema inference |
| `test_aggregation_payload_shape.py` | Aggregation output structure |
| `test_aggregation_word_context.py` | Word export context building |
| `test_extraction_orchestrator.py` | Celery task orchestration |
| `test_security.py` | JWT + bcrypt |
| `test_chunking.py` | Text chunking strategies |
| `test_embedding.py` | Gemini embedding service |

---

## 🤝 Contributing

1. Fork: `https://github.com/hunter875/doc-automation-engine`
2. Tạo branch: `git checkout -b feature/ten-tinh-nang`
3. Commit: `git commit -m 'feat: mô tả thay đổi'`
4. Push: `git push origin feature/ten-tinh-nang`
5. Tạo Pull Request

### Code Style

```bash
black app/           # Format
isort app/           # Sort imports
mypy app/            # Type check
flake8 app/          # Lint
```

- Type hints bắt buộc cho tất cả functions
- Docstrings theo Google style
- Snake_case cho biến/hàm/files

---

## 📄 License

MIT License — xem file [LICENSE](LICENSE) để biết thêm chi tiết.

---

## 📞 Hỗ Trợ

- **Documentation**: [docs/](docs/) — engine2_technical_spec.md, API_REFERENCE.md, DEPLOYMENT.md
- **Issues**: [GitHub Issues](https://github.com/hunter875/doc-automation-engine/issues)
- **Swagger UI**: `http://localhost:8000/docs` (khi chạy local)

---

<p align="center">
  Built with ❤️ for Vietnamese enterprises —
  <a href="https://github.com/hunter875/doc-automation-engine">hunter875/doc-automation-engine</a>
</p>
