"""
Paper Tools - 论文相关工具

Supports multiple academic data sources:
- arXiv (preprints, AI/ML/CS)
- Semantic Scholar (rich citation data, optional)
"""

import os
import json
import time
import re
import asyncio
import subprocess
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import pytz

from .base import Tool, ToolParameter, ToolResult, register_tool
from ..config import config

# Constants
BEIJING_TZ = pytz.timezone('Asia/Shanghai')
S2_SEARCH_API = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_API_KEY = os.getenv("S2_API_KEY", "").strip()

# Supported data sources
SUPPORTED_SOURCES = [
    "arxiv", "semantic"
]


@register_tool
class SearchPapersTool(Tool):
    """Paper search tool - Supports multiple academic data sources"""

    @property
    def name(self) -> str:
        return "search_papers"

    @property
    def description(self) -> str:
        return f"Search academic papers. Supports data sources: {', '.join(SUPPORTED_SOURCES)}."

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="搜索关键词，如 'LLM', 'transformer', 'RAG'",
                required=True
            ),
            ToolParameter(
                name="source",
                type="string",
                description=f"数据源：{', '.join(SUPPORTED_SOURCES)}。默认从 config.yaml 读取。",
                required=False,
                default="arxiv"
            ),
            ToolParameter(
                name="category",
                type="string",
                description="arXiv 分类，如 'cs.AI', 'cs.CL', 'cs.LG'（仅 arXiv 有效）。默认从 config.yaml 读取。",
                required=False,
                default="cs.AI"
            ),
            ToolParameter(
                name="days",
                type="integer",
                description="搜索最近几天的论文。默认从 config.yaml 读取。",
                required=False,
                default=3
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="最大返回数量",
                required=False,
                default=20
            ),
            ToolParameter(
                name="min_citations",
                type="integer",
                description="最少引用数（仅 semantic 支持）",
                required=False,
                default=0
            ),
        ]

    async def execute(
        self,
        query: str,
        source: Optional[str] = None,
        category: Optional[str] = None,
        days: Optional[int] = None,
        max_results: int = 20,
        min_citations: int = 0,
        **kwargs
    ) -> ToolResult:
        try:
            # 从配置读取默认值
            sources = config.get("research.sources", ["arxiv"])
            categories = config.get("research.categories", ["cs.AI"])
            default_days = config.get("research.days", 3)

            # Disable Semantic Scholar unless key is provided
            if not S2_API_KEY:
                sources = [
                    s for s in sources
                    if str(s).lower() not in ("s2", "semantic", "semantic_scholar")
                ]

            # 应用默认值
            if source is None:
                source = sources[0] if sources else "arxiv"
            if category is None:
                category = categories[0] if categories else "cs.AI"
            if days is None:
                days = default_days

            source = source.lower()

            # Semantic Scholar
            if source in ["s2", "semantic", "semantic_scholar"]:
                if not S2_API_KEY:
                    return ToolResult(
                        success=False,
                        error="未配置 S2_API_KEY，默认不启用 Semantic Scholar。请在 .env 中设置后再使用。"
                    )
                return await self._search_semantic_scholar(
                    query, days, max_results, min_citations
                )

            # arXiv（内置实现）
            if source == "arxiv":
                return await self._search_arxiv(query, category, days, max_results)

            # Unsupported source
            if source not in SUPPORTED_SOURCES:
                return ToolResult(
                    success=False,
                    error=f"不支持的数据源: {source}。支持: {', '.join(SUPPORTED_SOURCES)}"
                )

            # 默认使用 arXiv
            return await self._search_arxiv(query, category, days, max_results)

        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _search_arxiv(
        self,
        query: str,
        category: str,
        days: int,
        max_results: int
    ) -> ToolResult:
        """搜索 arXiv"""
        import requests
        import xml.etree.ElementTree as ET
        from urllib.parse import quote

        # 构建搜索查询（支持多分类）
        categories: List[str] = []
        if category:
            if isinstance(category, (list, tuple, set)):
                categories = [str(c).strip() for c in category if str(c).strip()]
            else:
                categories = [
                    c.strip() for c in re.split(r"[,\s]+", str(category)) if c.strip()
                ]

        if categories:
            cat_query = " OR ".join(f"cat:{c}" for c in categories)
            if len(categories) > 1:
                cat_query = f"({cat_query})"
            search_query = f"{cat_query} AND all:{query}"
        else:
            search_query = f"all:{query}"
        encoded_query = quote(search_query)

        # 默认使用 HTTPS，若 SSL 失败则回退到 HTTP
        url = f"https://export.arxiv.org/api/query?search_query={encoded_query}&sortBy=submittedDate&sortOrder=descending&start=0&max_results={max_results * 2}"
        url_http = f"http://export.arxiv.org/api/query?search_query={encoded_query}&sortBy=submittedDate&sortOrder=descending&start=0&max_results={max_results * 2}"

        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # 发起请求
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.exceptions.SSLError:
            response = requests.get(url_http, timeout=30)
            response.raise_for_status()

        # 解析 XML
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}

        papers = []
        for entry in root.findall('atom:entry', ns):
            # 获取发布时间
            published_str = entry.find('atom:published', ns).text
            published_date = datetime.fromisoformat(published_str.replace('Z', '+00:00'))

            # 过滤日期
            if published_date.replace(tzinfo=None) < start_date:
                continue

            # 获取 arXiv ID
            entry_id = entry.find('atom:id', ns).text
            arxiv_id = entry_id.split('/abs/')[-1]

            # 获取作者
            authors = []
            for author in entry.findall('atom:author', ns)[:5]:
                name = author.find('atom:name', ns)
                if name is not None:
                    authors.append(name.text)

            # 获取分类
            categories = []
            for cat in entry.findall('arxiv:primary_category', ns):
                categories.append(cat.get('term'))
            for cat in entry.findall('atom:category', ns):
                term = cat.get('term')
                if term and term not in categories:
                    categories.append(term)

            # 获取摘要
            summary = entry.find('atom:summary', ns).text.strip()
            if len(summary) > 500:
                summary = summary[:500] + "..."

            papers.append({
                "arxiv_id": arxiv_id,
                "title": entry.find('atom:title', ns).text.strip().replace('\n', ' '),
                "abstract": summary,
                "authors": authors,
                "published": published_date.strftime("%Y-%m-%d"),
                "categories": categories,
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                "source": "arxiv"
            })

            if len(papers) >= max_results:
                break

        return ToolResult(
            success=True,
            data={
                "total": len(papers),
                "query": query,
                "source": "arxiv",
                "category": category,
                "papers": papers
            }
        )

    async def _search_semantic_scholar(
        self,
        query: str,
        days: int,
        max_results: int,
        min_citations: int
    ) -> ToolResult:
        """搜索 Semantic Scholar"""
        import requests

        if not S2_API_KEY:
            return ToolResult(
                success=False,
                error="未配置 S2_API_KEY，Semantic Scholar 查询已禁用。"
            )

        headers = {
            "User-Agent": "XHS-Paper-Engine/1.0",
        }
        headers["x-api-key"] = S2_API_KEY

        # API 参数
        params = {
            "query": query,
            "offset": 0,
            "limit": 100,
            "fields": ",".join([
                "paperId", "title", "abstract", "year", "url",
                "openAccessPdf", "authors.name", "externalIds",
                "publicationVenue", "citationCount",
                "influentialCitationCount", "isOpenAccess",
                "fieldsOfStudy"
            ])
        }

        # 添加时间过滤
        if days > 0:
            cutoff_date = datetime.now(BEIJING_TZ) - timedelta(days=days)
            date_range = f"{cutoff_date.strftime('%Y-%m-%d')}:"
            params["publicationDateOrYear"] = date_range

        papers = []
        offset = 0

        while len(papers) < max_results:
            params["offset"] = offset
            time.sleep(1.1)  # Rate limiting

            response = requests.get(
                S2_SEARCH_API,
                params=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json().get("data", [])

            if not data:
                break

            for item in data:
                paper = self._normalize_s2_paper(item)
                if not paper:
                    continue

                # 引用数过滤
                if min_citations > 0:
                    cits = paper.get("citation_count", 0)
                    if cits < min_citations:
                        continue

                papers.append(paper)
                if len(papers) >= max_results:
                    break

            offset += len(data)
            if len(data) < 100:
                break

        return ToolResult(
            success=True,
            data={
                "total": len(papers),
                "query": query,
                "source": "semantic_scholar",
                "papers": papers
            }
        )

    def _normalize_s2_paper(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """规范化 Semantic Scholar 论文数据"""
        title = (item.get("title") or "").strip()
        abstract = (item.get("abstract") or "").strip()

        # 过滤：必须有标题和摘要
        if not title or not abstract or len(abstract) < 50:
            return None

        year = item.get("year")
        url = item.get("url", "")

        # PDF URL
        pdf_url = ""
        open_access_pdf = item.get("openAccessPdf")
        if isinstance(open_access_pdf, dict):
            pdf_url = open_access_pdf.get("url", "")

        # 作者
        authors = [a.get("name") for a in (item.get("authors") or [])[:5] if a.get("name")]

        # IDs
        ext = item.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        doi = ext.get("DOI")
        s2id = item.get("paperId")

        # 优先使用 arXiv ID
        if arxiv_id:
            url = url or f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = pdf_url or f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        elif doi:
            url = url or f"https://doi.org/{doi}"

        # 截断摘要
        if len(abstract) > 500:
            abstract = abstract[:500] + "..."

        return {
            "arxiv_id": arxiv_id or s2id,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "published": str(year) if year else "N/A",
            "pdf_url": pdf_url,
            "url": url,
            "citation_count": item.get("citationCount", 0),
            "influential_citations": item.get("influentialCitationCount", 0),
            "is_open_access": item.get("isOpenAccess", False),
            "fields": item.get("fieldsOfStudy") or [],
            "source": "semantic_scholar"
        }


@register_tool
class CheckDuplicateTool(Tool):
    """检查论文是否已发布"""

    @property
    def name(self) -> str:
        return "check_duplicate"

    @property
    def description(self) -> str:
        return "检查论文是否已经发布过，避免重复发布。返回未发布的论文列表。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="arxiv_ids",
                type="array",
                description="要检查的 arXiv ID 列表",
                required=True
            ),
            ToolParameter(
                name="days",
                type="integer",
                description="检查最近多少天内的发布记录",
                required=False,
                default=90
            ),
        ]

    async def execute(
        self,
        arxiv_ids: List[str],
        days: int = 90,
        **kwargs
    ) -> ToolResult:
        try:
            from ..dedup import PaperDeduplicator

            deduplicator = PaperDeduplicator()
            published_ids = deduplicator.get_published_arxiv_ids(days=days)

            # 过滤已发布的
            new_ids = [aid for aid in arxiv_ids if aid not in published_ids]
            duplicate_ids = [aid for aid in arxiv_ids if aid in published_ids]

            return ToolResult(
                success=True,
                data={
                    "total_checked": len(arxiv_ids),
                    "new_papers": new_ids,
                    "already_published": duplicate_ids,
                    "new_count": len(new_ids),
                    "duplicate_count": len(duplicate_ids)
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class SelectBestPaperTool(Tool):
    """选择最佳论文"""

    @property
    def name(self) -> str:
        return "select_best_paper"

    @property
    def description(self) -> str:
        return "从论文列表中选择最适合科普分享的论文。基于创新性、科普价值、可视化潜力等维度评估。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="papers",
                type="array",
                description="论文列表，每个论文包含 title, abstract, arxiv_id",
                required=True
            ),
        ]

    async def execute(self, papers: List[Dict], **kwargs) -> ToolResult:
        try:
            from ..api_client import APIClient

            if not papers:
                return ToolResult(success=False, error="论文列表为空")

            if len(papers) == 1:
                return ToolResult(
                    success=True,
                    data={
                        "selected": papers[0],
                        "reason": "只有一篇论文，直接选择"
                    }
                )

            # 构建评估 prompt
            papers_text = ""
            for i, p in enumerate(papers, 1):
                papers_text += f"\n论文{i}: {p.get('title', 'Unknown')}\n"
                papers_text += f"摘要: {p.get('abstract', 'No abstract')[:400]}...\n"

            prompt = f"""请从以下论文中选择最适合写成科普文章的一篇。

评估维度：
1. 科普价值（概念是否易懂，有没有好故事）
2. 创新性（方法是否新颖，有没有核心洞察）
3. 可视化潜力（是否容易图解）

候选论文：
{papers_text}

请选择一篇，输出 JSON 格式：
{{"selected_index": 1-{len(papers)}, "reason": "选择理由"}}

只输出 JSON，不要其他内容。"""

            api_client = APIClient()
            model = config.get("llm.text.model", api_client.MODEL_CHAT)
            response = api_client.call_siliconflow(
                [{"role": "user", "content": prompt}],
                model=model,
                response_format={"type": "json_object"}
            )

            result = json.loads(response)
            selected_idx = result.get("selected_index", 1) - 1

            if 0 <= selected_idx < len(papers):
                return ToolResult(
                    success=True,
                    data={
                        "selected": papers[selected_idx],
                        "reason": result.get("reason", "")
                    }
                )
            else:
                return ToolResult(success=False, error="选择的索引超出范围")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class DownloadPaperTool(Tool):
    """下载论文 PDF"""

    @property
    def name(self) -> str:
        return "download_paper"

    @property
    def description(self) -> str:
        return "下载论文 PDF 文件到本地。支持通过 arXiv ID 或 PDF URL 下载。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="arxiv_id",
                type="string",
                description="arXiv ID，如 '2401.12345'",
                required=False
            ),
            ToolParameter(
                name="pdf_url",
                type="string",
                description="PDF 下载链接",
                required=False
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="输出目录",
                required=True
            ),
        ]

    async def execute(
        self,
        output_dir: str,
        arxiv_id: Optional[str] = None,
        pdf_url: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            import requests

            # 确定下载 URL
            if arxiv_id:
                url = f"https://export.arxiv.org/pdf/{arxiv_id}.pdf"
            elif pdf_url:
                url = pdf_url
            else:
                return ToolResult(success=False, error="必须提供 arxiv_id 或 pdf_url")

            # 创建输出目录
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # 下载文件
            pdf_path = output_path / "paper.pdf"

            print(f"正在下载: {url}")
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            })

            response = session.get(url, timeout=180, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=32768):
                    f.write(chunk)
                    downloaded += len(chunk)

            return ToolResult(
                success=True,
                data={
                    "pdf_path": str(pdf_path),
                    "size_mb": round(downloaded / 1024 / 1024, 2),
                    "source": arxiv_id or pdf_url
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class ConvertPDFToMarkdownTool(Tool):
    """将 PDF 转换为 Markdown - 使用硅基流动 OCR API"""

    # 硅基流动 API 配置
    SILICONFLOW_API_BASE = "https://api.siliconflow.cn/v1"
    OCR_MODEL = "deepseek-ai/DeepSeek-OCR"

    @property
    def name(self) -> str:
        return "convert_pdf_to_markdown"

    @property
    def description(self) -> str:
        return """将论文 PDF 转换为 Markdown 格式。

优先使用简单文本提取（适用于 arXiv 等原生 PDF）。
如果文本提取失败或内容过少，会使用硅基流动 OCR API。

需要设置环境变量: SILICONFLOW_API_KEY"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="pdf_path",
                type="string",
                description="PDF 文件路径",
                required=True
            ),
            ToolParameter(
                name="output_path",
                type="string",
                description="输出 Markdown 文件路径",
                required=True
            ),
            ToolParameter(
                name="use_ocr",
                type="boolean",
                description="强制使用 OCR（默认自动判断）",
                required=False,
                default=False
            ),
            ToolParameter(
                name="ocr_dpi",
                type="integer",
                description="OCR 图像 DPI（默认 180）",
                required=False,
                default=180
            ),
        ]

    async def execute(
        self,
        pdf_path: str,
        output_path: str,
        use_ocr: bool = False,
        ocr_dpi: int = 180,
        **kwargs
    ) -> ToolResult:
        import io
        import base64
        import subprocess
        import shutil

        try:
            import fitz  # PyMuPDF
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 PyMuPDF: pip install pymupdf"
            )

        pdf_path = Path(pdf_path)
        output_path = Path(output_path)

        if not pdf_path.exists():
            return ToolResult(success=False, error=f"PDF 文件不存在: {pdf_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        def _run_pdftotext() -> ToolResult:
            """Fallback OCR using poppler's pdftotext."""
            pdftotext = shutil.which("pdftotext")
            if not pdftotext:
                return ToolResult(
                    success=False,
                    error="未找到 pdftotext 命令。请先安装 poppler（macOS: brew install poppler）。"
                )

            try:
                subprocess.run(
                    [pdftotext, "-layout", str(pdf_path), str(output_path)],
                    check=True,
                    capture_output=True
                )
            except subprocess.CalledProcessError as e:
                return ToolResult(
                    success=False,
                    error=f"pdftotext 执行失败: {e.stderr.decode(errors='ignore')[:200]}"
                )

            try:
                content = output_path.read_text(encoding="utf-8")
            except Exception:
                content = ""

            return ToolResult(
                success=True,
                data={
                    "markdown_path": str(output_path),
                    "length": len(content),
                    "method": "pdftotext",
                    "pages": None
                }
            )

        # 方案1: 尝试简单文本提取（适用于原生 PDF）
        if not use_ocr:
            try:
                doc = fitz.open(str(pdf_path))
                text_parts = []
                for page_num, page in enumerate(doc):
                    page_text = page.get_text()
                    if page_text.strip():
                        text_parts.append(f"<!-- Page {page_num + 1} -->\n\n{page_text}")
                doc.close()

                full_text = "\n\n".join(text_parts)

                # 如果提取到足够的文本（每页平均超过 100 字符），使用简单提取
                if len(full_text) > len(text_parts) * 100:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(full_text)

                    return ToolResult(
                        success=True,
                        data={
                            "markdown_path": str(output_path),
                            "length": len(full_text),
                            "method": "text_extraction",
                            "pages": len(text_parts)
                        }
                    )
                else:
                    print(f"⚠️ 文本提取内容过少，切换到 OCR 模式")
                    use_ocr = True

            except Exception as e:
                print(f"⚠️ 文本提取失败: {e}，切换到 OCR 模式")
                use_ocr = True

        # 方案2: 使用硅基流动 OCR API
        if use_ocr:
            provider = str(config.get("api.provider", "siliconflow")).lower()
            if provider == "openrouter":
                return _run_pdftotext()

            api_key = os.getenv('SILICONFLOW_API_KEY')
            if not api_key:
                # Fallback to pdftotext if available
                return _run_pdftotext()

            try:
                from PIL import Image
                import requests
                from ..retry import call_api_with_retry
                from ..config import config
            except ImportError:
                return ToolResult(
                    success=False,
                    error="需要安装依赖: pip install pillow requests"
                )

            try:
                # 1. PDF 转图像
                doc = fitz.open(str(pdf_path))
                total_pages = len(doc)
                print(f"📄 PDF 页数: {total_pages}")

                pages_text = []
                for page_num in range(total_pages):
                    page = doc[page_num]
                    mat = fitz.Matrix(ocr_dpi / 72, ocr_dpi / 72)
                    pix = page.get_pixmap(matrix=mat)

                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data)).convert("RGB")

                    # 2. OCR 单页
                    print(f"   🔍 OCR 第 {page_num + 1}/{total_pages} 页...")

                    # 转 base64
                    buffered = io.BytesIO()
                    img.save(buffered, format="PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

                    # 调用 API
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }

                    ocr_model = config.get("llm.ocr.model", self.OCR_MODEL)
                    payload = {
                        "model": ocr_model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                                {"type": "text", "text": "Convert the document to markdown format."}
                            ]
                        }],
                        "max_tokens": 6000,
                        "temperature": 0.0
                    }

                    response = call_api_with_retry(
                        lambda p=payload: requests.post(
                            f"{self.SILICONFLOW_API_BASE}/chat/completions",
                            headers=headers,
                            json=p,
                            timeout=config.get("api.siliconflow.timeout", 60)
                        ),
                        max_retries=config.get("api.siliconflow.max_retries", 3),
                        api_name="硅基流动 OCR"
                    )

                    if response.status_code != 200:
                        print(f"   ⚠️ 第 {page_num + 1} 页 OCR 失败: {response.status_code}")
                        pages_text.append(f"[Page {page_num + 1} - OCR Failed]")
                    else:
                        result = response.json()
                        page_text = result['choices'][0]['message']['content']
                        pages_text.append(page_text)
                        print(f"   ✓ 第 {page_num + 1}/{total_pages} 页完成")

                doc.close()

                # 3. 智能连接页面
                full_text = self._smart_join_pages(pages_text)

                # 4. 保存
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)

                return ToolResult(
                    success=True,
                    data={
                        "markdown_path": str(output_path),
                        "length": len(full_text),
                        "method": "siliconflow_ocr",
                        "pages": total_pages
                    }
                )

            except Exception as e:
                return ToolResult(success=False, error=f"OCR 转换失败: {str(e)}")

        return ToolResult(success=False, error="转换失败")

    def _smart_join_pages(self, pages: List[str]) -> str:
        """智能连接页面，改善跨页句子的衔接"""
        if not pages:
            return ""

        result = []
        incomplete_endings = [',', 'and', 'or', 'but', 'with', 'for', 'of', 'in', 'to', 'a', 'an', 'the', '-']

        for i, page in enumerate(pages):
            if i == 0:
                result.append(page)
                continue

            prev_page = result[-1].rstrip()
            curr_page = page.lstrip()

            # 检查上一页是否以不完整句子结尾
            is_incomplete = any(prev_page.endswith(ending) for ending in incomplete_endings)

            if is_incomplete:
                if prev_page.endswith('-'):
                    result[-1] = prev_page[:-1]
                    result.append(curr_page)
                else:
                    result[-1] = prev_page + " " + curr_page
            else:
                result.append("\n\n" + page)

        return "".join(result)


