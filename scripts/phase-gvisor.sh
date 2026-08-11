#!/bin/bash
# =============================================================================
# FILE: scripts/phase-gvisor.sh
# =============================================================================
# PURPOSE:
#   Phase: gVisor Installation and Configuration.
#   Installs and configures gVisor for container isolation.
#
#   gVisor is a user-space kernel that provides strong isolation for containers,
#   reducing the attack surface and improving security for multi-tenant workloads.
#
# USAGE:
#   ./phase-gvisor.sh [--auto] [--force]
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
export FORCE

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed "gvisor" && [[ "$FORCE" != true ]]; then
    log_warning "gVisor already installed. Use --force to reinstall."
    exit 0
fi

# -----------------------------------------------------------------------------
# Detect OS
# -----------------------------------------------------------------------------
OS=$(detect_os)
if [[ "$OS" != "linux" ]]; then
    log_error "gVisor is only supported on Linux"
    exit 1
fi

# -----------------------------------------------------------------------------
# Install gVisor
# -----------------------------------------------------------------------------
log_step "Installing gVisor..."

if command -v runsc &>/dev/null && [[ "$FORCE" != true ]]; then
    log_success "gVisor already installed"
else
    log_info "Downloading and installing gVisor..."
    
    # Download the latest gVisor release
    curl -fsSL https://gvisor.dev/install.sh | bash
    
    # Verify installation
    if command -v runsc &>/dev/null; then
        log_success "gVisor installed successfully"
        runsc --version
    else
        log_error "gVisor installation failed"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Configure Docker to use gVisor
# -----------------------------------------------------------------------------
log_step "Configuring Docker for gVisor..."

DOCKER_DAEMON_CONFIG="/etc/docker/daemon.json"

# Check if daemon.json exists
if [[ ! -f "$DOCKER_DAEMON_CONFIG" ]]; then
    echo '{}' > "$DOCKER_DAEMON_CONFIG"
fi

# Add gVisor runtime configuration
if ! grep -q "runsc" "$DOCKER_DAEMON_CONFIG"; then
    # Use jq to add the runtime configuration
    if command -v jq &>/dev/null; then
        jq '. + {"runtimes": {"runsc": {"path": "runsc"}}}' "$DOCKER_DAEMON_CONFIG" > "$DOCKER_DAEMON_CONFIG.tmp"
        mv "$DOCKER_DAEMON_CONFIG.tmp" "$DOCKER_DAEMON_CONFIG"
        log_success "Added gVisor runtime to Docker daemon.json"
    else
        # Fallback: add manually
        echo '{
            "runtimes": {
                "runsc": {
                    "path": "runsc"
                }
            }
        }' > "$DOCKER_DAEMON_CONFIG"
        log_success "Created Docker daemon.json with gVisor runtime"
    fi
else
    log_success "gVisor runtime already configured in Docker"
fi

# Restart Docker to apply changes
log_step "Restarting Docker..."
systemctl restart docker || service docker restart || true

# Verify gVisor is available
if docker info 2>/dev/null | grep -q "runsc"; then
    log_success "gVisor runtime is available in Docker"
else
    log_warning "gVisor runtime may not be available. Please check Docker configuration."
fi

# -----------------------------------------------------------------------------
# Test gVisor
# -----------------------------------------------------------------------------
log_step "Testing gVisor..."

if docker run --rm --runtime=runsc hello-world 2>/dev/null; then
    log_success "gVisor is working correctly"
else
    log_warning "gVisor test failed. Please check the installation."
fi

# -----------------------------------------------------------------------------
# Update docker-compose.yaml to use gVisor
# -----------------------------------------------------------------------------
log_step "Updating docker-compose.yaml for gVisor..."

COMPOSE_FILE="$PROJECT_ROOT/deploy/docker/docker-compose.yaml"

if [[ -f "$COMPOSE_FILE" ]]; then
    # Check if gVisor runtime is already set
    if grep -q "runtime: runsc" "$COMPOSE_FILE"; then
        log_success "gVisor runtime already set in docker-compose.yaml"
    else
        # Add runtime configuration to services
        log_info "Adding gVisor runtime to docker-compose.yaml services..."
        
        # Use sed to add runtime: runsc to services
        # This is a simple approach - for production, use a more robust method
        sed -i '/^  odoo:/,/^  / s/\(restart: unless-stopped\)/runtime: runsc\n    \1/' "$COMPOSE_FILE"
        sed -i '/^  langgraph-server:/,/^  / s/\(restart: unless-stopped\)/runtime: runsc\n    \1/' "$COMPOSE_FILE"
        sed -i '/^  dynamo:/,/^  / s/\(restart: unless-stopped\)/runtime: runsc\n    \1/' "$COMPOSE_FILE"
        
        log_success "Updated docker-compose.yaml with gVisor runtime"
    fi
else
    log_warning "docker-compose.yaml not found. Please manually add runtime: runsc to services."
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete "gvisor"
log_success "gVisor installation and configuration complete"

echo ""
echo "============================================================"
echo " gVisor Security Hardening"
echo "============================================================"
echo ""
echo "gVisor provides strong container isolation by running a user-space kernel."
echo ""
echo "To verify gVisor is working:"
echo "  docker run --rm --runtime=runsc hello-world"
echo ""
echo "To use gVisor with existing containers:"
echo "  docker compose -f deploy/docker/docker-compose.yaml down"
echo "  docker compose -f deploy/docker/docker-compose.yaml up -d"
echo ""
echo "Note: GPU workloads may not work with gVisor. For GPU containers,"
echo "consider using the default runtime or configuring gVisor with GPU support."
echo "============================================================"