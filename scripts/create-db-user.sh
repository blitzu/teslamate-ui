#!/usr/bin/env bash
# Creates a dedicated Postgres role for this app, so it does not use TeslaMate's owner account.
#   ./scripts/create-db-user.sh <teslamate-database-container>                  # read-only (history, statistics, everything except the Tessie import)
#   ./scripts/create-db-user.sh <teslamate-database-container> --allow-import   # also lets the Tessie import insert/delete its rows
# The generated password is printed ONCE on your terminal: put it in .env as DATABASE_USER=tessie_ui and DATABASE_PASS='...' and restart the app.
set -euo pipefail
DB_CONTAINER="${1:?usage: $0 <database-container> [--allow-import]}"
ALLOW_IMPORT=0
[ "${2:-}" = "--allow-import" ] && ALLOW_IMPORT=1
DB_ADMIN="${DATABASE_USER:-teslamate}"
DB_NAME="${DATABASE_NAME:-teslamate}"
PW="$(openssl rand -hex 24)"
psql_in() { docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -q -U "$DB_ADMIN" -d "$DB_NAME"; }

psql_in <<SQL
DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tessie_ui') THEN CREATE ROLE tessie_ui LOGIN; END IF; END \$\$;
ALTER ROLE tessie_ui PASSWORD '$PW';
GRANT CONNECT ON DATABASE "$DB_NAME" TO tessie_ui;
GRANT USAGE ON SCHEMA public TO tessie_ui;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tessie_ui;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO tessie_ui;
SQL
if [ "$ALLOW_IMPORT" = 1 ]; then
  psql_in <<'SQL'
GRANT INSERT, UPDATE, DELETE ON addresses, drives, positions, charging_processes, charges TO tessie_ui;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tessie_ui;
SQL
fi
MODE="read-only"
[ "$ALLOW_IMPORT" = 1 ] && MODE="read + Tessie import"
echo
echo "Role tessie_ui is ready ($MODE)."
echo "Put this in .env, then: docker compose up -d"
echo "  DATABASE_USER=tessie_ui"
echo "  DATABASE_PASS='$PW'"