@register_tool
class ExtractFiguresTool(Tool):
    """提取论文图表"""

    @property
    def name(self) -> str:
        return "extract_figures"

    @property
    def description(self) -> str:
        return """从论文 PDF 中智能提取图片和表格。

使用 Document Layout Analysis (Detectron2) 模型进行智能布局分析：
- 自动检测图片（Figure）和表格（Table）
- 提取图表标题作为文件名
- 智能裁剪边界框，去除截断文字
- 平衡四周白边

依赖：需要安装 Document-Layout-Analysis-staging 项目"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="pdf_path",
                type="string",
                description="PDF 文件路径",
                required=True
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="图片输出目录",
                required=True
            ),
        ]

    async def execute(
        self,
        pdf_path: str,
        output_dir: str,
        **kwargs
    ) -> ToolResult:
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # 检查 PDF 文件是否存在
            if not Path(pdf_path).exists():
                return ToolResult(success=False, error=f"PDF 文件不存在: {pdf_path}")

            # 使用 layoutparser/deepdoctection 提取
            from ..extract_figures_tables import extract_figures_and_tables

            stats = extract_figures_and_tables(
                pdf_path=pdf_path,
                output_dir=output_dir,
                min_score=0.7,
                dpi=300,
                save_json=True
            )

            # 获取提取的文件列表
            figures_dir = output_path / "figures"
            tables_dir = output_path / "tables"

            figure_files = []
            table_files = []

            if figures_dir.exists():
                figure_files = sorted([str(f) for f in figures_dir.glob("*.png")])
            if tables_dir.exists():
                table_files = sorted([str(f) for f in tables_dir.glob("*.png")])

            all_images = figure_files + table_files

            # 验证实际提取的文件
            if not all_images:
                return ToolResult(
                    success=False,
                    error="未能从 PDF 中提取出任何图片。可能论文中没有可识别的图表，或者 PDF 格式不支持。",
                    data={
                        "output_dir": output_dir,
                        "stats": stats,
                        "hint": "尝试使用 convert_pdf_to_markdown 查看论文内容"
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "figures_count": len(figure_files),
                    "tables_count": len(table_files),
                    "output_dir": output_dir,
                    "figure_files": figure_files,
                    "table_files": table_files,
                    "all_images": all_images,
                    "method": "layout_parser"
                }
            )

        except Exception as e:
            import traceback
            return ToolResult(success=False, error=f"提取图片失败: {str(e)}\n{traceback.format_exc()}")


@register_tool
class CapturePdfPagesTool(Tool):
    """将 PDF 页面转换为图片"""

    @property
    def name(self) -> str:
        return "capture_pdf_pages"

    @property
    def description(self) -> str:
        return """将 PDF 的指定页面渲染为图片。当 extract_figures 无法提取图片时，可以用此工具将论文的关键页面截图作为配图。"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="pdf_path",
                type="string",
                description="PDF 文件路径",
                required=True
            ),
            ToolParameter(
                name="output_dir",
                type="string",
                description="图片输出目录",
                required=True
            ),
            ToolParameter(
                name="pages",
                type="array",
                description="要截取的页码列表（从 1 开始），如 [1, 2, 5]。不指定则截取前 4 页。",
                required=False
            ),
            ToolParameter(
                name="dpi",
                type="integer",
                description="图片分辨率 DPI，默认 150",
                required=False,
                default=150
            ),
        ]

    async def execute(
        self,
        pdf_path: str,
        output_dir: str,
        pages: Optional[List[int]] = None,
        dpi: int = 150,
        **kwargs
    ) -> ToolResult:
        try:
            import fitz

            pdf_path = Path(pdf_path)
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            if not pdf_path.exists():
                return ToolResult(success=False, error=f"PDF 文件不存在: {pdf_path}")

            doc = fitz.open(str(pdf_path))
            total_pages = len(doc)

            # 确定要截取的页面
            if pages:
                # 用户指定的页面（转换为 0-indexed）
                page_nums = [p - 1 for p in pages if 0 < p <= total_pages]
            else:
                # 默认截取前 4 页
                page_nums = list(range(min(4, total_pages)))

            if not page_nums:
                doc.close()
                return ToolResult(success=False, error="没有有效的页面可以截取")

            captured_files = []
            zoom = dpi / 72  # 72 是 PDF 默认 DPI

            for page_num in page_nums:
                page = doc[page_num]
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                image_path = output_path / f"page_{page_num + 1}.png"
                pix.save(str(image_path))
                captured_files.append(str(image_path))

            doc.close()

            return ToolResult(
                success=True,
                data={
                    "captured_count": len(captured_files),
                    "total_pages": total_pages,
                    "output_dir": str(output_path),
                    "captured_files": captured_files,
                    "all_images": captured_files,
                    "dpi": dpi
                }
            )

        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 PyMuPDF: pip install pymupdf"
            )
        except Exception as e:
            import traceback
            return ToolResult(success=False, error=f"截取 PDF 页面失败: {str(e)}\n{traceback.format_exc()}")


