"""
Configuration management module - Centralized management of all configuration items

Usage:
    from dp_core.config import config
    timeout = config.get("api.deepseek.timeout", 120)
"""

import os
from pathlib import Path
from typing import Any

# Try to import yaml, use built-in default config if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# Default configuration (used when config.yaml doesn't exist or yaml library is not installed)
DEFAULT_CONFIG = {
    "research": {
        "keywords": ["LLM", "RAG"],
        "categories": ["cs.AI", "cs.CL", "cs.LG"],
        "sources": ["arxiv"],
        "days": 3
    },
    "api": {
        "provider": "siliconflow",
        "deepseek": {
            "timeout": 120,
            "max_retries": 3,
            "base_url": "https://api.deepseek.com/v1"
        },
        "siliconflow": {
            "timeout": 60,
            "max_retries": 3,
            "base_url": "https://api.siliconflow.cn/v1"
        },
        "openrouter": {
            "timeout": 120,
            "max_retries": 3,
            "base_url": "https://openrouter.ai/api/v1"
        },
        "arxiv": {
            "timeout": 30,
            "max_retries": 3,
            "rate_limit_delay": 1.1
        },
        "semantic_scholar": {
            "timeout": 20,
            "max_retries": 3,
            "rate_limit_delay": 1.1
        },
        "xiaohongshu_mcp": {
            "timeout": 10,
            "max_retries": 3
        }
    },
    "llm": {
        "text": {
            "model": "deepseek-chat",
            "temperature": 0.7,
            "max_tokens": 3000
        },
        "vision": {
            "model": "Qwen/Qwen3-VL-235B-A22B-Instruct",
            "temperature": 0.7,
            "max_tokens": 4000
        },
        "ocr": {
            "model": "deepseek-ai/DeepSeek-OCR"
        }
    },
    "search": {
        "max_results": 100,
        "issues_result": 15,
        "recent_days": 3,
        "recent_years": 0,
        "min_citations": 0,
        "page_size": 100
    },
    "batch": {
        "paper_selection_batch_size": 20,
        "paper_selection_top_k": 20,
        "cli_timeout": 600,
        "publish_timeout": 1200,
        "browser_agent_max_steps": 800,
        "browser_agent_max_failures": 10
    },
    "ocr": {
        "dpi": 180,
        "max_tokens": 6000,
        "mode": "markdown"
    },
    "extraction": {
        "min_score": 0.7,
        "dpi": 300,
        "model_dir": ""
    },
    "retry": {
        "base_delay": 2.0,
        "max_delay": 60.0,
        "backoff_factor": 2.0
    },
    "publish": {
        "xiaohongshu": {
            "save_as_draft": False,  # Changed to default direct publishing
            "visibility": "private",  # public=publicly visible, private=only visible to self
            "default_tags": ["AI Research", "Tech Frontier"]
        }
    }
}


class Config:
    """Configuration management class (singleton pattern)"""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Load configuration file"""
        # Find config.yaml location
        config_paths = [
            Path(__file__).parent.parent / "config.yaml",  # XHS Paper Engine/config.yaml
            Path.cwd() / "config.yaml",  # Current directory
        ]

        self._config = DEFAULT_CONFIG.copy()

        if HAS_YAML:
            for config_path in config_paths:
                if config_path.exists():
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            user_config = yaml.safe_load(f)
                            if user_config:
                                self._deep_merge(self._config, user_config)
                        break
                    except Exception as e:
                        print(f"⚠️  Failed to load configuration file: {e}, using default configuration")

    def _deep_merge(self, base: dict, override: dict):
        """Deep merge configuration dictionaries"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value, supports dot-separated paths

        Args:
            key: Configuration key, e.g., "api.deepseek.timeout"
            default: Default value

        Returns:
            Configuration value

        Example:
            >>> config.get("api.deepseek.timeout", 120)
            120
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_with_env(self, key: str, env_var: str, default: Any = None) -> Any:
        """
        Get configuration value, prioritize environment variable

        Args:
            key: Configuration key
            env_var: Environment variable name
            default: Default value

        Example:
            >>> config.get_with_env("api.timeout", "API_TIMEOUT", 120)
        """
        env_value = os.environ.get(env_var)
        if env_value is not None:
            # Try type conversion
            try:
                config_default = self.get(key, default)
                if isinstance(config_default, int):
                    return int(env_value)
                elif isinstance(config_default, float):
                    return float(env_value)
                elif isinstance(config_default, bool):
                    return env_value.lower() in ('true', '1', 'yes')
            except ValueError:
                pass
            return env_value

        return self.get(key, default)

    def reload(self):
        """Reload configuration"""
        self._load_config()


# Global configuration instance
config = Config()
