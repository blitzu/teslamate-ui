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

## Comparison with a petrol/diesel car (Stats)

In **Stats → Compared with a petrol/diesel car** (or Settings → Display) set:

| Setting | Meaning |
| --- | --- |
| `ice_l100` | consumption of the car you would otherwise drive, in l/100 km |
| `fuel_type` | `euro95` (petrol), `diesel`, or `manual` |
| `fuel_price` | manual price per litre (used with `manual`, or as a fallback when no price was stored yet) |
| `fuel_country` | country for the automatic price (default `Romania`) |

For each day with driving: `litres = km / 100 × l/100km`, `cost = litres × that day's fuel price`. The page shows the fuel cost, the
estimated electric cost for the same km (your average cost per kWh × the energy the drives used), the saving, the litres avoided and the
price chart.

### Where the daily fuel price comes from

Once a day (checked every 6 hours, the last read of the day wins) the server reads the **national average** from
[fuel-prices.eu](https://www.fuel-prices.eu) (for Romania it is built from the official *Monitorul Prețurilor Carburanților*), in EUR per litre for Euro 95 and Diesel,
converts it to your currency with the ECB rate from [frankfurter.dev](https://frankfurter.dev) (supported currency symbols: lei/RON, €, $, £, zł, Kč, Ft, лв, CHF, SEK, DKK, NOK;
any other currency: use `manual`) and **stores one entry per day** in `/data/fuel_prices.json`
(both fuels and the rate, so switching fuel later is retroactive). Only the country name is sent. Days from before the first stored reading use the first known price
(shown as "estimated" in the note). Disable the automatic lookup with `fuel_type=manual`.
