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
4. **Test (no writes)** runs everything without saving; **Import** writes it (after a confirmation). A progress bar shows the status; it can take a few minutes for long histories.
5. You can run the import again later (for example after using Tessie for another week); the ledger accumulates. **Undo import** removes everything the app imported, in all runs.

## What is imported (and what is not)

| Tessie | TeslaMate |
|---|---|
| Drives: dates, start/end place and coordinates, start/end battery, average temperatures, max speed, distance, energy used | `drives` + `addresses` (+ matching `geofences`) |
| Driving path (`details=true`, ~30 s points: lat/lon, speed, battery, odometer) | `positions` of each drive (the route map and charts work) |
| Charges: dates, place, energy added/used, battery start/end, supercharger flag, cost | `charging_processes` + a start and end point in `charges` |

Not available from Tessie, so left empty: instantaneous power, elevation, tyre pressures, and the detailed charging curve (the charge page shows two points). Range values are derived from the battery level using your car's typical range at 100 % and the energy used, so consumption (kWh) matches Tessie's numbers.

Units are detected per drive (miles vs km) by comparing the path with the drive's own totals.
