#!/bin/bash
# =============================================================================
# FILE: scripts/download-model.sh
# PURPOSE: Download a DeepSeek model in GGUF (llama.cpp) or HF (vLLM) format.
# USAGE:   ./download-model.sh [--model <name>] [--format <gguf|hf>] [--dir <path>] [--output <file>]
# =============================================================================
# CHANGELOG:
#   2026-08-02: Switched to ModelScope mirrors (no authentication required)
#               for both GGUF and HF formats.
#   2026-08-03: Added retry logic with exponential backoff for GGUF downloads
#               to improve resilience against transient network failures.
#   2026-08-27: Fixed HF_MODELSCOPE_URL for deepseek-7b to point to the actual
#               Hugging Face model repository (not the GGUF repo).
# =============================================================================

set -euo pipefail

# Defaults
MODEL_NAME="${MODEL_NAME:-deepseek-1.5b}"
FORMAT="${FORMAT:-gguf}"   # gguf or hf
OUTPUT_DIR="${OUTPUT_DIR:-}"
OUTPUT_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --model)
            MODEL_NAME="$2"
            shift 2
            ;;
        --format)
            FORMAT="$2"
            shift 2
            ;;
        --dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--model deepseek-1.5b|deepseek-7b] [--format gguf|hf] [--dir /path/to/models] [--output /path/to/file]"
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Map model names to ModelScope identifiers and URLs
# ModelScope mirrors work without authentication and are reliable.
# -----------------------------------------------------------------------------
case "$MODEL_NAME" in
    deepseek-1.5b|1.5b)
        HF_REPO="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
        # ModelScope GGUF URL (no auth required)
        GGUF_URL="https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
        DEFAULT_FILE_GGUF="DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
        # ModelScope HF format URL (no auth required) – the actual model repo
        HF_MODELSCOPE_URL="https://www.modelscope.cn/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B.git"
        ;;
    deepseek-7b|7b)
        HF_REPO="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        # ModelScope GGUF URL (no auth required) – used for llama.cpp fallback
        GGUF_URL="https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"
        DEFAULT_FILE_GGUF="deepseek-r1-distill-qwen-7b-q4_k_m.gguf"
        # ModelScope HF format URL (no auth required) – the actual model repo
        HF_MODELSCOPE_URL="https://www.modelscope.cn/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B.git"
        ;;
    *)
        echo "ERROR: Unknown model '$MODEL_NAME'. Available: deepseek-1.5b, deepseek-7b"
        exit 1
        ;;
esac

# -----------------------------------------------------------------------------
# Helper: Ensure `hf` CLI is available (only needed for HF format downloads)
# -----------------------------------------------------------------------------
ensure_hf_cli() {
    if command -v hf &>/dev/null; then
        return 0
    fi

    echo "The 'hf' command (from huggingface-hub) is not available."
    echo "Attempting to install it via pipx..."

    if ! command -v pipx &>/dev/null; then
        echo "pipx is not installed. Installing pipx..."
        if command -v apt &>/dev/null; then
            sudo apt update && sudo apt install -y pipx
            pipx ensurepath
        else
            echo "ERROR: pipx could not be installed automatically."
            echo "Please install pipx manually, then run:"
            echo "  pipx install huggingface-hub"
            echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            exit 1
        fi
    fi

    echo "Installing huggingface-hub via pipx..."
    pipx install huggingface-hub || {
        echo "ERROR: pipx install failed. Trying fallback with pip..."
        pip install --break-system-packages huggingface-hub || {
            echo "ERROR: Could not install huggingface-hub. Please install it manually."
            exit 1
        }
    }

    # Add ~/.local/bin to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    if ! command -v hf &>/dev/null; then
        echo "ERROR: 'hf' command still not found. Please add ~/.local/bin to your PATH."
        exit 1
    fi

    echo "'hf' command is now available."
}

