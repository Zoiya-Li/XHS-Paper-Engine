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
)
from .writing_tools import (
    WriteBlogTool,
    WriteXiaohongshuTool,
)
from .publish_tools import (
    PublishXiaohongshuTool,
)
from .analytics_tools import (
    GetAnalyticsTool,
    GetPublishRecommendationTool,
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
    # Writing tools
    "WriteBlogTool",
    "WriteXiaohongshuTool",
    # Publish tools
    "PublishXiaohongshuTool",
    # Analytics tools
    "GetAnalyticsTool",
    "GetPublishRecommendationTool",
    # Vision optimization tools
    "OptimizeXiaohongshuWithVisionTool",
    "AnalyzeImagesWithVisionTool",
]
