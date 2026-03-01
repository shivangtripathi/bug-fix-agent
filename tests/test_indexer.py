"""Smoke test for RepoIndexer (no LLM required)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Ensure we can import from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.indexing import RepoIndexer


@pytest.fixture()
def tiny_repo(tmp_path: Path) -> Path:
    """Create a minimal Python repo for testing."""
    (tmp_path / "sample.py").write_text(
        """
def add(a, b):
    '''Return the sum of a and b.'''
    return a + b


def subtract(a, b):
    '''Return a minus b.'''
    return a - b


class Calculator:
    def multiply(self, a, b):
        return a * b
""",
        encoding="utf-8",
    )
    return tmp_path


def test_indexer_builds_collection(tiny_repo: Path):
    indexer = RepoIndexer(str(tiny_repo))
    assert indexer._collection.count() > 0, "Collection should not be empty after indexing"


def test_indexer_returns_hits(tiny_repo: Path):
    indexer = RepoIndexer(str(tiny_repo))
    hits = indexer.query("addition of two numbers", n_results=3)
    assert len(hits) > 0, "Expected at least one hit"
    first = hits[0]
    assert "file" in first
    assert "start_line" in first
    assert "snippet" in first
    assert "distance" in first


def test_indexer_hit_contains_relevant_code(tiny_repo: Path):
    indexer = RepoIndexer(str(tiny_repo))
    hits = indexer.query("multiply", n_results=5)
    snippets = [h["snippet"] for h in hits]
    assert any("multiply" in s for s in snippets), (
        "Expected a hit containing 'multiply'"
    )


def test_indexer_idempotent(tiny_repo: Path):
    """Calling RepoIndexer twice should not duplicate documents."""
    indexer1 = RepoIndexer(str(tiny_repo))
    count1 = indexer1._collection.count()

    indexer2 = RepoIndexer(str(tiny_repo))
    count2 = indexer2._collection.count()

    assert count1 == count2, "Re-indexing should not add duplicate chunks"


def test_query_empty_string(tiny_repo: Path):
    indexer = RepoIndexer(str(tiny_repo))
    hits = indexer.query("")
    assert hits == [], "Empty query string should return no hits"
