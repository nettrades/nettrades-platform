#!/bin/bash
# =============================================================================
# FILE: scripts/install-modules.sh
# =============================================================================
# PURPOSE:
#   Installs all NETTRADES Odoo modules in the correct dependency order.
#   The script runs inside the Odoo container using docker compose exec.
#
#   It is idempotent and can be re-run safely. With --upgrade, it upgrades
#   existing modules; with --force, it reinstalls even if already installed.
#
# USAGE:
#   ./install-modules.sh [--force] [--upgrade] [--auto] [--verbose] [--help]
#                        [--modules=module1,module2,...]
#
# OPTIONS:
#   --force        Reinstall modules even if already installed
#   --upgrade      Upgrade existing modules to the latest version
#   --auto         Non-interactive; never prompt, always continue on failure
#   --verbose, -v  Show every command before executing it (set -x)
#   --modules=a,b  Override the module list (comma-separated)
#   --help, -h     Show this help message
#
# UPDATES (2026-09):
#   - ROBUSTNESS: Every docker/curl command is wrapped in a timeout.
#   - ROBUSTNESS: All docker exec calls redirect stdin from /dev/null to
#     prevent them from hanging waiting for input.
#   - VISIBILITY: Numbered STEP banners, per-command elapsed time, and a
#     live log file so the operator always knows where the script is.
#   - VISIBILITY: Auto-dumps the last 30 lines of the Odoo container log
#     whenever a module fails or times out.
#   - FIXED: Uses `set -uo pipefail` (dropped -e) so we can handle errors
#     explicitly and print diagnostic info before exiting.
#
# UPDATES (2026-11-16):
#   - AUTO-RECOVERY (STEP 6): if the Odoo base schema is missing (e.g. after
#     `docker volume rm postgres_data`), install `base` automatically rather
#     than exiting with a "run this command manually" message. This makes
#     `install-modules.sh --auto` self-healing on a fresh or wiped database.
#   - SKIP-ALREADY-INSTALLED: in --auto mode (without --force or --upgrade),
#     modules already in state='installed' are skipped. A healthy re-run now
#     takes ~5 s instead of ~90 s, and the summary reports both counts.
#   - SQL CONSTRAINTS WARNING: Odoo 19 emits
#         "Model attribute '_sql_constraints' is no longer supported"
#     on every module that still uses the old API. This script now surfaces
#     that as a one-line WARN per module (once), so the operator sees the
#     real data-integrity consequence rather than a wall of grey text.
#   - HELP TEXT: widened the `sed` range so `--help` shows the full block,
#     including the new options.
# =============================================================================

set -uo pipefail
# Note: we deliberately DO NOT use `set -e`. We want to catch each failure
# and print diagnostics rather than exiting silently.

stdbuf -oL -eL true 2>/dev/null || true

# -----------------------------------------------------------------------------
# Locate project root and load env
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"
COMMON_SH="$SCRIPT_DIR/lib/common.sh"

if [ ! -f "$ENV_FILE" ]; then
    echo "FATAL: .env not found at $ENV_FILE"
    exit 1
fi

# -----------------------------------------------------------------------------
# Parse arguments (do this BEFORE sourcing common.sh in case it prompts)
# -----------------------------------------------------------------------------
FORCE=false
UPGRADE=false
AUTO=false
VERBOSE=false
MODULES_LIST=""

for arg in "$@"; do
    case $arg in
        --force)    FORCE=true ;;
        --upgrade)  UPGRADE=true ;;
        --auto)     AUTO=true ;;
        --verbose|-v) VERBOSE=true ;;
        --modules=*) MODULES_LIST="${arg#--modules=}" ;;
        --help|-h)
            sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

if [ "$VERBOSE" = true ]; then
    set -x
fi

# -----------------------------------------------------------------------------
# Set up log file (tee everything)
# -----------------------------------------------------------------------------
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/install-modules-$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

# -----------------------------------------------------------------------------
# Colours
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

STEP_COUNTER=0
SCRIPT_START_TS=$(date +%s)

timestamp() { date '+%H:%M:%S'; }
elapsed_since() { echo $(( $(date +%s) - $1 )); }

