"""
Writing Tools - Writing-related tools
"""

import json
from typing import List, Optional
from pathlib import Path

from .base import Tool, ToolParameter, ToolResult, register_tool
from ..config import config


def _format_tag_line(tags) -> str:
    """Render tags with exactly one leading '#' each (the model sometimes
    already prefixes them, which previously produced '##')."""
    return ", ".join(
        "#" + str(t).lstrip("#").strip()
        for t in (tags or []) if str(t).strip()
    )


@register_tool
class WriteBlogTool(Tool):
    """Blog article writing tool - Supports two-stage writing (draft + polishing)"""

    @property
    def name(self) -> str:
        return "write_blog"

    @property
    def description(self) -> str:
        return ("Generate a detailed technical blog article (Markdown) from paper content and "
                "save it to a local file. This is an export tool only — there is no blog "
                "publisher, so the output is a draft for you to use elsewhere. Supports a "
                "two-stage writing process: draft generation + polishing.")

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="paper_title",
                type="string",
                description="Paper title",
                required=True
            ),
            ToolParameter(
                name="paper_abstract",
                type="string",
                description="Paper abstract",
                required=True
            ),
            ToolParameter(
                name="paper_content",
                type="string",
                description="Full paper content (Markdown format)",
                required=False
            ),
            ToolParameter(
                name="output_path",
                type="string",
                description="Output file path",
                required=True
            ),
            ToolParameter(
                name="style",
                type="string",
                description="Writing style: technical (detailed), popular (popular science), brief (brief)",
                required=False,
                default="popular",
                enum=["technical", "popular", "brief"]
            ),
            ToolParameter(
                name="two_stage",
                type="boolean",
                description="Whether to use two-stage writing (draft + polishing), higher quality but takes longer",
                required=False,
                default=True
            ),
        ]

    async def execute(
        self,
        paper_title: str,
        paper_abstract: str,
        output_path: str,
        paper_content: Optional[str] = None,
        style: str = "popular",
        two_stage: bool = True,
        **kwargs
    ) -> ToolResult:
        try:
            from ..api_client import APIClient

            api_client = APIClient()

            # Select prompt based on style
            style_prompts = {
                "technical": "请写一篇技术详解文章，深入分析方法细节、数学公式、实现要点。目标读者是有一定技术背景的工程师和研究者。",
                "popular": "请写一篇科普文章，用通俗易懂的语言解释核心思想，适合非专业读者。多用比喻和类比来解释复杂概念。",
                "brief": "请写一篇简要介绍，重点突出创新点和主要贡献，500字左右。"
            }

            content_section = ""
            if paper_content:
                # If it's a file path, try to read
                if Path(paper_content).exists():
                    with open(paper_content, 'r', encoding='utf-8') as f:
                        content_section = f"\n\n**论文全文节选**：\n{f.read()[:10000]}..."
                else:
                    content_section = f"\n\n**论文全文节选**：\n{paper_content[:10000]}..."

            # Stage 1: Generate draft
            draft_prompt = f"""你是一位学术论文解读专家，擅长将复杂的学术论文转化为通俗易懂的微信公众号文章。

请基于以下论文内容，撰写一篇微信公众号解读文章。

**论文标题**：{paper_title}

**论文摘要**：{paper_abstract}
{content_section}

**写作风格要求**：
{style_prompts.get(style, style_prompts['popular'])}

**文章结构要求**：
1. **标题**：吸引人，突出核心创新点
2. **开头**：用1-2段引入背景和问题
3. **核心内容**：
   - 问题是什么？为什么重要？
   - 现有方法有什么局限？
   - 本文提出什么创新方法？
   - 方法的核心思想是什么？（用通俗语言）
   - 实验结果如何？有什么亮点？
4. **结论**：总结贡献和意义

**写作风格要求**：
- 像在和朋友讲解论文，而不是在写学术报告
- 多用主动语态，少用被动语态
- 避免套路化的过渡句（如"值得注意的是"、"综上所述"）
- 每段有自己的节奏和语调变化
- 数据和结论要自然融入叙述，不要生硬罗列
- 适当使用emoji增加趣味性（但不要过度）

请直接开始写作，不要有任何前缀说明。"""

            draft = api_client.call_chat(
                [{"role": "user", "content": draft_prompt}],
                max_tokens=4000,
                temperature=0.7
            )

            # If not using two-stage, return directly
            if not two_stage:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(draft)

                return ToolResult(
                    success=True,
                    data={
                        "output_path": str(output_path),
                        "word_count": len(draft),
                        "style": style,
                        "stages": 1
                    }
                )

            # Stage 2: Polish and optimize
            polish_prompt = f"""请对以下微信公众号文章进行最终的结构调整和润色。

**文章**：
{draft}

**润色要求**：
1. **结构优化**：
   - 检查整体结构是否合理
   - 调整段落顺序使逻辑更流畅
   - 确保开头、正文、结尾衔接自然

2. **语言精炼**：
   - 删除冗余表达
   - 优化句式使其更简洁有力
   - 统一语言风格

3. **细节完善**：
   - 检查标点符号
   - 统一术语翻译

4. **消除AI写作痕迹**：
   - 删除"值得注意的是"、"综上所述"、"总而言之"等套话
   - 避免过于工整的"首先...其次...最后"结构
   - 让语言更自然、口语化
   - 每段语气要有变化，不要千篇一律

**重要要求**：
- 只输出最终文章的完整内容
- 不要添加任何"改写说明"或其他元信息
- 从文章标题开始，到文章结尾结束
- 保持原有的 Markdown 格式

直接输出文章即可。"""

            final_article = api_client.call_siliconflow(
                [{"role": "user", "content": polish_prompt}]
            )

            # Save article
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_article)

            return ToolResult(
                success=True,
                data={
                    "output_path": str(output_path),
                    "word_count": len(final_article),
                    "style": style,
                    "stages": 2
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class WriteXiaohongshuTool(Tool):
    """Xiaohongshu post writing tool"""

    @property
    def name(self) -> str:
        return "write_xiaohongshu"

    @property
    def description(self) -> str:
        return "Generate Xiaohongshu-style posts based on paper content. Requires detailed paper information or complete article content, with attractive titles and concise interesting content suitable for social media sharing."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="paper_title",
                type="string",
                description="Paper title",
                required=True
            ),
            ToolParameter(
                name="paper_abstract",
                type="string",
                description="Paper abstract",
                required=True
            ),
            ToolParameter(
                name="paper_content",
                type="string",
                description="Full paper content or already written blog article (Markdown format), providing more detailed content generates better posts",
                required=False
            ),
            ToolParameter(
                name="key_points",
                type="array",
                description="List of key points from the paper",
                required=False
            ),
            ToolParameter(
                name="output_path",
                type="string",
                description="Output file path",
                required=False
            ),
        ]

    async def execute(
        self,
        paper_title: str,
        paper_abstract: str,
        paper_content: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        output_path: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            from ..api_client import APIClient

            # Build input content
            content_for_conversion = f"""# {paper_title}

## 摘要
{paper_abstract}
"""
            if paper_content:
                content_for_conversion += f"\n## 详细内容\n{paper_content[:8000]}"

            if key_points:
                content_for_conversion += "\n\n## 关键点\n" + "\n".join(f"- {p}" for p in key_points)

            # Use detailed Xiaohongshu conversion prompt
            system_prompt = """你是一个学术科普博主，擅长将学术论文转化为通俗易懂的小红书内容。你的写作风格是：专业、真诚、有料，**绝不套路化**。

重要原则：
1) **标题必须≤10字（含标点）**：吸睛有冲击力，生成后务必数清字数
2) **正文600-900字**：把事情讲清楚，不要过于简略
3) **Emoji极简（3-5个）**：只用于小标题，不要过度堆砌
4) **段落适中**：避免大段文字，但也要有完整叙述
5) **数据要强调**：用符号突出关键数字（准确率从55.4%提升到82.3%）
6) **结尾必须写完整论文标题**，然后换行再写标签
7) **绝对禁止的网络用语**："家人们谁懂啊"、"绝绝子"、"yyds"、"拿捏"、"泰裤辣"、"姐妹们"、"宝子们"
8) 避免"值得注意的是"、"综上所述"等AI化表达
9) 像在给同学/朋友介绍一个有趣的学术发现，真诚、专业、不夸张

**内容结构要求**：
- 开头：简短引入（1-2句话说明这个研究在解决什么问题）
- 背景：为什么这个问题重要？现有方法有什么不足？
- 方法：论文的核心创新点是什么？用通俗语言解释
- 实验：有什么关键数据？效果如何提升？
- 意义：这个研究有什么价值？
- 结尾：完整的论文标题（必须一字不差），然后换行写标签"""

            prompt = f"""请将以下论文/文章内容转换为小红书风格的帖子。

**严格要求**：
1. **标题：最多10个字（包括标点符号！）**
   - 要吸睛、有冲击力，但不夸张
   - **必须严格控制在10字以内，宁可短不要超**

2. **正文：600-900字**
   - **把事情讲清楚**，不要过于简略
   - 段落适中，避免大段文字，但也要完整叙述
   - 重点内容换行强调

3. **Emoji 极简使用**：
   - 总共使用 **3-5个** emoji
   - 只用于小标题，不要过度堆砌

4. **数据展示格式**：
   - 准确率从55.4%提升到82.3%
   - 性能提升3倍
   - 用文字描述，不要过度依赖符号

5. **结构（必须包含）**：
   - 开头：简短引入（说明这个研究在解决什么问题）
   - 背景：为什么这个问题重要？现有方法有什么不足？
   - 方法：核心创新点是什么？用通俗语言解释
   - 实验：关键数据是什么？效果如何提升？
   - 意义：这个研究有什么价值？
   - 结尾：**完整的论文标题（一字不差）**，然后换行写标签

6. **标签格式**：
   - 在论文标题后换行
   - 用 #标签名 的格式
   - 提取 5-10 个相关标签

**🚫 绝对禁止的表达（极其重要！）**：
- ❌ "家人们谁懂啊"、"绝绝子"、"yyds"、"拿捏"、"泰裤辣"
- ❌ "姐妹们"、"宝子们"、"家人们"、"宝"
- ❌ "值得注意的是"、"有趣的是"、"不难发现"
- ❌ "首先...其次...最后"、"综上所述"
- ❌ "真的绝了"、"太秀了"、"太强了"
- ❌ "点赞收藏🌟"、"一键三连"、"关注我不迷路"

**应该用的真实表达**：
- ✅ 自然开头："最近读到一篇关于XX的研究"
- ✅ 客观描述："这个方法的效果比较明显"
- ✅ 提问引导："为什么会这样呢？"

**原文**：
论文标题：{paper_title}
{content_for_conversion}

**输出格式（严格JSON）**：
```json
{{
    "title": "最多10字的标题",
    "content": "600-900字的正文，完整讲述论文内容，结尾写完整论文标题，然后换行写标签",
    "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"]
}}
```

**⚠️ 结尾格式示例**：
...
这项研究为XX领域提供了新的思路。

《{paper_title}》作者团队研究论文

#人工智能 #机器学习 #论文分享

只返回JSON，不要其他内容。"""

            api_client = APIClient()
            model = config.get("llm.text.model", api_client.MODEL_CHAT)
            response = api_client.call_siliconflow(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model=model,
                response_format={"type": "json_object"}
            )

            # 解析结果
            import re
            result_text = response.strip()

            # 提取 JSON（可能被包裹在 ```json 中）
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(1)

            result = json.loads(result_text)

            # Save (if path specified)
            if output_path:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Save as Markdown format (consistent with original format)
                md_content = f"""# {result.get("title", "")}

{result.get("content", "")}

---
标签: {_format_tag_line(result.get("tags", []))}
"""
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)

            return ToolResult(
                success=True,
                data={
                    "title": result.get("title", ""),
                    "content": result.get("content", ""),
                    "tags": result.get("tags", []),
                    "output_path": str(output_path) if output_path else None
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


#
#                 images_info += """
# **图片插入规则**：
# 1. 在文章开头（标题后）插入最吸引眼球的主图
# 2. 在"方法"部分插入架构图/流程图
# 3. 在"实验结果"部分插入数据图/对比图
# 4. 使用 Markdown 图片语法: ![图片描述](图片路径)
# 5. 图片前后要空一行
# 6. 每张图片下方加简短说明（用斜体）
# """
#
#             prompt = f"""请根据以下论文信息，撰写一篇微信公众号文章。
#
# 论文标题：{paper_title}
#
# 论文摘要：{paper_abstract}
# {content_section}
# {images_info}
#
# 公众号文章要求：
# 1. **标题：必须10个字以内！** 微信有严格限制，超过会发布失败
#    - 示例好标题：「AI学会主动提问」「新范式提升推理」
#    - 不要用冒号、引号等标点
# 2. 文章结构（每个部分都应该有配图）：
#    - **引言**：点明论文价值和意义 → 插入主图（最能代表论文的图）
#    - **背景**：问题是什么，为什么重要
#    - **方法**：核心创新点是什么 → 插入架构图/方法图
#    - **实验**：主要结果和发现 → 插入实验结果图
#    - **总结**：对读者的启发
# 3. 写作风格：
#    - 专业但易懂
#    - 适当使用类比帮助理解
#    - 重要内容加粗
#    - 适合在手机上阅读
# 4. 字数：1500-2500字
# 5. **图片插入格式**：
#    - 使用 Markdown 语法: ![描述](路径)
#    - 图片单独一行，前后空行
#    - 图片下方用斜体加说明，如：*图1: 系统架构图*
#
# 请直接输出 Markdown 格式的文章，确保图片已正确插入。"""
#
#             api_client = APIClient()
#             article = api_client.call_siliconflow(
#                 [{"role": "user", "content": prompt}],
#                 max_tokens=4000,
#                 temperature=0.7
#             )
#
#             # 如果 LLM 没有插入图片，手动在开头插入第一张
#             if images and '![' not in article:
#                 first_img = images[0]
#                 first_desc = image_descriptions[0] if image_descriptions else "论文主图"
#                 # 在第一个标题后插入
#                 lines = article.split('\n')
#                 new_lines = []
#                 inserted = False
#                 for line in lines:
#                     new_lines.append(line)
#                     if line.startswith('# ') and not inserted:
#                         new_lines.append('')
#                         new_lines.append(f'![{first_desc}]({first_img})')
#                         new_lines.append(f'*{first_desc}*')
#                         new_lines.append('')
#                         inserted = True
#                 article = '\n'.join(new_lines)
#
#             # 保存文章
#             output_path = Path(output_path)
#             output_path.parent.mkdir(parents=True, exist_ok=True)
#
#             with open(output_path, 'w', encoding='utf-8') as f:
#                 f.write(article)
#
#             # 统计插入的图片数量
#             import re
#             image_count = len(re.findall(r'!\[.*?\]\(.*?\)', article))
#
#             return ToolResult(
#                 success=True,
#                 data={
#                     "output_path": str(output_path),
#                     "word_count": len(article),
#                     "image_count": image_count,
#                     "images_provided": len(images) if images else 0
#                 }
#             )
#
#         except Exception as e:
#             return ToolResult(success=False, error=str(e))
