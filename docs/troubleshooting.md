# Troubleshooting

**The app shows "DEMO" data / "TeslaMate database not responding".**
Check `docker compose logs ui`. The app must be on TeslaMate's Docker network: `TESLAMATE_NETWORK` in `.env` must match `docker network ls`, and `DATABASE_HOST` must be the database *service name* on that network (usually `database`). If the database password contains `$`, put it in single quotes.

**No live data (values only update every minute or are missing).**
MQTT is not reachable or not enabled in TeslaMate. Set `MQTT_HOST` (service name of the broker, usually `mosquitto`) and credentials; the badge/health endpoint `/api/health` shows `"mqtt": true` when connected. Tyre pressures are not provided by TeslaMate's MQTT/DB on most setups and show "—".

**`unauthorized_client` when connecting the Tesla account.**
The Client Secret reached the container mangled. Secrets must be in single quotes inside `.env.fleet` (the provided script does that). Verify lengths without printing: `docker exec tessie-ui sh -c 'printf %s "$FLEET_CLIENT_SECRET" | wc -c'`.

**Registering the domain fails.**
Tesla must be able to fetch `https://<domain>/.well-known/appspecific/com.tesla.3p.public-key.pem` — test it with `curl` from outside your network. The origin/redirect URI in the developer app must match the domain exactly. Check the region (`FLEET_BASE`).

**Commands fail with "public key has not been paired with the vehicle".**
Install the virtual key: open `https://tesla.com/_ak/<domain>` on your phone with the Tesla app and confirm in the car with your key card.

**Commands time out (408) / the car "doesn't answer".**
The car is asleep with poor connectivity (weak Wi-Fi/cellular). The app wakes it before commands and retries for ~30 s; try again once the car is awake.

**Commands return 403 "PIN greșit".**
The PIN you typed differs from `APP_PIN`. The browser remembers the last PIN; the app clears it on a wrong PIN and asks again.

**The route replay map is blank or very slow.**
It needs WebGL and internet access to `cdnjs.cloudflare.com` (MapLibre) and `tile.openstreetmap.org`. Disable aggressive content blockers for the site.

**I changed files in `static/` and nothing happens.**
The image copies `static/` at build time: `docker compose up -d --build ui`, then hard-refresh the browser (Ctrl+F5) or reopen the installed PWA.

**Sleep card shows "asleep" when TeslaMate says "offline".**
By design: on many cars TeslaMate reports `offline` while the car is actually asleep. The card treats `asleep` and `offline` as sleep. If your car is often truly offline (no signal), the numbers include those periods.
