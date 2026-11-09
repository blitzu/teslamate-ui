# Extra features (v1.1)

Everything here lives in the `features/` package: each module registers its own routes, background tasks and tables, and a module that fails to start is skipped without taking the app down. The modules keep their own data in `data/app.db` (SQLite), separate from TeslaMate.

## Backup of your TeslaMate data

Settings → *TeslaMate data backup*. The app keeps a local SQLite copy (`data/teslamate_backup.db`) of the TeslaMate tables that hold your history: cars, addresses, geofences, drives, positions, charging processes, charges, states, updates and settings. It never copies `tokens` (your Tesla credentials).

- Synced every 10 minutes; positions and charges are append-only, other tables are upserted. **Nothing is ever deleted from the copy**, even if it disappears from TeslaMate.
- A daily snapshot is kept in `data/backups/` (last 7).
- Download the copy or the app database from the same section (PIN required).
- Restore into a fresh TeslaMate database: start TeslaMate once on it (so it creates the schema), stop it, then `python3 tools/restore_backup.py <backup.db> --dsn postgresql://… [--dry-run]`. Rows that already exist are left alone (`ON CONFLICT DO NOTHING`), except `settings` and `car_settings` (language, units, base URL), which are updated; pass the connection string in `TESLAMATE_DSN` to keep the password out of `ps`; it needs a superuser to switch off foreign-key checks while inserting. After a restore you reconnect your Tesla account in TeslaMate (tokens are not copied).

## Alerts and sleep guard (`#/alerts`)

Rules: charging stopped unexpectedly, plugged in but not charging (with the reason), not plugged in at night at home, low tyre pressure, rain with a window open (Open-Meteo, coordinates rounded to 0.1°, only while a window is open), hot cabin in Dog/Camp mode (critical), awake for no reason, slow tyre leak. Quiet hours let only critical alerts through. Alerts go through every configured channel (webhook, push, Telegram).

The **sleep guard** attributes each awake period to Sentry, a command (app/rule/BLE), a user, a software update, or *unknown*. It never wakes the car to measure.

## Maintenance, tyres, software (`#/service`)

- **Maintenance:** items with a km and/or month interval (RCA, ITP, vignette, tyre rotation, brake fluid, cabin filter…), "done" log with cost and odometer, reminders when due soon (less than 10 % of the interval or 30 days left).
- **Tyres by set:** summer/winter sets, mounted dates, per-set mileage, pressure history normalised to 20 °C and slow-leak detection (needs TPMS data in TeslaMate positions).
- **Software:** every update with date, version, Wh/km 30 days before/after, and release notes when the car is awake (Fleet API, read only).

## Lists, tags, journey map and saved prices (v1.3)

- **Drives and Charges lists** show 50 items at a time (25/50/100/200, "load more") and can be limited to the last 30/90 days, this year, last year or a custom range; both also filter by tag. Dates show the year when it is not the current one.
- **Tags** (stored in the app database): add them on a drive or charge page, or press *Select* in a list, pick several items and tag them in one go.
- **Journey overview** (`#/journey/...`): a top-view map with the route, the charges and the stops between drives. Open it from the *Map* button of any drive (the whole trip), from the Drives list (the current period or filter), from a selection of drives, or by tag/date range on the page itself. Charges are included when they fall between the first departure and the last arrival (or carry the tag); a stop is a pause of at least 5 minutes between two drives that is not a charge. At most 300 drives per map.
- **Saved places with a price per kWh:** on a charge page, save the place with a name, radius and price. Every charge inside the radius, old ones included, gets the cost kWh × price. Priority: manual cost, real home cost (Home Assistant), saved place, TeslaMate cost. Nothing is written to TeslaMate.
- **Route replay:** the 3D/2D button flattens the camera into a top view, and the N button keeps north always up (and turns off map rotation). Both settings are remembered in the browser.
- **Tessie archive** (`#/tessie`, appears after a Tessie import): what TeslaMate cannot keep: the energy used while parked (with sentry/climate), the battery capacity over time, the alerts the car generated; and a *Tessie data* card on each imported drive (autopilot km, estimated peak power/regen). See [import-tessie.md](import-tessie.md).
- **Charging stats** (`#/chstats`): AC versus DC energy and share, average/peak speed per type, the average DC speed by battery level, the level where you start and stop charging, and kWh per month, for the chosen period.
- **Idle energy use** (`#/idleuse`, linked from Parked): what climate / cabin preheat, battery heating, Sentry, the car being awake and plain sleep cost while the car is neither driving nor charging. Per function: kWh, hours, average kW, estimated cost, share, how much is *beyond what the car would use asleep*, and the 30-day projection; plus the share of all the energy used and a stacked per-day chart. The car reports no figure per function, so the energy is derived from TeslaMate data: between two points where the car is not driving or charging, the drop in ideal range × the car's efficiency (the formula TeslaMate uses for a drive), assigned by the climate and battery-heating flags, the Sentry intervals of the event log and awake/asleep. Estimates: one 5-minute interval is noisy, daily and weekly sums are stable. Cost = the average price of the energy in the battery over the period (the drive-cost calculation). Charging TeslaMate never closed is cut at the next activity (24 h at most).
- **Google Maps links** for the location of a charge and for the start and arrival of a drive.

