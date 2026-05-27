"""Tests for the Xiaohongshu tag-line formatter."""

from dp_core.tools.writing_tools import _format_tag_line


def test_plain_tags_get_one_hash():
    assert _format_tag_line(["AI", "ML"]) == "#AI, #ML"


def test_already_hashed_tags_are_not_doubled():
    assert _format_tag_line(["#人工智能", "#Transformer"]) == "#人工智能, #Transformer"


def test_mixed_and_blank_tags():
    assert _format_tag_line(["#AI", "ML", "  ", ""]) == "#AI, #ML"


def test_empty():
    assert _format_tag_line([]) == ""
    assert _format_tag_line(None) == ""
