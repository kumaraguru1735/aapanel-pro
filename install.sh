#!/bin/bash
# ==============================================================================
# aaPanel Pro - Fully self-contained offline installer
# ------------------------------------------------------------------------------
# Installs aaPanel + all pro plugins + pro unlock ENTIRELY from this repository.
# No dependency on aapanel.com for the panel itself (only PyPI for the Python
# runtime, and — optionally — the LAMP stack via ./post_install.sh).
#
# Usage:
#   git clone https://github.com/kumaraguru1735/aapanel-pro.git
#   cd aapanel-pro && sudo bash install.sh
#
# Flags:
#   --port <n>        Panel port           (default 8888)
#   --password <pw>   Admin password       (default: random)
#   --user <name>     Admin username       (default: admin)
#   --pyenv-cdn       Download prebuilt Python runtime from aapanel.com instead
#                     of building it locally from requirements.txt via pip.
#   --no-stack        Skip the optional LAMP stack prompt at the end.
# ==============================================================================

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
head_() { echo -e "${BLUE}[==]${NC} $*"; }
error() { echo -e "${RED}[!]${NC} $*"; exit 1; }

[ "$(id -u)" = "0" ] || error "Please run as root (sudo bash install.sh)."

PANEL_DIR="/www/server/panel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/panel"

PANEL_PORT=8888
ADMIN_USER="admin"
ADMIN_PASS=""
USE_CDN_PYENV=0
PROMPT_STACK=1

while [ $# -gt 0 ]; do
    case "$1" in
        --port)     PANEL_PORT="$2"; shift 2 ;;
        --password) ADMIN_PASS="$2"; shift 2 ;;
        --user)     ADMIN_USER="$2"; shift 2 ;;
        --pyenv-cdn) USE_CDN_PYENV=1; shift ;;
        --no-stack) PROMPT_STACK=0; shift ;;
        *) error "Unknown option: $1" ;;
    esac
done

[ -d "$SRC_DIR" ] || error "Bundled panel source not found at $SRC_DIR. Did you clone the full repo?"

# ─── 0. Detect OS / package manager ───────────────────────────────────────────
if command -v apt-get &>/dev/null; then
    PKG="apt"; PKGTYPE=3
elif command -v dnf &>/dev/null; then
    PKG="dnf"; PKGTYPE=0
elif command -v yum &>/dev/null; then
    PKG="yum"; PKGTYPE=0
else
    error "No supported package manager (apt/dnf/yum) found."
fi
info "Package manager: $PKG"

