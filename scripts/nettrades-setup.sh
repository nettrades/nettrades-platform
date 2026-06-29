#!/bin/bash
# =============================================================================
# FILE: scripts/nettrades-setup.sh
# =============================================================================
# PURPOSE:
#   NETTRADES platform unified setup orchestrator.
#   This is the SINGLE ENTRY POINT for all installation and deployment operations.
#
#   It auto-detects your OS, hardware, and existing installation, then runs the
#   appropriate phases in the correct order. It is idempotent and safe to re-run.
#
#   PROFILES (pre-defined combinations):
#     dev      : Phase 1 only (development environment)
#     deploy   : Phase 1 + Phase 2 (single-VM deployment without GPU)
#     gpu      : Phase 1 + Phase 2 + Phase 3 (single-VM deployment with GPU)
#     k8s      : Phase 1 + Phase 4 (development environment + Kubernetes scaling)
#     modules  : Phase 5 only (install/upgrade Odoo modules)
#     all      : Run all phases (dev + deploy + modules)
#
#   PHASES (individual steps):
#     Phase 1 – Development environment (dependencies, folder structure)
#     Phase 2 – Deployment (secrets, images, Docker Compose, database)
#     Phase 3 – GPU setup (NVIDIA, GPUStack, vLLM)
#     Phase 4 – Kubernetes scaling (Talos, Argo, manifests)
#     Phase 5 – Module installation (Odoo modules, dependencies)
#
#   OPTIONS:
#     --force            Re-run phases even if already completed.
#     --upgrade          Upgrade existing modules instead of fresh install.
#     --skip-installed   Skip already installed Odoo modules.
#     --auto             Run in non-interactive mode (use defaults).
#     --phases=<list>    Comma-separated list of phases (overrides profile).
#     --help             Show this help message.
#
#   EXAMPLES:
#     ./nettrades-setup.sh dev                     # Set up development environment
#     ./nettrades-setup.sh deploy                  # Deploy without GPU
#     ./nettrades-setup.sh gpu --auto              # Deploy with GPU (non-interactive)
#     ./nettrades-setup.sh modules --upgrade       # Upgrade Odoo modules only
#     ./nettrades-setup.sh all --force             # Re-run everything from scratch
#     ./nettrades-setup.sh --phases=1,2,5          # Custom combination
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Colours for output
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# Help message
# -----------------------------------------------------------------------------
show_help() {
    cat << EOF
${GREEN}NETTRADES.AI – Unified Setup Orchestrator${NC}

${YELLOW}USAGE:${NC}
  ./nettrades-setup.sh <profile> [options]

${YELLOW}PROFILES:${NC}
  dev      : Phase 1 (development environment)
  deploy   : Phase 1 + Phase 2 (single-VM deployment without GPU)
  gpu      : Phase 1 + Phase 2 + Phase 3 (single-VM deployment with GPU)
  k8s      : Phase 1 + Phase 4 (development environment + Kubernetes scaling)
  modules  : Phase 5 (install/upgrade Odoo modules only)
  all      : Phase 1 + Phase 2 + Phase 5 (full deployment with modules)

${YELLOW}OPTIONS:${NC}
  --force            Re-run phases even if already completed.
  --upgrade          Upgrade existing modules instead of fresh install.
  --skip-installed   Skip already installed Odoo modules.
  --auto             Run in non-interactive mode (use defaults, no prompts).
  --phases=<list>    Comma-separated list of phases (overrides profile).
  --help             Show this help message.

${YELLOW}EXAMPLES:${NC}
  ./nettrades-setup.sh dev                     # Set up development environment
  ./nettrades-setup.sh deploy --auto           # Deploy without GPU (non-interactive)
  ./nettrades-setup.sh gpu --upgrade           # Deploy with GPU and upgrade modules
  ./nettrades-setup.sh modules --force         # Reinstall all Odoo modules
  ./nettrades-setup.sh all --force             # Re-run everything from scratch
  ./nettrades-setup.sh --phases=1,2,5          # Custom combination
EOF
}

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
PROFILE="${1:-}"
FORCE=false
UPGRADE=false
SKIP_INSTALLED=true
AUTO=false
PHASES_LIST=""

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
shift 2>/dev/null || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE=true
            shift
            ;;
        --upgrade)
            UPGRADE=true
            shift
            ;;
        --skip-installed)
            SKIP_INSTALLED=true
            shift
            ;;
        --auto)
            AUTO=true
            shift
            ;;
        --phases=*)
            PHASES_LIST="${1#--phases=}"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Get script directory and project root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

phase_completed() {
    local phase=$1
    local marker="$PROJECT_ROOT/.phase-$phase-complete"
    [[ -f "$marker" ]] && [[ "$FORCE" != true ]]
}

