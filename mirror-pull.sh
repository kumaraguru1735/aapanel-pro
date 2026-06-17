#!/bin/bash
# ==============================================================================
# mirror-pull.sh — Populate a LOCAL mirror of everything aaPanel would otherwise
# fetch from a CDN. Run this ONCE on any internet-connected machine (it can be
# the mirror server itself). Afterwards, serve ./mirror with mirror-serve.sh and
# every install is 100% CDN-free.
#
# What it mirrors into ./mirror :
#   install/<type>/lib.sh, <name>.sh        (the soft-install scripts)
#   install/src/... (and any other paths)   (compiled source tarballs they pull)
#   install/pyenv_<arch>.tar.gz             (prebuilt Python runtime)
#   pip/                                     (Python wheels for the panel runtime)
#
# Usage:
#   bash mirror-pull.sh                 # mirror the default software set
#   UPSTREAM=https://download.bt.cn bash mirror-pull.sh
#   SOFT="nginx:stable php:82 mysql:8.0" bash mirror-pull.sh
# ==============================================================================
set -u
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info(){ echo -e "${GREEN}[+]${NC} $*"; }
warn(){ echo -e "${YELLOW}[!]${NC} $*"; }
err(){  echo -e "${RED}[!]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIRROR_DIR="$SCRIPT_DIR/mirror"
UPSTREAM="${UPSTREAM:-https://node.aapanel.com}"
# CDN hosts whose tarball URLs we follow and localize.
HOSTS_RE='https?://(download\.bt\.cn|node\.aapanel\.com|[a-z0-9-]+\.bt\.cn|www\.aapanel\.com)'

# Package-manager types to mirror scripts for: 3=apt/deb, 0=yum/rpm.
TYPES="${TYPES:-0 3}"
# software:version list to mirror (matches post_install.sh).
DEFAULT_SOFT="nginx:stable mysql:8.0 redis:stable memcached:stable pure-ftpd:stable phpmyadmin:5.2 php:56 php:70 php:71 php:72 php:73 php:74 php:80 php:81 php:82 php:83"
SOFT="${SOFT:-$DEFAULT_SOFT}"

mkdir -p "$MIRROR_DIR/install/src"
DL(){ # DL <url> <dest>
    local url="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    [ -s "$dest" ] && { return 0; }
    wget -q --no-check-certificate -O "$dest" "$url" && [ -s "$dest" ]
}

# Save a CDN url into the mirror, mapping <host>/<path> -> mirror/<path>.
save_cdn_url(){
    local url="$1"
    local path; path=$(echo "$url" | sed -E "s#$HOSTS_RE/##")
    [ "$path" = "$url" ] && return 0    # not a CDN host we localize
    local dest="$MIRROR_DIR/$path"
    if DL "$url" "$dest"; then
        info "  tarball: $path"
    else
        warn "  MISS: $url  (may use a runtime-computed name — add manually if needed)"
    fi
}

# Pull lib.sh + each soft script, then follow tarball URLs found inside them.
for t in $TYPES; do
    info "Mirroring soft scripts for package type $t"
    DL "$UPSTREAM/install/$t/lib.sh" "$MIRROR_DIR/install/$t/lib.sh" \
        && info "  lib.sh ($t)" || warn "  lib.sh ($t) missing"
    for sv in $SOFT; do
        name="${sv%%:*}"
        DL "$UPSTREAM/install/$t/$name.sh" "$MIRROR_DIR/install/$t/$name.sh" \
            && info "  $name.sh ($t)" || { warn "  $name.sh ($t) missing"; continue; }
    done
done

info "Scanning downloaded scripts for tarball/source URLs..."
grep -rhoE "$HOSTS_RE[^\"' )]*" "$MIRROR_DIR/install" 2>/dev/null \
    | sort -u | while read -r url; do
        case "$url" in
            */net_test|*/api/*|*notpro*|*update*.sh) continue ;;
        esac
        save_cdn_url "$url"
    done

# ─── Prebuilt Python runtime (pyenv) ──────────────────────────────────────────
info "Mirroring prebuilt Python runtime(s)..."
for arch in x86_64 aarch64; do
    for cand in \
        "$UPSTREAM/install/pyenv_${arch}.tar.gz" \
        "https://www.aapanel.com/script/install/pyenv_${arch}.tar.gz" \
        "https://download.bt.cn/install/pyenv_${arch}.tar.gz"; do
        if DL "$cand" "$MIRROR_DIR/install/pyenv_${arch}.tar.gz"; then
            info "  pyenv_${arch}.tar.gz"
            break
        fi
    done
    [ -s "$MIRROR_DIR/install/pyenv_${arch}.tar.gz" ] || warn "  pyenv_${arch}: not found upstream (pip build still works)"
done

# ─── Python wheelhouse (makes the runtime PyPI-free) ──────────────────────────
if command -v python3 >/dev/null 2>&1; then
    info "Downloading Python wheels into mirror/pip (offline runtime)..."
    mkdir -p "$MIRROR_DIR/pip"
    python3 -m pip download -r "$SCRIPT_DIR/panel/requirements.txt" -d "$MIRROR_DIR/pip" \
        2>"$MIRROR_DIR/pip/.download.log" \
        && info "  wheels saved to mirror/pip" \
        || warn "  some wheels failed (see mirror/pip/.download.log) — pip/PyPI fallback remains available"
else
    warn "python3 not found — skipping wheelhouse. Run on a box with python3 to make the runtime PyPI-free."
fi

echo
info "Mirror populated at: $MIRROR_DIR"
info "Serve it with:  bash mirror-serve.sh"
info "Then set BT_MIRROR in mirror.conf to this server's URL and run install.sh."
warn "Note: a few soft scripts build tarball names at runtime; if an install reports a"
warn "404 against your mirror, copy that exact path from the error into mirror/ and re-serve."
