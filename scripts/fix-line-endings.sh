#!/bin/bash
# =============================================================================
# FILE: scripts/fix-line-endings.sh
# =============================================================================
# PURPOSE:
#   Recursively convert all text files in the nettrades-platform directory
#   to Unix (LF) line endings using dos2unix.
#
# USAGE:
#   cd /mnt/c/nettrades-platform
#   ./scripts/fix-line-endings.sh --dry-run   # preview files without converting
#   ./scripts/fix-line-endings.sh --force     # skip confirmation
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
DRY_RUN=false
FORCE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Preview files that would be converted without changing them"
            echo "  --force      Skip confirmation prompt"
            echo "  --help, -h   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information."
            exit 1
            ;;
    esac
done

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  NETTRADES – Fix Line Endings${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo -e "Project root: ${YELLOW}$PROJECT_ROOT${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Check if dos2unix is installed
# -----------------------------------------------------------------------------
if ! command -v dos2unix &> /dev/null; then
    echo -e "${YELLOW}dos2unix is not installed. Installing...${NC}"
    if [[ "$DRY_RUN" == false ]]; then
        sudo apt update -qq
        sudo apt install dos2unix -y
        echo -e "${GREEN}dos2unix installed successfully.${NC}"
    else
        echo -e "${YELLOW}DRY RUN: Would install dos2unix.${NC}"
    fi
else
    echo -e "${GREEN}dos2unix is already installed.${NC}"
fi

echo ""

# -----------------------------------------------------------------------------
# Step 2: Define file patterns to convert
# -----------------------------------------------------------------------------
# Text file extensions that should be converted
PATTERNS=(
    "*.py"
    "*.xml"
    "*.sh"
    "*.conf"
    "*.cfg"
    "*.ini"
    "*.txt"
    "*.md"
    "*.yml"
    "*.yaml"
    "*.json"
    "*.html"
    "*.css"
    "*.js"
    "*.env"
    "*.example"
    "*.csv"
    "*.sql"
)

# Directories to exclude
EXCLUDE_DIRS=(
    ".git"
    "__pycache__"
    ".pytest_cache"
    ".mypy_cache"
    "venv"
    "env"
    "node_modules"
    ".vscode"
    ".idea"
    "*.egg-info"
)

# -----------------------------------------------------------------------------
# Step 3: Build the find command
# -----------------------------------------------------------------------------
FIND_CMD="find \"$PROJECT_ROOT\" -type f"

# Add exclude directories
for dir in "${EXCLUDE_DIRS[@]}"; do
    FIND_CMD="$FIND_CMD -not -path \"*/$dir/*\" -not -path \"*/$dir\""
done

# Add file patterns
PATTERN_ARGS=""
for pattern in "${PATTERNS[@]}"; do
    if [ -z "$PATTERN_ARGS" ]; then
        PATTERN_ARGS="-name \"$pattern\""
    else
        PATTERN_ARGS="$PATTERN_ARGS -o -name \"$pattern\""
    fi
done

FIND_CMD="$FIND_CMD \\( $PATTERN_ARGS \\)"

echo -e "${BLUE}File patterns to convert:${NC}"
for pattern in "${PATTERNS[@]}"; do
    echo -e "  - $pattern"
done
echo ""

# -----------------------------------------------------------------------------
# Step 4: Preview files (dry run)
# -----------------------------------------------------------------------------
echo -e "${BLUE}Scanning for files to convert...${NC}"
echo ""

# Count files
FILE_COUNT=$(eval "$FIND_CMD" | wc -l)
echo -e "Found ${YELLOW}$FILE_COUNT${NC} files matching patterns."

if [[ "$FILE_COUNT" -eq 0 ]]; then
    echo -e "${YELLOW}No files to convert.${NC}"
    exit 0
fi

if [[ "$DRY_RUN" == true ]]; then
    echo ""
    echo -e "${BLUE}Files that would be converted (DRY RUN):${NC}"
    eval "$FIND_CMD" | while read -r file; do
        echo "  $file"
    done
    echo ""
    echo -e "${YELLOW}DRY RUN completed. No files were changed.${NC}"
    echo -e "Run without --dry-run to actually convert the files."
    exit 0
fi

# -----------------------------------------------------------------------------
# Step 5: Confirm conversion
# -----------------------------------------------------------------------------
if [[ "$FORCE" != true ]]; then
    echo ""
    echo -e "${YELLOW}This will convert $FILE_COUNT files to Unix (LF) line endings.${NC}"
    echo -e "${RED}WARNING: This is a destructive operation. Make sure you have a backup.${NC}"
    echo ""
    read -p "Continue? (y/N): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Aborted.${NC}"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Step 6: Convert the files
# -----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}Converting files...${NC}"

# Use find to pass files to dos2unix (handles spaces in filenames)
# Use -0 to handle filenames with spaces correctly
eval "$FIND_CMD" -print0 | while IFS= read -r -d '' file; do
    echo -n "  Converting: ${file#$PROJECT_ROOT/} ... "
    dos2unix "$file" > /dev/null 2>&1
    echo -e "${GREEN}Done${NC}"
done

echo ""
echo -e "${GREEN}All $FILE_COUNT files converted successfully.${NC}"

# -----------------------------------------------------------------------------
# Step 7: Verify conversion
# -----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}Verifying conversion...${NC}"

# Check a sample file to verify
SAMPLE_FILE=$(eval "$FIND_CMD" | head -1)
if [[ -n "$SAMPLE_FILE" ]]; then
    if file "$SAMPLE_FILE" | grep -q "CRLF"; then
        echo -e "${YELLOW}Warning: Some files may still have CRLF.${NC}"
    else
        echo -e "${GREEN}Sample file $SAMPLE_FILE is properly converted to LF.${NC}"
    fi
fi

echo ""
echo -e "${GREEN}✅ Line endings fixed successfully!${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. ./scripts/prepare-odoo-addons.sh --force"
echo -e "  2. cd deploy/docker && docker compose restart odoo"
echo -e "  3. docker exec odoo odoo -c /etc/odoo/odoo.conf -d odoo -i nettrades_gpu_admin --stop-after-init --log-level=info"
