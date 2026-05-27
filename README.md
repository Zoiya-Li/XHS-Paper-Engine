# XHS Paper Engine

> An Automated Paper Recommendation and Publishing System based on ReAct Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

XHS Paper Engine is an intelligent academic paper recommendation and publishing system that automatically searches, filters, downloads the latest papers, and generates content suitable for social media publishing.

> ## ⚠️ Disclaimer — Read Before Use
>
> This project is provided **for learning and research purposes only**. Use it at your own risk.
>
> - The Xiaohongshu (Little Red Book) publishing feature uses **browser automation** to operate the creator backend. This **bypasses the official API and very likely violates Xiaohongshu's Terms of Service**, and **may result in your account being restricted or banned**.
> - Automated publishing is **disabled by default**. You must explicitly opt in via `publish.xiaohongshu.enabled: true` in `config.yaml`. Without it, the pipeline stops after generating a local draft.
> - This tool generates content with LLMs. **You are responsible** for reviewing accuracy, respecting the cited papers' licenses, and complying with the platform's content rules. Do not use it to mass-produce low-quality or misleading content.
> - The authors accept **no liability** for account bans, data loss, or any other consequences of using this software.
>
> See [Ethical Use](#ethical-use) and [Security & Privacy](#security--privacy) below.

## Features

- **Intelligent Paper Search**: Supports multiple academic data sources including arXiv and Semantic Scholar (optional)
- **Automatic Deduplication**: Smart deduplication mechanism based on title similarity and publication history
- **Paper Selection**: Uses LLM to score papers across multiple dimensions and automatically selects the most valuable ones
- **PDF Processing**: Automatically downloads PDFs, extracts images, and converts to Markdown
- **Content Generation**: Automatically generates content for Xiaohongshu (Little Red Book) posts
- **Auto Publishing**: Supports publishing to Xiaohongshu
- **Configurable**: Flexibly adjust various parameters through YAML configuration file
- **Provider Optionality**: Supports SiliconFlow or OpenRouter for text models
- **PDF text extraction**: Reads the PDF text layer with PyMuPDF (fast, free; works for arXiv-style born-digital PDFs), falling back to `pdftotext` for scanned PDFs

## Architecture

```
XHS Paper Engine
├── dp_core/              # Core module
│   ├── agent.py         # ReAct Agent implementation
│   ├── api_client.py    # LLM API client (SiliconFlow/OpenRouter)
│   ├── config.py        # Configuration management
│   ├── retry.py         # Retry mechanism
│   ├── analytics.py     # Data analytics
│   ├── dedup.py         # Deduplication logic
│   ├── tools/           # Agent toolset
│   │   ├── paper_tools.py      # Paper search, download, processing
│   │   ├── writing_tools.py    # Content generation
│   │   ├── publish_tools.py    # Publishing tools
│   │   └── analytics_tools.py  # Analytics tools
│   └── publishers/      # Publishers
│       └── xiaohongshu.py      # Xiaohongshu publisher
├── config.yaml          # Configuration file
├── .env.example         # Environment variable template
└── auto_run.py          # Automated run entry point
```

## Quick Start

### 1. Install Dependencies

> **Figure extraction is required.** An image-heavy Xiaohongshu post needs real
> figures, so the project **refuses to start** if the figure-extraction backend
> is missing — there is no page-screenshot fallback. If a given paper yields no
> extractable figures, the agent simply picks a different paper.
>
> Figures are extracted by [pdffigures2](https://github.com/allenai/pdffigures2),
> which runs as a self-contained **Java JAR** — no Python ML stack, no GPU, no
> model download. You need a **Java runtime** + the **pdffigures2 JAR**.

```bash
# Clone the repository
git clone https://github.com/Zoiya-Li/XHS-Paper-Engine.git
cd XHS-Paper-Engine

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install Python dependencies (lightweight — no torch/detectron2)
pip install -r requirements.txt
# or, as a package:  pip install .

# Install the Playwright browser (needed for publishing)
playwright install chromium
```

**Install the figure-extraction backend (required): Java + the pdffigures2 JAR**

```bash
# 1) A Java runtime (JRE 11+)
# macOS:   brew install openjdk
# Linux:   sudo apt-get install -y default-jre
# Windows: choco install temurin   (or install Adoptium Temurin)

# 2) The pdffigures2 fat JAR -> ~/.xhs-paper-engine/pdffigures2.jar
#    Option A: build it (requires Docker; one-off, ~a few minutes)
./scripts/build_pdffigures2_jar.sh
#    Option B: download a prebuilt JAR from the project releases and drop it at
#              ~/.xhs-paper-engine/pdffigures2.jar
```

The JAR location is resolved from `PDFFIGURES2_JAR`, then `extraction.pdffigures2_jar`
in `config.yaml`, then the default `~/.xhs-paper-engine/pdffigures2.jar`.

Optional **PDF text fallback** (poppler's `pdftotext`, used only for PDFs without a text layer, e.g. scans):

```bash
# macOS
brew install poppler
# Linux:   sudo apt-get install -y poppler-utils
# Windows: choco install poppler   (or: scoop install poppler)
```

> Verify everything is ready with `python auto_run.py --dry-run` — it checks the
> API key, Java, and the JAR, and refuses to run if the figure backend is missing.

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` file:

```bash
# Required: SiliconFlow API Key (default text + vision model)
SILICONFLOW_API_KEY=sk-your-api-key-here

# Optional: OpenRouter (set api.provider=openrouter in config.yaml)
OPENROUTER_API_KEY=sk-your-openrouter-api-key
# Optional metadata for OpenRouter ranking/analytics
OPENROUTER_SITE_URL=https://your.site
OPENROUTER_APP_NAME=XHSPaperEngine

# Optional: Semantic Scholar API Key
S2_API_KEY=your-s2-api-key
```

If you don't provide `S2_API_KEY`, the system still runs normally, and Semantic Scholar is disabled by default. To enable it, set the key and add `"semantic"` to `research.sources` in `config.yaml`.

### 3. Run

#### Run

```bash
python auto_run.py
```

## Configuration

Edit `config.yaml` to adjust the following parameters:

### Research Configuration

```yaml
research:
  keywords:
    - "Multi-Agent System Memory"
  categories:
    - "cs.AI"
    - "cs.CL"
    - "cs.LG"
  days: 3  # Search for papers from the past N days
```

Edit `research.keywords` in `config.yaml` to change the search topic.

### LLM Parameters

```yaml
llm:
  # Unified text-to-text model (chat/selection/xiaohongshu)
  text:
    model: "deepseek-ai/DeepSeek-V3"
    temperature: 0.7
    max_tokens: 3000
  # Vision model (image analysis/optimization)
  vision:
    model: "Qwen/Qwen3-VL-235B-A22B-Instruct"
```

Notes:
- **text**: used for all text-only tasks (paper selection, writing, polishing)
- **vision**: used for image understanding/selection

PDF→text conversion uses PyMuPDF's text layer (no model/API needed) and only falls back to `pdftotext` for scanned PDFs — there is no LLM-based OCR step.

### Optional data sources

- **Semantic Scholar**: requires `S2_API_KEY`

### LLM Provider

Set `api.provider` in `config.yaml` and the matching key in `.env`. You only need
**one** provider. **A vision (VL) model is required** (to select figures and align
captions), so every listed provider serves one — the selected provider handles both
text and vision.

| `api.provider` | Provider | API key env var | Example text / vision model |
|----------------|----------|-----------------|------------------------------|
| `siliconflow` (default) | 硅基流动 SiliconFlow (CN) | `SILICONFLOW_API_KEY` | `deepseek-ai/DeepSeek-V3` / `Qwen/Qwen3-VL-235B-A22B-Instruct` |
| `dashscope` | 阿里云百炼 / 通义千问 (CN) | `DASHSCOPE_API_KEY` | `qwen-plus` / `qwen-vl-max` |
| `moonshot` | 月之暗面 Kimi (CN) | `MOONSHOT_API_KEY` | `kimi-k2.5` / `kimi-k2.5` (multimodal; set `llm.text.temperature: 1`) |
| `zhipu` | 智谱 GLM (CN) | `ZHIPU_API_KEY` | `glm-4-plus` / `glm-4v-plus` |
| `openrouter` | OpenRouter (international) | `OPENROUTER_API_KEY` | `deepseek/deepseek-chat` / `qwen/qwen2.5-vl-72b-instruct` |
| `custom` | any OpenAI-compatible endpoint | `CUSTOM_API_KEY` | (your model) |

```yaml
api:
  provider: "siliconflow"       # pick one from the table above
llm:
  text:
    model: "deepseek-ai/DeepSeek-V3"            # a text model the provider serves
  vision:
    model: "Qwen/Qwen3-VL-235B-A22B-Instruct"   # a VL model the provider serves
```

For a self-hosted / unlisted endpoint, use `custom` (you must point it at a
VL-capable model):

```yaml
api:
  provider: "custom"
  custom:
    base_url: "https://your-endpoint.example.com/v1"
```

> Note: switching provider means switching the **model names** too — each serves different model ids. `python auto_run.py --dry-run` checks the provider is VL-capable and has a key, and refuses to run otherwise.

## Permissions & Login

- **Xiaohongshu**: First publish requires QR code login. A Playwright browser window will open for scanning. Cookies are saved to `~/.xhs-paper-engine/` for subsequent runs.

### Publishing Parameters

```yaml
publish:
  xiaohongshu:
    save_as_draft: false
    visibility: private  # public or private
    max_content_len: 1000  # Xiaohongshu content length limit
```

For more configuration options, please refer to the comments in `config.yaml`.

## Agent Tools

XHS Paper Engine provides the following Agent tools:

| Tool Name | Function |
|-----------|----------|
| `search_papers` | Search papers (supports arXiv/Semantic Scholar) |
| `search_by_author` | Search papers by author |
| `get_citations` | Get citations for a paper |
| `lookup_by_doi` | Lookup paper by DOI |
| `check_duplicate` | Check if a paper has been published |
| `select_best_paper` | Select the best paper |
| `download_paper` | Download paper PDF |
| `extract_figures` | Extract images from papers |
| `convert_pdf_to_markdown` | Convert PDF to Markdown |
| `analyze_images_with_vision` | Analyze image content with vision model |
| `write_blog` | Generate blog article |
| `write_xiaohongshu` | Generate Xiaohongshu post |
| `login_xiaohongshu` | Trigger QR login for Xiaohongshu |
| `publish_xiaohongshu` | Publish to Xiaohongshu |
| `record_publish` | Record publish history |
| `get_publish_history` | Get publish history |

## Scheduled Tasks Setup

### macOS (launchd)

```bash
./setup_schedule.sh install     # Install scheduled tasks (daily at 06:00 and 18:00)
./setup_schedule.sh status      # Show task status and recent run history
./setup_schedule.sh test        # Validate environment without running (dry-run)
./setup_schedule.sh run         # Run once immediately
./setup_schedule.sh uninstall   # Remove scheduled tasks
```

`install` renders the `launchd/*.plist` templates with your current project path
and home directory, then loads them. Override the Python interpreter with the
`XHS_PAPER_ENGINE_PYTHON` environment variable if needed.

### Linux (crontab)

```bash
# Edit crontab
crontab -e

# Add the following line (runs at 6:00 and 18:00 daily)
0 6,18 * * * cd /path/to/xhs-paper-engine && /usr/bin/python3 auto_run.py
```

### Windows (Task Scheduler)

Option A (GUI):
1. Open Task Scheduler → Create Task
2. Action: Start a program
3. Program/script: `python`
4. Add arguments: `auto_run.py`
5. Start in: your XHS Paper Engine project directory

Option B (Command line):
```bat
schtasks /Create /TN "XHSPaperEngine" /TR "\"C:\Path\To\python.exe\" \"C:\Path\To\xhs-paper-engine\auto_run.py\"" /SC DAILY /ST 06:00
```

## Development

### Project Structure

- `dp_core/agent.py`: ReAct Agent core implementation
- `dp_core/tools/`: Tools callable by the Agent
- `dp_core/publishers/`: Publishers for different platforms
- `config.yaml`: Centralized configuration file
- `.env`: Sensitive information configuration (not committed to version control)

### Adding New Tools

1. Create a new file in `dp_core/tools/`
2. Inherit from `Tool` base class and implement the `execute` method
3. Use `@register_tool` decorator to register
4. Export in `dp_core/tools/__init__.py`

Example:

```python
from typing import List
from .base import Tool, ToolParameter, ToolResult, register_tool

@register_tool
class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "My tool description"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("param1", "string", "Parameter 1 description", required=True),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        # Implement your logic
        return ToolResult(success=True, data={"result": "..."})
```

Note: `@register_tool` is a plain decorator (no arguments) — it instantiates and
registers the class on the global registry. `name`, `description`, and
`parameters` are properties, and `ToolParameter.type` is a string such as
`"string"`, `"integer"`, `"boolean"`, or `"array"`.

## Ethical Use

This pipeline can generate and publish content at scale. Please use it responsibly:

- **Review before publishing.** LLM-generated summaries can contain errors or misrepresent a paper. Always read the draft yourself.
- **Don't spam.** Mass-posting auto-generated content degrades the platform and misleads readers. Prefer drafts/private visibility and a human in the loop.
- **Respect sources.** Cite papers accurately, honor their licenses, and don't republish figures where licensing forbids it.
- **Be transparent.** Consider disclosing that content is AI-assisted.

Automated publishing is opt-in (`publish.xiaohongshu.enabled`) precisely so that running the pipeline never posts to a live account by accident.

## Security & Privacy

- **Login cookies** are stored **in plaintext** under `~/.xhs-paper-engine/xiaohongshu_cookies.json`. These are equivalent to your account credentials — protect this directory, do not commit it, and revoke the session if your machine is shared or compromised.
- **API keys** are read from `.env` (git-ignored). Never commit real keys.
- **Third-party data flow.** Paper text (sent to the LLM) and extracted figures (sent to the vision model) go to external services (SiliconFlow/OpenRouter). Do **not** run this on confidential or unpublished papers you are not allowed to share.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Provided "as is", without warranty of any kind. See the [Disclaimer](#️-disclaimer--read-before-use) above.

## Contributing

Contributions are welcome! Please feel free to submit Issues and Pull Requests!

## Acknowledgments

- [DeepSeek](https://www.deepseek.com/) - LLM API support
- [Playwright](https://playwright.dev/) - Browser automation framework
- [arXiv](https://arxiv.org/), [Semantic Scholar](https://www.semanticscholar.org/) - Paper data sources
