#!/usr/bin/env python3
"""
XHS Paper Engine Automated Run Script
For launchd scheduled task invocation
"""

import sys
import json
import os
import argparse
import asyncio
from pathlib import Path
from datetime import datetime

# Add project directory to path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from dp_core.agent import XHSPaperEngineAgent
from dp_core.config import config


def build_search_task(keywords, days, s2_enabled) -> str:
    """Daily task: search arXiv (and optionally Semantic Scholar), select, publish."""
    search_steps = []
    step = 1
    for kw in keywords:
        prefix = "" if step == 1 else "If no results: "
        search_steps.append(f'{step}. {prefix}Search arXiv for "{kw}" from past {days} days')
        step += 1
    if s2_enabled:
        s2_days = max(days, 7)
        for kw in keywords:
            search_steps.append(
                f'{step}. If no results: search Semantic Scholar for "{kw}" from past {s2_days} days'
            )
            step += 1
    search_block = "\n        ".join(search_steps)

    return f"""
        Complete today's paper recommendation and publishing task:

        **Phase 1: Paper Search** (try in order until papers are found)
        {search_block}

        **Phase 2: Paper Selection** (once papers are found)
        {step}. Check for duplicates (pass the papers with titles to check_duplicate)
        {step + 1}. Select the best paper using select_best_paper
        {step + 2}. Download the paper PDF
        {step + 3}. Extract figures and tables from the PDF
        {step + 4}. Convert the PDF to Markdown
        - If extract_figures finds NO figures, that paper is unsuitable — go back and pick a
          different unpublished paper (never publish full-page screenshots).

        **Phase 3: Content Creation**
        {step + 5}. Write a Xiaohongshu post about the paper
        {step + 6}. Use optimize_xiaohongshu_with_vision to refine it and select 3-5 best images

        **Phase 4: Publishing**
        {step + 7}. Publish to Xiaohongshu (private), then record_publish

        **Important**:
        - Keep trying different search strategies until at least one paper is found.
        - The vision optimization step is important — don't skip it.
        """


def build_single_paper_task(pdf_path: str, title: str = None) -> str:
    """Targeted task: process one user-provided local PDF (skip search/selection)."""
    title_line = (
        f'The paper title is: "{title}".'
        if title else
        "Determine the paper's title and abstract from the converted Markdown (usually page 1)."
    )
    return f"""
        Process this specific paper the user provided. Do NOT search for papers.

        The paper PDF is located at:
        {pdf_path}

        Steps:
        1. Extract figures and tables from this PDF with extract_figures (use the path above).
           - If it yields NO figures, this paper is unsuitable for an image-heavy post — report
             that and stop. Do NOT switch to a different paper; the user chose this one.
        2. Convert the PDF to Markdown with convert_pdf_to_markdown.
        3. {title_line}
        4. Write a Xiaohongshu post with write_xiaohongshu (pass the title, abstract, and the
           converted Markdown as paper_content).
        5. Use optimize_xiaohongshu_with_vision to refine the post and select 3-5 best images.
        6. Publish to Xiaohongshu (private), then record_publish (use the PDF file name as the
           identifier, since there is no arXiv ID).

        The vision optimization step is important — don't skip it.
        """


async def main(args):
    """Run daily recommendation task"""
    # Base output dir; the agent creates the per-run <timestamp> subdir under it.
    base_output_dir = PROJECT_DIR / "output"
    base_output_dir.mkdir(parents=True, exist_ok=True)

    # Record run history
    history_file = PROJECT_DIR / "logs" / "run_history.json"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    success = False
    error_msg = None
    session_dir = None

    try:
        # Preflight: figure extraction is required — don't start without it.
        ok, msg = _check_figures_stack()
        if not ok:
            raise RuntimeError(msg)

        # Create Agent (it makes its own <timestamp> session dir under base_output_dir)
        agent = XHSPaperEngineAgent(
            max_steps=50,
            verbose=True,
            work_dir=str(PROJECT_DIR / "work"),
            output_dir=str(base_output_dir)
        )
        session_dir = agent.session_dir

        # Build the task: either a user-specified local PDF, or the daily search.
        if args.pdf:
            pdf_path = Path(args.pdf).expanduser().resolve()
            if not pdf_path.is_file():
                raise FileNotFoundError(f"--pdf not found: {pdf_path}")
            print(f"📄 Targeting a specific paper: {pdf_path}")
            task = build_single_paper_task(str(pdf_path), args.title)
        else:
            s2_enabled = _is_real_key(os.getenv("S2_API_KEY", ""))
            keywords = config.get("research.keywords", ["LLM"])
            keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()] or ["LLM"]
            days = args.recent_days if args.recent_days is not None else config.get("research.days", 3)
            task = build_search_task(keywords, days, s2_enabled)

        result = await agent.run(task.strip())
        success = result.success

        if not success:
            error_msg = result.error

    except Exception as e:
        error_msg = str(e)
        success = False

    finally:
        # Record run history
        duration = (datetime.now() - start_time).total_seconds()

        history = []
        if history_file.exists():
            with open(history_file, 'r') as f:
                history = json.load(f)

        history.append({
            "timestamp": start_time.isoformat(),
            "success": success,
            "error": error_msg,
            "duration_seconds": duration,
            "output_dir": str(session_dir) if session_dir else str(base_output_dir)
        })

        # Keep only the last 100 records
        history = history[-100:]

        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        # Output result
        if success:
            print(f"\n{'='*50}")
            print(f"XHS Paper Engine run completed successfully")
            print(f"Duration: {duration:.1f} seconds")
            print(f"{'='*50}")
            sys.exit(0)
        else:
            print(f"\n{'='*50}")
            print(f"XHS Paper Engine run failed: {error_msg}")
            print(f"{'='*50}")
            sys.exit(1)


