#!/bin/bash
# =============================================================================
# FILE: scripts/fix-line-endings.sh
# =============================================================================
# PURPOSE:
#   Recursively convert all text files in the nettrades-platform directory
#   to Unix (LF) line endings. 
#
#   This is critical when files are copied from a Windows development PC.
#   Windows uses CRLF (\r\n), while Linux (and Python, Bash) strictly expect LF (\n).
#   If a .sh file has CRLF, bash will fail with syntax errors.
#
# USAGE:
#   cd ~/nettrades-platform
#   ./scripts/fix-line-endings.sh --force
# =============================================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

DRY_RUN=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --force) FORCE=true; shift ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--force]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  NETTRADES – Fix Line Endings${NC}"
echo -e "${BLUE}============================================================${NC}"
echo "Project root: $PROJECT_ROOT"

if ! command -v dos2unix &> /dev/null; then
    echo -e "${YELLOW}dos2unix not found. Installing...${NC}"
    if [[ "$DRY_RUN" == false ]]; then
        sudo apt update -qq && sudo apt install -y dos2unix
    else
        echo "DRY RUN: Would install dos2unix."
        exit 0
    fi
fi

# Build the find command safely
# We explicitly include .sh, .py, .xml, .env, .yaml, .json, and .md
FIND_CMD=(find "$PROJECT_ROOT" -type f \( 
    -name "*.py" -o -name "*.xml" -o -name "*.sh" -o -name "*.conf" -o 
    -name "*.cfg" -o -name "*.ini" -o -name "*.txt" -o -name "*.md" -o 
    -name "*.yml" -o -name "*.yaml" -o -name "*.json" -o -name "*.html" -o 
    -name "*.css" -o -name "*.js" -o -name "*.env" -o -name "*.example" -o 
    -name "*.csv" -o -name "*.sql" 
\) -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/venv/*" -not -path "*/__pycache__/*")

echo -e "\n${BLUE}Scanning for files with Windows (CRLF) line endings...${NC}"

# Find files that actually contain CRLF
CRLF_FILES=()
while IFS= read -r -d '' file; do
    if grep -qU $'\r' "$file" 2>/dev/null; then
        CRLF_FILES+=("$file")
    fi
done < <("${FIND_CMD[@]}" -print0)

FILE_COUNT=${#CRLF_FILES[@]}

if [[ "$FILE_COUNT" -eq 0 ]]; then
    echo -e "${GREEN}All files already have Unix (LF) line endings. Nothing to do.${NC}"
    exit 0
fi

echo -e "Found ${YELLOW}$FILE_COUNT${NC} files with CRLF line endings."

if [[ "$DRY_RUN" == true ]]; then
    for f in "${CRLF_FILES[@]}"; do echo "  ${f#$PROJECT_ROOT/}"; done
    exit 0
fi

if [[ "$FORCE" != true ]]; then
    read -p "Convert these $FILE_COUNT files to LF? (y/N): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then exit 1; fi
fi

for file in "${CRLF_FILES[@]}"; do
    dos2unix "$file" > /dev/null 2>&1
    echo -e "  ${GREEN}Converted:${NC} ${file#$PROJECT_ROOT/}"
done

echo -e "\n${GREEN}✅ Successfully converted $FILE_COUNT files to Unix (LF) format.${NC}"

# Explicit verification for critical files
if [[ -f "$PROJECT_ROOT/scripts/configure-hub-for-spokes.sh" ]]; then
    if grep -qU $'\r' "$PROJECT_ROOT/scripts/configure-hub-for-spokes.sh"; then
        echo -e "${RED}ERROR: configure-hub-for-spokes.sh still has CRLF!${NC}"
        exit 1
    fi
fi

echo -e "\nNext steps:"
echo -e "  1. chmod +x scripts/*.sh"
echo -e "  2. ./scripts/nettrades-setup.sh hub --force --auto"