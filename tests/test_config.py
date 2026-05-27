"""Tests for the configuration loader (deep merge + dotted lookups)."""

from dp_core.config import Config, DEFAULT_CONFIG


def test_dotted_get_reads_nested_value():
    cfg = Config()
    assert cfg.get("api.provider") == DEFAULT_CONFIG["api"]["provider"]


def test_get_returns_default_for_missing_key():
    cfg = Config()
    assert cfg.get("does.not.exist", "fallback") == "fallback"
    assert cfg.get("api.missing.deep", 42) == 42


def test_deep_merge_overrides_only_given_leaves():
    cfg = Config()
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 20}}
    cfg._deep_merge(base, override)
    assert base == {"a": {"x": 1, "y": 20}, "b": 3}


def test_publish_enabled_defaults_to_false_optin():
    # Automated publishing must be opt-in.
    cfg = Config()
    assert cfg.get("publish.xiaohongshu.enabled") is False
