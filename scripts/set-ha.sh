#!/usr/bin/env bash
# Links the app to Home Assistant. The token is read hidden and written to .env.ha (mode 600). Run from the repository folder:
#   ./scripts/set-ha.sh
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -p "Home Assistant URL [http://homeassistant.local:8123]: " URL
URL="${URL:-http://homeassistant.local:8123}"
read -r -s -p "Long-lived access token (hidden): " TOK; echo
case "$TOK" in *"'"*) echo "Invalid token."; exit 1;; esac
read -r -p "ESP32 BLE entity prefix [tesla_ble]: " PFX
PFX="${PFX:-tesla_ble}"
read -r -p "Grid import power sensor (optional, W): " GRID
read -r -p "PV power sensor (optional, W): " PV
umask 077
{
  printf "HA_URL='%s'\n" "$URL"
  printf "HA_TOKEN='%s'\n" "$TOK"
  printf "HA_BLE_PREFIX='%s'\n" "$PFX"
  printf "BLE_FIRST='1'\n"
  [ -n "$GRID" ] && printf "HA_GRID_IMPORT='%s'\n" "$GRID"
  [ -n "$PV" ] && printf "HA_PV_POWER='%s'\n" "$PV"
} > .env.ha
chmod 600 .env.ha
docker compose up -d
echo "Saved. Commands now go through the local BLE path when available."
