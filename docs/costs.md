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
