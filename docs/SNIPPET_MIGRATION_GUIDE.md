# Snapshot Ingestion Migration Guide

## Overview

This guide walks through enabling the new snapshot-based ingestion architecture for Google Sheets.

## Prerequisites

- Database backup (always)
- Docker Compose environment running
- Access to `psql` or `docker exec` into the PostgreSQL container

## Step 1: Apply Database Migration

Run the SQL migration to add snapshot-specific columns:

```bash
# From project root
docker exec -i rag-db psql -U postgres -d rag_db < scripts/migrations/004_add_snapshot_ingestion_columns.sql
```

Or manually inside the DB container:

```bash
docker exec -it rag-db psql -U postgres -d rag_db
# Then: \i scripts/migrations/004_add_snapshot_ingestion_columns.sql
```

**Verify columns added:**

```sql
\d extraction_jobs
```

Should show:
- `sheet_revision_hash` (VARCHAR(64))
- `report_date` (DATE)
- `report_version` (INTEGER)
- `validation_report` (JSONB)
- `supersedes_job_id` (UUID)

## Step 2: Update Environment Variable

Set `SHEET_INGESTION_MODE=snapshot` in your `.env` file:

```bash
SHEET_INGESTION_MODE=snapshot
```

Restart the API service:

```bash
docker compose restart api
```

**Note:** Snapshot mode requires templates to have `google_sheet_configs` (list of worksheet configs with `target_section`). Existing templates may need to be updated via admin UI or API.

## Step 3: Verify Feature Flag

The `GoogleSheetIngestionService` routes automatically:

- If `SHEET_INGESTION_MODE=snapshot` **and** `template.google_sheet_configs` is a non-empty list → snapshot mode
- Else if `configs` provided → multi-worksheet row mode (legacy)
- Else → single-worksheet row mode (legacy)

## Step 4: Test with a Template

1. Ensure your template has `google_sheet_configs` configured, e.g.:

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
  }
]
```

2. Call the sync endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/sheets/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "x-tenant-id: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "sheet_id": "YOUR_SHEET_ID",
    "template_id": "YOUR_TEMPLATE_ID"
  }'
```

3. Expected response (snapshot):

```json
{
  "status": "ok",
  "sheet_id": "...",
  "job_id": "...",
  "report_date": "2026-04-26",
  "report_version": 1,
  "worksheets_processed": ["BC NGÀY", "CNCH"],
  "rows_processed": 150,
  "rows_valid": 148,
  "rows_failed": 2,
  "validation_summary": { ... },
  "metrics": { ... },
  "ingestion_mode": "snapshot"
}
```

4. Check the job in DB:

```sql
SELECT id, parser_used, sheet_revision_hash, report_date, report_version, validation_report
FROM extraction_jobs
WHERE id = '...';
```

`sheet_revision_hash` should be non-NULL.

## Step 5: Dual-Read Fallback

Reading reports via `DailyReportService.get_report()`:

- If a snapshot job exists for the report date → returned directly
- If not, falls back to aggregating legacy row-level jobs (if any)

This ensures continuity during migration.

## Step 6: Monitor & Validate

- Check ingestion logs for `sheet_revision_hash` computation and duplicate detection
- Verify `report_date` extraction succeeded (it's mandatory)
- Ensure `validation_summary` contains row-level errors but didn't block job creation
- Review the created `extracted_data` to confirm full report structure

## Rollback

To revert to row-level ingestion:

1. Set `SHEET_INGESTION_MODE=row` in `.env`
2. Restart API
3. New ingestions will use row-level mode
4. Snapshot jobs remain in DB and can still be read via dual-read (they'll be returned as-is)

## Next Steps

- Update all templates with `google_sheet_configs` (if not already)
- Adjust UI to display `report_version` and `validation_summary` for snapshot jobs
- Consider removing row-level aggregation for Google Sheets once all templates are migrated
- Add monitoring alerts for snapshot ingestion failures (e.g., missing `report_date`)

## Known Limitations

- **Race condition on duplicate detection:** The `sheet_revision_hash` duplicate check is not fully atomic under high concurrency. A unique index would make it truly idempotent. Consider adding:
  
  ```sql
  CREATE UNIQUE INDEX IF NOT EXISTS idx_extraction_jobs_snapshot_unique
    ON extraction_jobs (tenant_id, template_id, report_date, sheet_revision_hash)
    WHERE sheet_revision_hash IS NOT NULL;
  ```

- **Large sheets:** Snapshot mode loads all worksheets into memory. For sheets with >10k rows, consider increasing container memory limits.

- **Validation errors:** In snapshot mode, validation errors do not prevent job creation; they're only recorded in `validation_report`. Ensure consumers check row-level validity if needed.
