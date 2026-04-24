# 📚 API Reference - Enterprise Multi-Tenant RAG

> Complete API documentation với examples sử dụng cURL và Python.

---

## 🔑 Base Information

### Endpoints

| Environment | Base URL |
|-------------|----------|
| Development | `http://localhost:8000/api/v1` |
| Staging | `https://staging-api.your-domain.com/api/v1` |
| Production | `https://api.your-domain.com/api/v1` |

### Authentication

Tất cả API endpoints (trừ Auth) yêu cầu JWT Bearer token:

```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Request Headers

```http
Content-Type: application/json
Authorization: Bearer <access_token>
X-Request-ID: <optional-tracking-id>
```

### Response Format

**Success Response:**
```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-02-23T10:00:00Z"
  }
}
```

**Error Response:**
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": { ... }
  },
  "request_id": "req_abc123",
  "timestamp": "2026-02-23T10:00:00Z"
}
```

---

## 🔐 Authentication API

### Register User

Tạo tài khoản user mới.

**Endpoint:** `POST /auth/register`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "Nguyen Van A"
  }'
```

**Python:**
```python
import httpx

response = httpx.post(
    "http://localhost:8000/api/v1/auth/register",
    json={
        "email": "user@example.com",
        "password": "SecurePassword123!",
        "full_name": "Nguyen Van A"
    }
)
print(response.json())
```

**Response (201 Created):**
```json
{
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "full_name": "Nguyen Van A",
    "is_active": true,
    "created_at": "2026-02-23T10:00:00Z"
  }
}
```

**Validation Rules:**
- `email`: Valid email format, unique
- `password`: Min 8 chars, must contain uppercase, lowercase, number
- `full_name`: Min 2 chars, max 255 chars

---

### Login

Đăng nhập và nhận JWT token.

**Endpoint:** `POST /auth/login`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=SecurePassword123!"
```

**Python:**
```python
import httpx

response = httpx.post(
    "http://localhost:8000/api/v1/auth/login",
    data={
        "username": "user@example.com",
        "password": "SecurePassword123!"
    }
)
token_data = response.json()
access_token = token_data["access_token"]
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### Get Current User

Lấy thông tin user đang đăng nhập và danh sách tenants.

**Endpoint:** `GET /auth/me`

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer <access_token>"
```

**Python:**
```python
import httpx

headers = {"Authorization": f"Bearer {access_token}"}
response = httpx.get(
    "http://localhost:8000/api/v1/auth/me",
    headers=headers
)
print(response.json())
```

**Response (200 OK):**
```json
{
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "full_name": "Nguyen Van A",
    "tenants": [
      {
        "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
        "tenant_name": "Company ABC",
        "role": "owner"
      },
      {
        "tenant_id": "770e8400-e29b-41d4-a716-446655440002",
        "tenant_name": "Project XYZ",
        "role": "viewer"
      }
    ]
  }
}
```

---

### Refresh Token

Làm mới access token.

**Endpoint:** `POST /auth/refresh`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Authorization: Bearer <access_token>"
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

## 🏢 Tenant API

### Create Tenant

Tạo workspace/tenant mới. User tạo sẽ tự động được gán role `owner`.

**Endpoint:** `POST /tenants`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Company ABC",
    "description": "Main workspace for Company ABC documents"
  }'
```

**Python:**
```python
import httpx

response = httpx.post(
    "http://localhost:8000/api/v1/tenants",
    headers={"Authorization": f"Bearer {access_token}"},
    json={
        "name": "Company ABC",
        "description": "Main workspace for Company ABC documents"
    }
)
print(response.json())
```

**Response (201 Created):**
```json
{
  "data": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "Company ABC",
    "description": "Main workspace for Company ABC documents",
    "billing_status": "active",
    "created_at": "2026-02-23T10:00:00Z"
  }
}
```

---

### List User's Tenants

Liệt kê tất cả tenants mà user có quyền truy cập.

**Endpoint:** `GET /tenants`

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/tenants" \
  -H "Authorization: Bearer <access_token>"
```

