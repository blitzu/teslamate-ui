# Home Assistant integration (optional)

Link the app to Home Assistant (HA) to get:

1. **Local commands over Bluetooth** through an ESP32 running [esphome-tesla-ble](https://github.com/yoziru/esphome-tesla-ble) (or a fork exposing the same entities). When the ESP32 is connected to the car, commands (lock, climate, charging on/off, charging amps/limit, sentry, frunk/trunk, charge port, flash/honk, heated steering, seats, cabin overheat protection…) go **locally, free, and without the Fleet API**. If BLE is unavailable or reports a failure, the app falls back to the Fleet API automatically.
2. **Energy source of each charge** (estimated): how much of a charge came from the grid vs solar/home battery, using your inverter's grid-import sensor from HA history.

Without HA nothing changes: everything keeps working through the Fleet API.

## Set up

1. In HA: your profile → Security → *Long-lived access tokens* → create one. Prefer a dedicated, non-admin HA user for this token (it can call services).
2. Run:

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

## Energy source estimate

Set `HA_GRID_IMPORT` (grid import power, W) and optionally `HA_PV_POWER`. The charge detail page then shows *"X% from solar / home battery"*: `1 − grid import energy during the charge ÷ energy the car used`. It is an estimate — house load drawn from the grid during the same window inflates the grid part.

## Automations

The *Automations* page (Car page → Automations) runs server-side rules, no PIN at run time (creating/removing them needs the PIN):

* open the gate (HomeLink) when the car enters a TeslaMate geofence,
* set a charge limit when the cable is plugged in (optionally at a given geofence),
* start the climate at a given time on selected days.

Each rule has a 10-minute cooldown. Commands use BLE when available, otherwise the Fleet API. Set `TZ` in `.env` for time-based rules.
