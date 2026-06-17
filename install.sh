#!/bin/bash
# aaPanel Pro - One-command installer
# Usage: bash <(curl -s https://raw.githubusercontent.com/kumaraguru1735/aapanel-pro/main/install.sh)
# Or:    git clone https://github.com/kumaraguru1735/aapanel-pro && cd aapanel-pro && bash install.sh

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[!]${NC} $*"; exit 1; }

PANEL_DIR="/www/server/panel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Step 1: Install aaPanel if not present ───────────────────────────────────
if [ ! -f "$PANEL_DIR/class/public.py" ]; then
    info "Installing aaPanel from official source..."
    if command -v apt-get &>/dev/null; then
        INSTALL_URL="https://www.aapanel.com/script/install_7.0_en.sh"
    else
        INSTALL_URL="https://www.aapanel.com/script/install_7.0_en.sh"
    fi
    wget -qO /tmp/aapanel_install.sh "$INSTALL_URL" || \
        curl -sL "$INSTALL_URL" -o /tmp/aapanel_install.sh || \
        error "Failed to download aaPanel installer"
    bash /tmp/aapanel_install.sh <<< "y" || true
    info "aaPanel base installed."
else
    info "aaPanel already installed at $PANEL_DIR"
fi

# ─── Step 2: Apply pro patches ────────────────────────────────────────────────
info "Applying pro patches..."
bash "$SCRIPT_DIR/patch.sh"

# ─── Step 3: Install plugin directories ───────────────────────────────────────
info "Installing plugin directories..."
if [ -d "$SCRIPT_DIR/plugin" ]; then
    for p in "$SCRIPT_DIR/plugin"/*/; do
        name=$(basename "$p")
        dest="$PANEL_DIR/plugin/$name"
        mkdir -p "$dest"
        rsync -a "$p" "$dest/" 2>/dev/null || cp -rf "$p"/* "$dest/" 2>/dev/null || true
    done
    info "Plugin directories installed."
fi

# ─── Step 4: Restart panel ────────────────────────────────────────────────────
info "Restarting panel..."
bt restart 2>/dev/null || (bt stop 2>/dev/null; sleep 2; bt start 2>/dev/null) || true

info "Done! aaPanel Pro is ready."
info "Run ./post_install.sh to install PHP/Nginx/MySQL/Redis/phpMyAdmin"
