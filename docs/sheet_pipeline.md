# Google Sheets Operational Data Ingestion Pipeline

**Version:** 6.1 (April 2026) — Snapshot Architecture
**Runtime Validation:** `verify_snapshot_custom_schema.py` — 11/11 checks passed (2026-04-28). Unit test suite: not fully run at time of writing.

---

## Overview

The pipeline supports two ingestion modes. **Only snapshot mode is active.** Row mode is deprecated legacy and must not be used for new templates.

| Mode | Status | Behavior |
|------|--------|----------|
| `snapshot` **(active)** | ✅ In use | All worksheets → 1 `ExtractionJob` with full `BlockExtractionOutput` |
| `row` (legacy) | ⚠️ Deprecated | Each row → 1 `ExtractionJob`. Retained for migration only. Do not use for new templates. |

`SHEET_INGESTION_MODE=row` is ignored for templates that have `google_sheet_configs` defined. The `SHEET_INGESTION_MODE` flag only gates the fallback path for templates without configs.

**Snapshot mode eliminates the aggregation step.** The job already contains the complete report.

---

## Snapshot Architecture

### Core Concept

The Google Sheet is the working document. All worksheets together constitute one logical DailyReport. The ingestion run processes all worksheets in one transaction, builds the full `BlockExtractionOutput`, and persists it as a single `ExtractionJob`.

### Worksheet Configuration

Templates define `google_sheet_configs` in the database:

```json
[
  { "worksheet": "BC NGÀY",          "schema_path": "bc_ngay_schema.yaml",   "target_section": "header" },
  { "worksheet": "VỤ CHÁY THỐNG KÊ", "schema_path": "vu_chay_schema.yaml",   "target_section": "danh_sach_chay" },
  { "worksheet": "CNCH",              "schema_path": "cnch_schema.yaml",      "target_section": "danh_sach_cnch" },
  { "worksheet": "CHI VIỆN",          "schema_path": "chi_vien_schema.yaml",  "target_section": "danh_sach_chi_vien" }
]
```

> **BC NGÀY** is the master worksheet: it provides `header.ngay_bao_cao` (report date) as well as `phan_I_va_II_chi_tiet_nghiep_vu` (totals) and `bang_thong_ke` (statistics table). The other worksheets supply single-item list sections (`danh_sach_chay`, `danh_sach_cnch`, `danh_sach_chi_vien`). All sections are merged into one `BlockExtractionOutput`.

### Ingestion Flow (Snapshot Mode)

```
POST /jobs/ingest/google-sheet/sync
    ↓
GoogleSheetIngestionService.ingest()  [SHEET_INGESTION_MODE=snapshot]
    ↓
1. Load template → google_sheet_configs
2. Parallel fetch all worksheets → sheet_data dict (worksheet_name → rows)
3. DailyReportBuilder.build(template, sheet_data, worksheet_configs)
   a. For each config:
      - detect_header_row() → find header row index
      - For each data row:
        > Build row_dict: {normalized_header: cell_value}
        > validate_row() → RowValidationResult (optional)
        > SheetExtractionPipeline.run(row_dict, schema_path) → partial BlockExtractionOutput
          (Note: pipeline expects raw column headers as keys, NOT field names)
      - Merge partial output into full report by target_section
   b. Extract report_date from header.ngay_bao_cao (required)
   c. Build validation_summary from row results
4. Flatten aggregated BlockExtractionOutput → flat_dict via _flatten_report()
   Output shape: { ...all fields at top level (header fields, nghiệp vụ fields, lists) }
5. Create ExtractionJob with intermediate payload:
   - extraction_mode = "block"
   - parser_used = "google_sheets"
   - extracted_data = {
       "source": "google_sheet",
       "sheet_id": <sheet_id>,
       "data": <flat_dict>
     }
6. Return: { job_id, status, parser_used, template_id, worksheets_processed, rows_fetched }
```

---

## Key Components

### 5.1 `GoogleSheetIngestionService`

- **File:** `app/engines/extraction/sheet_ingestion_service.py`
- **MUST NOT:** Call LLM, render templates, trigger Celery tasks.

### 5.2 `DailyReportBuilder`

- **File:** `app/engines/extraction/daily_report_builder.py`
- **Purpose:** Assemble full `BlockExtractionOutput` from multiple worksheet snapshots.
- **Critical:** Extracts `report_date` from `header.ngay_bao_cao` (must exist after fix 2026-04-28).
- **Per-Row Processing:**
  1. Build `row_dict`: `{normalized_header → cell_value}` using `normalize_unicode_text()` on column headers.
  2. Validate via `validate_row()` against Pydantic model (optional).
  3. Call `SheetExtractionPipeline.run(row_dict, schema_path)` to produce partial output.
  4. Merge partial output into master report by `target_section`.
