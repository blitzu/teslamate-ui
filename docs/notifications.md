# Notifications

The server watches TeslaMate's MQTT stream and raises these events:

| Setting | Triggered when |
|---|---|
| `plugged` — Cable connected | `plugged_in` goes false → true |
| `charge_done` — Charging complete | `charging_state` becomes `Complete` |
| `door` — Door / trunk open | a door, trunk, frunk or window opens **while the car is locked**, or stays open for more than 5 minutes while parked |

Each event is stored in an in-app history (Car page → Notifications, last 60) and, if `NOTIFY_WEBHOOK` is set, POSTed as JSON:

```json
{"title": "🔌 Cable connected", "message": "Tesla: cable connected (battery 62%).", "kind": "plugged"}
```

Toggles are per type in the app (stored in `data/notify.json`). The *Send test* button fires a `test` event.

## Home Assistant example

1. Create `.env.notify` (copy `.env.notify.example`) with a long random webhook id:

```
NOTIFY_WEBHOOK=http://homeassistant.local:8123/api/webhook/tesla_app_REPLACE_WITH_RANDOM_STRING
```

2. Automation (YAML mode):

```yaml
alias: Tesla app notifications
triggers:
  - trigger: webhook
    webhook_id: tesla_app_REPLACE_WITH_RANDOM_STRING
    allowed_methods: [POST]
    local_only: true
actions:
  - action: notify.mobile_app_YOUR_PHONE
    data:
      title: "{{ trigger.json.title | default('Tesla') }}"
      message: "{{ trigger.json.message | default('') }}"
mode: queued
```

3. `docker compose up -d`, then press *Send test* in the app.

Set the app's public address in **Settings → Display → App address** (or `APP_URL` in `.env.notify`): every notification then carries a `url`, so tapping it opens the right page of the app (charges, dashboard, automations…).

## iPhone Live Activities (Home Assistant Companion app)

With the Home Assistant Companion app for iOS (iOS 17.2+, Core 2026.7+, Live Activities enabled in the app) the app can show a **Live Activity** on the Lock Screen / Dynamic Island: *charging* (progress bar towards your charge limit, power and countdown to full), *door/trunk open*, *plugged in but not charging*, *charging complete*, and optionally *driving*. One activity (tag `tesla_status`) is updated in place and closed automatically.

It uses the same webhook: payloads with a `data` object carry `live_update`, `tag`, `progress`, `chronometer`…; `{"clear": true, "tag": "tesla_status"}` closes it. Extend the Home Assistant automation like this:

```yaml
actions:
  - choose:
      - conditions: "{{ trigger.json['clear'] | default(false) }}"
        sequence:
          - action: notify.mobile_app_YOUR_PHONE
            data:
              message: clear_notification
              data:
                tag: "{{ trigger.json.tag | default('tesla_status') }}"
    default:
      - action: notify.mobile_app_YOUR_PHONE
        data:
          title: "{{ trigger.json.title | default('Tesla') }}"
          message: "{{ trigger.json.message | default('') }}"
          data: "{{ trigger.json.data | default({}) }}"
```

**Important:** write `trigger.json['clear']`, not `trigger.json.clear`. In Home Assistant templates `.clear` on a dictionary is the dictionary's own `clear()` method, so the condition is never true and the Live Activity (and the notifications below) would stay on the phone forever. Versions of this page before v1.5.2 showed the dotted form; if you copied it, change it now.

Toggle it in the app (Notifications → *iPhone Live Activity*, and *while driving*). Apple limits activities to 8 hours and throttles frequent updates.

**Notifications that disappear by themselves.** The cable, charging-complete, door, low-battery and update notifications carry a `tag` (`tesla_plugged`, `tesla_charge_done`, `tesla_door`, `tesla_low_batt`, `tesla_update`) and the app sends `{"clear": true, "tag": "…"}` when the situation is over (cable unplugged, everything closed, battery recovered, update installed). The `clear` branch of the automation above is what removes them from the phone, so keep it in your automation.

**Alerts clear themselves too.** Each alert (`tesla_alert_rain_window`, `…_charge_stopped`, `…_plugged_not_charging`, `…_not_plugged_night`, `…_tpms_low`, `…_cabin_hot`) is tagged as well, so a repeat replaces the old one, and the app sends the same `clear` when the cause is gone (window closed, charging resumed or cable removed, plugged in, pressure back to normal, cabin cooled down).

**Only away from home.** *Notifications → No status notifications at home* stops the cable and door/frunk notifications and the "open" and "plugged" Live Activity cards while the car is in your home geofence (same pattern as the "not plugged in tonight" alert). Alerts and the charging card are unaffected.

**Live Activity does not start?** iOS can keep an old activity with the same tag whose push token is gone; then neither updates nor new cards show. The app ends the old one first (`clear`, then a start 2 s later). Apple also limits how many activities an app may *start* remotely in a period (the "push-to-start budget"); updating a running one is free, so repeated start/stop in tests can exhaust it for a while.

**Doors, frunk, windows and lock while the car sleeps.** TeslaMate stops polling the car after it has been idle (`suspend_after_idle_min`, then `suspend_min`), so MQTT keeps the old values. If you run a Fleet Telemetry server and have the Profiler's ingest set up, add `DoorState`, `Locked`, `FdWindow`, `FpWindow`, `RdWindow` and `RpWindow` to the car's telemetry configuration (1 s interval; they are sent only on change): the app reads them all the time and the cards/notifications follow the car immediately, wherever it is. Tesla bills telemetry per signal sent (see the Fleet API billing page); these change a few dozen times a day.

## Command buttons on notifications

Regular notifications (cable connected, charging complete, door open) carry `actions` (buttons: *Start charging*, *Stop charging*, *Release cable*, *Turn climate on*, *Lock*). Home Assistant fires `mobile_app_notification_action` with the action id; add an automation that runs the matching command, e.g. through the ESP32 BLE entities (`switch.tesla_ble_charger`, `lock.tesla_ble_doors`, `climate.tesla_ble_climate`). **Use the Fleet API entities as a fallback** (e.g. the Home Assistant *Tesla Fleet* integration: `switch.tesla_charge`, `lock.tesla_lock`, `climate.tesla_climate`) when the ESP32 is not connected, and for **releasing the cable always use the Fleet cover** (`cover.tesla_charge_port_door`): a BLE key with the *charging manager* role is not allowed to open the charge port. Live Activities cannot have buttons (an iOS limitation). Toggle: Notifications → *Command buttons*.

## Other targets

Any endpoint that accepts a JSON POST works (n8n, Node-RED, a small relay to Telegram/ntfy/Pushover…). The payload has `title`, `message`, `kind`.
