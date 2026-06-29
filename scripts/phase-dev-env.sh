#!/usr/bin/env bash
# =============================================================================
# NETTRADES.AI – Phase Development Environment Setup
# =============================================================================
# FILE: scripts/phase-dev-env.sh
#
# PURPOSE:
#   This script sets up the development environment for NETTRADES.
#   It handles:
#     - Creating a Python virtual environment
#     - Installing all dependencies (torch, transformers, datasets, accelerate,
#       langchain, langgraph)
#     - Installing odoo_llm and Odoo requirements
#     - Installing the odoo-proxy service
#     - Fixing known vulnerabilities (Starlette)
#     - Installing Odoo modules in the correct order
#     - Validating the installation
#
# USAGE:
#   ./scripts/phase-dev-env.sh [--force]
#
# OPTIONS:
#   --force    Re-run even if already completed (idempotency).
#
# =============================================================================

set -e          # Exit on error
set -u          # Exit on undefined variable

# -----------------------------------------------------------------------------
# 1. Configuration
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PLATFORM_DIR/venv"

# Phase completion marker
PHASE_MARKER="$PLATFORM_DIR/.phase-1-complete"

# Check for --force flag
FORCE=false
for arg in "$@"; do
    if [[ "$arg" == "--force" ]]; then
        FORCE=true
    fi
done

# If phase already completed and not forcing, exit
if [ -f "$PHASE_MARKER" ] && [ "$FORCE" != true ]; then
    echo -e "${YELLOW}[WARNING] Phase 1 already completed. Use --force to re-run.${NC}"
    exit 0
fi

# Colour codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# 2. Helper Functions
# -----------------------------------------------------------------------------
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed or not in PATH"
        exit 1
    fi
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_info "Python version: $PYTHON_VERSION"
    if [[ $(echo "$PYTHON_VERSION" | cut -d. -f1,2) < "3.10" ]]; then
        log_error "Python 3.10 or higher is required"
        exit 1
    fi
}

check_wsl() {
    if grep -q Microsoft /proc/version 2>/dev/null; then
        log_info "Running in WSL environment"
        export IS_WSL=1
    else
        export IS_WSL=0
    fi
}

# -----------------------------------------------------------------------------
# 3. Main Setup Functions
# -----------------------------------------------------------------------------
setup_virtual_environment() {
    log_info "Setting up Python virtual environment..."
    if [ -d "$VENV_DIR" ]; then
        log_warning "Virtual environment already exists at $VENV_DIR"
        read -p "Do you want to recreate it? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Removing existing virtual environment..."
            rm -rf "$VENV_DIR"
        else
            log_info "Keeping existing virtual environment"
            return 0
        fi
    fi
    log_info "Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    # Activate the environment (source it)
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    log_success "Virtual environment created and activated"
}

install_dependencies() {
    log_info "Installing Python dependencies..."

    # Ensure virtual environment is active
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        # shellcheck source=/dev/null
        source "$VENV_DIR/bin/activate"
    fi

    log_info "Upgrading pip..."
    pip install --upgrade pip setuptools wheel

    # =========================================================================
    # Install ML packages (torch, transformers, datasets, accelerate)
    # =========================================================================
    log_info "Installing torch, transformers, datasets, accelerate..."
    for pkg in torch transformers datasets accelerate; do
        if pip show "$pkg" &> /dev/null; then
            log_info "Package $pkg is already installed"
        else
            log_info "Installing $pkg..."
            pip install "$pkg"
        fi
    done

    # =========================================================================
    # Install LangGraph and LangChain providers
    # =========================================================================
    log_info "Installing LangGraph and LangChain providers..."
    local lang_packages=(
        "langgraph"
        "langgraph-checkpoint-postgres"
        "langchain-openai"
        "langchain-anthropic"
        "langchain-ollama"
        "langchain-deepseek"
        "langchain-core"
    )
    for pkg in "${lang_packages[@]}"; do
        if pip show "$pkg" &> /dev/null; then
            log_info "Package $pkg is already installed"
        else
            log_info "Installing $pkg..."
            pip install "$pkg"
        fi
    done

    # =========================================================================
    # Install odoo_llm requirements
    # =========================================================================
    ODOO_LLM_REQS="$PLATFORM_DIR/third-party/odoo_llm/requirements.txt"
    if [ -f "$ODOO_LLM_REQS" ]; then
        log_info "Installing odoo_llm requirements..."
        pip install -r "$ODOO_LLM_REQS"
        log_success "odoo_llm requirements installed"
    else
        log_warning "odoo_llm requirements file not found at $ODOO_LLM_REQS"
    fi

    # =========================================================================
    # Install Odoo core requirements
    # =========================================================================
    ODOO_REQS="$PLATFORM_DIR/third-party/odoo/requirements.txt"
    if [ -f "$ODOO_REQS" ]; then
        log_info "Installing Odoo core requirements..."
        pip install -r "$ODOO_REQS"
        log_success "Odoo core requirements installed"
    else
        log_warning "Odoo requirements file not found at $ODOO_REQS"
    fi

    # =========================================================================
    # Install prometheus-client for metrics
    # =========================================================================
    if pip show prometheus-client &> /dev/null; then
        log_info "prometheus-client is already installed"
    else
        log_info "Installing prometheus-client..."
        pip install prometheus-client
    fi

    # =========================================================================
    # Upgrade Starlette (security fix for CVE-2026-48710)
    # =========================================================================
    log_info "Upgrading Starlette (CVE-2026-48710 fix)..."
    pip install --upgrade "starlette>=1.0.1"
    log_success "Starlette upgraded"

    log_success "All dependencies installed successfully"
}

