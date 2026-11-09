# Home Assistant integration (optional)

Link the app to Home Assistant (HA) to get:

1. **Local commands over Bluetooth** through an ESP32 running [esphome-tesla-ble](https://github.com/yoziru/esphome-tesla-ble) (or a fork exposing the same entities). When the ESP32 is connected to the car, commands (lock, climate, charging on/off, charging amps/limit, sentry, frunk/trunk, charge port, flash/honk, heated steering, seats, cabin overheat protection…) go **locally, free, and without the Fleet API**. If BLE is unavailable or reports a failure, the app falls back to the Fleet API automatically.
2. **Energy source of each charge** (estimated): how much of a charge came from the grid vs solar/home battery, using your inverter's grid-import sensor from HA history.

Without HA nothing changes: everything keeps working through the Fleet API.

## Set up

1. In HA: your profile → Security → *Long-lived access tokens* → create one. Prefer a dedicated, non-admin HA user for this token (it can call services).
2. Open the app → **⚙ Settings → Home Assistant**, fill the URL, token, entity prefix (and the optional grid/PV sensors), save, and press *Test connection*. Or run:

```bash
./scripts/set-ha.sh
```

   It asks for the HA URL, the token (hidden), the ESP32 entity prefix (default `tesla_ble`, i.e. entities like `lock.tesla_ble_doors`, `switch.tesla_ble_charger`, `binary_sensor.tesla_ble_status`) and optionally the grid-import and PV power sensors (W). Values are stored in `.env.ha` (mode 600).

3. After a command, the toast shows `· BLE` when it went through Bluetooth.

## Entities used

| Command | HA entity (prefix `tesla_ble`) |
|---|---|
| lock / unlock | `lock.tesla_ble_doors` |
| climate on/off, temperature, defrost | `climate.tesla_ble_climate` |
| charging start/stop | `switch.tesla_ble_charger` |
| charging amps / limit | `number.tesla_ble_charging_amps` / `number.tesla_ble_charging_limit` |
| sentry, heated steering | `switch.tesla_ble_sentry_mode`, `switch.tesla_ble_heated_steering` |
| frunk, trunk, charge port | `cover.tesla_ble_frunk`, `cover.tesla_ble_trunk`, `cover.tesla_ble_charge_port_door` |
| flash, horn, wake | `button.tesla_ble_flash_lights`, `button.tesla_ble_sound_horn`, `button.tesla_ble_wake_up` |
| front seats, cabin overheat protection | `select.tesla_ble_front_*_seat_climate`, `select.tesla_ble_cabin_overheat_*` |
| availability / confirmation | `binary_sensor.tesla_ble_status`, `sensor.tesla_ble_last_command` |

HomeLink, schedules, rear seats and windows are always sent through the Fleet API.

## Energy source

Set `HA_GRID_IMPORT` (grid import power, W) and `HA_PV_POWER`. The charge detail page then shows *"X% from solar / home battery"* and the **real cost** of a home charge (grid share × `PRICE_GRID`; solar and a battery charged by the sun cost 0).

**Origin tracking (home battery).** When the battery power and charge level sensors are also available, the app follows where the energy comes from minute by minute (*proportional tracing*): everything the sources produce (panels + grid import + battery discharge) goes into one shared bus that every consumer (the house, the car, the battery charging, the export) draws from in the same proportion. The grid share of the bus is `(import + discharge × g) ÷ (PV + import + discharge)`, where `g` is the fraction of the energy stored in the home battery that came from the grid: when the battery charges, `g` mixes with the grid share of that minute; when it discharges, `g` stays. So the sun costs 0, a battery charged by the sun costs 0, and a battery charged from the grid (for example an evening top-up) or direct grid power costs your grid price. The charge page also shows how much of the grid part went through the battery.

* Sensors: for a Solarman/Deye inverter the others are derived from the grid-import sensor name (`..._grid_import_power` → `..._battery_power`, `..._battery`, `..._battery_capacity`). Otherwise set `HA_BATT_POWER` (W), `HA_BATT_SOC` (%) and `HA_BATT_KWH` (usable kWh, a number or a sensor). `HA_BATT_SIGN=+` if your battery power is positive while charging (the default expects negative).
* Home Assistant keeps about 10 days of history, so the app fills in what it can on first start and then samples every 30 seconds into its own database (`src_min`, about 30 MB per year). Charges older than the stored minutes keep the older estimate (grid import during the charge, capped at the energy the car used).
* It starts from "the battery is all solar" (`g = 0`), so the first days after the first start can under-count grid energy still sitting in the battery. A single inverter/battery is assumed. `GET /api/energysrc` shows the coverage and the current grid share of the battery.

## Automations

The *Automations* page (Car page → Automations) runs server-side rules, no PIN at run time (creating/removing them needs the PIN):

* open the gate (HomeLink) when the car enters a TeslaMate geofence,
* set a charge limit when the cable is plugged in (optionally at a given geofence),
* start the climate at a given time on selected days.

Each rule has a 10-minute cooldown. Commands use BLE when available, otherwise the Fleet API. Set `TZ` in `.env` for time-based rules.
