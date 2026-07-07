#!/bin/bash
# =============================================================================
# FILE: scripts/download-model.sh
# PURPOSE: Download a DeepSeek model in GGUF (llama.cpp) or HF (vLLM) format.
# USAGE:   ./download-model.sh [--model <name>] [--format <gguf|hf>] [--dir <path>] [--output <file>]
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
# Map model names to Hugging Face identifiers and URLs
# -----------------------------------------------------------------------------
case "$MODEL_NAME" in
    deepseek-1.5b|1.5b)
        HF_REPO="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
        GGUF_URL="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
        DEFAULT_FILE_GGUF="DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
        ;;
    deepseek-7b|7b)
        HF_REPO="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        GGUF_URL="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"
        DEFAULT_FILE_GGUF="deepseek-r1-distill-qwen-7b-q4_k_m.gguf"
        ;;
    *)
        echo "ERROR: Unknown model '$MODEL_NAME'. Available: deepseek-1.5b, deepseek-7b"
        exit 1
        ;;
esac

# -----------------------------------------------------------------------------
# Helper: Ensure `hf` CLI is available
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
# Helper: Ensure Hugging Face authentication is set up
# -----------------------------------------------------------------------------
ensure_hf_auth() {
    # Check if token already exists
    if [[ -f "$HOME/.cache/huggingface/token" ]] || hf auth token &>/dev/null; then
        echo "Hugging Face authentication token found."
        return 0
    fi

    echo ""
    echo "======================================================================"
    echo "  Hugging Face Authentication Required"
    echo "======================================================================"
    echo "To download models from Hugging Face, you need to authenticate."
    echo ""
    echo "If you have a Hugging Face account, follow these steps:"
    echo "  1. Create an account at https://huggingface.co/join"
    echo "  2. Go to https://huggingface.co/settings/tokens to create a token"
    echo "  3. Run the following command and paste your token:"
    echo ""
    echo "     hf auth login"
    echo ""
    echo "If you already have a token, you can set it as an environment variable:"
    echo "     export HUGGINGFACE_TOKEN=your_token_here"
    echo ""
    echo "Press Enter to continue after you have logged in, or Ctrl+C to cancel."
    read -r
    echo ""

    # Try again after user action
    if hf auth token &>/dev/null; then
        echo "Authentication successful."
        return 0
    else
        echo "WARNING: Still not authenticated. Trying to proceed anyway..."
        return 1
    fi
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

    # Check if file already exists
    if [[ -f "$OUTPUT_FILE" ]]; then
        echo "GGUF model already exists at $OUTPUT_FILE – skipping download."
        exit 0
    fi

    echo "Downloading GGUF model from Hugging Face..."
    echo "URL: $GGUF_URL"
    echo "Target: $OUTPUT_FILE"

    # Download with progress
    if command -v wget &>/dev/null; then
        wget -O "$OUTPUT_FILE" "$GGUF_URL" --progress=dot:giga
    elif command -v curl &>/dev/null; then
        curl -L -o "$OUTPUT_FILE" "$GGUF_URL" --progress-bar
    else
        echo "ERROR: Neither wget nor curl found. Please install one."
        exit 1
    fi

    if [[ -f "$OUTPUT_FILE" ]]; then
        echo "Download complete: $OUTPUT_FILE"
        # Verify file size (at least 500 MB for 1.5B Q4)
        size=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || stat -f%z "$OUTPUT_FILE" 2>/dev/null || echo 0)
        if [[ "$size" -lt 500000000 ]]; then
            echo "WARNING: Downloaded file seems too small ($size bytes). Download may have failed."
            exit 1
        fi
    else
        echo "ERROR: Download failed."
        exit 1
    fi

elif [[ "$FORMAT" == "hf" ]]; then
    # Hugging Face format (directory)
    if [[ -z "$OUTPUT_DIR" ]]; then
        OUTPUT_DIR="./${HF_REPO##*/}"   # Default to repo name
    fi
    mkdir -p "$OUTPUT_DIR"

    # Check if the directory already contains a valid HF model (config.json exists)
    if [[ -f "$OUTPUT_DIR/config.json" ]]; then
        echo "HF model already exists at $OUTPUT_DIR – skipping download."
        exit 0
    fi

    # Ensure `hf` CLI is available
    ensure_hf_cli

    # Ensure authentication
    ensure_hf_auth

    echo "Downloading Hugging Face model: $HF_REPO"
    echo "Target directory: $OUTPUT_DIR"

    # Use the token if provided via environment variable
    if [[ -n "${HUGGINGFACE_TOKEN:-}" ]]; then
        echo "Using token from environment variable HUGGINGFACE_TOKEN."
        hf download "$HF_REPO" --local-dir "$OUTPUT_DIR" --token "$HUGGINGFACE_TOKEN"
    else
        hf download "$HF_REPO" --local-dir "$OUTPUT_DIR"
    fi

    if [[ -f "$OUTPUT_DIR/config.json" ]]; then
        echo "HF model downloaded successfully to $OUTPUT_DIR"
    else
        echo "ERROR: HF model download failed. No config.json found."
        echo "Please ensure you have access to the model: $HF_REPO"
        echo "If you are authenticated, try running:"
        echo "  hf download $HF_REPO --local-dir $OUTPUT_DIR"
        exit 1
    fi

else
    echo "ERROR: Unknown format '$FORMAT'. Use 'gguf' or 'hf'."
    exit 1
fi

echo "Download completed successfully."