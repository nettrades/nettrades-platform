#!/bin/bash
# =============================================================================
# FILE: scripts/restore.sh
# =============================================================================
# PURPOSE:
#   Restores the NETTRADES platform from a backup created by backup.sh.
#
# USAGE:
#   ./restore.sh /path/to/backup.tar.gz [--auto]
#
# EXAMPLES:
#   ./restore.sh ~/.nettrades/backups/nettrades-backup-20260808_143000.tar.gz
#   ./restore.sh /mnt/backup/nettrades-backup-20260808.tar.gz --auto
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --auto)
            AUTO=true
            shift
            ;;
        --help)
            echo "Usage: $0 /path/to/backup.tar.gz [--auto]"
            echo "  --auto    Non-interactive mode"
            exit 0
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            if [[ -z "$BACKUP_FILE" ]]; then
                BACKUP_FILE="$1"
                shift
            else
                echo "Error: Multiple backup files specified"
                exit 1
            fi
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Validate backup file
# -----------------------------------------------------------------------------
if [[ -z "$BACKUP_FILE" ]]; then
    log_error "No backup file specified"
    echo "Usage: $0 /path/to/backup.tar.gz [--auto]"
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    log_error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

log_info "Restoring from: $BACKUP_FILE"

# -----------------------------------------------------------------------------
# Confirm restore (unless auto mode)
# -----------------------------------------------------------------------------
if [[ "$AUTO" != true ]]; then
    echo ""
    echo -e "${RED}WARNING: This will OVERWRITE all existing data!${NC}"
    echo "This action CANNOT be undone."
    echo ""
    echo "Backup file: $BACKUP_FILE"
    echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
    echo ""
    read -p "Type 'YES' to continue: " confirm
    if [[ "$confirm" != "YES" ]]; then
        log_info "Restore cancelled."
        exit 0
    fi
fi

# -----------------------------------------------------------------------------
# Stop services
# -----------------------------------------------------------------------------
log_step "Stopping services..."
if docker compose -f deploy/docker/docker-compose.yaml ps &>/dev/null; then
    docker compose -f deploy/docker/docker-compose.yaml down
    log_success "Services stopped"
else
    log_warning "Docker Compose stack not running"
fi

# -----------------------------------------------------------------------------
# Extract backup
# -----------------------------------------------------------------------------
log_step "Extracting backup..."
TEMP_DIR=$(mktemp -d)
tar xzf "$BACKUP_FILE" -C "$TEMP_DIR" 2>/dev/null

# Find the extracted backup directory
BACKUP_PATH=$(find "$TEMP_DIR" -maxdepth 1 -type d -name "nettrades-backup-*" | head -1)
if [[ -z "$BACKUP_PATH" ]]; then
    log_error "Invalid backup format: could not find backup directory"
    rm -rf "$TEMP_DIR"
    exit 1
fi

log_success "Backup extracted to: $BACKUP_PATH"

# -----------------------------------------------------------------------------
# Validate backup contents
# -----------------------------------------------------------------------------
log_step "Validating backup contents..."

if [[ ! -d "$BACKUP_PATH/postgres" ]]; then
    log_warning "PostgreSQL backup directory not found"
fi

if [[ ! -d "$BACKUP_PATH/volumes" ]]; then
    log_warning "Volumes directory not found"
fi

if [[ ! -f "$BACKUP_PATH/metadata.txt" ]]; then
    log_warning "Metadata file not found"
else
    log_info "Backup metadata:"
    head -10 "$BACKUP_PATH/metadata.txt"
fi

# -----------------------------------------------------------------------------
# Restore PostgreSQL
# -----------------------------------------------------------------------------
if [[ -f "$BACKUP_PATH/postgres/dumpall.sql" ]]; then
    log_step "Restoring PostgreSQL..."
    docker compose -f deploy/docker/docker-compose.yaml up -d postgres
    sleep 10  # Wait for PostgreSQL to start

    if docker compose -f deploy/docker/docker-compose.yaml exec -T postgres psql -U odoo < "$BACKUP_PATH/postgres/dumpall.sql" 2>/dev/null; then
        log_success "PostgreSQL restored"
    else
        log_error "Failed to restore PostgreSQL"
        exit 1
    fi
