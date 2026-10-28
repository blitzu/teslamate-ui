# Changelog

All notable changes are listed here, newest first. Versions follow [Semantic Versioning](https://semver.org): *major* = breaking change, *minor* = new features, *patch* = fixes.
Each version below becomes the text of its GitHub release and is shown in the app (Settings → Version & updates).

## 1.8.0 - 2026-10-28

### New features
- **Direct internet access with HTTPS (Let's Encrypt), for people without Cloudflare - all from Settings → Security.** Two ways: a free **DuckDNS** subdomain (the app keeps it pointing at your IP and validates with a DNS-01 TXT record: no port 80, nothing to open for validation) or **your own domain** whose IP your ISP or router already keeps up to date (`home.go.ro` from Digi, No-IP, a domain you own; validated with TLS-ALPN-01 on port 443, no DNS access needed, not for CGNAT). The app gets the certificate by itself, renews it when under 30 days are left and serves the whole app over HTTPS on the public port. You only add one router rule (external 443 to the app's public port). It needs the app password and cannot be switched on without it; the HTTPS listener ignores proxy headers, answers only for your domain, checks `Origin`, sends HSTS, limits connections and serves nothing without a password. Full guide: docs/internet-access.md. (While it is on, the public port stops answering plain HTTP - do not use it together with a Cloudflare Tunnel on that port.)
- **Settings instead of `.env`.** *Addresses allowed from the local network* (`ALLOWED_HOSTS`), *AmpWhere countries* and *Tesla images for the car* (`TESLA_RENDERS`) are now in the interface (the `.env` values still work as defaults), and the `421 Unknown address` message tells you exactly which address was refused and where to add it.

## 1.7.0 - 2026-10-28

### New features
- **🔎 Find the station of a charge.** A button on the charge page finds the charging station at that place and suggests the provider, its **AC and DC tariffs** and the tariff matching your charge. Choosing a station **saves immediately** (no Save button); you can switch tariff with one tap or type a **manual tariff**, and the page shows what the charge would have cost at that tariff next to your real cost (useful when charging was free). Your cost is never changed by this. The provider of the linked station is used in lists and filters unless you set one yourself.
- **Station sources.** It uses **AmpWhere** first (**on by default**; switch it off in Settings → Display → Station lookup or with `AMPWHERE=0`): richer data with a price per kWh, for **all 14 countries AmpWhere covers** (Romania, Bulgaria, Lithuania, Greece, Hungary, Czech Republic, Slovakia, Croatia, Slovenia, Italy, Cyprus, Moldova, Turkey, Serbia): only the countries where you actually charge are downloaded (`AMPWHERE_COUNTRY=auto`, or a fixed list like `ro,hu`). When it is off or has nothing nearby, it uses **OpenStreetMap** (the coordinates of one charge are sent when you press the button). It is not an official, documented API (same request their public map makes; no key, no guarantees, not affiliated; the owner of AmpWhere told the maintainer he has no problem with it), so it can change or stop working (then OpenStreetMap is used). It downloads each country list **once a day at most**, searches **locally** (your coordinates never leave your server), identifies itself and backs off for a day if refused. Details and the responsibility note: docs/costs.md.
- **Currency from a list, prices converted automatically.** The app currency is now picked from a list (Settings → Display; old free-text values keep working). Station prices in any other currency are **converted to it automatically** (ECB rates; MDL, RSD, UAH and the like via Exchange Rate API, cached 12 h) and shown with the original price in brackets, e.g. `4.21 RON/kWh (289 HUF)`; the estimated cost uses the converted price. Only currency codes are sent.
- **Automatic link.** New charges are linked to their station when TeslaMate closes them, and **on the first start after updating, your existing charges are linked automatically in the background, once** (charges at home or without a station nearby stay as they are; your costs are never touched). An administrator can redo it any time with `POST /api/stations/autolink`.

## 1.6.0 - 2026-10-28

### New features
- **Cost of every drive.** The drive list and the drive page now show what the drive cost, calculated from the *price of the energy it actually used*: every charge adds its kWh at its own price and drives use the oldest energy first (FIFO), so the money of a charge ends up on the drives that used it. Energy from before the first charge in TeslaMate came from the factory and is free. The drive page also shows the average price per kWh used, the **petrol equivalent in l/100 km** (what a litre-based car would have to burn to cost the same, at that day's fuel price), the cost **with a petrol car** and the saving (these two need the petrol car's consumption in Settings → Display). A `~` means part of the energy comes from charges without a price. How it works: docs/costs.md. The **comparison with a petrol car in Stats and in the weekly/monthly reports** now uses the same drive costs, so the electric cost matches the drives and trips lists (before it was the average price of the charges in the period × the kWh used).
- **Energy cost on trips too.** The Trips list shows each trip's cost (with the period total on top), and the trip page and the map page (Journey) have the same cost card: cost, average price per kWh used, petrol equivalent in l/100 km, cost with a petrol car and the saving.
- **Provider dropdown.** On a charge, *Provider* is now a list with every provider used so far (set by you or recognised from the place), *Automatic*, and *➕ New provider…* to type a new name.
- **"How much did it cost?" notification after a charge.** When a charge ends and no price is known for it (no manual cost, tariff or saved place price), the app sends a notification that opens that charge so you can enter the cost, which also makes the drive costs exact. It is sent once per charge and disappears once you enter the cost. Switch: Settings → Notifications (also a kind for web push, off by default for Telegram).

## 1.5.6 - 2026-10-28

### Fixes
- **The currency (and other Display settings) could get stuck on the default.** Settings → Display is pre-filled with the values in use, including the default currency `€`, and saving that section (even just to change the app address) sent *all* of them back. The app then stored `€` and kept it above `CURRENCY=RON` in `.env`, so the euro never went away. Now only the fields you actually change are saved. **If you are already affected**, open Settings → Display, type your currency (for example `RON`) and save once; the value is then kept.

## 1.5.5 - 2026-10-28

### Fixes
- **The updater remembered a finished self-update as still running.** After it replaced its own image it corrected its state only in memory, so the state file stayed on "running" and any later restart (a reboot, for example) wrongly reported "updater restarted with the new image" again. The corrected state is now written back right away. The update itself was never affected.

## 1.5.4 - 2026-10-27

### Fixes
- **"Update now" and "Check now" did nothing on a fresh install.** Every button in Settings that sends a request needs the app PIN, and until you set one the app answered *"PIN wrong or not configured"* — so anyone who had not created a PIN could not update from the app (the updater itself works: tested from 1.5.2 to 1.5.3 with the published images). Both buttons now work for the administrator while no PIN is set; once a PIN exists they ask for it like every other command.

### New features
- **The car picture now shows more of the car's state.** On the top-down photo the app draws, live and animated: **Sentry** (red rings pulsing around the car), **charging** (glow on the charge port and a cable running out of the car, with a green flow while charging and a calm green when complete, grey when only plugged in; an orange ring when the flap is open without a cable), **climate** (warm or cool waves in the cabin depending on the outside temperature), **front/rear defrost**, **Dog / Camp mode** glyph, and the whole picture dimmed while the car **sleeps** (with "z z"; TeslaMate's `offline` counts as sleeping, like the "Asleep for…" card), with a blue ring while **updating**. Doors, frunk, trunk and windows keep opening on the real photo as before.
- **3/4 view of the car (Model 3 Highland and Model Y Juniper).** A **Top / 3/4** switch above the car picture shows Tesla's real front-left three-quarter render of your car (body, paint, wheels) with the state drawn on it: the hood, the left doors and the trunk are highlighted when open (a note appears for right-side doors, which are on the far side), a dashed line along the windows when one is open, Sentry rings on the ground, the charge port glow and a cable, climate waves above the roof, Dog/Camp glyph, "z z" and a dimmed car while it sleeps, an update ring, and pressure badges on the two visible wheels (all four are listed below). The choice is remembered on the device. If the image cannot be loaded, the app goes back to the top view. **These pictures are Tesla's, loaded by your browser from Tesla's servers, so the published version is off by default: set `TESLA_RENDERS=1` in `.env` to turn the 3/4 view on** (only Model 3 Highland and Model Y Juniper are supported; nothing is sent to Tesla otherwise).
- **Better stand-in picture when there is no `car.png`:** for a **Model 3 Highland** and a **Model Y Juniper** the app now asks Tesla's configurator for the current body, base wheels and your paint (Pearl White, Stealth Grey, Quicksilver and Ultra Red for the 3; those plus Solid Black and Deep Blue for the Y), already cropped to the car. Other paints fall back to the nearest valid one; other models keep the old picture. The old request returned the pre-2024 Model 3.

