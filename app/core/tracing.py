"""Tracing helpers for structured step-level pipeline observability."""

from __future__ import annotations

from functools import wraps
from time import perf_counter
from typing import Any, Callable

from app.core.logger import extract_safe_inputs, log_debug_step


def trace_step(step_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Trace a pipeline step with safe input/output logging and duration.

    Behavior:
    - Logs success with status="success"
    - Logs failure with status="failed" and re-raises
    - Includes trace_id/job_id/retry_count when available on bound self
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self_obj = args[0] if args else None
            start = perf_counter()

            safe_inputs = extract_safe_inputs(func, self_obj, *args[1:], **kwargs)
            job_id = None
            trace_id = None
            retry_count = 0

            if self_obj is not None:
                job_id = getattr(self_obj, "job_id", None)
                trace_id = getattr(self_obj, "trace_id", None)
                retry_count = int(getattr(self_obj, "retry_count", 0) or 0)

            if "job_id" in kwargs and kwargs["job_id"] is not None:
                job_id = kwargs["job_id"]

            try:
                result = func(*args, **kwargs)
                duration_ms = int((perf_counter() - start) * 1000)
                log_debug_step(
                    job_id=str(job_id) if job_id is not None else None,
                    step=step_name,
                    status="success",
                    input_data=safe_inputs,
                    output_data=result,
                    retry_count=retry_count,
                    duration_ms=duration_ms,
                    trace_id=str(trace_id) if trace_id is not None else None,
                )
                return result
            except Exception as exc:
                duration_ms = int((perf_counter() - start) * 1000)
                log_debug_step(
                    job_id=str(job_id) if job_id is not None else None,
                    step=step_name,
                    status="failed",
                    input_data=safe_inputs,
                    output_data=None,
                    error=exc,
                    retry_count=retry_count,
                    duration_ms=duration_ms,
                    trace_id=str(trace_id) if trace_id is not None else None,
                )
                raise

        return wrapper

    return decorator


__all__ = ["trace_step"]
