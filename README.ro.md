# TeslaMate UI

Aplicație web pentru telefon (PWA), în stilul [Tessie](https://tessie.com), construită peste propriul tău [TeslaMate](https://github.com/teslamate-org/teslamate): starea mașinii live, istoric de curse și încărcări, statistici și — opțional — comenzi la distanță prin API-ul oficial Tesla Fleet. Totul rulează pe serverul tău; datele mașinii nu sunt trimise unor terți. Puținele servicii externe opționale cu care vorbește aplicația sunt listate [mai jos](#servicii-externe-ce-se-trimite-și-când).

> **Fără legătură cu Tesla, Inc., Tessie sau TeslaMate.** „Tesla” și „Model 3/Y/S/X” sunt mărci ale Tesla, Inc. Proiectul reia idei din documentația publică și din propria interfață; nu conține cod sau resurse Tessie. Comanda la distanță a unei mașini e responsabilitatea ta — citește mai întâi [docs/security.md](docs/security.md) (în engleză). Furnizat ca atare, fără garanție.

**Limbi:** interfața e în română și engleză (se schimbă din bara de jos; implicit urmează browserul). [Read in English → README.md](README.md)

## Ce face

| Zonă | Ce primești |
|---|---|
| **Mașină** | Stare live prin MQTT-ul TeslaMate (baterie, autonomie, încărcare, încuietori, uși, presiunea cauciucurilor dacă e disponibilă), poza mașinii, hartă, ultima cursă/încărcare, **card de somn** (de când doarme, ultimul somn, somnul din ultimele 24 h) |
| **Comenzi** | Blocare/deblocare, clima, pornire/oprire încărcare, port de încărcare, sentry, frunk/portbagaj, geamuri, claxon/faruri, limită de încărcare, **HomeLink** (poartă). Prin Fleet API sau **local prin BLE, cu Home Assistant** (vezi mai jos) |
| **Clima** | Temperatură, 5 scaune încălzite, volan încălzit, dezgheață, protecție la supraîncălzire cu pragul ei |
| **Control încărcare** | Curent (A), programări de încărcare și de plecare cu pre-condiționare, **sursa energiei fiecărei încărcări** (rețea sau solar, estimată, prin Home Assistant) |
| **Curse** | Listă pe zile; detaliu cu hartă colorată după viteză, grafice legate de hartă, **stil de condus** (frânări/accelerări bruște, recuperare, scor); **reluare animată 3D** a traseului (vreme, opriri și încărcări, zoom adaptiv, click pe traseu) și **export video (MP4/WebM)** |
| **Profiler** | Flux live cu peste 200 de semnale (Fleet Telemetry), în sesiuni scurte: profile, celule cu mini-grafice, export CSV — [docs/profiler.md](docs/profiler.md) |
| **Import din Tessie** | Aduci istoricul Tessie (curse cu traseu GPS, încărcări, costuri) în TeslaMate: simulare, o singură tranzacție, anulare dintr-un click — [docs/import-tessie.md](docs/import-tessie.md) |
| **Somn și consum în repaus** | Cronologie somn/trezit pe 48 h, % somn pe zi, consum în repaus între curse (%/h și kWh/zi), detectarea trezirilor scurte periodice (ceva „întreabă” mașina) |
| **Încărcări** | Istoric cu curbe (putere, SoC, energie) și cost; **cost total editabil per sesiune**, **furnizor** (dedus din loc sau ales de tine) și filtru pe furnizor cu total kWh + cost — [docs/costs.md](docs/costs.md) |
| **Statistici** | Distanță pe zi, consum, cost, **comparație cu o mașină termică** (l/100 km ai tăi × prețul combustibilului din fiecare zi, preluat și stocat zilnic), degradarea autonomiei, **sănătatea bateriei**, istoricul stărilor, actualizări de software |
| **Notificări** | Cablu conectat, încărcare terminată, ușă/portbagaj deschise, actualizare software, baterie sub 20 % cât e parcată — către un webhook (ex. Home Assistant → telefon) și un istoric în aplicație |
| **Automatizări** | Deschide poarta la sosirea într-un geofence, setează limita de încărcare la conectare, clima înainte de plecare |
| **Copie de siguranță TeslaMate** | Oglindă SQLite locală a curselor, pozițiilor, încărcărilor și stărilor (nu șterge niciodată, instantanee zilnice, unealtă de restaurare) — [docs/features.md](docs/features.md) |
| **Alerte și paznic de somn** | Încărcare oprită, cablu conectat dar nu încarcă, presiune mică, ploaie cu geam deschis, cabină fierbinte, pierdere de aer din cauciuc; de ce a stat mașina trează |
| **Întreținere și anvelope** | Memento-uri (km/luni, RCA/ITP/vinietă), seturi de anvelope cu kilometraj și istoric de presiune, urmărirea actualizărilor software (Wh/km înainte/după) |
| **Călătorii și rapoarte** | Curse grupate în călătorii; rapoarte săptămânale/lunare; „cât ar fi costat pe piața PZU” |
| **Notificări oriunde** | Bot Telegram și Web Push nativ (fără Home Assistant, merge și pe PWA iPhone) |
| **Ecran pentru mașină** | `/incar.html`: pagină mare, doar pentru afișare, pentru browserul mașinii sau o tabletă pe perete |
| **Link de urmărire live** | Link public cu expirare, hartă și ETA, revocabil, ascunde casa |
| **Predare mașină și reguli de zonă** | Valet/Guest/limită de viteză cu cronometru și raport; alerte de viteză, zonă și program |
| **Partajare** | Roluri pentru utilizatorii Cloudflare Access: `admin`, `family` (doar comenzi uzuale), `viewer` (doar citire) |
| **PWA** | Adaugi pe ecranul principal în iOS/Android; rulează ca aplicație de sine stătătoare |

Tot ce nu e Comenzi/Clima/Control încărcare/HomeLink/Automatizări funcționează **doar cu TeslaMate** — fără cont de developer Tesla.

## Arhitectură

```
 telefon / browser ──► ui (:4100) ──► Postgres TeslaMate (istoric)      [stack-ul tău TeslaMate]
                          │      └──► MQTT TeslaMate (stare live)
                          └──► proxy (:4443, tesla-http-proxy) ──► Tesla Fleet API   [semnează comenzile cu cheia ta virtuală]
 Tesla / internet ──► ui :4101 (ascultător public: cheia publică Tesla, callback-ul OAuth și linkurile de partajare)
```

* `ui`: server Python cu puține dependențe (`server.py`) + aplicație statică (`static/`).
* `proxy`: proxy-ul oficial Tesla [vehicle-command](https://github.com/teslamotors/vehicle-command), compilat din sursă la o etichetă fixată; semnează comenzile (obligatoriu pentru mașinile moderne).
* `updater`: container minuscul care dă butonul **Actualizează acum** din Setări (vezi [docs/updates.md](docs/updates.md)).
* Istoricul vine din TeslaMate. Aplicația își ține propria stare în `./data` (token-uri OAuth, setări și `app.db` pentru memento-uri, alerte, etichete, locuri și copia de siguranță opțională).

## Cerințe

* TeslaMate în Docker, cu **MQTT activat** pentru date live (istoricul merge și fără) și o mașină deja conectată.
* Docker cu Compose v2.24+, `openssl` și `bash` pe gazda care rulează aplicația (poate fi aceeași cu TeslaMate).
* Doar pentru comenzi: un domeniu al tău cu HTTPS accesibil din internet și o aplicație gratuită Tesla developer — vezi [docs/fleet-api.md](docs/fleet-api.md).

## Instalare rapidă (doar citire)

```bash
git clone https://github.com/blitzu/teslamate-ui.git && cd teslamate-ui
./setup.sh                     # creează .env, cheile și certificatul intern
nano .env                      # parola bazei de date, gazda MQTT, TESLAMATE_NETWORK
docker compose up -d --build
```

Deschide `http://<server>:4100`. Dacă pagina arată date **DEMO**, nu s-a găsit încă nicio mașină în TeslaMate (sau baza de date nu răspunde — vezi `docker compose logs ui`).

**Valorile pentru `.env`:** aplicația trebuie să ajungă la baza de date și la brokerul TeslaMate după nume, deci intră în rețeaua Docker a TeslaMate.

```bash
docker network ls                                     # găsește rețeaua TeslaMate, ex. teslamate_default
docker inspect <container-teslamate> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'DATABASE|MQTT'
```

Folosește valorile în `.env` (`DATABASE_HOST` și `MQTT_HOST` sunt *numele serviciilor* din acea rețea, de obicei `database` și `mosquitto`).

**Imagini publicate.** Fiecare versiune publică imagini multi-arhitectură (`amd64`, `arm64`) pe `ghcr.io/blitzu/teslamate-ui`; pentru actualizare: `docker compose pull && docker compose up -d`, sau butonul **Actualizează acum** din Setări.

## Setări în aplicație

Tot ce urmează se configurează din **⚙ Setări** (doar administrator): PIN-ul comenzilor, datele Tesla Fleet API, legătura Home Assistant, webhook-ul de notificări, accesul din internet și rolurile, moneda și linkurile. Valorile se salvează în `./data/config.json` (mod 600) și se aplică imediat; câmpurile secrete nu se mai afișează niciodată. Scripturile din `scripts/` și fișierele `.env.*` rămân disponibile ca valori implicite (Setările le suprascriu). Primul PIN se poate seta doar din rețeaua locală (minimum 6 caractere).

## Comenzi (Fleet API)

Comenzile cer o aplicație Tesla developer, un domeniu public cu HTTPS care servește cheia ta publică și o cheie virtuală instalată în mașină. Pas cu pas: **[docs/fleet-api.md](docs/fleet-api.md)** (în engleză).

## Acces din internet

Ține aplicația în rețeaua locală, dacă n-o protejezi. Variante (recomandat Cloudflare Access), PIN, parole și ce expune portul 4101: **[docs/security.md](docs/security.md)**. Pe scurt:

* Cât timp nu ai setat o **parolă**, rețeaua locală rămâne deschisă (ca să nu te blochezi), iar aplicația afișează o avertizare roșie. „Rețea locală” înseamnă adrese private/locale: o cerere venită direct de pe o adresă **publică** pe portul 4100 e refuzată până setezi o parolă.
* Cu parolă (minimum 12 caractere), totul cere autentificare, inclusiv în rețeaua locală (30 de zile pe dispozitiv). **Setări → Acces din internet și roluri → Deconectează toate dispozitivele** încheie toate sesiunile.
* Portul `4100` se poate limita la gazda locală cu `UI_BIND=127.0.0.1` în `.env`.

## Home Assistant (opțional)

Comenzi locale prin Bluetooth cu un ESP32, sursa energiei per încărcare: **[docs/home-assistant.md](docs/home-assistant.md)**.

## Notificări

Setezi `NOTIFY_WEBHOOK` — vezi **[docs/notifications.md](docs/notifications.md)** (include o automatizare Home Assistant). Din Setări poți porni și Telegram sau Web Push.

## Personalizare

* **Poza mașinii:** pune un PNG transparent, văzut de sus, la `./data/car.png` (altfel se folosește un desen generic).
* **Moneda:** `CURRENCY` în `.env` (de ex. `CURRENCY=RON`; costul vine din prețurile setate în TeslaMate) sau în aplicație, la Setări → Afișare. Valoarea din aplicație are prioritate. După ce schimbi `.env` rulează `docker compose up -d` (`restart` nu îl recitește).
* **Demo public cu date fictive:** `docker compose --profile demo up -d demo` (port 4102, fără bază de date și chei, comenzile oprite).

## Servicii externe: ce se trimite și când

| Serviciu | Pentru ce | Ce se trimite | Cine |
|---|---|---|---|
| Tesla Fleet API (`fleet-api.prd.*.vn.cloud.tesla.com`, `auth.tesla.com`) | comenzi, citirea live a setărilor de clima/încărcare, profiler | token-ul OAuth, VIN-ul, parametrii comenzii | server |
| OpenStreetMap (`tile.openstreetmap.org`) | fundalul hărții | coordonatele dalelor (și adresa ta IP, ca la orice hartă web) | browser |
| Open-Meteo | vremea în reluarea traseului | latitudine/longitudine rotunjite la 0,1° și data | browser |
| fuel-prices.eu | prețul zilnic al combustibilului pentru comparația cu mașina termică | doar numele țării | server |
| Overpass / OpenStreetMap (`overpass-api.de` și oglinzi) | butonul „Caută stația” de pe o încărcare | coordonatele acelei încărcări, doar când apeși butonul | server |
| AmpWhere (`ampwhere.com`), **pornit implicit, se poate opri** | stația, furnizorul și tarifele pentru „Caută stația” și asocierea automată (vezi [docs/costs.md](docs/costs.md#find-the-station-of-a-charge)) | nimic despre tine sau mașină: o descărcare anonimă pe zi a listei de stații din fiecare țară în care încarci; căutarea e locală | server |
| frankfurter.dev (cursuri BCE) | EUR și prețurile stațiilor → moneda ta | doar codurile monedelor | server |
| Let's Encrypt (`acme-v02.api.letsencrypt.org`), DuckDNS (`www.duckdns.org`), ipify (`api.ipify.org`), doar dacă pornești *Acces direct din internet* | certificatul HTTPS; DuckDNS ține numele tău spre IP-ul tău; ipify arată IP-ul public în caseta de stare (doar la domeniu propriu) | numele domeniului și cererile ACME; tokenul DuckDNS ajunge doar la DuckDNS; ipify primește o cerere anonimă | server |
| open.er-api.com ([Exchange Rate API](https://www.exchangerate-api.com)) | cursuri pentru monedele pe care BCE nu le publică (MDL, RSD, UAH…), ca rezervă | doar codurile monedelor | server |
| energy-charts.info | prețurile PZU pentru raportul PZU | datele necesare | server |
| Open-Meteo (pe server) | alerta „ploaie cu geam deschis” | coordonate rotunjite la 0,1°, doar cât un geam e deschis | server |
| Telegram Bot API, servicii push ale browserelor | notificări Telegram și Web Push, doar dacă le pornești | textul notificării (push: criptat) | server |
| GitHub (`api.github.com`) | verificarea unei versiuni noi, de două ori pe zi (poate fi oprită) | nimic despre tine sau mașină (cerere anonimă) | server |
| Tessie API | import unic de istoric (doar dacă îl rulezi) | token-ul tău Tessie | server |
| Cloudflare / Home Assistant-ul tău | doar dacă le configurezi | vezi documentația | server |

Leaflet și MapLibre GL JS sunt **incluse** (`static/vendor/`), nu se încarcă dintr-un CDN. Respectă [politica de utilizare a dalelor OSM](https://operations.osmfoundation.org/policies/tiles/) — în regulă pentru uz personal. Licențele: [THIRD_PARTY.md](THIRD_PARTY.md). Browserul e restricționat de un Content-Security-Policy care permite exact aceste gazde (se poate suprascrie cu variabila `CSP`).

## Copii de siguranță, actualizare, restaurare

* **Ce salvezi:** folderul `data/` (token-uri, setări inclusiv PIN/parolă, costuri și furnizori, prețurile zilnice ale combustibilului, automatizări, `app.db`; fiecare fișier își păstrează și un `*.bak`) și `fleet/private-key.pem` (offline). Baza TeslaMate o salvezi cum faci deja — costurile manuale se referă la `charging_processes.id`, deci restaurează-le din același moment.
* **Actualizare:** `docker compose pull && docker compose up -d` (imagini publicate), butonul din Setări sau `git pull && docker compose up -d --build` (din sursă). Setările din `data/` se păstrează. Detalii: [docs/updates.md](docs/updates.md).
* **Restaurare:** copiezi `data/` la loc și pornești stack-ul; aplicația îi dă proprietatea utilizatorului ei fără privilegii (uid 10001) la pornire. Datele TeslaMate se pot reface din copia de siguranță cu `tools/restore_backup.py` (parola bazei se dă prin `TESLAMATE_DSN`, nu în linia de comandă).
* **Acces minim la baza de date:** `./scripts/create-db-user.sh <container-db>` creează un rol doar-citire pentru aplicație (adaugă `--allow-import` dacă folosești importul Tessie).

## Mai multe

* [docs/fleet-api.md](docs/fleet-api.md) — aplicația Tesla developer, domeniu, cheie, autorizare
* [docs/security.md](docs/security.md) — expunere în internet, PIN, parole, Cloudflare Access
* [docs/home-assistant.md](docs/home-assistant.md) — comenzi BLE, sursa energiei, automatizări
* [docs/profiler.md](docs/profiler.md) — profiler de telemetrie live
* [docs/features.md](docs/features.md) — copie de siguranță, alerte, întreținere, rapoarte/PZU, Telegram și push, ecran pentru mașină, link live, predare, reguli de zonă
* [docs/updates.md](docs/updates.md) — versiuni, notificări de versiune nouă, actualizare automată
* [CHANGELOG.md](CHANGELOG.md) — ce s-a schimbat în fiecare versiune
* [docs/costs.md](docs/costs.md) — costuri editabile, furnizori, comparația cu mașina termică
* [docs/import-tessie.md](docs/import-tessie.md) — importul istoricului Tessie
* [docs/notifications.md](docs/notifications.md) — webhook și exemplu Home Assistant
* [docs/troubleshooting.md](docs/troubleshooting.md) — erori frecvente
* [docs/development.md](docs/development.md) — structură, demo local, API, contribuții

## Licență

MIT — vezi [LICENSE](LICENSE).
