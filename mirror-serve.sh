#!/bin/bash
# ==============================================================================
# mirror-serve.sh — Serve the local ./mirror tree over HTTP, with no CDN.
# Run this on your mirror server. Point mirror.conf's BT_MIRROR at it, e.g.
#   BT_MIRROR="http://<this-server-ip>:5050"
#
# Usage:
#   bash mirror-serve.sh [port]      # default port 5050
# ==============================================================================
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIRROR_DIR="$SCRIPT_DIR/mirror"
PORT="${1:-5050}"

[ -d "$MIRROR_DIR" ] || { echo "No mirror/ dir. Run: bash mirror-pull.sh first."; exit 1; }

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "Serving $MIRROR_DIR on:"
echo "  http://${IP:-127.0.0.1}:$PORT"
echo "Set this in mirror.conf:  BT_MIRROR=\"http://${IP:-127.0.0.1}:$PORT\""
echo "Ctrl-C to stop."

cd "$MIRROR_DIR"
if command -v python3 >/dev/null 2>&1; then
    exec python3 -m http.server "$PORT" --bind 0.0.0.0
elif command -v python >/dev/null 2>&1; then
    exec python -m SimpleHTTPServer "$PORT"
else
    echo "python not found. Alternatively serve $MIRROR_DIR with nginx/apache."
    exit 1
fi
