"""
XHS Paper Engine Core Module

Provides:
- config: Configuration management
- retry: Retry mechanism
- checkpoint: Checkpoint recovery
- logger: Logging management
- analytics: Performance data analysis
- dedup: Paper deduplication
- agent: ReAct Agent (DeepSeek powered)
- tools: Callable tool set
"""

from .config import config
from .retry import call_api_with_retry
from .checkpoint import CheckpointManager
from .logger import get_logger, log_info, log_success, log_error, log_warning, log_section

# Performance data analysis
from .analytics import (
    DatabaseManager,
    PerformanceTracker,
    AnalyticsReport,
    AnalyticsCollector,
    record_publication,
    record_metrics,
    print_analytics_report,
    DB_PATH,
)

# Paper deduplication
from .dedup import (
    PaperDeduplicator,
    filter_published_papers,
    is_paper_published,
)

# ReAct Agent
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
    'CheckpointManager',
    'get_logger',
    'log_info',
    'log_success',
    'log_error',
    'log_warning',
    'log_section',
    # Performance data analysis
    'DatabaseManager',
    'PerformanceTracker',
    'AnalyticsReport',
    'AnalyticsCollector',
    'record_publication',
    'record_metrics',
    'print_analytics_report',
    'DB_PATH',
    # Paper deduplication
    'PaperDeduplicator',
    'filter_published_papers',
    'is_paper_published',
    # ReAct Agent
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
