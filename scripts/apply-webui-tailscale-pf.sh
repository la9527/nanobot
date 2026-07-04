#!/usr/bin/env zsh

set -euo pipefail

ANCHOR_NAME="com.nanobot.webui"
ANCHOR_FILE="/etc/pf.anchors/${ANCHOR_NAME}"
PF_CONF="/etc/pf.conf"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

cat >"${ANCHOR_FILE}" <<'EOF'
# Allow local + tailscale ingress for nanobot webui websocket/http surface.
pass in quick proto tcp from 127.0.0.1 to any port 8765
pass in quick proto tcp from ::1 to any port 8765
pass in quick proto tcp from 100.64.0.0/10 to any port 8765
pass in quick proto tcp from fd7a:115c:a1e0::/48 to any port 8765
block in quick proto tcp to any port 8765
EOF

if ! grep -q "anchor \"${ANCHOR_NAME}\"" "${PF_CONF}"; then
  printf "\nanchor \"%s\"\n" "${ANCHOR_NAME}" >>"${PF_CONF}"
fi

if ! grep -q "load anchor \"${ANCHOR_NAME}\" from \"${ANCHOR_FILE}\"" "${PF_CONF}"; then
  printf "load anchor \"%s\" from \"%s\"\n" "${ANCHOR_NAME}" "${ANCHOR_FILE}" >>"${PF_CONF}"
fi

pfctl -nf "${PF_CONF}"
pfctl -f "${PF_CONF}"
pfctl -E >/dev/null 2>&1 || true

echo "Applied pf anchor ${ANCHOR_NAME}"
pfctl -a "${ANCHOR_NAME}" -sr
