"""Tests for worksheet_resolver auto-resolution logic."""

from __future__ import annotations

from typing import Any

import pytest

from app.engines.extraction.worksheet_resolver import (
    WorksheetCandidate,
    resolve_daily_worksheet,
    score_worksheet,
)

# Helper: Build simple KV30-style rows with numeric day/month
def make_bc_rows(day_month_rows: list[tuple[float, float]]) -> list[list[Any]]:
    """Create rows where col0=day, col1=month, plus placeholder cols."""
    header = ["NGAY", "THANG", "VU CHAY", "SCLQ", "CNCH", "CHI VIEN"]
    rows = [header]
    for day, month in day_month_rows:
        rows.append([day, month, 0.0, 0.0, 0.0, 0.0])
    return rows

def make_summary_rows() -> list[list[Any]]:
    return [
        ["06 thang dau nam", "", "6.0", "0.0"],
        ["tong", "", "100.0", "50.0"],
    ]

class TestScoreWorksheet:
    """Unit tests for scoring logic."""

    def test_scores_preferred_bonus(self):
        rows = make_bc_rows([(1.0, 3.0)])
        cand = score_worksheet("BC NGAY", rows, "BC NGAY")
        assert cand.score >= 20 + 10 + 5  # name_match (20) + 1 valid row * 10 + preferred (5)

    def test_scores_valid_rows_multiplier(self):
        rows = make_bc_rows([(1.0, 3.0), (2.0, 3.0), (3.0, 3.0)])
        cand = score_worksheet("BC NGAY", rows, "OTHER")
        # Score includes: header (+50) + 3 valid rows * 10 + name match (+20) = 100
        assert cand.score == 100

    def test_penalizes_summary_only(self):
        rows = make_summary_rows()
        cand = score_worksheet("BC NGAY", rows, "BC NGAY")
        assert cand.valid_daily_rows == 0
        assert cand.score < 0

    def test_has_date_header_detection(self):
        header = ["NGÀY", "THÁNG", "VU CHAY"]
        rows = [header] + make_bc_rows([(1.0, 3.0)])[1:]
        cand = score_worksheet("BC NGAY 1", rows, "BC NGAY")
        assert cand.has_date_header is True

    def test_lacks_date_header_if_different_names(self):
        header = ["A", "B", "C"]
        rows = [header] + make_bc_rows([(1.0, 3.0)])[1:]
        cand = score_worksheet("BC NGAY 1", rows, "BC NGAY")
        assert cand.has_date_header is False

class TestResolveDailyWorksheet:
    """Integration tests for resolution."""

    def test_preferred_with_valid_rows_is_used(self):
        data = {"BC NGAY": make_bc_rows([(1.0, 3.0), (2.0, 3.0)])}
        resolved, debug = resolve_daily_worksheet("BC NGAY", data)
        assert resolved == "BC NGAY"
        assert debug["resolution_reason"] == "preferred_has_valid_rows"

    def test_fallback_to_bc_ngay_1_when_preferred_summary_only(self):
        # Preferred is summary-only; fallback has valid rows
        data = {
            "BC NGAY": make_summary_rows(),
            "BC NGAY 1": make_bc_rows([(1.0, 3.0), (2.0, 3.0)]),
        }
        resolved, debug = resolve_daily_worksheet("BC NGAY", data)
        assert resolved == "BC NGAY 1"
        assert debug["resolution_reason"] == "fallback_auto_detected"
        assert debug["candidate_scores"]["BC NGAY 1"] > debug["candidate_scores"]["BC NGAY"]

    def test_selects_candidate_with_most_valid_rows(self):
        data = {
            "BC NGAY": make_summary_rows(),
            "BC NGAY 1": make_bc_rows([(1.0, 3.0)]),
            "BC NGAY 2": make_bc_rows([(1.0, 3.0), (2.0, 3.0), (3.0, 3.0)]),
        }
        resolved, debug = resolve_daily_worksheet("BC NGAY", data)
        assert resolved == "BC NGAY 2"
        assert debug["candidates_checked"][0]["valid_daily_rows"] == 3

    def test_raises_when_no_valid_worksheet(self):
        data = {
            "BC NGAY": make_summary_rows(),
            "OTHER": [["A", "B"]],
        }
        with pytest.raises(ValueError) as exc:
            resolve_daily_worksheet("BC NGAY", data, all_worksheet_names=["BC NGAY", "OTHER"])
        msg = str(exc.value)
        assert "NO_VALID_DAILY_ROWS" in msg
        assert "Đã thử các tab" in msg

    def test_normalize_accent_insensitive(self):
        # "BC NGÀY" with accent should match pattern
        rows = make_bc_rows([(1.0, 3.0)])
        data = {"BC NGÀY": rows}
        # Directly call resolver; it should consider accent-insensitive match
        resolved, debug = resolve_daily_worksheet("BC NGAY", data)
        # The candidate list should include BC NGÀY because it's in worksheet_data keys
        cand_names = [c["name"] for c in debug["candidates_checked"]]
        assert "BC NGÀY" in cand_names

    def test_includes_all_available_worksheets_in_debug(self):
        data = {
            "Sheet1": make_summary_rows(),
            "Sheet2": make_summary_rows(),
            "BC NGAY": make_summary_rows(),
        }
        with pytest.raises(ValueError) as exc:
            resolve_daily_worksheet("BC NGAY", data, all_worksheet_names=["Sheet1", "Sheet2", "BC NGAY", "BC NGÀY 1"])
        assert "available_worksheets" in str(exc.value)

    def test_resolver_returns_debug_with_candidates_checked(self):
        data = {
            "BC NGAY": make_summary_rows(),
            "BC NGAY 1": make_bc_rows([(1.0, 3.0)]),
        }
        resolved, debug = resolve_daily_worksheet("BC NGAY", data)
        assert "candidates_checked" in debug
        assert len(debug["candidates_checked"]) == 2
        assert debug["candidates_checked"][0]["name"] == "BC NGAY 1"
