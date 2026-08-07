#!/bin/bash
# =============================================================================
# FILE: scripts/nettrades-setup.sh
# =============================================================================
# PURPOSE:
#   NETTRADES platform unified setup orchestrator.
#   Single entry point for installation, deployment, modules, monitoring.
#
# PHASES:
#   0 – System Preparation & Hardening
#   1 – Development Environment (with Python virtual environment)
#   2 – Single-VM Deployment (with NVIDIA Dynamo + llama.cpp fallback)
#   3 – Kubernetes Scaling
#   4 – Module Installation
#   5 – Monitoring Setup
#
# INFERENCE ARCHITECTURE:
#   - Primary: NVIDIA Dynamo (GPU-accelerated, distributed, includes vLLM)
#   - Fallback: llama.cpp (CPU, zero-dependency)
#   - Odoo provides governance and GPU resource management
#
# USAGE:
#   ./nettrades-setup.sh <PROFILE> [options]   (CLI mode)
#   ./nettrades-setup.sh                       (Interactive wizard)
#   ./nettrades-setup.sh --help                Show help.
#
# NEW OPTIONS:
#   --production        Set environment to production (applies hardening)
#   --development       Set environment to development (no hardening) [default]
#   --regenerate-secrets Regenerate all secrets in .env (use with caution)
#   --reset-data        Wipe all containers and volumes (destroys data!)
#   --with-finetune     Install fine-tuning packages (torch, unsloth, axolotl)
#   --platform          Override platform detection (linux, macos, wsl)
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Script setup and paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Read feature flags (early, for installer UI)
# -----------------------------------------------------------------------------
read_feature_flags

# -----------------------------------------------------------------------------
# Load .env if present (overrides environment)
# -----------------------------------------------------------------------------
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a          # automatically export all sourced variables
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Default USE_UV to true if not set (user can override via .env or env var)
USE_UV="${USE_UV:-true}"
export USE_UV

# -----------------------------------------------------------------------------
# Python virtual environment setup – exported for all phases
# -----------------------------------------------------------------------------
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
export VENV_DIR

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
ENVIRONMENT="${ENVIRONMENT:-development}"
REGENERATE_SECRETS="${REGENERATE_SECRETS:-false}"
RESET_DATA="${RESET_DATA:-false}"
FORCE=false
UPGRADE=false
SKIP_INSTALLED=true
AUTO=false
WITH_FINETUNE=false
PHASES_LIST=""
PROFILE=""
INTERACTIVE=false
PLATFORM_OVERRIDE=""

# -----------------------------------------------------------------------------
# Show help
# -----------------------------------------------------------------------------
show_help() {
    cat << EOF
${GREEN}NETTRADES.AI – Unified Setup Orchestrator${NC}

${YELLOW}USAGE:${NC}
    ./nettrades-setup.sh <PROFILE> [options]   (CLI mode)
    ./nettrades-setup.sh                       (Interactive wizard)
    ./nettrades-setup.sh --help                Show this help.

${YELLOW}ENVIRONMENTS:${NC}
    --development   Development mode (no SSH hardening, firewall relaxed) [default]
    --production    Production mode (SSH hardening, UFW, WireGuard, fail2ban)

${YELLOW}PHASES:${NC}
    0  System Preparation & Hardening
    1  Development Environment (with Python virtual environment)
    2  Single-VM Deployment (with NVIDIA Dynamo + llama.cpp fallback)
    3  Kubernetes Scaling
    4  Module Installation
    5  Monitoring Setup

${YELLOW}PROFILES (CLI):${NC}
    dev         : Phase 1 (development environment)
    deploy      : Phase 0 + Phase 1 + Phase 2 (single-VM deployment)
    k8s         : Phase 0 + Phase 1 + Phase 3 (Kubernetes scaling)
    monitoring  : Phase 5 (Prometheus & Grafana setup)
    modules     : Phase 4 (install/upgrade Odoo modules only)
    all         : Phase 0 + Phase 1 + Phase 2 + Phase 4 + Phase 5 (full deployment)

${YELLOW}OPTIONS (CLI):${NC}
    --force               Re-run phases even if already completed.
    --upgrade             Upgrade existing modules instead of fresh install.
    --skip-installed      Skip already installed Odoo modules.
    --auto                Run in non-interactive mode (use defaults, no prompts).
    --regenerate-secrets  Regenerate ALL secrets in .env (breaks running services!).
    --reset-data          Wipe ALL containers and volumes (destroys all data!).
    --phases=LIST         Comma-separated list of phases (overrides profile).
    --with-finetune       Install large fine-tuning packages (torch, unsloth, axolotl).
    --platform            Override platform detection (linux, macos, wsl).

${YELLOW}EXAMPLES:${NC}
    ./nettrades-setup.sh                        # Interactive wizard
    ./nettrades-setup.sh deploy --auto          # Automated deploy (development)
    ./nettrades-setup.sh deploy --production    # Deploy with production hardening
    ./nettrades-setup.sh all --force            # Full re-deployment (keeps data)
    ./nettrades-setup.sh all --with-finetune    # Include fine-tuning packages
EOF
}

