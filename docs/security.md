# Security and internet access

This app can unlock your car and open your gate. Treat it like a password manager.

## What is exposed where

| Port | Purpose | Expose to the internet? |
|---|---|---|
| `4100` | The app (state, history, commands) | **No**, unless protected (below) |
| `4101` | Public listener: Tesla's public key, the OAuth callback and live-location share links (`/share/<token>`, only while a link you created is active) | Yes (needed for the Fleet API setup) |
| `4443` | Command-signing proxy | Never published; reachable only inside the Docker network |

The private key (`fleet/private-key.pem`) never leaves your host.

## Layers of protection

1. **PIN** — every command (`POST /api/cmd/*`) and the sensitive settings changes (configuration, rules, import, updates, backups, sharing) must carry your PIN; notification preferences do not. Set in **Settings → Command PIN** (or `scripts/set-fleet.sh`; minimum 6 characters). It is kept in `/data/config.json` (mode `600`) or in `.env.fleet` — keep those files private. **Wrong PINs are throttled:** 5 per 10 minutes per client address and 30 in total, then the server answers `429` until the window passes.
2. **App password.** Set one in **Settings → Internet access & roles** (or `./scripts/set-password.sh`, minimum 12 characters). Once a password exists it protects **everything, also on your local network**: you sign in once per device (cookie valid 30 days; 5 wrong attempts per 10 min per address). *Until a password is set, the LAN stays open* so you cannot lock yourself out — the app shows a red notice on the dashboard and in Settings while that is the case.
3. **Requests that arrive through a proxy or tunnel** (they carry `X-Forwarded-For` / `Cf-*` headers) are treated as "internet" and are **refused** unless **Cloudflare Access** (recommended, below) or the app password above authorizes them.
4. HomeLink/gate and unlock actions ask for confirmation in the UI.

Your data files live in `/data` and are written atomically (temporary file + `fsync` + rename); the previous version is kept next to each file as `*.bak`, and a corrupted file is copied to `*.bad` and replaced by its backup instead of silently resetting your settings.

If you put a reverse proxy in front of port 4100 that does **not** add `X-Forwarded-For` (or a `Cf-*` header), the app cannot tell the request is external and treats it as LAN — so **set an app password** (step 2): with a password, even such requests need to sign in. Better still, bind port 4100 to your LAN address only (`"192.168.x.y:4100:4100"` in `docker-compose.yml`).

## Cloudflare Access (recommended)

Put the app behind Cloudflare Zero Trust and let the server verify Cloudflare's signed login token, so you sign in once (e-mail one-time code, passkey, SSO…):

1. Create a Cloudflare Tunnel hostname, e.g. `car.example.com` → `http://<host>:4100`.
2. Zero Trust → Access → Applications → *Self-hosted*: domain `car.example.com`, policy *Allow* for your e-mail only.
3. From the application note the **Application Audience (AUD) tag**; your **team domain** looks like `yourteam.cloudflareaccess.com`.
4. Create `.env.access` (copy `.env.access.example`):

```
ACCESS_TEAM=yourteam.cloudflareaccess.com
ACCESS_AUD=<the AUD tag>
ACCESS_EMAIL=you@example.com
```

5. `docker compose up -d`. The server validates the `Cf-Access-Jwt-Assertion` header (signature, audience, issuer, e-mail). Without a valid token (and without an app password) internet requests are rejected.

Keep your tunnel hostnames for the app (`car.example.com`) and for the Tesla key (`tesla.example.com` → 4101) separate; only the latter must be reachable without a login.

## Roles (sharing with family)

With Cloudflare Access you can let other people in and limit what they can do. Add their e-mails to the Access policy, then set in `.env.access`:

```
ACCESS_EMAIL=you@example.com                       # the administrator
ROLES=wife@example.com:family,guest@example.com:viewer
```

* `admin` — everything (also anyone on your LAN or using the app password).
* `family` — lock/unlock, climate, temperature, seats, steering heater, defrost, charge start/stop, flash/honk, wake, sentry. No frunk/trunk, windows, HomeLink, charge schedules/amps, automations.
* `viewer` — read-only.

Enforced on the server with an **allowlist**: only `admin` can do everything, `family` only the commands listed above, everyone else (including a typo such as `ROLES=a@b.c:editor`) is treated as `viewer`. A valid Cloudflare Access token **without an e-mail** (a service token) is `viewer`. Everyone still needs the command PIN.

Sessions made with the app password are bound to that password: **changing the password signs out every device**.

## Other protections

* JSON `POST`s must be sent as `Content-Type: application/json` (blocks simple cross-site form posts); bodies over 1 MB are refused.
* The same command (same parameters) is not sent twice within a few seconds (HomeLink 8 s, frunk/trunk 6 s, charge start/stop 5 s, lock/unlock/flash/honk 3 s): a double tap or a retry cannot reverse the effect of a toggle command.
* Changing the Home Assistant address requires entering the access token again, so the stored token is never sent to a new address you did not confirm.
* Viewers cannot change notification settings or force a live read from the car.
* If the BLE path times out for a toggle command (frunk/trunk), the app reports *"may have been executed"* instead of silently retrying on the Fleet API.

## Container and browser hardening (built in)

* The app container starts as root **only** to hand `data/` to an unprivileged user (uid 10001) and then drops root before doing anything else; the root filesystem is read-only, all Linux capabilities are dropped (a few are kept just for that one step), memory and process limits are set, logs rotate.
* The private Tesla keys are mounted only in the signing proxy, never in the app container.
* The browser gets a strict `Content-Security-Policy` (scripts only from the app itself — Leaflet and MapLibre are bundled, no CDN), `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy`. If you embed the app in a page or use another tile/weather host, adjust it with the `CSP` environment variable.
* The app uses at most `DB_MAX_CONN` (8) simultaneous Postgres connections with a 20 s statement timeout, and `MAX_SSE` (60) live-stream connections, so a burst of requests cannot exhaust TeslaMate's database.
* `/api/health` reports the database state; Docker's `HEALTHCHECK` uses it. Background threads (MQTT, automations, profiler watch, fuel price, public listener) are restarted automatically if they crash.
* Commands, wrong PINs and wrong passwords leave an `audit:` line (with role and address) in `docker compose logs ui`.
* For least privilege on the database use `./scripts/create-db-user.sh` (read-only role).

## Host and origin checks

From the local network (requests that did not come through Cloudflare or a proxy) the app only answers when the `Host` header is an IP address, `localhost`, a single-label or `.local`/`.lan` name, the host of `APP_URL`, or listed in `ALLOWED_HOSTS` (comma-separated). A malicious web page that makes its own domain resolve to your home IP (DNS rebinding) is therefore refused with `421`. `POST`s from a browser must carry an `Origin` equal to the page they come from.

## Hardening checklist

* Back up `fleet/private-key.pem` offline; if it leaks, remove the virtual key from the car (Controls → Locks → Keys) and regenerate.
* Use a PIN of 6+ characters; the PIN is separate from the app password.
* Keep `.env*`, `fleet/` and `data/` out of git (the provided `.gitignore` does that).
* Restrict the Tesla developer app to your domain/redirect URI only.
* Consider disabling HomeLink/unlock tiles if the app is shared with others (edit `static/app.js`).
