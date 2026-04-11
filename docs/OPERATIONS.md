# OPERATIONS GUIDE

## 1. Runtime Environment

All application services run as Docker containers orchestrated by `docker-compose.yml`. Containers share a single bridge network named `rag-network`.

**Ollama is NOT containerized.** It runs as a native process on the host machine and is accessed from containers via `host.docker.internal:11434`. It must be started separately and independently of Docker Compose.

**Code deployment model:** Application code is baked into images at build time via `COPY . .` in the Dockerfile. There is no bind mount. A code change requires a container rebuild before it takes effect.

**Container restart policy:** All services use `restart: unless-stopped`. Containers restart automatically on crash or host reboot unless explicitly stopped by the operator.

**Environment:** `DEBUG=true` is hardcoded in `docker-compose.yml` for the `api` service.

---

## 2. Services

| Container | Image | Port(s) | Responsibility |
|---|---|---|---|
| `rag-api` | Local build | `8000` | FastAPI HTTP API — request handling, auth, DB writes |
| `rag-streamlit` | Local build | `8501` | Streamlit operator UI |
| `rag-celery-worker` | Local build | — | Queues: `default`, `document_processing`, `embeddings`. Concurrency: 4 |
| `rag-celery-extraction` | Local build | — | Queue: `extraction`. Concurrency: **1**. Max tasks per child: 10 |
| `rag-celery-enrichment` | Local build | — | Queue: `enrichment`. Concurrency: 2. Max tasks per child: 10 |
| `rag-celery-beat` | Local build | — | Celery Beat periodic scheduler |
| `rag-postgres` | `pgvector/pgvector:pg15` | `5432` | Primary database. Named volume: `postgres-data` |
| `rag-redis` | `redis:7-alpine` | `6379` | Celery broker and result backend. Named volume: `redis-data` |
| `rag-minio` | `minio/minio:latest` | `9000` (API), `9001` (console) | S3-compatible object storage. Named volume: `minio-data` |
| `rag-minio-init` | `minio/mc:latest` | — | One-shot: creates bucket `rag-documents`, runs once at first start |
| `rag-flower` | Local build | `5555` | Celery task monitoring UI (optional) |
| Ollama | Host native | `11434` | LLM inference — **not managed by Docker Compose** |

### Celery Queue Routing

| Queue | Worker | Tasks |
|---|---|---|
| `extraction` | `rag-celery-extraction` | `extract_document_task` |
| `enrichment` | `rag-celery-enrichment` | `enrich_job_task` |
| `document_processing` | `rag-celery-worker` | `process_document_task` |
| `embeddings` | `rag-celery-worker` | `generate_embeddings_task` |
| `default` | `rag-celery-worker` | Fallback for unrouted tasks |

### Beat Periodic Tasks

| Task | Schedule | Function |
|---|---|---|
| `cleanup-expired-tasks` | Every 3600s (1h) | Removes stale Celery results |
| `cleanup-stuck-extraction-jobs` | Every 1800s (30min) | Jobs stuck in `PROCESSING` > 30min → marked `FAILED` |
| `file-operator-poll-inbox` | Every 120s (default) | `poll_inbox()` — scans MinIO `inbox/` for new PDFs |
| `batch-closer` | Every 180s (default) | `close_completed_batches()` — settles completed batches, triggers aggregation |

---

## 3. Startup Procedure

### Prerequisites

1. Ollama must be running on the host with model loaded:
   ```
   ollama serve
   ollama pull qwen2.5:7b-instruct
   ```

2. Verify Ollama is reachable:
   ```
   python scripts/check_ollama.py
   ```

### Start all services

```powershell
cd "d:\IDP project\doc-automation-engine"
docker compose up -d
```

Docker Compose startup order enforced by `depends_on`:

1. `postgres` and `redis` start first (health-checked before dependents proceed)
2. `minio` starts; `minio-init` runs once and exits
3. `api` starts after postgres + redis healthy
4. `streamlit` starts after `api`
5. `celery-worker`, `celery-extraction-worker`, `celery-enrichment-worker` start after postgres + redis
6. `celery-beat` starts after all three workers

### Verify startup

```powershell
# API health
Invoke-RestMethod http://localhost:8000/api/v1/health

# Expected: {"status":"ready","checks":{"database":"connected"}}

# Check all containers running
docker compose ps

# Check API imports (no module errors)
docker exec rag-api python -c "import app.main; print('ALL IMPORTS OK')"
```

### Database initialization

On first start, `Base.metadata.create_all()` runs automatically inside the API lifespan handler. All tables are created if they do not exist. No manual migration step is required for a fresh database.

---

## 4. Processing Lifecycle

### Manual upload path (via UI or API)

