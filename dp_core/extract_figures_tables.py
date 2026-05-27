#!/usr/bin/env python
"""
Extract figures and tables from scholarly PDFs using pdffigures2 (Allen AI).

pdffigures2 is a purpose-built tool for scientific PDFs: it locates figures and
tables by reasoning about captions and empty regions, and produces clean, tightly
cropped images plus caption metadata — no post-processing needed. We run it as a
self-contained fat JAR via a local Java runtime (no Python ML stack, no Docker at
runtime).

Requirements:
    - A Java runtime (JRE 11+). macOS: `brew install openjdk`.
    - The pdffigures2 fat JAR. Resolved from (in order):
        1. env  PDFFIGURES2_JAR
        2. config  extraction.pdffigures2_jar
        3. default  ~/.xhs-paper-engine/pdffigures2.jar
      See the README for how to obtain/build it.

Usage (CLI):
    python -m dp_core.extract_figures_tables --pdf paper.pdf --output-dir ./out

Or from code:
    from dp_core.extract_figures_tables import extract_figures_and_tables
    extract_figures_and_tables("paper.pdf", "./out")
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import tempfile
from pathlib import Path


_FIGURES_INSTALL_HINT = (
    "Figure extraction requires Java + the pdffigures2 JAR.\n"
    "  1) Install a Java runtime (macOS: brew install openjdk; Linux: apt install default-jre)\n"
    "  2) Place the pdffigures2 fat JAR at ~/.xhs-paper-engine/pdffigures2.jar\n"
    "     (or set PDFFIGURES2_JAR / extraction.pdffigures2_jar). See the README."
)


def resolve_java() -> str | None:
    """Locate a usable `java` executable, or None."""
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        cand = Path(java_home) / "bin" / "java"
        if cand.exists():
            return str(cand)

    found = shutil.which("java")
    if found:
        return found

    # Common Homebrew keg-only locations (java not on PATH by default)
    for p in (
        "/opt/homebrew/opt/openjdk/bin/java",
        "/usr/local/opt/openjdk/bin/java",
    ):
        if Path(p).exists():
            return p
    return None


def resolve_jar() -> str | None:
    """Locate the pdffigures2 fat JAR, or None."""
    env_jar = os.environ.get("PDFFIGURES2_JAR", "").strip()
    if env_jar and Path(env_jar).exists():
        return env_jar

    try:
        from dp_core.config import config
        cfg_jar = str(config.get("extraction.pdffigures2_jar", "")).strip()
        if cfg_jar and Path(cfg_jar).exists():
            return cfg_jar
    except Exception:
        pass

    default = Path.home() / ".xhs-paper-engine" / "pdffigures2.jar"
    if default.exists():
        return str(default)
    return None


def backend_available() -> tuple[bool, str]:
    """Return (ok, message). Used by the startup preflight."""
    missing = []
    if resolve_java() is None:
        missing.append("java runtime")
    if resolve_jar() is None:
        missing.append("pdffigures2.jar")
    if missing:
        return False, "Missing: " + ", ".join(missing) + "\n" + _FIGURES_INSTALL_HINT
    return True, ""


def extract_figures_and_tables(pdf_path, output_dir, dpi=200, save_json=True, **kwargs):
    """
    Extract figures and tables from a PDF via pdffigures2.

    Writes figure images to ``<output_dir>/figures/`` and table images to
    ``<output_dir>/tables/`` (so callers can glob each separately).

    Args:
        pdf_path (str): Path to the PDF.
        output_dir (str): Output directory.
        dpi (int): Render DPI for the cropped figure images (default 200).
        save_json (bool): Also write a combined extraction_results.json.

    Returns:
        dict: { total_items, figures_count, tables_count, figures: [...], tables: [...] }
    """
    pdf_path = os.path.abspath(pdf_path)
    output_dir = Path(os.path.abspath(output_dir))

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    java = resolve_java()
    jar = resolve_jar()
    if java is None or jar is None:
        ok, msg = backend_available()
        raise RuntimeError(msg)

    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        img_prefix = str(tmp) + "/"   # trailing slash -> files written into tmp/
        data_prefix = str(tmp) + "/"

        cmd = [
            java, "-jar", jar, pdf_path,
            "-m", img_prefix,     # render figure/table images
            "-d", data_prefix,    # write per-pdf JSON metadata (captions etc.)
            "-i", str(dpi),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"pdffigures2 failed (exit {proc.returncode}): "
                f"{(proc.stderr or proc.stdout)[-500:]}"
            )

        # Load caption/type metadata (one JSON per input pdf)
        meta_by_name = {}
        for jf in tmp.glob("*.json"):
            try:
                for item in json.load(open(jf, encoding="utf-8")):
                    rf = item.get("renderURL") or item.get("renderUrl")
                    key = Path(rf).name if rf else None
                    if key:
                        meta_by_name[key] = item
            except Exception:
                continue

        stats = {"figures_count": 0, "tables_count": 0, "figures": [], "tables": []}

        # Classify rendered PNGs by pdffigures2's naming (<pdf>-Figure1-1.png / -Table1-1.png)
        for png in sorted(tmp.glob("*.png")):
            name = png.name
            meta = meta_by_name.get(name, {})
            fig_type = (meta.get("figType") or "").lower()
            is_table = fig_type == "table" or "-Table" in name

            dest_dir = tables_dir if is_table else figures_dir
            dest = dest_dir / name
            shutil.copyfile(png, dest)

            record = {
                "filename": name,
                "path": str(dest),
                "page": (meta.get("page", -1) + 1) if "page" in meta else None,
                "caption": meta.get("caption", ""),
                "name": meta.get("name", ""),
            }
            if is_table:
                stats["tables_count"] += 1
                stats["tables"].append(record)
            else:
                stats["figures_count"] += 1
                stats["figures"].append(record)

    stats["total_items"] = stats["figures_count"] + stats["tables_count"]

    if save_json:
        with open(output_dir / "extraction_results.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    print(
        f"pdffigures2: extracted {stats['figures_count']} figures, "
        f"{stats['tables_count']} tables -> {output_dir}"
    )
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Extract figures and tables from a scholarly PDF (pdffigures2)."
    )
    parser.add_argument("--pdf", required=True, help="Path to the PDF file")
    parser.add_argument("--output-dir", default="./extracted", help="Output directory")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI (default: 200)")
    parser.add_argument("--no-json", action="store_true", help="Do not write extraction_results.json")
    args = parser.parse_args()

    try:
        extract_figures_and_tables(
            pdf_path=args.pdf,
            output_dir=args.output_dir,
            dpi=args.dpi,
            save_json=not args.no_json,
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
