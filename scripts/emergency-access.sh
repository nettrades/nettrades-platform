#!/bin/bash
# =============================================================================
# FILE: scripts/emergency-access.sh
# PURPOSE: Emergency admin access recovery with multiple fallback options
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

EMERGENCY_DIR="${PROJECT_ROOT}/emergency-access"
mkdir -p "$EMERGENCY_DIR"
chmod 700 "$EMERGENCY_DIR"

# -----------------------------------------------------------------------------
# Colours
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# -----------------------------------------------------------------------------
# 1. Create Odoo emergency user
# -----------------------------------------------------------------------------
create_odoo_emergency() {
    log_step "Creating Odoo emergency user..."
    local password=$(openssl rand -base64 24 | tr -d '+/=' | cut -c1-24)
    
    if ! docker compose exec -T postgres psql -U odoo -d odoo -c "SELECT 1" &>/dev/null; then
        log_warning "PostgreSQL not running. Skipping Odoo emergency user."
        return 1
    fi
    
    docker compose exec -T postgres psql -U odoo -d odoo <<EOF
INSERT INTO res_users (login, password, active, create_date, write_date)
VALUES ('emergency', crypt('$password', gen_salt('bf')), true, NOW(), NOW())
ON CONFLICT (login) DO NOTHING;
EOF
    
    echo "ODOO_EMERGENCY_USER=emergency" > "$EMERGENCY_DIR/credentials.txt"
    echo "ODOO_EMERGENCY_PASSWORD=$password" >> "$EMERGENCY_DIR/credentials.txt"
    chmod 600 "$EMERGENCY_DIR/credentials.txt"
    log_success "Odoo emergency user created"
    return 0
}

# -----------------------------------------------------------------------------
# 2. Create admin password reset script
# -----------------------------------------------------------------------------
create_reset_script() {
    log_step "Creating admin password reset script..."
    cat > "$EMERGENCY_DIR/reset-admin-password.sh" << 'EOF'
#!/bin/bash
# Reset Odoo admin password
cd "$(dirname "$0")"
read -sp "Enter new admin password: " new_password
echo
docker compose exec -T postgres psql -U odoo -d odoo <<SQL
UPDATE res_users SET password = crypt('$new_password', gen_salt('bf'))
WHERE login = 'admin';
SQL
echo "Admin password updated successfully"
EOF
    chmod +x "$EMERGENCY_DIR/reset-admin-password.sh"
    log_success "Admin password reset script created"
}

# -----------------------------------------------------------------------------
# 3. Backup .env file
# -----------------------------------------------------------------------------
backup_env() {
    log_step "Backing up .env file..."
    local backup_file="$EMERGENCY_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"
    if [[ -f "$PROJECT_ROOT/deploy/docker/.env" ]]; then
        cp "$PROJECT_ROOT/deploy/docker/.env" "$backup_file"
        chmod 600 "$backup_file"
        log_success ".env backed up to $backup_file"
    else
        log_warning ".env file not found"
    fi
}

# -----------------------------------------------------------------------------
# 4. Create WireGuard client config generator
# -----------------------------------------------------------------------------
create_wireguard_client_script() {
    log_step "Creating WireGuard client config generator..."
    cat > "$EMERGENCY_DIR/create-wireguard-client.sh" << 'EOF'
#!/bin/bash
# Generate WireGuard client config
cd "$(dirname "$0")"
read -p "Enter client name: " client_name
if [[ -z "$client_name" ]]; then
    echo "Client name required"
    exit 1
fi
/usr/local/bin/wireguard-manager.sh add "$client_name"
EOF
    chmod +x "$EMERGENCY_DIR/create-wireguard-client.sh"
    log_success "WireGuard client generator created"
}

# -----------------------------------------------------------------------------
# 5. Create emergency SSH key
# -----------------------------------------------------------------------------
create_emergency_ssh_key() {
    log_step "Creating emergency SSH key..."
    if [[ ! -f "$EMERGENCY_DIR/emergency_ssh_key" ]]; then
        ssh-keygen -t ed25519 -f "$EMERGENCY_DIR/emergency_ssh_key" -N "" -C "emergency@nettrades"
        chmod 600 "$EMERGENCY_DIR/emergency_ssh_key"
        chmod 644 "$EMERGENCY_DIR/emergency_ssh_key.pub"
        log_success "Emergency SSH key created"
    else
        log_info "Emergency SSH key already exists"
    fi
}

# -----------------------------------------------------------------------------
# 6. Display summary
# -----------------------------------------------------------------------------
display_summary() {
    echo ""
    echo "============================================================"
    echo " EMERGENCY ACCESS CONFIGURATION COMPLETE"
    echo "============================================================"
    echo ""
    echo "Emergency access options are stored in:"
    echo "  $EMERGENCY_DIR"
    echo ""
    echo "1. Odoo Emergency User:"
    echo "   Login: emergency"
    echo "   Password: see $EMERGENCY_DIR/credentials.txt"
    echo ""
    echo "2. Admin Password Reset:"
    echo "   Run: $EMERGENCY_DIR/reset-admin-password.sh"
    echo ""
    echo "3. .env Backup:"
    echo "   Location: $EMERGENCY_DIR/.env.backup.*"
    echo ""
    echo "4. WireGuard Client Generator:"
    echo "   Run: $EMERGENCY_DIR/create-wireguard-client.sh"
    echo ""
    echo "5. Emergency SSH Key:"
    echo "   Private: $EMERGENCY_DIR/emergency_ssh_key"
    echo "   Public:  $EMERGENCY_DIR/emergency_ssh_key.pub"
    echo ""
    echo "============================================================"
    echo ""
    echo "IMPORTANT: Save these credentials securely."
    echo "The emergency user password is also available via:"
    echo "  docker compose exec -T postgres psql -U odoo -d odoo"
    echo "  -c \"SELECT login, password FROM res_users WHERE login='emergency';\""
    echo "============================================================"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    log_header "Emergency Access Setup"
    create_odoo_emergency
    create_reset_script
    backup_env
    create_wireguard_client_script
    create_emergency_ssh_key
    display_summary
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi