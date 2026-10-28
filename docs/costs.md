# Charge costs, providers and the ICE-car comparison

All of this is stored **by this app** (in `/data`), never written to TeslaMate's database.

## Edit the total cost of a charge

Open a charge (Charges → tap a session) → **Cost & provider**. The cost you enter replaces the TeslaMate cost
(and the "real cost" estimate based on grid import) in the list, in the totals and in Stats. Leave the field empty to go
back to the automatic cost. Editing needs the app **PIN** and the **admin** role.

Stored in `/data/charge_meta.json`: `{"<charging_process id>": {"cost": 12.5, "provider": "Ionity"}}`.

## Providers and the filter

Every session gets a provider: the one you typed, otherwise one guessed from the place name (home, Tesla Supercharger,
Ionity, Renovatio, Enel X, MOL, OMV, Petrom, Kaufland, Lidl, ...). In **Charges**, pick a period (all / 30 / 90 days / 1 year) and a provider
chip: the summary shows the number of sessions, **total kWh, total cost and the average cost per kWh** for the filter.

## Find the station of a charge

On a charge, **🔎 Find the station** looks for the charging station at the place of the charge and suggests the provider and, when known, the tariffs. Picking one **saves immediately**
(no Save button): the provider, the station name and its tariffs. Your cost is never touched by this; it stays what you entered (or what TeslaMate / your saved places say).

* **Tariffs.** A station can have several (AC and DC, or different powers). They appear as buttons, the one matching your charge (AC/DC, closest power) is marked ✓. Pick another with one tap,
  or type your own **manual tariff** per kWh. The page then shows what the charge would have cost at that tariff (kWh × price) next to your real cost, which is handy when charging was free.
  **Remove the link** clears it.
* **Providers.** The provider of the linked station is used in the lists and filters, unless you set one yourself on the charge (that always wins).
* **Sources.** **AmpWhere** first (on by default; switch it off in Settings → Display → *Station lookup* or with `AMPWHERE=0`): much richer data, with a price per kWh for almost every charger.
  When it is off, has no station nearby or is unreachable, the lookup uses **OpenStreetMap** (via Overpass): operator and sometimes a price tag; in that case the coordinates of that one charge are sent
  when you press the button, and results are cached for a day.
* **About AmpWhere.** It is not an official, documented API: we use the same request their public map makes (no key, no guarantees, we are not affiliated) and it may change or stop working at any time
  (then the lookup falls back to OpenStreetMap). Their terms forbid bulk downloads, so the maintainer asked first, describing this open-source project and its use (cost tracking only), and the owner of AmpWhere replied that calling the API is fine with him. The app downloads the country's station list **once a day at most**, keeps it in `/data`, identifies itself in the User-Agent, stops for 24 h if the
  server refuses, and does the search **locally**, so none of your coordinates leave your server. The prices are today's, not the ones of the day of your charge. The data belongs to AmpWhere and the
  charge point operators; please respect their terms.
* **Countries.** AmpWhere covers Romania, Bulgaria, Lithuania, Greece, Hungary, the Czech Republic, Slovakia, Croatia, Slovenia, Italy, Cyprus, Moldova, Turkey and Serbia. By default (`AMPWHERE_COUNTRY=auto`)
  the app downloads **only the countries where you actually charged** (decided from the coordinates of the charge, so a trip to Hungary adds Hungary's list of ~170 KB; Romania's is ~5.6 MB), each at most
  once a day. Set `AMPWHERE_COUNTRY=ro,hu` to fix the list instead. Prices come in the currency of the station and are only offered as an estimated cost when it matches your currency.
