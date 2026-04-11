"""
Migration: Add filename_pattern column to extraction_templates table.

This column stores an optional regex pattern used to auto-match uploaded
filenames to a template — enabling the "drop files → auto report" flow.

Usage:
    python scripts/migrate_add_filename_pattern.py

Idempotent — safely skips if column already exists.
New deployments via Base.metadata.create_all() include it automatically.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ALTER_STATEMENTS = [
    """
    ALTER TABLE extraction_templates
        ADD COLUMN IF NOT EXISTS filename_pattern VARCHAR(500);
    """,
    """
    COMMENT ON COLUMN extraction_templates.filename_pattern IS
        'Regex pattern to auto-match uploaded filenames to this template. NULL = no auto-matching.';
    """,
]


def run_migration() -> None:
    from app.infrastructure.db.session import engine

    with engine.connect() as conn:
        for stmt in ALTER_STATEMENTS:
            clean = stmt.strip()
            logger.info("Running: %s", clean[:80].replace("\n", " "))
            conn.execute(text(clean))
            conn.commit()
    logger.info("Migration complete — filename_pattern column added to extraction_templates.")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        sys.exit(1)
