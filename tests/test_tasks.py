"""Tests for auto_run task builders (search vs. single-paper)."""

import auto_run


def test_search_task_includes_arxiv_and_window():
    t = auto_run.build_search_task(["LLM Agents"], 5, s2_enabled=False)
    assert 'Search arXiv for "LLM Agents" from past 5 days' in t
    assert "Semantic Scholar" not in t  # disabled


def test_search_task_includes_semantic_when_enabled():
    t = auto_run.build_search_task(["RAG"], 3, s2_enabled=True)
    assert "Semantic Scholar" in t


def test_single_paper_task_uses_path_and_skips_search():
    t = auto_run.build_single_paper_task("/tmp/mypaper.pdf")
    assert "/tmp/mypaper.pdf" in t
    assert "Do NOT search" in t
    # no explicit title -> instruct to infer it
    assert "Determine the paper's title" in t


def test_single_paper_task_uses_explicit_title():
    t = auto_run.build_single_paper_task("/tmp/p.pdf", title="Attention Is All You Need")
    assert 'Attention Is All You Need' in t
    assert "Determine the paper's title" not in t
