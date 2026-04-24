-- Migration: Add Google Sheets configuration to extraction_templates
-- Date: 2025-04-23
-- Purpose: Store Google Sheets ingestion config in template for automation

-- Add new columns (nullable, no defaults to allow existing templates without config)
ALTER TABLE extraction_templates
ADD COLUMN IF NOT EXISTS google_sheet_id VARCHAR(500),
ADD COLUMN IF NOT EXISTS google_sheet_worksheet VARCHAR(100),
ADD COLUMN IF NOT EXISTS google_sheet_range VARCHAR(50),
ADD COLUMN IF NOT EXISTS google_sheet_schema_path VARCHAR(500);

-- Optional: Add comments for documentation
COMMENT ON COLUMN extraction_templates.google_sheet_id IS 'Google Sheet ID or URL for deterministic ingestion';
COMMENT ON COLUMN extraction_templates.google_sheet_worksheet IS 'Worksheet name within the Google Sheet';
COMMENT ON COLUMN extraction_templates.google_sheet_range IS 'A1 notation range to read (default: A1:ZZZ)';
COMMENT ON COLUMN extraction_templates.google_sheet_schema_path IS 'Path to YAML schema file for mapping sheet columns';
