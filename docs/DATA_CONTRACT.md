# DATA CONTRACT

## 1. Data Authority

| Layer | Authority | Scope |
|---|---|---|
| **Template schema** | Admin human input | Defines which fields to extract and aggregation rules |
| **Regex / patterns** | `app/domain/templates/pccc.yaml` | All regex anchors, date formats, threshold — single source, no hardcode |
| **Stage 1 extraction** | Deterministic pipeline (pdfplumber + regex + business rules) | `extracted_data` — authoritative structural fields |
| **Stage 2 enrichment** | Ollama LLM (`qwen2.5:7b-instruct`) | `enriched_data` — allowlisted LLM-only fields (`danh_sach_cnch`) |
| **Human review** | Reviewer via API/UI | `reviewed_data` — always overrides AI output |
| **Final data** | `job.final_data` property | Priority chain: `reviewed_data` > `(extracted_data + enriched_data[allowlist])` > `extracted_data` |
| **Aggregated report** | `AggregationService` (Pandas) | `aggregated_data` — derived, not authoritative |

---

## 2. Core Entities

### 2.1 Document

**Purpose:** Metadata record for an uploaded file. The binary is stored in MinIO (S3).

**Owner:** `app/domain/models/document.py`, table `documents`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `file_name` | VARCHAR(255) | Original filename |
| `file_size_bytes` | BIGINT | |
| `mime_type` | VARCHAR(100) | |
| `s3_key` | VARCHAR(500) | MinIO object path |
| `checksum` | VARCHAR(64) | SHA hash; indexed for dedup |
| `status` | VARCHAR(50) | `pending` \| `processing` \| `completed` \| `failed` |
| `tags` | ARRAY(String) | |
| `uploaded_by` | UUID FK → users | |
| `created_at` | TIMESTAMP | |

---

### 2.2 ExtractionTemplate

**Purpose:** Defines the JSON schema and aggregation rules used to extract and reduce documents.

**Owner:** `app/domain/models/extraction_job.py`, table `extraction_templates`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `name` | VARCHAR(255) | |
| `description` | TEXT | |
| `schema_definition` | JSONB | See §3 — required |
| `aggregation_rules` | JSONB | See §3 — default `{}` |
| `word_template_s3_key` | VARCHAR(500) | S3 key of `.docx` for Word export; nullable |
| `filename_pattern` | VARCHAR(500) | Regex for auto-match on upload; nullable |
| `extraction_mode` | VARCHAR(20) | `block` only (active); `standard`, `vision` legacy |
| `version` | INTEGER | Auto-incremented on schema change |
| `is_active` | BOOLEAN | Soft-delete flag |
| `created_by` | UUID FK → users | |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

---

### 2.3 ExtractionJob

**Purpose:** Single extraction unit: 1 PDF × 1 template. Stores all AI outputs, review data, and audit metadata.

**Owner:** `app/domain/models/extraction_job.py`, table `extraction_jobs`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `template_id` | UUID FK → extraction_templates | |
| `document_id` | UUID FK → documents | |
| `batch_id` | UUID | Nullable — groups N jobs from one upload |
| `extraction_mode` | VARCHAR(20) | `block` \| `standard` \| `vision` |
| `status` | VARCHAR(30) | See §6 state machine |
| `extracted_data` | JSONB | Stage 1 deterministic output |
| `confidence_scores` | JSONB | `{_validation_report: {...}, _validation_attempts: int}` |
| `source_references` | JSONB | Page citations; nullable |
| `debug_traces` | JSONB | Array; default `[]` |
| `enrichment_status` | VARCHAR(20) | Audit-only (deprecated write); `pending\|running\|enriched\|failed\|skipped` |
| `enriched_data` | JSONB | Stage 2 LLM output; allowlist: `danh_sach_cnch` only |
| `enrichment_error` | TEXT | |
| `enrichment_started_at` | TIMESTAMP | |
| `enrichment_completed_at` | TIMESTAMP | |
| `reviewed_data` | JSONB | Human-edited copy of `extracted_data` |
| `reviewed_by` | UUID FK → users | |
| `reviewed_at` | TIMESTAMP | |
| `review_notes` | TEXT | |
| `parser_used` | VARCHAR(50) | `pdfplumber` \| `none` |
| `llm_model` | VARCHAR(100) | |
| `llm_tokens_used` | INTEGER | |
| `processing_time_ms` | INTEGER | |
| `error_message` | TEXT | |
| `retry_count` | INTEGER | |
| `created_by` | UUID FK → users | |
| `created_at` | TIMESTAMP | |
| `completed_at` | TIMESTAMP | |

---

### 2.4 AggregationReport

**Purpose:** Result of reducing N approved jobs into one report via Pandas map-reduce.