log_info()    { echo -e "${BLUE}[$(timestamp)] [INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[$(timestamp)] [OK]${NC}      $*"; }
log_warning() { echo -e "${YELLOW}[$(timestamp)] [WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[$(timestamp)] [ERROR]${NC}   $*"; }
log_debug()   { [ "$VERBOSE" = true ] && echo -e "${CYAN}[$(timestamp)] [DEBUG]${NC}   $*"; }

step() {
    STEP_COUNTER=$((STEP_COUNTER + 1))
    echo ""
    echo -e "${MAGENTA}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${MAGENTA}${BOLD}  STEP ${STEP_COUNTER}: $*${NC}"
    echo -e "${MAGENTA}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
}

# -----------------------------------------------------------------------------
# Robust command runner
#   run_cmd <description> <timeout_secs> <command...>
# Returns:
#   0  = success
#   124= timed out
#   >0 = failed with that exit code
# -----------------------------------------------------------------------------
run_cmd() {
    local description="$1"
    local timeout_secs="$2"
    shift 2

    local start_ts
    start_ts=$(date +%s)

    log_info "▶ ${description}"
    log_debug "  Timeout: ${timeout_secs}s"
    log_debug "  Command: $*"

    # </dev/null ensures the wrapped command cannot block waiting for stdin
    if timeout "${timeout_secs}s" "$@" </dev/null; then
        local elapsed
        elapsed=$(elapsed_since "$start_ts")
        log_success "✓ ${description} (${elapsed}s)"
        return 0
    else
        local rc=$?
        local elapsed
        elapsed=$(elapsed_since "$start_ts")
        if [ "$rc" -eq 124 ]; then
            log_error "✗ ${description} TIMED OUT after ${timeout_secs}s (waited ${elapsed}s)"
        else
            log_error "✗ ${description} failed with exit code ${rc} (${elapsed}s)"
        fi
        return "$rc"
    fi
}

# -----------------------------------------------------------------------------
# On any unexpected exit, print a breadcrumb so the operator knows where
# -----------------------------------------------------------------------------
CURRENT_STEP_DESC="startup"
trap 'rc=$?; log_error "Script exited unexpectedly (rc=$rc) during: ${CURRENT_STEP_DESC}"; log_error "Full log: $LOG_FILE"; exit $rc' ERR

# =============================================================================
# HEADER
# =============================================================================
echo -e "${GREEN}${BOLD}"
cat <<'BANNER'
  _   _ _____ _____ _____ ____      _    ____  _____ ____
 | \ | | ____|_   _|_   _|  _ \    / \  |  _ \| ____/ ___|
 |  \| |  _|   | |   | | | |_) |  / _ \ | | | |  _| \___ \
 | |\  | |___  | |   | | |  _ <  / ___ \| |_| | |___ ___) |
 |_| \_|_____| |_|   |_| |_| \_\/_/   \_\____/|_____|____/
BANNER
echo -e "${NC}"
echo -e "${GREEN}NETTRADES.AI – Odoo Module Installation${NC}"
echo -e "Log file: ${CYAN}${LOG_FILE}${NC}"
echo -e "Options:  FORCE=${FORCE} UPGRADE=${UPGRADE} AUTO=${AUTO} VERBOSE=${VERBOSE}"
echo ""

# =============================================================================
# STEP 1: Load environment
# =============================================================================
CURRENT_STEP_DESC="Load environment"
step "Load environment variables"
set -a
if ! source "$ENV_FILE" </dev/null; then
    log_error "Failed to source $ENV_FILE"
    exit 1
fi
log_success "Loaded $ENV_FILE"

if [ -f "$COMMON_SH" ]; then
    if ! source "$COMMON_SH" </dev/null; then
        log_warning "Failed to source common.sh (continuing anyway)"
    else
        # Wrap read_feature_flags with a timeout in case it prompts interactively
        if declare -F read_feature_flags >/dev/null; then
            if ! timeout 10s bash -c "source '$COMMON_SH' </dev/null; read_feature_flags </dev/null"; then
                log_warning "read_feature_flags() timed out or failed; continuing with defaults"
            else
                # Source again in this shell to pick up the exported vars
                source "$COMMON_SH" </dev/null 2>/dev/null || true
            fi
        fi
    fi
else
    log_warning "common.sh not found at $COMMON_SH; feature flags not loaded"
fi
set +a

