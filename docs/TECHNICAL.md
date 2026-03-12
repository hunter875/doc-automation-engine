# 📖 Tài Liệu Kĩ Thuật — Enterprise Multi-Tenant RAG System

> **Phiên bản:** 1.0.0  
> **Ngày cập nhật:** 2025  
> **Ngôn ngữ:** Python 3.10+  
> **Framework chính:** FastAPI · SQLAlchemy · Celery · pgvector

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Cấu trúc thư mục](#2-cấu-trúc-thư-mục)
3. [Thành phần hệ thống (Infrastructure)](#3-thành-phần-hệ-thống-infrastructure)
4. [Cơ sở dữ liệu & Models](#4-cơ-sở-dữ-liệu--models)
5. [Xác thực & Phân quyền (Auth & RBAC)](#5-xác-thực--phân-quyền-auth--rbac)
6. [API Endpoints](#6-api-endpoints)
7. [Services Layer](#7-services-layer)
8. [Worker & Background Tasks](#8-worker--background-tasks)
9. [Cấu hình (Configuration)](#9-cấu-hình-configuration)
10. [Logging & Monitoring](#10-logging--monitoring)
11. [Triển khai (Deployment)](#11-triển-khai-deployment)
12. [Luồng xử lý chính (Main Flows)](#12-luồng-xử-lý-chính-main-flows)
13. [Xử lý lỗi (Error Handling)](#13-xử-lý-lỗi-error-handling)
14. [Test UI (Streamlit)](#14-test-ui-streamlit)
15. [Hướng dẫn phát triển (Development Guide)](#15-hướng-dẫn-phát-triển-development-guide)

---

## 1. Tổng quan kiến trúc

### 1.1 Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Client Layer                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────────────┐  │
│  │  Streamlit UI  │  │   REST Client  │  │  Third-party Client   │  │
│  └───────┬────────┘  └───────┬────────┘  └──────────┬────────────┘  │
└──────────┼───────────────────┼──────────────────────┼────────────────┘
           │                   │                      │
           ▼                   ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     API Gateway (FastAPI)                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────┐  ┌──────────────────┐  │
│  │ Auth API │  │ Document API │  │RAG API │  │   Tenant API     │  │
│  │ /api/v1/ │  │  /api/v1/    │  │/api/v1/│  │   /api/v1/       │  │
│  │  auth/*  │  │  documents/* │  │ rag/*  │  │   tenants/*      │  │
│  └──────────┘  └──────────────┘  └────────┘  └──────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Middleware: CORS · Rate Limiting · Error Handler · Logging   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
┌──────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│  Services Layer  │ │  Background     │ │    External Services    │
│                  │ │  Workers        │ │                         │
│ · AuthService    │ │                 │ │ · Gemini Embedding API  │
│ · DocService     │ │ · Celery Worker │ │   (text-embedding-004)  │
│ · RAGService     │ │ · Celery Beat   │ │ · Gemini Chat API       │
│ · EmbeddingService│ │ · Task Queue   │ │   (gemini-2.0-flash)   │
│ · ChunkingService│ │                 │ │                         │
└────────┬─────────┘ └───────┬─────────┘ └─────────────────────────┘
         │                   │
         ▼                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Data Layer                                      │
│  ┌──────────────────────┐  ┌────────┐  ┌─────────────────────────┐  │
│  │ PostgreSQL + pgvector│  │ Redis  │  │    MinIO (S3)           │  │
│  │                      │  │        │  │                         │  │
│  │ · Users              │  │ · Task │  │ · Original documents    │  │
│  │ · Tenants            │  │   Queue│  │   (PDF, DOCX, TXT...)  │  │
│  │ · Documents          │  │ · Cache│  │                         │  │
│  │ · DocumentChunks     │  │        │  │ Bucket: rag-documents   │  │
│  │   (Vector embeddings)│  │        │  │                         │  │
│  │ · Usage Logs         │  │        │  │                         │  │
│  └──────────────────────┘  └────────┘  └─────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Nguyên tắc thiết kế

| Nguyên tắc | Mô tả |
|---|---|
| **Multi-Tenant Isolation** | Mỗi tenant có dữ liệu cách ly hoàn toàn qua `tenant_id` filter ở mọi tầng |
| **Layered Architecture** | API → Service → Data Access — tách biệt rõ ràng |
| **Async Processing** | Upload/embedding chạy background qua Celery, không block API |
| **RBAC** | 3 role: `owner` > `admin` > `viewer` — quyền kế thừa |
| **Fail-Safe Logging** | Usage logging không gây fail operation chính |

### 1.3 Tech Stack

| Component | Technology | Version | Mục đích |
|---|---|---|---|
| API Framework | FastAPI | 0.104+ | REST API, async support, auto docs |
| ORM | SQLAlchemy | 2.0+ | Database ORM, connection pooling |
| Database | PostgreSQL | 15 | Primary data store (JSONB + GIN indexes) |
| Vector DB | pgvector | 0.3+ | Vector similarity search (HNSW) |
| Message Broker | Redis | 7 | Celery broker & cache |
| Object Storage | MinIO | latest | S3-compatible file storage |
| Task Queue | Celery | 5.3+ | Background processing |
| AI/LLM | Google Gemini | 2.5 | Embedding, Chat, Extraction |
| Word Export | docxtpl | 0.16+ | Jinja2 template rendering for .docx |
| Data Processing | Pandas | 2.1+ | Aggregation, json_normalize |
| UI | Streamlit | 1.32+ | Test & demo interface |
| Container | Docker | - | Containerized deployment |

> **Engine 2 Technical Spec:** Xem [engine2_technical_spec.md](./engine2_technical_spec.md) cho tài liệu chi tiết hệ thống bóc tách dữ liệu.

---

## 2. Cấu trúc thư mục

```
ragPJ/
├── app/                          # Application root
│   ├── main.py                   # FastAPI app entry point
│   ├── api/                      # API layer
│   │   ├── dependencies.py       # Shared dependencies (auth, RBAC)
│   │   └── v1/                   # API version 1
│   │       ├── auth.py           # Authentication endpoints
│   │       ├── document.py       # Document management endpoints
│   │       ├── rag.py            # RAG query/search endpoints
│   │       └── tenant.py         # Tenant management endpoints
│   ├── core/                     # Core utilities
│   │   ├── config.py             # Pydantic Settings configuration
│   │   ├── exceptions.py         # Custom exception hierarchy
│   │   ├── logging.py            # Logging configuration
│   │   └── security.py           # JWT & password utilities
│   ├── db/                       # Database layer
│   │   ├── postgres.py           # SQLAlchemy engine & session
│   │   └── pgvector.py           # Vector operations (search, index)
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── document.py           # Document + DocumentChunk
│   │   ├── tenant.py             # Tenant + UserTenantRole + UsageLog
│   │   └── user.py               # User model
│   ├── schemas/                  # Pydantic request/response schemas
│   │   ├── auth_schema.py        # Auth DTOs
│   │   ├── doc_schema.py         # Document DTOs
│   │   └── rag_schema.py         # RAG + Tenant DTOs
│   ├── services/                 # Business logic layer
│   │   ├── auth_service.py       # User authentication & authorization
│   │   ├── chunking.py           # Text chunking strategies
│   │   ├── doc_service.py        # Document CRUD & S3 operations
│   │   ├── embedding.py          # Gemini embedding & chat services
│   │   └── rag_service.py        # RAG pipeline orchestration
│   └── worker/                   # Celery background workers
│       ├── celery_app.py         # Celery configuration
│       └── tasks.py              # Async task definitions
├── ui/
│   └── streamlit_app.py          # Streamlit test UI
├── tests/                        # Unit & integration tests
├── docs/                         # Documentation
├── docker-compose.yml            # Multi-service orchestration
├── Dockerfile                    # Multi-stage build
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables
└── README.md                     # Project overview
```

---

## 3. Thành phần hệ thống (Infrastructure)

### 3.1 Docker Compose Services

| Service | Image | Port(s) | Mô tả |
|---|---|---|---|
| `api` | Build from Dockerfile | `8000:8000` | FastAPI application server |
| `celery-worker` | Build from Dockerfile | — | Background task processor |
| `celery-beat` | Build from Dockerfile | — | Periodic task scheduler |
| `postgres` | `pgvector/pgvector:pg15` | `5432:5432` | PostgreSQL + pgvector extension |
| `redis` | `redis:7-alpine` | `6379:6379` | Message broker & cache |
| `minio` | `minio/minio` | `9000:9000`, `9001:9001` | Object storage (S3 API + Console) |
| `minio-init` | `minio/mc` | — | Tạo bucket `rag-documents` lần đầu |
| `flower` *(debug)* | Build from Dockerfile | `5555:5555` | Celery task monitoring UI |

### 3.2 Dockerfile (Multi-stage Build)

```
Stage 1: builder
  ├── Base: python:3.10-slim
  ├── Install: build dependencies (gcc, libpq-dev)
  └── pip install → /install prefix

Stage 2: runtime
  ├── Base: python:3.10-slim
  ├── Copy: /install from builder
  ├── Security: non-root user (appuser:appgroup, UID 1001)
  ├── Working dir: /app
  └── CMD: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3.3 Network & Dependencies

```
api ──depends──► postgres, redis, minio
celery-worker ──depends──► postgres, redis
celery-beat ──depends──► redis
minio-init ──depends──► minio
```

Tất cả services nằm trong `rag-network` (bridge driver).

### 3.4 Volumes

| Volume | Mount Point | Mục đích |
|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | Persist PostgreSQL data |
| `redis_data` | `/data` | Persist Redis data |
| `minio_data` | `/data` | Persist MinIO objects |

---

## 4. Cơ sở dữ liệu & Models

### 4.1 Entity Relationship Diagram

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────────┐
│    users     │     │ user_tenant_roles│     │     tenants       │
│──────────────│     │──────────────────│     │───────────────────│
│ id (UUID) PK │◄───┤ user_id (FK)     │     │ id (UUID) PK      │
│ email        │     │ tenant_id (FK)   ├────►│ name              │
│ password_hash│     │ role             │     │ description       │
│ full_name    │     │ created_at       │     │ billing_status    │
│ is_active    │     └──────────────────┘     │ created_at        │
│ created_at   │                               │ updated_at        │
│ updated_at   │                               └─────────┬─────────┘
└──────┬───────┘                                         │
       │                                                 │
       │          ┌──────────────────┐                   │
       │          │    documents     │                   │
       │          │──────────────────│                   │
       └─────────►│ id (UUID) PK     │◄──────────────────┘
                  │ tenant_id (FK)   │
                  │ title            │
                  │ description      │
                  │ file_name        │
                  │ file_size_bytes  │
                  │ mime_type        │
                  │ s3_key           │
                  │ status           │
                  │ chunk_count      │
                  │ embedding_model  │
                  │ error_message    │
                  │ tags (ARRAY)     │
                  │ uploaded_by (FK) │
                  │ created_at       │
                  │ processed_at     │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────────┐
                  │  document_chunks     │
                  │──────────────────────│
                  │ id (SERIAL) PK       │
                  │ chunk_id (UNIQUE)    │
                  │ document_id (FK)     │
                  │ tenant_id (UUID)     │
                  │ content (TEXT)       │
                  │ embedding (Vector    │
                  │           1536)      │
                  │ chunk_index (INT)    │
                  │ embedding_model      │
                  │ metadata (JSON)      │
                  │ created_at           │
                  └──────────────────────┘

                  ┌──────────────────────┐
                  │ tenant_usage_logs    │
                  │──────────────────────│
                  │ id (SERIAL) PK       │
                  │ tenant_id (FK)       │
                  │ user_id (FK)         │
                  │ operation_type       │
                  │ model_name           │
                  │ prompt_tokens        │
                  │ completion_tokens    │
                  │ total_tokens         │
                  │ cost_usd             │
                  │ created_at           │
                  └──────────────────────┘
```

### 4.2 Chi tiết bảng

#### 4.2.1 `users`

| Column | Type | Constraints | Mô tả |
|---|---|---|---|
| `id` | `UUID` | PK, default uuid4 | User identifier |
| `email` | `String(255)` | UNIQUE, NOT NULL, indexed | Email đăng nhập |
| `password_hash` | `String(255)` | NOT NULL | Bcrypt hash |
| `full_name` | `String(255)` | — | Tên hiển thị |
| `is_active` | `Boolean` | default True | Trạng thái tài khoản |
| `created_at` | `DateTime` | default utcnow | Ngày tạo |
| `updated_at` | `DateTime` | onupdate utcnow | Ngày cập nhật |

**File:** `app/models/user.py`

#### 4.2.2 `tenants`

| Column | Type | Constraints | Mô tả |
|---|---|---|---|
| `id` | `UUID` | PK, default uuid4 | Tenant identifier |
| `name` | `String(255)` | NOT NULL, indexed | Tên tổ chức |
| `description` | `Text` | — | Mô tả |
| `billing_status` | `String(50)` | default "active" | Trạng thái: active/suspended/cancelled |
| `created_at` | `DateTime` | default utcnow | Ngày tạo |
| `updated_at` | `DateTime` | onupdate utcnow | Ngày cập nhật |

**Relationships:** `members` (UserTenantRole, cascade all+delete-orphan), `documents` (Document), `usage_logs` (TenantUsageLog)

**File:** `app/models/tenant.py`

#### 4.2.3 `user_tenant_roles`

| Column | Type | Constraints | Mô tả |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Role assignment ID |
| `user_id` | `UUID` | FK → users.id, indexed | User reference |
| `tenant_id` | `UUID` | FK → tenants.id, indexed | Tenant reference |
| `role` | `String(50)` | NOT NULL | `owner` / `admin` / `viewer` |
| `created_at` | `DateTime` | default utcnow | Ngày gán quyền |

**Unique constraint:** `(user_id, tenant_id)` — mỗi user chỉ có 1 role trong 1 tenant.

#### 4.2.4 `documents`

| Column | Type | Constraints | Mô tả |
|---|---|---|---|
| `id` | `UUID` | PK, default uuid4 | Document identifier |
| `tenant_id` | `UUID` | FK → tenants.id, indexed | Tenant sở hữu |
| `title` | `String(500)` | NOT NULL | Tiêu đề tài liệu |
| `description` | `Text` | — | Mô tả |
| `file_name` | `String(500)` | NOT NULL | Tên file gốc |
| `file_size_bytes` | `BigInteger` | — | Kích thước (bytes) |
| `mime_type` | `String(100)` | — | MIME type |
| `s3_key` | `String(1000)` | NOT NULL | Object key trong MinIO |
| `status` | `String(50)` | default "pending" | `pending` / `processing` / `completed` / `failed` |
| `chunk_count` | `Integer` | default 0 | Số chunks đã tạo |
| `embedding_model` | `String(100)` | — | Model dùng để embed |
| `error_message` | `Text` | — | Lỗi nếu processing fail |
| `tags` | `ARRAY(String)` | — | Tags phân loại |
| `uploaded_by` | `UUID` | FK → users.id | User upload |
| `created_at` | `DateTime` | default utcnow | Ngày upload |
| `processed_at` | `DateTime` | — | Ngày hoàn tất xử lý |

**File:** `app/models/document.py`

#### 4.2.5 `document_chunks`

| Column | Type | Constraints | Mô tả |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Chunk ID nội bộ |
| `chunk_id` | `String(500)` | UNIQUE, NOT NULL | Format: `{document_id}_chunk_{index}` |
| `document_id` | `UUID` | FK → documents.id, indexed | Document gốc |
| `tenant_id` | `UUID` | NOT NULL, indexed | Tenant (denormalized for perf) |
| `content` | `Text` | NOT NULL | Nội dung chunk |
| `embedding` | `Vector(1536)` | — | Vector embedding 1536 chiều |
| `chunk_index` | `Integer` | NOT NULL | Thứ tự chunk trong document |
| `embedding_model` | `String(100)` | — | Model đã embed |
| `metadata` | `JSON` | column_name="metadata" | Metadata bổ sung |
| `created_at` | `DateTime` | default utcnow | Ngày tạo |

**Indexes:**
- HNSW index trên `embedding` (cosine distance, `m=16`, `ef_construction=200`)
- GIN index trên `to_tsvector('english', content)` cho full-text search

#### 4.2.6 `tenant_usage_logs`

| Column | Type | Constraints | Mô tả |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Log ID |
| `tenant_id` | `UUID` | FK → tenants.id, indexed | Tenant |
| `user_id` | `UUID` | FK → users.id | User thực hiện |
| `operation_type` | `String(100)` | NOT NULL | Loại thao tác |
| `model_name` | `String(100)` | — | AI model sử dụng |
| `prompt_tokens` | `Integer` | default 0 | Token prompt |
| `completion_tokens` | `Integer` | default 0 | Token completion |
| `total_tokens` | `Integer` | default 0 | Tổng token |
| `cost_usd` | `Float` | default 0.0 | Chi phí (USD) |
| `created_at` | `DateTime` | default utcnow | Timestamp |

### 4.3 PostgreSQL Connection Pool

```python
# File: app/db/postgres.py
engine = create_engine(
    DATABASE_URL,
    pool_size=10,          # Số connection tối đa trong pool
    max_overflow=20,       # Connection bổ sung khi pool đầy
    pool_pre_ping=True,    # Kiểm tra connection trước khi dùng
    pool_recycle=300,       # Recycle connection sau 5 phút
)
```

### 4.4 pgvector Operations

**File:** `app/db/pgvector.py` (449 dòng)

| Function | Mô tả |
|---|---|
| `ensure_pgvector_extension()` | Tạo extension `vector` nếu chưa có |
| `create_vector_index()` | Tạo HNSW index + GIN full-text search index |
| `index_document(db, doc)` | Insert 1 chunk vào `document_chunks` |
| `bulk_index_documents(db, docs)` | Batch insert nhiều chunks |
| `search_vectors(db, query_vector, tenant_id, top_k, ...)` | Vector similarity search (cosine `<=>`) |
| `hybrid_search(db, query_text, query_vector, tenant_id, ...)` | Kết hợp vector + BM25 full-text search |
| `delete_document_chunks(db, document_id, tenant_id)` | Xóa chunks của 1 document |
| `get_document_chunks(db, document_id, tenant_id, page, page_size)` | Lấy chunks có phân trang |
| `check_pgvector_connection(db)` | Health check |

**Hybrid Search Formula:**

$$\text{final\_score} = w_v \times (1 - \text{cosine\_distance}) + w_t \times \text{ts\_rank\_cd}$$

Mặc định: $w_v = 0.7$, $w_t = 0.3$

---

## 5. Xác thực & Phân quyền (Auth & RBAC)

### 5.1 JWT Authentication

**File:** `app/core/security.py`

| Thành phần | Chi tiết |
|---|---|
| **Algorithm** | HS256 |
| **Secret Key** | `JWT_SECRET_KEY` (env var) |
| **Expiry** | `JWT_EXPIRE_MINUTES` (default: 1440 = 24h) |
| **Token Type** | Bearer |
| **Subject** | User email |

**Flow:**

```
1. POST /api/v1/auth/login
   → Verify email + password (bcrypt)
   → Generate JWT token
   → Return: { access_token, token_type, expires_in }

2. Subsequent requests:
   → Header: Authorization: Bearer <token>
   → Middleware decode JWT → get user email
   → Lookup User from DB
   → Inject into route handler via Depends()
```

### 5.2 Password Hashing

```python
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash password
hashed = pwd_context.hash("plain_password")

# Verify
is_valid = pwd_context.verify("plain_password", hashed)
```

### 5.3 Role-Based Access Control (RBAC)

**Hierarchy:**

```
owner (level 3) ──► Toàn quyền: quản lý tenant, members, documents, queries
  │
  ▼
admin (level 2) ──► Upload/delete documents, query, xem members
  │
  ▼
viewer (level 1) ──► Chỉ query và xem documents
```

**Permission Check:**

```python
ROLE_HIERARCHY = {"owner": 3, "admin": 2, "viewer": 1}

def check_role_permission(user_role: str, required_role: str) -> bool:
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)
```

**Pre-configured Dependencies:**

```python
require_owner = RoleChecker("owner")    # Chỉ owner
require_admin = RoleChecker("admin")    # admin + owner
require_viewer = RoleChecker("viewer")  # Tất cả roles
```

### 5.4 Tenant Context

Mỗi request cần header `X-Tenant-ID`. System tự động:

1. Extract `tenant_id` từ header
2. Kiểm tra user có role trong tenant đó không
3. Kiểm tra role đủ quyền cho endpoint không
4. Tạo `TenantContext` object chứa `tenant_id`, `user`, `role`

```python
class TenantContext:
    tenant_id: str
    user: User
    role: UserTenantRole

    @property
    def is_owner(self) -> bool
    @property
    def is_admin(self) -> bool     # owner OR admin
    @property
    def can_upload(self) -> bool   # requires admin+
    @property
    def can_delete(self) -> bool   # requires admin+
    @property
    def can_query(self) -> bool    # requires viewer+
```

---

## 6. API Endpoints

### 6.1 Base URL

```
http://localhost:8000/api/v1
```

Tự động tạo OpenAPI docs tại:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 6.2 Authentication (`/api/v1/auth`)

| Method | Path | Auth | Mô tả | Request Body | Response |
|---|---|---|---|---|---|
| `POST` | `/register` | ❌ | Đăng ký user mới | `UserRegister` | `UserResponse` (201) |
| `POST` | `/login` | ❌ | Đăng nhập | `UserLogin` | `Token` (200) |
| `GET` | `/me` | ✅ Bearer | Thông tin user hiện tại | — | `UserResponse` (200) |
| `POST` | `/refresh` | ✅ Bearer | Refresh token | — | `Token` (200) |

**Schemas:**

```python
class UserRegister:
    email: str                 # EmailStr, required
    password: str              # min_length=8
    full_name: Optional[str]

class UserLogin:
    email: str
    password: str

class Token:
    access_token: str
    token_type: str = "bearer"
    expires_in: int            # seconds

class UserResponse:
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime
```

### 6.3 Document Management (`/api/v1/documents`)

| Method | Path | Auth | Role | Mô tả | Request | Response |
|---|---|---|---|---|---|---|
| `POST` | `/upload` | ✅ | admin+ | Upload tài liệu | `multipart/form-data` | `DocumentResponse` (201) |
| `GET` | `/` | ✅ | viewer+ | Danh sách tài liệu | Query params | `PaginatedDocumentResponse` |
| `GET` | `/{document_id}` | ✅ | viewer+ | Chi tiết tài liệu | — | `DocumentResponse` |
| `PUT` | `/{document_id}` | ✅ | admin+ | Cập nhật metadata | `DocumentUpdate` | `DocumentResponse` |
| `DELETE` | `/{document_id}` | ✅ | admin+ | Xóa tài liệu | — | 204 No Content |

**Upload Flow:**

```
Client ──multipart/form-data──► API
  1. Validate file (size ≤ 50MB, extension, magic bytes)
  2. Calculate SHA256 checksum (dedup check)
  3. Upload to MinIO (S3): key = "{tenant_id}/{uuid}_{filename}"
  4. Create Document record (status: "pending")
  5. Dispatch Celery task: process_document_task
  6. Return DocumentResponse immediately
```

**Query Parameters (GET /):**

| Param | Type | Default | Mô tả |
|---|---|---|---|
| `page` | int | 1 | Trang hiện tại |
| `page_size` | int | 20 | Số items/trang (max 100) |
| `status` | string | — | Filter theo status |
| `search` | string | — | Tìm theo title |

**Supported File Types:**

| Extension | MIME Type | Max Size |
|---|---|---|
| `.pdf` | application/pdf | 50 MB |
| `.docx` | application/vnd.openxmlformats... | 50 MB |
| `.doc` | application/msword | 50 MB |
| `.txt` | text/plain | 50 MB |
| `.md` | text/markdown | 50 MB |
| `.json` | application/json | 50 MB |
| `.csv` | text/csv | 50 MB |

**File Validation:** Kiểm tra cả extension **và** magic bytes (file signature) để tránh spoofing.

### 6.4 RAG Operations (`/api/v1/rag`)

| Method | Path | Auth | Role | Mô tả | Request Body | Response |
|---|---|---|---|---|---|---|
| `POST` | `/query` | ✅ | viewer+ | RAG query | `RAGQueryRequest` | `RAGResponse` |
| `POST` | `/query/stream` | ✅ | viewer+ | Streaming RAG | `RAGQueryRequest` | SSE stream |
| `POST` | `/search` | ✅ | viewer+ | Semantic search | `SearchRequest` | `list[SearchResult]` |
| `GET` | `/chunks/{document_id}` | ✅ | viewer+ | Document chunks | Query params | `list[dict]` |

**RAG Query Request:**

```python
class RAGQueryRequest:
    question: str                           # Câu hỏi
    document_ids: Optional[list[str]]       # Giới hạn documents
    top_k: int = 5                          # Số chunks context
    use_hybrid: bool = True                 # Hybrid search
    temperature: float = 0.7                # LLM temperature
    max_tokens: int = 1000                  # Max response length
```

**RAG Response:**

```python
class RAGResponse:
    answer: str                             # Câu trả lời
    sources: list[SearchResult]             # Nguồn tham khảo
    usage: dict                             # Token usage
    query_time_ms: float                    # Thời gian xử lý (ms)
```

**SSE Streaming Events:**

```
event: status     → data: "Đang tìm kiếm thông tin liên quan..."
event: sources    → data: [{chunk_id, document_id, score, content_preview}]
event: status     → data: "Đang tạo câu trả lời..."
event: answer_chunk → data: "partial answer text..."  (nhiều events)
event: done       → data: {query_time_ms, sources_count}
```

### 6.5 Tenant Management (`/api/v1/tenants`)

| Method | Path | Auth | Role | Mô tả |
|---|---|---|---|---|
| `POST` | `/` | ✅ | — | Tạo tenant (user = owner) |
| `GET` | `/` | ✅ | — | List tenant của user |
| `GET` | `/{tenant_id}` | ✅ | viewer+ | Chi tiết tenant |
| `PUT` | `/{tenant_id}` | ✅ | owner | Cập nhật tenant |
| `DELETE` | `/{tenant_id}` | ✅ | owner | Xóa tenant + tất cả data |
| `GET` | `/{tenant_id}/members` | ✅ | viewer+ | Danh sách members |
| `POST` | `/{tenant_id}/members` | ✅ | owner | Thêm member |
| `PUT` | `/{tenant_id}/members/{user_id}` | ✅ | owner | Đổi role member |
| `DELETE` | `/{tenant_id}/members/{user_id}` | ✅ | owner | Xóa member |

### 6.6 Health Check

| Method | Path | Auth | Response |
|---|---|---|---|
| `GET` | `/health` | ❌ | `{ status, database, pgvector, version, timestamp }` |

---

## 7. Services Layer

### 7.1 AuthService

**File:** `app/services/auth_service.py` (269 dòng)

| Method | Input | Output | Mô tả |
|---|---|---|---|
| `register_user(db, email, password, full_name)` | User info | `User` | Đăng ký, check duplicate email |
| `authenticate_user(db, email, password)` | Credentials | `User` | Verify credentials |
| `create_token_for_user(user)` | `User` | `dict(token info)` | Generate JWT |
| `get_user_by_id(db, user_id)` | UUID | `User \| None` | Lookup by ID |
| `get_user_by_email(db, email)` | Email | `User \| None` | Lookup by email |
| `get_user_tenants(db, user_id)` | UUID | `list[dict]` | User's tenants + roles |
| `get_user_role_in_tenant(db, user_id, tenant_id)` | UUIDs | `UserTenantRole \| None` | Role check |
| `check_tenant_permission(db, user_id, tenant_id, required_role)` | ... | `bool` | RBAC check |
| `change_password(db, user_id, old_pass, new_pass)` | ... | `bool` | Đổi mật khẩu |

### 7.2 DocService

**File:** `app/services/doc_service.py` (561 dòng)

Gồm 2 phần chính:

#### Document Management Functions

| Function | Mô tả |
|---|---|
| `validate_file(file_name, content, max_size)` | Validate size + extension + magic bytes |
| `upload_to_s3(s3_client, bucket, key, content, content_type)` | Upload file lên MinIO |
| `download_from_s3(s3_client, bucket, key)` | Download file từ MinIO |
| `delete_from_s3(s3_client, bucket, key)` | Xóa file từ MinIO |
| `create_document(db, tenant_id, title, file_name, ...)` | Tạo Document record (SHA256 dedup) |
| `get_document(db, document_id, tenant_id)` | Get document by ID + tenant |
| `list_documents(db, tenant_id, page, page_size, status, search)` | Paginated list |
| `update_document(db, document_id, tenant_id, updates)` | Update metadata |
| `delete_document(db, document_id, tenant_id, s3_client, bucket)` | Full cleanup (S3 + chunks + DB) |

#### DocumentProcessor Class

| Static Method | Mô tả |
|---|---|
| `extract_text_from_pdf(content: bytes)` | PDF → text (dùng `pypdf`) |
| `extract_text_from_docx(content: bytes)` | DOCX → text (dùng `python-docx`) |
| `extract_text(content, mime_type)` | Router cho các format |

**Magic Bytes Validation:**

```python
MAGIC_BYTES = {
    '.pdf':  b'%PDF',
    '.docx': b'PK',          # ZIP format
    '.doc':  b'\xd0\xcf\x11\xe0',  # OLE2
    '.json': [b'{', b'['],
}
```

### 7.3 EmbeddingService & ChatService

**File:** `app/services/embedding.py` (303 dòng)

#### EmbeddingService

Sử dụng OpenAI SDK trỏ đến Google Gemini endpoint:

```python
client = OpenAI(
    api_key=settings.GEMINI_API_KEY,
    base_url=settings.GEMINI_BASE_URL,   # https://generativelanguage.googleapis.com/v1beta/openai/
    timeout=settings.GEMINI_TIMEOUT,
    max_retries=settings.GEMINI_MAX_RETRIES,
)
model = settings.GEMINI_EMBEDDING_MODEL  # text-embedding-004
```

| Method | Input | Output | Mô tả |
|---|---|---|---|
| `embed_single(text)` | `str` | `list[float]` (1536-d) | Embed 1 text |
| `embed_batch(texts, batch_size)` | `list[str]` | `list[list[float]]` | Batch embed, tự chia batch |
| `embed_with_token_count(texts)` | `list[str]` | `(embeddings, token_count)` | Embed + đếm tokens |
| `count_tokens(text)` | `str` | `int` | Đếm tokens (tiktoken) |

#### ChatService

```python
model = settings.GEMINI_CHAT_MODEL  # gemini-2.0-flash
```

| Method | Input | Output | Mô tả |
|---|---|---|---|
| `generate(prompt, system_prompt, temperature, max_tokens)` | Strings + params | `(answer, usage_dict)` | Chat completion |
| `generate_stream(prompt, system_prompt, temperature, max_tokens)` | Same | `Generator[str]` | Streaming chunks |

### 7.4 ChunkingService

**File:** `app/services/chunking.py` (393 dòng)

4 chiến lược chunking:

| Strategy | Class | Mô tả |
|---|---|---|
| `FIXED_SIZE` | `FixedSizeChunker` | Chia theo số ký tự cố định, có overlap |
| `SENTENCE` | `SentenceChunker` | Chia theo câu (regex `.!?`), gom nhóm đến max_chunk_size |
| `PARAGRAPH` | `ParagraphChunker` | Chia theo paragraph (`\n\n`), gom nhóm |
| `RECURSIVE` *(default)* | `RecursiveChunker` | Chia đệ quy theo hierarchy: `\n\n` → `\n` → `. ` → ` ` → `""` |

**Facade:**

```python
chunker = TextChunker(
    strategy=ChunkingStrategy.RECURSIVE,
    chunk_size=512,    # Ký tự
    overlap=50,
)

chunks = chunker.chunk(text)
# hoặc
chunks_with_meta = chunker.chunk_with_metadata(text, base_metadata={"source": "doc1"})
```

### 7.5 RAGService

**File:** `app/services/rag_service.py` (540 dòng)

Orchestrator chính của hệ thống RAG:

| Method | Mô tả |
|---|---|
| `process_document(document_id, tenant_id, text)` | Chunk → Embed → Index vào pgvector |
| `search(query, tenant_id, document_ids, top_k, min_score, use_hybrid)` | Semantic/hybrid search |
| `query(question, tenant_id, ...)` | Full RAG: search → prompt → LLM → response |
| `query_stream(question, tenant_id, ...)` | Same nhưng streaming SSE |
| `get_document_chunks(document_id, tenant_id, page, page_size)` | Lấy chunks phân trang |
| `_log_usage(tenant_id, action, tokens_used, metadata)` | Log token usage (fail-safe) |

**RAG System Prompt:**

```
You are a helpful assistant that answers questions based on the provided context.
Instructions:
1. Answer using ONLY the provided context
2. If insufficient info, say so clearly
3. Cite specific parts of context
4. Be concise but comprehensive
5. Use markdown formatting
6. If asked in Vietnamese, respond in Vietnamese
```

---

## 8. Worker & Background Tasks

### 8.1 Celery Configuration

**File:** `app/worker/celery_app.py`

```python
celery_app = Celery("rag_worker", broker=REDIS_URL, backend=REDIS_URL)

# Key settings:
task_serializer = "json"
task_acks_late = True          # Acknowledge sau khi hoàn thành
worker_prefetch_multiplier = 1 # Lấy 1 task/lần
worker_concurrency = 4         # 4 worker threads
task_soft_time_limit = 300     # Soft limit: 5 phút
task_time_limit = 600          # Hard limit: 10 phút
```

**Task Routing:**

| Queue | Tasks |
|---|---|
| `document_processing` | `process_document_task`, `reindex_document_task`, `bulk_process_documents_task` |
| `embeddings` | `generate_embeddings_task` |
| `default` | `cleanup_expired_tasks`, `send_notification_task` |

### 8.2 Task Definitions

**File:** `app/worker/tasks.py` (365 dòng)

#### `process_document_task(document_id, tenant_id)`

**Retry:** max 3 lần, exponential backoff (60s, 120s, 240s)

```
Flow:
1. Get DB session
2. Lookup Document record → update status "processing"
3. Download file from MinIO (S3)
4. Extract text (PDF/DOCX/TXT)
5. Chunk text (RecursiveChunker, size=512, overlap=50)
6. Generate embeddings (Gemini API, batch)
7. Index chunks vào pgvector (bulk_index_documents)
8. Update Document: status="completed", chunk_count, embedding_model, processed_at
9. On failure: status="failed", error_message=str(exception)
```

#### `generate_embeddings_task(texts, document_id, tenant_id)`

Standalone embedding task — generate embeddings cho list texts.

#### `reindex_document_task(document_id, tenant_id)`

Xóa chunks cũ → re-process document (dùng `delete_document_chunks` rồi `process_document_task`).

#### `cleanup_expired_tasks()`

**Schedule:** Chạy mỗi giờ (Celery Beat)  
**Logic:** Tìm documents `status="processing"` quá 1 giờ → đánh dấu `status="failed"`.

#### `bulk_process_documents_task(document_ids, tenant_id)`

Dispatch `process_document_task` cho từng document trong list (group).

#### `send_notification_task(user_id, message, notification_type)`

Placeholder — chưa implement.

### 8.3 Celery Beat Schedule

```python
beat_schedule = {
    "cleanup-expired-tasks": {
        "task": "app.worker.tasks.cleanup_expired_tasks",
        "schedule": crontab(minute=0, hour="*/1"),  # Mỗi giờ
    }
}
```

---

## 9. Cấu hình (Configuration)

### 9.1 Environment Variables

**File:** `app/core/config.py` — Pydantic `BaseSettings` với `env_file=".env"`

#### Application

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `PROJECT_NAME` | str | "Enterprise RAG System" | Tên project |
| `VERSION` | str | "1.0.0" | Version |
| `DEBUG` | bool | False | Debug mode |

#### Database (PostgreSQL)

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `DATABASE_HOST` | str | "localhost" | DB host |
| `DATABASE_PORT` | int | 5432 | DB port |
| `DATABASE_USER` | str | "raguser" | DB username |
| `DATABASE_PASSWORD` | str | "ragpassword" | DB password |
| `DATABASE_NAME` | str | "ragdb" | DB name |

**Computed property:**

```python
@property
def DATABASE_URL(self) -> str:
    return f"postgresql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
```

#### Redis

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `REDIS_HOST` | str | "localhost" | Redis host |
| `REDIS_PORT` | int | 6379 | Redis port |

**Computed property:**

```python
@property
def REDIS_URL(self) -> str:
    return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
```

#### MinIO (S3)

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `S3_ENDPOINT_URL` | str | "http://localhost:9000" | MinIO endpoint |
| `S3_ACCESS_KEY` | str | "minioadmin" | Access key |
| `S3_SECRET_KEY` | str | "minioadmin" | Secret key |
| `S3_BUCKET_NAME` | str | "rag-documents" | Bucket name |
| `S3_REGION` | str | "us-east-1" | Region |

#### Gemini API

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `GEMINI_API_KEY` | str | — | Google Gemini API key |
| `GEMINI_BASE_URL` | str | `https://generativelanguage.googleapis.com/v1beta/openai/` | Gemini endpoint |
| `GEMINI_EMBEDDING_MODEL` | str | "text-embedding-004" | Embedding model |
| `GEMINI_CHAT_MODEL` | str | "gemini-2.0-flash" | Chat model |
| `GEMINI_TIMEOUT` | int | 30 | Request timeout (s) |
| `GEMINI_MAX_RETRIES` | int | 3 | Retry count |

#### Security

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `JWT_SECRET_KEY` | str | "change-in-production" | JWT signing key |
| `JWT_ALGORITHM` | str | "HS256" | Algorithm |
| `JWT_EXPIRE_MINUTES` | int | 1440 | Token TTL (phút) |

#### File Upload

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `MAX_FILE_SIZE` | int | 52428800 | Max file size (50MB) |
| `ALLOWED_EXTENSIONS` | list | [".pdf", ".docx", ".doc", ".txt", ".md", ".json", ".csv"] | Accepted extensions |

#### RAG Settings

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `CHUNK_SIZE` | int | 512 | Characters per chunk |
| `CHUNK_OVERLAP` | int | 50 | Overlap between chunks |
| `EMBEDDING_BATCH_SIZE` | int | 100 | Batch size for embedding API |
| `VECTOR_DIMENSION` | int | 1536 | Embedding dimension |

#### Logging

| Variable | Type | Default | Mô tả |
|---|---|---|---|
| `LOG_LEVEL` | str | "INFO" | Minimum log level |
| `LOG_DIR` | str | "logs" | Log directory |
| `LOG_FILE` | str | "app.log" | Log filename |
| `LOG_MAX_BYTES` | int | 10485760 | Max log file size (10MB) |
| `LOG_BACKUP_COUNT` | int | 5 | Rotated file count |

---

## 10. Logging & Monitoring

### 10.1 Logging Architecture

**File:** `app/core/logging.py`

```
Application Log Output
       │
       ├──► Console (StreamHandler)
       │    Format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
       │
       └──► File (RotatingFileHandler)
            Path: logs/app.log
            Max size: 10 MB per file
            Backup count: 5 files
            Format: same as console
```

Rotation behavior: Khi `app.log` đạt 10MB → rename thành `app.log.1` → tạo `app.log` mới. Giữ tối đa 5 file cũ (`app.log.1` ... `app.log.5`).

### 10.2 Usage Tracking

Mỗi thao tác RAG được log vào bảng `tenant_usage_logs`:

| Operation Type | Khi nào | Token tracking |
|---|---|---|
| `document_process` | Sau khi embed xong document | ✅ Chính xác |
| `rag_query` | Sau mỗi query | ✅ Chính xác |
| `rag_query_stream` | Sau mỗi streaming query | ⚠️ Ước tính (streaming không trả token count) |

### 10.3 Health Check

`GET /health` trả về:

```json
{
  "status": "healthy",
  "database": "connected",
  "pgvector": "available",
  "version": "1.0.0",
  "timestamp": "2025-01-01T00:00:00Z"
}
```

### 10.4 Flower Dashboard (Debug)

Chạy với profile `debug`:

```bash
docker compose --profile debug up -d flower
```

Truy cập: `http://localhost:5555` — monitor Celery tasks, workers, queues.

---

## 11. Triển khai (Deployment)

### 11.1 Quick Start

```bash
# 1. Clone & cấu hình
cp .env.example .env
# Sửa GEMINI_API_KEY và các config cần thiết

# 2. Start tất cả services
docker compose up -d --build

# 3. Kiểm tra
curl http://localhost:8000/health

# 4. Mở Swagger UI
# http://localhost:8000/docs
```

### 11.2 Service Ports

| Service | Port | URL |
|---|---|---|
| FastAPI | 8000 | http://localhost:8000 |
| Swagger UI | 8000 | http://localhost:8000/docs |
| MinIO Console | 9001 | http://localhost:9001 |
| MinIO API | 9000 | http://localhost:9000 |
| PostgreSQL | 5432 | postgresql://raguser:ragpassword@localhost:5432/ragdb |
| Redis | 6379 | redis://localhost:6379 |
| Flower (debug) | 5555 | http://localhost:5555 |
| Streamlit UI | 8501 | http://localhost:8501 |

### 11.3 Chạy Streamlit UI

```bash
# Sau khi API đã start
pip install streamlit requests
streamlit run ui/streamlit_app.py
```

### 11.4 Scaling

```bash
# Scale Celery workers
docker compose up -d --scale celery-worker=3

# Scale API (cần load balancer phía trước)
docker compose up -d --scale api=2
```

### 11.5 Production Checklist

- [ ] Đổi `JWT_SECRET_KEY` thành random strong key
- [ ] Đổi `DATABASE_PASSWORD` thành strong password
- [ ] Đổi MinIO credentials (`S3_ACCESS_KEY`, `S3_SECRET_KEY`)
- [ ] Set `DEBUG=false`
- [ ] Cấu hình CORS_ORIGINS phù hợp
- [ ] Giới hạn `MAX_FILE_SIZE` theo nhu cầu
- [ ] Set `LOG_LEVEL=WARNING` cho production
- [ ] Setup reverse proxy (nginx/traefik) cho HTTPS
- [ ] Enable PostgreSQL SSL
- [ ] Setup backup cho PostgreSQL + MinIO
- [ ] Monitor disk space cho log rotation

---

## 12. Luồng xử lý chính (Main Flows)

### 12.1 Flow: Upload & Process Document

```
User                API Server              Celery Worker          MinIO     PostgreSQL
 │                     │                        │                    │            │
 │  POST /upload       │                        │                    │            │
 │  (multipart file)   │                        │                    │            │
 │────────────────────►│                        │                    │            │
 │                     │                        │                    │            │
 │                     │  1. Validate file       │                    │            │
 │                     │  (size, ext, magic)     │                    │            │
 │                     │                        │                    │            │
 │                     │  2. SHA256 checksum     │                    │            │
 │                     │  (dedup check)         │                    │            │
 │                     │                        │                    │            │
 │                     │───────────────────────────────────────────►│            │
 │                     │  3. Upload to S3                           │            │
 │                     │◄───────────────────────────────────────────│            │
 │                     │                        │                    │            │
 │                     │──────────────────────────────────────────────────────►│
 │                     │  4. Create Document record (status=pending)          │
 │                     │◄──────────────────────────────────────────────────────│
 │                     │                        │                    │            │
 │                     │  5. Dispatch task       │                    │            │
 │                     │───────────────────────►│                    │            │
 │                     │                        │                    │            │
 │  Response (201)     │                        │                    │            │
 │◄────────────────────│                        │                    │            │
 │  {id, status:       │                        │                    │            │
 │   "pending"}        │                        │                    │            │
 │                     │                        │                    │            │
 │                     │                        │  6. Download file  │            │
 │                     │                        │───────────────────►│            │
 │                     │                        │◄───────────────────│            │
 │                     │                        │                    │            │
 │                     │                        │  7. Extract text   │            │
 │                     │                        │  (PDF/DOCX/TXT)    │            │
 │                     │                        │                    │            │
 │                     │                        │  8. Chunk text     │            │
 │                     │                        │  (Recursive, 512)  │            │
 │                     │                        │                    │            │
 │                     │                        │  9. Generate       │            │
 │                     │                        │  embeddings        │            │
 │                     │                        │  (Gemini API)      │            │
 │                     │                        │                    │            │
 │                     │                        │  10. Bulk index    │            │
 │                     │                        │──────────────────────────────►│
 │                     │                        │  (document_chunks)            │
 │                     │                        │◄──────────────────────────────│
 │                     │                        │                    │            │
 │                     │                        │  11. Update status │            │
 │                     │                        │  → "completed"     │            │
 │                     │                        │──────────────────────────────►│
 │                     │                        │◄──────────────────────────────│
```

### 12.2 Flow: RAG Query

```
User                API Server              PostgreSQL (pgvector)      Gemini API
 │                     │                          │                        │
 │  POST /rag/query    │                          │                        │
 │  {question,         │                          │                        │
 │   top_k: 5}         │                          │                        │
 │────────────────────►│                          │                        │
 │                     │                          │                        │
 │                     │  1. Embed question        │                        │
 │                     │──────────────────────────────────────────────────►│
 │                     │  (text-embedding-004)     │                        │
 │                     │◄──────────────────────────────────────────────────│
 │                     │  query_vector [1536-d]    │                        │
 │                     │                          │                        │
 │                     │  2. Hybrid search         │                        │
 │                     │──────────────────────────►│                        │
 │                     │  (vector cosine +          │                        │
 │                     │   BM25 full-text)          │                        │
 │                     │◄──────────────────────────│                        │
 │                     │  top_k chunks + scores    │                        │
 │                     │                          │                        │
 │                     │  3. Filter min_score      │                        │
 │                     │                          │                        │
 │                     │  4. Build RAG prompt       │                        │
 │                     │  (context + question)     │                        │
 │                     │                          │                        │
 │                     │  5. Generate answer        │                        │
 │                     │──────────────────────────────────────────────────►│
 │                     │  (gemini-2.0-flash)       │                        │
 │                     │◄──────────────────────────────────────────────────│
 │                     │  answer + token usage     │                        │
 │                     │                          │                        │
 │                     │  6. Log usage              │                        │
 │                     │──────────────────────────►│                        │
 │                     │  (tenant_usage_logs)       │                        │
 │                     │                          │                        │
 │  Response           │                          │                        │
 │◄────────────────────│                          │                        │
 │  {answer, sources,  │                          │                        │
 │   usage,            │                          │                        │
 │   query_time_ms}    │                          │                        │
```

### 12.3 Flow: User Authentication

```
1. Register:
   POST /auth/register → validate email unique → hash password → create User → return UserResponse

2. Login:
   POST /auth/login → find user by email → verify bcrypt → create JWT (sub=email, exp=24h) → return Token

3. Authenticated Request:
   Any endpoint → Extract Bearer token → Decode JWT → Find User by email → Check tenant role → Execute
```

---

## 13. Xử lý lỗi (Error Handling)

### 13.1 Exception Hierarchy

```
RAGException (base, 500)
├── AuthenticationError (401)
│   ├── InvalidCredentialsError (401)
│   ├── TokenExpiredError (401)
│   └── TokenInvalidError (401)
├── PermissionDeniedError (403)
├── ResourceNotFoundError (404)
│   ├── TenantNotFoundError (404)
│   ├── DocumentNotFoundError (404)
│   └── UserNotFoundError (404)
├── FileValidationError (400)
│   ├── FileTooLargeError (400)
│   ├── UnsupportedFileTypeError (400)
│   └── CorruptedFileError (400)
├── ProcessingError (500)
├── ExternalServiceError (502)
│   ├── OpenAIError (502)         # Gemini API errors
│   ├── VectorStoreError (502)    # pgvector errors
│   └── StorageError (502)        # MinIO errors
├── RateLimitError (429)
└── ServiceUnavailableError (503)
```

### 13.2 Error Response Format

```json
{
  "detail": {
    "error_code": "DOCUMENT_NOT_FOUND",
    "message": "Document not found",
    "details": { "document_id": "..." }
  }
}
```

### 13.3 Global Exception Handlers

Được đăng ký trong `app/main.py`:

```python
@app.exception_handler(RAGException)    → JSON response với status code tương ứng
@app.exception_handler(Exception)       → 500 Internal Server Error (generic)
```

---

## 14. Test UI (Streamlit)

**File:** `ui/streamlit_app.py`

### 14.1 Features

| Tab | Chức năng |
|---|---|
| 🔐 Login / Register | Đăng ký & đăng nhập user |
| 🏢 Tenants | Tạo & chọn tenant |
| 📄 Documents | Upload, xem danh sách, xóa tài liệu |
| 🤖 RAG Chat | Hỏi đáp với context từ documents |
| 🔍 Search | Tìm kiếm semantic trong documents |

### 14.2 Cách dùng

```bash
pip install streamlit requests
streamlit run ui/streamlit_app.py
```

Mở `http://localhost:8501`. Cần API server chạy ở `http://localhost:8000`.

---

## 15. Hướng dẫn phát triển (Development Guide)

### 15.1 Local Setup (không Docker)

```bash
# 1. Tạo virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Cần có sẵn:
#    - PostgreSQL 15 với pgvector extension
#    - Redis 7
#    - MinIO (hoặc S3)

# 4. Cấu hình .env (copy từ .env.example)
cp .env.example .env

# 5. Chạy API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Chạy Celery worker (terminal khác)
celery -A app.worker.celery_app worker --loglevel=info

# 7. Chạy Celery beat (terminal khác)
celery -A app.worker.celery_app beat --loglevel=info
```

### 15.2 Chạy Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=app        # Với coverage
pytest tests/test_auth.py -v      # Chỉ test auth
```

### 15.3 Thêm API endpoint mới

1. Định nghĩa schema trong `app/schemas/`
2. Tạo/cập nhật service trong `app/services/`
3. Tạo route trong `app/api/v1/`
4. Include router trong `app/main.py`
5. Viết tests trong `tests/`

### 15.4 Thêm background task mới

1. Định nghĩa task trong `app/worker/tasks.py`
2. Thêm routing trong `celery_app.py` (nếu cần queue riêng)
3. Dispatch task từ API: `task_name.delay(args)`

### 15.5 Key Dependencies

```
fastapi==0.104.1
uvicorn==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
pgvector>=0.3.0
celery==5.3.4
redis==5.0.1
boto3==1.33.0
openai==1.3.5
pypdf==3.17.1
python-docx==1.1.0
tiktoken==0.5.2
python-jose==3.3.0
passlib[bcrypt]==1.7.4
pydantic-settings==2.1.0
python-multipart==0.0.6
python-magic==0.4.27
streamlit==1.28.0
```

---

## Phụ lục

### A. Glossary

| Thuật ngữ | Giải thích |
|---|---|
| **RAG** | Retrieval-Augmented Generation — kỹ thuật kết hợp tìm kiếm tài liệu + LLM |
| **Multi-Tenant** | Kiến trúc 1 hệ thống phục vụ nhiều tổ chức, data cách ly |
| **pgvector** | PostgreSQL extension cho vector similarity search |
| **HNSW** | Hierarchical Navigable Small World — thuật toán tìm kiếm vector nhanh |
| **Hybrid Search** | Kết hợp vector similarity + BM25 full-text search |
| **Chunking** | Chia tài liệu lớn thành đoạn nhỏ để embed & tìm kiếm |
| **Embedding** | Biểu diễn text dưới dạng vector số học (1536 chiều) |
| **SSE** | Server-Sent Events — streaming dữ liệu từ server |
| **RBAC** | Role-Based Access Control — phân quyền theo vai trò |

### B. API Error Codes

| Error Code | HTTP Status | Mô tả |
|---|---|---|
| `AUTHENTICATION_ERROR` | 401 | Lỗi xác thực chung |
| `INVALID_CREDENTIALS` | 401 | Sai email/password |
| `TOKEN_EXPIRED` | 401 | Token hết hạn |
| `TOKEN_INVALID` | 401 | Token không hợp lệ |
| `PERMISSION_DENIED` | 403 | Không đủ quyền |
| `RESOURCE_NOT_FOUND` | 404 | Không tìm thấy resource |
| `TENANT_NOT_FOUND` | 404 | Không tìm thấy tenant |
| `DOCUMENT_NOT_FOUND` | 404 | Không tìm thấy document |
| `FILE_TOO_LARGE` | 400 | File vượt quá giới hạn |
| `UNSUPPORTED_FILE_TYPE` | 400 | Loại file không hỗ trợ |
| `PROCESSING_ERROR` | 500 | Lỗi xử lý nội bộ |
| `EXTERNAL_SERVICE_ERROR` | 502 | Lỗi service bên ngoài |
| `RATE_LIMIT_ERROR` | 429 | Vượt giới hạn request |
| `SERVICE_UNAVAILABLE` | 503 | Service không khả dụng |

---

> **Tài liệu này được tạo tự động từ source code review.**  
> **Cập nhật khi có thay đổi kiến trúc hoặc thêm tính năng mới.**