# -----------------------------------------------------------------------------
# Helper: Check if git is available (for HF format downloads from ModelScope)
# -----------------------------------------------------------------------------
ensure_git() {
    if ! command -v git &>/dev/null; then
        echo "ERROR: git is not installed. Please install git first."
        echo "  Ubuntu/Debian: sudo apt install git"
        echo "  macOS: brew install git"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Helper: Download with retries and timeout (used for GGUF format)
# -----------------------------------------------------------------------------
download_with_retries() {
    local url="$1"
    local output="$2"
    local max_retries=5
    local retry_delay=10
    local attempt=1

    while [ $attempt -le $max_retries ]; do
        echo "Download attempt $attempt/$max_retries..."
        if command -v wget &>/dev/null; then
            if wget --tries=1 --timeout=120 --no-check-certificate -O "$output" "$url" --progress=dot:giga; then
                return 0
            fi
        elif command -v curl &>/dev/null; then
            if curl -L --retry 1 --max-time 120 -o "$output" "$url" --progress-bar; then
                return 0
            fi
        else
            echo "ERROR: Neither wget nor curl found. Please install one."
            return 1
        fi

        echo "Download failed. Removing partial file..."
        rm -f "$output"

        if [ $attempt -lt $max_retries ]; then
            echo "Retrying in $retry_delay seconds..."
            sleep $retry_delay
            retry_delay=$((retry_delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    echo "ERROR: Download failed after $max_retries attempts."
    return 1
}

# -----------------------------------------------------------------------------
# Determine final output path and format-specific logic
# -----------------------------------------------------------------------------
if [[ "$FORMAT" == "gguf" ]]; then
    if [[ -z "$OUTPUT_FILE" ]]; then
        if [[ -n "$OUTPUT_DIR" ]]; then
            mkdir -p "$OUTPUT_DIR"
            OUTPUT_FILE="$OUTPUT_DIR/$DEFAULT_FILE_GGUF"
        else
            OUTPUT_FILE="./$DEFAULT_FILE_GGUF"
        fi
    else
        mkdir -p "$(dirname "$OUTPUT_FILE")"
    fi

    # Check if file already exists and is valid (non-empty, >500MB)
    if [[ -f "$OUTPUT_FILE" ]]; then
        size=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || stat -f%z "$OUTPUT_FILE" 2>/dev/null || echo 0)
        if [[ "$size" -gt 500000000 ]]; then
            echo "GGUF model already exists at $OUTPUT_FILE ($size bytes) – skipping download."
            exit 0
        else
            echo "WARNING: Existing file is too small ($size bytes). Re-downloading..."
            rm -f "$OUTPUT_FILE"
        fi
    fi

    echo "Downloading GGUF model from ModelScope mirror..."
    echo "URL: $GGUF_URL"
    echo "Target: $OUTPUT_FILE"

    # Download with retries and timeout
    if download_with_retries "$GGUF_URL" "$OUTPUT_FILE"; then
        echo "Download complete: $OUTPUT_FILE"
        # Verify file size (at least 500 MB for 1.5B Q4)
        size=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || stat -f%z "$OUTPUT_FILE" 2>/dev/null || echo 0)
        if [[ "$size" -lt 500000000 ]]; then
            echo "ERROR: Downloaded file seems too small ($size bytes). Download may have failed."
            echo "Please check the URL and try again."
            exit 1
        fi
        echo "File size: $size bytes – looks valid."
    else
        exit 1  # download_with_retries already printed error
    fi

elif [[ "$FORMAT" == "hf" ]]; then
    # Hugging Face format (directory) - using ModelScope as primary source
    if [[ -z "$OUTPUT_DIR" ]]; then
        OUTPUT_DIR="./${HF_REPO##*/}"   # Default to repo name
    fi
    mkdir -p "$OUTPUT_DIR"

    # Check if the directory already contains a valid HF model (config.json exists)
    if [[ -f "$OUTPUT_DIR/config.json" ]]; then
        echo "HF model already exists at $OUTPUT_DIR – skipping download."
        exit 0
    fi

    echo "Downloading Hugging Face format model from ModelScope mirror..."
    echo "Source: $HF_MODELSCOPE_URL"
    echo "Target directory: $OUTPUT_DIR"

    # Ensure git is available (needed for cloning)
    ensure_git

    # Clone from ModelScope (no authentication required)
    if git clone "$HF_MODELSCOPE_URL" "$OUTPUT_DIR" 2>/dev/null; then
        echo "HF model downloaded successfully from ModelScope to $OUTPUT_DIR"
    else
        echo "WARNING: ModelScope clone failed. Trying Hugging Face as fallback..."
        
        # Fallback: Try Hugging Face with authentication check
        ensure_hf_cli
        
        echo "Downloading from Hugging Face: $HF_REPO"
        echo "Target directory: $OUTPUT_DIR"
        
        # Check if token exists
        if [[ -f "$HOME/.cache/huggingface/token" ]] || hf auth token &>/dev/null; then
            echo "Hugging Face authentication found. Downloading..."
            hf download "$HF_REPO" --local-dir "$OUTPUT_DIR"
        else
            echo "WARNING: No Hugging Face authentication found."
            echo "Please run 'hf auth login' first or use --format gguf instead."
            echo "For GGUF format, ModelScope mirror works without authentication."
            exit 1
        fi
    fi

    if [[ -f "$OUTPUT_DIR/config.json" ]]; then
        echo "HF model downloaded successfully to $OUTPUT_DIR"
    else
        echo "ERROR: HF model download failed. No config.json found."
        echo "Please ensure you have access to the model: $HF_REPO"
        exit 1
    fi

else
    echo "ERROR: Unknown format '$FORMAT'. Use 'gguf' or 'hf'."
    exit 1
fi

echo "Download completed successfully."