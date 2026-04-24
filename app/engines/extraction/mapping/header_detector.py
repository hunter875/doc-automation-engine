"""Header row detection for spreadsheet ingestion."""

from __future__ import annotations

import unicodedata


def _normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).strip().lower()
    return " ".join(text.split())


def detect_header_row(
    rows: list[list[str]],
    *,
    known_aliases: set[str],
    scan_limit: int = 15,
) -> tuple[int, list[str]]:
    """Detect header row by maximal alias overlap in top rows."""
    if not rows:
        return 0, []

    normalized_aliases = {_normalize_key(item) for item in known_aliases if str(item).strip()}
    best_idx = 0
    best_score = -1

    limit = min(len(rows), max(1, scan_limit))
    for idx in range(limit):
        header = rows[idx] or []
        score = sum(1 for col in header if _normalize_key(col) in normalized_aliases)
        if score > best_score:
            best_score = score
            best_idx = idx

    detected = [str(col).strip() for col in (rows[best_idx] or [])]
    return best_idx, detected