**Response (200 OK):**
```json
{
  "data": {
    "items": [
      {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "name": "Company ABC",
        "role": "owner",
        "document_count": 150,
        "created_at": "2026-02-23T10:00:00Z"
      }
    ],
    "total": 1
  }
}
```

---

### Get Tenant Details

Lấy thông tin chi tiết tenant, bao gồm members và usage stats.

**Endpoint:** `GET /tenants/{tenant_id}`

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/tenants/660e8400-e29b-41d4-a716-446655440001" \
  -H "Authorization: Bearer <access_token>"
```

**Response (200 OK):**
```json
{
  "data": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "Company ABC",
    "description": "Main workspace for Company ABC documents",
    "billing_status": "active",
    "members": [
      {
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "user@example.com",
        "full_name": "Nguyen Van A",
        "role": "owner",
        "joined_at": "2026-02-23T10:00:00Z"
      }
    ],
    "usage": {
      "total_documents": 150,
      "completed_documents": 145,
      "processing_documents": 3,
      "failed_documents": 2,
      "total_chunks": 4500,
      "total_tokens_used": 1250000,
      "storage_used_mb": 450.5,
      "estimated_cost_usd": 12.50
    },
    "created_at": "2026-02-23T10:00:00Z"
  }
}
```

---

### Invite Member

Mời user khác vào tenant. Yêu cầu role `owner` hoặc `admin`.

**Endpoint:** `POST /tenants/{tenant_id}/invite`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants/660e8400-e29b-41d4-a716-446655440001/invite" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newmember@example.com",
    "role": "admin"
  }'
```

**Available Roles:**

| Role | Permissions |
|------|-------------|
| `owner` | Full access, manage billing, delete tenant |
| `admin` | Upload/delete documents, invite members |
| `viewer` | View documents, run queries |

**Response (200 OK):**
```json
{
  "data": {
    "message": "Invitation sent to newmember@example.com",
    "user_id": "880e8400-e29b-41d4-a716-446655440003",
    "role": "admin"
  }
}
```

---

### Update Member Role

Thay đổi role của member. Yêu cầu role `owner`.

**Endpoint:** `PATCH /tenants/{tenant_id}/members/{user_id}`

**Request:**
```bash
curl -X PATCH "http://localhost:8000/api/v1/tenants/660e8400-.../members/880e8400-..." \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"role": "viewer"}'
```

---

### Remove Member

Xóa member khỏi tenant. Yêu cầu role `owner` hoặc `admin`.

**Endpoint:** `DELETE /tenants/{tenant_id}/members/{user_id}`

**Response:** `204 No Content`

---

### Get Usage Statistics

Lấy thống kê sử dụng token theo thời gian.

**Endpoint:** `GET /tenants/{tenant_id}/usage`

**Query Parameters:**
- `from_date` (string): Start date (YYYY-MM-DD)
- `to_date` (string): End date (YYYY-MM-DD)
- `group_by` (string): `day`, `week`, `month`

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/tenants/660e8400-.../usage?from_date=2026-02-01&to_date=2026-02-23&group_by=day" \
  -H "Authorization: Bearer <access_token>"
```

**Response (200 OK):**
```json
{
  "data": {
    "summary": {
      "total_tokens": 1250000,
      "embedding_tokens": 800000,
      "chat_tokens": 450000,
      "estimated_cost_usd": 12.50
    },
    "breakdown": [
      {
        "date": "2026-02-22",
        "embedding_tokens": 50000,
        "chat_tokens": 25000,
        "query_count": 150,
        "cost_usd": 0.75
      },
      {
        "date": "2026-02-23",
        "embedding_tokens": 30000,
        "chat_tokens": 18000,
        "query_count": 120,
        "cost_usd": 0.48
      }
    ]
  }
}
```

---

## 📄 Document API

### Upload Document

Upload document mới. File sẽ được validate và đưa vào queue xử lý background.

**Endpoint:** `POST /tenants/{tenant_id}/documents`

**Content-Type:** `multipart/form-data`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants/660e8400-.../documents" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/document.pdf" \
  -F "title=Company Policy 2026" \
  -F "description=Nội quy công ty bản cập nhật năm 2026" \
  -F "tags=policy,hr,2026"
```

