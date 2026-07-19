#!/bin/bash
# =============================================================================
# NETTRADES WireGuard Manager
# =============================================================================
# FILE: scripts/wireguard-manager.sh
#
# PURPOSE:
#   This script automates the management of WireGuard peers for the NETTRADES
#   platform. It is designed to be called from:
#     1. The command line by administrators
#     2. Odoo via the nettrades_bridge module (server actions/cron jobs)
#     3. The Electron installer during initial setup
#     4. CI/CD pipelines for automated provisioning
#
#   It provides a secure, idempotent interface for:
#     - Generating key pairs for new clients
#     - Adding peers to the WireGuard server configuration
#     - Removing peers from the configuration
#     - Generating client configuration files
#     - Generating QR codes for mobile clients
#     - Listing all peers with their status
#     - Backing up and restoring configurations
#
# INTEGRATION WITH NETTRADES:
#   - The script is called by phase-system.sh during initial setup
#   - It stores peer information in /etc/wireguard/peers/ for persistence
#   - Client configurations are stored in /root/wireguard-clients/
#   - Keys are stored securely with appropriate permissions
#   - The script supports integration with Odoo for key storage and user management
#
# FUTURE-PROOFING:
#   - Supports automatic IP allocation from a configurable pool
#   - Includes backup/restore functionality for disaster recovery
#   - Logs all operations for audit purposes
#   - Supports integration with external secret management (future)
#   - Designed to work with both single-VM and Kubernetes deployments
#
# USAGE:
#   ./wireguard-manager.sh add <client-name> [ip-address]
#   ./wireguard-manager.sh remove <client-name>
#   ./wireguard-manager.sh list
#   ./wireguard-manager.sh generate <client-name>
#   ./wireguard-manager.sh qr <client-name>
#   ./wireguard-manager.sh backup
#   ./wireguard-manager.sh restore <backup-file>
#   ./wireguard-manager.sh status
#
# EXAMPLES:
#   ./wireguard-manager.sh add laptop 10.10.10.50
#   ./wireguard-manager.sh remove laptop
#   ./wireguard-manager.sh generate laptop
#   ./wireguard-manager.sh qr laptop
#   ./wireguard-manager.sh backup
#   ./wireguard-manager.sh restore /root/wireguard-backup-20260101.tar.gz
#   ./wireguard-manager.sh status
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------

# WireGuard interface name (default: wg0)
WG_INTERFACE="${WG_INTERFACE:-wg0}"

# WireGuard configuration directory
WG_CONFIG_DIR="${WG_CONFIG_DIR:-/etc/wireguard}"

# Directory for storing peer configurations
WG_PEERS_DIR="${WG_PEERS_DIR:-$WG_CONFIG_DIR/peers}"

# Directory for storing client configuration files
WG_CLIENTS_DIR="${WG_CLIENTS_DIR:-/root/wireguard-clients}"

# WireGuard subnet for client IPs
WG_SUBNET="${WG_SUBNET:-10.10.10.0/24}"
WG_SUBNET_START="${WG_SUBNET_START:-2}"
WG_SUBNET_END="${WG_SUBNET_END:-254}"

# WireGuard listen port
WG_PORT="${WG_PORT:-51821}"

# Log directory
LOG_DIR="${LOG_DIR:-/var/log/nettrades}"
LOG_FILE="$LOG_DIR/wireguard-manager.log"

# Backup directory
BACKUP_DIR="${BACKUP_DIR:-/root/wireguard-backups}"

# -----------------------------------------------------------------------------
# COLOR CODES (for terminal output)
# -----------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# LOGGING FUNCTIONS
# -----------------------------------------------------------------------------

log_info() {
    local msg="[INFO] $*"
    echo -e "${BLUE}${msg}${NC}"
    echo "$(date -Iseconds) $msg" >> "$LOG_FILE"
}

log_success() {
    local msg="[SUCCESS] $*"
    echo -e "${GREEN}${msg}${NC}"
    echo "$(date -Iseconds) $msg" >> "$LOG_FILE"
}

log_warning() {
    local msg="[WARNING] $*"
    echo -e "${YELLOW}${msg}${NC}" >&2
    echo "$(date -Iseconds) $msg" >> "$LOG_FILE"
}

