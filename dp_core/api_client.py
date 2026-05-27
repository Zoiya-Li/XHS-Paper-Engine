"""
API Client - Unified API call client

Using SiliconFlow or OpenRouter for text models:
- deepseek-ai/DeepSeek-V3: General dialogue (Agent reasoning, content generation)
"""

import os
from pathlib import Path
import requests
from typing import List, Dict, Any, Optional

# Automatically load .env file
from dotenv import load_dotenv

# Find and load .env file
_env_paths = [
    Path(__file__).parent.parent / ".env",  # XHS Paper Engine/.env
    Path.cwd() / ".env",  # Current directory
]
for _env_path in _env_paths:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

from .retry import call_api_with_retry
from .config import config


# ---------------------------------------------------------------------------
# Supported LLM providers.
#
# Every provider below exposes an OpenAI-compatible /chat/completions endpoint,
# so adding a new one is just another row here (base_url + api_key_env). Most are
# Chinese suppliers. Per-provider overrides (base_url / timeout / max_retries)
# can still be set in config.yaml under api.<provider>.*; "custom" lets you point
# at any other OpenAI-compatible endpoint via api.custom.base_url + CUSTOM_API_KEY.
# ---------------------------------------------------------------------------
# This project REQUIRES a vision-language (VL) model (image selection / caption
# alignment), so every listed provider serves one. `vision_model` is a known-good
# example id. (Text-only providers like DeepSeek are intentionally not listed.)
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
        "label": "硅基流动 SiliconFlow (CN)",
        "vision": True,
        "vision_model": "Qwen/Qwen3-VL-235B-A22B-Instruct",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "label": "阿里云百炼 / 通义千问 DashScope (CN)",
        "vision": True,
        "vision_model": "qwen-vl-max",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "label": "月之暗面 Moonshot / Kimi (CN)",
        "vision": True,
        "vision_model": "kimi-k2.5",   # multimodal; reasoning model — requires temperature: 1
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPU_API_KEY",
        "label": "智谱 AI / GLM (CN)",
        "vision": True,
        "vision_model": "glm-4v-plus",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "label": "OpenRouter (international aggregator)",
        "vision": True,
        "vision_model": "qwen/qwen2.5-vl-72b-instruct",
    },
    "custom": {
        "base_url": "",  # must be provided via config api.custom.base_url
        "api_key_env": "CUSTOM_API_KEY",
        "label": "Custom OpenAI-compatible endpoint",
        "vision": True,   # assume yes; you control the endpoint/model
        "vision_model": "",
    },
}

DEFAULT_PROVIDER = "siliconflow"