setup_odoo_proxy() {
    log_info "Setting up odoo-proxy service..."
    ODOO_PROXY_DIR="$PLATFORM_DIR/src/core/odoo_proxy"

    if [ ! -d "$ODOO_PROXY_DIR" ]; then
        log_info "Creating odoo-proxy directory..."
        mkdir -p "$ODOO_PROXY_DIR"
    fi

    # Create main.py if it doesn't exist
    if [ ! -f "$ODOO_PROXY_DIR/main.py" ]; then
        log_info "Creating odoo-proxy main.py..."
        cat > "$ODOO_PROXY_DIR/main.py" << 'EOF'
# =============================================================================
# Odoo JSON-RPC Proxy
# =============================================================================
# This FastAPI service provides a secure HTTP JSON-RPC endpoint that proxies
# calls to the Odoo server. It validates an API key sent in the request headers
# and forwards the JSON-RPC payload to Odoo's internal endpoint.
#
# It is intended to replace the broken mcp-odoo integration.
# =============================================================================

import os
import json
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse

ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "change_me_in_production")
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "change_me_in_production")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.on_event("startup")
async def startup():
    app.state.client = httpx.AsyncClient(timeout=60.0)

@app.on_event("shutdown")
async def shutdown():
    await app.state.client.aclose()

@app.post("/jsonrpc")
async def jsonrpc_proxy(request: Request):
    auth = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if auth != PROXY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    body = await request.json()
    client = request.app.state.client

    try:
        resp = await client.post(f"{ODOO_URL}/jsonrpc", json=body)
        return JSONResponse(content=resp.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3000)
EOF
        log_success "odoo-proxy main.py created"
    else
        log_info "odoo-proxy main.py already exists"
    fi

    # Create requirements.txt for odoo-proxy
    if [ ! -f "$ODOO_PROXY_DIR/requirements.txt" ]; then
        log_info "Creating odoo-proxy requirements.txt..."
        cat > "$ODOO_PROXY_DIR/requirements.txt" << 'EOF'
fastapi==0.115.6
uvicorn[standard]==0.34.0
httpx==0.28.1
EOF
        log_success "odoo-proxy requirements.txt created"
    fi

    log_success "odoo-proxy setup complete"
}

