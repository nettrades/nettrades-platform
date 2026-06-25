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
#   - Installing all dependencies
#   - Setting up Odoo, LLM modules, and core components
#   - Fixing known vulnerabilities
#   - Validating the installation
#
# USAGE:
#   ./scripts/phase-dev-env.sh
#
# =============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# -----------------------------------------------------------------------------
# 1. Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PLATFORM_DIR/venv"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# 2. Helper Functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed or not in PATH"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_info "Python version: $PYTHON_VERSION"
    
    # Check if Python 3.10+
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
    
    # Activate venv
    if [[ "$IS_WSL" -eq 1 ]]; then
        source "$VENV_DIR/bin/activate"
    else
        source "$VENV_DIR/bin/activate"
    fi
    
    log_success "Virtual environment created and activated"
}

install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Activate venv if not already
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        source "$VENV_DIR/bin/activate"
    fi
    
    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip setuptools wheel
    
    # =========================================================================
    # Install development tools
    # =========================================================================
    log_info "=== Installing development tools ==="
    
    if [[ "$IS_WSL" -eq 1 ]]; then
        # Convert Linux path to Windows path for Python on Windows
        WIN_REQUIREMENTS_PATH=$(wslpath -w "$PLATFORM_DIR/requirements-dev.txt" 2>/dev/null || echo "$PLATFORM_DIR/requirements-dev.txt")
        "$VENV_DIR/Scripts/python.exe" -m pip install -r "$WIN_REQUIREMENTS_PATH" || \
            "$VENV_DIR/bin/python" -m pip install -r "$PLATFORM_DIR/requirements-dev.txt"
    else
        pip install -r "$PLATFORM_DIR/requirements-dev.txt"
    fi
    
    # =========================================================================
    # Install core Odoo dependencies
    # =========================================================================
    log_info "=== Installing core Odoo dependencies (third-party Odoo) ==="
    
    if [[ "$IS_WSL" -eq 1 ]]; then
        WIN_ODOO_REQUIREMENTS_PATH=$(wslpath -w "$PLATFORM_DIR/third-party/odoo/requirements.txt" 2>/dev/null || echo "$PLATFORM_DIR/third-party/odoo/requirements.txt")
        "$VENV_DIR/Scripts/python.exe" -m pip install -r "$WIN_ODOO_REQUIREMENTS_PATH" || \
            "$VENV_DIR/bin/python" -m pip install -r "$PLATFORM_DIR/third-party/odoo/requirements.txt"
    else
        pip install -r "$PLATFORM_DIR/third-party/odoo/requirements.txt"
    fi
    
    # =========================================================================
    # Install community LLM module dependencies
    # =========================================================================
    log_info "=== Installing community LLM module dependencies ==="
    
    if [[ "$IS_WSL" -eq 1 ]]; then
        WIN_ODOO_LLM_REQUIREMENTS_PATH=$(wslpath -w "$PLATFORM_DIR/third-party/odoo_llm/requirements.txt" 2>/dev/null || echo "$PLATFORM_DIR/third-party/odoo_llm/requirements.txt")
        "$VENV_DIR/Scripts/python.exe" -m pip install -r "$WIN_ODOO_LLM_REQUIREMENTS_PATH" || \
            "$VENV_DIR/bin/python" -m pip install -r "$PLATFORM_DIR/third-party/odoo_llm/requirements.txt"
    else
        pip install -r "$PLATFORM_DIR/third-party/odoo_llm/requirements.txt"
    fi
    
    # =========================================================================
    # Install core orchestrator dependencies
    # =========================================================================
    log_info "=== Installing NETTRADES orchestrator dependencies (LangGraph, FastAPI, etc.) ==="
    
    if [[ "$IS_WSL" -eq 1 ]]; then
        WIN_CORE_REQUIREMENTS_PATH=$(wslpath -w "$PLATFORM_DIR/src/core/requirements.txt" 2>/dev/null || echo "$PLATFORM_DIR/src/core/requirements.txt")
        "$VENV_DIR/Scripts/python.exe" -m pip install -r "$WIN_CORE_REQUIREMENTS_PATH" || \
            "$VENV_DIR/bin/python" -m pip install -r "$PLATFORM_DIR/src/core/requirements.txt"
    else
        pip install -r "$PLATFORM_DIR/src/core/requirements.txt"
    fi
    
    # =========================================================================
    # Fix Starlette vulnerability (CVE-2026-48710 - BadHost)
    # =========================================================================
    log_info "=== FastAPI, LiteLLM and VLLM are built on top of Starlette. ==="
    log_info "=== Starlette v1.0.0 has a vulnerability, tracked as CVE-2026-48710 ==="
    log_info "=== and under the name BadHost. Upgrading to Starlette v1.0.1... ==="
    
    if [[ "$IS_WSL" -eq 1 ]]; then
        "$VENV_DIR/Scripts/python.exe" -m pip install --upgrade "starlette>=1.0.1" || \
            "$VENV_DIR/bin/python" -m pip install --upgrade "starlette>=1.0.1"
    else
        pip install --upgrade "starlette>=1.0.1"
    fi
    
    log_success "All dependencies installed successfully"
}

