#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"

WITH_JAVA=0
WITH_POPPLER=0

for arg in "$@"; do
  case "$arg" in
    --with-java) WITH_JAVA=1 ;;
    --with-poppler) WITH_POPPLER=1 ;;
    --all) WITH_JAVA=1; WITH_POPPLER=1 ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it first:"
  echo "  curl -Ls https://astral.sh/uv/install.sh | sh"
  exit 1
fi

echo "==> Project: $PROJECT_DIR"
echo "==> Venv:    $VENV_DIR"

uv venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

uv pip install -r "$PROJECT_DIR/requirements.txt"
python -m playwright install chromium

if [ ! -f "$PROJECT_DIR/.env" ] && [ -f "$PROJECT_DIR/.env.example" ]; then
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  echo "==> Created .env from .env.example (fill in your API keys)."
fi

if [ "$WITH_POPPLER" -eq 1 ]; then
  if command -v brew >/dev/null 2>&1; then
    brew install poppler
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y poppler-utils
  else
    echo "==> Please install poppler manually (pdftotext is required)."
  fi
fi

if [ "$WITH_JAVA" -eq 1 ]; then
  # Figure extraction (pdffigures2) needs a Java runtime.
  if command -v brew >/dev/null 2>&1; then
    brew install openjdk
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y default-jre
  else
    echo "==> Please install a Java runtime (JRE 11+) manually."
  fi
  echo "==> NOTE: also place the pdffigures2 fat JAR at ~/.xhs-paper-engine/pdffigures2.jar"
  echo "==>       (build it via scripts/build_pdffigures2_jar.sh, or see the README)."
fi

echo "==> Done."