install_odoo_modules() {
    log_info "Installing Odoo modules in the correct order..."

    # Ensure virtual environment is active
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        # shellcheck source=/dev/null
        source "$VENV_DIR/bin/activate"
    fi

    ADDONS_PATH=".\third-party\odoo\addons,.\odoo-modules,.\third-party\odoo_llm,.\third-party\odoo_llm_compat,.\third-party\website_sale_marketplace,.\third-party\queue-19"

    # Batch 1: Foundation modules
    log_info "Batch 1: Installing foundation modules..."
    python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
        -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
        --addons-path="$ADDONS_PATH" \
        -i queue_job,queue_job_batch,queue_job_cron,llm,llm_tool,llm_store,llm_pgvector,llm_knowledge,llm_assistant,llm_thread,llm_generate,llm_training \
        --stop-after-init || log_warning "Batch 1 had errors"

    # Batch 2: NETTRADES Core
    log_info "Batch 2: Installing NETTRADES Core..."
    python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
        -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
        --addons-path="$ADDONS_PATH" \
        -i nettrades_core \
        --stop-after-init || log_warning "Batch 2 had errors"

    # Batch 3: Core NETTRADES modules
    log_info "Batch 3: Installing core NETTRADES modules..."
    python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
        -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
        --addons-path="$ADDONS_PATH" \
        -i nettrades_gpu_admin,nettrades_gpustack_adapter,nettrades_good_answer,nettrades_ask_someone,nettrades_queue,nettrades_notifications,nettrades_job_matching,nettrades_lead_scoring,nettrades_chatbot \
        --stop-after-init || log_warning "Batch 3 had errors"

    # Batch 4: Self-improving system modules
    log_info "Batch 4: Installing self-improving modules..."
    python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
        -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
        --addons-path="$ADDONS_PATH" \
        -i nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config \
        --stop-after-init || log_warning "Batch 4 had errors"

    # Batch 5: LLM Configuration
    log_info "Batch 5: Installing LLM Configuration module..."
    python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
        -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
        --addons-path="$ADDONS_PATH" \
        -i nettrades_llm_config \
        --stop-after-init || log_warning "Batch 5 had errors"

    # Batch 6: Additional modules
    log_info "Batch 6: Installing additional modules..."
    python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
        -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
        --addons-path="$ADDONS_PATH" \
        -i nettrades_fairness,nettrades_onboarding,nettrades_proposals,nettrades_research,nettrades_pwa \
        --stop-after-init || log_warning "Batch 6 had errors"

    log_success "Odoo modules installation completed"
}

validate_installation() {
    log_info "Validating installation..."

    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        # shellcheck source=/dev/null
        source "$VENV_DIR/bin/activate"
    fi

    # Check key packages
    local packages=("langgraph" "fastapi" "uvicorn" "torch" "transformers" "datasets")
    for pkg in "${packages[@]}"; do
        if pip show "$pkg" &> /dev/null; then
            log_success "Package $pkg installed"
        else
            log_warning "Package $pkg not found"
        fi
    done

    # Check Starlette version
    STARLETTE_VERSION=$(pip show starlette | grep Version | cut -d' ' -f2)
    if [[ "$STARLETTE_VERSION" >= "1.0.1" ]]; then
        log_success "Starlette version $STARLETTE_VERSION (vulnerability fixed)"
    else
        log_warning "Starlette version $STARLETTE_VERSION (may be vulnerable to CVE-2026-48710)"
    fi

    # Check that Odoo binary exists
    if [[ -f "$PLATFORM_DIR/third-party/odoo/odoo-bin" ]]; then
        log_success "Odoo binary found"
    else
        log_error "Odoo binary not found"
        exit 1
    fi

    log_success "Installation validation complete"
}

# -----------------------------------------------------------------------------
# 4. Main Execution
# -----------------------------------------------------------------------------
main() {
    log_info "========================================="
    log_info "NETTRADES Development Environment Setup"
    log_info "========================================="

    check_python
    check_wsl

    # Ensure we are in the correct directory
    if [[ ! -f "$PLATFORM_DIR/third-party/odoo/odoo-bin" ]]; then
        log_error "Cannot find Odoo binary. Make sure you are in the nettrades-platform directory."
        exit 1
    fi

    setup_virtual_environment
    install_dependencies
    setup_odoo_proxy
    install_odoo_modules
    validate_installation

    # Mark phase complete
    echo "$(date -Iseconds)" > "$PHASE_MARKER"

    log_info "========================================="
    log_success "Development environment setup complete!"
    log_info ""
    log_info "To activate the virtual environment:"
    log_info "  source $VENV_DIR/bin/activate (Linux/Mac)"
    log_info "  $VENV_DIR\\Scripts\\activate (Windows)"
    log_info ""
    log_info "To start Odoo:"
    log_info "  python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf --addons-path=..."
    log_info ""
    log_info "To start odoo-proxy:"
    log_info "  cd src/core/odoo_proxy && uvicorn main:app --host 0.0.0.0 --port 3000"
    log_info "========================================="
}

# Run main
main "$@"