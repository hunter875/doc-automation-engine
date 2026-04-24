"""Single source of truth for ExtractionJob lifecycle.

ALL job state mutations MUST go through ``transition_job_state()``.
Workers, API handlers, and services are forbidden from writing
``job.status`` directly.

This module owns:
  1. The canonical state enum and transition map.
  2. The transition function (with row-level locking).
  3. The audit log writer (extraction_job_events).
  4. Domain event emission for downstream consumers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingError
from app.infrastructure.db.session import Base

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# 1. CANONICAL STATUS ENUM
# ══════════════════════════════════════════════════════════════════════════════

class JobStatus:
    """Single authoritative lifecycle state for ExtractionJob.

    Replaces both ExtractionJobStatus and EnrichmentStatus.

    State machine::

        PENDING ─→ PROCESSING ─→ EXTRACTED ─→ ENRICHING ─→ READY_FOR_REVIEW
                       │              │            │               │
                       ↓              ↓            ↓               ↓
                     FAILED        FAILED       FAILED          APPROVED
                                                                   │
                                                                   ↓
                                     ← ── ── REJECTED         AGGREGATED

        FAILED / REJECTED ─→ PENDING  (retry)

    EXTRACTED is a transient state:
      • Block mode: auto-transitions to ENRICHING (if CNCH text) or READY_FOR_REVIEW (if not)
      • Hybrid/Gemini mode: auto-transitions to READY_FOR_REVIEW (no enrichment)
    """

    PENDING = "pending"
    PROCESSING = "processing"
    EXTRACTED = "extracted"           # Stage 1 done — transient
    ENRICHING = "enriching"           # LLM enrichment in progress
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    AGGREGATED = "aggregated"
    FAILED = "failed"

    ALL = [
        PENDING, PROCESSING, EXTRACTED, ENRICHING,
        READY_FOR_REVIEW, APPROVED, REJECTED, AGGREGATED, FAILED,
    ]

    # States that indicate "done processing, can be shown to user"
    TERMINAL = {READY_FOR_REVIEW, APPROVED, REJECTED, AGGREGATED, FAILED}

    # States safe for deletion
    DELETABLE = {READY_FOR_REVIEW, APPROVED, REJECTED, AGGREGATED, FAILED}


# ══════════════════════════════════════════════════════════════════════════════
# 2. TRANSITION MAP — each key maps to the set of valid next states.
# ══════════════════════════════════════════════════════════════════════════════

VALID_TRANSITIONS: dict[str, set[str]] = {
    JobStatus.PENDING:          {JobStatus.PROCESSING, JobStatus.FAILED},
    JobStatus.PROCESSING:       {JobStatus.EXTRACTED, JobStatus.FAILED},
    JobStatus.EXTRACTED:        {JobStatus.ENRICHING, JobStatus.READY_FOR_REVIEW, JobStatus.FAILED},
    JobStatus.ENRICHING:        {JobStatus.READY_FOR_REVIEW, JobStatus.FAILED},
    JobStatus.READY_FOR_REVIEW: {JobStatus.APPROVED, JobStatus.REJECTED},
    JobStatus.APPROVED:         {JobStatus.AGGREGATED},
    JobStatus.REJECTED:         {JobStatus.PENDING},   # retry
    JobStatus.AGGREGATED:       set(),                  # terminal
    JobStatus.FAILED:           {JobStatus.PENDING},    # retry
}

# Backward compat: map old status values to new ones for DB migration
_LEGACY_STATUS_MAP = {
    "extracted": JobStatus.READY_FOR_REVIEW,  # old "extracted" means "ready for review"
}


# ══════════════════════════════════════════════════════════════════════════════
# 3. AUDIT LOG MODEL
# ══════════════════════════════════════════════════════════════════════════════

class ExtractionJobEvent(Base):
    """Append-only audit log for every job state transition."""

    __tablename__ = "extraction_job_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_state = Column(String(30), nullable=True)
    to_state = Column(String(30), nullable=False)
    actor_type = Column(String(20), nullable=False)   # 'worker', 'api', 'system'
    actor_id = Column(String(255), nullable=True)      # user_id or worker hostname
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Event {self.from_state}→{self.to_state} job={self.job_id}>"


# ══════════════════════════════════════════════════════════════════════════════
# 4. DOMAIN EVENTS — lightweight in-process event bus
# ══════════════════════════════════════════════════════════════════════════════

class JobEvent:
    """Immutable domain event emitted after a successful state transition."""

    __slots__ = ("job_id", "from_state", "to_state", "actor_type", "actor_id",
                 "reason", "timestamp", "metadata")

    def __init__(
        self,
        job_id: str,
        from_state: str | None,
        to_state: str,
        actor_type: str,
        actor_id: str | None,
        reason: str | None,
        metadata: dict[str, Any] | None = None,
    ):
        self.job_id = job_id
        self.from_state = from_state
        self.to_state = to_state
        self.actor_type = actor_type
        self.actor_id = actor_id
        self.reason = reason
        self.timestamp = datetime.utcnow()
        self.metadata = metadata or {}


# Simple synchronous event bus.  Handlers registered at app startup.
_event_handlers: list = []


def register_event_handler(handler) -> None:
    """Register a callable(JobEvent) to run after each transition."""
    _event_handlers.append(handler)


def _emit(event: JobEvent) -> None:
    for handler in _event_handlers:
        try:
            handler(event)
        except Exception:
            logger.exception("Event handler failed for %s", event)


# ══════════════════════════════════════════════════════════════════════════════
# 5. THE TRANSITION FUNCTION — single entry point for all status changes
# ══════════════════════════════════════════════════════════════════════════════

def transition_job_state(
    db: Session,
    *,
    job_id: str,
    to_state: str,
    actor_type: str,
    actor_id: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    allow_same: bool = False,
) -> "ExtractionJob":   # noqa: F821 — forward ref resolved at runtime
    """Atomically transition a job to a new state.

    1. SELECT ... FOR UPDATE (row-level lock).
    2. Validate transition against VALID_TRANSITIONS.
    3. Update job.status + job.updated_at.
    4. Write audit event to extraction_job_events.
    5. Commit.
    6. Emit domain event (post-commit, best-effort).

    Args:
        db: SQLAlchemy session.
        job_id: UUID of the extraction job.
        to_state: Target state from JobStatus.
        actor_type: 'worker', 'api', or 'system'.
        actor_id: Identifier of the actor (user UUID or worker hostname).
        reason: Human-readable reason for the transition.
        metadata: Optional dict stored on the domain event (not persisted).
        allow_same: If True, no-op when job is already in to_state (idempotent).

    Returns:
        The updated ExtractionJob instance (attached to ``db``).

    Raises:
        ProcessingError: If the transition is invalid or the job is not found.
    """
    from app.domain.models.extraction_job import ExtractionJob

    # 1. Lock the row
    job = (
        db.query(ExtractionJob)
        .filter(ExtractionJob.id == job_id)
        .with_for_update()
        .first()
    )
    if job is None:
        raise ProcessingError(message=f"Job {job_id} not found")

    from_state = job.status

    # 2. Idempotent shortcut
    if from_state == to_state:
        if allow_same:
            return job
        raise ProcessingError(
            message=f"Job {job_id} is already in state '{to_state}'"
        )

    # 3. Validate transition
    allowed = VALID_TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise ProcessingError(
            message=(
                f"Invalid transition: {from_state} → {to_state} "
                f"for job {str(job_id)[:8]}. "
                f"Allowed from '{from_state}': {sorted(allowed) or 'none (terminal state)'}"
            )
        )

    # 4. Write state
    job.status = to_state
    now = datetime.utcnow()
    job.updated_at = now

    # Lifecycle timestamps
    if to_state == JobStatus.FAILED:
        job.completed_at = job.completed_at or now
    elif to_state == JobStatus.PENDING:
        # Retry — clear completed_at
        job.completed_at = None

    # 5. Audit event
    event_row = ExtractionJobEvent(
        job_id=job.id,
        from_state=from_state,
        to_state=to_state,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
        created_at=now,
    )
    db.add(event_row)

    # 6. Commit both changes atomically
    db.flush()

    # 7. Emit domain event (non-critical — failures logged, not raised)
    domain_event = JobEvent(
        job_id=str(job.id),
        from_state=from_state,
        to_state=to_state,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
        metadata=metadata,
    )
    _emit(domain_event)

    logger.info(
        "Job %s transitioned %s → %s (actor=%s/%s reason=%s)",
        str(job.id)[:8], from_state, to_state, actor_type, actor_id, reason,
    )
    return job
