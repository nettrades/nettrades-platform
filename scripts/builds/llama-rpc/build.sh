#!/usr/bin/env bash
# =============================================================================
# FILE: scripts/builds/llama-rpc/build.sh
# =============================================================================
# PURPOSE:
#   Thin wrapper around docker build for the RPC master image.
#   Idempotent: skips if the image with the correct content hash exists.
#   This is the ONLY entry point the installer uses. Do not call
#   docker build directly against this directory.
# =============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Content hash = hash of Dockerfile + manifest.yaml. This is the tag.
HASH=$(sha256sum "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR/manifest.yaml" | sha256sum | cut -c1-12)
TAG="nettrades-rpc-master:${HASH}"

if docker image inspect "$TAG" >/dev/null 2>&1; then
    echo "Image $TAG exists — skipping build"
    # Re-tag as :latest so docker-compose.yaml's tagless reference works
    docker tag "$TAG" nettrades-rpc-master:latest
    exit 0
fi

# Read build args from manifest.yaml. The YAML parser is simple here
# because we control the format — no nested structures.
LLAMA_TAG=$(grep -E '^\s+LLAMA_CPP_TAG:' "$SCRIPT_DIR/manifest.yaml" | awk -F'"' '{print $2}')
CUDA_ARCH=$(grep -E '^\s+CUDA_ARCH:' "$SCRIPT_DIR/manifest.yaml" | awk -F'"' '{print $2}')

echo "Building $TAG (LLAMA_CPP_TAG=$LLAMA_TAG, CUDA_ARCH=$CUDA_ARCH)"
docker build \
    --build-arg LLAMA_CPP_TAG="$LLAMA_TAG" \
    --build-arg CUDA_ARCH="$CUDA_ARCH" \
    -t "$TAG" \
    -t "nettrades-rpc-master:latest" \
    "$SCRIPT_DIR"

# Verify every output exists.
for path in $(grep -E '^\s+- /' "$SCRIPT_DIR/manifest.yaml" | awk '{print $2}'); do
    echo "Verifying $path exists in image..."
    docker run --rm --entrypoint sh "$TAG" -c "test -e $path" || {
        echo "FAILED: $path not found in image"
        exit 1
    }
done

echo "Build complete: $TAG"