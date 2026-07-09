#!/bin/bash
#               THIS SCRIPT IS NO LONGER USED
# PHASE ADD GPU WAS REMOVED BECAUSE LLAMA.CPP AND VLLM WERE REPLACED WITH GPUSTACK
# =============================================================================
# NETTRADES.AI � Unified Setup Orchestrator
# =============================================================================
# This is the ONLY script you need to run.  It detects your hardware,
# asks which phase you want, and calls the appropriate scripts in order.
#
# Phases:
#   1 � dev-env    : create folder structure, clone repos, install dependencies
#   2 � deploy     : deploy single-VM production stack (no GPU required)
#   3 � add-gpu    : add a GPU to an existing single-VM deployment
#   4 � scale      : upgrade from single-VM to Kubernetes (Talos + K8s)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================="
echo " NETTRADES.AI � Setup Orchestrator"
echo "============================================================="
echo ""
echo "Which phase would you like to run?"
echo "  1 � Development environment (clone repos, install dependencies)"
echo "  2 � Single-VM deployment (production, no GPU required)"
echo "  3 � Add a GPU to an existing single-VM deployment"
echo "  4 � Scale to Kubernetes (Talos + K8s, requires Proxmox)"
echo ""
read -rp "Enter 1, 2, 3, or 4: " PHASE

case "$PHASE" in
    1)
        # Detect WSL
        if grep -qi "microsoft" /proc/version; then
            echo "Detected Environment: Windows (WSL)"
            
            # Use powershell.exe to call the Windows venv and run the script
            # Note: We use -Command to bridge the environment gap
            powershell.exe -ExecutionPolicy Bypass -Command "
                cd '$PLATFORM_DIR';
                .\\venv\\Scripts\\activate;
                bash '$SCRIPT_DIR/phase-dev-env.sh'
            "
        else
            echo "Detected Environment: Native Linux"
            bash "$SCRIPT_DIR/phase-dev-env.sh"
        fi
        ;;
    2) bash "$SCRIPT_DIR/phase-deploy.sh" ;;
    3) bash "$SCRIPT_DIR/phase-add-gpu.sh" ;;
    4) bash "$SCRIPT_DIR/phase-scale.sh" ;;    
    *) echo "Invalid choice. Please enter 1, 2, 3, or 4." ; exit 1 ;;
esac

echo ""
echo "============================================================="
echo " Phase $PHASE complete."
echo "============================================================="