**Python:**
```python
import httpx

with open("document.pdf", "rb") as f:
    response = httpx.post(
        "http://localhost:8000/api/v1/tenants/660e8400-.../documents",
        headers={"Authorization": f"Bearer {access_token}"},
        files={"file": ("document.pdf", f, "application/pdf")},
        data={
            "title": "Company Policy 2026",
            "description": "Nội quy công ty bản cập nhật năm 2026",
            "tags": "policy,hr,2026"
        }
    )
print(response.json())
```

**Validation:**
| Rule | Value |
|------|-------|
| Max file size | 10 MB |
| Allowed MIME types | `application/pdf`, `text/plain`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| File verification | Magic bytes check (không tin file extension) |

**Response (202 Accepted):**
```json
{
  "data": {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "title": "Company Policy 2026",
    "description": "Nội quy công ty bản cập nhật năm 2026",
    "status": "processing",
    "file_name": "document.pdf",
    "file_size_bytes": 2457600,
    "mime_type": "application/pdf",
    "tags": ["policy", "hr", "2026"],
    "uploaded_by": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2026-02-23T10:00:00Z"
  },
  "meta": {
    "message": "Document đang được xử lý. Kiểm tra status sau vài phút."
  }
}
```

---

### List Documents

Liệt kê documents của tenant với pagination và filtering.

**Endpoint:** `GET /tenants/{tenant_id}/documents`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Trang hiện tại |
| `limit` | int | 20 | Số items/trang (max 100) |
| `status` | string | - | Filter: `processing`, `completed`, `failed` |
| `search` | string | - | Search trong title |
| `tags` | string | - | Filter theo tags (comma-separated) |
| `sort_by` | string | `created_at` | Sort field |
| `sort_order` | string | `desc` | `asc` hoặc `desc` |

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/tenants/660e8400-.../documents?page=1&limit=10&status=completed&tags=policy" \
  -H "Authorization: Bearer <access_token>"
