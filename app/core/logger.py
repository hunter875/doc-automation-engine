"""Production-safe structured logging helpers for extraction pipelines."""

from __future__ import annotations

import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

try:
    from requests import RequestException
except Exception:  # pragma: no cover - requests might be optional
    class RequestException(Exception):
        """Fallback request exception when requests is unavailable."""


logger = logging.getLogger(__name__)

_MAX_LOG_CHARS = 1000


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that protects logs from unsafe/non-serializable payloads."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, bytes):
            size = len(obj)
            return f"[bytes:{size}](bytes:{size})"

        if isinstance(obj, BaseModel):
            return obj.model_dump(exclude_none=True)

        try:
            return super().default(obj)
        except TypeError:
            class_name = obj.__class__.__name__ if hasattr(obj, "__class__") else "Unknown"
            if class_name and class_name != "str":
                return f"[object:{class_name}](object:{class_name})"
            return str(obj)


def _clip_text(value: str, max_chars: int = _MAX_LOG_CHARS) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def safe_serialize(data: Any, max_chars: int = _MAX_LOG_CHARS) -> str:
    """Safely serialize any data into a bounded JSON string.

    - Never raises
    - Uses custom encoder for bytes/BaseModel/arbitrary objects
    - Truncates oversized output
    """
    try:
        serialized = json.dumps(
            data,
            cls=SafeJSONEncoder,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except Exception as exc:
        fallback = {
            "serialization_error": str(exc),
            "payload_preview": _clip_text(str(data), max_chars=max_chars),
        }
        try:
            return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return "{\"serialization_error\":\"unknown\"}"

    if len(serialized) <= max_chars:
        return serialized

    truncated_payload = {
        "truncated": True,
        "original_length": len(serialized),
        "preview": _clip_text(serialized, max_chars=max_chars),
    }
    try:
        return json.dumps(truncated_payload, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{\"truncated\":true}"


def _safe_value_for_input(value: Any) -> Any:
    if isinstance(value, bytes):
        size = len(value)
        return f"[bytes:{size}](bytes:{size})"
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _safe_value_for_input(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value_for_input(v) for v in value]
    class_name = value.__class__.__name__ if hasattr(value, "__class__") else "Unknown"
    return f"[object:{class_name}](object:{class_name})"


def extract_safe_inputs(
    func: Callable[..., Any],
    self_obj: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Extract function inputs for logs while removing self and unsafe payloads."""
    del self_obj

    try:
        signature = inspect.signature(func)
        bound = signature.bind_partial(None, *args, **kwargs)
        result: dict[str, Any] = {}
        for key, value in bound.arguments.items():
            if key == "self":
                continue
            result[key] = _safe_value_for_input(value)
        return result
    except Exception:
        fallback: dict[str, Any] = {}
        if args:
            fallback["args"] = [_safe_value_for_input(item) for item in args]
        if kwargs:
            fallback["kwargs"] = {k: _safe_value_for_input(v) for k, v in kwargs.items()}
        return fallback


def classify_error(error: Exception | None) -> str | None:
    """Classify error using exception types first, then fallback text matching."""
    if error is None:
        return None

    if isinstance(error, ValidationError):
        return "AI_OR_DATA_ERROR"

    if isinstance(error, (RequestException, TimeoutError)):
        return "SYSTEM_ERROR"

    text = str(error).lower()
    if any(token in text for token in ("validation", "schema", "pydantic", "json")):
        return "AI_OR_DATA_ERROR"
    if any(token in text for token in ("timeout", "connection", "rate limit", "503", "502", "network")):
        return "SYSTEM_ERROR"

    if isinstance(error, Exception):
        return "LOGIC_ERROR"

    return "UNKNOWN_ERROR"


def log_debug_step(
    *,
    job_id: str | None,
    step: str,
    status: str,
    input_data: Any = None,
    output_data: Any = None,
    error: Exception | None = None,
    retry_count: int = 0,
    duration_ms: int | float | None = None,
    trace_id: str | None = None,
) -> None:
    """Emit a structured JSON log for a pipeline step."""
    payload = {
        "trace_id": trace_id,
        "job_id": job_id,
        "step": step,
        "status": status,
        "input": _safe_value_for_input(input_data),
        "output": _safe_value_for_input(output_data),
        "error": str(error) if error is not None else None,
        "error_type": classify_error(error),
        "retry_count": retry_count,
        "duration_ms": duration_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    message = safe_serialize(payload)

    if status == "failed" or error is not None:
        logger.error(message)
    else:
        logger.info(message)


__all__ = [
    "SafeJSONEncoder",
    "safe_serialize",
    "extract_safe_inputs",
    "classify_error",
    "log_debug_step",
]