install_odoo_modules() {
    log_info "Installing NETTRADES Odoo modules..."
    
    # Activate venv if not already
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        source "$VENV_DIR/bin/activate"
    fi
    
    # Build addons path
    ADDONS_PATH=".\third-party\odoo\addons,.\odoo-modules,.\third-party\odoo_llm,.\third-party\odoo_llm_compat,.\third-party\website_sale_marketplace,.\third-party\queue_job,.\third-party\queue_job\queue_job"
    
    # Install core modules first
    log_info "Installing nettrades_core module..."
    
    if [[ "$IS_WSL" -eq 1 ]]; then
        "$VENV_DIR/Scripts/python.exe" "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
            -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
            --addons-path="$ADDONS_PATH" \
            -i nettrades_core \
            --stop-after-init || {
            log_error "Failed to install nettrades_core"
            exit 1
        }
        
        # Install remaining modules
        log_info "Installing remaining modules..."
        "$VENV_DIR/Scripts/python.exe" "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
            -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
            --addons-path="$ADDONS_PATH" \
            -i nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config \
            --stop-after-init || {
            log_error "Failed to install remaining modules"
            exit 1
        }
    else
        python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
            -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
            --addons-path="$ADDONS_PATH" \
            -i nettrades_core \
            --stop-after-init || {
            log_error "Failed to install nettrades_core"
            exit 1
        }
        
        # Install remaining modules
        log_info "Installing remaining modules..."
        python "$PLATFORM_DIR/third-party/odoo/odoo-bin" \
            -c "$PLATFORM_DIR/deploy/docker/config/odoo.conf" \
            --addons-path="$ADDONS_PATH" \
            -i nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config \
            --stop-after-init || {
            log_error "Failed to install remaining modules"
            exit 1
        }
    fi
    
    log_success "All Odoo modules installed successfully"
}

validate_installation() {
    log_info "Validating installation..."
    
    # Check virtual environment
    if [[ ! -d "$VENV_DIR" ]]; then
        log_error "Virtual environment not found at $VENV_DIR"
        exit 1
    fi
    log_success "Virtual environment found"
    
    # Activate venv
    source "$VENV_DIR/bin/activate"
    
    # Check key packages
    local packages=("langgraph" "fastapi" "uvicorn" "postgres")
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
    
    # Check if running in correct directory
    if [[ ! -f "$PLATFORM_DIR/third-party/odoo/odoo-bin" ]]; then
        log_error "Cannot find Odoo binary. Make sure you are in the nettrades-platform directory."
        exit 1
    fi
    
    setup_virtual_environment
    install_dependencies
    install_odoo_modules
    validate_installation
    
    log_info "========================================="
    log_success "Development environment setup complete!"
    log_info ""
    log_info "To activate the virtual environment:"
    log_info "  source $VENV_DIR/bin/activate (Linux/Mac)"
    log_info "  $VENV_DIR\\Scripts\\activate (Windows)"
    log_info ""
    log_info "To start Odoo:"
    log_info "  python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf --addons-path=... -u all"
    log_info "========================================="
}

# Run main
main "$@"