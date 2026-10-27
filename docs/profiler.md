# Profiler (live Fleet Telemetry)

The **Profiler** page streams 200+ internal vehicle signals live — charging (cell voltages, power, temperatures), drivetrain, climate, body, safety, navigation — in short, manual sessions, similar to Tessie's Profiler. Profiles: *Performance, Charging & battery, Climate, Body & lighting, Safety & security, Navigation & media, Turbo (everything)*.

## How it works

1. You pick a profile and a duration (5–30 min) and press **Start**. The app saves the car's current telemetry configuration, then sends a new one (the profile's fields at 1 s intervals, always keeping the base configuration: `SentryMode` plus, if you use them, `DoorState`, `Locked` and the window fields; see [docs/notifications.md](notifications.md)) through the signing proxy.
2. The car streams the fields to **your own Fleet Telemetry server**. A small forwarder ([tools/telemetry_forwarder.py](../tools/telemetry_forwarder.py)) pushes the decoded records to the app, which shows them live (table, sparklines, tiles) and records the session (CSV export).
3. When the time is up — or you press **Stop** — the app restores the previous configuration automatically.

Tesla applies the configuration when the car is awake and online. A sleeping car is not woken by this; **while a session runs the car will not sleep**, and Tesla may bill telemetry signals — keep sessions short.

The app corrects Tesla's field-by-field rejections automatically (fields that need a minimum delta get one; location fields are skipped if the `vehicle_location` scope is missing, and the skipped fields are listed in the session card).

## Requirements

* A running Fleet Telemetry server reachable by the car (mTLS ends in the telemetry server, so it cannot sit behind a Cloudflare Tunnel or similar), and the car already configured for it (hostname, port, CA). See Tesla's [fleet-telemetry](https://github.com/teslamotors/fleet-telemetry) docs. The server config needs `"json_log_enable": true`, `"transmit_decoded_records": true` and the `logger` for `V` records.
* The app's Tesla account authorised with `vehicle_device_data` (already part of the Fleet API setup). For location fields add the `vehicle_location` scope to your developer app and re-authorise.
* The forwarder on the telemetry host, pointing to the app:

```bash
export APP_INGEST_URL=http://<app-host>:4100/api/profiler/ingest
export APP_INGEST_TOKEN=<random secret>
python3 tools/telemetry_forwarder.py        # run it as a systemd service
```

Put the same secret in the app's `.env.profiler` (`INGEST_TOKEN='<random secret>'`, see `.env.profiler.example`), then `docker compose up -d`.

## Demo

On the public demo the Profiler runs a simulation with fictional values.