# =============================================================================
# STEP 2: Activate virtual environment (optional)
# =============================================================================
CURRENT_STEP_DESC="Activate venv"
step "Activate Python virtual environment (optional)"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
if [ -f "$VENV_DIR/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    log_success "Activated venv: $VENV_DIR"
else
    log_info "No venv at $VENV_DIR – skipping (running inside Odoo container)"
fi

# =============================================================================
# STEP 3: Change to docker compose dir and verify compose is available
# =============================================================================
CURRENT_STEP_DESC="Check docker compose"
step "Verify docker compose is available"
cd "$PROJECT_ROOT/deploy/docker" || { log_error "Cannot cd to deploy/docker"; exit 1; }

if ! run_cmd "docker compose version" 10 docker compose version; then
    log_error "docker compose not available"
    exit 1
fi

# =============================================================================
# STEP 4: Verify Odoo container is running
# =============================================================================
CURRENT_STEP_DESC="Check Odoo container"
step "Verify Odoo container is running"
CONTAINER_LIST=$(timeout 10 docker ps --format '{{.Names}}' </dev/null 2>/dev/null || echo "")
if echo "$CONTAINER_LIST" | grep -q odoo; then
    log_success "Odoo container is running"
    log_info "Containers: $(echo "$CONTAINER_LIST" | tr '\n' ' ')"
else
    log_error "Odoo container is NOT running"
    log_info "Start it with: cd $PROJECT_ROOT/deploy/docker && docker compose up -d"
    exit 1
fi

# =============================================================================
# STEP 5: Verify PostgreSQL is responsive
# =============================================================================
CURRENT_STEP_DESC="Ping PostgreSQL"
step "Verify PostgreSQL is responsive"
if ! run_cmd "pg_isready" 15 docker compose exec -T postgres pg_isready -U odoo; then
    log_error "PostgreSQL is not ready"
    log_info "Recent postgres logs:"
    timeout 10 docker compose logs --tail=30 postgres </dev/null || true
    exit 1
fi

# =============================================================================
# STEP 6: Verify Odoo DB is initialised (ir_module_module table exists)
# -----------------------------------------------------------------------------
# AUTO-RECOVERY (2026-11-16): if the schema is missing — which happens after
# `docker volume rm postgres_data` or on a fresh DB — install `base` directly
# rather than exiting with a "run this command" message. This keeps
# `install-modules.sh --auto` a one-command fix for the whole stack.
# =============================================================================
CURRENT_STEP_DESC="Check Odoo DB initialised"
step "Verify Odoo database is initialised"
DB_CHECK=$(timeout 20 docker compose exec -T postgres \
    psql -U odoo -d odoo -tAc "SELECT to_regclass('public.ir_module_module');" \
    </dev/null 2>/dev/null | tr -d '[:space:]' || echo "")

if [ "$DB_CHECK" = "ir_module_module" ]; then
    log_success "Odoo database is initialised"
else
    log_warning "Odoo database is NOT initialised (got: '$DB_CHECK')"
    log_info "Auto-installing base modules (safe, idempotent, ~90 s)..."

    PG_PASS_TMP=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" | cut -d= -f2- | tr -d "\"'")
    if ! run_cmd "install base modules" 300 docker compose run --rm \
        -e PGHOST=postgres -e PGUSER=odoo -e PGPASSWORD="$PG_PASS_TMP" \
        -e PGDATABASE=odoo \
        odoo odoo -d odoo \
        --db_host=postgres --db_port=5432 \
        --db_user=odoo --db_password="$PG_PASS_TMP" \
        -i base --stop-after-init --log-level=warn; then
        log_error "Auto-recovery failed. Inspect the log above."
        log_info "Full log: $LOG_FILE"
        exit 1
    fi

    # Re-verify
    DB_CHECK=$(timeout 20 docker compose exec -T postgres \
        psql -U odoo -d odoo -tAc "SELECT to_regclass('public.ir_module_module');" \
        </dev/null 2>/dev/null | tr -d '[:space:]' || echo "")
    if [ "$DB_CHECK" != "ir_module_module" ]; then
        log_error "Base install completed but ir_module_module still missing"
        exit 1
    fi
    log_success "Base modules installed — continuing with module install"
fi

# =============================================================================
# STEP 7: (Optional) Restart Odoo in force mode
# =============================================================================
if [ "$FORCE" = true ]; then
    CURRENT_STEP_DESC="Restart Odoo (--force)"
    step "Restart Odoo to reload modules (--force)"
    if run_cmd "docker compose restart odoo" 120 docker compose restart odoo; then
        log_info "Waiting 5s for Odoo to settle..."
        sleep 5
    else
        log_warning "Restart failed or timed out – continuing anyway"
    fi
