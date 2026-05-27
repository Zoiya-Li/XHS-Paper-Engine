"""Tests for paper deduplication helpers (title normalization + arXiv id)."""

import pytest

from dp_core.dedup import PaperDeduplicator


@pytest.fixture
def dedup(tmp_path):
    # Use a throwaway sqlite db so tests never touch the real analytics db.
    return PaperDeduplicator(db_path=tmp_path / "analytics.db")


def test_normalize_title_lowercases_and_strips_punct(dedup):
    assert dedup._normalize_title("Attention Is All You Need!") == "attention is all you need"
    assert dedup._normalize_title("  Multi--Agent   Memory  ") == "multiagent memory"


def test_title_similarity_identical_is_one(dedup):
    a = dedup._normalize_title("Deep Residual Learning")
    assert dedup._title_similarity(a, a) == 1.0


def test_title_similarity_different_is_low(dedup):
    a = dedup._normalize_title("Deep Residual Learning")
    b = dedup._normalize_title("Generative Adversarial Networks")
    assert dedup._title_similarity(a, b) < 0.5


def test_extract_arxiv_id_from_field(dedup):
    assert dedup._extract_arxiv_id({"arxiv_id": "2401.12345"}) == "2401.12345"


def test_extract_arxiv_id_from_link(dedup):
    paper = {"link": "https://arxiv.org/abs/2401.12345"}
    assert dedup._extract_arxiv_id(paper) == "2401.12345"


def test_extract_arxiv_id_none_when_absent(dedup):
    assert dedup._extract_arxiv_id({"title": "no id here"}) is None
