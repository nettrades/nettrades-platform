#!/bin/bash
# =============================================================================
# FILE: scripts/backup.sh
# =============================================================================
# PURPOSE:
#   Creates a complete backup of the NETTRADES platform.
#   Backs up:
#     - PostgreSQL databases (Odoo + LangGraph checkpoints)
#     - Docker volumes (Odoo data, Grafana, Prometheus, etc.)
#     - Configuration files (.env, custom Odoo modules)
#
# USAGE:
#   ./backup.sh [--output-dir /path/to/backups]
#
# RESTORE:
#   See restore.sh for restoring from a backup.
#
# EXAMPLES:
#   ./backup.sh                          # Creates backup in default location
#   ./backup.sh --output-dir /mnt/backup # Creates backup in custom location
#   ./backup.sh --auto                   # Non-interactive mode
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
BACKUP_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --auto)
            AUTO=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--output-dir /path/to/backups] [--auto]"
            echo "  --output-dir   Directory to store backups (default: ~/.nettrades/backups)"
            echo "  --auto         Non-interactive mode"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Set default backup directory if not specified
# -----------------------------------------------------------------------------
if [[ -z "$BACKUP_DIR" ]]; then
    BACKUP_DIR="$HOME/.nettrades/backups"
fi

mkdir -p "$BACKUP_DIR"
log_info "Backup directory: $BACKUP_DIR"

