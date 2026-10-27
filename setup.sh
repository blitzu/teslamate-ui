#!/usr/bin/env bash
# One-time setup: creates .env, the Tesla command-signing key and the internal TLS certificate of the proxy.
# Run from the repository folder:  ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Docker is required."; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required."; exit 1; }
mkdir -p fleet data
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created .env - edit it now (database password, MQTT host, TeslaMate network)."
fi
# Each file is checked on its own, so a run that failed half-way is repaired by running ./setup.sh again.
for f in fleet/public-key.pem fleet/tls-cert.pem; do
  [ -d "$f" ] && { echo "$f is a directory (Docker created it because the stack was started before setup). Remove it and run ./setup.sh again."; exit 1; }
done
umask 077
if [ ! -f fleet/private-key.pem ]; then
  # Tesla virtual key (prime256v1): the private key signs commands, the public key is published on your domain
  openssl ecparam -name prime256v1 -genkey -noout -out fleet/private-key.pem
  echo "Generated the Tesla private key in ./fleet (back it up; never share it)."
fi
if [ ! -f fleet/public-key.pem ]; then
  openssl ec -in fleet/private-key.pem -pubout -out fleet/public-key.pem
fi
if [ ! -f fleet/tls-key.pem ] || [ ! -f fleet/tls-cert.pem ]; then
  # self-signed certificate for the internal ui -> proxy connection (needs OpenSSL 1.1.1+ for -addext; on macOS install openssl from Homebrew)
  openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:secp384r1 -pkeyopt ec_param_enc:named_curve \
    -subj "/CN=proxy" -keyout fleet/tls-key.pem -out fleet/tls-cert.pem -sha256 -days 3650 \
    -addext "subjectAltName=DNS:proxy,DNS:localhost,IP:127.0.0.1"
fi
# only the proxy container reads the private keys (it has DAC_READ_SEARCH for exactly this); the UI mounts just the two public files
chmod 644 fleet/public-key.pem fleet/tls-cert.pem
chmod 600 fleet/private-key.pem fleet/tls-key.pem
cat <<'EOF'

Next steps:
  1. Edit .env, then:  docker compose up -d --build
  2. Open http://<host>:4100  (read-only dashboard works right away)
  3. To send commands to the car, follow docs/fleet-api.md
  Port 4100 listens on all interfaces of this host: set UI_BIND=127.0.0.1 in .env to keep it local, and set an app
  password (Settings) before exposing it anywhere. Without a password only private/local addresses are served.
EOF
