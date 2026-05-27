"""
Analytics Tools - publish history lookup
"""

from typing import List, Optional

from .base import Tool, ToolParameter, ToolResult, register_tool


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
