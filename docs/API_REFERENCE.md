# API Reference

Current API surface for Doc Automation Engine after removing the sheet pipeline flow.

Base URL: `http://localhost:8000`

Most endpoints require:

- `Authorization: Bearer <TOKEN>`
- `X-Tenant-ID: <TENANT_ID>` for tenant-scoped resources

## Auth

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Create user account |
| `POST` | `/api/v1/auth/login` | Return JWT access token |
| `GET` | `/api/v1/auth/me` | Current user profile |
| `POST` | `/api/v1/auth/refresh` | Refresh access token |

## Tenants

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/tenants` | Create tenant |
| `GET` | `/api/v1/tenants` | List current user's tenants |
| `GET` | `/api/v1/tenants/{tenant_id}` | Get current tenant context |
| `PATCH` | `/api/v1/tenants/{tenant_id}` | Update tenant |
| `DELETE` | `/api/v1/tenants/{tenant_id}` | Delete tenant |
| `GET` | `/api/v1/tenants/{tenant_id}/members` | List members |
| `POST` | `/api/v1/tenants/{tenant_id}/members` | Add member |
| `PATCH` | `/api/v1/tenants/{tenant_id}/members/{user_id}` | Change member role |
| `DELETE` | `/api/v1/tenants/{tenant_id}/members/{user_id}` | Remove member |

## Documents

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/documents/upload` | Upload source document |
| `GET` | `/api/v1/documents` | List documents |
| `GET` | `/api/v1/documents/{document_id}` | Get document metadata |
| `PATCH` | `/api/v1/documents/{document_id}` | Update document metadata |
| `DELETE` | `/api/v1/documents/{document_id}` | Delete document |
| `GET` | `/api/v1/documents/{document_id}/download` | Download original file |
| `POST` | `/api/v1/documents/{document_id}/reprocess` | Reset document processing status |
| `GET` | `/api/v1/documents/stats/summary` | Tenant document stats |

## Templates

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/extraction/templates/scan-word` | Scan a `.docx` template and save it to MinIO |
| `POST` | `/api/v1/extraction/templates` | Create extraction template |
| `GET` | `/api/v1/extraction/templates` | List templates |
| `GET` | `/api/v1/extraction/templates/{template_id}` | Get template |
| `PATCH` | `/api/v1/extraction/templates/{template_id}` | Update template |
| `DELETE` | `/api/v1/extraction/templates/{template_id}` | Soft-delete template |

Active extraction mode is `block`.

## Extraction Jobs

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/extraction/jobs` | Upload one PDF and queue extraction |
| `POST` | `/api/v1/extraction/jobs/batch` | Upload multiple PDFs |
| `POST` | `/api/v1/extraction/jobs/smart-upload` | Auto-detect template and queue extraction |
| `POST` | `/api/v1/extraction/jobs/from-document` | Create job from existing document |
| `GET` | `/api/v1/extraction/jobs` | List jobs |
| `GET` | `/api/v1/extraction/jobs/{job_id}` | Get job detail |
| `DELETE` | `/api/v1/extraction/jobs/{job_id}` | Delete finished job |
| `POST` | `/api/v1/extraction/jobs/{job_id}/retry` | Retry failed/rejected job |
| `GET` | `/api/v1/extraction/jobs/batch/{batch_id}/status` | Batch progress |
| `GET` | `/api/v1/extraction/jobs/by-date?month=5&year=2026` | Calendar job summary |
| `GET` | `/api/v1/extraction/dashboard` | Dashboard metrics |
| `GET` | `/api/v1/extraction/metrics` | Pipeline metrics |

## Review

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/extraction/review/{job_id}/approve` | Approve or edit extracted JSON |
| `POST` | `/api/v1/extraction/review/{job_id}/reject` | Reject job with notes |

## Aggregation And Export

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/extraction/aggregate` | Aggregate approved jobs |
| `POST` | `/api/v1/extraction/reports/create-by-date` | Aggregate by calendar date |
| `POST` | `/api/v1/extraction/reports/daily` | Generate daily report DOCX |
| `GET` | `/api/v1/extraction/aggregate` | List reports |
| `GET` | `/api/v1/extraction/aggregate/{report_id}` | Get report |
| `DELETE` | `/api/v1/extraction/aggregate/{report_id}` | Delete report |
| `GET` | `/api/v1/extraction/aggregate/{report_id}/export?format=excel` | Export Excel |
| `GET` | `/api/v1/extraction/aggregate/{report_id}/export?format=csv` | Export CSV |
| `GET` | `/api/v1/extraction/aggregate/{report_id}/export?format=json` | Export JSON |
| `POST` | `/api/v1/extraction/aggregate/{report_id}/export-word` | Export Word using uploaded template |
| `GET` | `/api/v1/extraction/aggregate/{report_id}/export-word-auto` | Export Word using saved template |

## Report Calendar

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/reports/calendar` | Calendar dates with available reports |
| `GET` | `/api/reports/daily?date=2026-05-18` | Daily report payload |
| `POST` | `/api/reports/weekly` | Generate weekly report |
| `GET` | `/api/reports/weekly?week_start=2026-05-18` | Get weekly report |

## Main Flow

```bash
# 1. Login
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin1234!"}'

# 2. Upload and queue extraction
curl -s -X POST http://localhost:8000/api/v1/extraction/jobs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "X-Tenant-ID: <TENANT_ID>" \
  -F "file=@./report.pdf;type=application/pdf" \
  -F "template_id=<TEMPLATE_ID>"

# 3. Approve after review
curl -s -X POST http://localhost:8000/api/v1/extraction/review/<JOB_ID>/approve \
  -H "Authorization: Bearer <TOKEN>" \
  -H "X-Tenant-ID: <TENANT_ID>" \
  -H "Content-Type: application/json" \
  -d '{"notes":"ok"}'

# 4. Aggregate approved jobs
curl -s -X POST http://localhost:8000/api/v1/extraction/aggregate \
  -H "Authorization: Bearer <TOKEN>" \
  -H "X-Tenant-ID: <TENANT_ID>" \
  -H "Content-Type: application/json" \
  -d '{"template_id":"<TEMPLATE_ID>","job_ids":["<JOB_ID>"],"report_name":"Bao cao"}'
```
