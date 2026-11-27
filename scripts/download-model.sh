#!/bin/bash
# =============================================================================
# FILE: scripts/download-model.sh
# PURPOSE: Download an LLM (DeepSeek, Fanar) or ASR model (Audar, Qwen3-ASR)
#          in GGUF (llama.cpp) or HF (vLLM) format.
# USAGE:   ./download-model.sh [--model <name>] [--format <gguf|hf>]
#                              [--dir <path>] [--output <file>]
#
# NOTE ON MULTI-FILE MODELS (audar-asr, qwen3-asr):
#   These ASR models need TWO files for llama.cpp: the decoder GGUF and the
#   audio projector (mmproj). When --model is a multi-file model, this script
#   ALWAYS downloads into a model-specific subdirectory
#   (e.g. <dir>/audar-asr/), and --output is ignored. This is because
#   llama-server loads both files by path, and they must live together.
# =============================================================================
# CHANGELOG:
#   2026-08-02: Switched to ModelScope mirrors (no authentication required)
#               for both GGUF and HF formats.
#   2026-08-03: Added retry logic with exponential backoff for GGUF downloads
#               to improve resilience against transient network failures.
#   2026-08-27: Fixed HF_MODELSCOPE_URL for deepseek-7b to point to the actual
#               Hugging Face model repository (not the GGUF repo).
#   2026-08-27: Added fallback to modelscope SDK and custom mirror.
#   2026-11-03: Added Fanar-9B model support. Since Fanar is not on ModelScope,
#               we use the public Hugging Face GGUF repository (mradermacher).
#               Public models on HF can be downloaded without an API token.
#   2026-11-03: RESTORED the ModelScope SDK fallback for HF format downloads.
#               It is a critical layer of robustness for DeepSeek models.
#   2026-11-06: Added audar-asr and qwen3-asr (multi-file GGUF with projector).
#               Restructured the GGUF block so the multi-file path runs BEFORE
#               the single-file existence check.
#   2026-11-06: FIXED projector filename for audar-asr. The correct file is
#               mmproj-Audar-ASR-V1-Flash.gguf (no -BF16 suffix). The old
#               name caused a 404 on every download attempt.
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
            echo "Usage: $0 [--model deepseek-1.5b|deepseek-7b|fanar-9b|audar-asr|qwen3-asr] [--format gguf|hf] [--dir /path/to/models] [--output /path/to/file]"
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Map model names to identifiers and URLs.
# -----------------------------------------------------------------------------
case "$MODEL_NAME" in
    deepseek-1.5b|1.5b)
        HF_REPO="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
        GGUF_URL="https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
        DEFAULT_FILE_GGUF="DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
        HF_MODELSCOPE_URL="https://www.modelscope.cn/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B.git"
        ;;
    deepseek-7b|7b)
        HF_REPO="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        GGUF_URL="https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"
        DEFAULT_FILE_GGUF="deepseek-r1-distill-qwen-7b-q4_k_m.gguf"
        HF_MODELSCOPE_URL="https://www.modelscope.cn/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B.git"
        ;;
    fanar-9b|fanar)
        HF_REPO="QCRI/Fanar-1-9B-Instruct"
        GGUF_URL="https://huggingface.co/mradermacher/Fanar-1-9B-Instruct-GGUF/resolve/main/Fanar-1-9B-Instruct.Q4_K_M.gguf"
        DEFAULT_FILE_GGUF="Fanar-1-9B-Instruct.Q4_K_M.gguf"
        HF_MODELSCOPE_URL=""
        ;;
    audar-asr|audar)
        # Audar-ASR-V1-Flash: Arabic + English + 30 languages, 0.78B params.
        # TWO files required for llama.cpp:
        #   - Audar-ASR-V1-Flash-Q8_0.gguf          (decoder, ~610 MB)
        #   - mmproj-Audar-ASR-V1-Flash.gguf        (projector, ~379 MB)
        # The projector filename is EXACTLY this. There is no -BF16 suffix.
        HF_REPO="audarai/Audar-ASR-V1-Flash"
        GGUF_URL="https://huggingface.co/audarai/Audar-ASR-V1-Flash/resolve/main/Audar-ASR-V1-Flash-Q8_0.gguf"
        DEFAULT_FILE_GGUF="Audar-ASR-V1-Flash-Q8_0.gguf"
        MMPROJ_URL="https://huggingface.co/audarai/Audar-ASR-V1-Flash/resolve/main/mmproj-Audar-ASR-V1-Flash.gguf"
        MMPROJ_FILE="mmproj-Audar-ASR-V1-Flash.gguf"
        HF_MODELSCOPE_URL=""
        ;;
    qwen3-asr|qwen-asr)
        # Fallback ASR model. NOTE: these URLs are unverified. Check the
        # Qwen3-ASR-0.6B model card for current GGUF filenames if download fails.
        HF_REPO="Qwen/Qwen3-ASR-0.6B"
        GGUF_URL="https://huggingface.co/Qwen/Qwen3-ASR-0.6B-GGUF/resolve/main/Qwen3-ASR-0.6B-Q8_0.gguf"
        DEFAULT_FILE_GGUF="Qwen3-ASR-0.6B-Q8_0.gguf"
        MMPROJ_URL="https://huggingface.co/Qwen/Qwen3-ASR-0.6B-GGUF/resolve/main/mmproj-Qwen3-ASR-0.6B-F16.gguf"
        MMPROJ_FILE="mmproj-Qwen3-ASR-0.6B-F16.gguf"
        HF_MODELSCOPE_URL=""
        ;;
    *)
        echo "ERROR: Unknown model '$MODEL_NAME'."
        echo "Available: deepseek-1.5b, deepseek-7b, fanar-9b, audar-asr, qwen3-asr"
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
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v hf &>/dev/null; then
        echo "ERROR: 'hf' command still not found. Please add ~/.local/bin to your PATH."
        exit 1
    fi
    echo "'hf' command is now available."
}

