"""Migration script for workflow state machine v4.0.

MUST run BEFORE deploying the new code.

Changes:
  1. ALTER extraction_jobs.status column from VARCHAR(20) to VARCHAR(30)
     to accommodate new states: enriching, ready_for_review, aggregated.
  2. CREATE TABLE extraction_job_events — audit log for all state transitions.
  3. Migrate legacy data: jobs that were 'extracted' and later approved/rejected
     should retroactively be marked as 'ready_for_review' in the audit trail.

Usage:
    python -m scripts.migrate_workflow_v4
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import text

from app.infrastructure.db.session import SessionLocal

# Ensure all models are loaded
from app.infrastructure.db import models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_migration() -> None:
    db = SessionLocal()
    try:
        # ── Step 1: Widen status column ──────────────────────────────────
        logger.info("Step 1: ALTER extraction_jobs.status VARCHAR(20) → VARCHAR(30)")
        db.execute(text("""
            ALTER TABLE extraction_jobs
            ALTER COLUMN status TYPE VARCHAR(30)
        """))
        db.commit()
        logger.info("  ✓ status column widened to VARCHAR(30)")

        # ── Step 2: Create extraction_job_events table ───────────────────
        logger.info("Step 2: CREATE TABLE extraction_job_events (if not exists)")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS extraction_job_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_id UUID NOT NULL REFERENCES extraction_jobs(id) ON DELETE CASCADE,
                from_state VARCHAR(30),
                to_state VARCHAR(30) NOT NULL,
                actor_type VARCHAR(20) NOT NULL DEFAULT 'system',
                actor_id VARCHAR(64),
                reason TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT now()
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_job_events_job_id
            ON extraction_job_events(job_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_job_events_created_at
            ON extraction_job_events(created_at)
        """))
        db.commit()
        logger.info("  ✓ extraction_job_events table created with indexes")

        # ── Step 3: Migrate legacy data ──────────────────────────────────
        # Jobs that are currently 'extracted' but have been approved/rejected
        # don't need migration (approve/reject already wrote the correct status).
        # What we DO need: backfill synthetic audit events for existing jobs.
        logger.info("Step 3: Backfill synthetic audit events for existing jobs")
        result = db.execute(text("""
            INSERT INTO extraction_job_events (job_id, from_state, to_state, actor_type, reason, created_at)
            SELECT
                id,
                NULL,
                status,
                'migration',
                'backfilled by migrate_workflow_v4',
                COALESCE(updated_at, created_at, now())
            FROM extraction_jobs
            WHERE NOT EXISTS (
                SELECT 1 FROM extraction_job_events e WHERE e.job_id = extraction_jobs.id
            )
        """))
        db.commit()
        count = result.rowcount
        logger.info("  ✓ %d synthetic audit events backfilled", count)

        logger.info("Migration complete.")

    except Exception as e:
        db.rollback()
        logger.error("Migration failed: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
