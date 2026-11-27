#!/usr/bin/env bash
# FILE: scripts/lib/env_parse.sh
# PURPOSE: Single source of truth for parsing .env values.

env_get() {
    local key="$1"
    local env_file="${2:-${ENV_FILE:-deploy/docker/.env}}"
    if [[ ! -f "$env_file" ]]; then
        return 1
    fi
    # Extract the value, strip both single and double quotes
    grep -E "^${key}=" "$env_file" | tail -1 | cut -d= -f2- | tr -d "\"'"
}

# Usage in other scripts:
#   source scripts/lib/env_parse.sh
#   DYNAMO_API_KEY=$(env_get DYNAMO_API_KEY)