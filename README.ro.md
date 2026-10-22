# TeslaMate UI (în stilul Tessie)

Aplicație web pentru telefon (PWA) peste propriul tău [TeslaMate](https://github.com/teslamate-org/teslamate): starea mașinii live, istoric curse și încărcări, statistici și — opțional — comenzi la distanță prin API-ul oficial Tesla Fleet. Rulează pe serverul tău; datele nu pleacă din rețeaua ta.

> Fără legătură cu Tesla, Tessie sau TeslaMate. Comanda la distanță a unei mașini e responsabilitatea ta — citește mai întâi [docs/security.md](docs/security.md) (în engleză).

## Ce face
* **Mașină:** stare live, hartă, card de somn (de când doarme, cât a dormit), comenzi (blocare, clima, încărcare, sentry, frunk/portbagaj, geamuri, HomeLink pentru poartă, limită încărcare).
* **Clima:** temperatură, 5 scaune încălzite, volan, dezgheață, protecție la supraîncălzire.
* **Încărcări:** istoric + control (curent în amperi, programări, plecare programată).
* **Curse:** istoric, hartă colorată după viteză și **reluare animată 3D** a traseului (cu vreme, opriri, încărcări, zoom, click pe traseu).
* **Statistici**, **notificări** (cablu conectat, încărcare terminată, ușă deschisă) către un webhook (ex. Home Assistant → telefon).

Fără cont de developer Tesla funcționează tot, **mai puțin comenzile**.

## Instalare rapidă (doar citire)

```bash
git clone https://github.com/blitzu/teslamate-ui.git && cd teslamate-ui
./setup.sh                 # creează .env, cheile și certificatul intern
nano .env                  # parola bazei de date TeslaMate, MQTT, rețeaua Docker
docker compose up -d --build
```

Deschide `http://<server>:4100`. Valorile pentru `.env` le iei din containerul TeslaMate (`docker inspect … | grep -E 'DATABASE|MQTT'`), iar `TESLAMATE_NETWORK` din `docker network ls`.

## Comenzi, acces din internet, notificări
Pașii complecți (în engleză): [docs/fleet-api.md](docs/fleet-api.md) (aplicația Tesla developer, domeniu, cheie virtuală), [docs/security.md](docs/security.md) (Cloudflare Access, PIN, parolă), [docs/notifications.md](docs/notifications.md) (webhook + exemplu Home Assistant), [docs/troubleshooting.md](docs/troubleshooting.md).

Interfața e în română și engleză (se schimbă din bara de jos).

Licență MIT.
