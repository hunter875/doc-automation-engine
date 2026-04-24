"""Lightweight debug trace helpers for extraction jobs."""

from __future__ import annotations

from typing import Any


def append_debug_trace(
    job: Any,
    step: str,
    status: str,
    error_type: str | None = None,
    max_items: int = 100,
) -> dict[str, str | None]:
    """Append a minimal debug trace entry using immutable JSONB update pattern.

    Uses assignment (`old + [new]`) so SQLAlchemy tracks JSONB changes reliably.
    """
    new_trace: dict[str, str | None] = {
        "step": step,
        "status": status,
        "error_type": error_type,
    }

    current = job.debug_traces or []
    job.debug_traces = (current + [new_trace])[-max_items:]
    return new_trace


__all__ = ["append_debug_trace"]