# ============================================================
# 以下是基于 research-master MCP 的扩展工具
# ============================================================

@register_tool
class SearchByAuthorTool(Tool):
    """按作者搜索论文（通过 research-master MCP）"""

    @property
    def name(self) -> str:
        return "search_by_author"

    @property
    def description(self) -> str:
        return "按作者姓名搜索论文。支持 arXiv, Semantic Scholar, OpenAlex, PubMed 等数据源。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="author",
                type="string",
                description="作者姓名，如 'Geoffrey Hinton', 'Yann LeCun'",
                required=True
            ),
            ToolParameter(
                name="source",
                type="string",
                description="数据源：arxiv, semantic, openalex, pubmed 等。默认搜索所有支持的源。",
                required=False,
                default="all"
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="最大返回数量",
                required=False,
                default=20
            ),
        ]

    async def execute(
        self,
        author: str,
        source: str = "all",
        max_results: int = 20,
        **kwargs
    ) -> ToolResult:
        try:
            if _check_research_master():
                args = ["author", author, "--max-results", str(max_results)]
                if source.lower() != "all":
                    args.extend(["--source", source])

                result = _call_research_master(args, timeout=120)
                if result:
                    papers = result.get("papers", result.get("results", []))
                    return ToolResult(
                        success=True,
                        data={
                            "total": len(papers),
                            "author": author,
                            "source": source,
                            "papers": papers
                        }
                    )

            # 回退：使用 Semantic Scholar 作者搜索
            import requests
            headers = {}
            if S2_API_KEY:
                headers["x-api-key"] = S2_API_KEY
            url = f"https://api.semanticscholar.org/graph/v1/author/search?query={author}&limit={max_results}"
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                authors = data.get("data", [])
                if authors:
                    # 获取第一个作者的论文
                    author_id = authors[0].get("authorId")
                    papers_url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers?limit={max_results}&fields=title,abstract,year,citationCount"
                    papers_response = requests.get(papers_url, headers=headers, timeout=30)
                    if papers_response.status_code == 200:
                        papers = papers_response.json().get("data", [])
                        return ToolResult(
                            success=True,
                            data={
                                "total": len(papers),
                                "author": author,
                                "source": "semantic_scholar",
                                "papers": papers
                            }
                        )

            return ToolResult(success=False, error="未找到该作者的论文")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class GetCitationsTool(Tool):
    """获取论文引用（通过 research-master MCP）"""

    @property
    def name(self) -> str:
        return "get_citations"

    @property
    def description(self) -> str:
        return "获取引用了指定论文的其他论文列表。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="paper_id",
                type="string",
                description="论文 ID（arXiv ID、DOI、PMC ID 等）",
                required=True
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="最大返回数量",
                required=False,
                default=20
            ),
        ]

    async def execute(
        self,
        paper_id: str,
        max_results: int = 20,
        **kwargs
    ) -> ToolResult:
        try:
            if _check_research_master():
                args = ["citations", paper_id, "--max-results", str(max_results)]
                result = _call_research_master(args, timeout=120)
                if result:
                    citations = result.get("citations", result.get("papers", []))
                    return ToolResult(
                        success=True,
                        data={
                            "total": len(citations),
                            "paper_id": paper_id,
                            "citations": citations
                        }
                    )

            # 回退：使用 Semantic Scholar
            import requests
            headers = {}
            if S2_API_KEY:
                headers["x-api-key"] = S2_API_KEY

            # 首先获取论文 ID
            search_url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{paper_id}"
            response = requests.get(search_url, headers=headers, timeout=30)

            if response.status_code == 200:
                paper_data = response.json()
                s2_id = paper_data.get("paperId")
                if s2_id:
                    citations_url = f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}/citations?limit={max_results}&fields=title,abstract,year,citationCount"
                    cit_response = requests.get(citations_url, headers=headers, timeout=30)
                    if cit_response.status_code == 200:
                        citations = [c.get("citingPaper", {}) for c in cit_response.json().get("data", [])]
                        return ToolResult(
                            success=True,
                            data={
                                "total": len(citations),
                                "paper_id": paper_id,
                                "citations": citations
                            }
                        )

            return ToolResult(success=False, error="无法获取引用信息")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class LookupByDOITool(Tool):
    """通过 DOI 查找论文（通过 research-master MCP）"""

    @property
    def name(self) -> str:
        return "lookup_by_doi"

    @property
    def description(self) -> str:
        return "通过 DOI（Digital Object Identifier）查找论文详细信息。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="doi",
                type="string",
                description="论文 DOI，如 '10.48550/arXiv.1706.03762'",
                required=True
            ),
        ]

    async def execute(
        self,
        doi: str,
        **kwargs
    ) -> ToolResult:
        try:
            if _check_research_master():
                args = ["lookup", doi]
                result = _call_research_master(args, timeout=60)
                if result:
                    return ToolResult(
                        success=True,
                        data={
                            "doi": doi,
                            "paper": result
                        }
                    )

            # 回退：使用 Semantic Scholar DOI 查找
            import requests
            headers = {}
            if S2_API_KEY:
                headers["x-api-key"] = S2_API_KEY
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,abstract,year,authors,citationCount,url,openAccessPdf"
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                paper = response.json()
                return ToolResult(
                    success=True,
                    data={
                        "doi": doi,
                        "paper": paper
                    }
                )

            return ToolResult(success=False, error=f"无法通过 DOI 查找论文: {doi}")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class ReadFileTool(Tool):
    """读取文件内容"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "读取本地文件内容。支持文本文件（.txt, .md, .json 等）。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="文件路径",
                required=True
            ),
            ToolParameter(
                name="max_chars",
                type="integer",
                description="最大读取字符数（默认 50000）",
                required=False,
                default=50000
            ),
        ]

    async def execute(
        self,
        path: str,
        max_chars: int = 50000,
        **kwargs
    ) -> ToolResult:
        try:
            file_path = Path(path)

            if not file_path.exists():
                return ToolResult(success=False, error=f"文件不存在: {path}")

            if not file_path.is_file():
                return ToolResult(success=False, error=f"路径不是文件: {path}")

            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(max_chars)

            truncated = len(content) >= max_chars

            return ToolResult(
                success=True,
                data={
                    "path": str(file_path),
                    "content": content,
                    "length": len(content),
                    "truncated": truncated
                }
            )

        except UnicodeDecodeError:
            return ToolResult(success=False, error=f"文件编码错误，无法读取: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class ListFilesTool(Tool):
    """列出目录内容"""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "列出指定目录下的文件和子目录。可用于查看 figures、papers 等目录的内容。"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="目录路径",
                required=True
            ),
            ToolParameter(
                name="pattern",
                type="string",
                description="文件名过滤模式（如 '*.png', '*.pdf'）",
                required=False
            ),
        ]

    async def execute(
        self,
        path: str,
        pattern: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            import glob

            dir_path = Path(path)

            if not dir_path.exists():
                return ToolResult(success=False, error=f"目录不存在: {path}")

            if not dir_path.is_dir():
                return ToolResult(success=False, error=f"路径不是目录: {path}")

            # 获取文件列表
            if pattern:
                files = list(dir_path.glob(pattern))
            else:
                files = list(dir_path.iterdir())

            # 分类文件和目录
            file_list = []
            dir_list = []

            for f in sorted(files):
                if f.is_file():
                    file_list.append({
                        "name": f.name,
                        "path": str(f),
                        "size": f.stat().st_size
                    })
                elif f.is_dir():
                    dir_list.append({
                        "name": f.name,
                        "path": str(f)
                    })

            return ToolResult(
                success=True,
                data={
                    "directory": str(dir_path),
                    "files": file_list,
                    "directories": dir_list,
                    "total_files": len(file_list),
                    "total_dirs": len(dir_list)
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class AnalyzeImagesTool(Tool):
    """分析和筛选图片工具"""

    @property
    def name(self) -> str:
        return "analyze_images"

    @property
    def description(self) -> str:
        return """分析指定目录中的图片，返回每张图片的详细信息。

