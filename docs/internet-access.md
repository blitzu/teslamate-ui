# Direct internet access: HTTPS with Let's Encrypt (DuckDNS or your own domain)

For people who do not use Cloudflare. Everything is configured in the app (**Settings → Security → Direct internet access**), nothing in `.env`, no reverse proxy, no terminal.

## Two ways to get the domain

| | **DuckDNS** (default) | **My own domain** |
|---|---|---|
| Domain | free `yourname.duckdns.org` | any name that already points at your public IP: `home.go.ro` from Digi, No-IP, a domain you own... |
| Who keeps the IP up to date | the app (every 5 minutes) | your ISP / router (the app never touches DNS) |
| How the certificate is validated | **DNS-01**: a TXT record written through DuckDNS | **TLS-ALPN-01**: Let's Encrypt connects to port 443 of your domain |
| What you type | subdomain + DuckDNS token | the full domain |
| Ports | **any** external port → app (e.g. 8443 → 4101; then open `https://name.duckdns.org:8443`) | external **443** → app (Let's Encrypt only validates this way on 443) |

Both then do the same: **renew by themselves** when less than 30 days are left (one attempt at most every 12 hours) and serve the whole app over **HTTPS on the public port** (`PUBLIC_PORT`, default 4101, the one already published by `docker-compose.yml`), plus the Tesla public key, the OAuth callback and share links as before.

## What you need

1. DuckDNS: a free account on [duckdns.org](https://www.duckdns.org), a subdomain and its **token**. Own domain: just the name, already pointing at your public IP.
2. A **password** for the app (Settings → Security → *Internet access & roles*). Without it the option cannot be turned on, and the HTTPS listener serves nothing.
3. A router rule: **external TCP 443 → the server's LAN IP, port 4101** (or your `PUBLIC_PORT`). That is the only thing opened. With DuckDNS the external port can be **any other** (for example 8443 if your provider blocks 443): the certificate is validated through DNS, not through a port, and you just add the port to the address. With your own domain the validation needs external 443 (a Let's Encrypt rule), at least while the certificate is obtained and renewed.

## Steps

1. Settings → Security → *Direct internet access*: switch it on, pick the mode, type the subdomain + token (DuckDNS) or the domain (own). The e-mail is optional (Let's Encrypt expiry notices).
2. **Save.** If there is no certificate yet, the app requests it by itself; the status box shows each step (DuckDNS IP, DNS TXT record, validation, certificate, HTTPS active). It takes about a minute. *Get the certificate now* retries by hand.
3. Add the router rule, then open `https://masina.duckdns.org` from outside your network.

Tip: tick **test certificate (staging)** first if you want to try the whole chain without Let's Encrypt's rate limits (browsers will flag that certificate as untrusted); untick it and save again for the real one.

## Own domain: what to know

* **It must already resolve to your public IP.** The status box shows what DNS answers and your public IP (looked up once in a while at `api.ipify.org`); if they differ, Let's Encrypt will not reach the app.
* **Port 443 must reach the server from the internet.** Let's Encrypt validates this way only on 443; another external port is not accepted. It does not work behind **CGNAT** (shared provider IP) or if your provider blocks inbound 443; in that case use DuckDNS, which works on any external port. Port 80 is **not** needed.
* **IPv6:** if the domain also has an AAAA record, Let's Encrypt may validate over IPv6. Docker does not publish IPv6 by default, so either make IPv6 reach the server or remove the AAAA record.
* **During validation** (a few seconds, and again at each renewal about every 60 days) the public port answers only Let's Encrypt, so the app is briefly unavailable on HTTPS.
* **Rate limits.** Let's Encrypt allows 50 new certificates per week per *registered domain*. Names under a provider domain that is **not** in the public suffix list (for example `go.ro` is not) share that limit with every other customer of the provider, so a first issuance can fail when others used it up. Renewals are not counted. Wait and retry, or use DuckDNS (it *is* in the list).

## What changes while it is on

* The public port **stops answering plain HTTP** and answers HTTPS instead. If you use that port through a **Cloudflare Tunnel**, do not turn this on.
* The LAN port (4100) is untouched.
* Turning the option off puts the public port back on HTTP immediately; the certificate stays on disk (`/data/tls`).

## Security notes

The listener is meant to be exposed directly, so it is stricter than the LAN one: it never trusts `X-Forwarded-For` or Cloudflare headers, takes the client IP from the connection, answers only for your domain (and the addresses you allowed), checks `Origin` on every `POST`, sends HSTS, limits simultaneous connections, times out slow handshakes and **serves nothing without a password**; login attempts are rate-limited (5 failures per 10 minutes per address). Password sessions use `Secure` cookies.
Cloudflare Tunnel + Access is still the stronger setup (nothing is exposed at your router, and Access adds a second factor). Use a long, unique password; consider Settings → *Sign out all devices* after changing it.

The private keys (account and certificate) live in `/data/tls`, readable only by the app user. The DuckDNS token is stored in the app configuration like the other secrets and is never shown again or written to the log.

## Troubleshooting

* **Own domain: "Let's Encrypt could not reach port 443"**: check the router rule (external 443 → server:4101), that the domain points at your public IP (see the status box), CGNAT, and any AAAA record.
* **"DuckDNS refused the request"**: check the subdomain (without `.duckdns.org`) and the token.
* **Validation fails**: DuckDNS answers the TXT record immediately but Let's Encrypt checks from several places; the app retries with longer waits (15, 45, 90 s). Check the log in the status box. After repeated failures Let's Encrypt limits attempts (5 failed validations per hour per name): wait and use the staging option to test.
* **The page opens on your LAN but not from outside**: the router rule (external 443 → server:4101) is missing, your provider blocks inbound ports or uses CGNAT (then a home server cannot be reached directly; use Cloudflare Tunnel).
* **`421 Unknown address`**: you opened the app with a name that is not yours; add it under *Addresses allowed from the local network*.
