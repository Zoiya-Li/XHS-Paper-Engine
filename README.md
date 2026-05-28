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
> - Automated publishing is **on by default** (`publish.xiaohongshu.enabled: true`) — this is a publishing tool. Posts default to **private (only-self) visibility** as a safety net. Set `enabled: false` to stop after generating a local draft, and review before making anything public.
> - This tool generates content with LLMs. **You are responsible** for reviewing accuracy, respecting the cited papers' licenses, and complying with the platform's content rules. Do not use it to mass-produce low-quality or misleading content.
> - The authors accept **no liability** for account bans, data loss, or any other consequences of using this software.
>
> See [Ethical Use](#ethical-use) and [Security & Privacy](#security--privacy) below.

## Features

- **Intelligent Paper Search**: arXiv and (optional) Semantic Scholar, filtered to the last N days
- **Targeted Mode**: process a specific local PDF you provide via `--pdf` (skips search)
- **Automatic Deduplication**: by arXiv ID and title similarity vs. publication history
- **Paper Selection**: LLM scores candidate papers and picks the most shareable one
- **Figure/Table Extraction**: [pdffigures2](https://github.com/allenai/pdffigures2) (Java JAR) — clean figure crops + captions, no Python ML stack
- **PDF→Text**: PyMuPDF text layer (fast, free), falling back to `pdftotext` for scans
- **Content + Vision**: generates a Xiaohongshu post, then a vision (VL) model selects the best images and aligns the text
- **Auto Publishing**: publishes to Xiaohongshu (browser automation; private by default)
- **Multiple LLM Providers**: SiliconFlow, DashScope/Qwen, Moonshot/Kimi, Zhipu/GLM, OpenRouter, or any OpenAI-compatible endpoint
- **Cross-platform Scheduling**: one daily auto-run on macOS (launchd), Windows (Task Scheduler), or Linux (cron)
- **Configurable**: all parameters via `config.yaml`

## Architecture

```
XHS Paper Engine
├── dp_core/              # Core module
│   ├── agent.py                 # Agent loop (native function calling + ReAct fallback)
│   ├── api_client.py            # LLM client for any OpenAI-compatible provider
│   ├── config.py                # Configuration management
│   ├── retry.py                 # Retry mechanism
│   ├── analytics.py             # Publication recording (backs deduplication)
│   ├── dedup.py                 # Deduplication logic
│   ├── extract_figures_tables.py# Figure/table extraction via pdffigures2
│   ├── scheduler.py             # Cross-platform daily scheduling
│   ├── tools/                   # Agent toolset
│   │   ├── paper_tools.py            # Search, dedup, download, extract, PDF→text
│   │   ├── writing_tools.py          # Blog / Xiaohongshu content generation
│   │   ├── vision_optimization_tools.py  # VL image selection + post optimization
│   │   ├── publish_tools.py          # Login, publish, record
│   │   └── analytics_tools.py        # Publish history
│   └── publishers/
│       └── xiaohongshu.py            # Xiaohongshu publisher (Playwright)
├── docker/pdffigures2.Dockerfile     # Builder image for the pdffigures2 JAR
├── scripts/build_pdffigures2_jar.sh  # One-off JAR build helper
├── config.yaml          # Configuration file
├── .env.example         # Environment variable template
└── auto_run.py          # Entry point (daily run / --pdf / --dry-run / scheduling)
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
#    Option A: build it with Docker (one-off, ~a few minutes)
./scripts/build_pdffigures2_jar.sh
#    Option B: download a prebuilt JAR from the project releases and drop it at
#              ~/.xhs-paper-engine/pdffigures2.jar
#    Option C: manual build without Docker (macOS/Linux example)
#       pdffigures2 requires sbt 1.7.x; newer sbt versions are incompatible.
#       brew install sbt          # installs latest sbt — may be too new
#       curl -fL -o /tmp/sbt-launch-1.7.1.jar \
#         https://repo1.maven.org/maven2/org/scala-sbt/sbt-launch/1.7.1/sbt-launch-1.7.1.jar
#       git clone --depth 1 https://github.com/allenai/pdffigures2.git /tmp/pdffigures2
#       cd /tmp/pdffigures2 && java -jar /tmp/sbt-launch-1.7.1.jar -batch assembly
#       mkdir -p ~/.xhs-paper-engine && cp /tmp/pdffigures2/pdffigures2.jar ~/.xhs-paper-engine/
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

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your API key:

```bash
cp .env.example .env
```

Edit `.env`. You only need the key for the **one** provider you will use (default is `siliconflow`):

```bash
# Default provider: SiliconFlow (text + vision)
SILICONFLOW_API_KEY=sk-your-api-key-here

# Optional: Semantic Scholar (enables the `semantic` data source)
S2_API_KEY=your-s2-api-key
```

See `.env.example` for keys of other providers.

### 3. Edit `config.yaml`

Before running, open `config.yaml` and change at least these two sections:

**Research topic** — what papers to search for:
```yaml
research:
  keywords:
    - "LLM"
    - "Computer Vision"
```

**LLM provider & models** — must match the API key you set in `.env`:
```yaml
api:
  provider: "siliconflow"   # or dashscope / moonshot / zhipu / openrouter

llm:
  text:
    model: "deepseek-ai/DeepSeek-V3"
  vision:
    model: "Qwen/Qwen3-VL-32B-Instruct"
```

> A **vision (VL) model is required** — it picks the best figures and aligns the post text to them. `python auto_run.py --dry-run` checks that your provider + key + model combo actually works.

### 4. Verify

```bash
python auto_run.py --dry-run
```

This validates your API key, the VL model, Java, and the pdffigures2 JAR — without starting the agent. Fix any errors it reports before proceeding.

### 5. Run

```bash
# Daily mode: search arXiv, pick a paper, generate & publish (private by default)
python auto_run.py

# Or process a specific PDF you already have (skips search)
python auto_run.py --pdf /path/to/paper.pdf
```

**What happens on the first run:**
1. The agent searches arXiv, downloads a paper, extracts figures, and writes a post.
2. A **Chromium browser window pops up** for **Xiaohongshu QR-code login**. Open your phone's 小红书 App → scan the code → the browser will close automatically. Your session is saved to `~/.xhs-paper-engine/xiaohongshu_cookies.json`; later runs reuse it without re-scanning.
3. The post is published as **private (仅自己可见)** — you review it before making it public.

> **Set `publish.xiaohongshu.enabled: false`** in `config.yaml` if you want to stop at the local draft and never trigger the browser.

### 6. After Your First Run — Review Before Going Public

All generated files are saved under `output/<timestamp>/`:

```
output/20260528_123456/
├── papers/paper.pdf          # downloaded PDF
├── figures/                  # extracted figure images
├── tables/                   # extracted table images
├── markdown/paper.md         # converted text
└── posts/xiaohongshu_post.md # generated post (title + content + tags)
```

The post is already on your Xiaohongshu account as a **private note**:
1. Open the 小红书 App → **我** → **私密笔记**.
2. Find the auto-generated post, read it carefully.
3. Edit if needed (fix facts, tone, images).
4. When satisfied, change visibility from **私密** to **公开**.

Only switch to public after you've personally reviewed the content — LLM-generated summaries can contain errors or misrepresent a paper.

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

- **Xiaohongshu**: The first publish requires a QR-code login. A Playwright browser window opens for scanning. After one successful scan, the full session state (cookies + localStorage) is saved to `~/.xhs-paper-engine/xiaohongshu_cookies.json`, and later runs reuse it without re-scanning. Delete that file to force a fresh login.

### Publishing Parameters

```yaml
publish:
  xiaohongshu:
    enabled: true        # publish automatically; set false to stop at the draft
    save_as_draft: false
    visibility: private  # public or private (private = only-self)
    max_content_len: 1000  # Xiaohongshu content length limit
```

**Why private by default?**  
Auto-generated content can contain errors or misrepresent a paper. The default `visibility: private` lets you open the post in your Xiaohongshu app, review and edit it, then manually switch to public when you're satisfied. Set `enabled: false` if you prefer to stop at the local draft file instead.

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
| `extract_figures` | Extract figures/tables from a paper (pdffigures2) |
| `convert_pdf_to_markdown` | Convert PDF to text/Markdown |
| `write_blog` | Generate a blog article (draft export) |
| `write_xiaohongshu` | Generate a Xiaohongshu post |
| `optimize_xiaohongshu_with_vision` | VL model selects best images + refines the post |
| `analyze_images_with_vision` | Analyze image content with the vision model |
| `login_xiaohongshu` | Trigger QR login for Xiaohongshu |
| `publish_xiaohongshu` | Publish to Xiaohongshu |
| `record_publish` | Record publish history |
| `get_publish_history` | Get publish history |
| `read_file` / `list_files` | Read a file / list a directory (utility) |

## Scheduled Tasks Setup

The app can schedule a **daily run for you, cross-platform** — it detects the OS
and uses the right mechanism (macOS launchd / Windows Task Scheduler / Linux cron).

**Easiest:** after your first interactive run, it asks whether to set up a daily
schedule. Answer `y` and it's installed. (Scheduled/background runs never re-ask —
they have no terminal.)

**Or manage it explicitly:**

```bash
python auto_run.py --install-schedule     # install a daily run (default 09:00) for this OS
python auto_run.py --uninstall-schedule   # remove it
python auto_run.py --no-schedule          # run once without the setup prompt
```

| OS | Mechanism | Where it lives |
|----|-----------|----------------|
| macOS | launchd LaunchAgent | `~/Library/LaunchAgents/com.xhs-paper-engine.daily.plist` |
| Windows | Task Scheduler | task `XHSPaperEngine` |
| Linux | crontab | a line tagged `# xhs-paper-engine-daily` |

It schedules the **current Python interpreter** (your venv) running `auto_run.py`,
so activate/point at the right environment when installing.

> The older macOS-only `setup_schedule.sh` (twice-daily launchd templates) still
> works if you prefer it, but the built-in `--install-schedule` is the portable path.

## Troubleshooting

Run `python auto_run.py --dry-run` first — it validates the API key, the VL model, and the figure-extraction stack without invoking the agent.

**Figure extraction fails with "Unable to locate a Java Runtime"**
pdffigures2 needs a real Java runtime. On macOS, `/usr/bin/java` is only a *stub* that fails at runtime when no JDK is installed — having it on `PATH` is not enough. Install a real JDK (`brew install openjdk`; Linux `sudo apt-get install -y default-jre`; Windows `choco install temurin`). The app verifies java actually runs and also checks the Homebrew keg-only location automatically.

**Vision step fails with `403 Forbidden`**
Your provider/account may not have access to the configured VL model (e.g. a SiliconFlow account without that specific `Qwen…-VL` model). Switch `api.provider` (or `llm.vision.model`) in `config.yaml` to a vision model you can access — OpenRouter is a reliable fallback. A VL model is required; the run won't curate images without it.

**It keeps asking me to scan the QR code**
A successful scan saves your session to `~/.xhs-paper-engine/xiaohongshu_cookies.json`; later runs reuse it. If you're re-prompted every run, make sure that file exists and is writable. (Login is only considered valid after the page settles — the creator dashboard redirects guests to `/login` after ~5s, so the check waits for that.)

**Publishing reaches the editor but can't click a button / set visibility**
Xiaohongshu's web UI changes often and the automation targets specific selectors (the publish control is a custom `<xhs-publish-btn>` element, and a topic-suggestion popup can overlay it). When a step fails, a debug screenshot is saved to `~/.xhs-paper-engine/debug/`. Open it, then update the selector lists near the top of `dp_core/publishers/xiaohongshu.py` and bump `SELECTORS_LAST_VERIFIED`. Automated publishing is inherently fragile — there is no stable public API.

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

Automated publishing is on by default but posts as **private (only-self)** visibility, so review your notes before switching any to public. Set `publish.xiaohongshu.enabled: false` to stop at the draft stage.

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

- [pdffigures2](https://github.com/allenai/pdffigures2) (Allen Institute for AI) - figure/table extraction
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF text extraction
- [Playwright](https://playwright.dev/) - Browser automation framework
- [arXiv](https://arxiv.org/), [Semantic Scholar](https://www.semanticscholar.org/) - Paper data sources
- LLM providers: SiliconFlow, Alibaba DashScope, Moonshot, Zhipu, OpenRouter
