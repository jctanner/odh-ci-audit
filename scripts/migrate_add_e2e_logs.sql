-- Migration: Add e2e_log_path and diagnostic_summary to test_runs table
-- Date: 2026-01-14
-- Description: Support filesystem storage of e2e test logs with extracted diagnostics

-- Add e2e_log_path column to store filesystem path to detailed test execution logs
ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS e2e_log_path TEXT;

-- Add diagnostic_summary column to store extracted diagnostic snippets for fast querying
ALTER TABLE test_runs ADD COLUMN IF NOT EXISTS diagnostic_summary JSONB;

-- Create index for log path queries (useful for cleanup and verification)
CREATE INDEX IF NOT EXISTS idx_test_runs_e2e_log_path ON test_runs(e2e_log_path) WHERE e2e_log_path IS NOT NULL;

-- Create GIN index for diagnostic_summary JSONB queries (fast searching of diagnostic data)
CREATE INDEX IF NOT EXISTS idx_test_runs_diagnostic_summary ON test_runs USING GIN (diagnostic_summary) WHERE diagnostic_summary IS NOT NULL;

-- Verify migration
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'test_runs' AND column_name = 'e2e_log_path'
    ) THEN
        RAISE NOTICE 'Migration successful: e2e_log_path column added';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'test_runs' AND column_name = 'diagnostic_summary'
    ) THEN
        RAISE NOTICE 'Migration successful: diagnostic_summary column added';
    END IF;
END $$;