* **Currency.** Pick the currency of the app from a list in Settings → Display (the old free-text value still works). Station prices in another currency (forint, koruna, lira, euro…) are
  **converted automatically** to it, with the ECB rate from [frankfurter.dev](https://frankfurter.dev) and, for currencies the ECB does not publish (MDL, RSD, UAH…), the free
  [Exchange Rate API](https://www.exchangerate-api.com) (*Rates By Exchange Rate API*). Rates are cached for 12 hours (and the last known one is used if the service is down); only currency codes are sent.
  The original price stays visible next to the converted one, e.g. `4.21 RON/kWh (289 HUF)`. The conversion is done when you look the station up or when it is linked, so a stored tariff keeps the rate of that day.
* **Automatic link.** With AmpWhere on (the default), every new charge is linked to the nearest station (within 150 m) when TeslaMate closes it. **The first time the app runs with a station source
  available (so, right after you update), the charges you already have are linked in the background, once**; charges at home or without a station nearby stay as they are, and your costs are never touched.
  An administrator can redo it with `POST /api/stations/autolink` (add `"force": true` to also redo the ones already linked).

## Cost of each drive

Every drive (in the list and on the drive page) shows what it cost, the equivalent in petrol litres and, if you set the petrol car's consumption, what it would have cost with a petrol car.

* **Oldest energy first (FIFO).** The battery is a queue of layers: every charge adds its kWh at that charge's price (its cost ÷ kWh added) and a drive uses kWh starting from the oldest layer. The cost of a drive is the sum of the prices of the kWh it used, so the money of a charge ends up on the drives that used its energy and, once that energy is gone, later drives do not carry it. Before each charge the battery is brought to the energy given by the state of charge at the start (what the car lost while parked is taken from the oldest layer).
* **Energy from before your first charge in TeslaMate came from the factory and is free.**
* The charge costs are the same ones used everywhere else (manual > real grid cost > saved place > TeslaMate).
* **Petrol equivalent (l/100 km)** = the electric cost per 100 km ÷ the price of a litre that day. It only needs the fuel price. **With a petrol car** = km ÷ 100 × the consumption you set × the fuel price of the day, and *Saved* is the difference. Both use the same settings as the Stats comparison below.
* **A `~` in front of the number** means part of the energy comes from charges that have no price: they are counted at the average price of your priced charges, so the drive is an estimate. Enter the cost of those charges and it becomes exact.
* Drives need a usable energy figure (TeslaMate's range difference × efficiency) and at least one charge with a price; otherwise no cost is shown.

## Comparison with a petrol/diesel car (Stats)

In **Stats → Compared with a petrol/diesel car** (or Settings → Display) set:

| Setting | Meaning |
| --- | --- |
| `ice_l100` | consumption of the car you would otherwise drive, in l/100 km |
| `fuel_type` | `euro95` (petrol), `diesel`, or `manual` |
| `fuel_price` | manual price per litre (used with `manual`, or as a fallback when no price was stored yet) |
| `fuel_country` | country for the automatic price (default `Romania`) |

For each day with driving: `litres = km / 100 × l/100km`, `cost = litres × that day's fuel price`. The page shows the fuel cost, the
electric cost for the same km (the sum of the costs of those drives, see *Cost of each drive* above), the saving, the litres avoided and the
price chart.

### Where the daily fuel price comes from

Once a day (checked every 6 hours, the last read of the day wins) the server reads the **national average** from
[fuel-prices.eu](https://www.fuel-prices.eu) (for Romania it is built from the official *Monitorul Prețurilor Carburanților*), in EUR per litre for Euro 95 and Diesel,
converts it to your currency with the ECB rate from [frankfurter.dev](https://frankfurter.dev) (supported currency symbols: lei/RON, €, $, £, zł, Kč, Ft, лв, CHF, SEK, DKK, NOK;
any other currency: use `manual`) and **stores one entry per day** in `/data/fuel_prices.json`
(both fuels and the rate, so switching fuel later is retroactive). Only the country name is sent. Days from before the first stored reading use the first known price
(shown as "estimated" in the note). Disable the automatic lookup with `fuel_type=manual`.

## How the numbers are defined

* **Days** in *Stats* (km per day, kWh per day, the daily fuel price lookup) are **local days** (the `TZ` of the container), not UTC days.
* **Average cost per kWh** = cost ÷ kWh, counting only the sessions that have a cost (a missing cost is not the same as zero).
* **Charging cost / 100 km** (Stats → Charging) = money spent on charging in the period ÷ km driven (it includes losses and charging for later trips). **Cost / 100 km: ICE vs electric** (comparison card) uses the energy the drives actually consumed.
* **Estimated real cost** of a home AC charge = grid import measured by your Home Assistant sensor during the session, capped at the energy the car drew, × the grid price; negative samples (export) are ignored. If Home Assistant has no history for that time the estimate is skipped (it is **not** cached as 0).
* The fuel price history only contains readings for your current currency and country; readings stored under another currency/country are ignored.
