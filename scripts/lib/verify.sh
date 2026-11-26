#!/bin/bash
# =============================================================================
# FILE: scripts/lib/verify.sh
# =============================================================================
# PURPOSE:
#   Declarative verification gates. Every install phase ends with a gate
#   run. A gate is a shell command with an expected outcome. If the gate
#   fails, the phase fails loudly with the failing gate name.
#
# USAGE:
#   source scripts/lib/colors.sh     # optional; verify.sh provides defaults
#   source scripts/lib/verify.sh
#
#   # Single gate
#   verify_gate "phase_service" "six RPC sockets" \
#       "ss -ltn | grep -cE ':5005[2-7]'" "6" || exit 1
#
#   # Multiple gates in one phase
#   verify_phase "phase_service" \
#       "six RPC sockets"  "ss -ltn | grep -cE ':5005[2-7]'" "6" \
#       "port 8080 open"   "ss -ltn | grep -cE ':8080'"      "1" \
#       "master healthy"   "curl -sf http://localhost:8082/health" "exit:0"
#
# The third argument to verify_gate is a shell command. The fourth is:
#   - a plain string: compared against command stdout (whitespace-trimmed)
#   - "exit:N": command exit code must be N
#   - "contains:SUBSTRING": stdout must contain SUBSTRING
#
# FIXES (2026-11-16):
#   * verify_phase was passing the entire (name + cmd + expect) tuple as
#     a single `gate` string to verify_gate. Because verify_gate expects
#     four positional arguments (phase, name, cmd, expect), the `cmd`
#     and `expect` slots were empty and the `eval ""` probe exited 0.
#     Result: every gate silently passed regardless of the actual state.
#     verify_phase now consumes (name, cmd, expect) TRIPLES from its
#     argument list, which matches what verify_gate expects.
#   * verify_gate now protects the eval against `set -e` in the caller.
#     Previously `out=$(eval "$cmd"); rc=$?` would exit the caller under
#     `set -e` because the assignment inherited the eval's non-zero exit
#     code. The `|| rc=$?` form always succeeds, letting the caller see
#     the real probe result.
#   * The colour variables now use ${VAR:-default} so that a caller who
#     has already sourced scripts/lib/colors.sh keeps its definitions
#     (previously the unconditional assignment at the top of this file
#     overwrote them).
# =============================================================================

# Colour defaults. The `:-` form means "use this if not already set", so
# a caller that sources scripts/lib/colors.sh first keeps its definitions.
RED="${RED:-\033[0;31m}"
GREEN="${GREEN:-\033[0;32m}"
YELLOW="${YELLOW:-\033[1;33m}"
NC="${NC:-\033[0m}"

# -----------------------------------------------------------------------------
# verify_gate <phase> <name> <cmd> <expect>
# -----------------------------------------------------------------------------
# Runs <cmd> under `eval`, captures stdout+stderr, and compares against
# <expect> according to the format documented at the top of this file.
#
# Returns 0 on success, 1 on failure. Never exits the caller.
# -----------------------------------------------------------------------------
verify_gate() {
    local phase="$1"
    local name="$2"
    local cmd="$3"
    local expect="$4"

    local out rc=0
    # The `|| rc=$?` form is deliberate: under `set -e`, a bare
    # `out=$(eval "$cmd"); rc=$?` would abort the calling script when
    # the probe command legitimately returns non-zero (which is the
    # exact condition we want to measure). Assigning through `||` keeps
    # the assignment command's exit status at 0 so `set -e` does not
    # fire, while still capturing the real rc in $rc.
    out=$(eval "$cmd" 2>&1) || rc=$?

    local ok=0
    if [[ "$expect" == exit:* ]]; then
        [[ "$rc" -eq "${expect#exit:}" ]] && ok=1
    elif [[ "$expect" == contains:* ]]; then
        # -q quiet, -F fixed-string (no regex interpretation of SUBSTRING).
        printf '%s\n' "$out" | grep -qF -- "${expect#contains:}" && ok=1
    else
        # Trim all whitespace from both sides before comparing. Shell
        # command output almost always ends with a trailing newline,
        # and many probes also pad with leading spaces; stripping makes
        # scalar comparisons robust to both.
        [[ "$(printf '%s' "$out"    | tr -d '[:space:]')" == \
           "$(printf '%s' "$expect" | tr -d '[:space:]')" ]] && ok=1
    fi

    if [[ "$ok" -eq 1 ]]; then
        echo -e "  ${GREEN}✅${NC} [$phase] $name"
        return 0
    else
        echo -e "  ${RED}❌${NC} [$phase] $name (expected $expect, got rc=$rc, out=$(printf '%s' "$out" | head -1))"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# verify_phase <phase> <name1> <cmd1> <expect1> [<name2> <cmd2> <expect2> ...]
# -----------------------------------------------------------------------------
# Runs each (name, cmd, expect) triple through verify_gate. Every triple
# is independent — a failure in one does not prevent the others from
# running, and the function returns non-zero if any triple failed.
#
# The triple form is required (see FIXES above): the earlier version
# accepted a flat list of pre-formatted strings and passed each one as a
# single `gate` argument, which was silently dropped by verify_gate.
# -----------------------------------------------------------------------------
verify_phase() {
    local phase="$1"; shift

    local arg_count=$#
    if (( arg_count % 3 != 0 )); then
        echo -e "${YELLOW}verify_phase: arguments must be (name, cmd, expect) triples; got $arg_count${NC}" >&2
        echo -e "${YELLOW}  usage: verify_phase \"phase\" \"name1\" \"cmd1\" \"expect1\" ...${NC}" >&2
        return 2
    fi

    local failures=0
    while (( $# >= 3 )); do
        verify_gate "$phase" "$1" "$2" "$3" || failures=$((failures + 1))
        shift 3
    done

    if (( failures > 0 )); then
        echo -e "${RED}Phase $phase FAILED: $failures gate(s)${NC}"
        return 1
    fi
    echo -e "${GREEN}Phase $phase PASSED${NC}"
    return 0
}