class APIClient:
    """Unified client for any OpenAI-compatible LLM provider (see PROVIDERS)."""

    # Available models (fallback default; SiliconFlow model id)
    MODEL_CHAT = "deepseek-ai/DeepSeek-V3"           # General dialogue

    def __init__(self):
        """Initialize API client"""
        # Provider selection (validated against the PROVIDERS table)
        self.provider = str(config.get("api.provider", DEFAULT_PROVIDER)).strip().lower()
        if self.provider not in PROVIDERS:
            print(f"⚠️  Unknown provider '{self.provider}', falling back to {DEFAULT_PROVIDER}")
            print(f"   Supported: {', '.join(PROVIDERS)}")
            self.provider = DEFAULT_PROVIDER

        # Active API key for text calls
        self.api_key = self._get_api_key(self.provider)

        if not self.api_key:
            env_var = PROVIDERS[self.provider]["api_key_env"]
            print(f"⚠️  API Key not configured for provider '{self.provider}'")
            print(f"   Please set {env_var} in your .env file")

    def _provider_meta(self, provider: str) -> Dict[str, str]:
        return PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])

    def _get_api_key(self, provider: str) -> str:
        env_var = self._provider_meta(provider)["api_key_env"]
        return os.getenv(env_var, "").strip()

    def _get_base_url(self, provider: str) -> str:
        # config override wins; otherwise the provider table default
        return config.get(
            f"api.{provider}.base_url",
            self._provider_meta(provider)["base_url"],
        )

    def _get_timeout(self, provider: str) -> int:
        return config.get(f"api.{provider}.timeout", config.get("api.default_timeout", 120))

    def _get_max_retries(self, provider: str) -> int:
        return config.get(f"api.{provider}.max_retries", config.get("api.default_max_retries", 3))

    def _get_headers(self, provider: str) -> Dict[str, str]:
        api_key = self._get_api_key(provider)
        if not api_key:
            raise ValueError(
                f"API Key not configured for provider '{provider}'. "
                f"Set {self._provider_meta(provider)['api_key_env']} in your .env file."
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Optional OpenRouter ranking/analytics headers
        if provider == "openrouter":
            referer = os.getenv("OPENROUTER_SITE_URL", "").strip()
            title = os.getenv("OPENROUTER_APP_NAME", "").strip()
            if referer:
                headers["HTTP-Referer"] = referer
            if title:
                headers["X-Title"] = title

        return headers

    def _chat_completion_message(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call the chat-completions endpoint and return the full assistant message.

        The message dict may contain a ``tool_calls`` list when ``tools`` is
        provided and the model decides to call a tool (native function calling).
        """
        provider = self.provider
        headers = self._get_headers(provider)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        timeout = self._get_timeout(provider)
        max_retries = self._get_max_retries(provider)
        base_url = self._get_base_url(provider)

        def make_request():
            response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout
            )
            # Some reasoning models (e.g. Moonshot kimi-k2.5) only accept
            # temperature=1 and 400 otherwise. Auto-recover once.
            if (response.status_code == 400
                    and "temperature" in (response.text or "").lower()
                    and payload.get("temperature") != 1):
                payload["temperature"] = 1
                response = requests.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )
            response.raise_for_status()
            return response.json()

        result = call_api_with_retry(
            make_request,
            max_retries=max_retries,
            base_delay=config.get("retry.base_delay", 2.0),
            max_delay=config.get("retry.max_delay", 60.0),
            backoff_factor=config.get("retry.backoff_factor", 2.0),
            api_name=f"{provider} ({model})"
        )
        return result['choices'][0]['message']

    def _call_api(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Call text model API (SiliconFlow/OpenRouter) and return the text content.

        Args:
            messages: Message list
            model: Model name (provider-specific)
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format (for forcing JSON output)

        Returns:
            Generated text
        """
        message = self._chat_completion_message(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        return message.get('content') or ""

    def call_chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Call the text model with native tool/function calling enabled.

        Returns the raw assistant message dict, which may contain ``tool_calls``.
        Used by the agent's function-calling loop instead of text parsing.
        """
        model = self._get_text_model()
        settings = self._get_text_settings()
        return self._chat_completion_message(
            messages=messages,
            model=model,
            temperature=settings["temperature"] if temperature is None else temperature,
            max_tokens=settings["max_tokens"] if max_tokens is None else max_tokens,
            tools=tools,
            tool_choice="auto",
        )

    def get_vision_endpoint(self) -> Dict[str, Any]:
        """
        Resolve the vision (VL) endpoint for the active provider.

        Returns a dict with: provider, base_url, headers, model, timeout, max_retries.
        Raises ValueError if no API key is configured. Every listed provider is
        VL-capable, so the active provider serves both text and vision.
        """
        provider = self.provider
        meta = self._provider_meta(provider)
        api_key = self._get_api_key(provider)
        if not api_key:
            raise ValueError(
                f"No API key configured for provider '{provider}'. "
                f"Set {meta['api_key_env']} in your .env file."
            )

        return {
            "provider": provider,
            "base_url": self._get_base_url(provider),
            "headers": self._get_headers(provider),
            "model": config.get("llm.vision.model", meta.get("vision_model") or "Qwen/Qwen3-VL-235B-A22B-Instruct"),
            "timeout": self._get_timeout(provider),
            "max_retries": self._get_max_retries(provider),
        }

    def _get_text_model(self) -> str:
        """Resolve unified text model name from config with fallback."""
        return config.get("llm.text.model", config.get("llm.chat.model", self.MODEL_CHAT))

    def _get_text_settings(self) -> Dict[str, Any]:
        """Resolve unified text settings (temperature/max_tokens) with safe defaults."""
        temperature = config.get("llm.text.temperature", 0.7)
        max_tokens = config.get("llm.text.max_tokens", 3000)

        # Clamp temperature to a sane range
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            temperature = 0.7
        if temperature < 0 or temperature > 2:
            temperature = 0.7

        return {"temperature": temperature, "max_tokens": max_tokens}

    def call_siliconflow(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Call text model (SiliconFlow/OpenRouter)

        Used for: Agent reasoning, content generation, daily tasks

        Args:
            messages: Message list
            model: Model name (provider-specific)
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format

        Returns:
            Generated text
        """
        if not model:
            model = self._get_text_model()
        text_settings = self._get_text_settings()
        temperature = text_settings["temperature"]
        max_tokens = text_settings["max_tokens"]

        return self._call_api(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format
        )

    def call_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Alias method for calling text model

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format

        Returns:
            Generated text
        """
        model = self._get_text_model()
        text_settings = self._get_text_settings()
        temperature = text_settings["temperature"]
        max_tokens = text_settings["max_tokens"]
        return self._call_api(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format
        )


# Global singleton
_client: Optional[APIClient] = None


def get_api_client() -> APIClient:
    """Get global API Client instance"""
    global _client
    if _client is None:
        _client = APIClient()
    return _client
