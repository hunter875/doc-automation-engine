"""Tests for SheetRevisionHasher deterministic hashing."""

from __future__ import annotations

import pytest

from app.engines.extraction.sheet_revision_hasher import SheetRevisionHasher


def test_hash_determinism():
    """Same sheet data should produce identical hash."""
    sheet_data = {
        "Sheet1": [
            ["A", "B", "C"],
            ["1", "2", "3"],
            ["4", "5", "6"],
        ],
    }
    hash1 = SheetRevisionHasher.compute_hash(sheet_data)
    hash2 = SheetRevisionHasher.compute_hash(sheet_data)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex length


def test_hash_sensitive_to_content_change():
    """Changing any cell value should change hash."""
    sheet_data1 = {
        "Sheet1": [
            ["A", "B"],
            ["1", "2"],
        ],
    }
    sheet_data2 = {
        "Sheet1": [
            ["A", "B"],
            ["1", "999"],  # changed
        ],
    }
    hash1 = SheetRevisionHasher.compute_hash(sheet_data1)
    hash2 = SheetRevisionHasher.compute_hash(sheet_data2)
    assert hash1 != hash2


def test_hash_ignores_whitespace():
    """Leading/trailing whitespace should be stripped."""
    sheet_data1 = {
        "Sheet1": [
            ["  A  ", "B  "],
            ["  1  ", "  2  "],
        ],
    }
    sheet_data2 = {
        "Sheet1": [
            ["A", "B"],
            ["1", "2"],
        ],
    }
    hash1 = SheetRevisionHasher.compute_hash(sheet_data1)
    hash2 = SheetRevisionHasher.compute_hash(sheet_data2)
    assert hash1 == hash2


def test_hash_orders_worksheets_deterministically():
    """Worksheet order in dict should not affect hash (sorted by name)."""
    sheet_data1 = {
        "SheetA": [["X"]],
        "SheetB": [["Y"]],
    }
    sheet_data2 = {
        "SheetB": [["Y"]],
        "SheetA": [["X"]],
    }
    hash1 = SheetRevisionHasher.compute_hash(sheet_data1)
    hash2 = SheetRevisionHasher.compute_hash(sheet_data2)
    assert hash1 == hash2


def test_hash_treats_empty_cells_as_none():
    """Empty strings and None should be treated equivalently."""
    sheet_data1 = {
        "Sheet1": [
            ["A", ""],
            ["1", None],
        ],
    }
    sheet_data2 = {
        "Sheet1": [
            ["A", None],
            ["1", ""],
        ],
    }
    hash1 = SheetRevisionHasher.compute_hash(sheet_data1)
    hash2 = SheetRevisionHasher.compute_hash(sheet_data2)
    assert hash1 == hash2
