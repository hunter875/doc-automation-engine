"""Pipeline metrics — lightweight in-process counters and timers for observability.

Metrics are collected per-pipeline-run and exposed as a dict.  They can also
be aggregated across runs via the module-level ``global_metrics`` singleton.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)


class PipelineMetrics:
    """Collect counters and timings for a single pipeline run."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._timers: dict[str, float] = {}
        self._active_timers: dict[str, float] = {}

    # ── counters ──────────────────────────────────────────────────────
    def inc(self, name: str, delta: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + delta

    def get_count(self, name: str) -> int:
        return self._counters.get(name, 0)

    # ── timers ────────────────────────────────────────────────────────
    @contextmanager
    def timer(self, name: str) -> Generator[None, None, None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._timers[name] = self._timers.get(name, 0.0) + elapsed_ms

    def record_time(self, name: str, ms: float) -> None:
        self._timers[name] = self._timers.get(name, 0.0) + ms

    def get_time(self, name: str) -> float:
        return self._timers.get(name, 0.0)

    # ── token tracking ────────────────────────────────────────────────
    def add_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.inc("llm_prompt_tokens", prompt_tokens)
        self.inc("llm_completion_tokens", completion_tokens)
        self.inc("llm_total_tokens", prompt_tokens + completion_tokens)
        self.inc("llm_calls")

    # ── snapshot ──────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "timers_ms": {k: round(v, 1) for k, v in self._timers.items()},
        }


class GlobalMetrics:
    """Thread-safe aggregator for metrics across many pipeline runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._timer_totals: dict[str, float] = {}
        self._timer_counts: dict[str, int] = {}
        self._runs: int = 0

    def merge(self, run_metrics: PipelineMetrics) -> None:
        snapshot = run_metrics.to_dict()
        with self._lock:
            self._runs += 1
            for k, v in snapshot["counters"].items():
                self._counters[k] = self._counters.get(k, 0) + v
            for k, v in snapshot["timers_ms"].items():
                self._timer_totals[k] = self._timer_totals.get(k, 0.0) + v
                self._timer_counts[k] = self._timer_counts.get(k, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            avg_timers = {}
            for k, total in self._timer_totals.items():
                count = self._timer_counts.get(k, 1)
                avg_timers[k] = {
                    "total_ms": round(total, 1),
                    "count": count,
                    "avg_ms": round(total / count, 1) if count else 0,
                }
            return {
                "total_runs": self._runs,
                "counters": dict(self._counters),
                "timers": avg_timers,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._timer_totals.clear()
            self._timer_counts.clear()
            self._runs = 0


# Module-level singleton
global_metrics = GlobalMetrics()
