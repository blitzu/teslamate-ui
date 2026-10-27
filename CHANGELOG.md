# Changelog

All notable changes are listed here, newest first. Versions follow [Semantic Versioning](https://semver.org): *major* = breaking change, *minor* = new features, *patch* = fixes.
Each version below becomes the text of its GitHub release and is shown in the app (Settings → Version & updates).

## 1.5.2 - unreleased

### Fixes
- **Action needed if you use the Home Assistant webhook automation: the documented `clear` condition never worked.** The example in `docs/notifications.md` used `trigger.json.clear`; in a Home Assistant template that is the dictionary's own `clear()` method, so the condition was always false and Live Activities / notifications were never removed from the phone. Change it to `trigger.json['clear']` (the documentation is fixed).
- **Notifications on the phone now disappear when the event is over.** The "Cable connected", "Charging complete", "Opened while locked" / "Left open", "Low battery" and "Update available" notifications now carry a tag and are removed from the phone by themselves when the situation ends: cable unplugged, everything closed, battery back above 20 % or plugged in, update installed. This needs the notification automation in Home Assistant to handle `clear` (the example in `docs/notifications.md` already does).
- **The iPhone Live Activity could stay on the Lock Screen forever** when the app restarted (an update, a reboot) while it was showing, or when you switched the Live Activity off in Settings while one was visible. The app now clears it on the first check after a restart if there is nothing to show, and when you switch it off. After a restart it also clears any state notification whose situation is no longer true.
- A "Low battery" alert is no longer sent for a 0 % reading (not a real value).

## 1.5.1 - 2026-10-23

### New features
- **Tyre sets mounted in the past.** Choose the date a set was mounted (and removed) when you add it, or press **Set dates** on an existing set: the km it covered are calculated automatically from the car odometer on the morning of those days (TeslaMate history). For dates before the TeslaMate records you can type the km by hand. A set mounted without a removal date is the active one: the previously active set is removed on the same date, and a set mounted in the past ends where the next one starts. The tyre page now also shows the odometer at mounting and removal.

## 1.5.0 - 2026-10-23

### New features
- **Charging stats** (`#/chstats`, link on the Charges page): energy charged AC versus DC (with the DC share), sessions, average and peak speed and efficiency for each type, the **average DC speed by battery level** (0-10 %, 10-20 % ... with average, maximum and sample count), the same for AC, the battery level where you start and stop charging, and kWh per month. It works for any period (30/90 days, this year, last year, a custom range) and tag, like the lists.

- **New-version push goes to administrators only** (the Settings page it points to is admin-only) and says what to press: "Update now" when an updater is available, otherwise where to read what changed.

### Fixes
- **iPhone: the map was drawn over the side menu.** The map's internal layers sat above the menu, so opening the menu showed the map through it. Maps now stay below the menu and its backdrop.

## 1.4.0 - 2026-10-23

### New features
- **One-click updates, nothing to configure.** The stack now includes a tiny `updater` container. When a new version exists, **Settings → Version & updates** shows what changed and an **Update now** button: it downloads the new images, restarts the app (about a minute) and the page waits for the new version and reloads itself. The updater finds its project by itself, creates its own token in `./data/updater.token` (the app reads it from there), publishes no port and only runs `docker compose pull` and `up -d` for the app's own services. Nothing is updated unless you press the button; `UPDATER_AUTO_HOURS=24` in `.env` turns on an optional daily automatic update. It needs the Docker socket, which is root-equivalent on the host, so `docs/updates.md` explains how to remove it if you prefer to update by hand. Whatever updater you already set up (for example Watchtower) keeps priority.
- **"Check now"** stays one click away in the same section and always looks for a new version.
- The release workflow also publishes the updater image (`ghcr.io/blitzu/teslamate-ui-updater`).

### Upgrading from an older version
- You need one manual update to get the updater: `git pull && docker compose up -d --build`. After that, updates are one click.

## 1.3.0 - 2026-10-23

### New features
- **Pages and period filters for Drives and Charges.** Both lists show 50 items at a time (25/50/100/200) with a "load more" button, and can be limited to the last 30 or 90 days, this year, last year or a custom date range. Drives are paged on the server, so the page no longer loads every drive.
- **Tags for drives and charges.** Add tags (for example "Greece trip") from a drive or charge page, or select several items in a list and tag them at once; filter both lists by tag.
- **Journey overview map** (`#/journey`): a top view with the route, the charges and the stops between drives, for a whole trip (button on every drive), a date range, a few picked drives, everything with a tag, or the current period of the Drives list. It shows a summary (distance, driving time, energy, charging cost, stops) and the events in order.
- **Saved places with a price per kWh.** On a charge page, save the place with a price: every charge there, old ones included, gets the cost kWh × price. Priority: manual cost, then the real home cost (Home Assistant), then the saved place, then the TeslaMate cost. Nothing is written to TeslaMate.
- **Route replay: top view and north-up lock.** Two new buttons next to the zoom controls switch the replay between the tilted 3D view and a flat top view (3D/2D), and lock the map with north always up (N), which also disables rotating the map by hand. Your choice is remembered.
- **Google Maps links:** open the location of a charge, and the start and arrival of a drive, in Google Maps.

### Fixes
- **Live-location link: map tiles showed "Access blocked" (403).** The public page asked the browser to send no Referer, and OpenStreetMap's tile servers reject requests without one. The page now sends only its domain (never the path that contains the link's token).
- Dates now show the year when it is not the current one (a drive from 25 September 2023 no longer shows as "25 September"), in lists, details and the replay.

