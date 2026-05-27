"""
Vision Optimization Tools - Content and image optimization using vision-language models

Uses Qwen3-VL-235B-A22B-Instruct model to:
- Analyze extracted figures from PDFs
- Select the best images for articles
- Optimize article content based on visual understanding
"""

import base64
from typing import List, Dict, Any, Optional
from pathlib import Path
from PIL import Image
import io

from .base import Tool, ToolParameter, ToolResult, register_tool
from ..config import config


def encode_image_to_base64(image_path: str, max_size: int = 2048) -> str:
    """
    Encode image to base64 string

    Args:
        image_path: Path to image file
        max_size: Maximum dimension (width/height) for resizing

    Returns:
        Base64 encoded string
    """
    img = Image.open(image_path)

    # Resize if too large (to save tokens)
    if max(img.width, img.height) > max_size:
        if img.width > img.height:
            new_width = max_size
            new_height = int(img.height * max_size / img.width)
        else:
            new_height = max_size
            new_width = int(img.width * max_size / img.height)
        img = img.resize((new_width, new_height), Image.LANCZOS)

    # Convert to RGB if necessary
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Encode to base64
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    img_bytes = buffer.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


@register_tool
class OptimizeXiaohongshuWithVisionTool(Tool):
    """Optimize Xiaohongshu content with vision model"""

    @property
    def name(self) -> str:
        return "optimize_xiaohongshu_with_vision"

    @property
    def description(self) -> str:
        return """使用视觉语言模型（Qwen3-VL）优化小红书笔记内容。

功能：
1. 分析论文中提取的图片，选择最适合小红书展示的3-5张图片
2. 基于图片内容优化笔记文案，使图文更加匹配
3. 确保标题吸引人且符合小红书风格

使用场景：
- 在生成小红书笔记后调用此工具进行优化
- 需要从多张图片中选择最佳展示图片

模型：Qwen/Qwen3-VL-235B-A22B-Instruct（SiliconFlow API）"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="title",
                type="string",
                description="原始笔记标题",
                required=True
            ),
            ToolParameter(
                name="content",
                type="string",
                description="原始笔记内容",
                required=True
            ),
            ToolParameter(
                name="image_paths",
                type="array",
                description="论文中提取的图片路径列表",
                required=True
            ),
            ToolParameter(
                name="max_images",
                type="integer",
                description="最多选择的图片数量，默认5张",
                required=False,
                default=5
            ),
        ]

    async def execute(
        self,
        title: str,
        content: str,
        image_paths: List[str],
        max_images: int = 5,
        **kwargs
    ) -> ToolResult:
        try:
            # Validate image paths
            valid_images = []
            for img_path in image_paths:
                if Path(img_path).exists():
                    valid_images.append(str(Path(img_path).absolute()))
                else:
                    print(f"⚠️ Image not found: {img_path}")

            if not valid_images:
                return ToolResult(
                    success=False,
                    error="No valid image files"
                )

            # Limit number of images to analyze
            images_to_analyze = valid_images[:10]  # Max 10 images to analyze

            # Encode images to base64
            base64_images = []
            for img_path in images_to_analyze:
                try:
                    base64_images.append(encode_image_to_base64(img_path))
                except Exception as e:
                    print(f"⚠️ Failed to encode image {img_path}: {e}")

            if not base64_images:
                return ToolResult(
                    success=False,
                    error="Failed to encode any images"
                )

            # Get API client
            from ..api_client import get_api_client
            client = get_api_client()

            # Build messages for vision model
            content_parts = []

            # Add images
            for b64_img in base64_images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_img}",
                        "detail": "high"
                    }
                })

            # Add text prompt
            prompt = f"""你是一位学术科普编辑。请分析上面这些来自学术论文的图片，并完成以下任务：

原始标题：{title}

原始内容：
{content}

任务要求：
1. 从这些图片中选择{min(max_images, len(base64_images))}张最适合小红书展示的图片（选择能清晰展示核心内容的图片）
2. 优化标题，使其更吸引人且符合小红书风格（标题≤10字，可以包含emoji）
3. 优化内容，使其更加完整、专业但易懂

