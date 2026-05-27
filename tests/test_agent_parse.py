"""Tests for ReActAgent._parse_response (the text protocol parser)."""

import pytest

from dp_core.agent import ReActAgent


@pytest.fixture
def agent(tmp_path):
    return ReActAgent(work_dir=str(tmp_path / "work"), output_dir=str(tmp_path / "out"), verbose=False)


def test_parses_thought_and_action(agent):
    resp = 'Thought: I should search.\nAction: {"tool": "search_papers", "args": {"query": "LLM"}}'
    thought, name, args, final = agent._parse_response(resp)
    assert "search" in thought.lower()
    assert name == "search_papers"
    assert args == {"query": "LLM"}
    assert final is None


def test_parses_final_answer(agent):
    resp = "Thought: done\nFinal Answer: All set."
    thought, name, args, final = agent._parse_response(resp)
    assert final == "All set."
    assert name is None


def test_truncates_fabricated_observation(agent):
    # The model must not invent an Observation; everything after it is dropped.
    resp = (
        'Thought: go\nAction: {"tool": "download_paper", "args": {"arxiv_id": "1"}}\n'
        'Observation: {"fake": true}'
    )
    thought, name, args, final = agent._parse_response(resp)
    assert name == "download_paper"
    assert args == {"arxiv_id": "1"}


def test_parses_nested_json_args(agent):
    resp = 'Action: {"tool": "t", "args": {"a": {"b": [1, 2]}, "c": "x"}}'
    _, name, args, _ = agent._parse_response(resp)
    assert name == "t"
    assert args == {"a": {"b": [1, 2]}, "c": "x"}


def test_no_action_returns_none(agent):
    thought, name, args, final = agent._parse_response("Thought: just thinking out loud")
    assert name is None and final is None
