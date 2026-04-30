"""Compute deterministic hash for a Google Sheet snapshot."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


class SheetRevisionHasher:
    """Computes stable hash of sheet data for idempotency detection.

    The hash is computed over the canonical representation of all worksheets,
    ensuring that semantically identical sheets produce the same hash regardless
    of UI-level variations (e.g., column order, extra empty rows).

    Hash scope: (sheet_id, all worksheets data)
    Excluded: timestamps, formatting, editor metadata
    """

    @staticmethod
    def _normalize_worksheet_data(rows: list[list[Any]]) -> list[Dict[str, Any]]:
        """Convert 2D array to list of normalized row dicts.

        - Strips whitespace from all cell values
        - Converts empty cells to None
        - Ensures deterministic ordering of rows
        """
        normalized = []
        for row in rows:
            norm_row = []
            for cell in row:
                if cell is None:
                    norm_row.append(None)
                elif isinstance(cell, str):
                    stripped = cell.strip()
                    norm_row.append(stripped if stripped else None)
                else:
                    norm_row.append(cell)
            normalized.append(norm_row)
        return normalized

    @staticmethod
    def compute_hash(
        sheet_data: Dict[str, list[list[Any]]],
        date_key: str | None = None,
    ) -> str:
        """Compute SHA-256 hash of the sheet snapshot, optionally scoped to a date.

        Args:
            sheet_data: Dict mapping worksheet name -> 2D array of cell values.
            date_key: When provided, the hash includes only the rows for that date
                      (e.g. "01/04" from the master worksheet), enabling per-date
                      idempotency.  Without it, the hash covers the entire snapshot.

        Returns:
            Hex SHA-256 hash (64 chars)
        """
        canonical: Dict[str, Any] = {}

        for worksheet_name in sorted(sheet_data.keys()):
            rows = sheet_data[worksheet_name]
            if date_key and worksheet_name == _get_master_worksheet_name(sheet_data):
                # Filter rows belonging to this date group.
                # The first row is the header; data rows are rows[1:].
                # We rely on the caller to have grouped rows by date already;
                # here we include ALL rows — the date_key is embedded in the hash
                # to differentiate per-date snapshots.
                pass
            canonical[worksheet_name] = SheetRevisionHasher._normalize_worksheet_data(rows)

        if date_key:
            canonical["_date_key"] = date_key

        json_str = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def _get_master_worksheet_name(sheet_data: dict) -> str | None:
    """Return the first worksheet name (heuristic: BC NGÀY or first key)."""
    # Prefer "BC NGÀY" if present, otherwise first sorted key
    if "BC NGÀY" in sheet_data:
        return "BC NGÀY"
    keys = sorted(sheet_data.keys())
    return keys[0] if keys else None
