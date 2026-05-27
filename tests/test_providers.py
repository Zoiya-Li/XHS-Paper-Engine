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
    for name in ["siliconflow", "dashscope", "moonshot", "zhipu"]:
        assert name in PROVIDERS


def test_text_only_providers_not_listed():
    # VL is required, so text-only providers (e.g. DeepSeek) must not be offered.
    assert "deepseek" not in PROVIDERS


def test_every_provider_is_vl_capable():
    # Every listed provider must serve a vision model.
    for name, meta in PROVIDERS.items():
        assert meta.get("vision") is True, f"{name} is not VL-capable but is listed"


def test_vl_providers_have_a_vision_model_example():
    for name, meta in PROVIDERS.items():
        if name != "custom":
            assert meta.get("vision_model"), f"{name} is VL-capable but has no example vision_model"


def test_unknown_provider_falls_back(monkeypatch):
    client = _client_with(monkeypatch, "totally-made-up")
    assert client.provider == DEFAULT_PROVIDER


def test_selected_provider_resolves_key_and_url(monkeypatch):
    client = _client_with(monkeypatch, "zhipu", ZHIPU_API_KEY="sk-real-zhipu")
    assert client.provider == "zhipu"
    assert client._get_api_key("zhipu") == "sk-real-zhipu"
    assert client._get_base_url("zhipu") == "https://open.bigmodel.cn/api/paas/v4"


def test_vision_endpoint_uses_active_provider(monkeypatch):
    client = _client_with(monkeypatch, "dashscope", DASHSCOPE_API_KEY="sk-qwen")
    ep = client.get_vision_endpoint()
    assert ep["provider"] == "dashscope"
    assert ep["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_headers_use_provider_key(monkeypatch):
    client = _client_with(monkeypatch, "moonshot", MOONSHOT_API_KEY="sk-kimi")
    headers = client._get_headers("moonshot")
    assert headers["Authorization"] == "Bearer sk-kimi"


def test_missing_key_raises_clear_error(monkeypatch):
    client = _client_with(monkeypatch, "zhipu")  # no key set
    with pytest.raises(ValueError) as exc:
        client._get_headers("zhipu")
    assert "ZHIPU_API_KEY" in str(exc.value)