log_error() {
    local msg="[ERROR] $*"
    echo -e "${RED}${msg}${NC}" >&2
    echo "$(date -Iseconds) $msg" >> "$LOG_FILE"
}

# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------------------------------------------

# Ensure required directories exist
ensure_directories() {
    mkdir -p "$WG_PEERS_DIR" "$WG_CLIENTS_DIR" "$LOG_DIR" "$BACKUP_DIR"
    chmod 700 "$WG_PEERS_DIR" "$WG_CLIENTS_DIR" "$BACKUP_DIR" 2>/dev/null || true
}

# Generate a private key
gen_private_key() {
    wg genkey 2>/dev/null
}

# Generate a public key from a private key
gen_public_key() {
    echo "$1" | wg pubkey 2>/dev/null
}

# Get the server's public key
get_server_public_key() {
    if [[ -f "$WG_CONFIG_DIR/publickey" ]]; then
        cat "$WG_CONFIG_DIR/publickey"
    else
        # Extract from the WireGuard config if available
        local private_key=$(grep -oP 'PrivateKey = \K.*' "$WG_CONFIG_DIR/$WG_INTERFACE.conf" 2>/dev/null | head -1)
        if [[ -n "$private_key" ]]; then
            echo "$private_key" | wg pubkey 2>/dev/null
        else
            echo ""
        fi
    fi
}

# Get the server's endpoint (IP:port)
get_server_endpoint() {
    local endpoint=$(grep -oP 'Endpoint = \K.*' "$WG_CONFIG_DIR/$WG_INTERFACE.conf" 2>/dev/null | head -1)
    if [[ -z "$endpoint" ]]; then
        # Fallback: use the server's public IP and the configured port
        local public_ip=$(curl -s ifconfig.me 2>/dev/null || echo "auto")
        endpoint="${public_ip}:${WG_PORT}"
    fi
    echo "$endpoint"
}

# Get the next available IP address in the subnet
get_next_ip() {
    local used_ips=$(grep -oP 'AllowedIPs = \K[0-9.]+' "$WG_CONFIG_DIR/$WG_INTERFACE.conf" 2>/dev/null || echo "")
    local last_ip=$WG_SUBNET_START

    for ip in $used_ips; do
        local num=$(echo "$ip" | cut -d. -f4)
        if [[ -n "$num" ]] && [[ "$num" -ge "$last_ip" ]] && [[ "$num" -lt "$WG_SUBNET_END" ]]; then
            last_ip=$((num + 1))
        fi
    done

    if [[ "$last_ip" -gt "$WG_SUBNET_END" ]]; then
        log_error "No available IP addresses in subnet $WG_SUBNET"
        return 1
    fi

    echo "${WG_SUBNET%.*}.$last_ip"
}

# Validate client name (alphanumeric, underscore, hyphen only)
validate_client_name() {
    local name="$1"
    if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        log_error "Invalid client name. Use only letters, numbers, underscores, and hyphens."
        return 1
    fi
    return 0
}

# -----------------------------------------------------------------------------
# CORE FUNCTIONS
# -----------------------------------------------------------------------------

