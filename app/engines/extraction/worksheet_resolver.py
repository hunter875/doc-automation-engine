"""Production worksheet resolver for KV30 daily data auto-detection."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.engines.extraction.kv30_fixed_mapping import kv30_extract_master_date_key

logger = logging.getLogger(__name__)

# Version marker for runtime diagnostics
DAILY_RESOLVER_VERSION = "v2.0-production-auto-fallback"


def _normalize(text: str) -> str:
    """Normalize Vietnamese text for fuzzy matching."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.lower().strip()


def _is_summary_row(row: list[Any]) -> bool:
    """Detect summary/total rows by keywords."""
    if not row:
        return False
    first_cell = str(row[0]).lower() if row[0] else ""
    keywords = ["thang dau nam", "tháng đầu năm", "tong", "tổng", "luy ke", "lũy kế"]
    return any(kw in first_cell for kw in keywords)


def _count_valid_daily_rows(rows: list[list[Any]]) -> int:
    """Count rows with valid date_key (numeric day/month)."""
    count = 0
    for row in rows:
        if _is_summary_row(row):
            continue
        date_key = kv30_extract_master_date_key(row)
        if date_key:
            count += 1
    return count


def _has_date_header(rows: list[list[Any]]) -> bool:
    """Check if first row contains NGÀY/THÁNG columns."""
    if not rows:
        return False
    header = rows[0]
    if len(header) < 2:
        return False
    col0 = _normalize(str(header[0]))
    col1 = _normalize(str(header[1]))
    return "ngay" in col0 and "thang" in col1


@dataclass
class WorksheetCandidate:
    name: str
    score: int
    valid_daily_rows: int
    has_date_header: bool
    reason: str


def score_worksheet(
    worksheet_name: str,
    rows: list[list[Any]],
    preferred_name: str,
) -> WorksheetCandidate:
    """Score a worksheet for KV30 daily data suitability."""
    score = 0
    reason_parts = []

    # Check header
    has_header = _has_date_header(rows)
    if has_header:
        score += 50
        reason_parts.append("has_date_header")

    # Count valid daily rows
    valid_count = _count_valid_daily_rows(rows)
    score += valid_count * 10
    reason_parts.append(f"{valid_count}_valid_rows")

    # Name matching
    norm_name = _normalize(worksheet_name)
    if "bc" in norm_name and "ngay" in norm_name:
        score += 20
        reason_parts.append("name_match_bc_ngay")

    # Preferred worksheet bonus
    if worksheet_name == preferred_name:
        score += 5
        reason_parts.append("preferred")

    # Penalty for summary-only sheets
    if valid_count == 0 and any(_is_summary_row(row) for row in rows):
        score -= 100
        reason_parts.append("summary_only")

    return WorksheetCandidate(
        name=worksheet_name,
        score=score,
        valid_daily_rows=valid_count,
        has_date_header=has_header,
        reason=", ".join(reason_parts),
    )


def resolve_daily_worksheet(
    preferred_worksheet: str,
    worksheet_data: dict[str, list[list[Any]]],
    all_worksheet_names: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Auto-resolve the correct daily data worksheet.

    Args:
        preferred_worksheet: Configured master worksheet name
        worksheet_data: Already-fetched worksheet data
        all_worksheet_names: All available worksheet names in spreadsheet (for discovery)

    Returns:
        (resolved_worksheet_name, debug_info)

    Raises:
        ValueError: if no valid daily worksheet found
    """
    logger.info(
        "[WorksheetResolver] DAILY_RESOLVER_VERSION=%s | preferred_worksheet=%s | available_worksheets=%s",
        DAILY_RESOLVER_VERSION,
        preferred_worksheet,
        all_worksheet_names or list(worksheet_data.keys()),
    )

    # Try preferred first
    preferred_rows = worksheet_data.get(preferred_worksheet, [])
    logger.info(
        "[WorksheetResolver] Preferred worksheet '%s' has %d rows (preview first 3): %s",
        preferred_worksheet,
        len(preferred_rows),
        [row[:5] for row in preferred_rows[:3]],
    )
    preferred_candidate = score_worksheet(preferred_worksheet, preferred_rows, preferred_worksheet)

    if preferred_candidate.valid_daily_rows > 0:
        logger.info(
            "[WorksheetResolver] Using preferred worksheet '%s' (score=%d, valid_rows=%d)",
            preferred_worksheet,
            preferred_candidate.score,
            preferred_candidate.valid_daily_rows,
        )
        return preferred_worksheet, {
            "preferred_worksheet": preferred_worksheet,
            "resolved_worksheet": preferred_worksheet,
            "resolution_reason": "preferred_has_valid_rows",
            "available_worksheets": all_worksheet_names or list(worksheet_data.keys()),
            "candidate_scores": {preferred_worksheet: preferred_candidate.score},
        }

    # Preferred failed, try fallbacks
    logger.warning(
        "[WorksheetResolver] Preferred worksheet '%s' has no valid daily rows (score=%d). Trying fallbacks...",
        preferred_worksheet,
        preferred_candidate.score,
    )

    candidates: list[WorksheetCandidate] = [preferred_candidate]

    # Build candidate list: worksheets matching "bc" + "ngay" pattern
    for ws_name, ws_rows in worksheet_data.items():
        if ws_name == preferred_worksheet:
            continue
        norm_name = _normalize(ws_name)
        if "bc" in norm_name and "ngay" in norm_name:
            candidate = score_worksheet(ws_name, ws_rows, preferred_worksheet)
            candidates.append(candidate)

    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Pick best candidate with valid_daily_rows > 0
    best = next((c for c in candidates if c.valid_daily_rows > 0), None)

    if best:
        logger.info(
            "[WorksheetResolver] ✅ Resolved to worksheet '%s' (score=%d, valid_rows=%d, reason=%s) | candidate_scores=%s",
            best.name,
            best.score,
            best.valid_daily_rows,
            best.reason,
            {c.name: c.score for c in candidates},
        )
        debug_info = {
            "preferred_worksheet": preferred_worksheet,
            "resolved_worksheet": best.name,
            "resolution_reason": "fallback_auto_detected",
            "available_worksheets": all_worksheet_names or list(worksheet_data.keys()),
            "candidate_scores": {c.name: c.score for c in candidates},
            "candidates_checked": [
                {
                    "name": c.name,
                    "score": c.score,
                    "valid_daily_rows": c.valid_daily_rows,
                    "has_date_header": c.has_date_header,
                    "reason": c.reason,
                }
                for c in candidates
            ],
        }
        return best.name, debug_info

    # No valid worksheet found
    available_worksheets = all_worksheet_names or list(worksheet_data.keys())
    logger.error(
        "[WorksheetResolver] No valid daily worksheet found. Available: %s. Candidates: %s",
        available_worksheets,
        [(c.name, c.score, c.valid_daily_rows) for c in candidates],
    )

    debug_info = {
        "preferred_worksheet": preferred_worksheet,
        "resolved_worksheet": None,
        "resolution_reason": "no_valid_worksheet_found",
        "available_worksheets": available_worksheets,
        "candidate_scores": {c.name: c.score for c in candidates},
        "candidates_checked": [
            {
                "name": c.name,
                "score": c.score,
                "valid_daily_rows": c.valid_daily_rows,
                "has_date_header": c.has_date_header,
                "reason": c.reason,
                "preview": [row[:5] for row in worksheet_data.get(c.name, [])[:3]],
            }
            for c in candidates
        ],
    }

    raise ValueError(
        f"NO_VALID_DAILY_ROWS: Không tìm thấy tab daily hợp lệ. "
        f"Preferred worksheet: '{preferred_worksheet}'. "
        f"Đã thử các tab: {available_worksheets}. "
        f"Checked {len(candidates)} candidates. "
        f"Debug: {debug_info}"
    )