# -----------------------------------------------------------------------------
# Helper: Check if git is available
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

# =============================================================================
# GGUF format
# =============================================================================
if [[ "$FORMAT" == "gguf" ]]; then

    # -------------------------------------------------------------------------
    # Multi-file models (decoder GGUF + audio projector) — audar-asr, qwen3-asr
    # Runs BEFORE the single-file existence check so both files are always
    # validated on every run. --output is ignored for multi-file models.
    # -------------------------------------------------------------------------
    if [[ -n "${MMPROJ_URL:-}" ]]; then
        if [[ -n "${OUTPUT_FILE:-}" ]]; then
            echo "NOTE: --output is ignored for multi-file models (${MODEL_NAME})."
            echo "      Files will be placed in a model-specific subdirectory."
            OUTPUT_DIR="$(dirname "$OUTPUT_FILE")"
            OUTPUT_FILE=""
        fi

        if [[ -z "${OUTPUT_DIR:-}" ]]; then
            OUTPUT_DIR="./${MODEL_NAME}"
        fi

        if [[ "$(basename "$OUTPUT_DIR")" != "${MODEL_NAME}" ]]; then
            OUTPUT_DIR="$OUTPUT_DIR/${MODEL_NAME}"
        fi

        mkdir -p "$OUTPUT_DIR"
        DECODER_PATH="$OUTPUT_DIR/$DEFAULT_FILE_GGUF"
        PROJECTOR_PATH="$OUTPUT_DIR/$MMPROJ_FILE"

        download_one() {
            local url="$1"; local dest="$2"; local min_bytes="$3"
            if [[ -f "$dest" ]]; then
                local sz
                sz=$(stat -c%s "$dest" 2>/dev/null || stat -f%z "$dest" 2>/dev/null || echo 0)
                if [[ "$sz" -gt "$min_bytes" ]]; then
                    echo "  Already present: $dest ($sz bytes)"
                    return 0
                fi
                echo "  Existing file too small ($sz bytes), re-downloading: $dest"
                rm -f "$dest"
            fi
            download_with_retries "$url" "$dest" || return 1
            local sz
            sz=$(stat -c%s "$dest" 2>/dev/null || stat -f%z "$dest" 2>/dev/null || echo 0)
            if [[ "$sz" -lt "$min_bytes" ]]; then
                echo "ERROR: $dest is only $sz bytes (expected >$min_bytes)."
                return 1
            fi
            echo "  Downloaded: $dest ($sz bytes)"
        }

        echo "Downloading ${MODEL_NAME} (decoder + audio projector)..."
        echo "Target directory: $OUTPUT_DIR"

        download_one "$GGUF_URL" "$DECODER_PATH" 400000000 || {
            echo "ERROR: decoder download failed."
            echo "       Try manual download: $GGUF_URL"
            exit 1
        }

        download_one "$MMPROJ_URL" "$PROJECTOR_PATH" 100000000 || {
            echo "ERROR: audio projector download failed."
            echo "       The projector is MANDATORY — llama-server cannot"
            echo "       process audio without it."
            echo "       Try manual download: $MMPROJ_URL"
            exit 1
        }

        echo ""
        echo "=== ${MODEL_NAME} ready ==="
        echo "  Decoder:   $DECODER_PATH"
        echo "  Projector: $PROJECTOR_PATH"
        echo ""
        echo "To use in docker-compose.yaml (llama-asr service):"
        echo "  -m \"/models/${MODEL_NAME}/$(basename "$DECODER_PATH")\""
        echo "  --mmproj \"/models/${MODEL_NAME}/$(basename "$PROJECTOR_PATH")\""
        exit 0
    fi

    # -------------------------------------------------------------------------
    # Single-file models — deepseek-*, fanar-*
    # -------------------------------------------------------------------------
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

    echo "Downloading GGUF model from $GGUF_URL..."
    echo "Target: $OUTPUT_FILE"

    if download_with_retries "$GGUF_URL" "$OUTPUT_FILE"; then
        echo "Download complete: $OUTPUT_FILE"
        size=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || stat -f%z "$OUTPUT_FILE" 2>/dev/null || echo 0)
        if [[ "$size" -lt 500000000 ]]; then
            echo "ERROR: Downloaded file seems too small ($size bytes). Download may have failed."
            exit 1
        fi
        echo "File size: $size bytes – looks valid."
        exit 0
    else
        exit 1
    fi

