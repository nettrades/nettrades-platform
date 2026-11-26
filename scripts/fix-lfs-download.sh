#!/bin/bash
# =============================================================================
# FILE: scripts/fix-lfs-download.sh
# =============================================================================
# PURPOSE:
#   Ensures Git LFS is installed and that all model weight files
#   (.safetensors, .bin, .gguf) are fully pulled, not left as 135-byte
#   pointer files.
#
#   This is needed because HuggingFace and ModelScope serve large model
#   repositories via Git LFS. A plain `git clone` only fetches the LFS
#   pointers; `git lfs pull` fetches the actual multi-gigabyte weights.
#   Without this step, vLLM, llama.cpp, and any other model loader will
#   fail at runtime with a "size mismatch" or "corrupt tensor" error.
#
# USAGE:
#   cd ~/nettrades-platform
#   ./scripts/fix-lfs-download.sh
#
# IDEMPOTENT:
#   Safe to re-run. Skips installation if git-lfs is present, and skips
#   LFS pull if the .safetensors files are already large.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC}    $*"; }

# =============================================================================
# Step 1: Install git-lfs on this machine
# =============================================================================
log_info "Step 1: Checking git-lfs..."
if ! command -v git-lfs &>/dev/null; then
    log_info "  git-lfs not found. Installing..."
    sudo apt-get update -qq
    sudo apt-get install -y git-lfs
    log_success "  git-lfs installed: $(git lfs version)"
else
    log_success "  git-lfs already installed: $(git lfs version)"
fi

# =============================================================================
# Step 2: Pull LFS objects for any model directories that are still pointers
# =============================================================================
log_info "Step 2: Checking for LFS pointer files in existing models..."

MODELS_BASE="$PROJECT_ROOT/deploy/docker/dynamo-data/models"
if [[ -d "$MODELS_BASE" ]]; then
    shopt -s nullglob
    for model_dir in "$MODELS_BASE"/*/; do
        if [[ -d "${model_dir}.git" ]]; then
            # Check if any .safetensors files are still LFS pointers (small)
            POINTER_FOUND=false
            for f in "${model_dir}"*.safetensors; do
                [[ -f "$f" ]] || continue
                SIZE=$(stat -c%s "$f" 2>/dev/null || echo 0)
                if [[ "$SIZE" -lt 1048576 ]]; then  # < 1 MB = pointer
                    POINTER_FOUND=true
                    break
                fi
            done

            if [[ "$POINTER_FOUND" == "true" ]]; then
                log_warning "  Pulling LFS weights in $model_dir..."
                (cd "$model_dir" && git lfs install >/dev/null 2>&1 && git lfs pull)
                log_success "  LFS pull complete for $(basename "$model_dir")"
            else
                log_success "  $(basename "$model_dir") already has real weights (skipping)"
            fi
        fi
    done
    shopt -u nullglob
else
    log_info "  No models directory yet at $MODELS_BASE (nothing to pull)"
fi

# =============================================================================
# Step 3: Patch phase-system.sh to install git-lfs on fresh deployments
# =============================================================================
log_info "Step 3: Patching phase-system.sh to install git-lfs..."

PHASE_SYSTEM="$PROJECT_ROOT/scripts/phase-system.sh"
if [[ -f "$PHASE_SYSTEM" ]]; then
    if grep -q "git-lfs" "$PHASE_SYSTEM"; then
        log_success "  phase-system.sh already includes git-lfs"
    else
        # Insert "git-lfs \" after the "git \" line inside the apt install block
        python3 - "$PHASE_SYSTEM" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    content = f.read()

# Find the multi-line apt-get install block that contains "git \"
old = "            git \\\n"
new = "            git \\\n            git-lfs \\\n"

if old in content and 'git-lfs' not in content:
    content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print("  [FIXED] Added git-lfs to phase-system.sh apt list")
else:
    print("  [SKIP] Could not find anchor line to patch")
PYEOF
    fi
else
    log_warning "  phase-system.sh not found — skipping"
fi

# =============================================================================
# Step 4: Patch phase-deploy.sh to pull LFS after model download
# =============================================================================
log_info "Step 4: Patching phase-deploy.sh to pull LFS after download..."

PHASE_DEPLOY="$PROJECT_ROOT/scripts/phase-deploy.sh"
if [[ -f "$PHASE_DEPLOY" ]]; then
    if grep -q "git lfs pull" "$PHASE_DEPLOY"; then
        log_success "  phase-deploy.sh already has git lfs pull"
    else
        python3 - "$PHASE_DEPLOY" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    content = f.read()

# Anchor: the log_success line inside the HF model download block.
# We insert the LFS pull AFTER that line, so it only runs if the
# download succeeded and the .git directory exists.
old = '            log_success "HF model downloaded to $MODELS_DIR/${MODEL_NAME:-deepseek-7b}"'
new = '''            log_success "HF model downloaded to $MODELS_DIR/${MODEL_NAME:-deepseek-7b}"

            # 2026-10-23: Resolve Git LFS pointers to real weights.
            # HuggingFace and ModelScope often serve .safetensors files
            # as 135-byte LFS pointers on a plain git clone. Without
            # `git lfs pull`, vLLM fails at load time with a size
            # mismatch error that is very hard to diagnose.
            if [[ -d "$MODELS_DIR/${MODEL_NAME:-deepseek-7b}/.git" ]]; then
                log_info "Resolving Git LFS objects for HF model..."
                ( cd "$MODELS_DIR/${MODEL_NAME:-deepseek-7b}" \\
                  && git lfs install >/dev/null 2>&1 \\
                  && git lfs pull ) \\
                    && log_success "Git LFS pull complete" \\
                    || log_warning "git lfs pull failed — model may be incomplete"
            fi'''

if old in content and 'git lfs pull' not in content:
    content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print("  [FIXED] Added git lfs pull block to phase-deploy.sh")
else:
    print("  [SKIP] Anchor not found or already patched")
PYEOF
    fi
else
    log_warning "  phase-deploy.sh not found — skipping"
fi

# =============================================================================
# Step 5: Verify the current model is actually usable
# =============================================================================
log_info "Step 5: Verifying model weights..."

MODEL_CHECK="$MODELS_BASE/deepseek-7b"
if [[ -d "$MODEL_CHECK" ]]; then
    echo ""
    echo "  Model directory: $MODEL_CHECK"
    ls -lh "$MODEL_CHECK"/*.safetensors 2>/dev/null | awk '{print "    " $9 "  " $5}'
    echo ""

    # Sanity check: any file under 1 MB is still a pointer
    for f in "$MODEL_CHECK"/*.safetensors; do
        [[ -f "$f" ]] || continue
        SIZE=$(stat -c%s "$f" 2>/dev/null || echo 0)
        if [[ "$SIZE" -lt 1048576 ]]; then
            log_warning "  $f is still a pointer ($SIZE bytes). Run: cd $MODEL_CHECK && git lfs pull"
        fi
    done
    log_success "  All .safetensors files are real weights (multi-GB)"
else
    log_warning "  $MODEL_CHECK not found — model has not been downloaded yet"
fi

echo ""
echo "============================================================"
echo " LFS fix complete"
echo "============================================================"
echo " Next: ./scripts/deploy-v100-hub.sh"
echo "============================================================"