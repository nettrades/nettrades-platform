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
#   ./backup.sh [--output-dir /path/to/backups] [--remote] [--auto]
#
# NEW (2026-11):
#   --remote  Upload the compressed archive to BACKUP_REPOSITORY via restic.
#             Requires BACKUP_REPOSITORY and BACKUP_PASSWORD to be set in
#             .env, and restic to be installed on the host.
#             If BACKUP_REPOSITORY is empty, --remote is a no-op (warning).
#
# RESTORE:
#   See restore.sh for restoring from a backup.
#
# EXAMPLES:
#   ./backup.sh                          # Local backup only
#   ./backup.sh --remote                 # Local + upload to BACKUP_REPOSITORY
#   ./backup.sh --output-dir /mnt/backup # Custom local directory
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
REMOTE=false               # NEW

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
        --remote)          # NEW
            REMOTE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--output-dir /path/to/backups] [--remote] [--auto]"
            echo "  --output-dir   Directory to store backups (default: ~/.nettrades/backups)"
            echo "  --remote       Upload to BACKUP_REPOSITORY via restic"
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
if ! docker_compose -f deploy/docker/docker-compose.yaml ps &>/dev/null; then
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

if docker_compose -f deploy/docker/docker-compose.yaml ps postgres &>/dev/null; then
    docker_compose -f deploy/docker/docker-compose.yaml exec -T postgres pg_dumpall -U odoo > "$BACKUP_PATH/postgres/dumpall.sql" 2>/dev/null
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
VOLUMES=$(docker_compose -f deploy/docker/docker-compose.yaml config --volumes 2>/dev/null | sort -u)

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

# Back up bind-mounted data
for binddir in odoo-data dynamo-data; do
    if [[ -d "deploy/docker/$binddir" ]]; then
        tar czf "$BACKUP_PATH/config/bind-${binddir}.tar.gz" \
            -C deploy/docker "$binddir" 2>/dev/null
        log_success "  $binddir (bind mount) backed up"
    fi
done

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
Docker Compose Version: $(docker_compose version 2>/dev/null || echo "N/A")
PostgreSQL Version: $(docker_compose -f deploy/docker/docker-compose.yaml exec -T postgres psql -U odoo -c "SELECT version();" 2>/dev/null | head -1 || echo "N/A")

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
# 7. Write Prometheus metric (NEW)
# -----------------------------------------------------------------------------
# The metric is written on every successful local backup so the
# BackupTooOld alert fires when backups stop working, regardless of
# whether off-host upload is enabled.
METRIC_DIR="$PROJECT_ROOT/deploy/docker/node-exporter-textfile"
mkdir -p "$METRIC_DIR"
echo "nettrades_backup_last_success_timestamp $(date +%s)" > "$METRIC_DIR/nettrades_backup.prom"
log_info "Prometheus metric written to $METRIC_DIR/nettrades_backup.prom"

# -----------------------------------------------------------------------------
# 8. Upload to remote (NEW — only when --remote is passed)
# -----------------------------------------------------------------------------
if [[ "$REMOTE" == true ]]; then
    log_step "Uploading to remote backup repository..."

    # Load .env to pick up BACKUP_REPOSITORY and BACKUP_PASSWORD.
    ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"
    if [[ -f "$ENV_FILE" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
    fi

    if [[ -z "${BACKUP_REPOSITORY:-}" ]]; then
        log_warning "BACKUP_REPOSITORY is not set in .env — skipping remote upload."
        log_info "Set BACKUP_REPOSITORY and BACKUP_PASSWORD in .env to enable off-host backup."
    elif [[ -z "${BACKUP_PASSWORD:-}" ]]; then
        log_error "BACKUP_PASSWORD is not set in .env — cannot encrypt remote backup."
        exit 1
    elif ! command -v restic &>/dev/null; then
        log_error "restic is not installed. Install it with: sudo apt install restic"
        exit 1
    else
        export RESTIC_REPOSITORY="$BACKUP_REPOSITORY"
        export RESTIC_PASSWORD="$BACKUP_PASSWORD"

        # Initialise on first use.
        if ! restic snapshots &>/dev/null; then
            log_info "Initialising restic repository: $RESTIC_REPOSITORY"
            if ! restic init; then
                log_error "restic init failed. Check BACKUP_REPOSITORY and credentials."
                exit 1
            fi
        fi

        log_info "Uploading $BACKUP_NAME.tar.gz..."
        if restic backup \
            --tag "nettrades" \
            --tag "date=$(date +%Y-%m-%d)" \
            "$BACKUP_DIR/$BACKUP_NAME.tar.gz"; then
            log_success "Remote upload complete"
        else
            log_error "restic backup failed. The local archive is intact."
            exit 1
        fi

        # Retention policy: 7 daily, 4 weekly, 12 monthly.
        if restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune; then
            log_success "Retention policy applied"
        else
            log_warning "restic forget failed — retention not applied"
        fi
    fi
fi

# -----------------------------------------------------------------------------
# 9. Rotate old local backups (keep last 30 days)
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
# 10. Display summary
# -----------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Backup Complete!"
echo "============================================================"
echo "  Backup Location: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
echo "  Backup Size:     $FINAL_SIZE"
echo "  Date:            $(date)"
if [[ "$REMOTE" == true ]] && [[ -n "${BACKUP_REPOSITORY:-}" ]]; then
    echo "  Remote:          $BACKUP_REPOSITORY"
fi
echo ""
echo "To restore this backup, run:"
echo "  ./scripts/restore.sh $BACKUP_DIR/$BACKUP_NAME.tar.gz"
echo "============================================================"

exit 0