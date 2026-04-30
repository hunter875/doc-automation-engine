"""Header row detection for spreadsheet ingestion."""

from __future__ import annotations

import unicodedata


def _normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).strip().lower()
    # Collapse spaces (no diacritics removal — NFC form preserves diacritics)
    return " ".join(text.split())


def detect_header_row(
    rows: list[list[str]],
    *,
    known_aliases: set[str],
    scan_limit: int = 15,
) -> tuple[int, list[str]]:
    """Detect header row by maximal alias overlap in top rows.

    Scans rows looking for the row with the most schema alias matches.
    Falls back to row 0 if no row contains strings (data rows only).
    """
    if not rows:
        return 0, []

    normalized_aliases = {_normalize_key(item) for item in known_aliases if str(item).strip()}

    best_idx = 0
    best_score = -1
    has_strings = False  # track if any row has string column headers

    limit = min(len(rows), max(1, scan_limit))
    for idx in range(limit):
        header = rows[idx] or []
        # Check if this row has string column headers
        has_str = any(isinstance(col, str) and str(col).strip() for col in header)
        if has_str:
            has_strings = True
            score = sum(
                1
                for col in header
                if isinstance(col, str) and _normalize_key(col) in normalized_aliases
            )
            if score > best_score:
                best_score = score
                best_idx = idx

    # If no row had string column headers, fall back to row 0
    if not has_strings:
        return 0, [str(col).strip() for col in (rows[0] or [])]

    detected = [str(col).strip() for col in (rows[best_idx] or [])]
    return best_idx, detected
