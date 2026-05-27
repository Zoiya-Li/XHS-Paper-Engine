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
        max_results: Optional[int] = None,
        min_citations: Optional[int] = None,
        **kwargs
    ) -> ToolResult:
        try:
            # 从配置读取默认值
            sources = config.get("research.sources", ["arxiv"])
            categories = config.get("research.categories", ["cs.AI"])
            default_days = config.get("research.days", 3)

            # 未显式指定时，从 config.yaml 读取检索默认值
            if max_results is None:
                max_results = config.get("search.max_results", 50)
            if min_citations is None:
                min_citations = config.get("search.min_citations", 0)

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
        return ("检查论文是否已经发布过，避免重复发布。优先传入 papers（含 title），"
                "会同时按 arXiv ID 和标题相似度去重；也可只传 arxiv_ids 做 ID 级去重。")

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="papers",
                type="array",
                description="要检查的论文列表，每个含 arxiv_id 和 title（推荐，可按标题相似度去重）",
                required=False
            ),
            ToolParameter(
                name="arxiv_ids",
                type="array",
                description="要检查的 arXiv ID 列表（仅做 ID 级去重；提供了 papers 时可省略）",
                required=False
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
        papers: Optional[List[Dict]] = None,
        arxiv_ids: Optional[List[str]] = None,
        days: int = 90,
        **kwargs
    ) -> ToolResult:
        try:
            from ..dedup import PaperDeduplicator

            deduplicator = PaperDeduplicator()

            # 优先：按 ID + 标题相似度去重（需要 papers 含 title）
            if papers:
                new_papers, duplicates = [], []
                for paper in papers:
                    if deduplicator.is_published(paper, days=days):
                        duplicates.append(paper)
                    else:
                        new_papers.append(paper)

                return ToolResult(
                    success=True,
                    data={
                        "method": "id+title",
                        "total_checked": len(papers),
                        "new_papers": new_papers,
                        "already_published": duplicates,
                        "new_count": len(new_papers),
                        "duplicate_count": len(duplicates),
                    }
                )

            # 回退：仅 arXiv ID 级去重
            arxiv_ids = arxiv_ids or []
            published_ids = deduplicator.get_published_arxiv_ids(days=days)
            new_ids = [aid for aid in arxiv_ids if aid not in published_ids]
            duplicate_ids = [aid for aid in arxiv_ids if aid in published_ids]

            return ToolResult(
                success=True,
                data={
                    "method": "id_only",
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
    """将 PDF 转换为文本/Markdown。

    主路径用 PyMuPDF 直接抽取 PDF 自带的文字层（arXiv 等原生 PDF 都有），
    既快又免费。仅当文字层缺失或过少（如扫描件）时，回退到 poppler 的
    pdftotext。不再使用逐页视觉 OCR——对 arXiv 数据源而言它几乎不会触发，
    却带来高昂的逐页 API 成本。
    """

    @property
    def name(self) -> str:
        return "convert_pdf_to_markdown"

    @property
    def description(self) -> str:
        return """将论文 PDF 转换为文本/Markdown。

优先使用 PyMuPDF 文本提取（适用于 arXiv 等原生 PDF，快速且免费）。
若 PDF 没有文字层或内容过少（如扫描件），回退到 pdftotext（需安装 poppler）。"""

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
                name="force_fallback",
                type="boolean",
                description="跳过 PyMuPDF 文本提取，直接用 pdftotext 回退（默认 False）",
                required=False,
                default=False
            ),
        ]

    async def execute(
        self,
        pdf_path: str,
        output_path: str,
        force_fallback: bool = False,
        **kwargs
    ) -> ToolResult:
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
            """Fallback for PDFs without a usable text layer, via poppler's pdftotext."""
            pdftotext = shutil.which("pdftotext")
            if not pdftotext:
                return ToolResult(
                    success=False,
                    error="该 PDF 没有可提取的文字层，且未找到 pdftotext 命令。"
                          "请安装 poppler（macOS: brew install poppler；Linux: apt-get install poppler-utils）。"
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

        # 方案1: PyMuPDF 文本提取（适用于原生 PDF）
        if not force_fallback:
            try:
                doc = fitz.open(str(pdf_path))
                text_parts = []
                for page_num, page in enumerate(doc):
                    page_text = page.get_text()
                    if page_text.strip():
                        text_parts.append(f"<!-- Page {page_num + 1} -->\n\n{page_text}")
                doc.close()

                full_text = "\n\n".join(text_parts)

                # 提取到足够文本（每页平均超过 100 字符）则采用
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
                print("⚠️ 文字层内容过少，回退到 pdftotext")
            except Exception as e:
                print(f"⚠️ 文本提取失败: {e}，回退到 pdftotext")

        # 方案2: pdftotext 回退（扫描件 / 无文字层）
        return _run_pdftotext()


@register_tool
class ExtractFiguresTool(Tool):
    """提取论文图表"""

    @property
    def name(self) -> str:
        return "extract_figures"

    @property
    def description(self) -> str:
        return """从论文 PDF 中提取图片和表格（基于 pdffigures2）。

- 自动检测并裁剪图（Figure）和表（Table），裁剪干净、带语义文件名
- 同时给出标题（caption）等元数据
- 图存到 figures/，表存到 tables/

依赖：Java 运行时 + pdffigures2 fat JAR（见 README）。"""

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

            # 使用 pdffigures2 提取
            from ..extract_figures_tables import extract_figures_and_tables

            stats = extract_figures_and_tables(
                pdf_path=pdf_path,
                output_dir=output_dir,
                dpi=config.get("extraction.dpi", 200),
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
                    error="未能从 PDF 中提取出任何图表。这篇论文不适合做图文帖。",
                    data={
                        "output_dir": output_dir,
                        "stats": stats,
                        "hint": "回到选稿步骤，换一篇未发布的论文重试（不要发整页截图）。"
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
                    "method": "pdffigures2"
                }
            )

        except Exception as e:
            import traceback
            return ToolResult(success=False, error=f"提取图片失败: {str(e)}\n{traceback.format_exc()}")


# ============================================================
# 以下是基于 Semantic Scholar 的扩展工具
# ============================================================

@register_tool
class SearchByAuthorTool(Tool):
    """按作者搜索论文（基于 Semantic Scholar）"""

    @property
    def name(self) -> str:
        return "search_by_author"

    @property
    def description(self) -> str:
        return "按作者姓名搜索论文（基于 Semantic Scholar，可匿名调用；配置 S2_API_KEY 可提升配额）。"

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
        max_results: int = 20,
        **kwargs
    ) -> ToolResult:
        try:
            # 使用 Semantic Scholar 作者搜索
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
    """获取论文引用（基于 Semantic Scholar）"""

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
            # 使用 Semantic Scholar 获取引用
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
    """通过 DOI 查找论文（基于 Semantic Scholar）"""

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
            # 使用 Semantic Scholar DOI 查找
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
