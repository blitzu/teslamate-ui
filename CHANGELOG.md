# Changelog

All notable changes are listed here, newest first. Versions follow [Semantic Versioning](https://semver.org): *major* = breaking change, *minor* = new features, *patch* = fixes.
Each version below becomes the text of its GitHub release and is shown in the app (Settings → Version & updates).

## 1.1.0 - 2026-10-23

### Features
- **Backup of your TeslaMate data:** local SQLite mirror (drives, positions, charges, states, updates, geofences, settings; never tokens), synced every 10 minutes, never deletes, daily snapshots, download from Settings and a tested restore tool.
- **Alerts and sleep guard:** charging stopped, plugged but not charging, not plugged at night, low tyre pressure, rain with a window open, hot cabin, tyre leak, awake without reason; the sleep guard attributes awake time to Sentry, commands, user, update or unknown.
- **Maintenance and tyres:** service reminders by km and months (RCA, ITP, vignette presets), tyre sets with mileage and pressure history, software update tracker with Wh/km before and after.
- **Trips:** drives grouped into trips with charging stops and cost.
- **Reports:** weekly and monthly summaries, and a "what would it have cost on the day-ahead market (PZU)" report with the cheapest-hours comparison.
- **Telegram and native Web Push notifications** (no Home Assistant needed, works on the iPhone PWA).
- **In-car / tablet screen** (`/incar.html`, display only).
- **Live-location link** with ETA: expiring, revocable, hides home by default, served on the public port.
- **Car handoff:** Valet, Guest and speed limit with a timer and a report; the car PIN is never stored.
- **Zone, speed and schedule rules** (notification only).

### Under the hood
- New `features/` package: modules register their own routes, background tasks, MQTT hooks, notification sinks and tables in `data/app.db`; a failing module is skipped.
- Every command is recorded in a command log with who issued it (user, rule, system); car state changes are recorded as events.

## 1.0.0 - 2026-10-23

First versioned release.

### Features
- Live car state over TeslaMate MQTT, drives and charges history with maps and charts, statistics, battery health, sleep and idle-drain reports.
- Remote commands through the Tesla Fleet API (signing proxy) or locally over BLE through Home Assistant; climate page, charging control (amps, schedules, scheduled departure), HomeLink, automations.
- Animated 3D route replay with video export; animated open doors/frunk/trunk on the car picture.
- Live telemetry profiler (Fleet Telemetry) with profiles, grouped signals and CSV export.
- Notifications to a webhook (Home Assistant), iOS Live Activities and action buttons.
- Charge costs: editable total cost and provider per session, provider filter with total kWh and cost, real cost from grid import, energy source (solar/grid).
- Comparison with a petrol/diesel car using the fuel price of each day (fetched and stored daily).
- Import of Tessie history into TeslaMate (dry run, one transaction, undo).
- Settings, roles (admin/family/viewer), PIN, app password, Cloudflare Access, Romanian and English.
- Versions: the app shows its version, checks GitHub for new releases, notifies you once per release and can trigger an updater (for example Watchtower).

### Security and reliability
- Atomic data files with `.bak` copies; PIN throttling; password protects the local network once set; role allowlist; sessions bound to the password; Host/Origin checks.
- Strict Content-Security-Policy with bundled Leaflet and MapLibre (no CDN); unprivileged read-only container with dropped capabilities; database connection cap and timeouts; real health check; supervised background threads; audit log.
- Unit and HTTP tests in CI; pinned dependencies and base images; published container images.
