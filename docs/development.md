# Development

## Layout

```
server.py            HTTP server, MQTT listener, TeslaMate SQL, Fleet API client, notification engine
static/index.html    shell (loads extra.js then app.js)
static/app.js        core SPA: router, Car/Drives/Charges/Stats pages, command tiles, i18n (RO source strings, EN dictionary `EN`)
static/extra.js      Climate page, charging control, notifications card, 3D route replay (MapLibre)
static/app.css       all styles
static/car-default.svg, icon*.png, manifest.webmanifest   assets / PWA
features/            optional modules (alerts, service, reports, backup, share...): each has init(S)
updater/             the "Update now" helper container
importer.py          Tessie gap import
tools/               restore_backup.py, telemetry forwarder
tests/               unit and HTTP tests: `python -m unittest discover -s tests`
Dockerfile, Dockerfile.proxy, Dockerfile.updater, docker-compose.yml, setup.sh, scripts/
```

No build step: plain JS/CSS served as-is.

## Run locally with fictional data

```bash
pip install paho-mqtt psycopg2-binary "pyjwt[crypto]"
DEMO_ONLY=1 PORT=4110 python server.py      # http://localhost:4110 — fake car, drives, charges; commands disabled
```

Without `DEMO_ONLY`, but with no reachable TeslaMate database, the app also falls back to demo data.

## HTTP API (JSON)

| Endpoint | Purpose |
|---|---|
| `GET /api/state` | cars + live state + sleep info |
| `GET /api/stream` | Server-Sent Events with live MQTT changes |
| `GET /api/drives`, `/api/drive/<id>`, `/api/trip/<id>` | drive list, GPS points, trip (consecutive drives with gaps < 2 h) with stops |
| `GET /api/charges`, `/api/charge/<id>`, `/api/charge_row/<id>`, `/api/drive_row/<id>` | charge history and curve; one exact row by id (with provider and manual/real/effective cost) |
| `POST /api/charge/meta` | set/clear the manual total cost and the provider of a charge (admin + PIN) |
| `GET /api/fuel`, `POST /api/fuel/refresh` | daily fuel price history / fetch now (admin + PIN) |
| `GET /api/activity`, `/api/caps` | unified timeline; detected equipment |
| `GET/POST /api/config`, `POST /api/config/test`, `GET /api/config/ha_entities` | settings from the app (admin; changes need the PIN) |
| `POST /api/import/tessie`, `GET /api/import/tessie/status` | Tessie import (dry-run, import, undo) |
| `GET /api/profiler`, `/api/profiler/stream`, `/api/profiler/diag`, `/api/profiler/export.csv`, `POST /api/profiler/start`, `/stop`, `/ingest` | live telemetry profiler |
| `GET /api/version`, `/api/changelog`, `POST /api/update/check`, `POST /api/update/apply` | installed/latest version and release notes, entries of `CHANGELOG.md`, check now, call the configured updater (admin + PIN) |
| `GET /api/health` | `{ok, db, mqtt, threads}`; 503 when the database does not answer (used by the Docker `HEALTHCHECK`) |
| `GET /api/overview`, `/api/battery` | statistics |
| `GET /api/vdata?car=` | climate/charge settings and schedules read from the car (only when TeslaMate says it is online; never wakes it) |
| `GET /api/notify`, `POST /api/notify/settings`, `POST /api/notify/test` | notification history/settings |
| `GET /api/sleep?days=`, `/api/health_battery`, `/api/charge_solar/<id>` | sleep & idle drain report, battery health, energy source of a charge |
| `GET/POST /api/rules` | automations (POST needs the PIN) |
| `POST /api/cmd/<name>` | command (header `X-Pin`, body `{"car":1,"arg":…}`); names in `CMDS` / `build_cmd()` in `server.py` |
| `GET /api/fleet/status`, `/api/fleet/login`, `POST /api/fleet/register` | Fleet API onboarding |

## Adding a command

1. Check the REST parameter names in `vehicle-command`'s [`pkg/proxy/command.go`](https://github.com/teslamotors/vehicle-command/blob/main/pkg/proxy/command.go).
2. Add it to `build_cmd()` (validate and clamp every client-supplied value).
3. Add a tile/control in `static/app.js` or `static/extra.js` and its strings to the `EN` dictionary.

## Translations

UI strings are Romanian in the source and translated through the `EN` dictionary (`app.js`) and the `X(ro, en)` helper (`extra.js`). Adding a language = extending `tr()`/`X()`; PRs welcome.

## Contributing

Issues and PRs are welcome. Keep it dependency-light (no front-end build step), never log secrets, and test against the demo mode before opening a PR.
