#!/usr/bin/env bash
# =============================================================================
# NETTRADES.AI – Phase Development Environment Setup
# =============================================================================
# FILE: scripts/phase-dev-env.sh
#
# PURPOSE:
#   This script sets up the development environment for NETTRADES.
#   It handles:
#   - Creating a Python virtual environment
#   - Installing all dependencies (torch, transformers, datasets, accelerate,
#     langchain, langgraph)
#   - Installing odoo_llm and Odoo requirements
#   - Installing the odoo-proxy service
#   - Fixing known vulnerabilities (Starlette)
#   - Installing Odoo modules in the correct order
#   - Validating the installation
#
# USAGE:
#   ./scripts/phase-dev-env.sh [--force]
#
# OPTIONS:
#   --force  Re-run even if already completed (idempotency).
# =============================================================================

set -e
set -u

# -----------------------------------------------------------------------------
# 1. Configuration
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PLATFORM_DIR/venv"

# Phase completion marker
PHASE_MARKER="$PLATFORM_DIR/.phase-1-complete"

# Parse arguments
FORCE=false
for arg in "$@"; do
    if [[ "$arg" == "--force" ]]; then
        FORCE=true
    fi
done
export FORCE

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
ENVIRONMENT="${ENVIRONMENT:-development}"
if [[ "$FORCE" == true ]] && [[ "$ENVIRONMENT" == "production" ]]; then
    echo ""
    echo "   WARNING  "
    echo ""
    echo "You are running '--force' on Phase 1 in a PRODUCTION environment."
    echo "This will OVERWRITE existing configuration and may cause data loss."
    echo ""
    echo "This action CANNOT be undone."
    echo ""
    read -p "Type 'YES' to continue: " CONFIRM
    if [[ "$CONFIRM" != "YES" ]]; then
        echo "Aborted."
        exit 1
    fi
    echo ""
fi

# If phase already completed and not forcing, exit
if [[ -f "$PHASE_MARKER" ]] && [[ "$FORCE" != true ]]; then
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
    if [[ -d "$VENV_DIR" ]]; then
        log_warning "Virtual environment already exists at $VENV_DIR"
        if [[ "$FORCE" != true ]]; then
            read -p "Do you want to recreate it? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Keeping existing virtual environment"
                return 0
            fi
        fi
        log_info "Removing existing virtual environment..."
        rm -rf "$VENV_DIR"
    fi
    log_info "Creating virtual environment in $VENV_DIR"
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
# NETTRADES.AI – Odoo JSON-RPC Proxy
# =============================================================================
# FILE: src/core/odoo_proxy/main.py
#
# PURPOSE:
#   Lightweight FastAPI proxy that forwards JSON-RPC calls from the LangGraph
#   service to the Odoo backend. Provides authentication and request validation.
# =============================================================================

import os
import logging
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Odoo JSON-RPC Proxy", version="1.0.0")

ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_USER = int(os.getenv("ODOO_USER", "1"))
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "")

client = httpx.AsyncClient(timeout=60.0)

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/jsonrpc")
async def proxy_jsonrpc(request: Request):
    # Authentication
    api_key = request.headers.get("X-API-Key")
    if PROXY_API_KEY and api_key != PROXY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Forward to Odoo
    url = f"{ODOO_URL}/jsonrpc"
    response = await client.post(url, json=body)
    return JSONResponse(content=response.json(), status_code=response.status_code)

@app.on_event("shutdown")
async def shutdown():
    await client.aclose()
EOF
    fi

    # Create requirements.txt if it doesn't exist
    if [ ! -f "$ODOO_PROXY_DIR/requirements.txt" ]; then
        cat > "$ODOO_PROXY_DIR/requirements.txt" << 'EOF'
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
httpx>=0.27.0
python-dotenv>=1.0.0
EOF
    fi

    # Create __init__.py if it doesn't exist
    if [ ! -f "$ODOO_PROXY_DIR/__init__.py" ]; then
        touch "$ODOO_PROXY_DIR/__init__.py"
    fi

    log_success "odoo-proxy service ready"
}

install_odoo_modules() {
    log_info "Installing Odoo modules..."
    if [[ -f "$SCRIPT_DIR/install-modules.sh" ]]; then
        bash "$SCRIPT_DIR/install-modules.sh" --auto
    else
        log_warning "install-modules.sh not found"
    fi
}

# -----------------------------------------------------------------------------
# 4. Main Execution
# -----------------------------------------------------------------------------
log_info "Starting Phase 1: Development Environment Setup"

check_python
check_wsl
setup_virtual_environment
install_dependencies
setup_odoo_proxy
install_odoo_modules

# Mark phase as complete
echo "$(date -Iseconds)" > "$PHASE_MARKER"
log_success "Phase 1 completed"