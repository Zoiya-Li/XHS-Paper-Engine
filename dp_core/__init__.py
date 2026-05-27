"""
XHS Paper Engine Core Module

Provides:
- config: Configuration management
- retry: Retry mechanism
- analytics: Publication recording (used for deduplication)
- dedup: Paper deduplication
- agent: ReAct / function-calling Agent
- tools: Callable tool set
"""

from .config import config
from .retry import call_api_with_retry

# Publication recording (backs deduplication)
from .analytics import (
    DatabaseManager,
    PerformanceTracker,
    DB_PATH,
)

# Paper deduplication
from .dedup import PaperDeduplicator

# Agent
from .agent import (
    ReActAgent,
    XHSPaperEngineAgent,
    AgentTrace,
    AgentStep,
    create_agent,
    run_task,
)

# Tool system
from .tools.base import (
    Tool,
    ToolRegistry,
    ToolResult,
    ToolParameter,
    default_registry,
    register_tool,
)

__all__ = [
    # Basic modules
    'config',
    'call_api_with_retry',
    # Publication recording
    'DatabaseManager',
    'PerformanceTracker',
    'DB_PATH',
    # Paper deduplication
    'PaperDeduplicator',
    # Agent
    'ReActAgent',
    'XHSPaperEngineAgent',
    'AgentTrace',
    'AgentStep',
    'create_agent',
    'run_task',
    # Tool system
    'Tool',
    'ToolRegistry',
    'ToolResult',
    'ToolParameter',
    'default_registry',
    'register_tool',
]
