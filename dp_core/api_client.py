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


class APIClient:
    """Unified API call client - SiliconFlow/OpenRouter"""

    # API base URLs
    SILICONFLOW_BASE = "https://api.siliconflow.cn/v1"
    OPENROUTER_BASE = "https://openrouter.ai/api/v1"

    # Available models (fallback defaults)
    MODEL_CHAT = "deepseek-ai/DeepSeek-V3"           # General dialogue

    def __init__(self):
        """Initialize API client"""
        # Read API keys from environment
        self.siliconflow_api_key = os.getenv('SILICONFLOW_API_KEY', '').strip()
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY', '').strip()

        # Provider selection
        self.provider = str(config.get("api.provider", "siliconflow")).strip().lower()
        if self.provider not in ("siliconflow", "openrouter"):
            print(f"⚠️  Unknown provider '{self.provider}', falling back to siliconflow")
            self.provider = "siliconflow"

        # Active API key for text calls
        self.api_key = self._get_api_key(self.provider)

        if not self.api_key:
            print("⚠️  API Key not configured")
            if self.provider == "openrouter":
                print("   Please set OPENROUTER_API_KEY in your .env file")
            else:
                print("   Please set SILICONFLOW_API_KEY in your .env file")

    def _get_api_key(self, provider: str) -> str:
        if provider == "openrouter":
            return self.openrouter_api_key
        return self.siliconflow_api_key

    def _get_base_url(self, provider: str) -> str:
        if provider == "openrouter":
            return config.get("api.openrouter.base_url", self.OPENROUTER_BASE)
        return config.get("api.siliconflow.base_url", self.SILICONFLOW_BASE)

    def _get_timeout(self, provider: str) -> int:
        if provider == "openrouter":
            return config.get("api.openrouter.timeout", 120)
        return config.get("api.siliconflow.timeout", 120)

    def _get_max_retries(self, provider: str) -> int:
        if provider == "openrouter":
            return config.get("api.openrouter.max_retries", 3)
        return config.get("api.siliconflow.max_retries", 3)

    def _get_headers(self, provider: str) -> Dict[str, str]:
        api_key = self._get_api_key(provider)
        if not api_key:
            raise ValueError("API Key not configured")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Optional OpenRouter headers
        if provider == "openrouter":
            referer = os.getenv("OPENROUTER_SITE_URL", "").strip()
            title = os.getenv("OPENROUTER_APP_NAME", "").strip()
            if referer:
                headers["HTTP-Referer"] = referer
            if title:
                headers["X-Title"] = title

        return headers

    def _call_api(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Call text model API (SiliconFlow/OpenRouter)

        Args:
            messages: Message list
            model: Model name (provider-specific)
            temperature: Temperature parameter
            max_tokens: Maximum token count
            response_format: Response format (for forcing JSON output)

        Returns:
            Generated text
        """
        provider = self.provider
        headers = self._get_headers(provider)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Add response format (if specified)
        if response_format:
            payload["response_format"] = response_format

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
            response.raise_for_status()
            return response.json()

        result = call_api_with_retry(
            make_request,
            max_retries=max_retries,
            api_name=f"{provider} ({model})"
        )
        return result['choices'][0]['message']['content']

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
