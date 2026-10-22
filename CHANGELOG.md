# Changelog

All notable changes are listed here, newest first. Versions follow [Semantic Versioning](https://semver.org): *major* = breaking change, *minor* = new features, *patch* = fixes.
Each version below becomes the text of its GitHub release and is shown in the app (Settings → Version & updates).

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
