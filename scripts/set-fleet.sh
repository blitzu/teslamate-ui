#!/usr/bin/env bash
# Stores your Tesla Fleet API credentials and the command PIN in .env.fleet (mode 600), then restarts the app.
# Values are read locally (secret and PIN are hidden) and never printed. Run from the repository folder:
#   ./scripts/set-fleet.sh
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -p "Client ID (from developer.tesla.com): " CID
read -r -s -p "Client Secret (hidden): " SEC; echo
read -r -p "Public domain (e.g. tesla.example.com): " DOM
read -r -s -p "PIN required for commands in the app (hidden): " PIN; echo
echo "Region: 1) Europe/Middle East/Africa   2) North America/Asia-Pacific"
read -r -p "Choose [1/2]: " REG
case "$REG" in
  2) BASE='https://fleet-api.prd.na.vn.cloud.tesla.com' ;;
  *) BASE='https://fleet-api.prd.eu.vn.cloud.tesla.com' ;;
esac
# values go between single quotes: otherwise Docker Compose expands '$' inside secrets
for V in "$CID" "$SEC" "$DOM" "$PIN"; do
  case "$V" in *"'"*) echo "Values cannot contain an apostrophe (')."; exit 1;; esac
done
umask 077
{
  printf "FLEET_CLIENT_ID='%s'\n" "$CID"
  printf "FLEET_CLIENT_SECRET='%s'\n" "$SEC"
  printf "FLEET_DOMAIN='%s'\n" "$DOM"
  printf "APP_PIN='%s'\n" "$PIN"
  printf "FLEET_BASE='%s'\n" "$BASE"
} > .env.fleet
chmod 600 .env.fleet
docker compose up -d
echo "Saved. Open the app and follow the checklist in the Controls section (register domain, connect Tesla account, virtual key)."
