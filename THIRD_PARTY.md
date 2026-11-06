# Third-party software and services

Bundled (served from `static/vendor/`, no CDN):

| Component | Version | License | Source |
|---|---|---|---|
| Leaflet | 1.9.4 | BSD-2-Clause, © 2010-2023 Vladimir Agafonkin, © 2010-2011 CloudMade | https://leafletjs.com |
| MapLibre GL JS | 4.7.1 | BSD-3-Clause, © MapLibre contributors | https://maplibre.org |
| @maplibre/maplibre-gl-leaflet | 0.0.22 | ISC, © MapLibre contributors | https://github.com/maplibre/maplibre-gl-leaflet |

The files are the unmodified `leaflet.js`, `leaflet.css`, `maplibre-gl.min.js` and `maplibre-gl.min.css` of those versions as distributed on cdnjs; check them with `sha256sum static/vendor/*` against the cdnjs files of the same version. `leaflet-maplibre-gl.js` is the unmodified `leaflet-maplibre-gl.js` of `@maplibre/maplibre-gl-leaflet@0.0.22` from npm (sha256 `59ecd8d2b32779d24f1bd26b87c8890f27e4a6e7858d993bd17e4d878e6d2677`); it is only loaded when you pick a vector map.

Used at build time: [tesla/vehicle-command](https://github.com/teslamotors/vehicle-command) (Apache-2.0; the signing proxy, built from the commit of tag `v0.4.1` in `Dockerfile.proxy`), paho-mqtt (EPL-2.0 / EDL-1.0), psycopg2 (LGPL-3.0 with exceptions), PyJWT (MIT), cryptography (Apache-2.0 / BSD).

Data and services the app talks to are listed in the README (*External services*). Attribution: map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL); weather by [Open-Meteo](https://open-meteo.com) (CC BY 4.0); fuel prices from [fuel-prices.eu](https://www.fuel-prices.eu) (for Romania derived from the official *Monitorul Prețurilor Carburanților*); exchange rates from the European Central Bank via [frankfurter.dev](https://frankfurter.dev).

This project is not affiliated with, endorsed by or sponsored by Tesla, Inc., Tessie or TeslaMate. Tesla is a trademark of Tesla, Inc.