else
    log_warning "No PostgreSQL dump found. Skipping database restore."
fi

# -----------------------------------------------------------------------------
# Restore Docker volumes
# -----------------------------------------------------------------------------
if [[ -d "$BACKUP_PATH/volumes" ]]; then
    log_step "Restoring Docker volumes..."
    VOLUME_BACKUPS=$(find "$BACKUP_PATH/volumes" -name "*.tar.gz" 2>/dev/null)
    if [[ -n "$VOLUME_BACKUPS" ]]; then
        for vol_file in $VOLUME_BACKUPS; do
            vol_name=$(basename "$vol_file" .tar.gz)
            log_info "  Restoring volume: $vol_name"
            docker run --rm -v "$vol_name:/data" -v "$BACKUP_PATH/volumes:/backup" alpine tar xzf "/backup/$vol_name.tar.gz" -C /data 2>/dev/null
            if [[ $? -eq 0 ]]; then
                log_success "    Volume $vol_name restored"
            else
                log_warning "    Failed to restore volume: $vol_name"
            fi
        done
    else
        log_warning "No volume backups found"
    fi
fi

# -----------------------------------------------------------------------------
# Restore configuration files
# -----------------------------------------------------------------------------
if [[ -d "$BACKUP_PATH/config" ]]; then
    log_step "Restoring configuration files..."

    # Restore .env
    if [[ -f "$BACKUP_PATH/config/.env" ]]; then
        cp "$BACKUP_PATH/config/.env" deploy/docker/.env
        log_success "  .env restored"
    fi

    # Restore docker-compose.yaml
    if [[ -f "$BACKUP_PATH/config/docker-compose.yaml" ]]; then
        cp "$BACKUP_PATH/config/docker-compose.yaml" deploy/docker/docker-compose.yaml
        log_success "  docker-compose.yaml restored"
    fi

    # Restore Odoo modules
    if [[ -f "$BACKUP_PATH/config/odoo-modules.tar.gz" ]]; then
        tar xzf "$BACKUP_PATH/config/odoo-modules.tar.gz" -C . 2>/dev/null
        log_success "  Odoo modules restored"
    fi

    if [[ -f "$BACKUP_PATH/config/docker-odoo-modules.tar.gz" ]]; then
        tar xzf "$BACKUP_PATH/config/docker-odoo-modules.tar.gz" -C deploy/docker 2>/dev/null
        log_success "  Docker Odoo modules restored"
    fi
fi

# -----------------------------------------------------------------------------
# Start services
# -----------------------------------------------------------------------------
log_step "Starting services..."
docker compose -f deploy/docker/docker-compose.yaml up -d
log_success "Services started"

# -----------------------------------------------------------------------------
# Verify services
# -----------------------------------------------------------------------------
log_step "Verifying services..."
sleep 10

if docker compose -f deploy/docker/docker-compose.yaml ps &>/dev/null; then
    docker compose -f deploy/docker/docker-compose.yaml ps
    log_success "Services running"
else
    log_warning "Some services may not be running. Check with: docker compose ps"
fi

# -----------------------------------------------------------------------------
# Clean up
# -----------------------------------------------------------------------------
rm -rf "$TEMP_DIR"

echo ""
echo "============================================================"
echo " Restore Complete!"
echo "============================================================"
echo "  Backup restored from: $BACKUP_FILE"
echo "  Date: $(date)"
echo ""
echo "To check service status:"
echo "  cd $PROJECT_ROOT/deploy/docker && docker compose ps"
echo ""
echo "To view logs:"
echo "  cd $PROJECT_ROOT/deploy/docker && docker compose logs"
echo "============================================================"

exit 0