用于在发布前筛选最佳图片：
- 返回图片尺寸、大小、宽高比等信息
- 帮助 Agent 判断哪些图片适合发布
- 小红书建议选择 3-9 张高质量图片

筛选建议：
- 优先选择论文的核心图表（如架构图、实验结果图）
- 避免选择 logo、参考文献截图、过小的图片
- 图片尺寸建议至少 800x600"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="image_dir",
                type="string",
                description="图片目录路径",
                required=True
            ),
            ToolParameter(
                name="min_width",
                type="integer",
                description="最小宽度（像素），过滤小图片，默认 300",
                required=False,
                default=300
            ),
            ToolParameter(
                name="min_height",
                type="integer",
                description="最小高度（像素），过滤小图片，默认 200",
                required=False,
                default=200
            ),
            ToolParameter(
                name="max_images",
                type="integer",
                description="最多返回的图片数量，默认 20",
                required=False,
                default=20
            ),
        ]

    async def execute(
        self,
        image_dir: str,
        min_width: int = 300,
        min_height: int = 200,
        max_images: int = 20,
        **kwargs
    ) -> ToolResult:
        try:
            from PIL import Image
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 Pillow: pip install Pillow"
            )

        try:
            dir_path = Path(image_dir)

            if not dir_path.exists():
                return ToolResult(success=False, error=f"目录不存在: {image_dir}")

            if not dir_path.is_dir():
                return ToolResult(success=False, error=f"路径不是目录: {image_dir}")

            # 支持的图片格式
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

            # 收集所有图片（递归搜索子目录）
            all_images = []
            for f in dir_path.rglob('*'):
                if f.is_file() and f.suffix.lower() in image_extensions:
                    try:
                        with Image.open(f) as img:
                            width, height = img.size
                            file_size = f.stat().st_size

                            all_images.append({
                                "name": f.name,
                                "path": str(f),
                                "width": width,
                                "height": height,
                                "aspect_ratio": round(width / height, 2) if height > 0 else 0,
                                "size_kb": round(file_size / 1024, 1),
                                "format": img.format or f.suffix.upper().replace('.', ''),
                                "mode": img.mode,
                                "is_suitable": width >= min_width and height >= min_height
                            })
                    except Exception as e:
                        # 无法打开的图片跳过
                        continue

            # 按尺寸排序（大的在前）
            all_images.sort(key=lambda x: x['width'] * x['height'], reverse=True)

            # 分离适合发布的和不适合的
            suitable = [img for img in all_images if img['is_suitable']]
            unsuitable = [img for img in all_images if not img['is_suitable']]

            # 限制返回数量
            suitable = suitable[:max_images]

            # 生成推荐
            recommendations = []
            if len(suitable) == 0:
                recommendations.append("没有找到合适尺寸的图片，建议使用 capture_pdf_pages 截取论文页面")
            elif len(suitable) < 3:
                recommendations.append(f"只有 {len(suitable)} 张合适的图片，小红书建议 3-9 张")
            elif len(suitable) > 9:
                recommendations.append(f"有 {len(suitable)} 张合适的图片，建议选择最重要的 5-9 张")

            # 分析图片类型（简单启发式）
            for img in suitable[:5]:  # 只分析前5张
                name_lower = img['name'].lower()
                if 'fig' in name_lower or 'figure' in name_lower:
                    img['likely_type'] = '论文图表'
                elif 'table' in name_lower:
                    img['likely_type'] = '表格'
                elif 'arch' in name_lower or 'framework' in name_lower:
                    img['likely_type'] = '架构图'
                elif 'result' in name_lower or 'exp' in name_lower:
                    img['likely_type'] = '实验结果'
                else:
                    img['likely_type'] = '未知'

            return ToolResult(
                success=True,
                data={
                    "directory": str(dir_path),
                    "total_images": len(all_images),
                    "suitable_count": len(suitable),
                    "unsuitable_count": len(unsuitable),
                    "suitable_images": suitable,
                    "unsuitable_images": unsuitable[:5],  # 只返回前5张不合适的
                    "recommendations": recommendations,
                    "selection_tips": [
                        "优先选择: 架构图、核心算法图、实验结果对比图",
                        "避免选择: logo、过小的图、模糊的截图、参考文献页",
                        "小红书最佳数量: 5-9 张图片"
                    ]
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))


