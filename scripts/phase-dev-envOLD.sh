#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 1: Development Environment
# =============================================================================
# Creates the full development environment:
#   1. Runs create-nettrades-projects.sh (folder structure + clone repos)
#   2. Installs all Python dependencies
#   3. Prints instructions for starting Odoo
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Step 1: Create project structure and clone repositories. Only do this when changing the odoo version or the version of other thirdparty apps etc. ==="
# bash "$SCRIPT_DIR/create-nettrades-projects.sh"

echo ""
echo "=== Step 2: Install Python dependencies ==="

echo "=== Installing development tools ==="
#pip install -r "$PLATFORM_DIR/requirements-dev.txt"  #   In linux or if you are not using a virtual environment is built for Windows

# Convert the Linux path to a Windows path for python.exe
WIN_REQUIREMENTS_DEV_PATH=$(wslpath -w "$PLATFORM_DIR/requirements-dev.txt")

# Run the command using the converted Windows path
"$PLATFORM_DIR/venv/Scripts/python.exe" -m pip install -r "$WIN_REQUIREMENTS_DEV_PATH"

echo "=== Installing core Odoo dependencies (third-party Odoo) ==="
#pip install -r "$PLATFORM_DIR/third-party/odoo/requirements.txt"  #   In linux or if you are not using a virtual environment is built for Windows

# Convert the Linux path to a Windows path for python.exe
WIN_ODOO_REQUIREMENTS_PATH=$(wslpath -w "$PLATFORM_DIR/third-party/odoo/requirements.txt")

# Run the command using the converted Windows path
"$PLATFORM_DIR/venv/Scripts/python.exe" -m pip install -r "$WIN_ODOO_REQUIREMENTS_PATH"

echo "=== Installing community LLM module dependencies ==="
#pip install -r "$PLATFORM_DIR/third-party/odoo_llm/requirements.txt"   #   In linux or if you are not using a virtual environment is built for Windows

# Convert the Linux path to a Windows path for python.exe
WIN_ODOO_LLM_REQUIREMENTS_PATH=$(wslpath -w "$PLATFORM_DIR/third-party/odoo_llm/requirements.txt")

# Run the command using the converted Windows path
"$PLATFORM_DIR/venv/Scripts/python.exe" -m pip install -r "$WIN_ODOO_LLM_REQUIREMENTS_PATH"

echo "=== Installing NETTRADES orchestrator dependencies (LangGraph, FastAPI, etc.) ==="
#pip install -r "$PLATFORM_DIR/src/core/requirements.txt"   #   In linux or if you are not using a virtual environment is built for Windows

# Convert the Linux path to a Windows path for python.exe
WIN_CORE_REQUIREMENTS_PATH=$(wslpath -w "$PLATFORM_DIR/src/core/requirements.txt")

# Run the command using the converted Windows path
"$PLATFORM_DIR/venv/Scripts/python.exe" -m pip install -r "$WIN_CORE_REQUIREMENTS_PATH"

echo "===  FastAPI, LiteLLM and VLLM are built on top of Starlette. Starlette v1.0.0 has a vulnerability, tracked as CVE-2026-48710 and under the name BadHost, that is trivial to exploit and works against most systems that aren’t behind a properly configured firewall ==="
echo "===  Upgrade to Starlette v1.0.1  ==="

# FastAPI, LiteLLM and VLLM are built on top of Starlette. Starlette v1.0.0 has a vulnerability, tracked as CVE-2026-48710 and under the name BadHost, that is trivial to exploit and works against most systems that aren’t behind a properly configured firewall
# Upgrade to Starlette v1.0.1 

#   pip install --upgrade "starlette>=1.0.1"
"$PLATFORM_DIR/venv/Scripts/python.exe" -m pip install --upgrade "starlette>=1.0.1"

echo ""
echo "============================================================="
echo " Development environment ready!"
echo "============================================================="
echo ""
echo "Start Odoo 19 CE:"
echo "  python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \\"
echo "      --addons-path=third-party/odoo/addons,odoo-modules"
echo ""
echo "Then open https://localhost:8069 and install the modules."