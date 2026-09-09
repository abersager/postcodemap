# GB postcode map

An interactive map of Great Britain's postcodes that reveals more detail as you zoom in:
postcode **areas** (SW, EH) → **districts** (SW1A, EH12) → **sectors**
(SW1A 2) → **unit** postcodes (SW1A 2AA). Layers swap automatically by zoom
level. It is a fully static site: MapLibre GL JS reading PMTiles over HTTP
range requests, no backend, no API keys.

## Coverage: Great Britain, not the UK

England, Scotland and Wales. Northern Ireland is not on the map because no
open dataset of its postcode locations exists: Code-Point Open stops at the
Irish Sea, and the ONS Postcode Directory carries BT postcodes only under a
Northern Ireland End User Licence that forbids public redistribution, which
a published map is. The one open alternative (postcodes harvested from Food
Hygiene Rating Scheme business records) covers only postcodes that contain a
food business, with the business's coordinates rather than the postcode's,
so it was not used. Isle of Man and the Channel Islands have their own
postcode systems outside Code-Point Open. See
[docs/CAVEATS.md](docs/CAVEATS.md).

Everything is built from open data. **Only the unit centroids are official**
(OS Code-Point Open / Royal Mail). The area, district and sector polygons are
**derived** by this repo's pipeline (Voronoi cells of the unit centroids,
dissolved and clipped to the coastline) because no official open polygons
exist. See [docs/CAVEATS.md](docs/CAVEATS.md) before relying on a boundary and
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for the source investigation.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) (manages Python and the
pipeline's dependencies), Node 18+, `tippecanoe` (≥ 2.17, for PMTiles
output), `curl`. On macOS: `brew install uv tippecanoe`; on Linux build
tippecanoe from source (see [pipeline/README.md](pipeline/README.md)).

```bash
npm install
make            # downloads Code-Point Open + ONS coastline, builds tiles + search index (~10 min)
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
thresholds: { district: 8, sector: 11, unit: 13 }   // areas below 8, units from 13
density: { enabled: true, baseUnitsPerKm2: 40, maxShift: 2 }
```

The thresholds shift upwards in dense places (by log10 of the local
postcode density over `baseUnitsPerKm2`, up to `maxShift`), so central London
switches to sectors and units two zoom levels later than the countryside.
The legend shows the density under the map centre and the shift applied.

Also there: tile and index URLs, basemap style URL, colours, opacities, label
sizes and the attribution string. Thresholds can be moved anywhere inside the
zoom ranges the tiles carry (areas 0–12, districts 5–14, sectors 8–14, units
12–14 and overzoomed beyond) without rebuilding; go further and widen the
ranges in `pipeline/build_tiles.sh`.

## Static deployment

`npm run build` writes a self-contained site to `dist/` (relative paths, so
it works at any sub-path). Copy it to any static host that supports HTTP
range requests, which includes GitHub Pages, Netlify, Cloudflare Pages, S3 or
R2 behind a CDN, and nginx/Apache.

Sizes to expect from a full GB build:

| File                          | Size    |
|-------------------------------|---------|
| `tiles/boundaries.pmtiles`    | ~30 MB  |
| `tiles/units.pmtiles`         | ~22 MB  |
| `data/` search index          | ~60 MB across ~3,000 small JSON files |
| app bundle                    | < 1 MB  |

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

- **Idle connections silently dropped.** On the network this was developed
  on, an HTTP connection to GitHub Pages that sits idle for about ten
  seconds dies without being closed. Chrome only discovers that on the next
  request and takes 10–18 s to reconnect, so the first tiles after any pause
  stalled or timed out; a plain Python client showed the same. The app now
  sends a 1-byte range request every 4 s while the page is visible
  (`tileKeepAliveMs` in `web/config.js`), which keeps the connection alive
  and removed the stalls. Connections to Cloudflare-hosted services over
  HTTP/3 did not have the problem.
- **Cold CDN cache.** GitHub Pages caches files for ten minutes; the first
  range request after that may wait for the whole archive to be fetched, so
  the archives are kept small (see the size table above).

For consistently fast loads, host the two `.pmtiles` files on Cloudflare R2
or similar and point `web/config.js` at them.

## Repository layout

```
Makefile              orchestrates the pipeline (make, make sample, make clean)
pyproject.toml        Python dependencies for the pipeline (uv.lock pins them)
pipeline/             download, clean, derive polygons, tile, index  (see pipeline/README.md)
web/                  the app: index.html, main.js, config.js, style.css
web/public/tiles/     generated PMTiles (gitignored)
web/public/data/      generated search index (gitignored)
data/                 raw downloads and intermediate files (gitignored)
docs/                 data sources report and caveats
```

## Attribution

The map shows: *Contains OS data © Crown copyright and database right 2026 ·
Contains Royal Mail data © Royal Mail copyright and database right 2026 ·
Contains ONS data © Crown copyright and database right 2026, OGL v3*, plus
the basemap's own attribution (OpenFreeMap / OpenMapTiles / OpenStreetMap
contributors), which MapLibre adds from the style. Keep these visible in any
deployment.
