#!/bin/bash
# XHS Paper Engine Run Script Wrapper
# For bypassing macOS security restrictions
# Allow override of python and project dir via env vars.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${XHS_PAPER_ENGINE_PROJECT_DIR:-${DAILYPAPER_PROJECT_DIR:-$SCRIPT_DIR}}"
PYTHON_BIN="${XHS_PAPER_ENGINE_PYTHON:-${DAILYPAPER_PYTHON:-python3}}"

cd "$PROJECT_DIR" || exit 1
"$PYTHON_BIN" auto_run.py
