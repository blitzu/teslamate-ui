# Security and internet access

This app can unlock your car and open your gate. Treat it like a password manager.

## What is exposed where

| Port | Purpose | Expose to the internet? |
|---|---|---|
| `4100` | The app (state, history, commands) | **No**, unless protected (below) |
| `4101` | Public listener: only Tesla's public key and the OAuth callback | Yes (needed for the Fleet API setup) |
| `4443` | Command-signing proxy | Never published; reachable only inside the Docker network |

The private key (`fleet/private-key.pem`) never leaves your host.

## Layers of protection

1. **PIN** — every command (`POST /api/cmd/*`) must carry your PIN. Set in **Settings → Command PIN** (or `scripts/set-fleet.sh`); stored in plain text in `.env.fleet`, so keep that file mode `600`.
2. **LAN is open by default.** Requests that arrive *through a proxy or tunnel* (they carry `X-Forwarded-For` / `Cf-*` headers) are treated as "internet" and are **refused** unless one of these is configured:
   * **Cloudflare Access** (recommended, below), or
   * **an app password** — `./scripts/set-password.sh` (login form; cookie valid 30 days; 5 wrong attempts per 10 min per IP).
3. HomeLink/gate and unlock actions ask for confirmation in the UI.

If you put a reverse proxy in front of port 4100 that does **not** add `X-Forwarded-For` (or a `Cf-*` header), the app cannot tell the request is external and treats it as LAN. Make sure your proxy adds it (most do), or keep 4100 off the proxy.

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

Enforced on the server; everyone still needs the command PIN.

## Hardening checklist

* Back up `fleet/private-key.pem` offline; if it leaks, remove the virtual key from the car (Controls → Locks → Keys) and regenerate.
* Use a PIN of 6+ characters; the PIN is separate from the app password.
* Keep `.env*`, `fleet/` and `data/` out of git (the provided `.gitignore` does that).
* Restrict the Tesla developer app to your domain/redirect URI only.
* Consider disabling HomeLink/unlock tiles if the app is shared with others (edit `static/app.js`).
