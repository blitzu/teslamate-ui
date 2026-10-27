#!/usr/bin/env bash
# Sets the app password. Once set it is required everywhere: through a reverse proxy / tunnel and on the local network alike.
# Without it, direct local-network access is open (see docs/security.md). The password is read hidden and written to .env.auth (mode 600). Run from the repository folder:
#   ./scripts/set-password.sh
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -s -p "Password for internet access (min. 12 characters): " P1; echo
read -r -s -p "Repeat password: " P2; echo
[ "$P1" = "$P2" ] || { echo "Passwords do not match."; exit 1; }
[ "${#P1}" -ge 12 ] || { echo "Too short (min. 12 characters)."; exit 1; }
case "$P1" in *"'"*) echo "The password cannot contain an apostrophe (')."; exit 1;; esac
SECRET="$(openssl rand -hex 32)"
umask 077
{
  printf "APP_PASSWORD='%s'\n" "$P1"
  printf "SESSION_SECRET='%s'\n" "$SECRET"
} > .env.auth
chmod 600 .env.auth
docker compose up -d
echo "Done. The app now asks for this password (also on the local network)."