**内容优化要求**：
- **篇幅600-900字**，把事情讲清楚
- **绝对禁止**："家人们谁懂啊"、"绝绝子"、"yyds"、"拿捏"、"泰裤辣"、"姐妹们"、"宝子们"
- **Emoji极简**（3-5个），只用于小标题
- **结构清晰**：引入→背景→方法→实验→意义
- **结尾格式**：完整论文标题，换行，再写标签

**结尾格式示例**：
...
这项研究为XX领域提供了新的思路。

《完整的论文标题》作者团队研究论文

#人工智能 #机器学习

请以JSON格式返回结果：
{{
  "selected_image_indices": [0, 2, 4],  // 选中的图片索引（从0开始）
  "optimized_title": "优化后的标题（≤10字）",
  "optimized_content": "优化后的内容（600-900字，结尾按格式写论文标题和标签）",
  "image_captions": ["图片1说明", "图片2说明", ...],
  "selection_reason": "选择这些图片的原因"
}}

只返回JSON，不要其他内容。"""

            content_parts.append({
                "type": "text",
                "text": prompt
            })

            messages = [{
                "role": "user",
                "content": content_parts
            }]

            # Call vision model using the active provider (SiliconFlow/OpenRouter)
            import requests
            try:
                endpoint = client.get_vision_endpoint()
            except ValueError as e:
                return ToolResult(success=False, error=str(e))

            headers = endpoint["headers"]
            payload = {
                "model": endpoint["model"],
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4000
            }

            timeout = endpoint["timeout"]
            max_retries = endpoint["max_retries"]

            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        f"{endpoint['base_url']}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    )
                    response.raise_for_status()
                    result = response.json()
                    content_text = result['choices'][0]['message']['content']

                    # Parse JSON response
                    import json
                    try:
                        # Extract JSON from response (in case there's extra text)
                        json_start = content_text.find('{')
                        json_end = content_text.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            content_text = content_text[json_start:json_end]

                        optimization_result = json.loads(content_text)

                        # Map selected indices to actual image paths
                        selected_indices = optimization_result.get("selected_image_indices", [])
                        selected_images = [
                            images_to_analyze[i] for i in selected_indices
                            if 0 <= i < len(images_to_analyze)
                        ]

                        return ToolResult(
                            success=True,
                            data={
                                "original_title": title,
                                "optimized_title": optimization_result.get("optimized_title", title),
                                "original_content": content,
                                "optimized_content": optimization_result.get("optimized_content", content),
                                "selected_images": selected_images,
                                "image_captions": optimization_result.get("image_captions", []),
                                "selection_reason": optimization_result.get("selection_reason", ""),
                                "total_images_analyzed": len(base64_images),
                                "images_selected": len(selected_images)
                            }
                        )
                    except json.JSONDecodeError as e:
                        # If JSON parsing fails, return raw content
                        return ToolResult(
                            success=True,
                            data={
                                "raw_response": content_text,
                                "note": "Failed to parse JSON response, returning raw content"
                            }
                        )

                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:
                        raise
                    print(f"Retry {attempt + 1}/{max_retries}: {e}")

        except Exception as e:
            import traceback
            return ToolResult(
                success=False,
                error=f"Vision optimization failed: {str(e)}",
                data={
                    "traceback": traceback.format_exc()
                }
            )



@register_tool
class AnalyzeImagesWithVisionTool(Tool):
    """Analyze images with vision model (general purpose)"""

    @property
    def name(self) -> str:
        return "analyze_images_with_vision"

    @property
    def description(self) -> str:
        return """使用视觉语言模型（Qwen3-VL）分析图片内容。

功能：
1. 识别图片中的主要元素和内容
2. 生成图片描述文字
3. 判断图片质量和适用场景

使用场景：
- 快速了解提取的图片内容
- 为图片选择提供参考