```
User → POST /api/v1/jobs (multipart PDF)
     → JobManager.create_job_from_upload()
     → Document record created, PDF stored to MinIO
     → ExtractionJob created (status=PENDING)
     → extract_document_task dispatched → queue: extraction
     → rag-celery-extraction picks up task (concurrency=1)
     → Stage 1: pdfplumber + regex → extracted_data written
     → job.status = EXTRACTED
     → enrich_job_task dispatched → queue: enrichment
     → rag-celery-enrichment picks up task (concurrency=2)
     → Stage 2: Ollama LLM → enriched_data written
     → job.status = READY_FOR_REVIEW
     → Reviewer approves via UI → reviewed_data written
     → job.status = APPROVED
     → Manual or auto aggregation → AggregationReport created
     → job.status = AGGREGATED
```

### Automatic hot-folder path (FileOperator)

```
PDF dropped to MinIO: inbox/{tenant_id}/filename.pdf
→ poll_inbox() fires every 120s
→ Template auto-detected via filename_pattern regex
→ Document + Job records created
→ File moved to processed/{tenant_id}/filename.pdf
→ extract_document_task dispatched
→ [continues same as manual path above]
```

### Batch auto-close (BatchCloser)

```
close_completed_batches() fires every 180s
→ Finds batches where all jobs are in terminal state
→ Force-closes batches idle > 60min regardless of job state
→ If BATCH_CLOSER_AUTO_AGGREGATE=True AND at least 1 APPROVED job:
     → AggregationReport created automatically
     → All APPROVED jobs → status = AGGREGATED
```

### Stage 2 skip conditions

Stage 2 (LLM enrichment) is skipped without error when:
- `chi_tiet_cnch` section is empty in the extracted text
- Upstream Stage 1 for that job failed

When skipped: `enrichment_status=skipped`, `job.status=READY_FOR_REVIEW`, `enriched_data=NULL`. Job remains usable with Stage 1 data only.

---

## 5. Monitoring

### Health endpoints

| Check | Command |
|---|---|
| API liveness | `GET http://localhost:8000/api/v1/health` |
| API OpenAPI | `GET http://localhost:8000/docs` |
| Flower (Celery tasks) | `http://localhost:5555` |
| MinIO console | `http://localhost:9001` (user: `minioadmin`, pass: `minioadmin`) |

### Container logs

```powershell
# Tail API logs
docker logs rag-api -f

# Tail extraction worker logs
docker logs rag-celery-extraction -f

# Tail enrichment worker logs (LLM calls appear here)
docker logs rag-celery-enrichment -f

# Tail beat scheduler logs
docker logs rag-celery-beat -f
```

### Log files inside containers

- Log level: `INFO` (configurable via `LOG_LEVEL` env var)
- Log directory: `/app/logs/` inside each container
- Rotating file handler; not persisted to a host volume by default

### Queue depth (Redis)

```powershell
docker exec rag-redis redis-cli llen extraction
docker exec rag-redis redis-cli llen enrichment
docker exec rag-redis redis-cli llen default
```

### Stuck job check (PostgreSQL)

```powershell
docker exec rag-postgres psql -U raguser -d ragdb -c \
  "SELECT id, status, created_at FROM extraction_jobs WHERE status='processing' AND created_at < NOW() - INTERVAL '30 minutes';"
```

---

## 6. Failure Recovery

### API container down

```powershell
docker compose up -d --no-deps api
```

Database tables are verified/created on startup automatically.

### Celery worker down

```powershell
# Restart specific worker
docker compose up -d --no-deps celery-extraction-worker
docker compose up -d --no-deps celery-enrichment-worker
docker compose up -d --no-deps celery-worker
```

In-flight tasks are re-queued because `task_acks_late=True` and `task_reject_on_worker_lost=True`. Tasks will be re-delivered to another worker.

### Beat scheduler down

```powershell
docker compose up -d --no-deps celery-beat
```

Beat does not run tasks itself — it only enqueues them. Missing a beat cycle causes one polling interval to be skipped; tasks will fire on the next cycle.

### Stuck jobs (status = `processing` > 30min)

The `cleanup-stuck-extraction-jobs` beat task runs every 30 minutes and automatically marks these jobs `FAILED`.

To force-recover a single job immediately:

```powershell
docker exec rag-postgres psql -U raguser -d ragdb -c \
  "UPDATE extraction_jobs SET status='failed', error_message='manual operator reset' WHERE id='<job-id>';"
```

### Ollama not responding

- Check Ollama is running on host: verify process on port 11434
- Extraction tasks will fail with timeout after 90 seconds (`OLLAMA_TIMEOUT_SECONDS=90`)
- Tasks retry up to 3 times (`EXTRACTION_MAX_RETRIES=3`)
- After 3 retries: `job.status=FAILED`
- Jobs with `status=FAILED` can be re-queued via `POST /api/v1/jobs/{id}/reprocess`

### PostgreSQL down

All API requests fail. Celery tasks that require DB writes fail and retry.

```powershell
docker compose up -d --no-deps postgres
# Wait for healthy:
docker exec rag-postgres pg_isready -U raguser -d ragdb
# Then restart API and workers to re-establish connection pools:
docker compose restart api celery-worker celery-extraction-worker celery-enrichment-worker
```