## Drive in progress (`#/live` and the Car page)

While the car is moving, the Car page's map shows the route driven so far, the car (an arrow pointing the way it heads) and, when the car has a navigation route, the destination as a pin; under it the distance, duration, battery, energy used, average Wh/km and an estimated cost. A card on top shows the destination, the distance left and the arrival time, and opens `#/live`, which adds battery and speed charts. Everything refreshes every 5 seconds. The destination, distance left, arrival time and charge on arrival come from TeslaMate's `active_route` (only published while a navigation route is set); the line from the car to the pin is straight, because the exact route is not published.

## Trips (`#/trips`)

Drives grouped into trips by the gap between them (1–12 h, configurable), with distance, energy, charging stops and cost, and the same map as the drive page.

- **Interactive timeline** (`#/timeline/<trip>`, from the trip page): the trip on a map with an *At cursor* card (speed, altitude, battery, distance, net energy used, energy charged) and swipeable cards for the section you select (*General*: average and top speed, stops, moving time; *Altitude*: minimum, maximum, ascent, descent; *Energy*: net used, regen, charged, Wh/km, battery). Under the map a chart of altitude and battery with stops and charges shaded: drag the two handles to select a section (the map zooms to it and the cards are recalculated), touch the chart to move the cursor.
- **Compare trips** (`#/compare/<id>,<id>,<id>`): up to three trips on one map. The cars start together and you see where each was after the same time since departure (speed, distance, elapsed time, battery and net energy next to each car; slider, pause, 1x-8x), plus a table of distance, duration, moving time, speeds, net energy, Wh/km, regen, energy charged on the way, battery and stops.
- **Similar trips** (in Compare): once the main trip is picked, the page suggests trips that start and end at about the same places (within 1 km, also in the opposite direction) with a similar distance (±20%). Each one shows the date, the distance difference, Wh/km, duration and average temperature (and how it differs from yours) plus badges: *same road* / *other road* (how much of the GPS routes overlap), *reverse*, and how close it is to your time of year (those come first). Filter by All / Other road / Same road and tap one to add it to the comparison. Computed from your TeslaMate drives only; nothing leaves the app.
- **Moving time and time stood still** (Compare statistics, Timeline): the time is split into moving (rolling, over 3 km/h), stationary in traffic (the drive is on but the car stands: lights, queues), stopped between drives (stops, charging), the share of time moving, the number of traffic stops over 15 s and the longest one, and two average speeds (while moving, and overall).
- **Fullscreen maps:** the map of Compare (with its play and speed controls), the trip Timeline and the live drive have a ⛶ button in the top right corner; Esc or the same button closes it.
- **Choose your map:** every map has a 🗺 button in the top right corner: OpenStreetMap dark (default) or light, and the OpenFreeMap vector maps Dark, Dark blue, Colourful, Bright and Minimal. The choice is kept on the device. Vector maps load only when you pick one and fall back to OpenStreetMap without WebGL or network.
- Net energy in both is the power of the GPS points integrated over time (consumption minus regen), so it can differ a few percent from the figure TeslaMate stores for the drive.

## Reports and "what PZU would have cost" (`#/reports`)

