"""
Migration: Add Stage-2 enrichment columns to extraction_jobs table.

Run this script ONCE against any existing PostgreSQL database to add the columns
introduced for the two-stage pipeline refactor.  New deployments created via
`Base.metadata.create_all()` will include the columns automatically from the
updated SQLAlchemy model.

Usage:
    python scripts/migrate_add_enrichment_columns.py

The script is idempotent — it safely skips columns that already exist.
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


ALTER_STATEMENTS = [
    # Enrichment lifecycle status: pending / running / enriched / failed / skipped
    """
    ALTER TABLE extraction_jobs
        ADD COLUMN IF NOT EXISTS enrichment_status VARCHAR(20);
    """,
    # Stage-2 LLM output — stored separately, NEVER overwrites extracted_data
    """
    ALTER TABLE extraction_jobs
        ADD COLUMN IF NOT EXISTS enriched_data JSONB;
    """,
    # Error message from the enrichment worker
    """
    ALTER TABLE extraction_jobs
        ADD COLUMN IF NOT EXISTS enrichment_error TEXT;
    """,
    # Timestamps for enrichment lifecycle tracking
    """
    ALTER TABLE extraction_jobs
        ADD COLUMN IF NOT EXISTS enrichment_started_at TIMESTAMP;
    """,
    """
    ALTER TABLE extraction_jobs
        ADD COLUMN IF NOT EXISTS enrichment_completed_at TIMESTAMP;
    """,
    # Index to allow the enrichment worker to efficiently poll pending jobs
    """
    CREATE INDEX IF NOT EXISTS idx_extraction_jobs_enrichment_status
        ON extraction_jobs (enrichment_status)
        WHERE enrichment_status IS NOT NULL;
    """,
]


def run_migration() -> None:
    from app.infrastructure.db.session import engine

    with engine.connect() as conn:
        for stmt in ALTER_STATEMENTS:
            clean = stmt.strip()
            logger.info("Running: %s", clean[:80].replace("\n", " "))
            conn.execute(clean)
            conn.commit()
    logger.info("Migration complete — enrichment columns added to extraction_jobs.")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        sys.exit(1)