## 1.2.1 - 2026-10-23

### Fixes
- **Driving score was 0 on almost every drive.** Hard braking and acceleration were counted from every pair of neighbouring GPS points, so with points a quarter of a second apart and whole km/h speeds, normal 1-2 km/h steps looked like violent manoeuvres, and every sample counted again. They are now measured over a 1.5 s window (above about 3 m/s²), counted as episodes, and drives longer than 30 km get the penalty scaled down instead of always reaching 0.

## 1.2.0 - 2026-10-23

### New features
- **Import from Tessie: everything that is missing.** The import now brings every Tessie drive and charge that does not overlap one already in TeslaMate, before, between and after your TeslaMate data (the previous behaviour, only older than the first TeslaMate record, is still available as an option). Overlaps are detected with a few seconds of tolerance, so partly duplicated histories do not create duplicates.
- The check shows how many items fall before, between and after your TeslaMate data, and how many TeslaMate already has.
- The import can be run repeatedly; the ledger accumulates and "Undo import" removes everything the app imported.

## 1.1.0 - 2026-10-23

### New features
- **Backup of your TeslaMate data** (Settings → Data & features): a local SQLite copy of drives, positions, charging processes, charges, states, software updates, addresses, geofences and cars. It never copies your Tesla tokens.
  - Synced every 10 minutes; positions and charges are append-only, other tables are updated in place. Nothing is ever deleted from the copy, even if it disappears from TeslaMate.
  - A daily snapshot is kept (last 7). Download the copy or the app database from Settings (PIN required).
  - `tools/restore_backup.py` restores the data into a fresh TeslaMate database (dry run available, existing rows untouched).
