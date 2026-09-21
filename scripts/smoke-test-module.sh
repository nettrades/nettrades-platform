#!/bin/bash
# =============================================================================
# FILE: scripts/smoke-test-module.sh
# =============================================================================
# PURPOSE:
#   Runtime smoke test for a NETTRADES Odoo module.
#
#   Answers the question: "the module installed, but does it actually work?"
#   Complements three earlier-stage checks:
#     - audit-views.py            → do views reference real fields?
#     - prepare-odoo-addons.sh    → do manifests resolve?
#     - install-modules.sh        → does the module load?
#   This script checks that the module RUNS at runtime.
#
# USAGE:
#   ./scripts/smoke-test-module.sh [MODULE] [options]
#
# OPTIONS:
#   --keep            Do not delete the test cycle record
#   --verbose, -v     Print extra diagnostic detail
#   --quiet, -q       Minimal output (one line per check)
#   --no-color        Disable ANSI colors (for logs / CI)
#   --timeout SECS    Abort if the shell takes longer (default: 60)
#   --help, -h        Show this help
#
# EXIT CODES:
#   0 - module verified (or SKIPPED because it is not installed)
#   1 - one or more checks failed
#   2 - could not reach Odoo (docker / DB problem, or module missing)
#   3 - the shell command timed out
#
#
#
# Default: test nettrades_self_improving
#./scripts/smoke-test-module.sh
#
# Test a specific module
#./scripts/smoke-test-module.sh nettrades_fairness
#
# Keep the test cycle for inspection
#./scripts/smoke-test-module.sh --keep
#
# Quiet mode for CI (one line of output on success)
#./scripts/smoke-test-module.sh --quiet
#
# No colors (for piping to a log file)
#./scripts/smoke-test-module.sh --no-color
#
# Longer timeout for slow environments
#./scripts/smoke-test-module.sh --timeout 120
#
# Get help
#./scripts/smoke-test-module.sh --help
# =============================================================================

set -uo pipefail

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
MODULE="nettrades_self_improving"
KEEP_DATA=false
VERBOSE=false
QUIET=false
USE_COLOR=true
TIMEOUT_SECS=60

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
show_help() {
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)         KEEP_DATA=true; shift ;;
        --verbose|-v)   VERBOSE=true; shift ;;
        --quiet|-q)     QUIET=true; shift ;;
        --no-color)     USE_COLOR=false; shift ;;
        --timeout)      TIMEOUT_SECS="$2"; shift 2 ;;
        --help|-h)      show_help; exit 0 ;;
        --*)            echo "Unknown flag: $1 (try --help)" >&2; exit 2 ;;
        *)              MODULE="$1"; shift ;;
    esac
done

