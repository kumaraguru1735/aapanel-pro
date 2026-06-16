#!/bin/bash
# aaPanel Pro bypass patcher
# Applies bypass patches to an installed aaPanel instance

PANEL_PATH="${1:-/www/server/panel}"
REPO_URL="https://raw.githubusercontent.com/kumaraguru1735/aapanel-pro/main/panel"

echo "[*] Patching aaPanel at: $PANEL_PATH"

# ---- 1. Copy new bypass files directly ----
copy_file() {
    local src="$1" dst="$2"
    mkdir -p "$(dirname "$dst")"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$REPO_URL/$src" -o "$dst"
    else
        wget -qO "$dst" "$REPO_URL/$src"
    fi
}

echo "[*] Installing bypass files..."

copy_file "class/PluginLoader.py"   "$PANEL_PATH/class/PluginLoader.py"
copy_file "class/pluginAuth.py"     "$PANEL_PATH/class/pluginAuth.py"
copy_file "data/.is_pro.pl"         "$PANEL_PATH/data/.is_pro.pl"
copy_file "data/panel_pro.pl"       "$PANEL_PATH/data/panel_pro.pl"
copy_file "data/plugin_bin.pl"      "$PANEL_PATH/data/plugin_bin.pl"
copy_file "script/check_auth.py"    "$PANEL_PATH/script/check_auth.py"

for mod in firewall freeip ips syslog safecloud quota total; do
    copy_file "class_v2/$mod.py" "$PANEL_PATH/class_v2/$mod.py"
done

for plugin in tamper_core fail2ban syssafe load_balance mysql_replicate task_manager nodejs btwaf btwaf_httpd monitor total bt_security ssl_verify rsync tamper_proof; do
    mkdir -p "$PANEL_PATH/plugin/$plugin"
    copy_file "plugin/$plugin/index.py" "$PANEL_PATH/plugin/$plugin/index.py"
done

# ---- 2. Patch large existing files using Python ----
echo "[*] Patching core Python files..."

python3 - "$PANEL_PATH" <<'PYEOF'
import sys, re

panel = sys.argv[1]

# --- patch class/config.py: is_pro() always returns pro ---
f = panel + '/class/config.py'
txt = open(f).read()
txt = re.sub(
    r'(def is_pro\(self,\s*get\)[^\n]*\n(?:[ \t]+[^\n]*\n)*?)',
    lambda m: re.sub(
        r'(def is_pro\(self,\s*get\)\s*:\s*\n)(.*?)(?=\n\s*def |\Z)',
        r"\1        return {'status': True, 'msg': 'pro', 'pro': True}\n",
        m.group(0), flags=re.DOTALL
    ),
    txt, count=1, flags=re.DOTALL
)
# simpler targeted replacement
old = None
new_body = "        return {'status': True, 'msg': 'pro', 'pro': True}\n"
lines = txt.splitlines(keepends=True)
out = []
i = 0
while i < len(lines):
    out.append(lines[i])
    if 'def is_pro(self,get)' in lines[i] or 'def is_pro(self, get)' in lines[i]:
        # skip old body until next def or blank+def
        i += 1
        out.append(new_body)
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('def ') or (not stripped and i+1 < len(lines) and lines[i+1].strip().startswith('def ')):
                break
            i += 1
        continue
    i += 1
open(f, 'w').write(''.join(out))
print("  Patched: class/config.py is_pro()")


# --- patch class_v2/config_v2.py: is_pro() ---
f = panel + '/class_v2/config_v2.py'
txt = open(f).read()
lines = txt.splitlines(keepends=True)
out = []
i = 0
while i < len(lines):
    out.append(lines[i])
    if 'def is_pro(self, get)' in lines[i] or 'def is_pro(self,get)' in lines[i]:
        i += 1
        out.append("        return {'status': True, 'msg': 'pro', 'pro': True}\n")
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('def '):
                break
            i += 1
        continue
    i += 1
open(f, 'w').write(''.join(out))
print("  Patched: class_v2/config_v2.py is_pro()")


# --- patch common.py: load_soft_list() bypass cloud ---
f = panel + '/class/public/common.py'
txt = open(f).read()
old_sig = 'def load_soft_list(force: bool = True, retry_count: int = 0):'
new_sig = (
    'def load_soft_list(force: bool = True, retry_count: int = 0):\n'
    '    import PluginLoader as _PL\n'
    '    return _PL.get_plugin_list(0)\n'
)
if old_sig in txt and 'import PluginLoader as _PL' not in txt:
    txt = txt.replace(old_sig, new_sig, 1)
    open(f, 'w').write(txt)
    print("  Patched: common.py load_soft_list() bypass")
else:
    print("  Skipped: common.py (already patched or not found)")


# --- patch ssl_domainModelV2/api.py: dns.is_pro() gate ---
f = panel + '/class_v2/ssl_domainModelV2/api.py'
try:
    txt = open(f).read()
    # Replace: if dns.is_pro(): return public.fail_v2(...)
    # with: if False:  # pro check bypassed
    txt = re.sub(
        r'if\s+dns\.is_pro\(\)\s*:',
        'if False:  # pro check bypassed',
        txt
    )
    open(f, 'w').write(txt)
    print("  Patched: ssl_domainModelV2/api.py dns.is_pro()")
except FileNotFoundError:
    print("  Skipped: ssl_domainModelV2/api.py (not found)")


print("[+] All patches applied successfully.")
PYEOF

# ---- 3. Ensure pro marker files have correct content ----
echo "True" > "$PANEL_PATH/data/.is_pro.pl"
echo "True" > "$PANEL_PATH/data/panel_pro.pl"

# ---- 4. Restart panel ----
echo "[*] Restarting aaPanel..."
if [ -f /etc/init.d/bt ]; then
    /etc/init.d/bt restart
elif command -v bt >/dev/null 2>&1; then
    bt restart
fi

echo "[+] Done! aaPanel Pro bypass applied."
