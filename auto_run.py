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


async def main(args):
    """Run daily recommendation task"""
    # Create output directory
    output_dir = PROJECT_DIR / "output" / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Record run history
    history_file = PROJECT_DIR / "logs" / "run_history.json"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    success = False
    error_msg = None

    try:
        # Preflight: figure extraction is required — don't start without it.
        ok, msg = _check_figures_stack()
        if not ok:
            raise RuntimeError(msg)

        # Create Agent
        agent = XHSPaperEngineAgent(
            max_steps=50,
            verbose=True,
            work_dir=str(PROJECT_DIR / "work"),
            output_dir=str(output_dir)
        )

        # Build task based on available sources and configured keywords
        s2_enabled = _is_real_key(os.getenv("S2_API_KEY", ""))

        keywords = config.get("research.keywords", ["LLM"])
        days = args.recent_days if args.recent_days is not None else config.get("research.days", 3)
        keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()]
        if not keywords:
            keywords = ["LLM"]

        search_steps = []
        step = 1
        for kw in keywords:
            prefix = "" if step == 1 else "If no results: "
            search_steps.append(
                f'{step}. {prefix}Search arXiv for "{kw}" from past {days} days'
            )
            step += 1

        if s2_enabled:
            s2_days = max(days, 7)
            for kw in keywords:
                search_steps.append(
                    f'{step}. If no results: search Semantic Scholar for "{kw}" from past {s2_days} days'
                )
                step += 1

        search_block = "\n        ".join(search_steps)

        phase2_steps = [
            "Check for duplicates (compare with previously published papers)",
            "Select the best paper using select_best_paper tool",
            "Download paper PDF",
            "Extract figures and tables from PDF",
            "Convert PDF to Markdown format",
        ]
        phase3_steps = [
            "Write Xiaohongshu post about the paper",
            "Use optimize_xiaohongshu_with_vision to optimize the post and select best images (3-5 images)",
        ]
        phase4_steps = [
            "Publish to Xiaohongshu (set to private visibility)",
            "Record publish history",
        ]

        def _format_steps(start: int, items: list) -> tuple[list, int]:
            lines = []
            current = start
            for item in items:
                lines.append(f"{current}. {item}")
                current += 1
            return lines, current

        phase2_lines, step = _format_steps(step, phase2_steps)
        phase3_lines, step = _format_steps(step, phase3_steps)
        phase4_lines, step = _format_steps(step, phase4_steps)
        phase2_block = "\n        ".join(phase2_lines)
        phase3_block = "\n        ".join(phase3_lines)
        phase4_block = "\n        ".join(phase4_lines)

        # Run daily task
        task = f"""
        Complete today's paper recommendation and publishing task:

        **Phase 1: Paper Search** (try in order until papers are found)
        {search_block}

        **Phase 2: Paper Selection** (once papers are found)
        {phase2_block}

        **Phase 3: Content Creation** (for selected paper)
        {phase3_block}

        **Phase 4: Publishing**
        {phase4_block}

        **Important Notes**:
        - Keep trying different search strategies until you find at least one paper
        - If absolutely no papers found after all attempts, report the specific search terms tried and suggest alternative topics
        - The vision optimization step is important - don't skip it
        """

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
            "output_dir": str(output_dir)
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

    figures_ok, figures_msg = _check_figures_stack()
    print(f"Figure extraction stack: {'installed' if figures_ok else 'MISSING (required)'}")

    print(f"{'='*50}")
    if not key_set:
        print(f"❌ {key_var} is not configured. Set it in your .env file before running.")
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
