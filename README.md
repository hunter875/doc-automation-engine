# 🚀 Enterprise Multi-Tenant RAG System

> **Production-Ready SaaS Platform** cho phép nhiều doanh nghiệp (Tenant) quản lý và truy vấn tài liệu nội bộ bằng AI một cách an toàn, độc lập và tối ưu chi phí.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)
[![OpenSearch](https://img.shields.io/badge/OpenSearch-2.x-yellow.svg)](https://opensearch.org/)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

---

## 📑 Mục Lục

- [Tổng Quan](#-tổng-quan)
- [Kiến Trúc Hệ Thống](#-kiến-trúc-hệ-thống)
- [Tech Stack](#-tech-stack)
- [Cài Đặt & Chạy](#-cài-đặt--chạy)
- [Cấu Trúc Project](#-cấu-trúc-project)
- [API Reference](#-api-reference)
- [Database Schema](#-database-schema)
- [Bảo Mật](#-bảo-mật)
- [Monitoring & Observability](#-monitoring--observability)
- [Deployment](#-deployment)
- [Contributing](#-contributing)

---

## 🎯 Tổng Quan

### Vấn Đề Giải Quyết

Doanh nghiệp cần một giải pháp để:
- **Tìm kiếm thông minh** trong khối lượng tài liệu nội bộ khổng lồ
- **Trả lời câu hỏi** dựa trên context từ tài liệu riêng của công ty
- **Bảo mật tuyệt đối** - dữ liệu không bị rò rỉ giữa các khách hàng

### 3 Trụ Cột Cốt Lõi

| Trụ Cột | Mô Tả |
|---------|-------|
| 🔒 **Absolute Data Isolation** | Dữ liệu và Vector của Tenant A không thể bị rò rỉ sang Tenant B ở mọi cấp độ (API, DB, Search) |
| ⚡ **Resiliency & Scale** | Xử lý file nặng không làm treo hệ thống (Async Worker). Có cơ chế chịu lỗi khi Third-party API sập |
| 💰 **Security & FinOps** | Kiểm soát chi phí (Token Tracking) và bảo mật hạ tầng chuẩn Cloud (VPC, IAM) |

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
│                         Let's Encrypt HTTPS                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐
│  FastAPI    │ │  FastAPI    │ │    Celery Worker    │
│  Instance 1 │ │  Instance 2 │ │  (Background Jobs)  │
└─────────────┘ └─────────────┘ └─────────────────────┘
        │               │                   │
        └───────────────┼───────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ PostgreSQL  │ │  OpenSearch │ │    Redis    │
│  (Metadata) │ │  (Vectors)  │ │(Queue/Cache)│
└─────────────┘ └─────────────┘ └─────────────┘
                        │
                        ▼
                ┌─────────────┐
                │  AWS S3 /   │
                │   MinIO     │
                │ (Raw Files) │
                └─────────────┘
                        │
                        ▼
                ┌─────────────┐
                │  OpenAI API │
                │ (Embedding  │
                │  & Chat)    │
                └─────────────┘
```

### RAG Pipeline Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          INGESTION PIPELINE                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌───────────┐    ┌─────┐ │
│  │ Upload  │───▶│ Validate│───▶│  Extract │───▶│  Chunking │───▶│Queue│ │
│  │  File   │    │  File   │    │   Text   │    │  (Chunks) │    │     │ │
│  └─────────┘    └─────────┘    └──────────┘    └───────────┘    └─────┘ │
│                                                                     │    │
│  ┌─────────────────────────────────────────────────────────────────┘    │
│  │ Celery Worker (Background)                                           │
│  ▼                                                                       │
│  ┌──────────┐    ┌───────────┐    ┌───────────────┐                     │
│  │ Embedding│───▶│  Index to │───▶│ Update Status │                     │
│  │ (OpenAI) │    │ OpenSearch│    │   in DB       │                     │
│  └──────────┘    └───────────┘    └───────────────┘                     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                           QUERY PIPELINE                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐    ┌─────────┐    ┌─────┐ │
│  │  User   │───▶│ Embed    │───▶│  Hybrid   │───▶│ Rerank  │───▶│ LLM │ │
│  │  Query  │    │  Query   │    │  Search   │    │ Results │    │ Gen │ │
│  └─────────┘    └──────────┘    └───────────┘    └─────────┘    └─────┘ │
│                                       │                              │   │
│                                       ▼                              ▼   │
│                               ┌─────────────┐                ┌──────────┐│
│                               │  k-NN +     │                │ Response ││
│                               │  BM25       │                │ + Sources││
│                               └─────────────┘                └──────────┘│
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠 Tech Stack

### Core Technologies

| Component | Technology | Purpose |
|-----------|------------|---------|
| **API Framework** | FastAPI | Async I/O, Auto OpenAPI docs, Type validation |
| **Relational DB** | PostgreSQL 15+ | Metadata, Users, RBAC, Usage Logs |
| **Vector DB** | OpenSearch 2.x | k-NN Search, BM25 Hybrid Search |
| **Object Storage** | AWS S3 / MinIO | Raw document storage |
| **Message Broker** | Redis + Celery | Background jobs, Caching |
| **AI/LLM** | OpenAI API | `text-embedding-3-small`, `gpt-4o-mini` |

### Python Dependencies

```
# Web Framework & Server
fastapi              # High-performance async web framework
uvicorn[standard]    # ASGI server
python-multipart     # File upload handling

# Database
sqlalchemy           # ORM
psycopg2-binary      # PostgreSQL driver
alembic              # Database migrations

# Security
passlib[bcrypt]      # Password hashing
python-jose[cryptography]  # JWT tokens

# Validation
pydantic             # Data validation
pydantic-settings    # Settings management

# RAG Stack
opensearch-py        # OpenSearch client
minio                # S3-compatible storage
openai               # OpenAI API client
tiktoken             # Token counting

# Background Processing
redis                # Caching & message broker
celery               # Distributed task queue
```

---

## ⚡ Cài Đặt & Chạy

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- OpenAI API Key

### 1. Clone & Setup Environment

```bash
# Clone repository
git clone https://github.com/your-org/ragPJ.git
cd ragPJ

# Tạo virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# hoặc: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Cấu Hình Environment Variables

Tạo file `.env` ở root directory:

```bash
# Application
APP_NAME="Enterprise RAG System"
DEBUG=false
SECRET_KEY="your-super-secret-key-change-in-production"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpassword
POSTGRES_DB=ragdb

# OpenSearch
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=admin

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# MinIO / S3
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-documents

# OpenAI
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini

# File Upload Limits
MAX_FILE_SIZE_MB=10
ALLOWED_MIME_TYPES=application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

### 3. Khởi Động Services (Docker)

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

### 4. Database Migration

```bash
# Initialize Alembic (nếu chưa có)
alembic init alembic

# Generate migration
alembic revision --autogenerate -m "Initial schema"

# Apply migration
alembic upgrade head
```

### 5. Run Application

```bash
# Development mode
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6. Start Celery Worker

```bash
# Start worker
celery -A app.worker.celery_app worker --loglevel=info

# Start with concurrency
celery -A app.worker.celery_app worker --loglevel=info --concurrency=4
```

### Quick Start với Docker Compose (All-in-One)

```bash
# Build và chạy toàn bộ
docker-compose up --build -d

# Xem logs
docker-compose logs -f api

# Stop
docker-compose down
```

---

## 📁 Cấu Trúc Project

```
ragPJ/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── api/
│   │   ├── dependencies.py     # Shared dependencies (auth, db session)
│   │   └── v1/
│   │       ├── auth.py         # Authentication endpoints
│   │       ├── document.py     # Document management endpoints
│   │       ├── rag.py          # RAG query endpoints
│   │       └── tenant.py       # Tenant management endpoints
│   ├── core/
│   │   ├── config.py           # Application settings (Pydantic)
│   │   ├── exceptions.py       # Custom exception handlers
│   │   └── security.py         # JWT, password hashing, RBAC
│   ├── db/
│   │   ├── postgres.py         # PostgreSQL connection & session
│   │   └── opensearch.py       # OpenSearch client setup
│   ├── models/
│   │   ├── user.py             # SQLAlchemy User model
│   │   ├── tenant.py           # SQLAlchemy Tenant model
│   │   └── document.py         # SQLAlchemy Document model
│   ├── schemas/
│   │   ├── auth_schema.py      # Pydantic schemas for auth
│   │   ├── doc_schema.py       # Pydantic schemas for documents
│   │   └── rag_schema.py       # Pydantic schemas for RAG
│   ├── services/
│   │   ├── auth_service.py     # Authentication business logic
│   │   ├── doc_service.py      # Document processing logic
│   │   ├── rag_service.py      # RAG pipeline logic
│   │   ├── chunking.py         # Text chunking strategies
│   │   └── embedding.py        # OpenAI embedding service
│   └── worker/
│       ├── celery_app.py       # Celery configuration
│       └── tasks.py            # Background task definitions
├── docs/                       # Additional documentation
├── docker-compose.yml          # Docker services configuration
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
└── README.md                   # This file
```

---

## 📚 API Reference

### Base URL

```
Development: http://localhost:8000
Production:  https://api.your-domain.com
```

### Authentication

Tất cả API (trừ `/auth/*`) yêu cầu JWT token trong header:

```
Authorization: Bearer <access_token>
```

---

### 🔐 Auth Endpoints

#### POST `/api/v1/auth/register`

Đăng ký user mới.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "Nguyen Van A"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "Nguyen Van A",
  "created_at": "2026-02-23T10:00:00Z"
}
```

---

#### POST `/api/v1/auth/login`

Đăng nhập và nhận JWT token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

#### GET `/api/v1/auth/me`

Lấy thông tin user hiện tại.

**Headers:** `Authorization: Bearer <token>`

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "Nguyen Van A",
  "tenants": [
    {
      "tenant_id": "uuid",
      "tenant_name": "Company ABC",
      "role": "admin"
    }
  ]
}
```

---

### 🏢 Tenant Endpoints

#### POST `/api/v1/tenants`

Tạo tenant/workspace mới. User tạo sẽ tự động có role `owner`.

**Request Body:**
```json
{
  "name": "Company ABC",
  "description": "Main workspace for Company ABC"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "name": "Company ABC",
  "description": "Main workspace for Company ABC",
  "billing_status": "active",
  "created_at": "2026-02-23T10:00:00Z"
}
```

---

#### GET `/api/v1/tenants/{tenant_id}`

Lấy thông tin chi tiết tenant.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "name": "Company ABC",
  "billing_status": "active",
  "members": [
    {
      "user_id": "uuid",
      "email": "user@example.com",
      "role": "owner"
    }
  ],
  "usage": {
    "total_documents": 150,
    "total_tokens_used": 1250000,
    "storage_used_mb": 450.5
  }
}
```

---

#### POST `/api/v1/tenants/{tenant_id}/invite`

Mời user vào tenant (chỉ `owner` hoặc `admin`).

**Request Body:**
```json
{
  "email": "newuser@example.com",
  "role": "viewer"
}
```

**Roles Available:**
- `owner` - Toàn quyền, quản lý billing
- `admin` - Quản lý documents, invite members
- `viewer` - Chỉ xem và query

---

### 📄 Document Endpoints

#### POST `/api/v1/tenants/{tenant_id}/documents`

Upload document mới. File được validate và đưa vào queue xử lý.

**Request:** `multipart/form-data`
```
file: <binary>
title: "Company Policy 2026"
description: "Nội quy công ty bản cập nhật"
tags: ["policy", "hr", "2026"]
```

**Validation Rules:**
- Max file size: 10MB
- Allowed MIME types: PDF, TXT, DOCX
- Magic bytes verification (không tin extension)

**Response:** `202 Accepted`
```json
{
  "id": "uuid",
  "title": "Company Policy 2026",
  "status": "processing",
  "file_name": "company_policy_2026.pdf",
  "file_size_bytes": 2457600,
  "created_at": "2026-02-23T10:00:00Z",
  "message": "Document đang được xử lý. Kiểm tra status sau vài phút."
}
```

---

#### GET `/api/v1/tenants/{tenant_id}/documents`

Liệt kê documents của tenant.

**Query Parameters:**
- `page` (int): Trang hiện tại (default: 1)
- `limit` (int): Số items/trang (default: 20, max: 100)
- `status` (string): Filter theo status (`processing`, `completed`, `failed`)
- `search` (string): Tìm theo title

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Company Policy 2026",
      "status": "completed",
      "file_name": "company_policy_2026.pdf",
      "chunk_count": 45,
      "created_at": "2026-02-23T10:00:00Z"
    }
  ],
  "total": 150,
  "page": 1,
  "limit": 20,
  "pages": 8
}
```

---

#### GET `/api/v1/tenants/{tenant_id}/documents/{doc_id}`

Chi tiết document.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "title": "Company Policy 2026",
  "description": "Nội quy công ty bản cập nhật",
  "status": "completed",
  "file_name": "company_policy_2026.pdf",
  "file_size_bytes": 2457600,
  "mime_type": "application/pdf",
  "chunk_count": 45,
  "embedding_model": "text-embedding-3-small",
  "tags": ["policy", "hr", "2026"],
  "created_at": "2026-02-23T10:00:00Z",
  "processed_at": "2026-02-23T10:02:30Z"
}
```

---

#### DELETE `/api/v1/tenants/{tenant_id}/documents/{doc_id}`

Xóa document (cần role `admin` trở lên).

**Response:** `204 No Content`

---

### 🤖 RAG Query Endpoints

#### POST `/api/v1/tenants/{tenant_id}/query`

**Main RAG endpoint** - Hỏi đáp dựa trên documents của tenant.

**Request Body:**
```json
{
  "question": "Chính sách nghỉ phép của công ty như thế nào?",
  "top_k": 5,
  "search_type": "hybrid",
  "include_sources": true
}
```

**Parameters:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `question` | string | required | Câu hỏi của user |
| `top_k` | int | 5 | Số chunks retrieve (1-20) |
| `search_type` | string | "hybrid" | `semantic`, `keyword`, hoặc `hybrid` |
| `include_sources` | bool | true | Có trả về sources không |
| `temperature` | float | 0.7 | LLM temperature (0-1) |

**Response:** `200 OK`
```json
{
  "answer": "Theo chính sách công ty, nhân viên chính thức được nghỉ phép 12 ngày/năm. Nhân viên có thể đăng ký nghỉ phép qua hệ thống HR Portal và cần được quản lý trực tiếp phê duyệt trước ít nhất 3 ngày làm việc...",
  "sources": [
    {
      "document_id": "uuid",
      "document_title": "Company Policy 2026",
      "chunk_id": "chunk_23",
      "content": "Điều 15: Chế độ nghỉ phép năm\n15.1. Nhân viên chính thức được hưởng 12 ngày phép năm...",
      "relevance_score": 0.92
    },
    {
      "document_id": "uuid",
      "document_title": "HR Guidelines",
      "chunk_id": "chunk_8",
      "content": "Quy trình đăng ký nghỉ phép:\n1. Đăng nhập HR Portal\n2. Chọn loại nghỉ phép...",
      "relevance_score": 0.87
    }
  ],
  "usage": {
    "prompt_tokens": 1250,
    "completion_tokens": 320,
    "total_tokens": 1570
  },
  "processing_time_ms": 2340
}
```

---

#### POST `/api/v1/tenants/{tenant_id}/search`

Semantic search (không có LLM generation). Dùng để tìm documents liên quan.

**Request Body:**
```json
{
  "query": "chính sách nghỉ phép",
  "top_k": 10,
  "search_type": "hybrid",
  "filters": {
    "tags": ["policy", "hr"],
    "date_from": "2025-01-01"
  }
}
```

**Response:** `200 OK`
```json
{
  "results": [
    {
      "document_id": "uuid",
      "document_title": "Company Policy 2026",
      "chunk_content": "Điều 15: Chế độ nghỉ phép năm...",
      "score": 0.92,
      "highlight": "Nhân viên chính thức được <em>nghỉ phép</em> 12 ngày/năm"
    }
  ],
  "total_results": 15,
  "processing_time_ms": 450
}
```

---

### Error Responses

Tất cả error responses tuân theo format:

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Bạn không có quyền truy cập tenant này",
    "details": {
      "required_role": "viewer",
      "your_role": null
    }
  },
  "request_id": "req_abc123",
  "timestamp": "2026-02-23T10:00:00Z"
}
```

**Common Error Codes:**

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 400 | `VALIDATION_ERROR` | Request body không hợp lệ |
| 401 | `UNAUTHORIZED` | Token missing hoặc expired |
| 403 | `PERMISSION_DENIED` | Không có quyền |
| 404 | `NOT_FOUND` | Resource không tồn tại |
| 413 | `FILE_TOO_LARGE` | File vượt quá 10MB |
| 415 | `UNSUPPORTED_FILE_TYPE` | MIME type không được hỗ trợ |
| 429 | `RATE_LIMITED` | Quá nhiều requests |
| 500 | `INTERNAL_ERROR` | Lỗi server |
| 503 | `SERVICE_UNAVAILABLE` | OpenAI hoặc service khác đang sập |

---

## 🗄 Database Schema

### PostgreSQL Tables

```sql
-- Tenants (Workspace/Organization)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    billing_status VARCHAR(50) DEFAULT 'active', -- active, suspended, cancelled
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User-Tenant Roles (RBAC Junction Table)
CREATE TABLE user_tenant_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- owner, admin, viewer
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, tenant_id)
);

-- Documents Metadata
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    file_name VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    s3_key VARCHAR(500), -- Path trong S3/MinIO
    status VARCHAR(50) DEFAULT 'processing', -- processing, completed, failed
    chunk_count INTEGER DEFAULT 0,
    embedding_model VARCHAR(100),
    error_message TEXT, -- Lưu lỗi nếu processing fail
    tags TEXT[], -- PostgreSQL array
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- Token Usage Logs (FinOps)
CREATE TABLE tenant_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    operation_type VARCHAR(50), -- embedding, chat, search
    model_name VARCHAR(100),
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 6), -- Estimated cost
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_usage_tenant_date ON tenant_usage_logs(tenant_id, created_at);
CREATE INDEX idx_user_roles_user ON user_tenant_roles(user_id);
CREATE INDEX idx_user_roles_tenant ON user_tenant_roles(tenant_id);
```

### OpenSearch Index Mapping

```json
{
  "settings": {
    "index": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "knn": true
    }
  },
  "mappings": {
    "properties": {
      "tenant_id": {
        "type": "keyword"
      },
      "document_id": {
        "type": "keyword"
      },
      "chunk_id": {
        "type": "keyword"
      },
      "embedding_model": {
        "type": "keyword"
      },
      "content": {
        "type": "text",
        "analyzer": "standard"
      },
      "vector": {
        "type": "knn_vector",
        "dimension": 1536,
        "method": {
          "engine": "nmslib",
          "space_type": "cosinesimil",
          "name": "hnsw",
          "parameters": {
            "ef_construction": 256,
            "m": 48
          }
        }
      },
      "metadata": {
        "type": "object",
        "properties": {
          "page_number": { "type": "integer" },
          "chunk_index": { "type": "integer" },
          "tags": { "type": "keyword" }
        }
      },
      "created_at": {
        "type": "date"
      }
    }
  }
}
```

---

## 🔐 Bảo Mật

### Authentication Flow

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  User   │────▶│  Login  │────▶│ Verify  │────▶│  Issue  │
│         │     │  API    │     │ Password│     │  JWT    │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
                                                     │
     ┌───────────────────────────────────────────────┘
     ▼
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  API    │────▶│ Extract │────▶│  Check  │────▶│ Process │
│ Request │     │ user_id │     │  RBAC   │     │ Request │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
```

### Security Best Practices

#### 1. JWT Token Security

```python
# JWT chỉ chứa user_id, không chứa sensitive data
{
    "sub": "user_uuid",
    "exp": 1708684800,  # Expiration
    "iat": 1708682000   # Issued at
}
```

#### 2. RBAC Middleware

Mọi request đều phải qua RBAC check:

```python
async def check_tenant_permission(
    user_id: str,
    tenant_id: str,
    required_role: str
) -> bool:
    # Query user_tenant_roles table
    # Verify user has required_role or higher
    # Return 403 if not authorized
```

#### 3. File Upload Security

| Check | Method |
|-------|--------|
| Size Limit | Nginx + FastAPI (10MB max) |
| MIME Type | Magic bytes verification |
| Content Scan | Parse file, reject corrupted |
| Filename | Sanitize, generate UUID |

#### 4. API Rate Limiting

```python
# Rate limits per endpoint
RATE_LIMITS = {
    "auth/login": "5/minute",
    "documents/upload": "10/minute",
    "query": "30/minute",
    "search": "60/minute"
}
```

#### 5. Data Isolation

- **API Level**: Tenant_id extracted from URL, validated against user's roles
- **Database Level**: All queries include `WHERE tenant_id = :tenant_id`
- **OpenSearch Level**: Pre-filter query always includes `tenant_id` term

---

## 📊 Monitoring & Observability

### Structured Logging Format

```json
{
  "timestamp": "2026-02-23T10:00:00.123Z",
  "level": "INFO",
  "logger": "app.services.rag_service",
  "message": "RAG query completed",
  "tenant_id": "uuid",
  "user_id": "uuid",
  "trace_id": "trace_abc123",
  "request_id": "req_xyz789",
  "data": {
    "query_length": 45,
    "chunks_retrieved": 5,
    "tokens_used": 1570,
    "latency_ms": 2340
  }
}
```

### Key Metrics to Track

| Metric | Type | Description |
|--------|------|-------------|
| `rag_query_latency_p95` | Histogram | P95 latency của RAG queries |
| `embedding_latency_p95` | Histogram | P95 latency embedding |
| `document_processing_time` | Histogram | Thời gian xử lý document |
| `tokens_used_total` | Counter | Tổng tokens đã dùng |
| `active_celery_tasks` | Gauge | Số tasks đang chạy |
| `failed_tasks_total` | Counter | Số tasks thất bại |
| `opensearch_query_latency` | Histogram | Search latency |

### Health Check Endpoints

```bash
# Application health
GET /health

# Detailed component status
GET /health/detailed
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "postgresql": { "status": "healthy", "latency_ms": 5 },
    "opensearch": { "status": "healthy", "latency_ms": 12 },
    "redis": { "status": "healthy", "latency_ms": 2 },
    "celery": { "status": "healthy", "active_workers": 4 },
    "openai": { "status": "healthy", "latency_ms": 450 }
  }
}
```

---

## 🚀 Deployment

### Development (Docker Compose)

```yaml
# docker-compose.yml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - OPENSEARCH_HOST=opensearch
    depends_on:
      - postgres
      - redis
      - opensearch
      - minio

  celery_worker:
    build: .
    command: celery -A app.worker.celery_app worker --loglevel=info
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
    depends_on:
      - redis
      - postgres

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: raguser
      POSTGRES_PASSWORD: ragpassword
      POSTGRES_DB: ragdb
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  opensearch:
    image: opensearchproject/opensearch:2.11.0
    environment:
      - discovery.type=single-node
      - plugins.security.disabled=true
    volumes:
      - opensearch_data:/usr/share/opensearch/data

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  redis_data:
  opensearch_data:
  minio_data:
```

### Production (AWS)

#### Infrastructure Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                           AWS VPC                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Public Subnet                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │   │
│  │  │   EC2 (API)  │  │   EC2 (API)  │  │    Nginx     │    │   │
│  │  │   + Celery   │  │   + Celery   │  │  (Optional)  │    │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Private Subnet                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │   │
│  │  │     RDS      │  │ ElastiCache  │  │  OpenSearch  │    │   │
│  │  │ (PostgreSQL) │  │   (Redis)    │  │   Service    │    │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                        S3 Bucket                          │   │
│  │                    (Document Storage)                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### Security Groups

```bash
# EC2 Security Group (Public)
- Inbound: 80, 443 from 0.0.0.0/0
- Inbound: 22 from VPN/Bastion only
- Outbound: All

# RDS Security Group (Private)
- Inbound: 5432 from EC2 Security Group only
- Outbound: None

# ElastiCache Security Group (Private)
- Inbound: 6379 from EC2 Security Group only

# OpenSearch Security Group (Private)
- Inbound: 9200 from EC2 Security Group only
```

#### IAM Role cho EC2

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::your-rag-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::your-rag-bucket"
    }
  ]
}
```

#### Nginx Configuration (SSL)

```nginx
server {
    listen 80;
    server_name api.your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # File upload limit
    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

---

## 🔄 Resiliency Patterns

### Celery Retry Policy

```python
@celery_app.task(
    bind=True,
    autoretry_for=(OpenAIError, ConnectionError),
    retry_backoff=True,        # Exponential backoff
    retry_backoff_max=60,      # Max 60s between retries
    retry_jitter=True,         # Add randomness
    max_retries=3              # Max 3 attempts
)
def process_document(self, document_id: str):
    try:
        # Processing logic
        pass
    except Exception as exc:
        # After 3 retries, move to DLQ
        if self.request.retries >= 3:
            mark_document_failed(document_id, str(exc))
            raise Reject(exc, requeue=False)
        raise
```

### Circuit Breaker Pattern

```python
from circuitbreaker import circuit

@circuit(
    failure_threshold=5,     # Open after 5 failures
    recovery_timeout=30,     # Try again after 30s
    expected_exception=OpenAIError
)
async def call_openai_with_circuit_breaker(prompt: str):
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            # ...
        )
    return response.json()
```

### Fallback Response

```python
async def rag_query(question: str) -> RAGResponse:
    try:
        return await call_openai_with_circuit_breaker(question)
    except CircuitBreakerError:
        return RAGResponse(
            answer="Hệ thống đang tải cao, vui lòng thử lại sau 30 giây.",
            sources=[],
            error_code="SERVICE_OVERLOADED"
        )
```

---

## 🧪 Testing

### Run Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_rag_service.py -v
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_auth.py             # Auth endpoint tests
├── test_documents.py        # Document API tests
├── test_rag.py              # RAG query tests
├── test_services/
│   ├── test_chunking.py     # Chunking service tests
│   └── test_embedding.py    # Embedding service tests
└── test_integration/
    └── test_full_pipeline.py
```

---

## 🤝 Contributing

1. Fork repository
2. Tạo feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Tạo Pull Request

### Code Style

- Sử dụng **Black** cho Python formatting
- Sử dụng **isort** cho import sorting
- Type hints bắt buộc cho tất cả functions
- Docstrings theo Google style

```bash
# Format code
black app/
isort app/

# Type checking
mypy app/
```

---

## 📄 License

MIT License - xem file [LICENSE](LICENSE) để biết thêm chi tiết.

---

## 📞 Support

- **Documentation**: [docs/](docs/)
- **Issues**: GitHub Issues
- **Email**: support@your-domain.com

---

<p align="center">
  Built with ❤️ by Your Team
</p>
# doc-automation-engine
