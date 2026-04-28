-- Migration: Add google_sheet_configs to extraction_templates
-- Date: 2025-04-24
-- Purpose: Support multiple worksheet configurations in a single template

-- Add new JSONB column (nullable, no default)
ALTER TABLE extraction_templates
ADD COLUMN IF NOT EXISTS google_sheet_configs JSONB;

-- Add comment for documentation
COMMENT ON COLUMN extraction_templates.google_sheet_configs IS
  'Array of worksheet configurations for Google Sheets ingestion. Each item contains: {worksheet, schema_path, range}. Enables a single template to ingest multiple worksheets from the same Google Sheet ID.';

-- Note: Existing templates using single-field configs (google_sheet_worksheet, google_sheet_schema_path, google_sheet_range)
-- will continue to work via auto-conversion logic in the ingestion service. No data migration required.
