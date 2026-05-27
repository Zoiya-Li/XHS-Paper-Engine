#!/usr/bin/env bash
#
# Build the pdffigures2 fat JAR (figure/table extraction backend) using Docker,
# and install it to ~/.xhs-paper-engine/pdffigures2.jar (or $PDFFIGURES2_JAR).
#
# Requires Docker. You only need to run this once. Alternatively, download a
# prebuilt JAR from the project's releases and drop it at the same path.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${PDFFIGURES2_JAR:-$HOME/.xhs-paper-engine/pdffigures2.jar}"
IMAGE="pdffigures2-builder:local"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to build the JAR. Install Docker, or download a prebuilt JAR to $DEST." >&2
  exit 1
fi

echo "==> Building builder image (first time pulls the Scala toolchain; a few minutes)..."
docker build -f "$PROJECT_DIR/docker/pdffigures2.Dockerfile" -t "$IMAGE" "$PROJECT_DIR/docker"

echo "==> Extracting JAR -> $DEST"
mkdir -p "$(dirname "$DEST")"
cid="$(docker create "$IMAGE")"
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT
docker cp "$cid:/pdffigures2/pdffigures2.jar" "$DEST"

echo "==> Done. JAR installed at: $DEST"
ls -la "$DEST"