# =============================================================================
# HF format (directory)
# =============================================================================
elif [[ "$FORMAT" == "hf" ]]; then
    if [[ -z "$OUTPUT_DIR" ]]; then
        OUTPUT_DIR="./${HF_REPO##*/}"
    fi
    mkdir -p "$OUTPUT_DIR"

    if [[ -f "$OUTPUT_DIR/config.json" ]]; then
        echo "HF model already exists at $OUTPUT_DIR – skipping download."
        exit 0
    fi

    # METHOD 1: Git clone from ModelScope
    if [[ -n "${HF_MODELSCOPE_URL:-}" ]]; then
        echo "Downloading Hugging Face format model from ModelScope (git clone)..."
        echo "Source: $HF_MODELSCOPE_URL"
        echo "Target: $OUTPUT_DIR"
        ensure_git
        if git clone "$HF_MODELSCOPE_URL" "$OUTPUT_DIR" 2>/dev/null; then
            if [[ -f "$OUTPUT_DIR/config.json" ]]; then
                echo "HF model downloaded successfully from ModelScope (git clone)."
                exit 0
            else
                echo "WARNING: Git clone succeeded but config.json not found. Removing partial directory..."
                rm -rf "$OUTPUT_DIR"
            fi
        fi
    fi

    # METHOD 2: modelscope SDK download (fallback)
    if [[ -n "${HF_MODELSCOPE_URL:-}" ]]; then
        echo "ModelScope git clone failed. Trying modelscope SDK..."
        if ! python3 -c "import modelscope" 2>/dev/null; then
            echo "Installing modelscope SDK..."
            pip install modelscope -q
        fi
        if python3 -c "from modelscope import snapshot_download; snapshot_download('$HF_REPO', cache_dir='$OUTPUT_DIR', local_dir='$OUTPUT_DIR')" 2>/dev/null; then
            if [[ -f "$OUTPUT_DIR/config.json" ]]; then
                echo "HF model downloaded successfully via modelscope SDK."
                exit 0
            else
                echo "WARNING: modelscope SDK download completed but config.json not found."
                rm -rf "$OUTPUT_DIR"
            fi
        fi
    fi

    # METHOD 3: Hugging Face CLI
    echo "Trying Hugging Face CLI (no auth required for public models)..."
    ensure_hf_cli
    if hf download "$HF_REPO" --local-dir "$OUTPUT_DIR" 2>/dev/null; then
        if [[ -f "$OUTPUT_DIR/config.json" ]]; then
            echo "HF model downloaded successfully via Hugging Face CLI."
            exit 0
        else
            echo "WARNING: Hugging Face CLI download completed but config.json not found."
            rm -rf "$OUTPUT_DIR"
        fi
    fi

    # METHOD 4: Custom mirror
    if [[ -n "${HF_MODEL_MIRROR:-}" ]]; then
        echo "Trying custom mirror: $HF_MODEL_MIRROR"
        if curl -L "$HF_MODEL_MIRROR" -o /tmp/model.tar.gz; then
            tar -xzf /tmp/model.tar.gz -C "$OUTPUT_DIR" --strip-components=1
            if [[ -f "$OUTPUT_DIR/config.json" ]]; then
                echo "HF model downloaded successfully from custom mirror."
                exit 0
            else
                echo "WARNING: Custom mirror download completed but config.json not found."
                rm -rf "$OUTPUT_DIR"
            fi
        fi
    fi

    echo "ERROR: All download methods failed. Please manually place the HF model in $OUTPUT_DIR"
    echo "You can download it from: https://huggingface.co/$HF_REPO"
    exit 1

else
    echo "ERROR: Unknown format '$FORMAT'. Use 'gguf' or 'hf'."
    exit 1
fi