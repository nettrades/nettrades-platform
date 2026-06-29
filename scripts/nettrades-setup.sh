#!/bin/bash
# =============================================================================
# FILE: scripts/nettrades-setup.sh
# =============================================================================
# PURPOSE:
#   NETTRADES platform setup orchestrator.
#
#   Unlike a monolithic "do everything" script, this tool provides composable
#   profiles and options so you can set up exactly the environment you need.
#
#   PROFILES (pre‑defined combinations):
#     dev    : Phase 1 only (development environment)
#     deploy : Phase 1 + Phase 2 (single‑VM deployment without GPU)
#     gpu    : Phase 1 + Phase 2 + Phase 3 (single‑VM deployment with GPU)
#     k8s    : Phase 1 + Phase 4 (development environment + Kubernetes scaling)
#
#   PHASES (individual steps):
#     Phase 1 – Development environment (repos, dependencies, folder structure)
#     Phase 2 – Deployment (secrets, images, Docker Compose, database)
#     Phase 3 – GPU setup (NVIDIA, GPUStack, vLLM)
#     Phase 4 – Kubernetes scaling (Talos, Argo, manifests)
#
# USAGE:
#   ./nettrades-setup.sh <profile> [options]
#
# OPTIONS:
#   --force            Re‑run phases even if already completed.
#   --upgrade          Upgrade modules instead of fresh install.
#   --skip-installed   Skip already installed Odoo modules.
#   --phases=<list>    Comma‑separated list of phases (overrides profile).
#   --help             Show this help message.
#
# EXAMPLES:
#   ./nettrades-setup.sh dev                    # Set up development environment
#   ./nettrades-setup.sh deploy                 # Deploy without GPU
#   ./nettrades-setup.sh gpu                   # Deploy with GPU
#   ./nettrades-setup.sh k8s                   # Set up for Kubernetes scaling
#   ./nettrades-setup.sh --phases=1,2,3        # Custom combination
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Colours
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
${GREEN}NETTRADES.AI – Setup Orchestrator${NC}

${YELLOW}USAGE:${NC}
  ./nettrades-setup.sh <profile> [options]

${YELLOW}PROFILES:${NC}
  dev      : Phase 1 (development environment)
  deploy   : Phase 1 + Phase 2 (single‑VM deployment without GPU)
  gpu      : Phase 1 + Phase 2 + Phase 3 (single‑VM deployment with GPU)
  k8s      : Phase 1 + Phase 4 (development environment + Kubernetes scaling)

${YELLOW}OPTIONS:${NC}
  --force            Re‑run phases even if already completed.
  --upgrade          Upgrade modules instead of fresh install.
  --skip-installed   Skip already installed Odoo modules.
  --phases=<list>    Comma‑separated list of phases (overrides profile).
  --help             Show this help message.

${YELLOW}EXAMPLES:${NC}
  ./nettrades-setup.sh dev
  ./nettrades-setup.sh deploy --force
  ./nettrades-setup.sh gpu --upgrade
  ./nettrades-setup.sh k8s
  ./nettrades-setup.sh --phases=1,2,3
EOF
}

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
PROFILE="${1:-}"
FORCE=false
UPGRADE=false
SKIP_INSTALLED=true
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
# Determine which phases to run
# -----------------------------------------------------------------------------
if [[ -n "$PHASES_LIST" ]]; then
    # User specified phases directly
    IFS=',' read -ra PHASES <<< "$PHASES_LIST"
elif [[ -n "$PROFILE" ]]; then
    # Map profile to phases
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
        *)
            echo -e "${RED}Unknown profile: $PROFILE${NC}"
            show_help
            exit 1
            ;;
    esac
else
    echo -e "${RED}No profile or --phases specified.${NC}"
    show_help
    exit 1
fi

# -----------------------------------------------------------------------------
# Get script directory and project root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
phase_completed() {
    local phase=$1
    local marker="$PROJECT_ROOT/.phase-$phase-complete"
    [[ -f "$marker" ]] && [[ "$FORCE" != true ]]
}

