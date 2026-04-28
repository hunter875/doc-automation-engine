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
    ) -> str:
        """Compute SHA-256 hash of the entire sheet snapshot.

        Args:
            sheet_data: Dict mapping worksheet name -> 2D array of cell values

        Returns:
            Hex SHA-256 hash (64 chars)

        Example:
            {
                "BC NGÀY": [[...], [...]],
                "VỤ CHÁY": [[...], [...]],
                "CNCH": [[...], [...]],
                "CHI VIỆN": [[...], [...]]
            }
        """
        # Build canonical structure
        canonical: Dict[str, Any] = {}
        for worksheet_name in sorted(sheet_data.keys()):
            rows = sheet_data[worksheet_name]
            canonical[worksheet_name] = SheetRevisionHasher._normalize_worksheet_data(rows)

        # Deterministic JSON serialization
        json_str = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