### Redis down

All Celery task dispatch fails. Beat cannot enqueue periodic tasks.

```powershell
docker compose up -d --no-deps redis
docker compose restart celery-worker celery-extraction-worker celery-enrichment-worker celery-beat
```

Tasks en-route at time of Redis failure are lost (not persisted to disk in default Redis config).

### MinIO down

File uploads fail. Extraction tasks that require PDF download fail.

```powershell
docker compose up -d --no-deps minio
```

`minio-init` is a one-shot container — it does not re-run. The bucket already exists after first start.

### Apply a database migration

```powershell
# Example: enrichment columns migration
docker exec rag-api python scripts/migrate_add_enrichment_columns.py

# Example: workflow v4 migration
docker exec rag-api python scripts/migrate_workflow_v4.py
```

Migration scripts are idempotent (`ADD COLUMN IF NOT EXISTS`).

---

## 7. Data Storage

| Data | Location | Persistence |
|---|---|---|
| PostgreSQL data | Named Docker volume `postgres-data` → `/var/lib/postgresql/data` | Persistent across restarts |
| MinIO objects | Named Docker volume `minio-data` → `/data` | Persistent across restarts |
| Redis data | Named Docker volume `redis-data` → `/data` | Persistent (AOF off by default — data may be lost on crash) |
| Application logs | `/app/logs/` inside each container | **Not persisted** — lost when container is removed |
| MinIO bucket | `rag-documents` | Created by `minio-init` on first start |

### MinIO path layout

| Prefix | Contents |
|---|---|
| `inbox/{tenant_id}/` | Drop zone for FileOperator auto-pickup |
| `processed/{tenant_id}/` | Files moved here after FileOperator pickup |
| (other keys) | Documents uploaded via API — keyed by UUID S3 key stored in `documents.s3_key` |

### Database backup

Operational detail not defined. No automated backup is configured in `docker-compose.yml`.

---

## 8. Deployment Model

### Apply a code change

All application code (API, workers, UI) is baked into images at build time. A code change requires:

```powershell
cd "d:\IDP project\doc-automation-engine"

# Rebuild one service
docker compose build api
docker compose up -d --no-deps api

# Rebuild all application services (not postgres/redis/minio)
docker compose build api streamlit celery-worker celery-extraction-worker celery-enrichment-worker celery-enrichment-worker celery-beat flower
docker compose up -d --no-deps api streamlit celery-worker celery-extraction-worker celery-enrichment-worker celery-beat
```

### Full clean rebuild

```powershell
docker compose build --no-cache
docker compose up -d
```

### Environment variable changes

Environment variables are set directly in `docker-compose.yml`. Variables that accept override via shell env (prefixed with `${}`) are:

| Variable | Default in compose | Override |
|---|---|---|
| `JWT_SECRET_KEY` | `your-super-secret-key-change-in-production` | Shell env `JWT_SECRET_KEY` |
| `GEMINI_API_KEY` | (empty) | Shell env `GEMINI_API_KEY` |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Shell env `OLLAMA_MODEL` |
| `EXTRACTION_BACKEND` | `ollama` | Shell env `EXTRACTION_BACKEND` |

All other variables are hardcoded in `docker-compose.yml`. Changing them requires editing the file and restarting the affected container.

---

## 9. Known Operational Constraints

| Constraint | Detail |
|---|---|
| **Concurrent extractions** | `celery-extraction-worker` runs at concurrency=1. Only one Stage 1 extraction can run at a time. |
| **Concurrent LLM enrichments** | `celery-enrichment-worker` runs at concurrency=2. Max two simultaneous Ollama calls. |
| **Ollama is external** | Ollama is not in Docker Compose. If the host reboots, it must be restarted manually. |
| **Task result TTL** | Celery results expire from Redis after 3600s. Querying a finished task result after 1h returns nothing. |
| **Max file size** | 10 MB per upload (`MAX_FILE_SIZE_MB=10`). |
| **Max batch size** | 20 files per batch upload (`EXTRACTION_BATCH_MAX_FILES=20`). |
| **LLM call timeout** | 90 seconds (`OLLAMA_TIMEOUT_SECONDS=90`). Longer PDFs may exhaust this. |
| **Worker recycle** | Extraction and enrichment workers recycle after 10 tasks (`--max-tasks-per-child=10`) to prevent memory leak from Ollama context accumulation. |
| **--reload active** | `uvicorn --reload` is active on the API container. File system events inside the container can cause worker restarts. This flag is present because `DEBUG=true` is hardcoded in the compose file. |
| **No log persistence** | Application logs in `/app/logs/` inside containers are lost when a container is removed. |
| **Redis durability** | Default Redis config with no explicit AOF/RDB tuning. Tasks in-flight at time of Redis crash are lost. |
| **No TLS** | All inter-service and host→container communication is plain HTTP. `MINIO_SECURE=false`. |
| **Single-host only** | All services run on one Docker host. There is no cross-host networking defined. |
