# 1. Purpose

The Google Sheets → Canonical JSON pipeline solves one specific problem:

- Convert spreadsheet rows into deterministic, validated JSON records.
- Persist those records into `extraction_jobs` with idempotency (`row_hash`).
- Transform sheet-shaped payloads into the canonical contract `BlockExtractionOutput` when sheet extraction is executed.

**Integration with Engine 2:** Sheet pipeline is a first-class extraction mode alongside PDF Block mode. Both share:
- Same database (`extraction_jobs` table)
- Same canonical output (`BlockExtractionOutput`)
- Same aggregation pipeline (sheet jobs and PDF jobs can aggregate together)
- Different `parser_used` marker: `"google_sheets"` vs `"pdfplumber"`

This pipeline is implemented in code under:

- `app/engines/extraction/sheet_ingestion_service.py`
- `app/engines/extraction/sheet_pipeline.py`

---

# 2. Entry Point

## `GoogleSheetIngestionService`

- Class: `GoogleSheetIngestionService`
- File: `app/engines/extraction/sheet_ingestion_service.py`
- Main method: `async ingest(self, req: IngestionRequest) -> dict[str, Any]`

## `IngestionRequest`

- Dataclass: `IngestionRequest`
- File: `app/engines/extraction/sheet_ingestion_service.py`
- Fields:
  - `tenant_id`
  - `user_id`
  - `template_id`
  - `sheet_id`
  - `worksheet`
  - `schema_path`
  - `source_document_id` (optional)
  - `range_a1` (optional)

## How ingestion starts

HTTP entrypoint:

- Route: `POST /jobs/ingest/google-sheet`
- File: `app/api/v1/ingestion.py`
- Handler: `ingest_google_sheet(...)`

Execution inside handler:

1. Build `IngestionRequest` from request body + tenant/user context.
2. Instantiate `GoogleSheetIngestionService(db)`.
3. Call `await service.ingest(req)`.

---

# 3. Data Flow (REAL EXECUTION ORDER)

There are two distinct runtime paths in the implementation:

- **Ingestion path** (`GoogleSheetIngestionService`) writes rows into `extraction_jobs`.
- **Extraction path** (`SheetExtractionPipeline`) converts provided `sheet_data` into canonical `BlockExtractionOutput`.

The **complete end-to-end flow** is:

```
HTTP POST /jobs/ingest/google-sheet
    ↓
GoogleSheetIngestionService.ingest()
    ↓
GoogleSheetsSource.fetch_values()
    ↓
detect_header_row()
    ↓
FOR EACH ROW:
    map_row_to_document_data()
    validate_row()
    build_row_hash()
    writer.is_duplicate()
    writer.write_row() → extraction_jobs row với parser_used="google_sheets"
    ↓
Return ingestion summary

[Async: Celery extract_document_task picks up job]
    ↓
ExtractionOrchestrator.run(job_id, source_type="sheet", sheet_data=job.extracted_data)
    ↓
run_sheet_pipeline(sheet_data)
    ↓
SheetExtractionPipeline.run()
    ↓
normalize() + map_to_schema()
    ↓
BlockExtractionOutput (canonical)
    ↓
persist_stage1_result() → job.extracted_data = canonical JSON, status=EXTRACTED
```

**Code-level sequence**

### Ingestion sequence (`GoogleSheetIngestionService.ingest`)

File: `app/engines/extraction/sheet_ingestion_service.py`

1. `schema = load_schema(req.schema_path)`
2. `model = build_validation_model(schema)`
3. `raw_rows = await asyncio.to_thread(source.fetch_values, SheetsFetchConfig(...))`
4. `header_idx, header = detect_header_row(raw_rows, known_aliases=schema.all_aliases)`
5. For each data row:
   - `map_row_to_document_data(row_dict, schema)`
   - `validate_row(model=..., normalized_data=..., ...)`
   - Build `row_document` + `source_references`
   - `writer.is_duplicate(row_hash)` check
   - `writer.write_row(...)` if valid/non-duplicate
6. Return ingestion summary with row status counts and metrics.

### Canonical mapping sequence (`SheetExtractionPipeline.run`)