def _check_figures_stack():
    """Verify the (required) figure-extraction backend is available.

    Figure extraction is a core capability — an image-heavy Xiaohongshu post is
    pointless without real figures. It runs via pdffigures2 (a Java JAR), so we
    need a Java runtime + the JAR. If missing we fail fast instead of degrading.
    Returns (ok: bool, message: str).
    """
    try:
        from dp_core import extract_figures_tables as ef
    except Exception as e:  # pragma: no cover - import-time failure
        return False, f"Cannot import figure-extraction module: {e}"
    return ef.backend_available()


def _is_real_key(value: str) -> bool:
    """True only if the env value is a real key (not empty and not a placeholder).

    The .env.example template ships placeholders like 'sk-your-...-api-key' and a
    row of 'x's; treat those as unconfigured so we never claim readiness or enable
    a data source with a junk key.
    """
    v = (value or "").strip().lower()
    if not v:
        return False
    if "your-" in v or "xxxx" in v or "api-key-here" in v:
        return False
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="XHS Paper Engine automated run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate environment and configuration without running the agent"
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=None,
        help="Override research.days: search papers from the past N days"
    )
    parser.add_argument(
        "--pdf",
        default=None,
        metavar="PATH",
        help="Process a specific local PDF instead of searching arXiv"
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional paper title to use with --pdf (otherwise inferred from the PDF)"
    )
    return parser.parse_args(argv)


def dry_run(args) -> int:
    """Validate environment and configuration without invoking the LLM/Agent."""
    print(f"\n{'='*50}")
    print("XHS Paper Engine dry-run (environment check)")
    print(f"{'='*50}")

    from dp_core.api_client import PROVIDERS, DEFAULT_PROVIDER

    provider = str(config.get("api.provider", DEFAULT_PROVIDER)).strip().lower()
    if provider not in PROVIDERS:
        print(f"Provider: {provider} (UNKNOWN — will fall back to {DEFAULT_PROVIDER})")
        provider = DEFAULT_PROVIDER
    else:
        print(f"Provider: {provider} ({PROVIDERS[provider]['label']})")

    key_var = PROVIDERS[provider]["api_key_env"]
    key_set = _is_real_key(os.getenv(key_var, ""))
    print(f"{key_var}: {'set' if key_set else 'MISSING or placeholder'}")

    s2_enabled = _is_real_key(os.getenv("S2_API_KEY", ""))
    print(f"S2_API_KEY: {'set (semantic enabled)' if s2_enabled else 'not set (semantic disabled)'}")

    keywords = [str(k).strip() for k in (config.get("research.keywords", []) or []) if str(k).strip()]
    days = args.recent_days if args.recent_days is not None else config.get("research.days", 3)
    print(f"Keywords: {keywords or ['LLM (default)']}")
    print(f"Search window: past {days} days")
    print(f"Text model: {config.get('llm.text.model', 'n/a')}")
    print(f"Vision model: {config.get('llm.vision.model', 'n/a')}")

    # Vision (VL) is required; every listed provider serves one.
    has_vl = bool(PROVIDERS.get(provider, {}).get("vision", False))

    figures_ok, figures_msg = _check_figures_stack()
    print(f"Figure extraction stack: {'installed' if figures_ok else 'MISSING (required)'}")

    print(f"{'='*50}")
    if not key_set:
        print(f"❌ {key_var} is not configured. Set it in your .env file before running.")
        return 1
    if not has_vl:
        print(f"❌ Provider '{provider}' has no VL model (required). Choose a VL-capable provider.")
        return 1
    if not figures_ok:
        print(f"❌ {figures_msg}")
        return 1
    print("✅ Environment looks ready.")
    return 0


def run():
    args = parse_args()
    if args.dry_run:
        sys.exit(dry_run(args))
    asyncio.run(main(args))


if __name__ == "__main__":
    run()
