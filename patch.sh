#!/bin/bash
# aaPanel Pro - Patch script
# Applies DRM bypass and frontend unlocks to any aaPanel installation
# Safe to re-run — idempotent

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }

PANEL_DIR="/www/server/panel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLASS_DIR="$PANEL_DIR/class"
VITE_JS_DIR="$PANEL_DIR/BTPanel/static/vite/js"

[ -d "$CLASS_DIR" ] || { echo "aaPanel not found at $PANEL_DIR"; exit 1; }

# ─── 1. Stop panel ────────────────────────────────────────────────────────────
info "Stopping panel..."
bt stop 2>/dev/null || true

# ─── 2. Install PluginLoader bypass ──────────────────────────────────────────
info "Installing PluginLoader bypass..."

# Backup original .so if not already backed up
if [ ! -f "$CLASS_DIR/PluginLoader_real.so" ]; then
    ARCH=$(uname -m)
    PY_VER=$("$PANEL_DIR/pyenv/bin/python3" -c "import sys; print('Python{}.{}'.format(*sys.version_info[:2]))" 2>/dev/null || echo "Python3.12")
    # Try exact match first, then fallback candidates
    for so in \
        "$SCRIPT_DIR/so/PluginLoader.${ARCH}.${PY_VER}.so" \
        "$SCRIPT_DIR/so/PluginLoader.${ARCH}.glibc214.${PY_VER}.so" \
        "$CLASS_DIR/PluginLoader.${ARCH}.${PY_VER}.so" \
        "$CLASS_DIR/PluginLoader.${ARCH}.glibc214.${PY_VER}.so"; do
        if [ -f "$so" ]; then
            cp "$so" "$CLASS_DIR/PluginLoader_real.so"
            info "Backed up .so: $(basename $so) → PluginLoader_real.so"
            break
        fi
    done
fi

# Copy all .so files from repo to class dir (so the mock can find them)
if [ -d "$SCRIPT_DIR/so" ]; then
    cp -f "$SCRIPT_DIR/so/"*.so "$CLASS_DIR/" 2>/dev/null || true
fi

# Install PluginLoader.py mock
cp -f "$SCRIPT_DIR/patches/PluginLoader.py" "$CLASS_DIR/PluginLoader.py"
info "PluginLoader.py bypass installed."

# ─── 3. Patch frontend JS files ───────────────────────────────────────────────
info "Patching frontend JS (version-agnostic)..."

python3 << 'PYEOF'
import os, sys

vite_dir = "/www/server/panel/BTPanel/static/vite/js"
if not os.path.isdir(vite_dir):
    print("WARN: vite/js dir not found, skipping JS patches")
    sys.exit(0)

# (pattern, replacement, description)
PATCHES = [
    # App Store "Buy now" indicator — always hide
    (
        'Rd=e=>e.price!=="0.00"&&(e.endtime==-1||e.endtime==-2),',
        'Rd=e=>!1,',
        'App Store buy indicator disabled'
    ),
    # WAF router guard — bypass auth check
    (
        'Mt=async(e,t,s)=>{const n=Wd();try{if(await n.getWafInfo(),!n.isBuyAndInstall&&e.path!=="/waf/install"){s("/waf/install");return}if(n.isBuyAndInstall&&e.path==="/waf/install"){s("/waf/overview");return}if(n.isBuyAndInstall&&!n.isNewVersion&&e.path!=="/waf/site"){s("/waf/site");return}}catch(o){console.error(o)}s()},',
        'Mt=async(e,t,s)=>{const n=Wd();try{await n.getWafInfo()}catch(o){}if(e.path==="/waf/install"){s("/waf/overview");return}s()},',
        'WAF router guard bypassed'
    ),
    # WAF install page — always show Install button (not Buy)
    (
        't(v)?(p(),r(m,{key:0,type:"primary",class:"text-14px",onClick:h}',
        '(!0)?(p(),r(m,{key:0,type:"primary",class:"text-14px",onClick:h}',
        'WAF install button unlocked'
    ),
]

applied = 0
already = 0
for fname in os.listdir(vite_dir):
    if not fname.endswith('.js'):
        continue
    fpath = os.path.join(vite_dir, fname)
    try:
        with open(fpath, 'r', errors='replace') as f:
            content = f.read()
        modified = False
        for old, new, desc in PATCHES:
            if old in content:
                content = content.replace(old, new)
                modified = True
                print(f"  [+] {desc} ({fname})")
                applied += 1
            elif new in content:
                already += 1  # already patched
        if modified:
            with open(fpath, 'w') as f:
                f.write(content)
    except Exception as e:
        print(f"  [!] Error in {fname}: {e}")

if applied == 0 and already > 0:
    print("  [+] All JS patches already applied.")
elif applied == 0 and already == 0:
    print("  [!] WARNING: No patterns matched. Panel may be a different version.")
    print("  [!] Falling back to pre-patched JS files if available...")
PYEOF

# Fallback: copy pre-patched JS files if they exist in repo
if [ -d "$SCRIPT_DIR/patches/js" ]; then
    for f in "$SCRIPT_DIR/patches/js/"*.js; do
        fname=$(basename "$f")
        dest="$VITE_JS_DIR/$fname"
        if [ -f "$dest" ]; then
            cp -f "$f" "$dest"
            info "Overlay: $fname"
        fi
    done
fi

# ─── 4. Start panel ───────────────────────────────────────────────────────────
info "Starting panel..."
bt start 2>/dev/null || true

info "All patches applied successfully."