## 1.5.3 - 2026-10-27

### New features
- **The updater now updates itself**, as the very last step (after `ui` and `proxy`, so a problem with its own new image can never interrupt the app update). It pulls its own image and a helper container recreates it; the new instance shows the status of the run it came from (kept in `./data/updater.state.json`). Set `UPDATER_SELF=0` in `.env` to switch it off. The updater container now also runs with a **read-only filesystem** (it writes only to `./data` and a `/tmp` tmpfs). **To get the new `read_only` setting, fetch the new `docker-compose.yml`** (the updater does not change compose files); the self-update itself works with the old file too.
- **Alerts now go away when the cause is gone** (rain with a window open: the window is closed; charging stopped / plugged but not charging: charging resumes or the cable is removed; not plugged in tonight: plugged in or driving away; low tyre pressure: pressure back above the threshold; hot cabin: temperature back below it). Alert notifications on the phone carry a tag, so the same alert replaces the old one instead of stacking, and after an app restart the stale ones are swept once. (They used to stay until you swiped them away.)
- **"No status notifications at home"** switch in Notifications: cable connected and door/frunk-open notifications, and the "open" and "plugged" Live Activity cards, are not sent while the car is in your home geofence (the same pattern as the "not plugged in tonight" alert, default `acas|home`). Alerts and the charging card are not affected. Off by default.
- **Settings → Internet access & roles → Sign out all devices** ends every password session at once (password sessions were stateless: only a password or `SESSION_SECRET` change could end them). Session cookies now also carry a random nonce.