mark_phase_complete() {
    local phase=$1
    local marker="$PROJECT_ROOT/.phase-$phase-complete"
    echo "$(date -Iseconds)" > "$marker"
    log_success "Phase $phase completed"
}

# -----------------------------------------------------------------------------
# Detect OS and hardware
# -----------------------------------------------------------------------------
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

detect_gpu() {
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Phase 1: Development Environment
# -----------------------------------------------------------------------------
run_phase1() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 1 — Development Environment${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 1; then
        log_warning "Phase 1 already completed. Use --force to re-run."
        return 0
    fi

    OS=$(detect_os)
    log_info "Detected OS: $OS"

    # Install Python dependencies
    log_info "Installing Python dependencies..."
    if [[ -f "$PROJECT_ROOT/requirements-dev.txt" ]]; then
        pip install -r "$PROJECT_ROOT/requirements-dev.txt" 2>/dev/null || \
        pip3 install -r "$PROJECT_ROOT/requirements-dev.txt" 2>/dev/null || \
        log_warning "Could not install Python dependencies automatically. Please install manually."
    fi

    # Create .env from template if it doesn't exist
    if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
        log_info "Creating .env file from template..."
        if [[ -f "$PROJECT_ROOT/deploy/docker/.env.example" ]]; then
            cp "$PROJECT_ROOT/deploy/docker/.env.example" "$PROJECT_ROOT/.env"
            log_warning "Created .env from .env.example. Please edit with your secrets."
        fi
    fi

    # Install Odoo module dependencies (if not already done)
    if [[ -f "$PROJECT_ROOT/scripts/install-odoo-modules.ps1" ]] && [[ "$OS" == "windows" ]]; then
        log_info "Installing Odoo module dependencies (Windows)..."
        powershell -ExecutionPolicy Bypass -File "$PROJECT_ROOT/scripts/install-odoo-modules.ps1" -SkipInstalled:$SKIP_INSTALLED -ForceReinstall:$FORCE
    elif [[ -f "$PROJECT_ROOT/scripts/install-modules.sh" ]] && [[ "$OS" != "windows" ]]; then
        log_info "Installing Odoo module dependencies (Linux/macOS)..."
        bash "$PROJECT_ROOT/scripts/install-modules.sh"
    fi

    mark_phase_complete 1
}

# -----------------------------------------------------------------------------
# Phase 2: Deployment
# -----------------------------------------------------------------------------
run_phase2() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 2 — Deployment${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 2; then
        log_warning "Phase 2 already completed. Use --force to re-run."
        return 0
    fi

    # Phase 1 is a prerequisite
    if ! phase_completed 1; then
        log_info "Phase 1 not completed. Running Phase 1 first..."
        run_phase1
    fi

    cd "$PROJECT_ROOT/deploy/docker"

    # Generate .env if it doesn't exist or if --force
    if [[ ! -f ".env" ]] || [[ "$FORCE" == true ]]; then
        log_info "Generating .env file with secure secrets..."
        # Use the updated generator that uses PROXY_API_KEY
        bash .env.generator.sh > .env
        chmod 600 .env
        log_success ".env file generated"
    fi

    # Build and start the stack
    log_info "Building and starting Docker Compose stack..."
    docker compose up -d --build

    # Wait for PostgreSQL to be ready
    log_info "Waiting for PostgreSQL to be ready..."
    sleep 10
    docker exec -i postgres psql -U odoo odoo < init-db.sql 2>/dev/null || true

    cd "$PROJECT_ROOT"

    mark_phase_complete 2
}

# -----------------------------------------------------------------------------
# Phase 3: GPU Setup
# -----------------------------------------------------------------------------
run_phase3() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 3 — GPU Setup${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 3; then
        log_warning "Phase 3 already completed. Use --force to re-run."
        return 0
    fi

    # Phase 2 is a prerequisite
    if ! phase_completed 2; then
        log_info "Phase 2 not completed. Running Phase 2 first..."
        run_phase2
    fi

    if ! detect_gpu; then
        log_error "NVIDIA GPU not detected or drivers not installed."
        log_info "Please install NVIDIA drivers and the nvidia-container-toolkit."
        log_info "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
        exit 1
    fi

    log_success "NVIDIA GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"

    # Run the GPU migration script
    if [[ -f "$PROJECT_ROOT/deploy/docker/migrate-to-gpu.sh" ]]; then
        log_info "Running GPU migration..."
        bash "$PROJECT_ROOT/deploy/docker/migrate-to-gpu.sh"
    else
        log_warning "migrate-to-gpu.sh not found. GPU migration skipped."
    fi

    mark_phase_complete 3
}

# -----------------------------------------------------------------------------
# Phase 4: Kubernetes Scaling
# -----------------------------------------------------------------------------
run_phase4() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 4 — Kubernetes Scaling${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 4; then
        log_warning "Phase 4 already completed. Use --force to re-run."
        return 0
    fi

    # Check for required tools
    local missing_tools=()
    for tool in kubectl helm talosctl; do
        if ! command -v $tool &>/dev/null; then
            missing_tools+=($tool)
        fi
    done

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_info "Please install:"
        log_info "  kubectl:    https://kubernetes.io/docs/tasks/tools/"
        log_info "  helm:       https://helm.sh/docs/intro/install/"
        log_info "  talosctl:   https://www.talos.dev/docs/v1.7/introduction/getting-started/"
        exit 1
    fi

    log_success "All required Kubernetes tools are installed"

    # Run the Kubernetes deployment script
    if [[ -f "$PROJECT_ROOT/deploy/kubernetes/deploy-k8s-base.sh" ]]; then
        log_info "Deploying Kubernetes base..."
        cd "$PROJECT_ROOT"
        bash "$PROJECT_ROOT/deploy/kubernetes/deploy-k8s-base.sh"
    else
        log_warning "deploy-k8s-base.sh not found. Kubernetes deployment skipped."
    fi

    mark_phase_complete 4
}

# -----------------------------------------------------------------------------
# Phase 5: Module Installation
# -----------------------------------------------------------------------------
run_phase5() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 5 — Module Installation${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 5 && [[ "$FORCE" != true ]]; then
        log_warning "Phase 5 already completed. Use --force to re-run."
        return 0
    fi

    # Phase 2 is a prerequisite (Odoo must be running)
    if ! phase_completed 2; then
        log_info "Phase 2 not completed. Running Phase 2 first..."
        run_phase2
    fi

    OS=$(detect_os)
    log_info "Detected OS: $OS"

    # Install Odoo modules with the appropriate script
    if [[ "$OS" == "windows" ]]; then
        if [[ -f "$PROJECT_ROOT/scripts/install-odoo-modules.ps1" ]]; then
            log_info "Installing Odoo modules (Windows)..."
            local ps_args=""
            [[ "$FORCE" == true ]] && ps_args="$ps_args -ForceReinstall"
            [[ "$UPGRADE" == true ]] && ps_args="$ps_args -ForceReinstall"
            [[ "$SKIP_INSTALLED" == true ]] && ps_args="$ps_args -SkipInstalled"
            powershell -ExecutionPolicy Bypass -File "$PROJECT_ROOT/scripts/install-odoo-modules.ps1" $ps_args
        else
            log_error "install-odoo-modules.ps1 not found"
            exit 1
        fi
    else
        if [[ -f "$PROJECT_ROOT/scripts/install-modules.sh" ]]; then
            log_info "Installing Odoo modules (Linux/macOS)..."
            local sh_args=""
            [[ "$FORCE" == true ]] && sh_args="$sh_args --force"
            [[ "$UPGRADE" == true ]] && sh_args="$sh_args --upgrade"
            bash "$PROJECT_ROOT/scripts/install-modules.sh" $sh_args
        else
            log_error "install-modules.sh not found"
            exit 1
        fi
    fi

    mark_phase_complete 5
}

# -----------------------------------------------------------------------------
# Determine which phases to run
# -----------------------------------------------------------------------------
if [[ -n "$PHASES_LIST" ]]; then
    IFS=',' read -ra PHASES <<< "$PHASES_LIST"
elif [[ -n "$PROFILE" ]]; then
    case "$PROFILE" in
        dev)
            PHASES=(1)
            ;;
        deploy)
            PHASES=(1 2)
            ;;
        gpu)
            PHASES=(1 2 3)
            ;;
        k8s)
            PHASES=(1 4)
            ;;
        modules)
            PHASES=(5)
            ;;
        all)
            PHASES=(1 2 5)
            ;;
        *)
            log_error "Unknown profile: $PROFILE"
            show_help
            exit 1
            ;;
    esac
else
    log_error "No profile or --phases specified."
    show_help
    exit 1
fi

# -----------------------------------------------------------------------------
# Main execution
# -----------------------------------------------------------------------------
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  NETTRADES.AI – Unified Setup${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
log_info "Profile: $PROFILE"
log_info "Phases: ${PHASES[*]}"
log_info "Force: $FORCE"
log_info "Upgrade: $UPGRADE"
log_info "Auto: $AUTO"
echo ""

for phase in "${PHASES[@]}"; do
    case $phase in
        1) run_phase1 ;;
        2) run_phase2 ;;
        3) run_phase3 ;;
        4) run_phase4 ;;
        5) run_phase5 ;;
        *)
            log_error "Invalid phase: $phase"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Next steps:"
echo "  1. Configure fairness settings: Settings → Technical → Fairness → Global Configuration"
echo "  2. Configure GPU registration tokens: GPU → Registration Tokens"
echo "  3. Set up bridge routing: Settings → Technical → Bridge → Global Configuration"
echo "  4. Check the self-improving loop: Settings → Technical → Self‑Improving → Dashboard"