```

**Response (200 OK):**
```json
{
  "data": {
    "items": [
      {
        "id": "990e8400-e29b-41d4-a716-446655440004",
        "title": "Company Policy 2026",
        "status": "completed",
        "file_name": "document.pdf",
        "file_size_bytes": 2457600,
        "chunk_count": 45,
        "tags": ["policy", "hr", "2026"],
        "created_at": "2026-02-23T10:00:00Z",
        "processed_at": "2026-02-23T10:02:30Z"
      }
    ],
    "pagination": {
      "total": 150,
      "page": 1,
      "limit": 10,
      "pages": 15,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

---

### Get Document Details

Lấy thông tin chi tiết document.

**Endpoint:** `GET /tenants/{tenant_id}/documents/{document_id}`

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/tenants/660e8400-.../documents/990e8400-..." \
  -H "Authorization: Bearer <access_token>"
```

**Response (200 OK):**
```json
{
  "data": {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "title": "Company Policy 2026",
    "description": "Nội quy công ty bản cập nhật năm 2026",
    "status": "completed",
    "file_name": "document.pdf",
    "file_size_bytes": 2457600,
    "mime_type": "application/pdf",
    "chunk_count": 45,
    "embedding_model": "text-embedding-3-small",
    "tags": ["policy", "hr", "2026"],
    "uploaded_by": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user@example.com",
      "full_name": "Nguyen Van A"
    },
    "processing_stats": {
      "total_characters": 125000,
      "total_tokens_embedded": 35000,
      "processing_time_seconds": 150
    },
    "created_at": "2026-02-23T10:00:00Z",
    "processed_at": "2026-02-23T10:02:30Z"
  }
}
```

---

### Get Document Processing Status

Kiểm tra trạng thái xử lý document (polling endpoint).

**Endpoint:** `GET /tenants/{tenant_id}/documents/{document_id}/status`

**Response (200 OK):**
```json
{
  "data": {
    "document_id": "990e8400-e29b-41d4-a716-446655440004",
    "status": "processing",
    "progress": {
      "stage": "embedding",
      "completed_chunks": 30,
      "total_chunks": 45,
      "percentage": 67
    },
    "started_at": "2026-02-23T10:00:30Z",
    "estimated_completion": "2026-02-23T10:02:30Z"
  }
}
```

**Status Values:**
- `pending` - Đang trong queue
- `processing` - Đang xử lý
- `completed` - Hoàn tất
- `failed` - Thất bại

---

### Update Document Metadata

Cập nhật title, description, tags.

**Endpoint:** `PATCH /tenants/{tenant_id}/documents/{document_id}`

**Request:**
```bash
curl -X PATCH "http://localhost:8000/api/v1/tenants/660e8400-.../documents/990e8400-..." \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Company Policy 2026 (Updated)",
    "tags": ["policy", "hr", "2026", "important"]
  }'
```

**Response (200 OK):**
```json
{
  "data": {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "title": "Company Policy 2026 (Updated)",
    "tags": ["policy", "hr", "2026", "important"],
    "updated_at": "2026-02-23T11:00:00Z"
  }
}
```

---

### Delete Document

Xóa document và tất cả chunks/embeddings liên quan. Yêu cầu role `admin` trở lên.

**Endpoint:** `DELETE /tenants/{tenant_id}/documents/{document_id}`

**Request:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/tenants/660e8400-.../documents/990e8400-..." \
  -H "Authorization: Bearer <access_token>"
```

**Response:** `204 No Content`

---

### Reprocess Document

Xử lý lại document (dùng khi status = failed hoặc muốn re-embed).

**Endpoint:** `POST /tenants/{tenant_id}/documents/{document_id}/reprocess`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants/660e8400-.../documents/990e8400-.../reprocess" \
  -H "Authorization: Bearer <access_token>"
```

**Response (202 Accepted):**
```json
{
  "data": {
    "document_id": "990e8400-e29b-41d4-a716-446655440004",
    "status": "processing",
    "message": "Document được đưa vào queue xử lý lại."
  }
}
```

---

## 🤖 RAG API

### Query (Main RAG Endpoint)

Hỏi đáp dựa trên documents của tenant. Đây là endpoint chính của RAG system.

**Endpoint:** `POST /tenants/{tenant_id}/query`

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `question` | string | ✅ | - | Câu hỏi của user |
| `top_k` | int | ❌ | 5 | Số chunks retrieve (1-20) |
| `search_type` | string | ❌ | `hybrid` | `semantic`, `keyword`, `hybrid` |
| `include_sources` | bool | ❌ | true | Include source documents |
| `temperature` | float | ❌ | 0.7 | LLM creativity (0-1) |
| `max_tokens` | int | ❌ | 1000 | Max response tokens |
| `document_ids` | array | ❌ | null | Filter specific documents |
| `tags` | array | ❌ | null | Filter by document tags |

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants/660e8400-.../query" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Chính sách nghỉ phép của công ty như thế nào?",
    "top_k": 5,
    "search_type": "hybrid",
    "include_sources": true,
    "temperature": 0.7
  }'
```

**Python:**
```python
import httpx

response = httpx.post(
    "http://localhost:8000/api/v1/tenants/660e8400-.../query",
    headers={"Authorization": f"Bearer {access_token}"},
    json={
        "question": "Chính sách nghỉ phép của công ty như thế nào?",
        "top_k": 5,
        "search_type": "hybrid",
        "include_sources": True
    },
    timeout=30.0  # RAG queries có thể mất thời gian
)
print(response.json())
```

**Response (200 OK):**
```json
{
  "data": {
    "answer": "Theo chính sách công ty, nhân viên chính thức được nghỉ phép **12 ngày/năm**. Cụ thể:\n\n1. **Nhân viên chính thức**: 12 ngày phép năm\n2. **Nhân viên thử việc**: Không có phép năm, chỉ được nghỉ không lương\n3. **Quy trình đăng ký**:\n   - Đăng nhập HR Portal\n   - Chọn ngày nghỉ và loại phép\n   - Gửi yêu cầu cho quản lý\n   - Phải được phê duyệt trước ít nhất 3 ngày làm việc\n\nNgoài ra, nhân viên được nghỉ thêm 3 ngày phép khi có thâm niên từ 5 năm trở lên.",
    "sources": [
      {
        "document_id": "990e8400-e29b-41d4-a716-446655440004",
        "document_title": "Company Policy 2026",
        "chunk_id": "chunk_23",
        "content": "Điều 15: Chế độ nghỉ phép năm\n\n15.1. Nhân viên chính thức được hưởng 12 ngày phép năm, tính từ ngày ký hợp đồng chính thức.\n\n15.2. Nhân viên thử việc không được hưởng phép năm.\n\n15.3. Nhân viên có thâm niên từ 5 năm trở lên được cộng thêm 3 ngày phép/năm.",
        "relevance_score": 0.94,
        "page_number": 12
      },
      {
        "document_id": "aa0e8400-e29b-41d4-a716-446655440005",
        "document_title": "HR Guidelines",
        "chunk_id": "chunk_8",
        "content": "Quy trình đăng ký nghỉ phép:\n\n1. Đăng nhập vào HR Portal (hr.company.com)\n2. Chọn mục 'Đăng ký nghỉ phép'\n3. Chọn loại phép: Phép năm / Phép không lương / Phép ốm\n4. Chọn ngày bắt đầu và kết thúc\n5. Nhập lý do nghỉ phép\n6. Submit và chờ quản lý phê duyệt\n\nLưu ý: Yêu cầu cần được gửi trước ít nhất 3 ngày làm việc.",
        "relevance_score": 0.89,
        "page_number": 5
      }
    ],
    "confidence_score": 0.91,
    "usage": {
      "prompt_tokens": 1250,
      "completion_tokens": 320,
      "total_tokens": 1570,
      "estimated_cost_usd": 0.0024
    },
    "processing_time_ms": 2340
  }
}
```

---

### Search (Semantic Search Only)

Tìm kiếm documents liên quan mà không generate answer từ LLM.

**Endpoint:** `POST /tenants/{tenant_id}/search`

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | ✅ | - | Search query |
| `top_k` | int | ❌ | 10 | Number of results |
| `search_type` | string | ❌ | `hybrid` | Search method |
| `filters` | object | ❌ | null | Advanced filters |
| `highlight` | bool | ❌ | true | Highlight matches |

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants/660e8400-.../search" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "chính sách nghỉ phép thâm niên",
    "top_k": 10,
    "search_type": "hybrid",
    "filters": {
      "tags": ["policy", "hr"],
      "date_from": "2025-01-01"
    },
    "highlight": true
  }'