# =============================================================================
# INTERACTIVE WIZARD
# =============================================================================

run_interactive() {
    log_header "NETTRADES Setup Wizard (Interactive Mode)"

    # --- Profile selection ---
    echo ""
    echo "Available profiles:"
    echo "  1) dev         - Development environment (Phase 1 only)"
    echo "  2) deploy      - Single-VM Docker deployment (with NVIDIA Dynamo + llama.cpp)"
    echo "  3) k8s         - Kubernetes scaling (Talos, Argo CD)"
    echo "  4) monitoring  - Prometheus & Grafana monitoring stack (Phase 5)"
    echo "  5) modules     - Install/upgrade Odoo modules only (Phase 4)"
    echo "  6) all         - Full deployment (Phases 0,1,2,4,5)"
    echo ""
    read -rp "Enter the number of your choice (1-6): " profile_choice

    case "$profile_choice" in
        1) PROFILE="dev" ;;
        2) PROFILE="deploy" ;;
        3) PROFILE="k8s" ;;
        4) PROFILE="monitoring" ;;
        5) PROFILE="modules" ;;
        6) PROFILE="all" ;;
        *) log_error "Invalid choice"; exit 1 ;;
    esac
    log_info "Selected profile: $PROFILE"

    echo ""
    echo "Select environment:"
    echo "  1) Development (no hardening, SSH password auth kept)"
    echo "  2) Production (SSH hardening, UFW, WireGuard, fail2ban)"
    read -rp "Enter 1 or 2: " env_choice
    case "$env_choice" in
        1) ENVIRONMENT="development" ;;
        2) ENVIRONMENT="production" ;;
        *) log_error "Invalid choice"; exit 1 ;;
    esac
    log_info "Environment: $ENVIRONMENT"

    echo ""
    read -rp "Force re-run completed phases? (y/N): " force_yn
    [[ "$force_yn" =~ ^[Yy]$ ]] && FORCE=true || FORCE=false

    read -rp "Upgrade modules instead of fresh install? (y/N): " upgrade_yn
    [[ "$upgrade_yn" =~ ^[Yy]$ ]] && UPGRADE=true || UPGRADE=false

    read -rp "Fine Tuning packages take too long to install. (You could install them later if you want to fine tune your models by running pip install -r requirements-finetune.txt) It is best to press n if you are just getting started. Do you want to install fine-tuning packages (torch, unsloth, axolotl)? (y/N): " finetune_yn
    [[ "$finetune_yn" =~ ^[Yy]$ ]] && WITH_FINETUNE=true || WITH_FINETUNE=false

    read -rp "Auto mode (non-interactive, no prompts)? (y/N): " auto_yn
    [[ "$auto_yn" =~ ^[Yy]$ ]] && AUTO=true || AUTO=false

    # --- Determine phases ---
    case "$PROFILE" in
        dev) PHASES=(1) ;;
        deploy) PHASES=(0 1 2) ;;
        k8s) PHASES=(0 1 3) ;;
        monitoring) PHASES=(5) ;;
        modules) PHASES=(4) ;;
        all) PHASES=(0 1 2 4 5) ;;
    esac

    # --- Confirm ---
    echo ""
    echo -e "${YELLOW}Summary:${NC}"
    echo "  Profile: $PROFILE"
    echo "  Environment: $ENVIRONMENT"
    echo "  Force: $FORCE"
    echo "  Upgrade: $UPGRADE"
    echo "  Auto: $AUTO"
    echo "  With Fine-tuning: $WITH_FINETUNE"
    echo "  Phases: ${PHASES[*]}"
    echo ""
    read -rp "Proceed with these settings? (y/N): " confirm
    [[ ! "$confirm" =~ ^[Yy]$ ]] && { log_info "Aborted."; exit 0; }

    export FORCE UPGRADE AUTO ENVIRONMENT WITH_FINETUNE
}