- **CRITICAL BUG (2026-04-30):** Current code incorrectly passes `doc_data` (field-name keys) to the pipeline instead of `row_dict`. This breaks field matching. **Fix:** Replace `pipeline.run({"data": doc_data})` with `pipeline.run(row_dict)`.

### 5.3 `SheetExtractionPipeline`

- **File:** `app/engines/extraction/sheet_pipeline.py`
- **Key fix (2026-04-28):** `_resolve_field_value()` now includes the canonical `field_name` as an implicit alias, fixing `ngay_bao_cao_month` resolution.
- **Signature:** `_resolve_field_value(core_norm, field_name, aliases)` — `field_name` is always the first candidate.
- **MUST NOT:** Call Google Sheets API, write to DB.
- **Critical:** Snapshot mode (`schema_path` provided) never loads `sheet_mapping.yaml`. See §Mapping Source of Truth.

### 5.4 `SheetRevisionHasher`

- **File:** `app/engines/extraction/sheet_revision_hasher.py`
- **Purpose:** SHA-256 of all worksheet data for snapshot idempotency.

### 5.5 `DailyReportService`

- **File:** `app/application/daily_report_service.py`
- **Purpose:** Read API for snapshot jobs by (tenant, template, report_date).

---

## Idempotency

Duplicate check: `(tenant_id, template_id, report_date, sheet_revision_hash)`

Version chain: if sheet content changed → new `report_version`, `supersedes_job_id` links to previous.

---

## Database Schema

```sql
ALTER TABLE extraction_jobs ADD COLUMN sheet_revision_hash VARCHAR(64);
ALTER TABLE extraction_jobs ADD COLUMN report_date DATE;
ALTER TABLE extraction_jobs ADD COLUMN report_version INTEGER;
ALTER TABLE extraction_jobs ADD COLUMN validation_report JSONB;
ALTER TABLE extraction_jobs ADD COLUMN supersedes_job_id UUID REFERENCES extraction_jobs(id);

CREATE INDEX idx_extraction_jobs_snapshot_lookup
  ON extraction_jobs (tenant_id, template_id, report_date, parser_used)
  WHERE parser_used = 'google_sheets' AND report_date IS NOT NULL;
```

---

## Canonical Output: `BlockExtractionOutput`

### Sections by Worksheet Type

| Worksheet | Populated Sections |
|-----------|-------------------|
| BC NGÀY | `header`, `phan_I_va_II_chi_tiet_nghiep_vu`, `bang_thong_ke` |
| VỤ CHÁY THỐNG KÊ | `danh_sach_chay` |
| CNCH | `danh_sach_cnch` |
| CHI VIỆN | `danh_sach_chi_vien` |

All other sections are present with empty/zero values.

---

## Mapping Source of Truth

Snapshot mode uses a **worksheet-specific schema only**. There is one schema file per worksheet, and it is always loaded via the `schema_path` declared in the template's `google_sheet_configs`.

```
GoogleSheetIngestionService.ingest()
    ↓
DailyReportBuilder.build(template, sheet_data, worksheet_configs)
    ↓
SheetExtractionPipeline.run(sheet_data, schema_path="bc_ngay_schema.yaml")
    ↓
_load_custom_mapping(schema_path)     ← loads ONLY the schema_path file
    ↓  NEVER loads app/domain/templates/sheet_mapping.yaml
_build_output_custom(core_data, mapping)
```

**`SheetExtractionPipeline.run()` — snapshot mode path:**

```python
def run(self, sheet_data, schema_path=None):
    if schema_path:
        mapping = _load_custom_mapping(schema_path)  # worksheet-specific YAML only
        output = _build_output_custom(core_data, mapping)
    else:
        # Legacy fallback: loads global sheet_mapping.yaml
        mapping = _load_sheet_mapping()
        output = self.map_to_schema(sheet_data, mapping)
```

**`sheet_mapping.yaml` is legacy/global fallback only.** It is loaded when `schema_path` is `None`. No KV30 template should pass `schema_path=None`.

---

## Schema Files

Custom schemas live in `app/domain/templates/`:

| File | Worksheet | Populated Sections |
|------|-----------|-------------------|
| `bc_ngay_schema.yaml` | BC NGÀY | `header`, `phan_I_va_II_chi_tiet_nghiep_vu`, `bang_thong_ke` |
| `vu_chay_schema.yaml` | VỤ CHÁY THỐNG KÊ | `danh_sach_chay` |
| `cnch_schema.yaml` | CNCH | `danh_sach_cnch` |
| `chi_vien_schema.yaml` | CHI VIỆN | `danh_sach_chi_vien` |

All four schemas are defined as **worksheet-specific** under `sheet_mapping.<section>.fields`. BC NGÀY additionally uses `sheet_mapping.header.ngay_bao_cao_day` and `ngay_bao_cao_month` auxiliary fields to reconstruct the full report date.

### BC NGÀY Date Computation

Columns A (NGÀY) and B (THÁNG) store **plain integers** (e.g., `1`, `4`) — not Excel serial dates. The BC NGÀY worksheet is a single-row-per-report layout, so the reader returns these as integers directly. `_build_output_custom_header` combines them into the full date string:

```
day_val   = _resolve_field_value(core_norm, "ngay_bao_cao_day",   aliases)   # "1"
month_val = _resolve_field_value(core_norm, "ngay_bao_cao_month", aliases)  # "4"
ngay_bao_cao = f"{int(day_val):02d}/{int(month_val):02d}/2026"               # "01/04/2026"
```

**Event-list date fields** (CNCH, VỤ CHÁY, CHI VIỆN) — where each row is one incident — may store dates as **Excel serial integers** (e.g., `45680`). The reader (`excel_kv30_reader.py`) converts these via `datetime.date(1899, 12, 30) + timedelta(days=N)` before they reach the pipeline.

---

## System Invariants

1. **Ingestion never calls LLM.** Pure data transformation only.
2. **Pipeline never calls Google Sheets API.** All data received in-memory.
3. **Canonical output passes Pydantic validation.** `_assert_contract_or_raise()` + `BlockExtractionOutput.model_validate()`.
4. **Snapshot idempotency.** A duplicate ingestion run (same tenant, template, report_date, sheet content) returns the existing job. Idempotency key: `(tenant_id, template_id, report_date, sheet_revision_hash)`.
5. **Report date is always extracted.** Snapshot job fails creation if `header.ngay_bao_cao` is missing.
6. **Snapshot mode uses worksheet-specific schema only.** `SheetExtractionPipeline.run(schema_path=...)` loads only the schema at `schema_path`. It never loads `sheet_mapping.yaml`. See §Mapping Source of Truth.

---

## Optimizations Applied (2026-04-28)

### Fix: `_resolve_field_value` field_name as implicit alias

**Before:** Function only tried YAML aliases → `ngay_bao_cao_month` aliases `["tháng"]` didn't match `core_norm` key `"ngay bao cao month"` → returned `None` → `ngay_bao_cao = ""`.

**After:** `field_name` (snake_case) is always the first candidate. `"ngay_bao_cao_month"` normalizes to `"ngay bao cao month"` → exact match in `core_norm`.

**Code change:**
```python
# Before
def _resolve_field_value(core_norm, aliases) -> Any:
    for alias in aliases:          # only tried aliases
        lookup = _normalize_key(alias)
        ...

# After
def _resolve_field_value(core_norm, field_name, aliases) -> Any:
    candidates = [field_name] + aliases  # field_name is always first
    for cand in candidates:         # try field_name first
        lookup = _normalize_key(cand)
        if lookup in core_norm:
            return core_norm[lookup]
```

### Fix: BC NGÀY YAML aliases from Excel evidence

Added exact Excel column headers as aliases:
- `tong_so_vu_chay` → `"VỤ CHÁY THỐNG KÊ"`
- `tong_chi_vien` → `"VỤ CHÁY CHI VIỆN"`
- `tong_so_vu_cnch` → `"SCLQ PCCC&CNCH"`, `"CNCH"`
- `tong_tin_bai` → `"TIN BÀI, PHÓNG SỰ"`
- `kiem_tra_dinh_ky` → `"KIỂM TRA ĐỊNH KỲ NHÓM I"`, `"KIỂM TRA ĐỊNH KỲ NHÓM II"`
- `kiem_tra_dot_xuat` → `"KIỂM TRA ĐỘT XUẤT NHÓM I"`, `"KIỂM TRA ĐỘT XUẤT NHÓM II"`
- Typo fix: `noi_duang` → `noi_dung` in `stt_map` entry "48"

### Fix: CNCH/VỤ CHÁY/CHI VIỆN schema aliases