```

**Response (200 OK):**
```json
{
  "data": {
    "results": [
      {
        "document_id": "990e8400-e29b-41d4-a716-446655440004",
        "document_title": "Company Policy 2026",
        "chunk_id": "chunk_23",
        "content": "Điều 15: Chế độ nghỉ phép năm...",
        "highlight": "Nhân viên có <em>thâm niên</em> từ 5 năm trở lên được cộng thêm 3 ngày <em>phép</em>/năm",
        "score": 0.94,
        "metadata": {
          "page_number": 12,
          "tags": ["policy", "hr", "2026"]
        }
      }
    ],
    "total_results": 15,
    "search_type": "hybrid",
    "processing_time_ms": 125
  }
}
```

---

### Get Similar Chunks

Tìm chunks tương tự với một chunk cụ thể (useful for "See more like this").

**Endpoint:** `GET /tenants/{tenant_id}/chunks/{chunk_id}/similar`

**Query Parameters:**
- `top_k` (int): Number of similar chunks (default: 5)

**Response (200 OK):**
```json
{
  "data": {
    "source_chunk": {
      "chunk_id": "chunk_23",
      "document_title": "Company Policy 2026",
      "content": "Điều 15: Chế độ nghỉ phép năm..."
    },
    "similar_chunks": [
      {
        "chunk_id": "chunk_24",
        "document_id": "990e8400-...",
        "document_title": "Company Policy 2026",
        "content": "Điều 16: Chế độ nghỉ ốm...",
        "similarity_score": 0.85
      }
    ]
  }
}
```

---

## 🔄 Streaming API

### Query with Streaming

Stream response từ LLM (Server-Sent Events).

**Endpoint:** `POST /tenants/{tenant_id}/query/stream`

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/tenants/660e8400-.../query/stream" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "question": "Chính sách nghỉ phép của công ty như thế nào?",
    "top_k": 5
  }'
```

