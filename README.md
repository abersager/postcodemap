# Postcode map

An interactive map of postcodes, currently Great Britain and Austria, that
reveals more detail as you zoom in:
postcode **areas** (SW, EH) → **districts** (SW1A, EH12) → **sectors**
(SW1A 2) → **unit** postcodes (SW1A 2AA). Layers swap automatically by zoom
level. It is a fully static site: MapLibre GL JS reading PMTiles over HTTP
range requests, no backend, no API keys.

## Coverage

Great Britain (England, Scotland and Wales) and Austria. Each country is a
module in `pipeline/countries/` with its own source, licence and level
structure, and the app loads every built country at once; the legend follows
the country under the map centre. Which other countries could be added from
open data, and in what order, is in
[docs/WORLD_POSTCODES.md](docs/WORLD_POSTCODES.md); the GitHub issues track
them.

Northern Ireland is not on the map because no
open dataset of its postcode locations exists: Code-Point Open stops at the
Irish Sea, and the ONS Postcode Directory carries BT postcodes only under a
Northern Ireland End User Licence that forbids public redistribution, which
a published map is. The one open alternative (postcodes harvested from Food
Hygiene Rating Scheme business records) covers only postcodes that contain a
food business, with the business's coordinates rather than the postcode's,
so it was not used. Isle of Man and the Channel Islands have their own
postcode systems outside Code-Point Open. See
[docs/CAVEATS.md](docs/CAVEATS.md).

Everything is built from open data. **Only the points are official** (OS
Code-Point Open unit postcodes for GB; BEV address register addresses for
Austria). Every polygon is **derived** by this repo's pipeline (Voronoi
cells of the points, dissolved up the code hierarchy and clipped to the
country's boundary) because no official open polygons exist. See [docs/CAVEATS.md](docs/CAVEATS.md) before relying on a boundary and
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for the source investigation.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) (manages Python and the
pipeline's dependencies), Node 18+, `tippecanoe` (≥ 2.17, for PMTiles
output), `curl`. On macOS: `brew install uv tippecanoe`; on Linux build
tippecanoe from source (see [pipeline/README.md](pipeline/README.md)).

```bash
npm install
make            # Great Britain: downloads Code-Point Open + ONS coastline, builds tiles + index (~10 min)
make COUNTRY=at # Austria: BEV address register (100 MB download), ~5 min
npm run dev     # http://localhost:5173
```

For a fast development loop build a few areas only:

```bash
make sample SAMPLE_AREAS=SW,W,WC,EC
```

## Using the map

- Zoom to change level. The legend (bottom left) shows the active level and
  the zoom band of each; click a legend row to jump to that level.
- Only boundaries between postcodes are drawn; the coast comes from the
  basemap.
- Hover a polygon or point to highlight it and see its code and unit count.
- Click a polygon to zoom into it at the next level. Click a unit for a popup.
- Search any fragment: `SW`, `EH12`, `SW1A 2`, `SW1A 2AA`, or a partial unit
  like `SW1A 2A`. Suggestions appear as you type. The searched polygon is
  outlined until the next search.
- The URL hash stores the view, so links are shareable.

## Configuration

Everything tunable is in [`web/config.js`](web/config.js):

```js
countries: ["gb", "at"]
thresholds: { gb: { district: 8, sector: 11, unit: 13 } }   // per-country overrides of meta.json defaults
density: { enabled: true, baseUnitsPerKm2: 40, maxShift: 2 }
```

The thresholds shift upwards in dense places (by log10 of the local
postcode density over `baseUnitsPerKm2`, up to `maxShift`), so central London
switches to sectors and units two zoom levels later than the countryside.
The legend shows the density under the map centre and the shift applied.

Also there: basemap style URL, colours by level depth, label sizes and the
keep-alive interval. Each country's default thresholds and attribution live
in its module and reach the app through `countries/<cc>/meta.json`.

## Static deployment

`npm run build` writes a self-contained site to `dist/` (relative paths, so
it works at any sub-path). Copy it to any static host that supports HTTP
range requests, which includes GitHub Pages, Netlify, Cloudflare Pages, S3 or
R2 behind a CDN, and nginx/Apache.

Sizes to expect from a full GB build:

| File                                   | Size    |
|----------------------------------------|---------|
| `countries/gb/boundaries.pmtiles`      | ~30 MB  |
| `countries/gb/points.pmtiles`          | ~22 MB  |
| `countries/gb/` search index           | ~60 MB across ~3,000 small JSON files |
| `countries/at/boundaries.pmtiles`      | ~10 MB  |
| app bundle                             | < 1 MB  |

Tiles are fetched in small ranges on demand, so visitors never download the
whole archive. If your host has a per-file size limit, or for the fastest
loads (see "Performance" below), host the two `.pmtiles` files on object
storage with a long cache TTL (Cloudflare R2, S3 + CloudFront) and point
`tiles.boundaries` / `tiles.units` in `web/config.js` at their absolute URLs.

An optional GitHub Actions workflow,
[`.github/workflows/pages.yml`](.github/workflows/pages.yml), builds the data
from the live sources and deploys `dist/` to GitHub Pages. It runs on manual
dispatch only, so a refresh after a quarterly Royal Mail update is:

```bash
gh workflow run pages.yml          # needs Pages enabled with source "GitHub Actions"
```

The run takes about 15 minutes (tippecanoe is compiled from source on the
runner). The live site is at https://abersager.github.io/postcodemap/.

## Performance

Tiles are fetched with HTTP range requests against two PMTiles archives.
Two things were found to make them slow, both outside the app:

- **Idle connections silently dropped.** From the network this was developed
  on, an HTTP connection to GitHub Pages that sits idle for 10–20 s dies
  without being closed, and the client (Chrome or Python alike) needs 10–18 s
  to notice and reconnect, so the first tiles after any pause stalled or
  timed out. A control connection to another host on the same network was
  unaffected, and the same test from a GitHub Actions runner never stalled,
  so it is specific to that network path to Fastly's edge, not a general
  property of either end. The app now sends a 1-byte range request every 4 s
  while the page is visible (`tileKeepAliveMs` in `web/config.js`), which
  keeps the connection alive and removed the stalls where they occur.
- **Cold CDN cache.** GitHub Pages caches files for ten minutes; the first
  range request after that may wait for the whole archive to be fetched, so
  the archives are kept small (see the size table above).

For consistently fast loads, host the two `.pmtiles` files on Cloudflare R2
or similar and point `web/config.js` at them.

## Repository layout

```
Makefile              orchestrates the pipeline (make, make sample, make clean)
pyproject.toml        Python dependencies for the pipeline (uv.lock pins them)
pipeline/             country modules, derive polygons, tile, index  (see pipeline/README.md)
web/                  the app: index.html, main.js, config.js, style.css
web/public/countries/ generated tiles, search index and meta.json per country (gitignored)
data/<cc>/            raw downloads and intermediate files per country (gitignored)
docs/                 data sources report and caveats
```

## Attribution

Each country's attribution is set in its module and shown on the map. GB:
*Contains OS data © Crown copyright and database right 2026 · Contains Royal
Mail data © Royal Mail copyright and database right 2026 · Contains ONS data ©
Crown copyright and database right 2026, OGL v3*. Austria: *© Österreichisches
Adressregister, data of the record date 01.04.2026 (BEV) · Postleitzahlen:
RTR-GmbH, CC BY 4.0 · Datenquelle: Statistik Austria*. Plus the basemap's own
attribution (OpenFreeMap / OpenMapTiles / OpenStreetMap
contributors), which MapLibre adds from the style. Keep these visible in any
deployment.
