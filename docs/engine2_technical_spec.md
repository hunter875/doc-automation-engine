# Engine 2 Technical Spec

Tai lieu nay mo ta trang thai hien tai sau khi da go bo SheetPipeline va cac luong legacy khong con dung.

## 1. Scope

Engine 2 xu ly luong tu PDF bao cao ngay den bao cao tong hop Word:

```text
PDF upload
  -> ExtractionJob
  -> BlockExtractionPipeline
  -> optional enrichment task
  -> human review
  -> AggregationService
  -> Word export
```

Ngoai pham vi hien tai:

- SheetPipeline, Google Sheets inspection, tab inspect.
- Streamlit UI.
- Free-form RAG/vector-search API.
- `standard`, `vision`, `fast` extraction modes for new jobs.

Active extraction mode: `block`.

## 2. Main Modules

| Area | Path | Purpose |
|---|---|---|
| API bootstrap | `app/main.py` | FastAPI app, router registration, startup migration guard |
| Auth | `app/api/v1/auth.py` | JWT login/register/current user |
| Tenant | `app/api/v1/tenant.py` | Multi-tenant membership and role API |
| Documents | `app/api/v1/document.py` | Upload, list, download, reprocess documents |
| Templates | `app/api/v1/templates.py` | Extraction template CRUD and Word template scan |
| Jobs | `app/api/v1/jobs.py` | Upload PDFs, create jobs, review, retry, calendar, dashboard |
| Aggregation | `app/api/v1/aggregation.py` | Aggregate approved jobs and export reports |
| Reports calendar | `app/api/v1/reports.py` | Daily/weekly report calendar APIs |
| Job service | `app/application/job_service.py` | Job creation, listing, status, persistence |
| Template service | `app/application/template_service.py` | Template CRUD and extraction mode defaults |
| Aggregation service | `app/application/aggregation_service.py` | Map-reduce over reviewed job data |
| Block pipeline | `app/engines/extraction/block_pipeline.py` | Deterministic PDF parsing and business extraction |
| Batch runner | `app/engines/extraction/batch.py` | In-process block batch execution |
| Orchestrator | `app/engines/extraction/orchestrator.py` | Loads job input and runs extraction |
| Worker config | `app/infrastructure/worker/celery_app.py` | Celery queues and periodic tasks |
| File operator | `app/infrastructure/worker/operator_tasks.py` | MinIO inbox polling and batch auto-close |
| Word scanner | `app/utils/word_scanner.py` | Scan `.docx` placeholders into template schema |
| Word export | `app/utils/word_export.py` | Render report data into `.docx` |
| Frontend | `frontend/` | Next.js management UI |

## 3. Extraction Mode Contract

New templates and jobs default to `block`.

Persistence accepts old database rows that contain `standard`, `vision`, or `fast` only as migration input. On startup, `app/main.py` normalizes those rows to `block`.

API request schemas now only accept `block` for user-created jobs.

## 4. Job Lifecycle

```text
pending
  -> processing
  -> extracted
  -> ready_for_review
  -> approved
  -> aggregated
```

Failure/rework states:

- `failed`: extraction or worker error.
- `rejected`: human reviewer rejected the extracted payload.

The frontend should treat `ready_for_review` as the review queue and `approved` as eligible for aggregation.

## 5. Data Authority

| Data | Source of truth |
|---|---|
| Tenant scope | `X-Tenant-ID` plus authenticated user membership |
| Template schema | `extraction_templates.schema_definition` |
| Active extraction mode | `extraction_templates.extraction_mode = block` |
| Raw uploaded file | MinIO object referenced by `documents.file_path` / object key |
| Extraction result | `extraction_jobs.extracted_data` |
| Human-edited result | `extraction_jobs.reviewed_data` |
| Final aggregation input | Reviewed data first, extracted data fallback |
| Aggregated report | `aggregation_reports.aggregated_data` |
| Word output | Runtime render from saved/uploaded `.docx` template |

## 6. Queues

| Queue | Worker | Purpose |
|---|---|---|
| `extraction` | `celery-extraction-worker` | Run extraction jobs |
| `enrichment` | `celery-enrichment-worker` | Optional async LLM enrichment |
| `document_processing` | `celery-worker` | General document tasks |
| `default` | `celery-worker` | Misc tasks |

The old `embeddings` queue is no longer routed.

## 7. API Surface

Primary prefix: `/api/v1/extraction`.

Important groups:

- `/templates`: template scan, create, list, update, delete.
- `/jobs`: single upload, batch upload, smart upload, list, detail, retry, delete.
- `/review/{job_id}/approve` and `/review/{job_id}/reject`.
- `/aggregate`: create/list/read/delete/export aggregation reports.
- `/jobs/by-date`: calendar summary for the Next.js UI.
- `/dashboard`: dashboard metrics.

Full endpoint list lives in `docs/API_REFERENCE.md`.

## 8. Frontend Contract

The Next.js UI imports shared helpers from `frontend/lib`:

- `api.ts`: typed fetch wrapper and endpoint groups.
- `auth.ts`: local auth token and tenant persistence.
- `types.ts`: API-facing TypeScript models.
- `utils.ts`: class merge, date format, download helpers.

SheetPipeline UI and inspect tabs have been removed. The active UI areas are dashboard, documents, extraction templates/jobs/review/export, and tenant-aware auth context.

## 9. Docker Compose

Core services:

- `rag-api`: FastAPI.
- `rag-frontend`: Next.js dev server.
- `rag-celery-worker`: default/document queues.
- `rag-celery-extraction`: extraction queue, concurrency 1.
- `rag-celery-enrichment`: enrichment queue.
- `rag-celery-beat`: scheduled cleanup/operator tasks.
- `rag-postgres`, `rag-redis`, `rag-minio`.

## 10. Operational Notes

- Keep `GEMINI_API_KEY` optional when using the default Ollama path.
- Keep `OLLAMA_BASE_URL` reachable from Docker as `http://host.docker.internal:11434`.
- If old database rows were created before the block-only cleanup, restart the API once so startup normalization can rewrite legacy extraction modes.
- Do not reintroduce SheetPipeline code paths unless the API, UI, docs, and tests are all updated together.