**Owner:** `app/domain/models/extraction_job.py`, table `aggregation_reports`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `template_id` | UUID FK → extraction_templates | |
| `name` | VARCHAR(255) | |
| `description` | TEXT | |
| `job_ids` | ARRAY(UUID) | Ordered list of contributing job IDs |
| `aggregated_data` | JSONB | See §4 — full reduced dataset |
| `total_jobs` | INTEGER | |
| `approved_jobs` | INTEGER | |
| `status` | VARCHAR(20) | `draft` \| `finalized` |
| `created_by` | UUID FK → users | |
| `created_at` | TIMESTAMP | |
| `finalized_at` | TIMESTAMP | |

---

### 2.5 ExtractionJobEvent

**Purpose:** Append-only audit log for every job state transition.

**Owner:** `app/domain/workflow.py`, table `extraction_job_events`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `job_id` | UUID FK → extraction_jobs | |
| `from_state` | VARCHAR(30) | Nullable on first transition |
| `to_state` | VARCHAR(30) | |
| `actor_type` | VARCHAR(20) | `worker` \| `api` \| `system` |
| `actor_id` | VARCHAR(255) | user_id or worker hostname |
| `reason` | TEXT | |
| `created_at` | TIMESTAMP | |

---

## 3. Input Data Contract

### 3.1 Accepted File Types

| Type | MIME | Max size |
|---|---|---|
| PDF | `application/pdf` | 10 MB (configurable via `MAX_FILE_SIZE_MB`) |
| Word (.docx) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | 10 MB (uploads); 50 MB (Word template scanner) |
| Plain text | `text/plain` | 10 MB |

### 3.2 Template `schema_definition` Contract

```json
{
  "fields": [
    {
      "name": "snake_case_identifier",
      "type": "string | number | boolean | array | object",
      "description": "...",
      "required": true,
      "items": { ... },
      "fields": [ ... ]
    }
  ]
}
```

- `name`: snake_case, regex `^[A-Za-z_][A-Za-z0-9_]*$`, max 64 chars, unique within template
- `type`: one of `string`, `number`, `boolean`, `array`, `object`
- `items`: required when `type == "array"` describing element structure
- `fields`: required when `type == "object"` describing sub-fields
- Minimum 1 field required

### 3.3 Template `aggregation_rules` Contract

```json
{
  "rules": [
    {
      "output_field": "string",
      "source_field": "string",
      "method": "SUM | AVG | MAX | MIN | COUNT | CONCAT | LAST",
      "label": "string",
      "round_digits": null
    }
  ],
  "sort_by": null,
  "group_by": null
}
```

- `method`: must be one of `SUM`, `AVG`, `MAX`, `MIN`, `COUNT`, `CONCAT`, `LAST`
- `round_digits`: optional integer for `AVG` rounding
- `sort_by`, `group_by`: optional string field names

---

## 4. LLM Output Contract

### 4.1 Stage 2 — `CNCHListOutput` (the only LLM call in block pipeline)

**Model:** `app/engines/extraction/schemas.py::CNCHListOutput`

**Input to LLM:** raw `chi_tiet_cnch` text string (section III of the report narrative)

**Required response structure:**
```json
{
  "items": [
    {
      "stt": 1,
      "ngay_xay_ra": "dd/mm/yyyy",
      "thoi_gian": "HH:MM dd/mm/yyyy | HH giờ MM phút ngày dd/mm/yyyy | HH:MM | dd/mm/yyyy",
      "dia_diem": "string",
      "noi_dung_tin_bao": "string",
      "luc_luong_tham_gia": "string",
      "ket_qua_xu_ly": "string",
      "thong_tin_nan_nhan": "string"
    }
  ]
}
```

**Field rules for each `CNCHItem`:**

| Field | Type | Required | Validation |
|---|---|---|---|
| `stt` | int | No (default 0) | strict int |
| `ngay_xay_ra` | string | No (default "") | |
| `thoi_gian` | string | No (default "") | Must match one of: `dd/mm/yyyy`, `dd/mm/yyyy HH:MM`, `HH:MM dd/mm/yyyy`, `HH:MM ngày dd/mm/yyyy`, `HH:MM`, `HH giờ MM phút ngày dd/mm/yyyy`; LLM short form `HHhMM` is auto-normalized to `HH:MM` |
| `dia_diem` | string | No (default "") | |
| `noi_dung_tin_bao` | string | No (default "") | |
| `luc_luong_tham_gia` | string | No (default "") | |
| `ket_qua_xu_ly` | string | No (default "") | |
| `thong_tin_nan_nhan` | string | No (default "") | |
| `mo_ta` | string | No (default "") | Internal backward-compat only |

**Forbidden fields:** None — `extra="ignore"` on `CNCHItem`. Unknown keys are silently dropped.

