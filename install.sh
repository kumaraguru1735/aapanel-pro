#!/bin/bash
# aaPanel Pro - One-command patcher and post-installer
# Prerequisites: aaPanel must already be installed (bt panel must be running)
# To install aaPanel first: bash <(curl -s https://www.aapanel.com/script/install_7.0_en.sh)

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[!]${NC} $*"; exit 1; }

PANEL_DIR="/www/server/panel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check aaPanel is installed
[ -f "$PANEL_DIR/class/public.py" ] || error "aaPanel not found. Install it first: bash <(curl -s https://www.aapanel.com/script/install_7.0_en.sh)"

# Apply pro patches
info "Applying pro patches..."
bash "$SCRIPT_DIR/patch.sh"

# Install plugin directories
info "Installing plugin directories..."
if [ -d "$SCRIPT_DIR/plugin" ]; then
    for p in "$SCRIPT_DIR/plugin"/*/; do
        name=$(basename "$p")
        dest="$PANEL_DIR/plugin/$name"
        mkdir -p "$dest"
        cp -rf "$p"* "$dest/" 2>/dev/null || true
    done
fi

# Restart panel
info "Restarting panel..."
bt restart 2>/dev/null || true

info "Done! Run: bash post_install.sh --all  (installs PHP/Nginx/MySQL/phpMyAdmin/Redis)"
