# Postcode map

An interactive map of postcode boundaries, live at
**https://postcodemap.net**. It covers Great Britain, Austria, the
Netherlands, Norway and Germany and shows more detail as you zoom in, from
1- or 2-character regions down to individual postcodes:

| Country | Levels, coarse to fine | Source of the geometry |
|---|---|---|
| Great Britain | area (`SW`) → district (`SW1A`) → sector (`SW1A 2`) → unit (`SW1A 2AA`, drawn as points) | polygons derived from OS Code-Point Open unit centroids |
| Austria | zone (`1`) → region (`10`) → PLZ (`1010`) | polygons derived from the BEV address register (2.5 M geocoded addresses) |
| Netherlands | region (`10`) → PC4 (`1012`) → PC5 (`1012A`) → PC6 (`1012AB`) | official PC6 polygons from Statistics Netherlands (CBS), dissolved upwards |
| Norway | zone (`0`) → region (`01`) → postcode (`0150`) | official postcode polygons from Kartverket (boundaries by Posten Norge), clipped to the N500 coastline |
| Germany | zone (`1`) → region (`10`) → area (`101`) → PLZ (`10115`) | community-drawn PLZ polygons from OpenStreetMap (ODbL, see Licences), dissolved upwards |

The site is fully static: [MapLibre GL JS](https://maplibre.org/) reads
[PMTiles](https://docs.protomaps.com/pmtiles/) archives with HTTP range
requests. There is no backend and no API key. Everything on the map is built
from open data by the pipeline in this repository; nothing generated is
committed.

## What the boundaries mean

The Netherlands and Norway publish postcode polygons as open data (Norway's
run out to sea, so the pipeline clips them to Kartverket's coastline).
Germany has no official open postcode data at all: Deutsche Post sells it,
so the map uses the PLZ boundaries that OpenStreetMap contributors have
mapped, which are complete but unofficial. For Great Britain and Austria the
open data consists of **points** (one per unit postcode, or one per address)
and the pipeline **derives** polygons from them: it computes the Voronoi cell of every point, dissolves the cells up
the code hierarchy and clips the result to the country's coastline or
municipal boundary. A derived boundary runs halfway between neighbouring
postcodes' points, which is a good approximation in built-up areas and a
rough one in the countryside. Only the boundaries *between* postcodes are
drawn; the coast comes from the basemap.

Northern Ireland is missing because its postcode locations are not open
data (Code-Point Open stops at the Irish Sea and the ONS Postcode Directory
licenses BT postcodes under terms that forbid redistribution). The Isle of
Man and the Channel Islands have their own postcode systems outside
Code-Point Open.

Read [docs/CAVEATS.md](docs/CAVEATS.md) before relying on a boundary.
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) records how the sources were
chosen; [docs/WORLD_POSTCODES.md](docs/WORLD_POSTCODES.md) surveys which
other countries publish open postcode data, and the GitHub issues track
adding them.

## Running it locally

Requirements: [uv](https://docs.astral.sh/uv/) (installs Python and the
pipeline's dependencies), Node 18+, [tippecanoe](https://github.com/felt/tippecanoe)
2.17 or newer (`brew install uv tippecanoe` on macOS; build tippecanoe from
source on Linux) and `curl`.

```bash
npm install
make            # Great Britain: downloads Code-Point Open and the ONS coastline, ~10 min
make COUNTRY=at # Austria: BEV address register, 100 MB download, ~5 min
make COUNTRY=nl # Netherlands: CBS PC6 polygons, 190 MB download, ~5 min
make COUNTRY=no # Norway: Kartverket polygons, addresses and N500 map data, 230 MB download, ~5 min
make COUNTRY=de # Germany: OpenStreetMap PLZ polygons (yetzt/postleitzahlen release), 25 MB download, ~2 min
npm run dev     # http://localhost:5173
```

Each `make` writes `web/public/countries/<cc>/` (tiles, search index,
`meta.json`); the app loads every country listed in `web/config.js`. For
a quick build of a few top-level codes only:

```bash
make sample COUNTRY=gb SAMPLE_AREAS=SW,W,WC,EC   # central London in about a minute
make sample COUNTRY=nl SAMPLE_AREAS=10,11         # Amsterdam
make sample COUNTRY=no SAMPLE_AREAS=0,1           # Oslo and the east
make sample COUNTRY=de SAMPLE_AREAS=1             # Berlin and Brandenburg
```

The pipeline stages, timings and how to add a country are described in
[pipeline/README.md](pipeline/README.md).

## Using the map

- Zoom to change level. The legend (bottom left) names the country under
  the map centre, the active level and each level's zoom band; click a
  legend row to jump to that level.
- Hover a polygon to see its code, place name and how many postcodes it
  contains. Click a polygon to zoom into it at the next level; click a GB
  unit point for its coordinates.
- Search any fragment of a code: `SW`, `EH12`, `SW1A 2`, `SW1A 2AA`,
  `1010`, `1012AB`, or a partial code like `SW1A 2A`. Suggestions appear as
  you type; the matched polygon stays outlined until the next search. The
  country under the map centre is searched first.
- The view is stored in the URL hash, so links can be shared.

## Configuration

All tunables are in [`web/config.js`](web/config.js):

```js
countries: ["gb", "at", "nl", "no", "de"],   // countries to load (each needs a build in web/public/countries/)
thresholds: { gb: { district: 8, sector: 11, unit: 13 } },   // per-country overrides of the zoom at which each level appears
density: { enabled: true, baseUnitsPerKm2: 40, maxShift: 2 },
```

Postcodes are far denser in city centres than in the countryside, so fixed
zoom thresholds cannot suit both. The app therefore shifts the active
country's thresholds upwards by log10 of the local postcode density over
`baseUnitsPerKm2`, capped at `maxShift`: central London or Amsterdam switch
to the finer levels about two zoom levels later than a rural area. The
legend shows the density under the map centre and the shift in effect.
Germany has no open address data, so it gets no density readout and no
shift; its thresholds apply as they are.

The same file holds the basemap style URL (OpenFreeMap by default, no key
needed), the colours and label sizes per level, and `tileKeepAliveMs` (see
Hosting below). Each country's default thresholds, attribution and level
names come from its pipeline module via `countries/<cc>/meta.json`.

## Deployment and hosting

`npm run build` writes a static `dist/` with relative paths that can be
served from any web server or object store that supports HTTP range
requests.

**postcodemap.net** runs on Cloudflare's free tier. The app is a Cloudflare
Pages project; the data archives live in an R2 bucket behind the custom
domain `data.postcodemap.net` and are served from Cloudflare's cache with
free egress. `.github/workflows/cloudflare.yml` (run manually from the
Actions tab) builds each country in its own job, uploads `dist/countries` to
R2 under a versioned prefix `v/<date>-<sha>/` with immutable cache headers,
deploys the app with `VITE_COUNTRY_BASE` pointing at that prefix, and
pre-warms the cache. Versioned prefixes mean a deploy never needs a cache
purge and never breaks a client that is still using the previous version.

A country is only rebuilt when something that determines its output has
changed (the pipeline scripts, its module, the Makefile, the Python
dependencies or the pinned tippecanoe version); otherwise its previous build
is restored from the Actions cache and the deploy takes a couple of minutes.
Upstream data refreshes change no file in the repository, so pass the
countries to refresh in the workflow's `rebuild` input (`gb,at` or `all`).
The list of countries is the job matrix in the workflow; keep it in step
with `countries` in `web/config.js`.

`scripts/cloudflare_setup.py` creates everything the workflow needs (bucket,
CORS for range requests, the custom domain, a cache-everything rule with a
one-year edge TTL because `.pmtiles` is not cached by default, Smart Tiered
Cache, the Pages project and the apex DNS record). It is idempotent and runs
when the workflow's `setup` input is ticked. The workflow needs two
repository secrets, `CLOUDFLARE_API_TOKEN` (permissions are listed at the
top of the script) and `CLOUDFLARE_ACCOUNT_ID`.

The GitHub Pages site of this repository only redirects to postcodemap.net,
keeping the map view in the URL hash (`.github/workflows/pages.yml` publishes
the two files in `redirect/`).

Sizes of a full build:

| File | Size |
|---|---|
| `countries/gb/boundaries.pmtiles` | ~30 MB |
| `countries/gb/points.pmtiles` | ~22 MB |
| `countries/gb/index.json` + `units.bin` | ~15 MB (search index; unit lists as gzipped slices fetched by range) |
| `countries/at/boundaries.pmtiles` | ~7 MB |
| `countries/nl/boundaries.pmtiles` | ~77 MB (466 k official PC6 polygons at z12, PC5 at z9–12) |
| `countries/nl/index.json` + `units.bin` | ~7 MB (PC5/PC6 codes as gzipped slices fetched by range) |
| `countries/no/boundaries.pmtiles` | ~23 MB (3.4 k official postcode polygons along a very long coastline) |
| `countries/de/boundaries.pmtiles` | ~34 MB (8.2 k PLZ polygons at four levels) |
| app bundle | < 1 MB |

This is well inside R2's free tier (10 GB stored, 10 M reads a month, reads
counted only on cache misses). Cloudflare Pages caps individual files at
25 MiB, which is why the archives are in R2 rather than deployed with the
app.

**Hosting elsewhere.** A PMTiles host must honour range requests and should
cache the archives for a long time: a CDN that caches for minutes will
repeatedly fetch whole 30–80 MB files to answer the first range request
after expiry. GitHub Pages works but has that ten-minute cache, and on some
network paths its edge silently drops idle connections, which shows up as
tile requests stalling for 10–18 s. `tileKeepAliveMs` in `web/config.js`
sends a one-byte range request every N milliseconds to keep the connection
warm; it is off (0) for Cloudflare and should be about 4000 on GitHub Pages.

## Repository layout

```
Makefile              runs the pipeline for one country (make, make sample, make clean)
pyproject.toml        Python dependencies for the pipeline (uv.lock pins them)
pipeline/             country modules and the four stages: points, polygons, tiles, index
web/                  the app: index.html, main.js, config.js, style.css
web/public/countries/ generated tiles, search index and meta.json per country (gitignored)
data/<cc>/            raw downloads and intermediate files per country (gitignored)
scripts/              Cloudflare setup and R2 upload used by the deploy workflow
redirect/             the GitHub Pages redirect
docs/                 data sources, caveats, world survey of open postcode data
```

## Licences and attribution

The code is MIT licensed. The data keeps its sources' licences, all of
which require attribution, and the map shows each country's line in its
attribution bar:

- Great Britain: *Contains OS data © Crown copyright and database right
  2026 · Contains Royal Mail data © Royal Mail copyright and database right
  2026 · Contains ONS data © Crown copyright and database right 2026*, Open
  Government Licence v3.
- Austria: *© Österreichisches Adressregister, data of the record date
  01.04.2026 (BEV) · Postleitzahlen: RTR-GmbH, CC BY 4.0 · Datenquelle:
  Statistik Austria*.
- Netherlands: *Postcodegebieden: © CBS / Esri Nederland (CC BY 4.0) · Place
  names: GeoNames (CC BY 4.0)*.
- Norway: *Postnummerområder: © Kartverket / Posten Norge (CC BY 4.0) ·
  Addresses (Matrikkelen) and coastline (N500): © Kartverket (CC BY 4.0)*.
- Germany: *Postleitzahlgebiete: © OpenStreetMap contributors (ODbL) · Place
  names: GeoNames (CC BY 4.0)*.
- Basemap: OpenFreeMap, OpenMapTiles, © OpenStreetMap contributors (added
  by MapLibre from the style).

Keep these visible in any deployment. The derived GB and Austrian polygons
are derivatives of the respective point data and carry the same terms.

Germany is the one country under a **share-alike** licence. Its polygons
come from OpenStreetMap under the Open Database License (ODbL), so
`countries/de/` (tiles and search index) is a derivative database that is
itself ODbL and may be reused on those terms. Every country's data lives in
its own archive and index, which makes the site a collective database in
the ODbL's sense: the German files are ODbL and the others keep their own
permissive licences. Keep it that way when reusing the data: do not merge
the German polygons into a file with any other country's, and if you build
something on the German files, publish it under ODbL with the
OpenStreetMap attribution.