**Persistence:** Written to `extraction_jobs.enriched_data` as `{"danh_sach_cnch": [...]}`.

**Allowlist merge into `extracted_data`:** Only the key `danh_sach_cnch` is allowed to propagate from `enriched_data` into `final_data`. All other keys in `enriched_data` are dropped at merge time.

### 4.2 Stage 1 — No LLM

Block pipeline Stage 1 (`run_stage1_from_bytes`) does not call any LLM. All extraction is deterministic via pdfplumber + regex patterns from `pccc.yaml`.

### 4.3 `BlockExtractionOutput` — Stage 1 output model

```json
{
  "header": {
    "so_bao_cao": "string",
    "ngay_bao_cao": "dd/mm/yyyy",
    "thoi_gian_tu_den": "string",
    "don_vi_bao_cao": "string"
  },
  "phan_I_va_II_chi_tiet_nghiep_vu": {
    "tong_so_vu_chay": 0,
    "tong_so_vu_no": 0,
    "tong_so_vu_cnch": 0,
    "chi_tiet_cnch": "raw text — passed to Stage 2, not persisted in extracted_data",
    "quan_so_truc": 0,
    "tong_chi_vien": 0,
    "tong_cong_van": 0,
    "tong_xe_hu_hong": 0
  },
  "bang_thong_ke": [
    { "stt": "2", "noi_dung": "Tổng số vụ cháy", "ket_qua": 0 }
  ],
  "danh_sach_cnch": [],
  "danh_sach_phuong_tien_hu_hong": [
    { "bien_so": "string", "tinh_trang": "string" }
  ],
  "danh_sach_cong_van_tham_muu": [
    { "so_ky_hieu": "string", "noi_dung": "string" }
  ]
}
```

**Model config:** `extra="forbid"` on `BlockHeader`, `BlockNghiepVu`, `BlockBangThongKe`, `ChiTieu`. Unknown keys from extraction raise `ValidationError`.

---

## 5. Validation Rules

### 5.1 Pre-persistence business validation (`validate_business`)

Executed by `app/domain/rules/validation_rules.py` after Stage 1 extraction.

**Required fields:**
- `so_bao_cao` — report number; format validated against `tpl.report_number_format_re`
- `ngay_bao_cao` OR `ngay` — date in `dd/mm/yyyy`, year within `tpl.year_range` (default 2020–2030)
- `don_vi` — reporting unit

**Format rules:**
- All dates: `dd/mm/yyyy`, day 1–31, month 1–12, day ≤ month max
- `thoi_gian_tu_den`: must contain at least one `dd/mm/yyyy` substring
- `so_bao_cao`: must match `tpl.report_number_format_re`

**Range rules:**
- All fields in `tpl.non_negative_fields`: value must be ≥ 0
- Any `ket_qua` in `bang_thong_ke_raw`: `abs(ket_qua) ≤ tpl.max_ket_qua` (default 10 000)

**Cross-field rules:**
- `stat_total > narrative_total * tpl.cross_field_tolerance` → error `cross_field_incident_total_mismatch`

**Error format:** list of string error codes, e.g. `["missing_so_bao_cao", "invalid_date_format"]`

### 5.2 `CNCHItem.thoi_gian` validation (post LLM)

Applied by `model_validator(mode="after")` at schema parse time:

- Short form `HHhMM` → auto-normalized to `HH:MM`
- Must match one of 6 regex patterns: `dd/mm/yyyy`, `dd/mm/yyyy HH:MM`, `HH:MM dd/mm/yyyy`, `HH:MM ngày dd/mm/yyyy`, `HH:MM`, `HH giờ MM phút ngày dd/mm/yyyy`
- Validation failure → `ValueError` (item is dropped from the list)

### 5.3 API-layer schema validation (`extraction_schema.py`)

- `FieldDefinition.name`: regex `^[A-Za-z_][A-Za-z0-9_]*$`; auto-fix attempted before reject
- `FieldDefinition.type`: must be in `{string, number, boolean, array, object}`
- `SchemaDefinition.fields`: min 1; top-level names must be unique and non-empty
- `AggregationRule.method`: must be in `{SUM, AVG, MAX, MIN, COUNT, CONCAT, LAST}`
- `TemplateCreate.extraction_mode`: must be `"block"`
- `filename_pattern`: must compile as valid Python regex

---

## 6. Persistence Contract

### 6.1 What is persisted permanently

