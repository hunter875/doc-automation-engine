# Google Sheets Operational Data Ingestion Pipeline

**Version:** 5.1 (April 2026) — Snapshot Architecture

## Overview

The Google Sheets pipeline now supports **two ingestion modes**:

### Snapshot Mode (Default, Recommended)

Treats the entire Google Sheet (all worksheets) as a **single DailyReport aggregate**. All worksheets are processed together in one ingestion run, producing a single `ExtractionJob` that contains the complete canonical `BlockExtractionOutput` with all sections populated.

**Key Characteristics:**

- **Report-oriented ingestion**: One ingestion run → one `extraction_jobs` record representing the full daily report
- **Deterministic sheet hash**: SHA-256 of all worksheet data enables idempotency across the entire sheet
- **Report date extraction**: `report_date` is extracted from `header.ngay_bao_cao` (determined during build)
- **Single job per report date**: Multiple versions allowed (via `report_version`) but identical sheet content is deduplicated
- **Validation summary**: Row-level validation errors are collected into `validation_report` metadata without blocking job creation
- **No aggregation needed**: Snapshot job already contains the full report; aggregation layer becomes optional

### Row-Level Mode (Legacy)

Original row-oriented ingestion where each spreadsheet row becomes a discrete `extraction_jobs` record. Later daily aggregation combines rows by date. This mode remains supported for backward compatibility via `SHEET_INGESTION_MODE=row`.

**See legacy documentation** in previous versions for row-level details.

---

## Mode Selection

Set environment variable:

```bash
SHEET_INGESTION_MODE=snapshot  # default (new)
# or
SHEET_INGESTION_MODE=row       # legacy
```

The `GoogleSheetIngestionService.ingest()` routes based on this flag and the presence of `template.google_sheet_configs` (snapshot requires multi-worksheet configs with `target_section`).

---

## Integration with Engine 2

Both modes share:

- Same database (`extraction_jobs` table)
- Same canonical output (`BlockExtractionOutput`)
- Different `parser_used` marker: `"google_sheets"`
- Sheet extraction pipeline (`SheetExtractionPipeline`) for deterministic transformation
- Dual-read capability: consumers can read snapshot jobs directly or fall back to aggregating legacy row-level jobs

This pipeline is implemented in code under:

- `app/engines/extraction/sheet_ingestion_service.py`
- `app/engines/extraction/daily_report_builder.py`
- `app/engines/extraction/sheet_revision_hasher.py`
- `app/engines/extraction/sheet_pipeline.py`

---

# 2. Snapshot Architecture

## Core Concept

In snapshot mode, **the Google Sheet is the working document**. All worksheets together constitute one logical DailyReport. The ingestion run processes all worksheets in one transaction (in-memory), builds the full `BlockExtractionOutput`, and persists it as a single `ExtractionJob`.

This aligns the event granularity with the business aggregate: a daily report is created or updated as a unit.

## Worksheet Configuration

Templates must define `google_sheet_configs` as a list of worksheet configurations:

```json
[
  {
    "worksheet": "BC NGÀY",
    "schema_path": "bc_ngay_schema.yaml",
    "target_section": "header"
  },
  {
    "worksheet": "CNCH",
    "schema_path": "cnch_schema.yaml",
    "target_section": "danh_sach_cnch"
  },
  ...
]
```

Each config specifies:
- `worksheet`: Name of the worksheet in the Google Sheet
- `schema_path`: Path to custom YAML schema (same as row-level mode)
- `target_section`: Which top-level section in `BlockExtractionOutput` this worksheet's data populates

## Ingestion Flow (Snapshot Mode)

```
HTTP POST /jobs/ingest/google-sheet/sync (or async)
    ↓
GoogleSheetIngestionService.ingest() with SHEET_INGESTION_MODE=snapshot
    ↓
1. Load template → google_sheet_configs (list)
2. Parallel fetch all worksheets via GoogleSheetsSource
   → sheet_data: {worksheet_name: rows}
3. Build DailyReport:
   a. DailyReportBuilder(template, sheet_data, worksheet_configs)
   b. For each worksheet:
      - Detect header row
      - Map & validate each data row
      - Run SheetExtractionPipeline on each row → partial BlockExtractionOutput
      - Merge partial output into full report by target_section
   c. Extract report_date from header.ngay_bao_cao (must exist)
   d. Build validation_summary (aggregate row-level results)
4. Compute sheet_revision_hash = SHA-256(canonical sheet_data)
5. Duplicate check: find existing job with same (tenant, template, report_date, sheet_revision_hash)
   - If found → return existing job (idempotent)
6. Determine next report_version for this (tenant, template, report_date)
7. Create source document (JSON snapshot of all worksheets)
8. Create ExtractionJob:
   - extraction_mode = "block"
   - status = "extracted"
   - parser_used = "google_sheets"
   - extracted_data = full BlockExtractionOutput (from DailyReportBuilder)
   - sheet_revision_hash = computed hash
   - report_date = extracted date
   - report_version = next version
   - validation_report = row-level summary
   - supersedes_job_id = previous version (if any)
   - completed_at = now
9. Return summary with job_id, report_date, report_version, worksheets_processed, validation_summary
```

## Idempotency & Versioning

### Duplicate Detection

