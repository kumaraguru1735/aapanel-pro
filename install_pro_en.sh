#!/bin/bash
# aaPanel Pro - Custom Installer with Pro Bypass
# One-liner: wget -O - https://raw.githubusercontent.com/kumaraguru1735/aapanel-pro/main/install_pro_en.sh | bash

PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
LANG=en_US.UTF-8
export LANG

GITHUB_RAW="https://raw.githubusercontent.com/kumaraguru1735/aapanel-pro/main"
PANEL_PATH="/www/server/panel"
PATCH_SCRIPT="$GITHUB_RAW/patch.sh"

# ---- sanity checks ----
if [ "$(whoami)" != "root" ]; then
    echo "Please run as root: sudo bash $0"
    exit 1
fi

if [ "$(uname -s)" = "Darwin" ]; then
    echo "macOS not supported. Use Debian/Ubuntu/CentOS."
    exit 1
fi

echo "======================================================"
echo "  aaPanel Pro Installer (with bypass)"
echo "======================================================"

# ---- Step 1: Install official aaPanel ----
echo "[*] Downloading and running official aaPanel installer..."
if command -v wget >/dev/null 2>&1; then
    wget -qO /tmp/install_aapanel.sh https://www.aapanel.com/script/install_pro_en.sh
elif command -v curl >/dev/null 2>&1; then
    curl -fsSL https://www.aapanel.com/script/install_pro_en.sh -o /tmp/install_aapanel.sh
else
    echo "Error: Neither wget nor curl found. Install one and retry."
    exit 1
fi

if [ ! -f /tmp/install_aapanel.sh ]; then
    echo "Error: Failed to download aaPanel installer."
    exit 1
fi

bash /tmp/install_aapanel.sh
rm -f /tmp/install_aapanel.sh

# ---- Step 2: Apply pro bypass patches ----
echo ""
echo "[*] Applying Pro bypass patches..."
if command -v wget >/dev/null 2>&1; then
    wget -qO /tmp/aapanel_patch.sh "$PATCH_SCRIPT"
elif command -v curl >/dev/null 2>&1; then
    curl -fsSL "$PATCH_SCRIPT" -o /tmp/aapanel_patch.sh
fi

if [ -f /tmp/aapanel_patch.sh ]; then
    bash /tmp/aapanel_patch.sh "$PANEL_PATH"
    rm -f /tmp/aapanel_patch.sh
else
    echo "Warning: Could not download patch script. Run manually:"
    echo "  wget -O - $PATCH_SCRIPT | bash"
fi

echo ""
echo "======================================================"
echo "  Installation complete!"
echo "  Panel URL: http://$(hostname -I | awk '{print $1}'):$(cat $PANEL_PATH/data/port.pl 2>/dev/null || echo 7800)"
echo "  Run 'bt default' to see credentials."
echo "======================================================"