File: `app/engines/extraction/sheet_pipeline.py`

1. `normalized = self.normalize(sheet_data)`
2. `output = self.map_to_schema(normalized)`
3. `_assert_contract_or_raise(output)` inside mapping path
4. Return `PipelineResult(status="ok", output=BlockExtractionOutput(...))`
5. On exception, return `PipelineResult(status="failed", output=None, errors=[...])`

### Where `SheetExtractionPipeline` is executed

File: `app/engines/extraction/orchestrator.py`

- `ExtractionOrchestrator.run(..., source_type="sheet" | input_type="sheet")`
- Calls `self.run_sheet_pipeline(sheet_data)`
- `run_sheet_pipeline` instantiates `SheetExtractionPipeline` and calls `pipeline.run(...)`.
- Then `job_manager.persist_stage1_result()` lưu canonical output vào `job.extracted_data`.

**CRITICAL FIX (v4.1+):** `extract_document_task` MUST pass `source_type="sheet"` và `sheet_data=job.extracted_data` khi `job.parser_used == "google_sheets"`. See Bug #1-2 in analysis.

---

# 4. Components Implemented

## 4.1 `GoogleSheetIngestionService`

- File: `app/engines/extraction/sheet_ingestion_service.py`
- Input:
  - `IngestionRequest`
  - DB session
- Output:
  - Ingestion summary dict (`rows_processed`, `rows_failed`, `rows_inserted`, `errors`, `metrics`, etc.)
- Responsibility:
  - Orchestrate end-to-end row ingestion.
  - Apply schema loading, fetch, header detection, mapping, validation, idempotent writing.
- MUST NOT do:
  - Must not call any LLM.
  - Must not perform template rendering.
  - Must not trigger extraction pipeline (that's Celery's job).

## 4.2 `GoogleSheetsSource`

- File: `app/engines/extraction/sources/sheets_source.py`
- Input:
  - `SheetsFetchConfig(sheet_id, worksheet, range_a1, max_retries, retry_backoff_seconds)`
- Output:
  - `list[list[str]]` raw rows from Google Sheets API
- Responsibility:
  - Build Google Sheets client credentials.
  - Fetch rows with retry.
- MUST NOT do:
  - Must not map business fields.
  - Must not validate schema.