# -----------------------------------------------------------------------------
# Check if Docker Compose stack is running
# -----------------------------------------------------------------------------
if ! docker compose -f deploy/docker/docker-compose.yaml ps &>/dev/null; then
    log_warning "Docker Compose stack is not running. Some services may not be available."
    if [[ "$AUTO" != true ]]; then
        read -rp "Continue anyway? (y/N): " cont
        if [[ ! "$cont" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# -----------------------------------------------------------------------------
# Generate timestamp and backup name
# -----------------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="nettrades-backup-$TIMESTAMP"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

log_info "Creating backup: $BACKUP_NAME"
mkdir -p "$BACKUP_PATH"

# -----------------------------------------------------------------------------
# 1. Backup PostgreSQL using pg_dumpall
# -----------------------------------------------------------------------------
log_step "Backing up PostgreSQL..."
mkdir -p "$BACKUP_PATH/postgres"

if docker compose -f deploy/docker/docker-compose.yaml ps postgres &>/dev/null; then
    docker compose -f deploy/docker/docker-compose.yaml exec -T postgres pg_dumpall -U odoo > "$BACKUP_PATH/postgres/dumpall.sql" 2>/dev/null
    if [[ $? -eq 0 ]] && [[ -s "$BACKUP_PATH/postgres/dumpall.sql" ]]; then
        log_success "PostgreSQL backup complete ($(du -h "$BACKUP_PATH/postgres/dumpall.sql" | cut -f1))"
    else
        log_warning "PostgreSQL backup may be incomplete. Check the dump file."
    fi
else
    log_warning "PostgreSQL container not running. Skipping database backup."
    echo "PostgreSQL container not running" > "$BACKUP_PATH/postgres/ERROR.txt"
fi

# -----------------------------------------------------------------------------
# 2. Backup Docker volumes using tar
# -----------------------------------------------------------------------------
log_step "Backing up Docker volumes..."
mkdir -p "$BACKUP_PATH/volumes"

# Get all volumes used by the stack
VOLUMES=$(docker compose -f deploy/docker/docker-compose.yaml config --volumes 2>/dev/null | sort -u)

if [[ -z "$VOLUMES" ]]; then
    log_warning "No Docker volumes found. Skipping volume backup."
else
    for vol in $VOLUMES; do
        log_info "  Backing up volume: $vol"
        # Use a temporary container to tar the volume
        if docker run --rm -v "$vol:/data:ro" -v "$BACKUP_PATH/volumes:/backup" alpine tar czf "/backup/$vol.tar.gz" -C /data . 2>/dev/null; then
            log_success "    Volume $vol backed up ($(du -h "$BACKUP_PATH/volumes/$vol.tar.gz" | cut -f1))"
        else
            log_warning "    Failed to back up volume: $vol"
        fi
    done
fi

# -----------------------------------------------------------------------------
# 3. Backup configuration files
# -----------------------------------------------------------------------------
log_step "Backing up configuration files..."
mkdir -p "$BACKUP_PATH/config"

# Backup .env file
if [[ -f "deploy/docker/.env" ]]; then
    cp "deploy/docker/.env" "$BACKUP_PATH/config/.env"
    log_success "  .env backed up"
else
    log_warning "  .env file not found"
fi

# Backup Odoo modules (if present)
if [[ -d "odoo-modules" ]]; then
    tar czf "$BACKUP_PATH/config/odoo-modules.tar.gz" odoo-modules/ 2>/dev/null
    log_success "  Odoo modules backed up"
fi

# Backup custom Odoo addons (if present)
if [[ -d "deploy/docker/odoo-modules" ]]; then
    tar czf "$BACKUP_PATH/config/docker-odoo-modules.tar.gz" deploy/docker/odoo-modules/ 2>/dev/null
    log_success "  Docker Odoo modules backed up"
fi

# Backup docker-compose.yaml
if [[ -f "deploy/docker/docker-compose.yaml" ]]; then
    cp "deploy/docker/docker-compose.yaml" "$BACKUP_PATH/config/docker-compose.yaml"
    log_success "  docker-compose.yaml backed up"
fi

# -----------------------------------------------------------------------------
# 4. Create metadata file
# -----------------------------------------------------------------------------
log_step "Creating metadata..."
cat > "$BACKUP_PATH/metadata.txt" << EOF
NETTRADES Backup
===============
Date: $(date)
Host: $(hostname)
User: $(whoami)
Platform: $(detect_platform)
OS: $(detect_os)
Backup Tool: $0
Project Root: $PROJECT_ROOT
Backup Size: $(du -sh "$BACKUP_PATH" | cut -f1)

Docker Version: $(docker --version 2>/dev/null || echo "N/A")
Docker Compose Version: $(docker compose version 2>/dev/null || echo "N/A")
PostgreSQL Version: $(docker compose -f deploy/docker/docker-compose.yaml exec -T postgres psql -U odoo -c "SELECT version();" 2>/dev/null | head -1 || echo "N/A")

Files backed up:
- PostgreSQL dump: $BACKUP_PATH/postgres/dumpall.sql
- Volumes: $BACKUP_PATH/volumes/
- Configuration: $BACKUP_PATH/config/
EOF

log_success "Metadata created"

# -----------------------------------------------------------------------------
# 5. Verify the backup
# -----------------------------------------------------------------------------
log_step "Verifying backup..."

# Check PostgreSQL dump
if [[ -f "$BACKUP_PATH/postgres/dumpall.sql" ]]; then
    if grep -q "PostgreSQL" "$BACKUP_PATH/postgres/dumpall.sql" 2>/dev/null; then
        log_success "  PostgreSQL dump verified"
    else
        log_warning "  PostgreSQL dump may be invalid"
    fi
fi

# Check volume backups
VOLUME_BACKUPS=$(find "$BACKUP_PATH/volumes" -name "*.tar.gz" 2>/dev/null | wc -l)
if [[ "$VOLUME_BACKUPS" -gt 0 ]]; then
    log_success "  $VOLUME_BACKUPS volume backups verified"
else
    log_warning "  No volume backups found"
fi

# -----------------------------------------------------------------------------
# 6. Compress the backup
# -----------------------------------------------------------------------------
log_step "Compressing backup..."
cd "$BACKUP_DIR"
tar czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME" 2>/dev/null
if [[ $? -eq 0 ]]; then
    rm -rf "$BACKUP_NAME"
    FINAL_SIZE=$(du -h "$BACKUP_NAME.tar.gz" | cut -f1)
    log_success "Backup compressed: $BACKUP_NAME.tar.gz ($FINAL_SIZE)"
else
    log_error "Failed to compress backup"
    exit 1
fi

# -----------------------------------------------------------------------------
# 7. Rotate old backups (keep last 30 days)
# -----------------------------------------------------------------------------
log_step "Rotating old backups..."
OLD_BACKUPS=$(find "$BACKUP_DIR" -name "nettrades-backup-*.tar.gz" -mtime +30 2>/dev/null)
if [[ -n "$OLD_BACKUPS" ]]; then
    echo "$OLD_BACKUPS" | while read -r old; do
        rm -f "$old"
        log_info "  Removed old backup: $(basename "$old")"
    done
fi
log_success "Backup rotation complete (kept last 30 days)"

# -----------------------------------------------------------------------------
# 8. Display summary
# -----------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Backup Complete!"
echo "============================================================"
echo "  Backup Location: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
echo "  Backup Size:     $FINAL_SIZE"
echo "  Date:            $(date)"
echo ""
echo "To restore this backup, run:"
echo "  ./scripts/restore.sh $BACKUP_DIR/$BACKUP_NAME.tar.gz"
echo "============================================================"

exit 0