模型：Qwen/Qwen3-VL-235B-A22B-Instruct（SiliconFlow API）"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="image_paths",
                type="array",
                description="要分析的图片路径列表",
                required=True
            ),
            ToolParameter(
                name="analysis_type",
                type="string",
                description="分析类型：general（通用）、figures（图表）、tables（表格）",
                required=False,
                default="general",
                enum=["general", "figures", "tables"]
            ),
        ]

    async def execute(
        self,
        image_paths: List[str],
        analysis_type: str = "general",
        **kwargs
    ) -> ToolResult:
        try:
            # Validate image paths
            valid_images = []
            for img_path in image_paths:
                if Path(img_path).exists():
                    valid_images.append(str(Path(img_path).absolute()))
                else:
                    print(f"⚠️ Image not found: {img_path}")

            if not valid_images:
                return ToolResult(
                    success=False,
                    error="No valid image files"
                )

            # Limit number of images to analyze
            images_to_analyze = valid_images[:10]

            # Encode images to base64
            base64_images = []
            for img_path in images_to_analyze:
                try:
                    base64_images.append(encode_image_to_base64(img_path))
                except Exception as e:
                    print(f"⚠️ Failed to encode image {img_path}: {e}")

            if not base64_images:
                return ToolResult(
                    success=False,
                    error="Failed to encode any images"
                )

            # Get API client
            from ..api_client import get_api_client
            client = get_api_client()

            # Build messages for vision model
            content_parts = []

            # Add images
            for b64_img in base64_images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_img}",
                        "detail": "high"
                    }
                })

            # Add text prompt based on analysis type
            prompts = {
                "general": "请详细描述这些图片的内容。包括：1) 图片主要展示了什么 2) 图片的质量如何 3) 适合在什么场景使用。请为每张图片分别描述，并以JSON格式返回，格式为：{\"images\": [{\"index\": 0, \"description\": \"描述\", \"quality\": \"high/medium/low\", \"use_case\": \"适用场景\"}]}",
                "figures": "这些图片来自学术论文。请分析每张图片：1) 图片类型（架构图、实验结果图、流程图等） 2) 主要信息 3) 是否适合作为论文推荐文章的配图。请以JSON格式返回：{\"images\": [{\"index\": 0, \"type\": \"图片类型\", \"main_info\": \"主要信息\", \"suitable_for_article\": true/false}]}",
                "tables": "这些图片来自学术论文的表格。请提取：1) 表格的标题 2) 主要数据 3) 核心结论。请以JSON格式返回：{\"images\": [{\"index\": 0, \"title\": \"表格标题\", \"key_data\": \"关键数据\", \"conclusion\": \"结论\"}]}"
            }

            content_parts.append({
                "type": "text",
                "text": prompts.get(analysis_type, prompts["general"])
            })

            messages = [{
                "role": "user",
                "content": content_parts
            }]

            # Call vision model using the active provider (SiliconFlow/OpenRouter)
            import requests
            try:
                endpoint = client.get_vision_endpoint()
            except ValueError as e:
                return ToolResult(success=False, error=str(e))

            headers = endpoint["headers"]
            payload = {
                "model": endpoint["model"],
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 4000
            }

            timeout = endpoint["timeout"]
            max_retries = endpoint["max_retries"]

            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        f"{endpoint['base_url']}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    )
                    response.raise_for_status()
                    result = response.json()
                    content_text = result['choices'][0]['message']['content']

                    # Try to parse JSON response
                    import json
                    try:
                        json_start = content_text.find('{')
                        json_end = content_text.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            content_text = content_text[json_start:json_end]

                        analysis_result = json.loads(content_text)
                        analysis_result["total_images"] = len(base64_images)
                        analysis_result["analysis_type"] = analysis_type

                        return ToolResult(
                            success=True,
                            data=analysis_result
                        )
                    except json.JSONDecodeError:
                        return ToolResult(
                            success=True,
                            data={
                                "raw_response": content_text,
                                "note": "Failed to parse JSON response"
                            }
                        )

                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:
                        raise
                    print(f"Retry {attempt + 1}/{max_retries}: {e}")

        except Exception as e:
            import traceback
            return ToolResult(
                success=False,
                error=f"Image analysis failed: {str(e)}",
                data={
                    "traceback": traceback.format_exc()
                }
            )
