"""Tests for multi-provider resolution in APIClient."""

import pytest

from dp_core.api_client import APIClient, PROVIDERS, DEFAULT_PROVIDER


def _client_with(monkeypatch, provider, **env):
    # Force the provider and a clean env, then build a client.
    monkeypatch.setattr("dp_core.api_client.config.get",
                        lambda key, default=None: provider if key == "api.provider" else default)
    for k in (m["api_key_env"] for m in PROVIDERS.values()):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return APIClient()


def test_all_providers_have_required_fields():
    for name, meta in PROVIDERS.items():
        assert "base_url" in meta and "api_key_env" in meta and "label" in meta
        # only "custom" is allowed to ship without a built-in base_url
        if name != "custom":
            assert meta["base_url"].startswith("http")


def test_chinese_providers_present():
    for name in ["siliconflow", "deepseek", "dashscope", "moonshot", "zhipu", "ark", "hunyuan"]:
        assert name in PROVIDERS


def test_unknown_provider_falls_back(monkeypatch):
    client = _client_with(monkeypatch, "totally-made-up")
    assert client.provider == DEFAULT_PROVIDER


def test_selected_provider_resolves_key_and_url(monkeypatch):
    client = _client_with(monkeypatch, "deepseek", DEEPSEEK_API_KEY="sk-real-deepseek")
    assert client.provider == "deepseek"
    assert client._get_api_key("deepseek") == "sk-real-deepseek"
    assert client._get_base_url("deepseek") == "https://api.deepseek.com/v1"


def test_headers_use_provider_key(monkeypatch):
    client = _client_with(monkeypatch, "moonshot", MOONSHOT_API_KEY="sk-kimi")
    headers = client._get_headers("moonshot")
    assert headers["Authorization"] == "Bearer sk-kimi"


def test_missing_key_raises_clear_error(monkeypatch):
    client = _client_with(monkeypatch, "zhipu")  # no key set
    with pytest.raises(ValueError) as exc:
        client._get_headers("zhipu")
    assert "ZHIPU_API_KEY" in str(exc.value)