**Python với Streaming:**
```python
import httpx

with httpx.stream(
    "POST",
    "http://localhost:8000/api/v1/tenants/660e8400-.../query/stream",
    headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "text/event-stream"
    },
    json={"question": "Chính sách nghỉ phép?", "top_k": 5}
) as response:
    for line in response.iter_lines():
        if line.startswith("data: "):
            data = line[6:]  # Remove "data: " prefix
            if data == "[DONE]":
                break
            print(data, end="", flush=True)
```

**SSE Response Format:**
```
event: sources
data: {"sources": [{"document_id": "...", "title": "..."}]}

event: token
data: {"content": "Theo"}

event: token
data: {"content": " chính"}

event: token
data: {"content": " sách"}

...

event: done
data: {"usage": {"total_tokens": 1570}, "processing_time_ms": 2340}
```

---

## ❌ Error Codes Reference

### HTTP Status Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 201 | Created |
| 202 | Accepted (async processing started) |
| 204 | No Content (successful deletion) |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 413 | Payload Too Large |
| 415 | Unsupported Media Type |
| 422 | Validation Error |
| 429 | Too Many Requests |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

### Error Codes Detail

```json
{
  "VALIDATION_ERROR": "Request body validation failed",
  "INVALID_CREDENTIALS": "Email hoặc password không đúng",
  "TOKEN_EXPIRED": "JWT token đã hết hạn",
  "TOKEN_INVALID": "JWT token không hợp lệ",
  "PERMISSION_DENIED": "Không có quyền thực hiện action này",
  "TENANT_NOT_FOUND": "Tenant không tồn tại",
  "DOCUMENT_NOT_FOUND": "Document không tồn tại",
  "FILE_TOO_LARGE": "File vượt quá giới hạn 10MB",
  "UNSUPPORTED_FILE_TYPE": "Loại file không được hỗ trợ",
  "CORRUPTED_FILE": "File bị hỏng hoặc không thể đọc",
  "PROCESSING_FAILED": "Xử lý document thất bại",
  "RATE_LIMITED": "Quá nhiều requests, vui lòng thử lại sau",
  "SERVICE_OVERLOADED": "Hệ thống đang tải cao",
  "OPENAI_ERROR": "Lỗi khi gọi OpenAI API",
  "SEARCH_ERROR": "Lỗi khi search OpenSearch"
}
```

---

## 📊 Rate Limits

| Endpoint Category | Rate Limit | Window |
|-------------------|------------|--------|
| Auth (login/register) | 5 requests | 1 minute |
| Document Upload | 10 requests | 1 minute |
| RAG Query | 30 requests | 1 minute |
| Search | 60 requests | 1 minute |
| Other endpoints | 100 requests | 1 minute |

**Rate Limit Headers:**
```http
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1708684800
```

---

## 🧪 Testing with Postman

Import collection: [Download Postman Collection](./docs/postman_collection.json)

**Environment Variables:**
```json
{
  "base_url": "http://localhost:8000/api/v1",
  "access_token": "",
  "tenant_id": ""
}
```

---

## 📝 Changelog

### v2.0.0 (2026-03-10)
- **Engine 2:** Structured Data Extraction — 20 new endpoints
- Template CRUD with JSONB schema_definition
- 3 extraction modes: standard / vision / fast
- Validation Layer (DataValidator) — auto type coercion
- Aggregation & Map-Reduce (Pandas)
- Word Template Export (docxtpl)
- Word Template Scanner (auto-generate schema from .docx)
- JSONB + GIN indexes for high-speed JSON search
- See [Engine 2 Technical Spec](./engine2_technical_spec.md) for full documentation

### v1.0.0 (2026-02-23)
- Initial release
- Authentication API
- Tenant Management
- Document Upload & Processing
- RAG Query & Search
- Streaming Support
