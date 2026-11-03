# Import your history from Tessie into TeslaMate

Brings your drives (with GPS paths), charges, places and costs from Tessie into your TeslaMate database, so Drives/Charges/Activity/Statistics contain everything Tessie has and TeslaMate is missing.

**Safety model**

* It never imports a drive or charge that **overlaps one already in TeslaMate** (a few seconds of tolerance, because the two services do not start and stop on the same second), so running it again, or on data you partly have on both sides, does not create duplicates.
* Everything runs in **one transaction**; the *Test (no writes)* button executes the whole import and rolls it back.
* It never changes or deletes existing rows. A ledger (`./data/import_tessie.json`) lists every inserted id, so **Undo import** removes exactly what was added.
* Still, make a backup first: `docker exec <teslamate-database-container> pg_dump -U teslamate teslamate | gzip > teslamate-backup.sql.gz`.

## Use it

1. In Tessie get your API access token (see <https://developer.tessie.com>).
2. In the app: **⚙ Settings → Import from Tessie** → paste the token → *Save*.
3. Pick **What to import**: *Everything missing from TeslaMate* (default: before, between and after your TeslaMate data, e.g. when TeslaMate was down for a while or you used both apps in turns) or *Only what is older than the first TeslaMate record* (the conservative mode). **Check** shows what would be imported (counts, km, kWh, period, how many items are before/between/after your TeslaMate data and how many TeslaMate already has).
4. **Test (no writes)** runs everything without saving; **Import** writes it (after a confirmation). A progress bar shows the status; it can take a few minutes for long histories (a drive is one request to Tessie: they run 5 at a time, `IMPORT_WORKERS` 1-8; the routes fetched by *Test* are kept in `data/import_cache` for 3 days, so *Import* right after *Test* does not download them again).
5. You can run the import again later (for example after using Tessie for another week); the ledger accumulates. **Undo import** removes everything the app imported, in all runs.

## What is imported (and what is not)

| Tessie | Where it goes |
|---|---|
| Drives: dates, start/end place and coordinates, start/end battery, temperatures, top speed, distance, exact start/end odometer, energy used | TeslaMate `drives` + `addresses` (+ matching `geofences`). A place you saved in Tessie becomes the name of a **new** address |
| State history of each drive (`/states`, a point about every 30 s: GPS, speed, battery, **real range**, **altitude**, inside/outside **temperature**, climate on/off, odometer) | TeslaMate `positions` (route, charts, altitude, temperatures work) and the drive's total ascent / descent |
| Charges: dates, place, energy added/used, battery start/end, fast-charger flag, cost | TeslaMate `charging_processes` |
| Charging state history (power, voltage, current, range about every 45 s) | TeslaMate `charges`: the **real charging curve** (energy integrated from the power and scaled to Tessie's total; a charge without power data keeps a start and an end point) |
| Parked periods (energy used, battery start/end, climate and sentry share) | the app's own database, page **Tessie archive** |
| Battery measurements (capacity in kWh, max range, odometer; also taken from each charge) | the app's own database, **Tessie archive** (capacity chart) |
| Firmware alerts the car generated (name, description, impact) | the app's own database, **Tessie archive** (grouped by kind) |
| Autopilot distance, average speed, energy used, tag of a drive | the app's own database (drive page, *Tessie data*); the tag becomes an app tag |
| Peak power / regen of a drive | **estimated** by the app from the energy left in the battery over ~60 s windows and shown as an estimate on the drive page; never written into TeslaMate's power column |

Not available from Tessie, so left empty: **real instantaneous power** (so TeslaMate's `power_max` / `power_min` stay empty), tyre pressures, sleep/offline history, software-version history and charger phases. Tessie's `/states` also reports the energy added of a charge as 0, which is why the app integrates it from the power. Tessie's invoices and licence-plate endpoints returned nothing on the accounts we checked.

TeslaMate computes a drive's consumption from the range at the start and at the end; the start range is the real one and the end range is derived from Tessie's energy figure, so the consumption (kWh) matches Tessie's. Units are detected per drive (miles vs km) by comparing the path with the drive's own totals.

**Imported before 1.10.0?** Older imports used the GPS path only and have no altitude, temperatures or charging curve. Use **Undo import** and import again (the routes download several at a time now, so it is much faster); **Undo import** also empties the Tessie archive.