| Data | Table.column | Permanent |
|---|---|---|
| Uploaded file binary | MinIO S3 via `documents.s3_key` | Yes |
| Document metadata | `documents.*` | Yes |
| Template definition | `extraction_templates.*` | Yes (soft-delete only) |
| Stage 1 output | `extraction_jobs.extracted_data` | Yes — never overwritten after write |
| Stage 2 LLM output | `extraction_jobs.enriched_data` | Yes — separate from `extracted_data` |
| Human review | `extraction_jobs.reviewed_data` | Yes — overrides all AI output |
| Aggregated report | `aggregation_reports.aggregated_data` | Yes |
| State audit trail | `extraction_job_events.*` | Yes — append-only |
| Word template binary | MinIO S3 via `extraction_templates.word_template_s3_key` | Yes |

### 6.2 What is temporary / derived

| Data | Notes |
|---|---|
| `PipelineResult` dataclass | In-memory only; never written to DB as-is |
| `chi_tiet_cnch` on `PipelineResult` | Passed from Stage 1 worker to enrichment task via Celery args; not directly persisted |
| `flatten_block_output()` expansion | Computed at aggregation time; flat keys stored in `aggregated_data` but not in `extracted_data` |
| `job.final_data` | Computed property; not a DB column |
| Celery task result backend | Redis, TTL 3600s |

### 6.3 Write isolation rules

- `extracted_data`: written exactly once by `persist_stage1_result()`. Never modified thereafter.
- `enriched_data`: written exactly once by `persist_enrichment_result()`. Never overwrites `extracted_data`.
- `reviewed_data`: written by reviewer approval. If `reviewed_data` is set, `final_data` ignores AI output entirely.
- Merge at read time only — `job.final_data` property merges in memory; merged result is not stored back.

---

## 7. Failure Handling

### 7.1 Stage 1 failure

- `job.status` → `FAILED` via `transition_job_state()`
- `job.error_message` set to exception text
- Celery retries up to `EXTRACTION_MAX_RETRIES` (default 3) with exponential backoff (30s → 60s → 120s + jitter)
- After max retries: `status = FAILED` permanently; `extracted_data = None`
- Stuck jobs (status `processing` > `EXTRACTION_TIMEOUT_MINUTES` minutes): `cleanup_stuck_extraction_jobs` beat task marks them `FAILED`

### 7.2 Stage 2 (enrichment) failure

- `job.enrichment_status` → `failed` (audit column)
- `job.status` → `READY_FOR_REVIEW` (job remains usable with Stage 1 data)
- `job.enriched_data` remains `NULL`
- Celery retries up to 3 times with 60s default delay
- Transient errors retry; `ValidationError` / empty `chi_tiet_cnch` → no retry (`SKIPPED`)
- `job.final_data` falls back to `extracted_data` only (Stage 1 regex CNCH list used instead)

### 7.3 Aggregation failure

- `ProcessingError` raised if any job has `enrichment_status IN (pending, running)` — caller must wait for settlement
- Individual job `final_data = None` → job is skipped with warning in aggregation log
- Aggregation does not partially commit — all-or-nothing per call

### 7.4 Validation failure (API layer)

- `422 Unprocessable Entity` with Pydantic error detail
- Nothing is persisted

### 7.5 Word export failure

- `422 Unprocessable Entity` for Jinja2 render errors (`ValueError` from `render_aggregation_to_word`)
- `400 Bad Request` if `word_template_s3_key` is NULL on template
- `500 Internal Server Error` if S3 download fails
- Anti zip-bomb: files exceeding uncompressed limits or compression ratio > 150× are rejected before parse

---

## 8. Versioning Rules

### 8.1 Template versioning

- `extraction_templates.version` starts at 1
- `ExtractionService.update_template()` increments `version` when `schema_definition` changes
- Old `version` is not archived — only the latest schema is stored
- Jobs retain a FK to the template; the schema at extraction time is not snapshotted per job

### 8.2 Job status versioning

- Canonical state enum: `app/domain/workflow.py::JobStatus`
- `transition_job_state()` is the single write path — enforces `VALID_TRANSITIONS` map
- Legacy DB values `"extracted"` map to `READY_FOR_REVIEW` via `_LEGACY_STATUS_MAP`
- `ExtractionJobStatus` class in `extraction_job.py` is a backward-compat alias — new code must use `JobStatus` directly

### 8.3 DB schema migrations

- Migration scripts in `scripts/` (e.g. `migrate_add_enrichment_columns.py`)
- Scripts are idempotent (`ADD COLUMN IF NOT EXISTS`)
- No Alembic; migrations are run manually
- `Base.metadata.create_all()` runs at API startup for new tables only

### 8.4 `BlockExtractionOutput` model versioning

- `extra="forbid"` on `BlockHeader`, `BlockNghiepVu`, `ChiTieu` — adding fields to the pipeline output model requires coordinated update of both schema and DB JSONB structure
- `CNCHItem` and `PhuongTienHuHongItem` use `extra="ignore"` — LLM can return extra keys safely
- `model_config` is defined per class; no global inheritance versioning
