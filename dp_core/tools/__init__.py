"""
XHS Paper Engine Tools Module
All tools callable by Agent
"""

from .base import Tool, ToolRegistry, ToolResult, default_registry
from .paper_tools import (
    SearchPapersTool,
    SearchByAuthorTool,
    GetCitationsTool,
    LookupByDOITool,
    DownloadPaperTool,
    ConvertPDFToMarkdownTool,
    ExtractFiguresTool,
    CheckDuplicateTool,
    SelectBestPaperTool,
    ReadFileTool,
    ListFilesTool,
)
from .writing_tools import (
    WriteBlogTool,
    WriteXiaohongshuTool,
)
from .publish_tools import (
    PublishXiaohongshuTool,
    LoginXiaohongshuTool,
    RecordPublishTool,
)
from .analytics_tools import (
    GetPublishHistoryTool,
)
from .vision_optimization_tools import (
    OptimizeXiaohongshuWithVisionTool,
    AnalyzeImagesWithVisionTool,
)

__all__ = [
    # Base
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "default_registry",
    # Paper tools
    "SearchPapersTool",
    "SearchByAuthorTool",
    "GetCitationsTool",
    "LookupByDOITool",
    "DownloadPaperTool",
    "ConvertPDFToMarkdownTool",
    "ExtractFiguresTool",
    "CheckDuplicateTool",
    "SelectBestPaperTool",
    "ReadFileTool",
    "ListFilesTool",
    # Writing tools
    "WriteBlogTool",
    "WriteXiaohongshuTool",
    # Publish tools
    "PublishXiaohongshuTool",
    "LoginXiaohongshuTool",
    "RecordPublishTool",
    # Analytics tools
    "GetPublishHistoryTool",
    # Vision optimization tools
    "OptimizeXiaohongshuWithVisionTool",
    "AnalyzeImagesWithVisionTool",
]
