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
if [ ! -f fleet/private-key.pem ]; then
  umask 077
  # Tesla virtual key (prime256v1): the private key signs commands, the public key is published on your domain
  openssl ecparam -name prime256v1 -genkey -noout -out fleet/private-key.pem
  openssl ec -in fleet/private-key.pem -pubout -out fleet/public-key.pem 2>/dev/null
  # self-signed certificate for the internal ui -> proxy connection
  openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:secp384r1 -pkeyopt ec_param_enc:named_curve \
    -subj "/CN=proxy" -keyout fleet/tls-key.pem -out fleet/tls-cert.pem -sha256 -days 3650 \
    -addext "subjectAltName=DNS:proxy,DNS:localhost,IP:127.0.0.1" 2>/dev/null
  # only the proxy container reads the private keys (it runs as root, so 600 is enough); the UI mounts just the two public files
  chmod 644 fleet/public-key.pem fleet/tls-cert.pem
  chmod 600 fleet/private-key.pem fleet/tls-key.pem
  echo "Generated Tesla key pair and TLS certificate in ./fleet (back up fleet/private-key.pem; never share it)."
fi
cat <<'EOF'

Next steps:
  1. Edit .env, then:  docker compose up -d --build
  2. Open http://<host>:4100  (read-only dashboard works right away)
  3. To send commands to the car, follow docs/fleet-api.md
EOF