@register_tool
class SelectBestImagesTool(Tool):
    """智能选择最佳发布图片"""

    @property
    def name(self) -> str:
        return "select_best_images"

    @property
    def description(self) -> str:
        return """根据论文内容智能选择最适合发布的图片。

会分析图片文件名和属性，自动筛选：
- 架构图、框架图（优先）
- 实验结果图（优先）
- 核心算法流程图
- 排除 logo、参考文献、过小图片

返回推荐的图片列表，可直接用于 publish_xiaohongshu。"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="image_dir",
                type="string",
                description="图片目录路径",
                required=True
            ),
            ToolParameter(
                name="num_images",
                type="integer",
                description="选择的图片数量，默认 6（小红书最佳）",
                required=False,
                default=6
            ),
            ToolParameter(
                name="include_cover",
                type="boolean",
                description="是否包含封面图推荐，默认 True",
                required=False,
                default=True
            ),
        ]

    async def execute(
        self,
        image_dir: str,
        num_images: int = 6,
        include_cover: bool = True,
        **kwargs
    ) -> ToolResult:
        try:
            from PIL import Image
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 Pillow: pip install Pillow"
            )

        try:
            dir_path = Path(image_dir)

            if not dir_path.exists():
                return ToolResult(success=False, error=f"目录不存在: {image_dir}")

            # 支持的图片格式
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

            # 评分函数
            def score_image(img_info: dict) -> float:
                score = 0.0
                name_lower = img_info['name'].lower()
                width = img_info.get('width', 0)
                height = img_info.get('height', 0)

                # 尺寸评分（越大越好，但太大也扣分）
                pixels = width * height
                if pixels < 100000:  # 小于 ~316x316
                    score -= 50
                elif pixels < 500000:  # 中等
                    score += 10
                elif pixels < 2000000:  # 较大
                    score += 20
                else:  # 太大
                    score += 15

                # 宽高比评分（接近 4:3 或 16:9 更好）
                if height > 0:
                    ratio = width / height
                    if 1.2 <= ratio <= 1.8:  # 接近 4:3 或 16:9
                        score += 15
                    elif 0.8 <= ratio <= 1.2:  # 接近正方形
                        score += 10

                # 文件名关键词评分
                positive_keywords = [
                    ('figure', 30), ('fig', 30),
                    ('arch', 40), ('framework', 40), ('model', 35),
                    ('result', 35), ('exp', 30), ('comparison', 30),
                    ('overview', 35), ('pipeline', 35), ('workflow', 30),
                    ('method', 25), ('approach', 25),
                    ('main', 20), ('key', 20),
                ]
                negative_keywords = [
                    ('logo', -50), ('icon', -40),
                    ('ref', -30), ('reference', -30),
                    ('appendix', -20), ('supp', -15),
                    ('thumb', -40), ('small', -30),
                ]

                for keyword, points in positive_keywords:
                    if keyword in name_lower:
                        score += points
                        break  # 只加一次

                for keyword, points in negative_keywords:
                    if keyword in name_lower:
                        score += points

                return score

            # 收集所有图片（递归搜索子目录）
            images = []
            for f in dir_path.rglob('*'):
                if f.is_file() and f.suffix.lower() in image_extensions:
                    try:
                        with Image.open(f) as img:
                            width, height = img.size
                            file_size = f.stat().st_size

                            # 最小尺寸过滤
                            if width < 200 or height < 150:
                                continue

                            img_info = {
                                "name": f.name,
                                "path": str(f),
                                "width": width,
                                "height": height,
                                "size_kb": round(file_size / 1024, 1),
                            }
                            img_info['score'] = score_image(img_info)
                            images.append(img_info)
                    except:
                        continue

            if not images:
                return ToolResult(
                    success=True,
                    data={
                        "selected_images": [],
                        "cover_image": None,
                        "message": "没有找到合适的图片，建议使用 capture_pdf_pages 截取论文页面"
                    }
                )

            # 按评分排序
            images.sort(key=lambda x: x['score'], reverse=True)

            # 选择最佳图片
            selected = images[:num_images]

            # 选择封面图（评分最高且尺寸合适的）
            cover_image = None
            if include_cover:
                for img in selected:
                    # 封面图倾向于选择宽幅图片
                    if img['width'] >= img['height']:
                        cover_image = img['path']
                        break
                if not cover_image and selected:
                    cover_image = selected[0]['path']

            return ToolResult(
                success=True,
                data={
                    "selected_images": [img['path'] for img in selected],
                    "selected_details": selected,
                    "cover_image": cover_image,
                    "total_available": len(images),
                    "selection_reason": f"从 {len(images)} 张图片中选择了评分最高的 {len(selected)} 张"
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