### Security
- **Without an app password, the LAN stays open, but only for private, loopback and link-local addresses.** A request that reaches port 4100 directly from a public address (a router port-forward, a cloud host with the port open) is now refused until a password is set. `setup.sh` and the docs explain `UI_BIND=127.0.0.1` to keep the port on the host only.
- Unexpected internal errors (database, file, library exceptions) are no longer sent to the browser; the client gets a general message and the details stay in the app log. Messages written for the user (for example "the Tesla account is not authorised") are still shown.
- `POST /api/push/test` is limited to one test every 10 seconds.

### Fixes
- Car handoff (valet / guest / speed limit) now uses the car selected in the app, and the page shows only that car's handoffs (it always used car 1).
- **The Live Activity (iPhone card) now starts reliably.** iOS can keep an old card with the same tag whose push token is gone; updates and new cards with that tag then never show. Before a card starts "from nothing" the app now ends the old one first (2 s earlier; ending does not use up the push-to-start budget).
- **Doors, frunk, trunk, windows and lock now come from the car itself (Fleet Telemetry), anywhere.** If a telemetry server is configured (the Profiler's ingest), the app also reads `DoorState`, `Locked` and the four window fields from the same stream, all the time and not only during a Profiler session, and feeds them through the same path as MQTT. The car sends them the moment they change, wherever it is and even when TeslaMate has stopped polling it. Needs these fields in the car's telemetry config (billed by Tesla per signal sent; they are sent only on change). The Profiler's "back to base" configuration should include them too. Values such as `{"doorValue": {...}}` are now shown as an object in the Profiler instead of a text.
- **Frunk, trunk and lock changes now show up while the car sleeps** (with the ESP32 BLE link configured in Home Assistant). TeslaMate stops asking the car once it is asleep or "suspended", so MQTT kept the old values and an opened frunk, or a closed one, was not noticed for minutes: neither the app nor the Live Activity card changed. The app now also reads the BLE entities (`cover.<prefix>_frunk`, `cover.<prefix>_trunk`, `lock.<prefix>_doors`) every 15 s and feeds any change through the same path as MQTT (the car is not woken). The delay now is the ESP32's own refresh interval.
- A trip can chain up to 30 drives (it was cut at 12, unlike the Journey page).
- The daily fuel price is stored under the app's local date (`TZ`), not the server's.
- Small layout fixes: left/right safe-area padding in landscape, the sticky category bar in Settings no longer slides under the top bar, rows of 3-4 buttons wrap instead of overflowing on narrow phones.
- The documentation in Romanian (`README.ro.md`) is brought up to date with the English one.

### Tests
- New tests for the sleep guard report (including a Sentry period that started before the window), the PZU analysis (cost, cheapest night, offline fallback), the restore tool (order, conflict rules, DSN from the environment, dry run) and the updater (self-update, state across restarts). Tests no longer depend on the order they run in (each test restores what it changed in the server module).

## 1.5.2 - 2026-10-27

### Fixes
- **Action needed if you use the Home Assistant webhook automation: the documented `clear` condition never worked.** The example in `docs/notifications.md` used `trigger.json.clear`; in a Home Assistant template that is the dictionary's own `clear()` method, so the condition was always false and Live Activities / notifications were never removed from the phone. Change it to `trigger.json['clear']` (the documentation is fixed).
- **Notifications on the phone now disappear when the event is over.** The "Cable connected", "Charging complete", "Opened while locked" / "Left open", "Low battery" and "Update available" notifications now carry a tag and are removed from the phone by themselves when the situation ends: cable unplugged, everything closed, battery back above 20 % or plugged in, update installed. This needs the notification automation in Home Assistant to handle `clear` (the example in `docs/notifications.md` already does).
- **The iPhone Live Activity could stay on the Lock Screen forever** when the app restarted (an update, a reboot) while it was showing, or when you switched the Live Activity off in Settings while one was visible. The app now clears it on the first check after a restart if there is nothing to show, and when you switch it off. After a restart it also clears any state notification whose situation is no longer true.
- A "Low battery" alert is no longer sent for a 0 % reading (not a real value).
- **Audit pass: security hardening.** A wrong-PIN attempt is now counted inside the same lock as the check, so parallel requests can no longer get past the 5-attempt limit; viewers can no longer probe (or burn) the PIN; the app refuses to be framed by other sites (`frame-ancestors 'none'` + `X-Frame-Options`); outgoing requests never follow redirects (an `Authorization` header can't leak to another host); backup downloads are created mode 600; `/api/overview` and `/api/changelog` limit their parameters. POST errors now answer 400/404 instead of 500.
- **Alerts raised during quiet hours are no longer lost.** The cooldown used to start even when the alert was only logged, so a low-pressure or open-window alert first seen at 23:05 stayed silent for days. Now it is retried every ~10 minutes and sent when the quiet hours end (logged once). "Alerts enabled = off" now really silences every alert (including the slow tyre leak and "awake for no reason"), and the slow tyre leak has its own switch. "Plugged in but not charging" is skipped for 6 hours after you stopped the charging yourself.
- **Sleep guard**: a Sentry/"user present" state that started before the 24-hour window is now taken into account, so a fully awake day with Sentry on is no longer reported as "unexplained" every morning.
- **Reports**: the monthly report summed only the last 30 idle intervals (now all of them); it compares with the previous *calendar* month; "best consumption" ignores negative values (downhill drives); a missed weekly/monthly report is generated when the app is back, and a failed one is retried instead of skipped. "Short wakes" no longer count ordinary drives, and the sleep per-day split uses your local midnight.
- **Statistics**: total charging cost and the daily cost bars use the same cost as the Charges list (manual > real > saved place price > TeslaMate); average consumption divides by the km of drives that have range data; the ICE comparison no longer shows a negative "saving" when no fuel price is known; battery degradation needs at least 16 charges (no more overlapping samples); the last point of a route / charging curve is no longer dropped. Charging stats: 80 % now falls in the same bucket at start and end, months follow your timezone, the efficiency ignores sessions without consumed-energy data, the tag filter applies, and the power-by-level query only reads the chosen period.
- **PZU**: the average price is divided by the energy that actually had a price, hourly prices work, weekend exchange rates are cached, a network error falls back to the cache, and the "cheap night" window is correct for 0-7 style hours.
- **Tyres and service**: a set mounted retroactively closes the earlier open set even when a later set exists (no more double-counted km); a 1-month interval is no longer "soon" the day after it was done; slow-leak detection is more sensitive (0.008 bar/day).
- **Backup / restore**: the backup now includes `car_settings`, the restore tool brings back language/units/base URL (`settings` and `car_settings` are updated, not skipped), a crash mid-snapshot no longer leaves a truncated "finished" snapshot, and one failing table no longer aborts the rest.
- **Tessie import**: odometer values in miles are no longer stored as km when a drive has too few points (the unit found on other drives is used, otherwise the odometer is left empty); drives/charges without a battery level are skipped and counted; "Undo" also works when only the crash-recovery ledger exists, and cannot run during an import.
- **Journey** now shows a tag that only has charges; the push notification of one alert no longer replaces another (own tag per alert); module routes (valet, handoff...) log the user in the command log instead of "system"; zone rules ignore empty alternatives ("a|") and a stale retained speed after a restart; the events/command log cleanup also runs shortly after a restart; a live-location link keeps the home hidden when the geofence blinks out for a moment.
- **Interface**: tags on the charge page work; the Charges filters keep working when the list is empty; the Car page no longer jumps while live data arrives and stops redrawing after you leave it; a 403 for the role is no longer shown as "wrong PIN" (and no longer deletes the saved PIN); saving offline no longer leaves "Saving…" forever; saving a setting keeps the scroll position; the journey page loads once; the tag you typed in the selection bar is kept; the "Update now" progress check stops when you leave Settings; the PIN hint says 6 characters.
- **Handoff**: if turning Valet / the speed limit off fails (wrong PIN, car asleep) the handoff stays open so you can retry, or end it anyway (you then switch it off in the car).
- **Service and tyres**: negative or infinite numbers are refused; a service or tyre check dated in the past takes the odometer of that day; a removed set without a km value no longer keeps growing; the odometer uses the live value instead of scanning the whole positions table.
- **Consistency**: the activity timeline, trips and journey now show the same charging cost as the Charges list (including the real cost) and no longer stop at 300 / 1000 / 2000 rows; reports and PZU filter by date in SQL.
- **Housekeeping**: creating or revoking a live-location link is recorded in the command log; expired links and old handoff warnings are cleaned up; a rejected Cloudflare Access token is remembered for a minute (no certificate refetch or log flood); the unauthenticated health endpoint no longer shows the version or thread names; the public demo refuses module admin routes; imported places without text get a proper name.
- **Restore tool** reads the connection string from `TESLAMATE_DSN` (the password stays out of `ps`); `scripts/set-fleet.sh` enforces the 6-character PIN; documentation corrected (public port, PIN scope, three packages, project layout).
- **Packaging**: the signing proxy can read the keys created by `./setup.sh` as a normal user; `setup.sh` repairs a half-finished run and shows OpenSSL errors; the updater passes `APP_UID`, times out stalled connections and removes a stuck helper container; "Update now" reports an unreachable updater instead of success; the release workflow moves `:latest` only after all three images were pushed (and never for `-rc` tags); CI checks all JavaScript files and builds the updater image; the app reports its build commit; `UI_BIND` lets you publish the app on one interface only.

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
