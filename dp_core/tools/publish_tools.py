"""
Publish Tools - Publishing related tools

Supported platforms:
- Xiaohongshu (Little Red Book): Based on Playwright browser automation

Dependencies:
- pip install playwright markdown requests
- playwright install chromium

Configuration:
- Xiaohongshu: First-time use requires QR code scan login, cookies will be automatically saved
"""

from typing import List, Optional
from pathlib import Path

from .base import Tool, ToolParameter, ToolResult, register_tool


def _trim_xiaohongshu_content(content: str, max_len: int) -> str:
    """Trim content to Xiaohongshu length limit while keeping title/tags if possible."""
    if max_len <= 0 or len(content) <= max_len:
        return content

    lines = [line.rstrip() for line in content.strip().splitlines()]
    if not lines:
        return content[:max_len]

    suffix_lines = []
    while lines:
        tail = lines[-1].strip()
        if not tail:
            suffix_lines.insert(0, lines.pop())
            continue
        if tail.startswith("#") or tail.startswith("《"):
            suffix_lines.insert(0, lines.pop())
            continue
        break

    suffix = "\n".join([line for line in suffix_lines if line.strip()]).strip()
    prefix = "\n".join(lines).strip()

    if not suffix:
        return content[:max_len]

    # Leave at least one newline between prefix and suffix
    allowed = max_len - len(suffix) - 1
    if allowed <= 0:
        return suffix[:max_len]

    trimmed_prefix = prefix[:allowed].rstrip()
    return f"{trimmed_prefix}\n{suffix}"


@register_tool
class PublishXiaohongshuTool(Tool):
    """Publish to Xiaohongshu tool"""

    @property
    def name(self) -> str:
        return "publish_xiaohongshu"

    @property
    def description(self) -> str:
        return """Publish content to Xiaohongshu platform.

Implemented using Playwright browser automation, first-time use requires QR code scan login.
After successful login, cookies are automatically saved for future use without repeated login.

Dependency: pip install playwright && playwright install chromium"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="title",
                type="string",
                description="Post title (max 20 characters)",
                required=True
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Post content",
                required=True
            ),
            ToolParameter(
                name="images",
                type="array",
                description="List of image paths (at least 1 image required)",
                required=True
            ),
            ToolParameter(
                name="tags",
                type="array",
                description="List of topic tags",
                required=False
            ),
        ]

    async def execute(
        self,
        title: str,
        content: str,
        images: List[str],
        tags: Optional[List[str]] = None,
        **kwargs
    ) -> ToolResult:
        try:
            # Validate images
            valid_images = []
            for img_path in images:
                if Path(img_path).exists():
                    valid_images.append(str(Path(img_path).absolute()))
                else:
                    print(f"⚠️ Image not found: {img_path}")

            if not valid_images:
                return ToolResult(
                    success=False,
                    error="No valid image files"
                )

            # Get configuration
            from ..config import config

            # Opt-in gate: automated publishing is disabled unless the user
            # explicitly enables it, because it likely violates Xiaohongshu's ToS.
            if not config.get("publish.xiaohongshu.enabled", False):
                return ToolResult(
                    success=False,
                    error=(
                        "Automated publishing is disabled. Set "
                        "publish.xiaohongshu.enabled: true in config.yaml to opt in. "
                        "Warning: this likely violates Xiaohongshu's Terms of Service "
                        "and may get your account banned — use at your own risk."
                    ),
                    data={
                        "action_required": "enable_publishing",
                        "title": title,
                        "content": content,
                        "images": valid_images,
                        "tags": tags,
                    }
                )

            print(
                "⚠️  Automated publishing to Xiaohongshu may violate its Terms of "
                "Service and risks account suspension. Proceeding because "
                "publish.xiaohongshu.enabled is true."
            )

            # Use built-in Playwright publisher
            from ..publishers.xiaohongshu import XiaohongshuPublisher

            save_draft = config.get("publish.xiaohongshu.save_as_draft", False)
            visibility = config.get("publish.xiaohongshu.visibility", "private")  # Default only self visible
            max_content_len = config.get("publish.xiaohongshu.max_content_len", 1000)

            if isinstance(content, str) and max_content_len:
                trimmed = _trim_xiaohongshu_content(content, int(max_content_len))
                if trimmed != content:
                    print(f"⚠️ Content trimmed to {max_content_len} characters for Xiaohongshu")
                content = trimmed

            publisher = XiaohongshuPublisher(headless=False)

            try:
                await publisher.start()

                # Check login status
                if not await publisher.check_login():
                    # Need to login
                    return ToolResult(
                        success=False,
                        error="Xiaohongshu not logged in, need QR code scan login",
                        data={
                            "action_required": "login",
                            "message": "Please run the XHS Paper Engine login command, or manually login using Playwright",
                            "title": title,
                            "content": content,
                            "images": valid_images,
                            "tags": tags
                        }
                    )

                # Publish
                result = await publisher.publish(
                    title=title[:20],
                    content=content,
                    images=valid_images,
                    tags=tags or [],
                    save_draft=save_draft,
                    visibility=visibility  # Pass visibility range
                )

                if result.get("success"):
                    status = "draft" if save_draft else ("private" if visibility == "private" else "published")
                    return ToolResult(
                        success=True,
                        data={
                            "status": status,
                            "visibility": visibility,
                            "title": title[:20],
                            "image_count": len(valid_images),
                            "message": result.get("message", "Publish successful")
                        }
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=result.get("message", "Publish failed"),
                        data={
                            "title": title,
                            "images": valid_images
                        }
                    )

            finally:
                await publisher.stop()

        except Exception as e:
            return ToolResult(success=False, error=str(e))


# Note: CheckXiaohongshuLoginTool was removed as it was redundant
# publish_xiaohongshu tool handles login internally

@register_tool
class LoginXiaohongshuTool(Tool):
    """小红书扫码登录工具"""

    @property
    def name(self) -> str:
        return "login_xiaohongshu"

    @property
    def description(self) -> str:
        return """触发小红书扫码登录流程。