# -----------------------------------------------------------------------------
# Colour setup (respects --no-color and non-tty stdout)
# -----------------------------------------------------------------------------
if [ "$USE_COLOR" = true ] && [ -t 1 ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    YELLOW=$'\033[0;33m'
    BLUE=$'\033[0;34m'
    CYAN=$'\033[0;36m'
    BOLD=$'\033[1m'
    NC=$'\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; BOLD=''; NC=''
fi

# -----------------------------------------------------------------------------
# Locate project root and .env
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"

if [ ! -f "$ENV_FILE" ]; then
    printf '%b\n' "${RED}FATAL${NC}: .env not found at $ENV_FILE" >&2
    exit 2
fi

# Extract POSTGRES_PASSWORD (single or double quoted, or bare)
POSTGRES_PASSWORD=$(
    grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" \
    | head -1 \
    | cut -d= -f2- \
    | sed -E "s/^['\"]//; s/['\"]$//"
)

if [ -z "$POSTGRES_PASSWORD" ]; then
    printf '%b\n' "${RED}FATAL${NC}: could not extract POSTGRES_PASSWORD from $ENV_FILE" >&2
    exit 2
fi

cd "$PROJECT_ROOT/deploy/docker" || exit 2

# -----------------------------------------------------------------------------
# Build the Python payload
# -----------------------------------------------------------------------------
# Values are passed via environment variables, not templated into the
# heredoc, so no shell quoting can leak into Python source.
# -----------------------------------------------------------------------------
PAYLOAD_FILE=$(mktemp)
trap 'rm -f "$PAYLOAD_FILE"' EXIT

cat > "$PAYLOAD_FILE" <<'PYEOF'
import os
import sys
import traceback
from collections import Counter

MODULE       = os.environ['TEST_MODULE']
KEEP_DATA    = os.environ.get('TEST_KEEP_DATA', 'false') == 'true'
VERBOSE      = os.environ.get('TEST_VERBOSE', 'false') == 'true'
QUIET        = os.environ.get('TEST_QUIET', 'false') == 'true'

# ANSI (empty strings if colors are off)
C_RED     = os.environ.get('TEST_C_RED',     '')
C_GREEN   = os.environ.get('TEST_C_GREEN',   '')
C_YELLOW  = os.environ.get('TEST_C_YELLOW',  '')
C_BLUE    = os.environ.get('TEST_C_BLUE',    '')
C_CYAN    = os.environ.get('TEST_C_CYAN',    '')
C_BOLD    = os.environ.get('TEST_C_BOLD',    '')
C_NC      = os.environ.get('TEST_C_NC',      '')

checks_passed = 0
checks_failed = 0
failed_labels = []
skipped = False

def pass_(label):
    global checks_passed
    checks_passed += 1
    if not QUIET:
        print(f"  {C_GREEN}PASS{C_NC}  {label}")

def fail_(label, detail=""):
    global checks_failed
    checks_failed += 1
    failed_labels.append(label)
    msg = f"  {C_RED}FAIL{C_NC}  {label}"
    if detail:
        msg += f" {C_YELLOW}({detail}){C_NC}"
    print(msg)

def check(label, condition, detail=""):
    if condition:
        pass_(label)
    else:
        fail_(label, detail)

def info(msg):
    if not QUIET:
        print(f"        {C_CYAN}{msg}{C_NC}")

def section(title):
    if not QUIET:
        print()
        print(f"  {C_BOLD}{title}{C_NC}")

def bail_skip(reason):
    global skipped
    skipped = True
    if not QUIET:
        print()
        print(f"  {C_YELLOW}SKIP{C_NC}  {reason}")
    sys.exit(0)

# =============================================================================
# Header
# =============================================================================
if not QUIET:
    print()
    print("=" * 70)
    print(f"Smoke test: {C_BOLD}{MODULE}{C_NC}")
    print("=" * 70)

# =============================================================================
# Check 1 — module exists and is installed
# =============================================================================
mod = env['ir.module.module'].search([('name', '=', MODULE)], limit=1)

if not mod:
    fail_(f"module '{MODULE}' exists in ir.module.module", "not found")
    print()
    print(f"  {C_RED}Module not found. Is the name spelled correctly?{C_NC}")
    sys.exit(1)

pass_(f"module '{MODULE}' exists in ir.module.module")

if mod.state == 'uninstalled':
    bail_skip(
        f"module '{MODULE}' is present but not installed. "
        f"Install it with:\n"
        f"            ./scripts/install-modules.sh --modules={MODULE}"
    )

if mod.state != 'installed':
    fail_(f"module state is 'installed'", f"got '{mod.state}'")
    sys.exit(1)

pass_(f"module state is 'installed'")

# =============================================================================
# Check 2 — module owns data (menus, actions, views)
# =============================================================================
section("Module data ownership")
data = env['ir.model.data'].search([('module', '=', MODULE)])
owned_by_model = Counter(data.mapped('model'))

if not data:
    fail_("module owns no ir.model.data records",
          "nothing was loaded — check the manifest 'data' list")
else:
    pass_(f"module owns {len(data)} XML data records")
    if VERBOSE or not QUIET:
        for model_name, count in sorted(owned_by_model.items()):
            info(f"{count:>3}  {model_name}")

# Sanity: at least one menu, one action, one view
expected_kinds = {
    'ir.ui.menu':          'menus',
    'ir.actions.act_window': 'window actions',
    'ir.ui.view':          'views',
}
for model_name, human in expected_kinds.items():
    count = owned_by_model.get(model_name, 0)
    check(f"module defines at least one {human} ({count} found)", count > 0)

# =============================================================================
# Check 3 — models registered (module-specific)
# =============================================================================
EXPECTED_MODELS = {
    'nettrades_self_improving': [
        'trigger.config',
        'trigger.event',
        'training.pipeline',
        'loop.cycle',
        'loop.orchestrator',
        'self.improving.config',
    ],
    'nettrades_fairness': [
        'nettrades.fairness.config',
        'nettrades.fairness.field.config',
        'nettrades.fairness.audit',
        'nettrades.fairness.flag',
        'nettrades.fairness.evaluator',
        'nettrades.fairness.metrics',
    ],
}

models_to_check = EXPECTED_MODELS.get(MODULE, [])
if models_to_check:
    section("Model registration")
    for mname in models_to_check:
        try:
            _ = env[mname]
            pass_(f"model '{mname}' is registered")
        except KeyError:
            fail_(f"model '{mname}' is registered", "not found")

# =============================================================================
# Check 4 — module-specific functional test
# =============================================================================
if MODULE == 'nettrades_self_improving':
    section("State machine end-to-end")
    cycle = None
    try:
        if not QUIET:
            print("        Running execute_cycle()...")

        cycle = env['loop.orchestrator'].execute_cycle()
        env.cr.commit()

        if not QUIET:
            info(f"Cycle ID:     {cycle.id}")
            info(f"Final state:  {cycle.status}")
            info(f"Origin:       {cycle.origin}")
            info(f"Duration:     {cycle.duration_seconds:.2f}s")
            info(f"Episodes:     {cycle.episode_count}")

        check(
            f"cycle reached a terminal state",
            cycle.is_terminal(),
            f"got '{cycle.status}'",
        )

        if cycle.status == 'failed':
            fail_("cycle completed without error",
                  cycle.error_message or "no message")
        else:
            pass_("cycle completed without error")
            if cycle.status == 'skipped' and not QUIET:
                info("(skipped is normal when no triggers fire or no data qualifies)")
    except Exception as e:
        fail_("state machine ran without exception", str(e))
        if VERBOSE:
            traceback.print_exc()

    # -------------------------------------------------------------------------
    # Config singleton
    # -------------------------------------------------------------------------
    section("Configuration singleton")
    try:
        cfg = env['self.improving.config'].get_config()
        env.cr.commit()
        check("config singleton is readable", bool(cfg))
        count = env['self.improving.config'].search_count([])
        check("config has exactly one record", count == 1, f"got {count}")
    except Exception as e:
        fail_("config singleton is readable", str(e))

    # -------------------------------------------------------------------------
    # Provider configuration (informational, not pass/fail)
    # -------------------------------------------------------------------------
    section("Training pipeline configuration")
    try:
        pipelines = env['training.pipeline'].search([])
        if not pipelines:
            info("no training pipelines configured yet")
        else:
            for p in pipelines:
                prov = p.provider_id.name or 'none'
                model = p.base_model_id.name or 'none'
                ready = bool(p.provider_id and p.base_model_id)
                marker = f"{C_GREEN}ready{C_NC}" if ready else f"{C_YELLOW}incomplete{C_NC}"
                info(f"{p.name}: provider={prov}, model={model} [{marker}]")
    except Exception as e:
        info(f"(could not inspect pipelines: {e})")

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    if not KEEP_DATA and cycle is not None:
        try:
            cycle.unlink()
            env.cr.commit()
            if not QUIET:
                info("(cleaned up test cycle)")
        except Exception as e:
            if not QUIET:
                info(f"(cleanup warning: {e})")

# =============================================================================
# Summary
# =============================================================================
if not QUIET:
    print()
    print("=" * 70)

if checks_failed > 0:
    print(f"  {C_RED}FAILED{C_NC}: {checks_failed} check(s) failed, "
          f"{checks_passed} passed")
    for label in failed_labels:
        print(f"    - {label}")
    sys.exit(1)
else:
    print(f"  {C_GREEN}PASSED{C_NC}: all {checks_passed} check(s) passed")
    sys.exit(0)
PYEOF

# -----------------------------------------------------------------------------
# Run the payload inside the Odoo container
# -----------------------------------------------------------------------------
COLOR_ENV_ARGS=(
    -e TEST_C_RED="$RED"
    -e TEST_C_GREEN="$GREEN"
    -e TEST_C_YELLOW="$YELLOW"
    -e TEST_C_BLUE="$BLUE"
    -e TEST_C_CYAN="$CYAN"
    -e TEST_C_BOLD="$BOLD"
    -e TEST_C_NC="$NC"
)

timeout "$TIMEOUT_SECS" docker compose exec -T \
    -e PGPASSWORD="$POSTGRES_PASSWORD" \
    -e TEST_MODULE="$MODULE" \
    -e TEST_KEEP_DATA="$KEEP_DATA" \
    -e TEST_VERBOSE="$VERBOSE" \
    -e TEST_QUIET="$QUIET" \
    "${COLOR_ENV_ARGS[@]}" \
    odoo odoo shell \
    -d odoo \
    --db_host=postgres \
    --db_port=5432 \
    --db_user=odoo \
    --db_password="$POSTGRES_PASSWORD" \
    --no-http \
    < "$PAYLOAD_FILE"

RC=$?

if [ "$RC" -eq 124 ]; then
    printf '%b\n' "${RED}TIMEOUT${NC}: smoke test exceeded ${TIMEOUT_SECS}s. Increase with --timeout." >&2
    exit 3
fi

exit "$RC"