mark_phase_complete() {
    local phase=$1
    local marker="$PROJECT_ROOT/.phase-$phase-complete"
    echo "$(date -Iseconds)" > "$marker"
    echo -e "${GREEN}✓ Phase $phase completed${NC}"
}

run_phase1() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 1 — Development Environment${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 1; then
        echo -e "${YELLOW}Phase 1 already completed. Use --force to re-run.${NC}"
        return 0
    fi

    bash "$SCRIPT_DIR/create-nettrades-projects.sh"
    if [[ -f "$PROJECT_ROOT/requirements.txt" ]]; then
        pip install -r "$PROJECT_ROOT/requirements.txt"
    fi
    if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env" 2>/dev/null || true
        echo -e "${YELLOW}Created .env from .env.example. Please edit with your secrets.${NC}"
    fi
    mark_phase_complete 1
}

run_phase2() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 2 — Deployment${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 2; then
        echo -e "${YELLOW}Phase 2 already completed. Use --force to re-run.${NC}"
        return 0
    fi

    # Phase 1 is a prerequisite
    if ! phase_completed 1; then
        echo -e "${YELLOW}Phase 1 not completed. Running Phase 1 first...${NC}"
        run_phase1
    fi

    cd "$PROJECT_ROOT/deploy/docker"
    if [[ "$FORCE" == true ]]; then
        sudo ./install-nettrades.sh --auto
    else
        sudo ./install-nettrades.sh
    fi
    cd "$PROJECT_ROOT"

    # Install Odoo modules
    if [[ -f "$SCRIPT_DIR/install-modules.sh" ]]; then
        if [[ "$UPGRADE" == true ]]; then
            bash "$SCRIPT_DIR/install-modules.sh" --upgrade
        else
            bash "$SCRIPT_DIR/install-modules.sh"
        fi
    fi

    mark_phase_complete 2
}

run_phase3() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 3 — GPU Setup${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 3; then
        echo -e "${YELLOW}Phase 3 already completed. Use --force to re-run.${NC}"
        return 0
    fi

    if ! command -v nvidia-smi &>/dev/null; then
        echo -e "${RED}NVIDIA GPU not detected or drivers not installed.${NC}"
        echo "Please install NVIDIA drivers and the nvidia-container-toolkit."
        echo "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
        exit 1
    fi

    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"

    if [[ -f "$SCRIPT_DIR/gpustackinstall.ps1" ]]; then
        echo -e "${YELLOW}Installing GPUStack...${NC}"
        if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
            powershell -ExecutionPolicy Bypass -File "$SCRIPT_DIR/gpustackinstall.ps1"
        else
            echo -e "${YELLOW}GPUStack installation on Linux requires manual setup.${NC}"
            echo "Please run the GPUStack installer manually."
        fi
    fi

    mark_phase_complete 3
}

run_phase4() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Phase 4 — Kubernetes Scaling${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if phase_completed 4; then
        echo -e "${YELLOW}Phase 4 already completed. Use --force to re-run.${NC}"
        return 0
    fi

    local missing_tools=()
    for tool in kubectl helm talosctl tofu; do
        if ! command -v $tool &>/dev/null; then
            missing_tools+=($tool)
        fi
    done

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        echo -e "${RED}Missing required tools: ${missing_tools[*]}${NC}"
        echo "Please install the missing tools and try again."
        echo "  kubectl:    https://kubernetes.io/docs/tasks/tools/"
        echo "  helm:       https://helm.sh/docs/intro/install/"
        echo "  talosctl:   https://www.talos.dev/docs/v1.7/introduction/getting-started/"
        echo "  tofu:       https://opentofu.org/docs/intro/install/"
        exit 1
    fi

    echo -e "${GREEN}✓ All required Kubernetes tools are installed${NC}"
    echo -e "${YELLOW}Kubernetes scaling is a separate deployment path.${NC}"
    echo "Please run the Kubernetes deployment manually using the scripts in deploy/kubernetes/"

    mark_phase_complete 4
}

# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------
for phase in "${PHASES[@]}"; do
    case $phase in
        1) run_phase1 ;;
        2) run_phase2 ;;
        3) run_phase3 ;;
        4) run_phase4 ;;
        *)
            echo -e "${RED}Invalid phase: $phase${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Done!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"