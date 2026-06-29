#!/bin/bash
# =============================================================================
# FILE: scripts/nettrades-setup.sh
# =============================================================================
# PURPOSE:
#   NETTRADES platform unified setup orchestrator.
#   Single entry point for installation, deployment, GPU, Kubernetes, modules.
#   Includes comprehensive dependency checks and OS-specific setup.
#
# USAGE:
#   ./nettrades-setup.sh <PROFILE> [options]   (CLI mode)
#   ./nettrades-setup.sh                       (Interactive wizard)
#   ./nettrades-setup.sh --help                Show help.
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
# Show help
# -----------------------------------------------------------------------------
show_help() {
    cat << EOF
${GREEN}NETTRADES.AI – Unified Setup Orchestrator${NC}

${YELLOW}USAGE:${NC}
    ./nettrades-setup.sh <PROFILE> [options]   (CLI mode)
    ./nettrades-setup.sh                       (Interactive wizard)
    ./nettrades-setup.sh --help                Show this help.

${YELLOW}PROFILES (CLI):${NC}
    dev         : Phase 1 (development environment)
    deploy      : Phase 0 + Phase 1 + Phase 2 (single-VM deployment without GPU)
    gpu         : Phase 0 + Phase 1 + Phase 2 + Phase 3 (single-VM deployment with GPU)
    k8s         : Phase 0 + Phase 1 + Phase 4 (Kubernetes scaling)
    monitoring  : Phase 6 (Prometheus & Grafana setup)
    modules     : Phase 5 (install/upgrade Odoo modules only)
    all         : Phase 0 + Phase 1 + Phase 2 + Phase 5 (full deployment with modules)

${YELLOW}OPTIONS (CLI):${NC}
    --force           Re-run phases even if already completed.
    --upgrade         Upgrade existing modules instead of fresh install.
    --skip-installed  Skip already installed Odoo modules.
    --auto            Run in non-interactive mode (use defaults, no prompts).
    --phases=LIST     Comma-separated list of phases (overrides profile).

${YELLOW}EXAMPLES:${NC}
    ./nettrades-setup.sh                        # Interactive wizard
    ./nettrades-setup.sh deploy --auto          # Automated deploy
    ./nettrades-setup.sh gpu --force --upgrade  # Re-deploy with GPU and upgrade modules
EOF
}

# =============================================================================
# INTERACTIVE WIZARD (plain Bash)
# =============================================================================

run_interactive() {
    log_header "NETTRADES Setup Wizard (Interactive Mode)"

    # --- Profile selection ---
    echo ""
    echo "Available profiles:"
    echo "  1) dev         - Development environment (Phase 1 only)"
    echo "  2) deploy      - Single-VM Docker deployment (no GPU)"
    echo "  3) gpu         - Single-VM with GPU (vLLM, GPUStack)"
    echo "  4) k8s         - Kubernetes scaling (Talos, Argo CD)"
    echo "  5) monitoring  - Prometheus & Grafana monitoring stack"
    echo "  6) modules     - Install/upgrade Odoo modules only"
    echo "  7) all         - Full deployment (Phases 0,1,2,5)"
    echo ""
    read -rp "Enter the number of your choice (1-7): " profile_choice

    case "$profile_choice" in
        1) PROFILE="dev" ;;
        2) PROFILE="deploy" ;;
        3) PROFILE="gpu" ;;
        4) PROFILE="k8s" ;;
        5) PROFILE="monitoring" ;;
        6) PROFILE="modules" ;;
        7) PROFILE="all" ;;
        *) log_error "Invalid choice"; exit 1 ;;
    esac
    log_info "Selected profile: $PROFILE"

    # --- Options ---
    echo ""
    read -rp "Force re-run completed phases? (y/N): " force_yn
    [[ "$force_yn" =~ ^[Yy]$ ]] && FORCE=true || FORCE=false

    read -rp "Upgrade modules instead of fresh install? (y/N): " upgrade_yn
    [[ "$upgrade_yn" =~ ^[Yy]$ ]] && UPGRADE=true || UPGRADE=false

    read -rp "Auto mode (non-interactive, no prompts)? (y/N): " auto_yn
    [[ "$auto_yn" =~ ^[Yy]$ ]] && AUTO=true || AUTO=false

    # --- Determine phases ---
    case "$PROFILE" in
        dev) PHASES=(1) ;;
        deploy) PHASES=(0 1 2) ;;
        gpu) PHASES=(0 1 2 3) ;;
        k8s) PHASES=(0 1 4) ;;
        monitoring) PHASES=(6) ;;
        modules) PHASES=(5) ;;
        all) PHASES=(0 1 2 5) ;;
    esac

    # --- Confirm ---
    echo ""
    echo -e "${YELLOW}Summary:${NC}"
    echo "  Profile: $PROFILE"
    echo "  Force: $FORCE"
    echo "  Upgrade: $UPGRADE"
    echo "  Auto: $AUTO"
    echo "  Phases: ${PHASES[*]}"
    echo ""
    read -rp "Proceed with these settings? (y/N): " confirm
    [[ ! "$confirm" =~ ^[Yy]$ ]] && { log_info "Aborted."; exit 0; }

    export FORCE UPGRADE AUTO
}

# =============================================================================
# PHASE 1: Development Environment (Integrated)
# =============================================================================