- Weekly (Monday) and monthly (1st) reports: distance, energy, charging cost, solar share, idle drain, records, ICE-car comparison and change versus the previous period. Generated on demand too, and sent to your notification channels.
- **PZU report:** your home AC charging priced with the Romanian day-ahead market (15-minute prices from [energy-charts.info](https://energy-charts.info), Fraunhofer ISE), converted with ECB rates (frankfurter.dev), compared with your fixed tariff and with "charge only in the cheapest hours of the night". PZU is the **energy price only**: set the add-on per kWh and the VAT to approximate a dynamic offer. It is an estimate, not advice to change contract.

## Notifications: Telegram and push

- **Telegram:** create a bot with @BotFather, paste the token and your chat id in Settings, choose which kinds of messages go there. The token is stored like the other secrets and never returned by the API.
- **Push (no Home Assistant needed):** Settings → *Push notifications* → *Enable on this device*. Standard Web Push (VAPID keys generated on first use, stored in `data/app.db`); works on Android, desktop and iPhone (add the app to the Home Screen first, iOS 16.4+). Only the push services of Google, Mozilla, Apple and Microsoft are accepted as endpoints. If you also keep the Home Assistant webhook you will get each notification twice: turn off the kinds you don't want on one of the two.

## In-car / tablet screen (`/incar.html`)

A display-only page (no commands) with big tiles: battery, range, state, temperatures, lock, odometer, tyres. Live over the existing stream, keeps the screen awake where supported, dims at night. `?kiosk=1` hides the buttons, `?car=2` picks another car, `?dim=on|off|auto`.

## Live-location link (Settings → *Live-location link*)

A public page with a map and the arrival time for someone waiting for you.

- Served on the **public** port (`PUBLIC_PORT`, the one that already serves the Fleet public key), so it needs a public domain; set `SHARE_BASE` or use the Fleet domain. If you put a geo-fence or access policy in front of that hostname, recipients must be allowed through it.
- The token is 32 random bytes; only its SHA-256 is stored, so the link is shown **once**. Links expire (15 min to 48 h), can be revoked, are limited to 10 active, and token guessing is rate-limited per IP.
- The page receives only: position, heading, speed, ETA and (optionally) the destination name. By default the position is hidden while the car is inside your home geofence.
- **Comparison (optional):** when you create the link you can pick up to two saved trips. The page then also receives, for each, a thinned route (about 300 points of time, position, speed, battery and distance, **without any place name**) and, while you drive, the time since your current drive started, so it can show where each saved trip was after the same time. While *Hide the position while at home* is on, 600 m are cut from both ends of those routes (the direction you leave in can still be guessed). Without a comparison nothing changes.
- Anyone holding the link sees the position while it is valid: treat it like the position itself.

## Car handoff (`#/handoff`, admin only)

Valet mode, Guest mode and/or a speed limit for a set time, then a report of what was driven (trips, km, top speed, places). Uses the Fleet signed commands (`set_valet_mode`, `guest_mode`, `speed_limit_*`).

- The car's 4-digit PIN is typed in each time, goes straight to Tesla and is **never stored or logged**. Because of that the app cannot switch Valet/limit off by itself when the timer ends: it notifies you, and you end the handoff with the PIN (or switch it off in the car).
- Zone rules can be restricted to "only during a handoff".

## Zone, speed and schedule rules (`#/zones`, admin only)

Notification-only rules: speed over N km/h, enters or leaves a TeslaMate geofence (by name, regex), or the car moves outside a schedule such as 23:00–06:00. Each rule has a cooldown and can be limited to a handoff.

## External services used by these features

| Service | Used for | What is sent | By |
|---|---|---|---|
| Open-Meteo | rain-with-window alert | coordinates rounded to 0.1° | server |
| energy-charts.info, frankfurter.dev | PZU report | the dates needed; the currency code | server |
| frankfurter.dev (ECB), open.er-api.com | converting station prices to your currency | only the currency codes | server |
| Overpass (OpenStreetMap) | “Find the station” | the coordinates of one charge, only when you press the button | server |
| OpenFreeMap | vector map backgrounds, only when you pick one | style, tile and font requests from the browser (and your IP address); no key | browser |
| AmpWhere (on by default, can be switched off) | station tariffs, see docs/costs.md | nothing: one anonymous download per day of the station list of each country where you charge | server |
| Telegram Bot API | Telegram notifications | the notification text | server |
| Google / Mozilla / Apple / Microsoft push services | Web Push | an encrypted payload (RFC 8291) | server |
