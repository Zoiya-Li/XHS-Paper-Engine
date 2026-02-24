"""
Analytics Tools - Analytics related tools
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from .base import Tool, ToolParameter, ToolResult, register_tool


@register_tool
class GetAnalyticsTool(Tool):
    """Get publish data analysis"""

    @property
    def name(self) -> str:
        return "get_analytics"

    @property
    def description(self) -> str:
        return "Get statistical analysis of publish data, including publish count, platform distribution, hot topics, etc."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="days",
                type="integer",
                description="Number of recent days to analyze",
                required=False,
                default=30
            ),
        ]

    async def execute(self, days: int = 30, **kwargs) -> ToolResult:
        try:
            from ..analytics import AnalyticsCollector

            collector = AnalyticsCollector()
            report = collector.generate_report(days=days)

            return ToolResult(
                success=True,
                data=report
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class GetPublishRecommendationTool(Tool):
    """Get publish recommendations"""

    @property
    def name(self) -> str:
        return "get_publish_recommendation"

    @property
    def description(self) -> str:
        return "Get publish recommendations based on historical data, including best publish times, hot topics, etc."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="platform",
                type="string",
                description="Target platform: xiaohongshu",
                required=False,
                default="xiaohongshu",
                enum=["xiaohongshu"]
            ),
        ]

    async def execute(self, platform: str = "xiaohongshu", **kwargs) -> ToolResult:
        try:
            from ..analytics import AnalyticsCollector

            collector = AnalyticsCollector()

            # Get best publish times
            best_times = collector.get_best_publish_times(platform=platform)

            # Get hot topics
            hot_topics = collector.get_hot_topics(days=7)

            return ToolResult(
                success=True,
                data={
                    "platform": platform,
                    "best_publish_times": best_times,
                    "hot_topics": hot_topics[:10],  # Top 10 hot topics
                    "recommendation": f"Recommended to publish at {best_times[0] if best_times else '10 AM'}"
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class GetPublishHistoryTool(Tool):
    """Get publish history"""

    @property
    def name(self) -> str:
        return "get_publish_history"

    @property
    def description(self) -> str:
        return "Get recent publish history records."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="limit",
                type="integer",
                description="Number of records to return",
                required=False,
                default=10
            ),
            ToolParameter(
                name="platform",
                type="string",
                description="Filter by platform",
                required=False,
                enum=["xiaohongshu", "blog"]
            ),
        ]

    async def execute(
        self,
        limit: int = 10,
        platform: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            from ..dedup import PaperDeduplicator

            deduplicator = PaperDeduplicator()
            papers = deduplicator.get_published_papers(days=90)

            # Filter by platform (if specified)
            if platform:
                papers = [p for p in papers if p.get('platform') == platform]

            # Limit count
            papers = papers[:limit]

            return ToolResult(
                success=True,
                data={
                    "total": len(papers),
                    "papers": papers
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