会打开浏览器窗口显示二维码，用户需要用小红书 APP 扫码登录。
登录成功后，Cookie 会被保存以便后续使用。"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="timeout",
                type="integer",
                description="等待扫码的超时时间（秒），默认 120",
                required=False,
                default=120
            )
        ]

    async def execute(self, timeout: int = 120, **kwargs) -> ToolResult:
        try:
            from ..publishers.xiaohongshu import XiaohongshuPublisher

            # 登录时不使用 headless 模式，以便用户可以看到二维码
            publisher = XiaohongshuPublisher(headless=False)

            try:
                await publisher.start()

                # 先检查是否已登录
                if await publisher.check_login():
                    return ToolResult(
                        success=True,
                        data={
                            "status": "already_logged_in",
                            "message": "小红书已登录，无需重复登录"
                        }
                    )

                # 触发扫码登录
                print("\n请使用小红书 APP 扫描屏幕上的二维码...")
                success = await publisher.login_with_qrcode(timeout=timeout)

                if success:
                    return ToolResult(
                        success=True,
                        data={
                            "status": "login_success",
                            "message": "小红书登录成功",
                            "cookies_saved": str(publisher.cookies_path)
                        }
                    )
                else:
                    return ToolResult(
                        success=False,
                        error="登录超时或失败",
                        data={
                            "timeout": timeout,
                            "hint": "请确保在超时前完成扫码"
                        }
                    )
            finally:
                await publisher.stop()

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class RecordPublishTool(Tool):
    """记录发布历史"""

    @property
    def name(self) -> str:
        return "record_publish"

    @property
    def description(self) -> str:
        return "记录论文发布历史，用于去重和统计分析。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="arxiv_id",
                type="string",
                description="论文的 arXiv ID",
                required=True
            ),
            ToolParameter(
                name="title",
                type="string",
                description="论文标题",
                required=True
            ),
            ToolParameter(
                name="platform",
                type="string",
                description="发布平台：xiaohongshu",
                required=True,
                enum=["xiaohongshu"]
            ),
            ToolParameter(
                name="url",
                type="string",
                description="发布后的链接（如果有）",
                required=False
            ),
        ]

    async def execute(
        self,
        arxiv_id: str,
        title: str,
        platform: str,
        url: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            from ..analytics import PerformanceTracker
            import uuid

            tracker = PerformanceTracker()

            # 生成一个临时的 post_id（如果没有真实的帖子ID）
            post_id = url if url else f"local_{uuid.uuid4().hex[:8]}"

            # 记录发布
            success = tracker.record_publication(
                post_id=post_id,
                paper_info={
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "topic": "general"
                },
                content_meta={
                    "title": title,
                    "content_length": 0,
                    "image_count": 0,
                    "tags": []
                },
                platform=platform
            )

            if success:
                return ToolResult(
                    success=True,
                    data={
                        "recorded": True,
                        "arxiv_id": arxiv_id,
                        "platform": platform,
                        "post_id": post_id
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    error="记录失败"
                )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