Added all-caps Excel column headers as aliases in all three schema files.

---

## Proposed Optimizations (Not Applied)

### 1. Remove deprecated `row` mode code path (low priority)

The `row` mode branch in `GoogleSheetIngestionService` is no longer exercised by any active template. After confirming there are no live `SHEET_INGESTION_MODE=row` deployments, the branch can be removed to simplify the codebase.

> **Do not use `row` mode for new templates.** It has not been tested in the current snapshot architecture.

**File:** `app/engines/extraction/sheet_ingestion_service.py`

### 2. Snapshot unique index (medium priority)

**Current:** Duplicate detection is done in-memory after building the full report. Concurrent ingestion requests can both pass the check and create duplicate jobs.

**Proposed fix:**
```sql
CREATE UNIQUE INDEX idx_snapshot_idempotency
  ON extraction_jobs (tenant_id, template_id, report_date, sheet_revision_hash)
  WHERE sheet_revision_hash IS NOT NULL;
```

**Benefit:** Moves duplicate detection to the DB layer, eliminating the race condition. If the unique index is violated, the second request returns the existing job.

**File:** `app/engines/extraction/sheet_ingestion_service.py` (wrap write in try/except on `UniqueViolation`)

### 3. Increase `detect_header_row` scan_limit (low priority)

**Current:** `scan_limit=15` may miss headers beyond row 15.

**Proposed fix:** Increase to 30 or make configurable.

**File:** `app/engines/extraction/mapping/header_detector.py`

### 4. Add request timeout to `GoogleSheetsSource` (low priority)

Prevents indefinite hangs on API failures.

**File:** `app/engines/extraction/sources/sheets_source.py`

### 5. Consolidate `ExcelKV30Reader` into pipeline (low priority)

The `ExcelKV30Reader` class reads the `.xlsx` file directly for local development. The production path uses `GoogleSheetsSource`. These two paths could share a common row-normalization interface.

---

## Column Header Normalization & Aliases

To ensure robust matching across diverse Google Sheets exports, both column headers and schema aliases undergo the same normalization pipeline:

1. Unicode NFC normalization
2. Strip leading/trailing whitespace
3. Remove diacritics (e.g., "ĐỀ" → "DE", "ngày" → "ngay")
4. Collapse all whitespace (including newlines, tabs) to single space
5. Lowercase

**Example:**  
Raw header: `"VỤ CHÁY \nTHỐNG KÊ "` → Normalized: `"vu chay thong ke"`

Schema alias: `"VỤ CHÁY THỐNG KÊ"` → Normalized: `"vu chay thong ke"` → **MATCH**

**Schema authoring must include all observed header variants** (including newlines, trailing spaces, merged headers) as aliases to guarantee matching. The normalization step makes matching tolerant to formatting differences.

**Matching algorithm** (`_resolve_field_value`):
1. Try the canonical `field_name` first (e.g., `"ngay_bao_cao_day"` → `"ngay bao cao day"`).
2. Then try each alias in order.
3. Also supports diacritics-stripped exact match and prefix matching for single-word candidates.

---

## Known Issues (Open)

| # | Description | File | Status |
|---|-------------|------|--------|
| Bug #3 | `JobWriter._load_existing_row_hashes()` loads ALL jobs into memory | `sheet_job_writer.py` | Open |
| Bug #4 | Race condition on duplicate check (in-memory set) | `sheet_job_writer.py` | Open |
| Bug #9 | No transaction rollback on batch failure | `sheet_job_writer.py` | Open |
| Bug #11 | `detect_header_row` scan_limit=15 may miss header | `header_detector.py` | Open |
| Bug #12 | `DailyReportBuilder._process_worksheet_with_schema()` passes `doc_data` (field-name keys) to pipeline instead of raw `row_dict`, causing field matching to fail. Integration tests return empty reports. | `daily_report_builder.py:789` | **Open (Critical)** |

---

## References

- `app/engines/extraction/sheet_ingestion_service.py`
- `app/engines/extraction/daily_report_builder.py`
- `app/engines/extraction/sheet_pipeline.py`
- `app/engines/extraction/sheet_revision_hasher.py`
- `app/application/daily_report_service.py`
- `app/engines/extraction/schemas.py` — `BlockExtractionOutput`
- `app/domain/templates/bc_ngay_schema.yaml`
- `app/domain/templates/cnch_schema.yaml`
- `app/domain/templates/chi_vien_schema.yaml`
- `app/domain/templates/vu_chay_schema.yaml`