- **TODO:** Add `request_timeout` to prevent indefinite hangs (Bug #5).

## 4.3 `header_detector`

- File: `app/engines/extraction/mapping/header_detector.py`
- Function:
  - `detect_header_row(rows, known_aliases, scan_limit=15)`
- Input:
  - Raw rows + known aliases
- Output:
  - `(header_index, header_columns)`
- Responsibility:
  - Select header row by maximum alias overlap in top rows.
  - Score: count how many columns match known aliases (normalized lowercased).
- MUST NOT do:
  - Must not convert field values.
  - Must not write DB records.
- **WARNING:** `scan_limit=15` may miss header if it's on line 16+ (Bug #11). Consider increasing to 30.

## 4.4 `mapper`

- File: `app/engines/extraction/mapping/mapper.py`
- Function:
  - `map_row_to_document_data(row, schema)`
- Input:
  - One row dict + `IngestionSchema`
- Output:
  - `(normalized_data, matched_fields, total_fields, missing_required)`
- Responsibility:
  - Match aliases to schema fields (case-insensitive unicode normalized).
  - Normalize values via `normalize_field_value`.
- MUST NOT do:
  - Must not persist to DB.
  - Must not decide duplicate status.

## 4.5 `row_validator`

- File: `app/engines/extraction/validation/row_validator.py`
- Functions:
  - `build_validation_model(schema)`
  - `validate_row(...)`
- Input:
  - Schema + normalized row + coverage stats
- Output:
  - `RowValidationResult(is_valid, normalized_data, errors, confidence)`
- Responsibility:
  - Runtime type/required validation using generated Pydantic model.
  - Produce deterministic confidence metrics (60% schema_match + 40% validation_ok).
- MUST NOT do:
  - Must not fetch from Google Sheets.
  - Must not write jobs.

## 4.6 `JobWriter`

- File: `app/engines/extraction/sheet_job_writer.py`
- Input:
  - `row_document`, `confidence`, `source_references`
- Output:
  - `(created: bool, job_id: str | None)`
- Responsibility:
  - Idempotency by `row_hash`.
  - Create job and write `extracted_data`, `confidence_scores`, `source_references`.
  - Apply workflow transitions (`PROCESSING` → `EXTRACTED` → `READY_FOR_REVIEW`).
- MUST NOT do:
  - Must not do schema mapping.
  - Must not compute canonical block contract.
- **CRITICAL BUGS:**
  - **Bug #3:** `_load_existing_row_hashes()` loads ALL jobs into memory (no DB filter by sheet_id/worksheet). Fix: add JSONB filters.
  - **Bug #4:** Race condition on duplicate check (in-memory set not atomic). Fix: add unique index on `(source_references->>'row_hash')`.
  - **Bug #9:** No transaction rollback on batch failure (each row commits individually). Fix: batch-level transaction.

## 4.7 `SheetExtractionPipeline`

- File: `app/engines/extraction/sheet_pipeline.py`
- Input:
  - `sheet_data: dict[str, Any] | None` — raw row document from `job.extracted_data`
- Output:
  - `PipelineResult` containing `BlockExtractionOutput` on success
- Responsibility:
  - Normalize sheet payload shape (support nested `data`, flat, etc.)
  - Map payload to canonical `BlockExtractionOutput` using aliases from `sheet_mapping.yaml`.
  - Inject computed STT rows (32, 33, 51, 22-25)
  - Enforce strict contract check via `_assert_contract_or_raise()`.
- MUST NOT do:
  - Must not call Google Sheets API.
  - Must not write to DB.
- **NOTE:** This pipeline is called by `ExtractionOrchestrator` when `source_type="sheet"`.

---

# 5. Canonical Output

Canonical output model is `BlockExtractionOutput` (file: `app/engines/extraction/schemas.py`):

- `header: BlockHeader`
  - `so_bao_cao`
  - `ngay_bao_cao`
  - `thoi_gian_tu_den`
  - `don_vi_bao_cao`
- `phan_I_va_II_chi_tiet_nghiep_vu: BlockNghiepVu`
  - includes totals such as `tong_so_vu_chay`, `tong_so_vu_no`, `tong_so_vu_cnch`, etc.
- `bang_thong_ke: list[ChiTieu]`
  - each item: `stt`, `noi_dung`, `ket_qua`
- `danh_sach_cnch: list[CNCHItem]`
- `danh_sach_phuong_tien_hu_hong: list[PhuongTienHuHongItem]`
- `danh_sach_cong_van_tham_muu: list[CongVanItem]`
- `danh_sach_cong_tac_khac: list[str]`
- `danh_sach_chi_vien: list[ChiVienItem]` (from Excel CHI VIỆN sheet)
- `danh_sach_chay: list[VuChayItem]` (from Excel VỤ CHÁY sheet)
- `tuyen_truyen_online: TuyenTruyenOnline` (online metrics)

## Example canonical JSON

```json
{
  "header": {
    "so_bao_cao": "02/BC-TEST",
    "ngay_bao_cao": "20/04/2026",
    "thoi_gian_tu_den": "01/04/2026 - 20/04/2026",
    "don_vi_bao_cao": "Đội CNCH Test"
  },
  "phan_I_va_II_chi_tiet_nghiep_vu": {
    "tong_so_vu_chay": 0,
    "tong_so_vu_no": 0,
    "tong_so_vu_cnch": 3,
    "chi_tiet_cnch": "",
    "quan_so_truc": 0,
    "tong_chi_vien": 0,
    "tong_cong_van": 0,
    "tong_bao_cao": 0,
    "tong_ke_hoach": 0,
    "cong_tac_an_ninh": "",
    "tong_xe_hu_hong": 0,
    "tong_tin_bai": 0,
    "tong_hinh_anh": 0,
    "so_lan_cai_app_114": 0
  },
  "bang_thong_ke": [
    {
      "stt": "14",
      "noi_dung": "Tổng số vụ CNCH",
      "ket_qua": 3
    }
  ],
  "danh_sach_cnch": [
    {
      "stt": 1,
      "ngay_xay_ra": "20/04/2026",
      "thoi_gian": "09:30",
      "dia_diem": "Phường 1",
      "noi_dung_tin_bao": "Cứu nạn giao thông",
      "luc_luong_tham_gia": "",
      "ket_qua_xu_ly": "",
      "thiet_hai": "0",
      "thong_tin_nan_nhan": "2",
      "mo_ta": ""
    }
  ],
  "danh_sach_phuong_tien_hu_hong": [],
  "danh_sach_cong_van_tham_muu": [],
  "danh_sach_cong_tac_khac": [],
  "danh_sach_chi_vien": [],
  "danh_sach_chay": [],
  "tuyen_truyen_online": {
    "so_tin_bai": 0,
    "so_hinh_anh": 0,
    "so_lan_cai_app_114": 0
  }
}
```

---

# 6. Mapping Logic

## 4.1 `GoogleSheetIngestionService`

- File: `app/engines/extraction/sheet_ingestion_service.py`
- Input:
  - `IngestionRequest`
  - DB session
- Output:
  - Ingestion summary dict (`rows_processed`, `rows_failed`, `rows_inserted`, `errors`, `metrics`, etc.)
- Responsibility:
  - Orchestrate end-to-end row ingestion.
  - Apply schema loading, fetch, header detection, mapping, validation, idempotent writing.
- MUST NOT do:
  - Must not call any LLM.
  - Must not perform template rendering.

## 4.2 `GoogleSheetsSource`

- File: `app/engines/extraction/sources/sheets_source.py`
- Input:
  - `SheetsFetchConfig(sheet_id, worksheet, range_a1, max_retries, retry_backoff_seconds)`
- Output:
  - `list[list[str]]` raw rows from Google Sheets API
- Responsibility:
  - Build Google Sheets client credentials.
  - Fetch rows with retry.
- MUST NOT do:
  - Must not map business fields.
  - Must not validate schema.

## 4.3 `header_detector`

- File: `app/engines/extraction/mapping/header_detector.py`
- Function:
  - `detect_header_row(rows, known_aliases, scan_limit=15)`
- Input:
  - Raw rows + known aliases
- Output:
  - `(header_index, header_columns)`
- Responsibility:
  - Select header row by maximum alias overlap in top rows.
- MUST NOT do:
  - Must not convert field values.
  - Must not write DB records.

## 4.4 `mapper`

- File: `app/engines/extraction/mapping/mapper.py`
- Function:
  - `map_row_to_document_data(row, schema)`
- Input:
  - One row dict + `IngestionSchema`
- Output:
  - `(normalized_data, matched_fields, total_fields, missing_required)`
- Responsibility:
  - Match aliases to schema fields.
  - Normalize values via `normalize_field_value`.
- MUST NOT do:
  - Must not persist to DB.
  - Must not decide duplicate status.

## 4.5 `row_validator`

- File: `app/engines/extraction/validation/row_validator.py`
- Functions:
  - `build_validation_model(schema)`
  - `validate_row(...)`
- Input:
  - Schema + normalized row + coverage stats
- Output:
  - `RowValidationResult(is_valid, normalized_data, errors, confidence)`
- Responsibility:
  - Runtime type/required validation using generated Pydantic model.
  - Produce deterministic confidence metrics.
- MUST NOT do:
  - Must not fetch from Google Sheets.
  - Must not write jobs.

## 4.6 `JobWriter`

- File: `app/engines/extraction/sheet_job_writer.py`
- Input:
  - `row_document`, `confidence`, `source_references`
- Output:
  - `(created: bool, job_id: str | None)`
- Responsibility:
  - Idempotency by `row_hash`.
  - Create job and write `extracted_data`, `confidence_scores`, `source_references`.
  - Apply workflow transitions (`PROCESSING` → `EXTRACTED` → `READY_FOR_REVIEW`).
- MUST NOT do:
  - Must not do schema mapping.
  - Must not compute canonical block contract.

## 4.7 `SheetExtractionPipeline`

- File: `app/engines/extraction/sheet_pipeline.py`
- Input:
  - `sheet_data: dict[str, Any] | None`
- Output:
  - `PipelineResult` containing `BlockExtractionOutput` on success
- Responsibility:
  - Normalize sheet payload shape.
  - Map payload to canonical `BlockExtractionOutput` using aliases from `sheet_mapping.yaml`.
  - Enforce strict contract check.
- MUST NOT do:
  - Must not call Google Sheets API.
  - Must not write to DB.

---

# 5. Canonical Output

Canonical output model is `BlockExtractionOutput` (file: `app/engines/extraction/schemas.py`):

- `header: BlockHeader`
  - `so_bao_cao`
  - `ngay_bao_cao`
  - `thoi_gian_tu_den`
  - `don_vi_bao_cao`
- `phan_I_va_II_chi_tiet_nghiep_vu: BlockNghiepVu`
  - includes totals such as `tong_so_vu_chay`, `tong_so_vu_no`, `tong_so_vu_cnch`, etc.
- `bang_thong_ke: list[ChiTieu]`
  - each item: `stt`, `noi_dung`, `ket_qua`
- `danh_sach_cnch: list[CNCHItem]`
- `danh_sach_phuong_tien_hu_hong: list[PhuongTienHuHongItem]`
- `danh_sach_cong_van_tham_muu: list[CongVanItem]`
- `danh_sach_cong_tac_khac: list[str]`

## Example canonical JSON

```json
{
  "header": {
    "so_bao_cao": "02/BC-TEST",
    "ngay_bao_cao": "20/04/2026",
    "thoi_gian_tu_den": "01/04/2026 - 20/04/2026",
    "don_vi_bao_cao": "Đội CNCH Test"
  },
  "phan_I_va_II_chi_tiet_nghiep_vu": {
    "tong_so_vu_chay": 0,
    "tong_so_vu_no": 0,
    "tong_so_vu_cnch": 3,
    "chi_tiet_cnch": "",
    "quan_so_truc": 0,
    "tong_chi_vien": 0,
    "tong_cong_van": 0,
    "tong_bao_cao": 0,
    "tong_ke_hoach": 0,
    "cong_tac_an_ninh": "",
    "tong_xe_hu_hong": 0
  },
  "bang_thong_ke": [
    {
      "stt": "14",
      "noi_dung": "Tổng số vụ CNCH",
      "ket_qua": 3
    }
  ],
  "danh_sach_cnch": [
    {
      "stt": 1,
      "ngay_xay_ra": "20/04/2026",
      "thoi_gian": "09:30",
      "dia_diem": "Phường 1",
      "noi_dung_tin_bao": "Cứu nạn giao thông",
      "luc_luong_tham_gia": "",
      "ket_qua_xu_ly": "",
      "thiet_hai": "0",
      "thong_tin_nan_nhan": "2",
      "mo_ta": ""
    }
  ],
  "danh_sach_phuong_tien_hu_hong": [],
  "danh_sach_cong_van_tham_muu": [],
  "danh_sach_cong_tac_khac": []
}
```

---

# 6. Mapping Logic

## `sheet_mapping.yaml`

- File: `app/domain/templates/sheet_mapping.yaml`
- Loaded by `_load_sheet_mapping()` in `app/engines/extraction/sheet_pipeline.py`.
- Contains section mappings for:
  - `header`
  - `nghiep_vu`
  - `bang_thong_ke` (`fields` + `stt_map`)
  - list sections (`danh_sach_cnch`, `danh_sach_phuong_tien_hu_hong`, etc.)

## Alias matching

- In ingestion row mapping:
  - `map_row_to_document_data()` matches schema field aliases from `schema_path` YAML.
- In canonical mapping:
  - `SheetExtractionPipeline._aliases(...)` resolves aliases from `sheet_mapping.yaml`.
  - Supports both:
    - direct list form
    - nested `aliases`
    - nested `fields` map

## Normalization strategy

- `normalize_unicode_text()` applies Unicode NFC + whitespace normalization.
- Type coercion is deterministic:
  - integer/float/boolean/date parsing
  - optional transforms (`lowercase`, `uppercase`, `strip_non_digit`)
- Empty values become `None` before default resolution.

---

# 7. Deterministic Rules

- No LLM is used in this pipeline path.
- All transformations are deterministic functions (`fetch`, `alias match`, `coercion`, `validation`, `write`).
- Contract enforcement is strict in `SheetExtractionPipeline`:
  - Top-level key set must match `EXPECTED_TOP_LEVEL_KEYS` exactly.
  - Final model validation via `BlockExtractionOutput.model_validate(...)`.

---

# 8. Failure Modes

## `INVALID`

Set in ingestion summary when `validate_row(...)` returns errors:

- required field missing (`required_missing:<field>`)
- Pydantic model validation failure

Location: `GoogleSheetIngestionService.ingest`.

## `PARTIAL`

Set when row is valid but not all schema fields are matched:

- condition: `matched_fields < total_fields`

Location: `GoogleSheetIngestionService.ingest`.

## `DUPLICATE`

Set when `row_hash` already exists for `(tenant_id, template_id, sheet_id, worksheet)` scope:

- checked via `JobWriter.is_duplicate(row_hash)` or `write_row` duplicate return.

## `CONTRACT_MISMATCH`

Raised in canonical mapping when `BlockExtractionOutput` top-level keys differ from expected:

- raised by `_assert_contract_or_raise(...)` in `sheet_pipeline.py`
- message format: `CONTRACT_MISMATCH:missing=[...];extra=[...]`

## failed `PipelineResult`

`SheetExtractionPipeline.run(...)` catches exception and returns:

- `PipelineResult(status="failed", output=None, errors=[...])`

---

# 9. Minimal Diagram

```text
HTTP POST /jobs/ingest/google-sheet
            |
            v
 GoogleSheetIngestionService.ingest(req)
            |
            v
 GoogleSheetsSource.fetch_values()
            |
            v
 header_detector.detect_header_row()
            |
            v
 mapper.map_row_to_document_data()
            |
            v
 row_validator.validate_row()
            |
            v
 JobWriter.write_row()  ---> extraction_jobs.extracted_data

(when sheet extraction path is executed)
            |
            v
 SheetExtractionPipeline.normalize()
            |
            v
 SheetExtractionPipeline.map_to_schema()
            |
            v
 BlockExtractionOutput (canonical JSON)
```

---

## Pipeline Boundaries

### Ingestion Pipeline Boundary

- Starts at: `POST /jobs/ingest/google-sheet` (`app/api/v1/ingestion.py`).
- Core executor: `GoogleSheetIngestionService.ingest(...)`.
- Ends when: validated non-duplicate rows are persisted by `JobWriter.write_row(...)`.
- Persistent output: `extraction_jobs` records with:
  - `extracted_data` (row document)
  - `confidence_scores`
  - `source_references` (includes `row_hash`, `ingestion_run_id`, `row_status`, etc.)

### Extraction Pipeline Boundary

- Starts at: `ExtractionOrchestrator.run(..., source_type="sheet" | input_type="sheet")` in `app/engines/extraction/orchestrator.py`.
- Core executor: `SheetExtractionPipeline.run(sheet_data)`.
- Ends when: `PipelineResult` is returned.
  - Success: `PipelineResult.output` is `BlockExtractionOutput`.
  - Failure: `PipelineResult.status="failed"`, `output=None`, `errors=[...]`.

### Exact Handoff Point Between Pipelines

- Ingestion pipeline writes sheet row payloads into `extraction_jobs.extracted_data`.
- Extraction pipeline consumes in-memory `sheet_data` passed by orchestrator and produces canonical contract output.
- There is no direct call from `GoogleSheetIngestionService` to `SheetExtractionPipeline` in the implemented code.

---

## Data Ownership

### Source of truth

- Source of truth for persisted sheet-ingested business row data is `extraction_jobs.extracted_data`.
- Source of truth for row provenance/idempotency metadata is `extraction_jobs.source_references`.

### Persistence authority

- `JobWriter` is the component that persists sheet-ingested rows into `extraction_jobs`.
- `GoogleSheetIngestionService` orchestrates, but persistence is executed through `JobWriter`.

### Business data ownership

- Ingestion-owned business payload at persistence time is the row document written into `extracted_data`.
- Extraction-owned canonical payload is the `BlockExtractionOutput` object produced by `SheetExtractionPipeline`.

### Derived artifacts

- Ingestion summary (`rows_processed`, `rows_failed`, `row_status_counts`, etc.) is a derived runtime artifact.
- `PipelineResult` and its `BlockExtractionOutput` are derived execution artifacts of extraction.

### Role of `extraction_jobs.extracted_data`

- For ingestion path, it stores deterministic row-level sheet payload (`source`, `sheet_id`, `worksheet`, `row_index`, `row_hash`, `data`).
- It is written by `JobWriter.write_row(...)` after mapping and validation complete.

---

## System Invariants

The following invariants are directly provable from implementation:

1. Ingestion never produces canonical `BlockExtractionOutput`.
  - `GoogleSheetIngestionService.ingest` returns summary metrics/errors, not canonical contract models.

2. Extraction never fetches Google Sheets API data.
  - `SheetExtractionPipeline` only receives `sheet_data` input; Google API calls exist in `GoogleSheetsSource` only.

3. Canonical output must pass strict contract validation.
  - `SheetExtractionPipeline.map_to_schema` calls `_assert_contract_or_raise(output)` and `BlockExtractionOutput.model_validate(...)`.

4. Duplicate rows never create new jobs.
  - `JobWriter.is_duplicate(row_hash)` and early-return in `JobWriter.write_row` prevent new job creation for known hashes.

5. Orchestrator routes execution but does not transform sheet business fields.
  - `ExtractionOrchestrator` selects source path, calls `run_sheet_pipeline`, and delegates persistence of pipeline result to `JobManager`.

6. Row hash is derived from normalized mapped data.
  - `GoogleSheetIngestionService` computes `row_hash = JobWriter.build_row_hash(validation.normalized_data)`.

7. Ingestion row status is explicit and finite.
  - Status set is `VALID`, `INVALID`, `PARTIAL`, `SKIPPED`, `DUPLICATE`.

---

## Orchestrator Responsibility

### What the orchestrator does

- Selects execution branch by `source_type`/`input_type` (`sheet` vs non-sheet).
- For sheet branch:
  - sets parser marker (`parser_used="sheet"` at processing stage)
  - calls `run_sheet_pipeline(sheet_data)`
  - receives `PipelineResult`
- Delegates persistence/state handling to `JobManager.persist_stage1_result(...)`.
- Handles timing, logging, and failure marking through `job_manager.mark_failed_exception(...)`.

### What the orchestrator must not do

- Must not fetch Google Sheets rows directly.
- Must not perform row mapping or row validation.
- Must not compute alias-based field transformations.
- Must not enforce idempotency logic for ingestion rows.

---

## Idempotency Model

### Purpose of `row_hash`

- `row_hash` is the deterministic identity of a normalized row payload.
- Built from `validation.normalized_data` using SHA-256 in `JobWriter.build_row_hash(...)`.

### Duplicate detection lifecycle

1. At `JobWriter` initialization, existing hashes are loaded from persisted jobs (`parser_used == "google_sheets"`) for the same tenant/template.
2. Hash set is further scoped by `sheet_id` and `worksheet` in `source_references`.
3. For each prepared row, ingestion checks duplicate via `writer.is_duplicate(row_hash)` before write.
4. `write_row(...)` re-checks duplicate and returns `(False, None)` if hash already exists.

### Retry safety guarantees

- Re-running ingestion with unchanged normalized row payload does not create an additional job for the same row hash scope.
- Duplicate rows are reported as `DUPLICATE` and counted in `rows_skipped_idempotent`.

### Ingestion re-run behavior

- First run inserts new valid rows.
- Subsequent run over same source rows:
  - existing hashes are skipped
  - summary reflects skips (`rows_skipped_idempotent`) and status distribution includes `DUPLICATE`.