- **Alerts** (`#/alerts`): charging stopped unexpectedly, plugged in but not charging (with the reason), not plugged in at night at home, low tyre pressure, rain with a window open (Open-Meteo, only while a window is open), hot cabin in Dog/Camp mode (critical), awake for no reason, slow tyre leak. Quiet hours let only critical alerts through; every alert is logged.
- **Sleep guard:** attributes each awake period to Sentry, a command (app, rule or BLE), a user, a software update or "unknown", per day. It never wakes the car to measure. A daily check raises an alert when the car stays awake without a reason.
- **Maintenance** (`#/service`): service items with a km and/or month interval (presets for rotation, cabin filter, brake fluid, calipers, seasonal tyres, ITP, RCA, vignette, CASCO), a "done" log with date, odometer and cost, and reminders when something is due soon or overdue.
- **Tyre sets:** summer/winter sets with mounted dates and mileage per set, pressure history normalised to 20 °C and slow-leak detection from the pressure trend.
- **Software tracker:** every update with its date and version, Wh/km 30 days before and after, and the release notes when the car is awake.
- **Trips** (`#/trips`): drives grouped into trips by the gap between them (1-12 h, configurable) with distance, energy, charging stops and cost, a map and a detail page.
- **Reports** (`#/reports`): a weekly report (Monday) and a monthly report (1st) with distance, energy, charging cost, solar share, idle drain, records, the petrol/diesel comparison and the change versus the previous period. Generate one on demand (last week, last month, this year) and send it to your notification channels.
- **"What would it have cost on PZU":** your home AC charging priced with the Romanian day-ahead market (15-minute prices from energy-charts.info, ECB exchange rate), compared with your fixed tariff and with charging only in the cheapest hours of the night. Add-on per kWh, VAT and the night window are configurable; the PZU price is energy only.
- **Telegram notifications:** your own bot (token and chat id in Settings, stored like the other secrets) and a choice of which kinds of messages go there.
- **Native push notifications (Web Push):** no Home Assistant needed; Android, desktop and iPhone (PWA on the Home Screen, iOS 16.4+). Standard VAPID keys generated on first use, only the push services of Google, Mozilla, Apple and Microsoft accepted, expired devices removed automatically, choice of message kinds for all devices.
- **Guided phone notifications** (`#/push`, for every role except viewer): on iPhone it walks you through adding the app to the Home Screen, then one big button turns notifications on and sends a test; it explains how to unblock notifications if they were denied. A hint chip on the Car page stays until notifications are on.
- **In-car / tablet screen** (`/incar.html`): a display-only page with big tiles (battery, range, state, temperatures, lock, odometer, tyres), live updates, screen wake lock, night dimming and a kiosk mode (`?kiosk=1`, `?car=`, `?dim=`).
- **Live-location link with ETA:** a public page with a map, arrival time and optionally the destination, valid from 15 minutes to 48 hours and revocable at any time. Only a hash of the 32-byte token is stored (the link is shown once), at most 10 active links, requests and wrong-token attempts are rate-limited, and the position is hidden by default while the car is at home. Served on the public port.
- **Car handoff** (`#/handoff`, admin): Valet mode, Guest mode and/or a speed limit for a set time, then a report of what was driven (trips, km, top speed, places). The car's 4-digit PIN is typed each time, goes straight to Tesla and is never stored or logged; a notification tells you when the time is up.
- **Zone, speed and schedule rules** (`#/zones`, admin): notify when the car goes over a speed, enters or leaves a TeslaMate geofence, or moves outside a schedule (for example 23:00-06:00). Cooldown per rule; a rule can be limited to the time of a handoff.
- **Settings grouped into categories:** General, Notifications, Connections, Security and Data & features, in a bar that stays visible and remembers the last category.
- **New command types** in the Fleet command layer: valet mode, guest mode and speed limit set/activate/deactivate.

### Fixes and improvements
- The app reloads itself when a new version was deployed while it was suspended in memory (iOS kept showing the old version); `index.html` is never cached and its scripts and styles carry a build id.
- Address fields in "In-car screen" and the live-location link now select on tap (inline handlers were blocked by the Content-Security-Policy).

### Under the hood
- New `features/` package: modules register their own routes, background tasks, MQTT hooks, notification sinks, public routes and tables in `data/app.db` (SQLite); a module that fails to start is skipped without taking the app down.
- Every command is recorded in a command log with who issued it (user, rule, system); car state changes are recorded as events (used by the sleep guard and alerts).
- 74 automated tests (up from 22), including the Web Push encryption checked against the RFC 8291 test vector.

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
