# UK postcode map

An interactive map of UK postcodes that reveals more detail as you zoom in:
postcode **areas** (SW, EH) → **districts** (SW1A, EH12) → **sectors**
(SW1A 2) → **unit** postcodes (SW1A 2AA). Layers swap automatically by zoom
level. It is a fully static site: MapLibre GL JS reading PMTiles over HTTP
range requests, no backend, no API keys.

Everything is built from open data. **Only the unit centroids are official**
(OS Code-Point Open / Royal Mail). The area, district and sector polygons are
**derived** by this repo's pipeline (Voronoi cells of the unit centroids,
dissolved and clipped to the coastline) because no official open polygons
exist. See [docs/CAVEATS.md](docs/CAVEATS.md) before relying on a boundary and
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for the source investigation.

## Quick start

Requirements: Python 3.10+, Node 18+, `tippecanoe` (≥ 2.17, for PMTiles
output), `curl`. Installing tippecanoe: `brew install tippecanoe` on macOS, or
build from source on Linux (see [pipeline/README.md](pipeline/README.md)).

```bash
pip install -r pipeline/requirements.txt
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
```

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
| `tiles/boundaries.pmtiles`    | ~80 MB  |
| `tiles/units.pmtiles`         | ~70 MB  |
| `data/` search index          | ~60 MB across ~3,000 small JSON files |
| app bundle                    | < 1 MB  |

Tiles are fetched in small ranges on demand, so visitors never download the
whole archive. If your host has a per-file size limit, host the two
`.pmtiles` files elsewhere (any object storage with CORS + range support)
and point `tiles.boundaries` / `tiles.units` in `web/config.js` at their
absolute URLs.

An optional GitHub Actions workflow,
[`.github/workflows/pages.yml`](.github/workflows/pages.yml), builds the data
and deploys `dist/` to GitHub Pages. It runs on manual dispatch only.

## Repository layout

```
Makefile              orchestrates the pipeline (make, make sample, make clean)
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
