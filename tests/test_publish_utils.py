"""Tests for publishing helpers: content trimming and CJK title width."""

from dp_core.tools.publish_tools import _trim_xiaohongshu_content
from dp_core.publishers.xiaohongshu import XiaohongshuPublisher


def test_trim_noop_when_within_limit():
    text = "short body\n#tag"
    assert _trim_xiaohongshu_content(text, 1000) == text


def test_trim_keeps_trailing_tags_and_title_line():
    body = "x" * 200
    content = f"{body}\n《Some Paper Title》\n#ai #ml"
    trimmed = _trim_xiaohongshu_content(content, 60)
    assert len(trimmed) <= 60
    # The tag/title suffix is preserved even though the body is cut.
    assert "#ai #ml" in trimmed
    assert "《Some Paper Title》" in trimmed


def test_title_width_counts_cjk_as_two(tmp_path):
    pub = XiaohongshuPublisher(cookies_path=str(tmp_path / "c.json"), headless=True)
    assert pub._calculate_title_width("abc") == 3
    assert pub._calculate_title_width("论文") == 4          # 2 CJK chars
    assert pub._calculate_title_width("AI论文") == 6        # 2 ascii + 2 CJK