# Add a new peer
add_peer() {
    local client_name="$1"
    local client_ip="${2:-}"

    ensure_directories

    # Validate client name
    if ! validate_client_name "$client_name"; then
        return 1
    fi

    # Check if peer already exists
    if [[ -f "$WG_PEERS_DIR/$client_name.conf" ]]; then
        log_error "Peer '$client_name' already exists"
        return 1
    fi

    # Generate keys
    local private_key=$(gen_private_key)
    local public_key=$(gen_public_key "$private_key")

    if [[ -z "$private_key" ]] || [[ -z "$public_key" ]]; then
        log_error "Failed to generate WireGuard keys"
        return 1
    fi

    # Determine IP
    if [[ -z "$client_ip" ]]; then
        client_ip=$(get_next_ip)
        if [[ -z "$client_ip" ]]; then
            return 1
        fi
    fi

    # Validate IP format
    if ! [[ "$client_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        log_error "Invalid IP address format: $client_ip"
        return 1
    fi

    # Store peer information
    cat > "$WG_PEERS_DIR/$client_name.conf" << EOF
# Peer: $client_name
# Added: $(date -Iseconds)
# IP: $client_ip/32
[Peer]
PublicKey = $public_key
AllowedIPs = $client_ip/32
EOF

    # Append to main WireGuard config (if it exists)
    if [[ -f "$WG_CONFIG_DIR/$WG_INTERFACE.conf" ]]; then
        cat >> "$WG_CONFIG_DIR/$WG_INTERFACE.conf" << EOF

# Peer: $client_name
[Peer]
PublicKey = $public_key
AllowedIPs = $client_ip/32
EOF
    else
        log_warning "WireGuard config not found at $WG_CONFIG_DIR/$WG_INTERFACE.conf"
        log_info "Creating new config..."
        cat > "$WG_CONFIG_DIR/$WG_INTERFACE.conf" << EOF
[Interface]
Address = ${WG_SUBNET%.*}.1/24
ListenPort = $WG_PORT
PrivateKey = $(cat "$WG_CONFIG_DIR/privatekey" 2>/dev/null || echo "")

# Peer: $client_name
[Peer]
PublicKey = $public_key
AllowedIPs = $client_ip/32
EOF
    fi

    # Reload WireGuard
    if command -v wg &>/dev/null; then
        wg syncconf "$WG_INTERFACE" <(wg-quick strip "$WG_INTERFACE" 2>/dev/null || echo "") 2>/dev/null || {
            log_warning "Failed to reload WireGuard. You may need to restart the service."
        }
    fi

    log_success "Peer '$client_name' added with IP $client_ip"
    log_info "Public key: $public_key"

    # Generate client config
    generate_client_config "$client_name" "$private_key" "$client_ip" "$public_key"

    # Log the operation
    echo "$(date -Iseconds) ADD $client_name $client_ip $public_key" >> "$LOG_FILE"
}

# Remove a peer
remove_peer() {
    local client_name="$1"
    local peer_file="$WG_PEERS_DIR/$client_name.conf"

    ensure_directories

    if [[ ! -f "$peer_file" ]]; then
        log_error "Peer '$client_name' not found"
        return 1
    fi

    # Get the public key from the stored configuration
    local public_key=$(grep -oP 'PublicKey = \K.*' "$peer_file" 2>/dev/null || echo "")

    if [[ -z "$public_key" ]]; then
        log_error "Could not find public key for peer '$client_name'"
        return 1
    fi

    # Remove from main config
    if [[ -f "$WG_CONFIG_DIR/$WG_INTERFACE.conf" ]]; then
        # Remove the peer section (including the comment line)
        sed -i "/# Peer: $client_name/d" "$WG_CONFIG_DIR/$WG_INTERFACE.conf" 2>/dev/null || true
        sed -i "/PublicKey = $public_key/,+1d" "$WG_CONFIG_DIR/$WG_INTERFACE.conf" 2>/dev/null || true
        # Remove any blank lines left behind
        sed -i '/^$/N;/^\n$/d' "$WG_CONFIG_DIR/$WG_INTERFACE.conf" 2>/dev/null || true
    fi

    # Remove peer file
    rm -f "$peer_file"

    # Remove client config and QR code
    rm -f "$WG_CLIENTS_DIR/$client_name.conf"
    rm -f "$WG_CLIENTS_DIR/$client_name.png" 2>/dev/null || true

    # Reload WireGuard
    if command -v wg &>/dev/null; then
        wg syncconf "$WG_INTERFACE" <(wg-quick strip "$WG_INTERFACE" 2>/dev/null || echo "") 2>/dev/null || {
            log_warning "Failed to reload WireGuard. You may need to restart the service."
        }
    fi

    log_success "Peer '$client_name' removed"
    echo "$(date -Iseconds) REMOVE $client_name" >> "$LOG_FILE"
}

# List all peers
list_peers() {
    ensure_directories

    echo ""
    echo "WireGuard Peers"
    echo "==============="
    echo ""

    if [[ -d "$WG_PEERS_DIR" ]] && [[ -n "$(ls -A "$WG_PEERS_DIR" 2>/dev/null)" ]]; then
        printf "%-20s %-18s %-45s %-10s\n" "NAME" "IP" "PUBLIC KEY" "STATUS"
        printf "%-20s %-18s %-45s %-10s\n" "----" "--" "----------" "------"

        for peer in "$WG_PEERS_DIR"/*.conf; do
            if [[ -f "$peer" ]]; then
                local name=$(basename "$peer" .conf)
                local ip=$(grep -oP 'AllowedIPs = \K[0-9.]+' "$peer" 2>/dev/null || echo "unknown")
                local pubkey=$(grep -oP 'PublicKey = \K.*' "$peer" 2>/dev/null || echo "unknown")
                local status=$(wg show "$WG_INTERFACE" 2>/dev/null | grep -q "$pubkey" && echo "active" || echo "inactive")
                printf "%-20s %-18s %-45s %-10s\n" "$name" "$ip" "$pubkey" "$status"
            fi
        done
    else
        echo "No peers configured"
    fi

    echo ""
    echo "Total peers: $(find "$WG_PEERS_DIR" -name "*.conf" 2>/dev/null | wc -l)"
}

# Generate a client configuration file
generate_client_config() {
    local client_name="$1"
    local private_key="$2"
    local client_ip="$3"
    local public_key="$4"

    ensure_directories

    local server_public_key=$(get_server_public_key)
    local server_endpoint=$(get_server_endpoint)

    if [[ -z "$server_public_key" ]]; then
        log_warning "Server public key not found. Client config will have placeholder."
        server_public_key="SERVER_PUBLIC_KEY_PLACEHOLDER"
    fi

    cat > "$WG_CLIENTS_DIR/$client_name.conf" << EOF
[Interface]
PrivateKey = $private_key
Address = $client_ip/32
DNS = 8.8.8.8, 1.1.1.1

[Peer]
PublicKey = $server_public_key
Endpoint = $server_endpoint
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

    chmod 600 "$WG_CLIENTS_DIR/$client_name.conf"
    log_success "Client configuration created: $WG_CLIENTS_DIR/$client_name.conf"
}

# Generate a QR code for a client
generate_qr() {
    local client_name="$1"
    local config_file="$WG_CLIENTS_DIR/$client_name.conf"

    ensure_directories

    if [[ ! -f "$config_file" ]]; then
        log_error "Client config not found: $config_file"
        return 1
    fi

    if command -v qrencode &>/dev/null; then
        qrencode -t PNG -o "$WG_CLIENTS_DIR/$client_name.png" < "$config_file"
        log_success "QR code generated: $WG_CLIENTS_DIR/$client_name.png"
        echo ""
        echo "📱 Scan this QR code with your WireGuard mobile app:"
        echo "   File: $WG_CLIENTS_DIR/$client_name.png"
    else
        log_warning "qrencode not installed. Please install: sudo apt install qrencode"
        log_info "Client config contents:"
        echo ""
        cat "$config_file"
    fi
}

# Backup all WireGuard configurations
backup_configs() {
    ensure_directories

    local backup_file="$BACKUP_DIR/wireguard-backup-$(date +%Y%m%d-%H%M%S).tar.gz"

    if [[ -d "$WG_CONFIG_DIR" ]]; then
        tar -czf "$backup_file" -C / etc/wireguard/ 2>/dev/null || {
            log_error "Failed to create backup"
            return 1
        }
        log_success "Backup created: $backup_file"
        echo "$(date -Iseconds) BACKUP $backup_file" >> "$LOG_FILE"
    else
        log_error "WireGuard config directory not found: $WG_CONFIG_DIR"
        return 1
    fi
}

# Restore WireGuard configurations from a backup
restore_configs() {
    local backup_file="$1"

    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi

    # Stop WireGuard
    wg-quick down "$WG_INTERFACE" 2>/dev/null || true

    # Restore
    tar -xzf "$backup_file" -C / 2>/dev/null || {
        log_error "Failed to restore from backup"
        return 1
    }

    # Restart WireGuard
    wg-quick up "$WG_INTERFACE" 2>/dev/null || {
        log_warning "Failed to start WireGuard after restore. Please check the configuration."
    }

    log_success "Restored from backup: $backup_file"
    echo "$(date -Iseconds) RESTORE $backup_file" >> "$LOG_FILE"
}

# Show WireGuard status
show_status() {
    echo ""
    echo "WireGuard Status"
    echo "================"
    echo ""

    if command -v wg &>/dev/null; then
        wg show "$WG_INTERFACE" 2>/dev/null || {
            echo "WireGuard interface '$WG_INTERFACE' is not running"
            echo ""
            echo "To start it: wg-quick up $WG_INTERFACE"
        }
    else
        echo "WireGuard tools not found"
    fi

    echo ""
    echo "Interface: $WG_INTERFACE"
    echo "Port: $WG_PORT"
    echo "Subnet: $WG_SUBNET"
    echo "Peers: $(find "$WG_PEERS_DIR" -name "*.conf" 2>/dev/null | wc -l)"
}

# -----------------------------------------------------------------------------
# MAIN ENTRY POINT
# -----------------------------------------------------------------------------

main() {
    local command="${1:-}"

    # Ensure log directory exists
    mkdir -p "$LOG_DIR"

    case "$command" in
        add)
            if [[ $# -lt 2 ]]; then
                echo "Usage: $0 add <client-name> [ip-address]"
                exit 1
            fi
            add_peer "$2" "${3:-}"
            ;;
        remove)
            if [[ $# -lt 2 ]]; then
                echo "Usage: $0 remove <client-name>"
                exit 1
            fi
            remove_peer "$2"
            ;;
        list)
            list_peers
            ;;
        generate)
            if [[ $# -lt 2 ]]; then
                echo "Usage: $0 generate <client-name>"
                exit 1
            fi
            local client_name="$2"
            local peer_file="$WG_PEERS_DIR/$client_name.conf"
            if [[ ! -f "$peer_file" ]]; then
                log_error "Peer '$client_name' not found"
                exit 1
            fi
            local public_key=$(grep -oP 'PublicKey = \K.*' "$peer_file" 2>/dev/null || echo "")
            local client_ip=$(grep -oP 'AllowedIPs = \K[0-9.]+' "$peer_file" 2>/dev/null || echo "")
            local private_key=$(gen_private_key)
            generate_client_config "$client_name" "$private_key" "$client_ip" "$public_key"
            ;;
        qr)
            if [[ $# -lt 2 ]]; then
                echo "Usage: $0 qr <client-name>"
                exit 1
            fi
            generate_qr "$2"
            ;;
        backup)
            backup_configs
            ;;
        restore)
            if [[ $# -lt 2 ]]; then
                echo "Usage: $0 restore <backup-file>"
                exit 1
            fi
            restore_configs "$2"
            ;;
        status)
            show_status
            ;;
        help|--help|-h)
            cat << EOF
NETTRADES WireGuard Manager

Usage:
    $0 add <client-name> [ip-address]   Add a new peer
    $0 remove <client-name>             Remove a peer
    $0 list                             List all peers
    $0 generate <client-name>           Generate client config
    $0 qr <client-name>                 Generate QR code for client
    $0 backup                           Backup all WireGuard configs
    $0 restore <backup-file>            Restore from backup
    $0 status                           Show WireGuard status
    $0 help                             Show this help message

Examples:
    $0 add laptop 10.10.10.50
    $0 remove laptop
    $0 generate laptop
    $0 qr laptop
    $0 backup
    $0 restore /root/wireguard-backup-20260101.tar.gz
    $0 status

Environment Variables:
    WG_INTERFACE    WireGuard interface name (default: wg0)
    WG_CONFIG_DIR   WireGuard config directory (default: /etc/wireguard)
    WG_SUBNET       Subnet for client IPs (default: 10.10.10.0/24)
    WG_PORT         WireGuard listen port (default: 51821)
    LOG_DIR         Log directory (default: /var/log/nettrades)
    BACKUP_DIR      Backup directory (default: /root/wireguard-backups)
EOF
            ;;
        *)
            echo "Unknown command: $command"
            echo "Run '$0 help' for usage information."
            exit 1
            ;;
    esac
}

# -----------------------------------------------------------------------------
# SCRIPT EXECUTION
# -----------------------------------------------------------------------------

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root. Please use sudo."
    exit 1
fi

# Ensure WireGuard tools are installed
if ! command -v wg &>/dev/null; then
    log_error "WireGuard tools not found. Please install wireguard-tools."
    exit 1
fi

# Run main function
main "$@"