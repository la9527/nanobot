#!/usr/bin/env zsh

set -euo pipefail

ANCHOR_NAME="com.nanobot.webui"
ANCHOR_FILE="/etc/pf.anchors/${ANCHOR_NAME}"
PF_CONF="/etc/pf.conf"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

if [[ -f "${PF_CONF}" ]]; then
  sed -i '' "/^anchor \"${ANCHOR_NAME}\"$/d" "${PF_CONF}"
  sed -i '' "#^load anchor \"${ANCHOR_NAME}\" from \"${ANCHOR_FILE}\"$#d" "${PF_CONF}"
fi

rm -f "${ANCHOR_FILE}"

pfctl -nf "${PF_CONF}"
pfctl -f "${PF_CONF}"

echo "Removed pf anchor ${ANCHOR_NAME}"