fi

# =============================================================================
# STEP 8: Wait for Odoo HTTP to respond
# =============================================================================
CURRENT_STEP_DESC="Wait for Odoo HTTP"
step "Wait for Odoo HTTP /web/health to respond"
ODOO_READY=false
for i in $(seq 1 30); do
    if curl -s --connect-timeout 2 --max-time 4 -f -o /dev/null \
        http://localhost:8069/web/health 2>/dev/null; then
        log_success "Odoo HTTP is ready (after ${i} attempts)"
        ODOO_READY=true
        break
    fi
    printf "."
    sleep 2
done
echo ""

if [ "$ODOO_READY" = false ]; then
    log_warning "Odoo did not respond within 60s"
    log_info "Recent Odoo logs:"
    timeout 10 docker compose logs --tail=30 odoo </dev/null || true
    log_warning "Continuing anyway – module install may fail"
fi

# =============================================================================
# STEP 9: Validate view files in container
# =============================================================================
CURRENT_STEP_DESC="Validate module files"
step "Validate Odoo module view files inside the container"

MODULE_DIRS=$(timeout 60 docker compose exec -T odoo \
    find /mnt/extra-addons -maxdepth 1 -type d -name "nettrades_*" \
    </dev/null 2>/dev/null || echo "")

if [ -z "$MODULE_DIRS" ]; then
    log_warning "No nettrades_* modules found or find timed out"
else
    log_info "Found modules:"
    echo "$MODULE_DIRS" | sed 's|/mnt/extra-addons/|  - |' | tr -d '\r'
    log_success "Module file validation complete"
fi

# =============================================================================
# STEP 10: Build module list
# =============================================================================
CURRENT_STEP_DESC="Build module list"
step "Build list of modules to install"

# =============================================================================
# MODULE INSTALLATION ORDER
# =============================================================================
# Order matters! Odoo installs modules in the order given, and a module's
# dependencies must be installed BEFORE it. The order below is:
#
#   1. llm_openai                — Apexive service modules (populates the
#                                  "Service" dropdown on llm.provider)
#   2. nettrades_core            — no NETTRADES dependencies (base + mail only)
#   3. nettrades_gpu_admin       — depends on nettrades_core
#   4. nettrades_bridge          — depends on nettrades_core
#   5. nettrades_llm_config      — depends on nettrades_core
#   6. nettrades_queue           — depends on nettrades_core
#   7. nettrades_notifications   — depends on nettrades_core
#   8. nettrades_fairness        — depends on nettrades_core
#   9. nettrades_data_collection — depends on nettrades_core
#  10. nettrades_self_improving  — depends on nettrades_core
#  11. nettrades_ask_someone     — depends on nettrades_core (and queue)
#  12. nettrades_good_answer     — depends on nettrades_core (and ask_someone)
#  13. nettrades_wireguard       — depends on nettrades_core
#  14. nettrades_onboarding      — depends on nettrades_core (and website)
# =============================================================================

MODULES=(
    # Apexive llm service modules. These add the values that appear in
    # the "Service" dropdown on llm.provider. Without at least one of
    # these, the field has no valid choices and Odoo refuses to save a
    # provider record. llm_openai is the right choice for llama.cpp and
    # vLLM, both of which speak the OpenAI-compatible protocol.
    "llm_openai"

    # NETTRADES business modules, in dependency order.
    "nettrades_core"
    "nettrades_queue"
    "nettrades_notifications"
    "nettrades_llm_config"
    "nettrades_gpu_admin"
    "nettrades_bridge"
    "nettrades_ask_someone"
    "nettrades_good_answer"
    "nettrades_fairness"
    "nettrades_data_collection"
    "nettrades_self_improving"
    "nettrades_wireguard"
    "nettrades_onboarding"
)

if [[ -n "$MODULES_LIST" ]]; then
    IFS=',' read -ra MODULES <<< "$MODULES_LIST"
    log_info "Overriding with provided module list"
fi

log_info "Modules to install (${#MODULES[@]}):"
for m in "${MODULES[@]}"; do
    echo -e "  ${CYAN}→${NC} $m"