A sheet ingestion is considered a duplicate if an existing job has the same:

- `tenant_id`
- `template_id`
- `report_date`
- `sheet_revision_hash` (full content hash)

This ensures that re-ingesting the **exact same sheet** (all worksheets unchanged) for the same report date does not create a new version.

### Version Chain

If a snapshot job already exists for the report date but the sheet content has changed, a **new version** is created:

- `report_version` increments from the latest version
- `supersedes_job_id` links to the previous version
- All versions are retained for audit trail

Query latest version:

```sql
SELECT * FROM extraction_jobs
WHERE tenant_id = ? AND template_id = ? AND report_date = ? AND sheet_revision_hash IS NOT NULL
ORDER BY report_version DESC LIMIT 1;
```

## Dual-Read Pattern

To support gradual migration, the system implements **dual-read**:

`DailyReportService.get_report(tenant_id, template_id, report_date)`:

1. Try to find the latest **snapshot job** (`sheet_revision_hash IS NOT NULL`) for that date
   - If found → return `extracted_data` directly (already full report)
2. Fallback: query **legacy row-level jobs** (`sheet_revision_hash IS NULL`) created on that date
   - If found → aggregate them using `AggregationService.aggregate_data_only()`
3. Return `None` if no data

This allows:
- New templates to use snapshot mode immediately
- Old templates to continue with row-level ingestion
- UI and downstream services to call a single read endpoint without caring about the underlying mode

## Response Summary

Snapshot ingestion returns:

```json
{
  "status": "ok",
  "sheet_id": "1Abc...",
  "job_id": "uuid",
  "report_date": "2026-04-26",
  "report_version": 2,
  "worksheets_processed": ["BC NGÀY", "CNCH", "CHI VIỆN"],
  "rows_processed": 150,
  "rows_valid": 148,
  "rows_failed": 2,
  "validation_summary": {
    "total_rows": 150,
    "valid_rows": 148,
    "invalid_rows": [
      {"worksheet": "CNCH", "row_index": 5, "errors": [...], "confidence": {...}}
    ],
    "warnings": ["worksheet_missing:VỤ CHÁY"]
  },
  "metrics": { ... },
  "ingestion_mode": "snapshot"
}
```

Row-level ingestion (legacy) returns the traditional `GoogleSheetIngestionSummary` with `worksheet`, `rows_inserted`, `rows_skipped_idempotent`, etc.

## Database Schema Changes

Migration `004_add_snapshot_ingestion_columns.sql` adds:

```sql
ALTER TABLE extraction_jobs
  ADD COLUMN sheet_revision_hash VARCHAR(64),
  ADD COLUMN report_date DATE,
  ADD COLUMN report_version INTEGER,
  ADD COLUMN validation_report JSONB,
  ADD COLUMN supersedes_job_id UUID REFERENCES extraction_jobs(id);

CREATE INDEX idx_extraction_jobs_snapshot_lookup
  ON extraction_jobs (tenant_id, template_id, report_date, parser_used)
  WHERE parser_used = 'google_sheets' AND report_date IS NOT NULL;

CREATE INDEX idx_extraction_jobs_sheet_revision
  ON extraction_jobs (sheet_revision_hash)
  WHERE sheet_revision_hash IS NOT NULL;
```

Snapshot jobs have these columns populated; legacy row-level jobs have them `NULL`.

## Key Components

### 5.1 `GoogleSheetIngestionService`

- **File:** `app/engines/extraction/sheet_ingestion_service.py`
- **Main method:** `async ingest(self, req: IngestionRequest) -> dict[str, Any]`
- **Responsibility:** Orchestrate ingestion based on mode: row-level (schema loading, fetch, header detection, row mapping, validation, idempotent write) OR snapshot (build full report from all worksheets).
- **MUST NOT:** Call LLM, perform template rendering, trigger extraction pipeline.

### 5.2 `GoogleSheetsSource`

- **File:** `app/engines/extraction/sources/sheets_source.py`
- **Input:** `SheetsFetchConfig(sheet_id, worksheet, range_a1, max_retries, retry_backoff_seconds)`
- **Output:** `list[list[str]]` raw 2D array from Google Sheets API
- **Responsibility:** Build Google Sheets client, fetch rows with exponential retry.
- **MUST NOT:** Map business fields, validate schema.

### 5.3 `header_detector`

- **File:** `app/engines/extraction/mapping/header_detector.py`
- **Function:** `detect_header_row(rows, known_aliases, scan_limit=15)`
- **Output:** `(header_index, header_columns)`
- **Responsibility:** Find header row by scoring alias overlap with known field names.
- **WARNING:** `scan_limit=15` may miss headers beyond line 15.

### 5.4 `mapper`

- **File:** `app/engines/extraction/mapping/mapper.py`
- **Function:** `map_row_to_document_data(row, schema)`
- **Output:** `(normalized_data, matched_fields, total_fields, missing_required)`
- **Responsibility:** Match column headers to schema field aliases, normalize values (Unicode, type coercion).
- **MUST NOT:** Persist to DB, decide duplicate status.

### 5.5 `row_validator`

