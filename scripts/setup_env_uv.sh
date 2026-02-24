#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"

WITH_DETECTRON2=0
WITH_POPPLER=0

for arg in "$@"; do
  case "$arg" in
    --with-detectron2) WITH_DETECTRON2=1 ;;
    --with-poppler) WITH_POPPLER=1 ;;
    --all) WITH_DETECTRON2=1; WITH_POPPLER=1 ;;
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

if [ "$WITH_DETECTRON2" -eq 1 ]; then
  if [ ! -d "$PROJECT_DIR/detectron2" ]; then
    git clone https://github.com/facebookresearch/detectron2.git "$PROJECT_DIR/detectron2"
  fi

  if [[ "$OSTYPE" == "darwin"* ]]; then
    ARCH="$(uname -m)"
    if [ "$ARCH" = "arm64" ]; then
      ARCHFLAGS="-arch arm64"
    else
      ARCHFLAGS="-arch x86_64"
    fi
    CC=clang CXX=clang++ ARCHFLAGS="$ARCHFLAGS" python -m pip install -e "$PROJECT_DIR/detectron2"
  else
    python -m pip install -e "$PROJECT_DIR/detectron2"
  fi
fi

echo "==> Done."
