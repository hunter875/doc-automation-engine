-- Migration: Add snapshot ingestion columns to extraction_jobs
-- Date: 2025-04-26
-- Purpose: Support Google Sheets snapshot-based ingestion with report-level events

-- Add snapshot-related columns
ALTER TABLE extraction_jobs
ADD COLUMN IF NOT EXISTS sheet_revision_hash VARCHAR(64),
ADD COLUMN IF NOT EXISTS report_date DATE,
ADD COLUMN IF NOT EXISTS report_version INTEGER,
ADD COLUMN IF NOT EXISTS validation_report JSONB,
ADD COLUMN IF NOT EXISTS supersedes_job_id UUID REFERENCES extraction_jobs(id) ON DELETE SET NULL;

-- Add indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_snapshot_lookup
ON extraction_jobs (tenant_id, template_id, report_date, parser_used)
WHERE parser_used = 'google_sheets' AND report_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_sheet_revision
ON extraction_jobs (sheet_revision_hash)
WHERE sheet_revision_hash IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN extraction_jobs.sheet_revision_hash IS
  'SHA-256 hash of the entire Google Sheet snapshot (all worksheets, all rows). Used for idempotency: identical sheet content produces same hash.';

COMMENT ON COLUMN extraction_jobs.report_date IS
  'The business date of the report, extracted from header.ngay_bao_cao. Defines the aggregate root identity for daily reports.';

COMMENT ON COLUMN extraction_jobs.report_version IS
  'Monotonically increasing version number for reports with the same (tenant_id, template_id, report_date). Starts at 1.';

COMMENT ON COLUMN extraction_jobs.validation_report IS
  'Row-level validation summary for snapshot ingestion: {total_rows, valid_rows, invalid_rows: [{worksheet, row_index, errors, confidence}], warnings, confidence_stats}';

COMMENT ON COLUMN extraction_jobs.supersedes_job_id IS
  'Self-referential FK to the previous version of this report (same tenant/template/report_date). Enables version chain traversal.';

-- Note: Existing row-level ingestion jobs (pre-snapshot) will have these columns NULL.
-- Dual-read mode: aggregation service falls back to row-level jobs when snapshot jobs don''t exist.
-- No data migration required — legacy rows remain unchanged.