done

# =============================================================================
# STEP 11: Query current module state (for skip-already-installed)
# =============================================================================
CURRENT_STEP_DESC="Query installed modules"
step "Query installed module states"

INSTALLED_MODULES_RAW=$(timeout 15 docker compose exec -T postgres \
    psql -U odoo -d odoo -tAc \
    "SELECT name FROM ir_module_module WHERE name IN ('$(IFS="','"; echo "${MODULES[*]}")') AND state='installed';" \
    </dev/null 2>/dev/null | tr -d '\r' || echo "")

# Build an associative array of already-installed module names.
declare -A INSTALLED=()
while IFS= read -r line; do
    [ -z "$line" ] && continue
    INSTALLED["$line"]=1
done <<< "$INSTALLED_MODULES_RAW"

INSTALLED_COUNT=0
PENDING_COUNT=0
for m in "${MODULES[@]}"; do
    if [[ -n "${INSTALLED[$m]:-}" ]]; then
        INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
    else
        PENDING_COUNT=$((PENDING_COUNT + 1))
    fi
done

log_info "Already installed: ${INSTALLED_COUNT}/${#MODULES[@]}"
log_info "To be processed:   ${PENDING_COUNT}/${#MODULES[@]}"

# =============================================================================
# STEP 12: Install each module
# =============================================================================
CURRENT_STEP_DESC="Install modules"
step "Install modules (one at a time, 120s timeout each)"

install_module() {
    local module="$1"
    local action="install"
    local flag="-i"

    if [ "$UPGRADE" = true ]; then
        action="upgrade"
        flag="-u"
    elif [ "$FORCE" = true ]; then
        action="reinstall"
        flag="-i"
    fi

    local start_ts
    start_ts=$(date +%s)

    log_info "┌─ ${action^}ing: ${BOLD}${module}${NC}"
    log_info "│  Starting at $(timestamp)..."

    cd "$PROJECT_ROOT/deploy/docker" || return 1

    # 120-second hard timeout. < /dev/null prevents hangs on stdin.
    # Capture output to a temp file so we can inspect it for silent
    # failures. Odoo returns exit code 0 when a module is skipped due to
    # a bad manifest — "not installable, skipped" is a WARNING, not a
    # hard error. Without this check, the script reports success when the
    # module was never installed.
    local out_file
    out_file=$(mktemp)

    if stdbuf -oL -eL timeout 120s docker compose exec -T \
        -e PGPASSWORD="$POSTGRES_PASSWORD" \
        odoo odoo \
        -d odoo \
        --db_host=postgres \
        --db_port=5432 \
        --db_user=odoo \
        --db_password="$POSTGRES_PASSWORD" \
        "$flag" "$module" \
        --stop-after-init </dev/null 2>&1 | tee "$out_file"; then

        # Even on exit code 0, check for signals that mean the module was
        # not actually installed.
        if grep -qE 'manifest not found|not installable, skipped|inconsistent states|Failed to load registry|ParseError|CRITICAL' "$out_file"; then
            log_error "└─ ✗ ${module} was skipped or failed silently (exit code was 0)"
            log_info "│  Matching lines:"
            grep -E 'manifest not found|not installable, skipped|inconsistent states|Failed to load registry|ParseError|CRITICAL' "$out_file" \
                | sed 's/^/│    /' || true
            rm -f "$out_file"
            cd "$PROJECT_ROOT"
            return 1
        fi

        # Detect the Odoo 19 _sql_constraints deprecation warning. These
        # constraints are NOT being enforced. Surface it once per module
        # so the operator knows data-integrity constraints are missing.
        if grep -q "Model attribute '_sql_constraints' is no longer supported" "$out_file"; then
            log_warning "└─ ⚠ ${module}: legacy '_sql_constraints' NOT applied by Odoo 19"
            log_warning "│  These constraints are silently ignored. Migrate to"
            log_warning "│  'models.Constraint(...)' class attributes. See DECISIONS.md."
        fi

        local elapsed
        elapsed=$(elapsed_since "$start_ts")
        log_success "└─ ✓ ${module} ${action}ed successfully (${elapsed}s)"
        rm -f "$out_file"
        cd "$PROJECT_ROOT"
        return 0
    else
        local rc=$?
        local elapsed
        elapsed=$(elapsed_since "$start_ts")
        if [ "$rc" -eq 124 ]; then
            log_error "└─ ✗ ${module} TIMED OUT after 120s"
        else
            log_error "└─ ✗ ${module} ${action} failed (rc=${rc}, ${elapsed}s)"
        fi

        # Dump recent Odoo logs to help diagnose
        log_info "│  Recent Odoo logs (last 20 lines):"
        timeout 15 docker compose logs --tail=20 odoo </dev/null 2>&1 \
            | sed 's/^/│    /' || true

        cd "$PROJECT_ROOT"
        return $rc
    fi
}