- **File:** `app/engines/extraction/validation/row_validator.py`
- **Functions:** `build_validation_model(schema)`, `validate_row(...)`
- **Output:** `RowValidationResult(is_valid, normalized_data, errors, confidence)`
- **Responsibility:** Pydantic model validation (required, types). Confidence = 60% schema_match + 40% validation_ok.
- **MUST NOT:** Fetch from Google Sheets, write jobs.

### 5.6 `JobWriter`

- **File:** `app/engines/extraction/sheet_job_writer.py`
- **Input:** `row_document`, `confidence`, `source_references` (includes `row_hash`, `schema_path`, `sheet_id`, `worksheet`)
- **Output:** `(created: bool, job_id: str | None)`
- **Responsibility:** Idempotency check via in-memory hash set, create job, apply workflow transitions (`PROCESSING` → `EXTRACTED` → `READY_FOR_REVIEW`).
- **MUST NOT:** Do schema mapping, compute canonical block contract.
- **CRITICAL:** Duplicate check uses in-memory set loaded at initialization. Race condition possible under concurrent ingestion (see Bug #4). Consider DB-level unique constraint on `(source_references->>'row_hash')`.

### 5.7 `SheetExtractionPipeline` (Custom Schema Mode)

- **File:** `app/engines/extraction/sheet_pipeline.py`
- **Method:** `run(self, sheet_data: dict[str, Any] | None, schema_path: str | None = None) -> PipelineResult`
- **New behavior (when `schema_path` provided):**
  1. `_load_custom_mapping(schema_path)` — load YAML with `sheet_mapping.<section>.fields` definitions
  2. `_build_output_custom(core_data, mapping)` — construct `BlockExtractionOutput` directly from flat row
     - Build `header` from mapped fields (may be all nulls)
     - Build `phan_I_va_II_chi_tiet_nghiep_vu` from mapped fields (may be all zeros/empty)
     - Build `bang_thong_ke` from `stt_map` if present
     - For each list section: create single-item list with fields extracted from row via section's field map
  3. Special case: **BC NGÀY date computation** when `header` mapping contains `ngay_bao_cao_day` and `ngay_bao_cao_month`
  4. Validate output via `_assert_contract_or_raise()` and `BlockExtractionOutput.model_validate()`
- **Legacy mode (no `schema_path`):** Falls back to global `sheet_mapping.yaml` and original `map_to_schema()`.
- **MUST NOT:** Call Google Sheets API, write to DB.

### 5.8 `DailyReportBuilder` (Snapshot Mode)

- **File:** `app/engines/extraction/daily_report_builder.py`
- **Purpose:** Assemble full `BlockExtractionOutput` from multiple worksheet snapshots.
- **Input:** `template`, `sheet_data` (dict of worksheet → 2D array), `worksheet_configs`
- **Process:**
  - Iterates each worksheet config
  - Detects header row using `detect_header_row`
  - Maps & validates each data row
  - Runs `SheetExtractionPipeline` per row to produce partial output
  - Merges partial outputs into the full report by `target_section`
- **Output:** `BlockExtractionOutput` with all sections merged
- **Critical:** Extracts `report_date` from `header.ngay_bao_cao` (must exist)

### 5.9 `SheetRevisionHasher` (Snapshot Mode)

- **File:** `app/engines/extraction/sheet_revision_hasher.py`
- **Method:** `compute_hash(sheet_data: dict) -> str`
- **Purpose:** Compute deterministic SHA-256 hash of the entire sheet for idempotency
- **Normalization:** Strips whitespace, converts empty cells to `None`, sorts worksheet keys
- **Output:** 64-character hex string

### 5.10 `DailyReportService` (Read Layer)

- **File:** `app/application/daily_report_service.py`
- **Methods:**
  - `get_report(tenant_id, template_id, report_date)` — dual-read logic
  - `get_report_history(tenant_id, template_id, start_date, end_date)` — list snapshot jobs
- **Purpose:** Unified read API for daily reports regardless of ingestion mode

---

# 3. Business Use Case: Operational Sheets

## Why Row-Oriented Ingestion?

The Google Sheets used in this system are **operational logs**, not finished reports:

- **BC NGÀY** (Báo cáo ngày): Daily incident summary table → each row = one day's statistics
- **VỤ CHÁY THỐNG KÊ**: Fire incident log → each row = one fire event
- **CNCH**: Traffic/rescue incident log → each row = one incident
- **CHI VIỆN**: Vehicle dispatch log → each row = one vehicle trip

These sheets are **append-only tables** where users add rows daily. The system:

1. **Ingests** all rows (with idempotency)
2. **Transforms** each row into a canonical `BlockExtractionOutput` with only the relevant section populated
3. **Aggregates** later by date (e.g., group all CNCH rows from 2026-04-20 into a single daily report)

## Example: CNCH Row → Canonical Output

**Google Sheet row (flat):**

| STT | Ngày xảy ra sự cố | Thời gian | Địa điểm | Loại hình CNCH | Thiệt hại về người |
|-----|-------------------|-----------|----------|----------------|-------------------|
| 1   | 20/04/2026        | 09:30     | Phường 1 | Cứu nạn giao thông | 0 |

**Canonical `BlockExtractionOutput` (after `SheetExtractionPipeline`):**

```json
{
  "header": { "so_bao_cao": null, "ngay_bao_cao": null, "thoi_gian_tu_den": null, "don_vi_bao_cao": null },
  "phan_I_va_II_chi_tiet_nghiep_vu": { "tong_so_vu_chay": 0, "tong_so_vu_no": 0, "tong_so_vu_cnch": 0, "chi_tiet_cnch": "", "quan_so_truc": 0, "tong_chi_vien": 0, "tong_cong_van": 0, "tong_bao_cao": 0, "tong_ke_hoach": 0, "cong_tac_an_ninh": "", "tong_xe_hu_hong": 0, "tong_tin_bai": 0, "tong_hinh_anh": 0, "so_lan_cai_app_114": 0 },
  "bang_thong_ke": [],
  "danh_sach_cnch": [
    { "stt": 1, "ngay_xay_ra": "20/04/2026", "thoi_gian": "09:30", "dia_diem": "Phường 1", "noi_dung_tin_bao": "Cứu nạn giao thông", "luc_luong_tham_gia": "", "ket_qua_xu_ly": "", "thiet_hai": "0", "thong_tin_nan_nhan": "", "mo_ta": "" }
  ],
  "danh_sach_phuong_tien_hu_hong": [],
  "danh_sach_cong_van_tham_muu": [],
  "danh_sach_cong_tac_khac": [],
  "danh_sach_chi_vien": [],
  "danh_sach_chay": [],
  "tuyen_truyen_online": { "so_tin_bai": 0, "so_hinh_anh": 0, "so_lan_cai_app_114": 0 }
}
```

Note: Empty sections are still present with empty/null values to maintain contract consistency.

---

# 3. Entry Point & Request

## API Endpoint

- **Route:** `POST /jobs/ingest/google-sheet`
- **File:** `app/api/v1/ingestion.py`
- **Handler:** `ingest_google_sheet(...)`
- **Authentication:** Requires Bearer token + `x-tenant-id` header

## Request Body

```json
{
  "sheet_id": "1AbcDefGhIJKlmnOPqrSTuvwxyz1234567890",
  "template_id": "bc_ngay_template",
  "worksheet_name": "BC NGÀY",
  "range_a1": "A1:Z1000"  // optional, defaults to all data rows
}
```

## `IngestionRequest` Dataclass

- **File:** `app/engines/extraction/sheet_ingestion_service.py`
- **Fields:**
  - `tenant_id` (from context)
  - `user_id` (from context)
  - `template_id`
  - `sheet_id`
  - `worksheet`
  - `schema_path` (computed from `template_id` via `TemplateService`)
  - `source_document_id` (optional)
  - `range_a1` (optional)

**Important:** The `schema_path` is resolved from the `template_id` using the `TemplateService`. It points to a custom YAML schema file in `app/domain/templates/` that defines the mapping for that specific worksheet.

---

# 4. Data Flow

## End-to-End Flow (Snapshot Mode)

```
HTTP POST /jobs/ingest/google-sheet/sync (or async)
    ↓
GoogleSheetIngestionService.ingest(req) with mode="snapshot"
    ↓
1. Load template.google_sheet_configs (list of {worksheet, schema_path, target_section})
2. Parallel fetch all worksheets via GoogleSheetsSource → sheet_data dict
3. DailyReportBuilder.build():
   - For each worksheet config:
     * detect_header_row()
     * For each data row:
       > map_row_to_document_data() → normalized dict
       > validate_row() → RowValidationResult (collect errors)
       > SheetExtractionPipeline.run() → partial BlockExtractionOutput
     * Merge partial output into full report (by target_section)
   - Extract report_date from header.ngay_bao_cao (required)
   - Build validation_summary from row results
4. SheetRevisionHasher.compute_hash(sheet_data) → sheet_revision_hash
5. Duplicate check: existing job with same (tenant, template, report_date, hash)
   - If duplicate → return existing job_id, skip creation
6. Determine next report_version for this date
7. Create source document containing full sheet snapshot
8. Create ExtractionJob with:
   - extracted_data = full BlockExtractionOutput (from builder)
   - sheet_revision_hash, report_date, report_version
   - validation_report = row-level summary
   - supersedes_job_id = previous version (if any)
   - status = "extracted", parser_used = "google_sheets"
9. Return snapshot summary (job_id, report_date, worksheets_processed, validation_summary)

[No further Celery processing needed — the job already contains the canonical report]
```

## Row-Level Mode (Legacy)

```
HTTP POST /jobs/ingest/google-sheet
    ↓
GoogleSheetIngestionService.ingest(req) with mode="row"
    ↓
1. Load custom schema from req.schema_path
2. GoogleSheetsSource.fetch_values() → raw 2D array
3. detect_header_row() → find header row
4. FOR EACH DATA ROW:
   a. map_row_to_document_data(row, schema) → normalized dict
   b. validate_row(model, normalized_data) → RowValidationResult
   c. Build row_document + confidence_scores
   d. Build row_hash = SHA-256(normalized_data)
   e. writer.is_duplicate(row_hash) check
   f. writer.write_row() → extraction_jobs row (parser_used="google_sheets")
5. Return ingestion summary (rows_processed, rows_inserted, rows_duplicate, errors)

[Later: Celery extract_document_task picks up job]
    ↓
ExtractionOrchestrator.run(job_id, source_type="sheet", sheet_data=job.extracted_data)
    ↓
SheetExtractionPipeline.run(sheet_data, schema_path=source_references.schema_path)
    ↓
persist_stage1_result() → job.extracted_data = canonical JSON, status=EXTRACTED
```

## Key Difference from PDF Pipeline

- **PDF pipeline:** Single document → full report with all sections populated
- **Sheet pipeline (snapshot):** All worksheets → full report in one job (no per-row jobs)
- **Sheet pipeline (row-level):** Each row → single canonical output with only one section populated (later aggregation merges rows)

Snapshot mode eliminates the aggregation step; row-level mode still requires aggregation.

---

# 5. Components

## 5.1 `GoogleSheetIngestionService`

- **File:** `app/engines/extraction/sheet_ingestion_service.py`
- **Main method:** `async ingest(self, req: IngestionRequest) -> dict[str, Any]`
- **Responsibility:** Orchestrate row ingestion: schema loading, fetch, header detection, row mapping, validation, idempotent write.
- **MUST NOT:** Call LLM, perform template rendering, trigger extraction pipeline (Celery does that).

## 5.2 `GoogleSheetsSource`

- **File:** `app/engines/extraction/sources/sheets_source.py`
- **Input:** `SheetsFetchConfig(sheet_id, worksheet, range_a1, max_retries, retry_backoff_seconds)`
- **Output:** `list[list[str]]` raw 2D array from Google Sheets API
- **Responsibility:** Build Google Sheets client, fetch rows with exponential retry.
- **MUST NOT:** Map business fields, validate schema.

## 5.3 `header_detector`

- **File:** `app/engines/extraction/mapping/header_detector.py`
- **Function:** `detect_header_row(rows, known_aliases, scan_limit=15)`
- **Output:** `(header_index, header_columns)`
- **Responsibility:** Find header row by scoring alias overlap with known field names.
- **WARNING:** `scan_limit=15` may miss headers beyond line 15. Consider increasing.

## 5.4 `mapper`

- **File:** `app/engines/extraction/mapping/mapper.py`
- **Function:** `map_row_to_document_data(row, schema)`
- **Output:** `(normalized_data, matched_fields, total_fields, missing_required)`
- **Responsibility:** Match column headers to schema field aliases, normalize values (Unicode, type coercion).
- **MUST NOT:** Persist to DB, decide duplicate status.

## 5.5 `row_validator`

- **File:** `app/engines/extraction/validation/row_validator.py`
- **Functions:** `build_validation_model(schema)`, `validate_row(...)`
- **Output:** `RowValidationResult(is_valid, normalized_data, errors, confidence)`
- **Responsibility:** Pydantic model validation (required, types). Confidence = 60% schema_match + 40% validation_ok.
- **MUST NOT:** Fetch from Google Sheets, write jobs.

## 5.6 `JobWriter`

- **File:** `app/engines/extraction/sheet_job_writer.py`
- **Input:** `row_document`, `confidence`, `source_references` (includes `row_hash`, `schema_path`, `sheet_id`, `worksheet`)
- **Output:** `(created: bool, job_id: str | None)`
- **Responsibility:** Idempotency check via in-memory hash set (loaded at init), create job, apply workflow transitions (`PROCESSING` → `EXTRACTED` → `READY_FOR_REVIEW`).
- **MUST NOT:** Do schema mapping, compute canonical block contract.
- **CRITICAL:** Duplicate check uses in-memory set loaded at initialization. Race condition possible under concurrent ingestion (see Bug #4). Consider DB-level unique constraint on `(source_references->>'row_hash')`.

## 5.7 `DailyReportBuilder` (Snapshot Mode)

- **File:** `app/engines/extraction/daily_report_builder.py`
- **Purpose:** Assemble full `BlockExtractionOutput` from multiple worksheet snapshots.
- **Input:** `template`, `sheet_data` (dict of worksheet → 2D array), `worksheet_configs`
- **Process:**
  - Iterates through each worksheet config
  - Detects header row using `detect_header_row`
  - Maps & validates each data row
  - Runs `SheetExtractionPipeline` per row to produce partial output
  - Merges partial outputs into the full report by `target_section`
- **Output:** `BlockExtractionOutput` with all sections populated
- **Critical:** Extracts `report_date` from `header.ngay_bao_cao`; raises error if missing

## 5.8 `SheetRevisionHasher` (Snapshot Mode)

- **File:** `app/engines/extraction/sheet_revision_hasher.py`
- **Method:** `compute_hash(sheet_data: dict) -> str`
- **Purpose:** Compute deterministic SHA-256 hash of the entire sheet for idempotency
- **Normalization:** Strips whitespace, converts empty cells to `None`, sorts worksheet keys
- **Output:** 64-character hex string

## 5.9 `DailyReportService` (Read Layer)

- **File:** `app/application/daily_report_service.py`
- **Purpose:** Unified read API for daily reports, supporting both snapshot and legacy row-level modes via dual-read
- **Key Methods:**
  - `get_report(tenant_id, template_id, report_date)` → returns full report dict (from snapshot job or aggregated row jobs)
  - `get_report_history(tenant_id, template_id, start_date, end_date)` → list of snapshot versions
- **Fallback Logic:** Tries snapshot first; if none, aggregates legacy row-level jobs using `AggregationService.aggregate_data_only()`

## 5.10 `SheetExtractionPipeline` (Custom Schema Mode)

- **File:** `app/engines/extraction/sheet_pipeline.py`
- **Method:** `run(self, sheet_data: dict[str, Any] | None, schema_path: str | None = None) -> PipelineResult`
- **New behavior (when `schema_path` provided):**
  1. `_load_custom_mapping(schema_path)` — load YAML with `sheet_mapping.<section>.fields` definitions
  2. `_build_output_custom(core_data, mapping)` — construct `BlockExtractionOutput` directly from flat row
     - Build `header` from mapped fields (may be all nulls)
     - Build `phan_I_va_II_chi_tiet_nghiep_vu` from mapped fields (may be all zeros/empty)
     - Build `bang_thong_ke` from `stt_map` if present
     - For each list section (`danh_sach_cnch`, `danh_sach_phuong_tien_hu_hong`, `danh_sach_cong_van_tham_muu`, `danh_sach_cong_tac_khac`, `danh_sach_chi_vien`, `danh_sach_chay`, `tuyen_truyen_online`): create single-item list with fields extracted from row via section's field map
  3. Special case: **BC NGÀY date computation** — if `header` mapping contains `ngay_bao_cao_day` and `ngay_bao_cao_month`, compute `ngay_bao_cao` as `dd/mm/yyyy` with year inference (month ≤ 2 → 2026 else 2025)
  4. Validate output via `_assert_contract_or_raise()` and `BlockExtractionOutput.model_validate()`
- **Legacy mode (no `schema_path`):** Falls back to global `sheet_mapping.yaml` and original `map_to_schema()` (PDF-style nested normalization).
- **MUST NOT:** Call Google Sheets API, write to DB.

---

# 6. Custom Schema Format

## Schema File Location

Custom schemas live in `app/domain/templates/`:

- `bc_ngay_schema.yaml` — BC NGÀY worksheet
- `vu_chay_schema.yaml` — VỤ CHÁY THỐNG KÊ worksheet
- `cnch_schema.yaml` — CNCH worksheet
- `chi_vien_schema.yaml` — CHI VIỆN worksheet

## Schema Structure

```yaml
sheet_mapping:
  <section_name>:
    fields:
      <canonical_field_name>: [<alias1>, <alias2>, ...]
      ...
```

**Example: `cnch_schema.yaml`**

```yaml
sheet_mapping:
  danh_sach_cnch:
    fields:
      stt: ["STT", "stt"]
      ngay_xay_ra: ["Ngày xảy ra sự cố", "ngay_xay_ra"]
      thoi_gian: ["Thời gian đến", "thoi_gian"]
      dia_diem: ["Địa điểm", "dia_diem"]
      dia_chi: ["Địa chỉ", "dia_chi"]
      noi_dung_tin_bao: ["Loại hình CNCH", "noi_dung_tin_bao", "noi_dung"]
      thiet_hai: ["Thiệt hại về người", "thiet_hai"]
      thong_tin_nan_nhan: ["Số người cứu được", "thong_tin_nan_nhan"]
```

**Example: `bc_ngay_schema.yaml`** (with special date computation)

```yaml
sheet_mapping:
  header:
    fields:
      so_bao_cao: ["SỐ BÁO CÁO", "so_bao_cao"]
      ngay_bao_cao_day: ["ngay_bao_cao_day"]  # auxiliary: extract day from column A
      ngay_bao_cao_month: ["ngay_bao_cao_month"]  # auxiliary: extract month from column B
      don_vi_bao_cao: ["ĐƠN VỊ BÁO CÁO", "don_vi"]
  phan_I_va_II_chi_tiet_nghiep_vu:
    fields:
      tong_so_vu_chay: ["TỔNG SỐ VỤ CHÁY", "tong_chay"]
      kiem_tra_dinh_ky: ["KIỂM TRA ĐỊNH KỲ", "kiem_tra"]
      ...
  bang_thong_ke:
    fields: {}  # not used directly
    stt_map:  # full STT 1-61 mapping goes here
      "1": "I. Lực lượng tham gia"
      "2": "CAND"
      ...
```

The `bc_ngay_schema` uses **auxiliary fields** (`ngay_bao_cao_day`, `ngay_bao_cao_month`) to compute the report date. These fields are not part of the final `BlockExtractionOutput.header`; instead, the pipeline combines them into `ngay_bao_cao`.

## How Aliases Work

For each field in a section, the mapper tries each alias in order:

1. Normalize alias: Unicode NFC + lowercase, strip spaces
2. Match against normalized column header from the sheet
3. First match wins → extract the cell value
4. If no alias matches, field remains `None` (or default if specified)

Aliases are **case-insensitive** and **Unicode-normalized**.

---

# 7. Special Business Logic

## BC NGÀY Date Computation

The BC NGÀY worksheet stores report dates as separate day and month columns (columns A and B). The pipeline computes the full date string `ngay_bao_cao` as follows:

```python
day = core.get("ngay_bao_cao_day")   # e.g., "20"
month = core.get("ngay_bao_cao_month")  # e.g., "4"
year = 2026 if int(month) <= 2 else 2025  # Jan/Feb → current year, else previous year
ngay_bao_cao = f"{int(day):02d}/{int(month):02d}/{year}"
```

**Rationale:** The operational sheet spans year boundaries. Reports from January-February belong to the current year's batch; March-December belong to the previous year's batch.

This logic lives in `_build_output_custom()` and is triggered when the `header` mapping contains both `ngay_bao_cao_day` and `ngay_bao_cao_month` fields.

---

# 8. Canonical Output for Sheet Jobs

## Model: `BlockExtractionOutput`

- **File:** `app/engines/extraction/schemas.py`

All sheet jobs produce this exact contract, but **most sections will be empty** except the one(s) relevant to that worksheet type.

### Sections by Worksheet Type

| Worksheet | Populated Sections | Example Section Content |
|-----------|-------------------|------------------------|
| BC NGÀY | `header`, `phan_I_va_II_chi_tiet_nghiep_vu`, `bang_thong_ke` | Header with computed date, totals, statistics table |
| VỤ CHÁY THỐNG KÊ | `danh_sach_chay` | Single fire incident item |
| CNCH | `danh_sach_cnch` | Single CNCH incident item |
| CHI VIỆN | `danh_sach_chi_vien` | Single vehicle trip item |

### Empty Sections

All other sections are present with empty/zero/null values to maintain schema consistency:

- `danh_sach_cnch`: `[]` (unless CNCH worksheet)
- `danh_sach_phuong_tien_hu_hong`: `[]`
- `danh_sach_cong_van_tham_muu`: `[]`
- `danh_sach_cong_tac_khac`: `[]`
- `danh_sach_chi_vien`: `[]` (unless CHI VIỆN worksheet)
- `danh_sach_chay`: `[]` (unless VỤ CHÁY worksheet)
- `tuyen_truyen_online`: `{ "so_tin_bai": 0, "so_hinh_anh": 0, "so_lan_cai_app_114": 0 }`

---

# 9. Daily Aggregation

## Purpose

Combine multiple sheet rows (from the same calendar day) into a single aggregated report per worksheet type.

## Aggregation Logic

The aggregation service (`app/application/aggregation_service.py`) groups jobs by:

1. **Tenant ID**
2. **Template IDs** (can aggregate across multiple templates if needed)
3. **Date** (extracted from `extracted_data.header.ngay_bao_cao` for BC NGÀY rows, or from row date fields for incident logs)

Then it merges the canonical outputs:

- **List sections** (`danh_sach_*`): Concatenate all items
- **Numeric totals** (`phan_I_va_II_chi_tiet_nghiep_vu`): Sum across rows
- **Header fields**: Take from the first row (or compute min/max dates for `thoi_gian_tu_den`)
- **`bang_thong_ke`**: Concatenate all `ChiTieu` items (may have duplicate STT numbers — downstream dedup may be needed)

## Example: CNCH Daily Aggregation

**Input rows (3 CNCH incidents on 2026-04-20):**

```json
// Row 1
{ "danh_sach_cnch": [{ "stt": 1, "ngay_xay_ra": "20/04/2026", ... }] }

// Row 2
{ "danh_sach_cnch": [{ "stt": 2, "ngay_xay_ra": "20/04/2026", ... }] }

// Row 3
{ "danh_sach_cnch": [{ "stt": 3, "ngay_xay_ra": "20/04/2026", ... }] }
```

**Aggregated output:**

```json
{
  "header": { "so_bao_cao": "TỔNG KẾT NGÀY 20/04/2026", ... },
  "danh_sach_cnch": [
    { "stt": 1, ... },
    { "stt": 2, ... },
    { "stt": 3, ... }
  ],
  "phan_I_va_II_chi_tiet_nghiep_vu": {
    "tong_so_vu_cnch": 3,
    ...
  }
}
```

---

# 10. Determinism & Idempotency

## Row Hash Computation

```python
row_hash = hashlib.sha256(
    json.dumps(normalized_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
```

The hash is computed from the **normalized row document** after alias mapping and type coercion, ensuring identical rows produce identical hashes regardless of original column order or minor formatting variations.

## Duplicate Detection Scope

Row hashes are scoped to:

```sql
WHERE tenant_id = ? 
  AND template_id = ? 
  AND parser_used = 'google_sheets'
  AND source_references->>'sheet_id' = ?
  AND source_references->>'worksheet' = ?
```

This allows the same physical row to be ingested into multiple templates (if needed) without collision, but prevents re-ingestion within the same worksheet.

## Retry Safety

Re-running ingestion on the same Google Sheet with unchanged data will:

- Insert new rows (new `row_hash` values)
- Skip existing rows (`DUPLICATE` status)
- Report accurate counts in `rows_skipped_idempotent`

---

# 11. Failure Modes

## `INVALID`

Required field missing or Pydantic validation error.

Set in `GoogleSheetIngestionService.ingest()` when `validate_row()` returns errors.

## `PARTIAL`

Row valid but some schema fields were not matched (coverage < 100%).

Condition: `matched_fields < total_fields`.

## `DUPLICATE`

`row_hash` already exists in the current scope.

Checked by `JobWriter.is_duplicate(row_hash)` before write.

## `CONTRACT_MISMATCH`

`SheetExtractionPipeline` output failed contract validation.

Raised by `_assert_contract_or_raise()` when top-level keys don't match `EXPECTED_TOP_LEVEL_KEYS`.

## Pipeline `failed` status

`SheetExtractionPipeline.run()` catches all exceptions and returns:

```python
PipelineResult(
    status="failed",
    output=None,
    errors=[f"EXCEPTION:{type(e).__name__}: {str(e)}"]
)
```

---

# 12. System Invariants

1. **Ingestion never produces canonical `BlockExtractionOutput`.** The ingestion service returns summary metrics only. Canonical transformation happens later in the extraction pipeline.

2. **Extraction never fetches Google Sheets data.** `SheetExtractionPipeline` only receives in-memory `sheet_data`; all Google API calls are confined to `GoogleSheetsSource`.

3. **Canonical output must pass strict contract validation.** `_assert_contract_or_raise()` and `BlockExtractionOutput.model_validate()` ensure exact schema compliance.

4. **Duplicate rows never create new jobs.** In-memory hash check + early return in `JobWriter.write_row()`.

5. **Row hash is derived from normalized mapped data.** Deterministic SHA-256 of sorted JSON ensures consistency across re-runs.

6. **Each sheet row produces at most one populated section.** The custom mapping ensures only the relevant section(s) contain data; all others are empty.

---

# 13. Minimal Diagram

```text
HTTP POST /jobs/ingest/google-sheet
            |
            v
GoogleSheetIngestionService.ingest()
            |
            v
Load custom schema from template_id → schema_path
            |
            v
GoogleSheetsSource.fetch_values() → raw 2D array
            |
            v
detect_header_row() → header index & columns
            |
            v
FOR EACH DATA ROW:
    map_row_to_document_data(row, schema)
            |
            v
    validate_row() → normalized_data + confidence
            |
            v
    row_hash = SHA-256(normalized_data)
            |
            v
    writer.is_duplicate(row_hash)?
            |
         YES|NO
            |  \
            |   writer.write_row()
            |       |
            |       v
            |   extraction_jobs row inserted
            |   (extracted_data = row doc,
            |    source_references = {row_hash, schema_path, sheet_id, worksheet})
            |
    count as DUPLICATE

Return ingestion summary

[Later: Celery task extract_document_task]
            |
            v
ExtractionOrchestrator.run(..., source_type="sheet", sheet_data=job.extracted_data)
            |
            v
SheetExtractionPipeline.run(sheet_data, schema_path)
            |
            v
_load_custom_mapping(schema_path)
            |
            v
_build_output_custom(core_data, mapping)
            |
            v
BlockExtractionOutput (canonical)
            |
            v
persist_stage1_result() → job.extracted_data = canonical JSON
```

---

# 14. Configuration & Templates

## Template Resolution

The `template_id` passed in the ingestion request is used to look up:

1. **Template record** in `templates` table (contains metadata, filename patterns, etc.)
2. **Custom schema path** via `TemplateService.get_schema_path(template_id)` → returns path like `app/domain/templates/bc_ngay_schema.yaml`

This decoupling allows multiple templates to share the same schema if needed.

## Schema Caching

`SheetExtractionPipeline` caches loaded custom mappings in module-level `_CUSTOM_MAPPING_CACHE` to avoid repeated YAML parsing within the same process.

---

# 15. Testing Strategy

- **Unit tests:** `tests/test_sheet_ingestion_service.py` — mock Google Sheets API, test row mapping, validation, duplicate detection.
- **Integration tests:** End-to-end ingestion with test sheets in a staging Google account.
- **Contract tests:** Ensure `BlockExtractionOutput` produced by `_build_output_custom()` validates against Pydantic model for each worksheet type.
- **Aggregation tests:** Verify that daily aggregation correctly concatenates lists and sums numeric fields across multiple rows.

---

# 16. Known Issues & TODOs

| Issue | Description | Status |
|-------|-------------|--------|
| Bug #3 | `JobWriter._load_existing_row_hashes()` loads ALL jobs into memory (no DB filter by sheet_id/worksheet). Fix: add JSONB filters. | Open |
| Bug #4 | Race condition on duplicate check (in-memory set not atomic). Fix: add unique index on `(source_references->>'row_hash')`. | Open |
| Bug #9 | No transaction rollback on batch failure (each row commits individually). Fix: batch-level transaction. | Open |
| Bug #11 | `detect_header_row()` `scan_limit=15` may miss header if it's on line 16+. Consider increasing to 30. | Open |
| TODO | Add request timeout to `GoogleSheetsSource` to prevent indefinite hangs. | Open |

---

# 17. References

- **Canonical schema:** `app/engines/extraction/schemas.py` — `BlockExtractionOutput` model
- **Custom schemas:** `app/domain/templates/*.yaml`
- **Pipeline code:** `app/engines/extraction/sheet_pipeline.py`
- **Ingestion service:** `app/engines/extraction/sheet_ingestion_service.py`
- **API endpoint:** `app/api/v1/ingestion.py`
- **Aggregation service:** `app/application/aggregation_service.py`
- **Workflow states:** `app/domain/workflow.py` — `JobStatus` enum and state machine