# =============================================================================
# Install uv (fast Python package installer)
# =============================================================================
install_uv() {
    if command -v uv &>/dev/null; then
        log_success "uv already installed"
        return 0
    fi
    log_step "Installing uv (fast Python package installer)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Ensure uv is in PATH for the current session (default install location is ~/.local/bin)
    export PATH="$HOME/.local/bin:$PATH"
    # Also add to .bashrc for future sessions
    if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi
    # Verify installation
    if command -v uv &>/dev/null; then
        log_success "uv installed successfully"
        return 0
    else
        log_error "uv installation failed. Falling back to pip."
        return 1
    fi
}

# =============================================================================
# PHASE 1: Development Environment (with Python virtual environment)
# =============================================================================

setup_dev_environment() {
    local os
    os=$(detect_os)

    log_step "Setting up development environment..."

    # ============================================================
    # Python virtual environment setup
    # ============================================================

    # Check if venv module is available
    if ! python3 -c "import venv" 2>/dev/null; then
        log_error "python3-venv not installed. Please install it:"
        log_info "  Ubuntu/Debian: sudo apt install python3-venv"
        log_info "  macOS: brew install python3"
        exit 1
    fi

    # Create virtual environment if it doesn't exist OR if FORCE is true
    if [[ ! -d "$VENV_DIR" ]] || [[ "$FORCE" == true ]]; then
        log_step "Creating Python virtual environment at $VENV_DIR..."
        python3 -m venv "$VENV_DIR"
        log_success "Virtual environment created"
    else
        log_info "Virtual environment already exists at $VENV_DIR (use --force to recreate)"
    fi

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    log_success "Virtual environment activated"

    # Upgrade pip inside the venv
    log_step "Upgrading pip in virtual environment..."
    pip install --upgrade pip
    log_success "pip upgraded"

    # ============================================================
    # Make all scripts executable
    # ============================================================
    log_step "Making scripts executable..."
    chmod +x "$PROJECT_ROOT"/scripts/*.sh 2>/dev/null || true
    chmod +x "$PROJECT_ROOT"/scripts/lib/*.sh 2>/dev/null || true
    log_success "Scripts made executable"

    # Fix line endings
    if [[ -f "$PROJECT_ROOT/scripts/fix-line-endings.sh" ]]; then
        log_step "Fixing line endings (converting to LF)..."
        bash "$PROJECT_ROOT/scripts/fix-line-endings.sh" --force 2>/dev/null || {
            log_warning "fix-line-endings.sh failed – continuing anyway"
        }
    else
        log_warning "fix-line-endings.sh not found – skipping line ending fix"
    fi

    # Install uv only if USE_UV is true
    if [[ "$USE_UV" == "true" ]]; then
        if ! install_uv; then
            log_warning "uv installation failed; falling back to pip."
            USE_UV=false
            export USE_UV
        fi
    else
        log_info "USE_UV=false, skipping uv installation and using pip."
    fi

    # Define requirement files
    local base_req="$PROJECT_ROOT/requirements-base.txt"
    local dev_req="$PROJECT_ROOT/requirements-dev.txt"
    local finetune_req="$PROJECT_ROOT/requirements-finetune.txt"

    # Determine which requirements file to use for base
    local req_file="$dev_req"
    if [[ -f "$base_req" ]]; then
        req_file="$base_req"
    fi

    # Install base Python dependencies inside virtual environment
    if [[ -f "$req_file" ]]; then
        log_step "Installing base Python development dependencies from $(basename "$req_file")..."
        if [[ "$USE_UV" != false ]] && command -v uv &>/dev/null; then
            if ! uv pip install --verbose --index-url https://pypi.org/simple/ -r "$req_file"; then
                log_error "uv installation failed. Falling back to pip."
                pip install --verbose -r "$req_file" || {
                    log_error "Python base dependency installation failed."
                    exit 1
                }
            fi
        else
            pip install --verbose -r "$req_file" || {
                log_error "Python base dependency installation failed."
                exit 1
            }
        fi
    else
        log_warning "No base requirements file found – skipping."
    fi

    # Install fine-tuning dependencies if requested
    if [[ "$WITH_FINETUNE" == true ]]; then
        if [[ -f "$finetune_req" ]]; then
            log_step "Installing fine-tuning packages (torch, unsloth, axolotl) from $(basename "$finetune_req")..."
            if [[ "$USE_UV" != false ]] && command -v uv &>/dev/null; then
                if ! uv pip install --verbose --index-url https://pypi.org/simple/ -r "$finetune_req"; then
                    log_error "uv fine-tune installation failed. Falling back to pip."
                    pip install --verbose -r "$finetune_req" || {
                        log_error "Fine-tune dependency installation failed."
                        exit 1
                    }
                fi
            else
                pip install --verbose -r "$finetune_req" || {
                    log_error "Fine-tune dependency installation failed."
                    exit 1
                }
            fi
        else
            log_warning "requirements-finetune.txt not found – fine-tuning packages skipped."
        fi
    else
        log_info "Skipping fine-tuning packages (use --with-finetune or answer 'y' in interactive mode)."
    fi

    # NOTE: apt-mark hold python3-jwt removed – virtual environment provides isolation

    # NOTE: Odoo module installation has been moved to Phase 2/4.
    # Phase 1 only sets up the local development environment.

    mark_phase_complete 1
}

# =============================================================================
# MAIN SCRIPT
# =============================================================================

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --interactive) INTERACTIVE=true; shift ;;
        --force) FORCE=true; shift ;;
        --upgrade) UPGRADE=true; shift ;;
        --skip-installed) SKIP_INSTALLED=true; shift ;;
        --auto) AUTO=true; shift ;;
        --production) ENVIRONMENT="production"; shift ;;
        --development) ENVIRONMENT="development"; shift ;;
        --regenerate-secrets) REGENERATE_SECRETS=true; shift ;;
        --reset-data) RESET_DATA=true; shift ;;
        --with-finetune) WITH_FINETUNE=true; shift ;;
        --platform)
            PLATFORM_OVERRIDE="$2"
            shift 2
            ;;
        --phases=*) PHASES_LIST="${1#--phases=}"; shift ;;
        --help) show_help; exit 0 ;;
        -*)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
        *)
            if [ -z "$PROFILE" ]; then
                PROFILE="$1"
                shift
            else
                log_error "Extra argument: $1"
                show_help
                exit 1
            fi
            ;;
    esac
done

export ENVIRONMENT REGENERATE_SECRETS RESET_DATA WITH_FINETUNE VENV_DIR

# Set PLATFORM for phase scripts
if [[ -n "$PLATFORM_OVERRIDE" ]]; then
    export PLATFORM="$PLATFORM_OVERRIDE"
else
    export PLATFORM=$(detect_platform)
fi

# -----------------------------------------------------------------------------
# Environment preparation
# -----------------------------------------------------------------------------
prepare_environment() {
    local os
    os=$(detect_os)
    log_info "Detected OS: $os"
    log_info "Environment: $ENVIRONMENT"
    log_info "Platform: $PLATFORM"

    if [[ "$os" == "windows" ]]; then
        if [[ "$(detect_wsl)" == "false" ]]; then
            log_error "Windows detected but NOT inside WSL2."
            cat << EOF
${YELLOW}To enable WSL2:${NC}
  1. Open PowerShell as Administrator and run:
       dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
       dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
       wsl --set-default-version 2
  2. Restart your computer.
  3. Install a Linux distribution from Microsoft Store (e.g., Ubuntu 22.04).
  4. Launch the WSL distribution and re-run this script from inside it.

${GREEN}For the best experience, we recommend running this script inside a WSL terminal.${NC}
EOF
            exit 1
        else
            log_success "Running inside WSL2."

            # Check for Docker Desktop integration
            if ! command -v docker &>/dev/null; then
                log_warning "Docker not found in WSL2."
                log_info "Please install Docker Desktop with WSL2 backend enabled."
                log_info "See: https://docs.docker.com/desktop/wsl/"
                if [[ "$AUTO" != true ]]; then
                    read -rp "Continue anyway? (y/N): " cont
                    [[ ! "$cont" =~ ^[Yy]$ ]] && exit 1
                fi
            else
                log_success "Docker found in WSL2."
            fi
        fi
    elif [[ "$os" == "macos" ]]; then
        log_success "Running on macOS."
        # Check if Homebrew is installed
        if ! command -v brew &>/dev/null; then
            log_warning "Homebrew not found. Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add Homebrew to PATH for this session
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
        if ! command -v docker &>/dev/null; then
            log_warning "Docker not found. Please install Docker Desktop for macOS."
            log_info "See: https://docs.docker.com/desktop/mac/install/"
            if [[ "$AUTO" != true ]]; then
                read -rp "Continue anyway? (y/N): " cont
                [[ ! "$cont" =~ ^[Yy]$ ]] && exit 1
            fi
        fi
    elif [[ "$os" == "linux" ]]; then
        log_success "Running on native Linux."
    else
        log_error "Unsupported OS: $os"
        exit 1
    fi

    # Run global dependency checks
    check_dependencies
}

# -----------------------------------------------------------------------------
# Global Dependency Check
# -----------------------------------------------------------------------------
check_dependencies() {
    local os
    os=$(detect_os)
    local missing=()

    if [[ "$os" == "linux" ]]; then
        for cmd in curl wget git jq; do
            if ! command -v "$cmd" &>/dev/null; then
                missing+=("$cmd")
            fi
        done
        if [[ ${#missing[@]} -gt 0 ]]; then
            log_warning "Missing system packages: ${missing[*]}"
            log_info "Install with: sudo apt-get install -y ${missing[*]}"
            if [[ "$AUTO" != true ]]; then
                read -rp "Continue anyway? (y/N): " cont
                [[ ! "$cont" =~ ^[Yy]$ ]] && exit 1
            fi
        fi
    fi

    # Python 3.10+ – attempt to install if missing
    if ! command -v python3 &>/dev/null; then
        log_error "Python3 not found. Please install Python 3.10 or higher."
        if [[ "$os" == "macos" ]]; then
            if command -v brew &>/dev/null; then
                log_info "Installing Python 3.12 via Homebrew..."
                brew install python@3.12
                export PATH="/usr/local/opt/python@3.12/bin:$PATH"
            else
                log_error "Homebrew not found. Please install Python 3.12 manually."
                exit 1
            fi
        else
            exit 1
        fi
    fi
    local py_version
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ "$(printf '%s\n' "3.10" "$py_version" | sort -V | head -n1)" != "3.10" ]]; then
        log_error "Python version $py_version detected. Need 3.10+."
        if [[ "$os" == "macos" ]]; then
            if command -v brew &>/dev/null; then
                log_info "Installing Python 3.12 via Homebrew..."
                brew install python@3.12
                export PATH="/usr/local/opt/python@3.12/bin:$PATH"
                # Re-check
                py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
                if [[ "$(printf '%s\n' "3.10" "$py_version" | sort -V | head -n1)" != "3.10" ]]; then
                    log_error "Python version $py_version still detected after installation. Please install Python 3.12 manually."
                    exit 1
                fi
            else
                log_error "Homebrew not found. Please install Python 3.12 manually."
                exit 1
            fi
        else
            exit 1
        fi
    fi
    log_success "Python $py_version detected."

    # pip – try apt first (Ubuntu/Debian), then fallback to ensurepip
    if ! command -v pip3 &>/dev/null; then
        log_warning "pip3 not found. Attempting to install..."
        # Try apt first (Ubuntu/Debian)
        if command -v apt &>/dev/null; then
            sudo apt update -qq 2>/dev/null || true
            sudo apt install -y python3-pip 2>/dev/null || {
                log_error "Failed to install pip via apt. Please install manually."
                exit 1
            }
        # Fallback to ensurepip
        else
            python3 -m ensurepip --upgrade 2>/dev/null || {
                log_error "Failed to install pip. Please install manually."
                log_info "On Ubuntu/Debian: sudo apt install python3-pip"
                log_info "On macOS: brew install python3"
                exit 1
            }
        fi
        log_success "pip3 installed"
    else
        log_success "pip3 already installed"
    fi

    # Install build dependencies for Python packages (psycopg2, etc.)
    if [[ "$os" == "linux" ]] && command -v apt &>/dev/null; then
        log_step "Installing build dependencies (build-essential, python3-dev, libpq-dev)..."
        sudo apt update -qq 2>/dev/null || true
        sudo apt install -y build-essential python3-dev libpq-dev 2>/dev/null || {
            log_warning "Failed to install some build dependencies. Continuing anyway."
        }
    elif [[ "$os" == "macos" ]] && command -v brew &>/dev/null; then
        log_step "Installing build dependencies (postgresql) via Homebrew..."
        brew install postgresql 2>/dev/null || {
            log_warning "Failed to install postgresql via Homebrew. Continuing anyway."
        }
    fi
}

# =============================================================================
# Main execution
# =============================================================================

# Prepare environment (OS/WSL checks and dependencies)
prepare_environment

# Interactive mode if requested
if [ "$INTERACTIVE" = true ]; then
    run_interactive
else
    if [[ -z "$PROFILE" && -z "$PHASES_LIST" ]]; then
        log_error "No profile or --phases specified. Use --interactive or provide a profile."
        show_help
        exit 1
    fi
fi

# Determine phases
if [[ -n "$PHASES_LIST" ]]; then
    IFS=',' read -ra PHASES <<< "$PHASES_LIST"
elif [[ -n "$PROFILE" ]]; then
    case "$PROFILE" in
        dev) PHASES=(1) ;;
        deploy) PHASES=(0 1 2) ;;
        k8s) PHASES=(0 1 3) ;;
        monitoring) PHASES=(5) ;;
        modules) PHASES=(4) ;;
        all) PHASES=(0 1 2 4 5) ;;
        *)
            log_error "Unknown profile: $PROFILE"
            show_help
            exit 1
            ;;
    esac
else
    log_error "No phases defined."
    exit 1
fi

export PROJECT_ROOT FORCE UPGRADE SKIP_INSTALLED AUTO

log_header "NETTRADES.AI – Unified Setup"
log_info "Profile: ${PROFILE:-custom}"
log_info "Environment: $ENVIRONMENT"
log_info "Phases: ${PHASES[*]}"
log_info "Force: $FORCE"
log_info "Upgrade: $UPGRADE"
log_info "Auto: $AUTO"
log_info "With Fine-tuning: $WITH_FINETUNE"
log_info "Virtual Environment: $VENV_DIR"
log_info "Platform: $PLATFORM"
echo ""

# -----------------------------------------------------------------------------
# Run phases in sequence
# -----------------------------------------------------------------------------
for phase in "${PHASES[@]}"; do
    case $phase in
        0)
            log_header "Phase 0 — System Preparation & Hardening"
            bash "$SCRIPT_DIR/phase-system.sh"
            ;;
        1)
            log_header "Phase 1 — Development Environment"
            if phase_completed 1 && [[ "$FORCE" != true ]]; then
                log_warning "Phase 1 already completed. Use --force to re-run."
            else
                if ! setup_dev_environment; then
                    log_error "Phase 1 failed. Not marking as complete."
                    exit 1
                fi
                mark_phase_complete 1
            fi
            ;;
        2)
            log_header "Phase 2 — Single-VM Deployment"
            # Ensure VENV_DIR is available for phase-deploy.sh
            export VENV_DIR
            bash "$SCRIPT_DIR/phase-deploy.sh"
            ;;
        3)
            log_header "Phase 3 — Kubernetes Scaling"
            export VENV_DIR
            bash "$SCRIPT_DIR/phase-k8s.sh"
            ;;
        4)
            log_header "Phase 4 — Module Installation"
            export VENV_DIR
            bash "$SCRIPT_DIR/phase-modules.sh"
            ;;
        5)
            log_header "Phase 5 — Monitoring Setup"
            export VENV_DIR
            bash "$SCRIPT_DIR/phase-monitoring.sh"
            ;;
        *)
            log_error "Invalid phase: $phase"
            exit 1
            ;;
    esac
done

echo ""
log_header "Setup Complete!"
echo ""
echo "Next steps:"
echo " 1. Configure fairness settings: Settings → Technical → Fairness → Global Configuration"
echo " 2. Configure GPU marketplace settings: Settings → GPU → Marketplace"
echo " 3. Set up WireGuard peers for secure communication"
echo " 4. Access your platform at https://your-domain"
if [[ "$ENVIRONMENT" == "development" ]]; then
    echo " 5. Development mode: SSH password auth is still enabled on port 22."
else
    echo " 5. Production mode: SSH is key-only on port 22. Use port 2222 for password auth."
fi
echo ""
echo "To activate the Python virtual environment manually:"
echo "  source $VENV_DIR/bin/activate"