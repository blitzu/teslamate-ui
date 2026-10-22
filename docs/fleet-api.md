# Enabling commands: Tesla Fleet API setup

Commands (lock, climate, charging, HomeLink, …) go through Tesla's official Fleet API, signed by your own *virtual key*. TeslaMate itself is not involved. You need:

1. a domain on HTTPS that serves your **public key** (and the OAuth callback),
2. a Tesla **developer app** (free),
3. the app authorised on your Tesla account,
4. the **virtual key** installed in the car.

Tesla's Fleet API has usage-based pricing with a free monthly allowance aimed at personal use; this app only calls it for commands and a few on-demand reads, so personal use stays tiny. Check Tesla's current terms.

## 1. Generate keys

```bash
./setup.sh
```

This creates `fleet/private-key.pem` (signs commands — **back it up, never share it**), `fleet/public-key.pem` and an internal TLS certificate for the proxy.

## 2. Publish the public key on your domain

Pick a domain or subdomain, e.g. `tesla.example.com`. Tesla requires the key at exactly:

```
https://tesla.example.com/.well-known/appspecific/com.tesla.3p.public-key.pem
```

The app serves that file (and the OAuth callback) on **port 4101** — nothing else is reachable there. Forward your HTTPS domain to `http://<host>:4101` with whatever you already use (Cloudflare Tunnel, Caddy, nginx, Traefik…). Example Caddyfile:

```
tesla.example.com {
    reverse_proxy <host>:4101
}
```

Verify: `curl https://tesla.example.com/.well-known/appspecific/com.tesla.3p.public-key.pem` prints a `-----BEGIN PUBLIC KEY-----` block.

> Do **not** forward your normal app port 4100 on this hostname unless you protect it (see [security.md](security.md)).

## 3. Create the developer app

At <https://developer.tesla.com> → create an app:

* **Origin / Allowed origin:** `https://tesla.example.com`
* **Redirect URI:** `https://tesla.example.com/auth/callback`
* **Scopes:** Vehicle Information (`vehicle_device_data`), Vehicle Commands (`vehicle_cmds`), Vehicle Charging Management (`vehicle_charging_cmds`)
* Note the **Client ID** and **Client Secret**.

## 4. Give the app its credentials

Open the app → **⚙ Settings** → *Command PIN* (set a PIN) and *Tesla Fleet API* (Client ID, Client Secret, domain, region) and save. Or, from a terminal:

```bash
./scripts/set-fleet.sh
```

It asks for Client ID, Client Secret (hidden), the domain, a **PIN** (the app asks for it before every command) and your region. Everything is written to `.env.fleet` (mode 600). Secrets never appear on screen.

## 5. Register, authorise, install the key

Open the app → **Car** page → the *Controls* card shows a checklist:

1. **Register domain with Tesla** — one-time call that tells Tesla your domain and public key.
2. **Connect Tesla account** — Tesla login/consent page; you return to your domain's `/auth/callback`.
3. **Install the virtual key in the car** — open `https://tesla.com/_ak/tesla.example.com` **on your phone with the Tesla app**, then confirm in the car by tapping your key card on the centre console when prompted.

When all steps are ticked the command tiles appear. Try *Flash lights* first.

## Notes

* Commands wake a sleeping car (takes a few seconds). Reading live state never wakes it: it comes from TeslaMate, and the few on-demand reads (Climate/Charging pages) only run when TeslaMate reports the car online.
* Vehicles with `vehicle_command_protocol_required` (all recent cars) **must** use the signing proxy — that is why `proxy` is part of the stack.
* Wrong region → 4xx/421 errors: re-run `set-fleet.sh` and choose the other region (`FLEET_BASE`).
* The app picks the VIN from TeslaMate's `cars` table.
