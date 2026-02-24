# XHS Paper Engine

> An Automated Paper Recommendation and Publishing System based on ReAct Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

XHS Paper Engine is an intelligent academic paper recommendation and publishing system that automatically searches, filters, downloads the latest papers, and generates content suitable for social media publishing.

## Features

- **Intelligent Paper Search**: Supports multiple academic data sources including arXiv and Semantic Scholar (optional)
- **Automatic Deduplication**: Smart deduplication mechanism based on title similarity and publication history
- **Paper Selection**: Uses LLM to score papers across multiple dimensions and automatically selects the most valuable ones
- **PDF Processing**: Automatically downloads PDFs, extracts images, and converts to Markdown
- **Content Generation**: Automatically generates content for Xiaohongshu (Little Red Book) posts
- **Auto Publishing**: Supports publishing to Xiaohongshu
- **Configurable**: Flexibly adjust various parameters through YAML configuration file
- **Provider Optionality**: Supports SiliconFlow or OpenRouter for text models, with OCR fallback to `pdftotext` when using OpenRouter

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

**Using uv (recommended, one-shot):**

macOS/Linux:
```bash
./scripts/setup_env_uv.sh --all
```

Windows (PowerShell):
```powershell
# If scripts are blocked:
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_env_uv.ps1 --all
```

**Windows (PowerShell) one-shot setup (pip):**

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_env.ps1 --all
```

```bash
# Clone the repository
git clone https://github.com/yourusername/xhs-paper-engine.git
cd xhs-paper-engine

# One-shot setup (macOS/Linux)
./scripts/setup_env.sh --all

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Install detectron2 (required for figure/table extraction)
# macOS (source install):
#   git clone https://github.com/facebookresearch/detectron2.git
#   # If GitHub is blocked, use Gitee mirror:
#   # git clone https://gitee.com/facebookresearch/detectron2.git
#   cd detectron2
#   # Intel Mac:
#   CC=clang CXX=clang++ ARCHFLAGS="-arch x86_64" python -m pip install -e .
#   # Apple Silicon (M1/M2/M3):
#   CC=clang CXX=clang++ ARCHFLAGS="-arch arm64" python -m pip install -e .
#   cd ..
#
# Notes:
# - detectron2 must be compiled against your current PyTorch.
# - You may need: ninja, fvcore, iopath.
# - PubLayNet weights will be downloaded automatically by layoutparser.
#   To use a local model, set `extraction.model_dir` in config.yaml
#   or export `PUBLAYNET_MODEL_DIR=/path/to/model_dir` (must contain config.yml + model_final.pth).
#
# Windows:
# - detectron2 source install is not automated here. Use WSL2 or follow detectron2's official Windows guide.

**Important**: detectron2 is mandatory if you want real figure/table extraction (not just page screenshots). Please install it as above.

The first time you run figure extraction, the PubLayNet model files (~800MB) will be downloaded automatically to `~/.xhs-paper-engine/publaynet` if you haven't provided a local model directory.

# Optional: OCR fallback (used when api.provider=openrouter or no SiliconFlow key)
# macOS:
brew install poppler
# Linux:
#   sudo apt-get install -y poppler-utils
# Windows:
#   choco install poppler
#   # or: scoop install poppler
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` file:

```bash
# Required: SiliconFlow API Key (default text + OCR)
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
  # OCR model (SiliconFlow only)
  ocr:
    model: "deepseek-ai/DeepSeek-OCR"
```

Notes:
- **text**: used for all text-only tasks (paper selection, writing, polishing)
- **vision**: used for image understanding/selection
- **ocr**: only used with SiliconFlow; if `api.provider=openrouter` or no SiliconFlow key, OCR falls back to `pdftotext`

### Optional data sources

- **Semantic Scholar**: requires `S2_API_KEY`

### LLM Provider (SiliconFlow / OpenRouter)

```yaml
api:
  provider: "siliconflow"   # or "openrouter"
  openrouter:
    base_url: "https://openrouter.ai/api/v1"
```

**OCR fallback**: if `api.provider=openrouter` or no `SILICONFLOW_API_KEY` is set, PDF OCR falls back to Poppler `pdftotext` (install via `brew install poppler` on macOS).

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
| `capture_pdf_pages` | Screenshot PDF pages if extraction fails |
| `convert_pdf_to_markdown` | Convert PDF to Markdown |
| `select_best_images` | Select best images for publishing |
| `analyze_images` | Analyze image metadata |
| `analyze_images_with_vision` | Analyze image content with vision model |
| `write_blog` | Generate blog article |
| `write_xiaohongshu` | Generate Xiaohongshu post |
| `login_xiaohongshu` | Trigger QR login for Xiaohongshu |
| `publish_xiaohongshu` | Publish to Xiaohongshu |
| `record_publish` | Record publish history |
| `get_analytics` | Get runtime statistics |
| `get_publish_recommendation` | Get publish recommendations |
| `get_publish_history` | Get publish history |

## Scheduled Tasks Setup

### macOS (launchd)

```bash
./setup_schedule.sh
```

This script renders the `launchd/*.plist` templates with your current project path and home directory.

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
from .base import Tool, ToolParameter, ToolResult, register_tool

@register_tool(
    name="my_tool",
    description="My tool description",
    parameters=[
        ToolParameter("param1", str, "Parameter 1 description", required=True),
    ]
)
class MyTool(Tool):
    async def execute(self, **kwargs) -> ToolResult:
        # Implement your logic
        return ToolResult.success(data={"result": "..."})
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details

## Contributing

Contributions are welcome! Please feel free to submit Issues and Pull Requests!

## Acknowledgments

- [DeepSeek](https://www.deepseek.com/) - LLM API support
- [Playwright](https://playwright.dev/) - Browser automation framework
- [arXiv](https://arxiv.org/), [Semantic Scholar](https://www.semanticscholar.org/) - Paper data sources
