-- Migration: Add aggregation_group to extraction_templates
-- Date: 2025-04-24
-- Purpose: Support cross-template aggregation for daily operational reports

-- Add new column (nullable, no default)
ALTER TABLE extraction_templates
ADD COLUMN IF NOT EXISTS aggregation_group VARCHAR(100);

-- Optional: Add comment for documentation
COMMENT ON COLUMN extraction_templates.aggregation_group IS 'Group name for cross-template aggregation. Templates with the same group will be aggregated together in daily reports.';

-- Create index for performance (optional but recommended)
CREATE INDEX IF NOT EXISTS idx_extraction_templates_aggregation_group
ON extraction_templates(aggregation_group);