# ─── 1. Install OS build dependencies ─────────────────────────────────────────
head_ "Installing OS dependencies"
if [ "$PKG" = "apt" ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y \
        python3 python3-dev python3-venv python3-pip \
        build-essential gcc g++ make pkg-config \
        libffi-dev libssl-dev libxml2-dev libxslt1-dev \
        libcurl4-openssl-dev libjpeg-dev zlib1g-dev \
        libmysqlclient-dev default-libmysqlclient-dev \
        curl wget unzip cron openssl ca-certificates \
        libsasl2-dev libldap2-dev 2>/dev/null || \
    apt-get install -y python3 python3-dev python3-venv python3-pip build-essential \
        gcc make libffi-dev libssl-dev libxml2-dev libxslt1-dev libcurl4-openssl-dev \
        curl wget unzip cron openssl ca-certificates
else
    $PKG install -y \
        python3 python3-devel python3-pip \
        gcc gcc-c++ make pkgconfig \
        libffi-devel openssl-devel libxml2-devel libxslt-devel \
        libcurl-devel libjpeg-devel zlib-devel \
        mysql-devel curl wget unzip cronie openssl ca-certificates \
        cyrus-sasl-devel openldap-devel 2>/dev/null || \
    $PKG install -y python3 python3-devel python3-pip gcc gcc-c++ make \
        libffi-devel openssl-devel libxml2-devel libxslt-devel libcurl-devel \
        curl wget unzip openssl ca-certificates
fi

# ─── 2. Deploy panel source from repo ─────────────────────────────────────────
head_ "Deploying panel source to $PANEL_DIR"
FRESH=1
[ -f "$PANEL_DIR/BT-Panel" ] && [ -f "$PANEL_DIR/data/default.db" ] && FRESH=0 && warn "Existing aaPanel detected — updating in place (data preserved)."

mkdir -p /www/server /www/wwwroot /www/wwwlogs /www/backup/database
mkdir -p "$PANEL_DIR"

if command -v rsync &>/dev/null; then
    if [ "$FRESH" = "1" ]; then
        rsync -a "$SRC_DIR"/ "$PANEL_DIR"/
    else
        # Preserve runtime state: data/, logs/, pyenv/, ssl/, vhost/, config/
        rsync -a \
            --exclude='data/' --exclude='logs/' --exclude='pyenv/' \
            --exclude='ssl/' --exclude='vhost/' --exclude='config/' \
            "$SRC_DIR"/ "$PANEL_DIR"/
    fi
else
    cp -a "$SRC_DIR"/. "$PANEL_DIR"/
fi
mkdir -p "$PANEL_DIR/logs" "$PANEL_DIR/data" "$PANEL_DIR/vhost/nginx" "$PANEL_DIR/vhost/apache" "$PANEL_DIR/vhost/rewrite"
info "Panel source deployed."

# ─── 3. Python runtime (pyenv) ────────────────────────────────────────────────
head_ "Setting up Python runtime"
build_pyenv_pip() {
    info "Building Python venv from requirements.txt (via pip)..."
    rm -rf "$PANEL_DIR/pyenv"
    python3 -m venv "$PANEL_DIR/pyenv" || return 1
    "$PANEL_DIR/pyenv/bin/pip" install --upgrade pip setuptools wheel || return 1
    if "$PANEL_DIR/pyenv/bin/pip" install -r "$PANEL_DIR/requirements.txt"; then
        return 0
    fi
    warn "Pinned requirements failed to build fully — retrying best-effort (line by line)..."
    while read -r pkg; do
        [ -z "$pkg" ] && continue
        case "$pkg" in \#*) continue ;; esac
        "$PANEL_DIR/pyenv/bin/pip" install "$pkg" 2>/dev/null \
            || "$PANEL_DIR/pyenv/bin/pip" install "${pkg%%==*}" 2>/dev/null \
            || warn "  skipped: $pkg"
    done < "$PANEL_DIR/requirements.txt"
    return 0
}

download_pyenv_cdn() {
    info "Downloading prebuilt Python runtime from aapanel.com..."
    local arch; arch=$(uname -m)
    local url="https://www.aapanel.com/script/install/pyenv_${arch}.tar.gz"
    cd "$PANEL_DIR"
    wget -O pyenv.tar.gz "$url" --no-check-certificate || return 1
    tar xzf pyenv.tar.gz && rm -f pyenv.tar.gz
    [ -f "$PANEL_DIR/pyenv/bin/python3" ]
}

if [ "$USE_CDN_PYENV" = "1" ]; then
    download_pyenv_cdn || error "CDN pyenv download failed."
elif [ -f "$PANEL_DIR/pyenv/bin/python3" ] && [ "$FRESH" = "0" ]; then
    info "Existing pyenv found — keeping it. (Run with --pyenv-cdn or delete $PANEL_DIR/pyenv to rebuild.)"
else
    build_pyenv_pip || {
        warn "Local pip build failed; falling back to prebuilt runtime from aapanel.com."
        download_pyenv_cdn || error "Could not provision a Python runtime."
    }
fi
"$PANEL_DIR/pyenv/bin/python3" -c "import flask, gevent, sqlalchemy" 2>/dev/null \
    && info "Python runtime OK." \
    || warn "Python runtime present but some core modules missing — panel may need manual pip fixes."

# ─── 4. Initialize panel data (fresh install only) ────────────────────────────
if [ "$FRESH" = "1" ]; then
    head_ "Initializing panel configuration"
    echo -n "$PANEL_PORT" > "$PANEL_DIR/data/port.pl"

    # Random security entrance path
    ENTRANCE=$(head -c 16 /dev/urandom | md5sum | cut -c1-8)
    echo -n "/$ENTRANCE" > "$PANEL_DIR/data/admin_path.pl"

    # Admin password (random if not supplied)
    [ -z "$ADMIN_PASS" ] && ADMIN_PASS=$(head -c 24 /dev/urandom | md5sum | cut -c1-12)
    PASS_MD5=$(printf '%s' "$ADMIN_PASS" | md5sum | cut -d' ' -f1)
    "$PANEL_DIR/pyenv/bin/python3" - "$ADMIN_USER" "$PASS_MD5" <<'PYEOF'
import sqlite3, sys
user, pmd5 = sys.argv[1], sys.argv[2]
db = "/www/server/panel/data/default.db"
c = sqlite3.connect(db)
c.execute("UPDATE users SET username=?, password=? WHERE id=1", (user, pmd5))
if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
    c.execute("INSERT INTO users (id,username,password,login_ip,login_time,phone_check,email) VALUES (1,?,?,'','','0','')", (user, pmd5))
c.commit(); c.close()
PYEOF
    info "Admin user configured."
else
    [ -f "$PANEL_DIR/data/port.pl" ] || echo -n "$PANEL_PORT" > "$PANEL_DIR/data/port.pl"
fi

# ─── 5. Permissions + entry scripts ───────────────────────────────────────────
head_ "Fixing permissions and entry scripts"
PY="$PANEL_DIR/pyenv/bin/python"
[ -f "$PY" ] || PY="$PANEL_DIR/pyenv/bin/python3"
# Rewrite BT-Panel / BT-Task shebangs to the local pyenv interpreter
sed -i "1s|^#!.*|#!$PY|" "$PANEL_DIR/BT-Panel" "$PANEL_DIR/BT-Task" 2>/dev/null || true
chmod 700 "$PANEL_DIR/BT-Panel" "$PANEL_DIR/BT-Task" 2>/dev/null || true
chmod -R 700 "$PANEL_DIR/pyenv/bin" 2>/dev/null || true

# ─── 6. Install init service ──────────────────────────────────────────────────
head_ "Installing panel service (/etc/init.d/bt)"
cp -f "$PANEL_DIR/init.sh" /etc/init.d/bt
chmod +x /etc/init.d/bt
if command -v chkconfig &>/dev/null; then
    chkconfig --add bt 2>/dev/null || true
elif command -v update-rc.d &>/dev/null; then
    update-rc.d bt defaults 2>/dev/null || true
fi
# Convenience CLI wrapper
ln -sf /etc/init.d/bt /usr/bin/bt 2>/dev/null || true

# ─── 7. Apply pro patches (DRM bypass + frontend unlock) ──────────────────────
head_ "Applying pro patches"
bash "$SCRIPT_DIR/patch.sh" || warn "patch.sh reported issues — review output above."

# ─── 8. Install pro plugins from repo ─────────────────────────────────────────
head_ "Installing pro plugins"
if [ -d "$SCRIPT_DIR/plugin" ]; then
    for p in "$SCRIPT_DIR/plugin"/*/; do
        name=$(basename "$p")
        dest="$PANEL_DIR/plugin/$name"
        mkdir -p "$dest"
        cp -rf "$p"* "$dest/" 2>/dev/null || true
        info "  plugin: $name"
    done
fi

# ─── 9. Start panel ───────────────────────────────────────────────────────────
head_ "Starting panel"
/etc/init.d/bt start 2>/dev/null || bt start 2>/dev/null || true
sleep 2

# ─── 10. Summary ──────────────────────────────────────────────────────────────
IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
ENT=$(cat "$PANEL_DIR/data/admin_path.pl" 2>/dev/null)
PORT=$(cat "$PANEL_DIR/data/port.pl" 2>/dev/null)
echo
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  aaPanel Pro installed successfully${NC}"
echo -e "${GREEN}============================================================${NC}"
echo -e "  URL:      http://${IP}:${PORT}${ENT}"
echo -e "  Username: ${ADMIN_USER}"
if [ "$FRESH" = "1" ]; then
    echo -e "  Password: ${ADMIN_PASS}"
fi
echo -e "${GREEN}------------------------------------------------------------${NC}"
echo -e "  Pro features unlocked, all plugins installed."
echo -e "  Manage: ${YELLOW}bt${NC}  (e.g. bt restart, bt default to see login info)"
echo -e "${GREEN}============================================================${NC}"
echo

if [ "$PROMPT_STACK" = "1" ]; then
    echo -e "Install the web stack now (PHP / Nginx / MySQL / phpMyAdmin / Redis)?"
    echo -e "  Run: ${YELLOW}bash post_install.sh --all${NC}   (downloads compiled software from aapanel.com CDN)"
fi