FAILED_MODULES=()
SKIPPED_MODULES=()
INSTALLED_LIST=()
TOTAL_MODULES=${#MODULES[@]}
CURRENT=0

if [ "$TOTAL_MODULES" -eq 0 ]; then
    log_warning "No modules to install"
    exit 0
fi

for module in "${MODULES[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo ""
    echo -e "${YELLOW}━━━ Module ${CURRENT}/${TOTAL_MODULES}: ${BOLD}${module}${NC} ${YELLOW}━━━${NC}"

    # Skip-already-installed optimisation: only when --auto and neither
    # --force nor --upgrade. This makes a re-run of a healthy system
    # complete in seconds instead of re-loading the registry 14 times.
    if [[ "$AUTO" == "true" ]] \
       && [[ "$FORCE" != "true" ]] \
       && [[ "$UPGRADE" != "true" ]] \
       && [[ -n "${INSTALLED[$module]:-}" ]]; then
        log_info "└─ ⊝ ${module} already installed — skipping (--auto without --force/--upgrade)"
        SKIPPED_MODULES+=("$module")
        continue
    fi

    if install_module "$module"; then
        INSTALLED_LIST+=("$module")
    else
        FAILED_MODULES+=("$module")

        if [ "$AUTO" != true ]; then
            log_warning "Module '$module' failed."
            printf "Continue with remaining modules? (y/N, 15s timeout): "
            if ! read -r -t 15 continue_anyway; then
                log_info "No response within 15s – continuing automatically"
                continue_anyway="y"
            fi
            if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
                log_error "Aborting on user request"
                break
            fi
        fi
    fi
done

# =============================================================================
# SUMMARY
# =============================================================================
# This block exits with code 1 when any module failed. The exit code is
# the source of truth:
#   0 -> every module installed successfully (or was already installed)
#   1 -> one or more modules failed (the caller should stop and investigate)
# =============================================================================
TOTAL_ELAPSED=$(elapsed_since "$SCRIPT_START_TS")

echo ""
echo -e "${MAGENTA}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}${BOLD}  INSTALLATION SUMMARY${NC}"
echo -e "${MAGENTA}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
echo -e "  Total modules:    ${#MODULES[@]}"
echo -e "  Newly installed:  ${#INSTALLED_LIST[@]}"
echo -e "  Skipped (already):${#SKIPPED_MODULES[@]}"
echo -e "  Failed modules:   ${#FAILED_MODULES[@]}"
echo -e "  Total time:       ${TOTAL_ELAPSED}s"
echo -e "  Full log:         ${CYAN}${LOG_FILE}${NC}"
echo ""

if [ ${#FAILED_MODULES[@]} -eq 0 ]; then
    log_success "ALL MODULES INSTALLED SUCCESSFULLY"
    echo ""
    log_info "Next steps:"
    echo "  1. Configure fairness:  Settings → Technical → Fairness → Global Configuration"
    echo "  2. Run an audit:        Settings → Technical → Fairness → Dashboard"
    echo "  3. GPU tokens:          GPU → Registration Tokens"
    echo "  4. Bridge routing:      Settings → Technical → Bridge → Global Configuration"
    echo ""
    log_info "To wire the hub for spokes, run: ./scripts/recover-hub.sh"
    exit 0
else
    log_error "The following modules failed or timed out:"
    for m in "${FAILED_MODULES[@]}"; do
        echo -e "  ${RED}✗${NC} $m"
    done
    echo ""
    log_info "Diagnose the first failure by re-running a single module with verbose logs:"
    echo "  cd $PROJECT_ROOT/deploy/docker"
    echo "  docker compose exec odoo odoo -d odoo -i <module_name> --stop-after-init --log-level=debug"
    echo ""
    log_info "Full log: $LOG_FILE"
    exit 1
fi