setup_dev_environment() {
    local os
    os=$(detect_os)

    log_step "Setting up development environment..."

    # Install Python dependencies if requirements-dev.txt exists
    if [[ -f "$PROJECT_ROOT/requirements-dev.txt" ]]; then
        log_step "Installing Python development dependencies..."
        pip3 install -r "$PROJECT_ROOT/requirements-dev.txt" 2>/dev/null || {
            log_warning "Failed to install Python dependencies automatically. Please install manually."
        }
    else
        log_warning "requirements-dev.txt not found – skipping Python dependencies."
    fi

    # Create .env from template if not exists
    if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
        if [[ -f "$PROJECT_ROOT/deploy/docker/.env.example" ]]; then
            log_step "Creating .env from template..."
            cp "$PROJECT_ROOT/deploy/docker/.env.example" "$PROJECT_ROOT/.env"
            chmod 600 "$PROJECT_ROOT/.env"
            log_warning "Created .env from .env.example. Please review and set secrets."
        else
            log_warning ".env.example not found – skipping .env creation."
        fi
    else
        log_success ".env already exists."
    fi

    # Install Odoo module dependencies (if appropriate scripts exist)
    if [[ "$os" == "windows" ]]; then
        if [[ -f "$PROJECT_ROOT/scripts/install-odoo-modules.ps1" ]]; then
            log_step "Installing Odoo module dependencies (Windows)..."
            powershell -ExecutionPolicy Bypass -File "$PROJECT_ROOT/scripts/install-odoo-modules.ps1" -SkipInstalled:"$SKIP_INSTALLED" -ForceReinstall:"$FORCE" 2>/dev/null || {
                log_warning "Odoo module dependency installation failed."
            }
        else
            log_warning "install-odoo-modules.ps1 not found – skipping Odoo dependencies."
        fi
    else
        if [[ -f "$PROJECT_ROOT/scripts/install-modules.sh" ]]; then
            log_step "Installing Odoo module dependencies (Linux/macOS)..."
            bash "$PROJECT_ROOT/scripts/install-modules.sh" --deps-only 2>/dev/null || {
                log_warning "Odoo module dependency installation failed."
            }
        else
            log_warning "install-modules.sh not found – skipping Odoo dependencies."
        fi
    fi

    mark_phase_complete 1
}

# =============================================================================
# MAIN SCRIPT
# =============================================================================

# Defaults
PROFILE=""
FORCE=false
UPGRADE=false
SKIP_INSTALLED=true
AUTO=false
PHASES_LIST=""
INTERACTIVE=false

# If no arguments, auto-launch interactive
if [ $# -eq 0 ]; then
    INTERACTIVE=true
fi

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --interactive) INTERACTIVE=true; shift ;;
        --force) FORCE=true; shift ;;
        --upgrade) UPGRADE=true; shift ;;
        --skip-installed) SKIP_INSTALLED=true; shift ;;
        --auto) AUTO=true; shift ;;
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

# -----------------------------------------------------------------------------
# Environment preparation (OS/WSL check)
# -----------------------------------------------------------------------------
prepare_environment() {
    local os
    os=$(detect_os)
    log_info "Detected OS: $os"

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
        for cmd in curl wget git; do
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

    # Python 3.10+
    if ! command -v python3 &>/dev/null; then
        log_error "Python3 not found. Please install Python 3.10 or higher."
        exit 1
    fi
    local py_version
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ "$(printf '%s\n' "3.10" "$py_version" | sort -V | head -n1)" != "3.10" ]]; then
        log_error "Python version $py_version detected. Need 3.10+."
        exit 1
    fi
    log_success "Python $py_version detected."

    # pip
    if ! command -v pip3 &>/dev/null; then
        log_warning "pip3 not found. Installing..."
        python3 -m ensurepip --upgrade 2>/dev/null || {
            log_error "Failed to install pip. Please install manually."
            exit 1
        }
    fi
}

# -----------------------------------------------------------------------------
# Main execution
# -----------------------------------------------------------------------------

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
        gpu) PHASES=(0 1 2 3) ;;
        k8s) PHASES=(0 1 4) ;;
        monitoring) PHASES=(6) ;;
        modules) PHASES=(5) ;;
        all) PHASES=(0 1 2 5) ;;
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

# Export variables for phase scripts
export PROJECT_ROOT
export FORCE
export UPGRADE
export SKIP_INSTALLED
export AUTO

log_header "NETTRADES.AI – Unified Setup"
log_info "Profile: ${PROFILE:-custom}"
log_info "Phases: ${PHASES[*]}"
log_info "Force: $FORCE"
log_info "Upgrade: $UPGRADE"
log_info "Auto: $AUTO"
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
            if phase_completed 1; then
                log_warning "Phase 1 already completed. Use --force to re-run."
            else
                setup_dev_environment
                mark_phase_complete 1
            fi
            ;;
        2)
            log_header "Phase 2 — Single-VM Deployment"
            bash "$SCRIPT_DIR/phase-deploy.sh"
            ;;
        3)
            log_header "Phase 3 — GPU Setup"
            bash "$SCRIPT_DIR/phase-add-gpu.sh"
            ;;
        4)
            log_header "Phase 4 — Kubernetes Scaling"
            bash "$SCRIPT_DIR/phase-k8s.sh"
            ;;
        5)
            log_header "Phase 5 — Module Installation"
            bash "$SCRIPT_DIR/phase-modules.sh"
            ;;
        6)
            log_header "Phase 6 — Monitoring Setup"
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
if [[ "$(detect_os)" == "windows" ]]; then
    echo "💡 You are running in WSL2. Remember to access services via localhost or use port forwarding."
fi