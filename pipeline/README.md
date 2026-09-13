# Data pipeline

Reproducible build of every data file the app needs, one country at a time.
Nothing generated is committed; `make COUNTRY=<cc>` regenerates it all from the
live sources.

```
pipeline/countries/<cc>.py ─ download() ──► data/<cc>/raw/
                           ─ read_units() + parse()
                                   │
                    build_points.py ──► data/<cc>/build/units.csv
                                   │
  <cc>.mask() ──► build_polygons.py ──► data/<cc>/build/polygons/<level>.geojsonl (+ _lines, _labels)
                                   │
                    build_tiles.py ──► web/public/countries/<cc>/boundaries.pmtiles (+ points.pmtiles)
                    build_index.py ──► web/public/countries/<cc>/index.json, units.bin, meta.json
```

## Country modules

Each country is a module in `pipeline/countries/` implementing the interface
documented in `countries/__init__.py`: its levels (coarse to fine) with default
zoom thresholds, an optional point level, attribution, `download()`,
`read_units()` (one point per unit postcode or address, with its finest code),
`parse()` (splits a code into the levels) and optionally `names()` and `mask()`
(land polygons for clipping). A country with official polygons implements
`read_polygons()` instead of relying on the Voronoi derivation; its
`read_units()` then yields either one representative point per finest code
(NL) or the country's addresses (NO, `POINT_NOUN = "addresses"`), which give
the counts. If it also provides `mask()`, the official polygons are clipped
to it (NO, whose polygons run out to sea). The generic scripts never contain
country logic.

| Country | Module | Source | Levels | Polygons |
|---|---|---|---|---|
| Great Britain | `gb.py` | OS Code-Point Open unit postcodes (1.7 M); ONSPD or a CSV via `SOURCE=` | area, district, sector + unit points | derived, clipped to ONS country boundaries (BGC) |
| Austria | `at.py` | BEV Adressregister addresses (2.5 M), each with its PLZ | zone (1 digit), region (2 digits), PLZ | derived, clipped to Statistik Austria municipalities |
| Netherlands | `nl.py` | CBS "Kerncijfers per postcode" PC6 GeoPackage (466 k polygons); GeoNames for PC4 names | pc2, pc4, pc5, pc6 | official PC6, coarser levels dissolved |
| Norway | `no.py` | Kartverket Postnummerområder GeoJSON (3.4 k polygons, names included); Matrikkelen addresses CSV (2.6 M); N500 Kartdata GML for the land mask | zone, region, postnr | official, clipped to N500 land areas (everything but `Havflate`), coarser levels dissolved |

## Tools

- [uv](https://docs.astral.sh/uv/) (`brew install uv`). Dependencies (numpy,
  scipy, shapely ≥ 2.0, pyproj, pyshp) are declared in `pyproject.toml` and
  pinned in `uv.lock`; the Makefile runs every script through `uv run python`.
  Override the interpreter with `make PYTHON="poetry run python"`.
- [tippecanoe](https://github.com/felt/tippecanoe) ≥ 2.17 (writes `.pmtiles`
  directly). macOS: `brew install tippecanoe`. Linux:

  ```bash
  git clone --depth 1 https://github.com/felt/tippecanoe.git
  cd tippecanoe && make -j4 && sudo make install     # needs g++, make, libsqlite3-dev, zlib1g-dev
  ```

## Targets

| Command | What it does |
|---|---|
| `make` / `make COUNTRY=gb` | download → points → polygons → tiles → index for Great Britain |
| `make COUNTRY=at` | the same for Austria (any module in `pipeline/countries/`) |
| `make sample COUNTRY=gb SAMPLE_AREAS=SW,EH` | only the listed top-level codes (seconds instead of minutes) |
| `make polygons COUNTRY=at` | run a single stage (make tracks what is stale) |
| `make clean COUNTRY=at` | delete that country's generated data, keep downloads |
| `make distclean COUNTRY=at` | delete its downloads too |

GB-only variables: `SOURCE=codepoint|onspd|csv` (default codepoint),
`ONSPD_ZIP`, `CSV_FILE`, `INCLUDE_NI=1` (keeps Northern Ireland from ONSPD;
separate licence, see docs/CAVEATS.md), `COASTLINE_URL`.

## Stages

### 1. `build_points.py`

Calls the country module's `read_units()` and `parse()`, drops unparseable
codes, dedupes unit postcodes (addresses are not deduped) and writes
`units.csv`: `code,<one column per polygon level>,lon,lat` in WGS84.

### 2. `build_polygons.py`

For a country with `read_polygons()` (NL, NO) the finest level is read as
given, projected to the local transverse Mercator and dissolved into each
coarser level with coverage unions (checked, with a proper union as fallback
where the source overlaps itself). Without a `mask()` (NL) nothing is
clipped; with one (NO) every level is clipped like derived polygons, except
that polygons entirely outside the mask's extent (Svalbard and Jan Mayen,
beyond N500) are kept whole. Polygons whose code has no address keep a count
of 0. Otherwise:

1. Projects every point to a local transverse Mercator centred on the data and
   computes the Voronoi diagram of all distinct locations (scipy/Qhull; 1.7 M
   points take ~40 s). Sixteen sentinel points far outside keep every real
   cell finite.
2. Where several points share one location, the finest-level code with most
   points there owns the cell. Sectors whose units *all* coincide with another sector's
   (PO-box and large-user sectors such as BS99 or EC3P, 232 in the 2017 test
   data, fewer with Code-Point Open which drops them upstream) get no polygon; they
   are listed in `report.json` and remain searchable through the unit index.
3. Cells are dissolved into the finest level, then each level into the next
   coarser one, with GEOS coverage unions (exact shared edges, so no slivers).
4. Every level is clipped to the land mask, cut into 25 km pieces for speed.
   The mask is whatever the country module provides (ONS country boundaries
   for GB, the union of municipalities for AT); otherwise a 1 km
   occupancy grid of the points dilated by 2 km (visibly blocky at the
   coast, flagged as `"mask": "grid"` in `report.json`). Unit locations that
   fall outside the mask get a 250 m buffer added so nothing disappears.
   The coastline is prepared first: countries containing no postcodes are
   dropped (Northern Ireland with Code-Point Open, otherwise Scottish cells
   would claim its land) and inland water smaller than 4 km² is filled
   (`MIN_HOLE_M2`). The prepared mask is cached in `data/build/mask-cache.pkl`
   and reused until the coastline file changes.
5. Boundary *lines* are written separately from the polygons
   (`*_lines.geojsonl`): the edges shared by two polygons of a level, clipped
   to land. They never follow the coast, so the map draws postcode
   boundaries only and leaves the coastline to the basemap. The polygons
   (which do follow the ONS coast, tidal rivers included) are used for
   hover, click and search highlighting.
6. Writes newline-delimited GeoJSON per level, plus label points (centre of
   the largest inscribed circle of the biggest part) with the same
   properties: `code`, `level`, `units` (count), `km2` (land area),
   `minx/miny/maxx/maxy` (WGS84 bbox, used for click-to-zoom and search),
   `parent`, `area`, `district`.

### 3. `build_tiles.py`

One tippecanoe run per layer, then `tile-join` into `boundaries.pmtiles` and,
for countries with a point level, `points.pmtiles`:

- `boundaries.pmtiles`: one polygon layer per level (GB: `area` z0–10,
  `district` z6–12, `sector` z9–12) and its `*_labels` point layer (code
  only). Levels clipped to a land mask (derived ones, and official ones with
  a `mask()` such as NO) also get a `*_lines` layer with the boundaries
  between polygons but not the coast; unclipped official polygons (NL) are
  outlined by the app directly, which halves their archive (`meta.json`
  `lines` says which). A level whose threshold is above z12 (NL `pc6` at 13)
  is tiled at z12 only. `--detect-shared-borders`
  keeps neighbouring polygons consistent when simplified. MapLibre overzooms
  z12 tiles for closer views; boundary lines are straight Voronoi edges or
  official outlines, so that costs little visible.
- `points.pmtiles`: every unit point at z13, overzoomed beyond.

Zoom ranges are kept tight on purpose: GitHub Pages' CDN fetches a whole
file on a cold range request and caches it for only ten minutes, so archive
size directly sets how long the first visitor waits.

### 4. `build_index.py`

Static search index: `index.json` maps every polygon code to
`[minx, miny, maxx, maxy, units, km2, name?]` (the app also uses units/km2 to
adapt the zoom thresholds to postcode density); for countries with a point
level (GB) or with `SHARDED_LEVELS` (NL PC5/PC6, too many for `index.json`),
`units.bin` holds one gzipped JSON slice per `SHARD_LEVEL` code, concatenated,
with `index.json["shards"]` giving each slice's byte offset and length, so a
search below the indexed levels is one range request. A slice is
`{"<level id>": {code: value}}` with `[lon, lat]` for points and
`[minx, miny, maxx, maxy]` for sharded polygons. `meta.json` also names the
`densityLevel` whose units/km² drives the app's density shift (the finest
polygon level by default; PC4 for NL, where the finest polygons each hold
one code).

## Timings (4 cores, 15 GB RAM, October 2017 test extract of 1.74 M postcodes)

| Stage           | Time   | Output                                  |
|-----------------|--------|-----------------------------------------|
| build_points    | 7 s    | units.csv, 1,738,088 rows (98 MB)       |
| build_polygons  | 107 s  | 10,879 sectors, 2,942 districts, 121 areas; 40 MB GeoJSON |
| build_tiles     | ~3 min | boundaries.pmtiles 30 MB, units.pmtiles 22 MB |
| build_index     | 20 s   | 2,958 district files, 57 MB             |

Peak memory is about 4 GB during the Voronoi step. Preparing the ONS coastline
takes about 30 s the first time and is cached afterwards.

## Official polygon inputs

A country whose postal operator or statistics office publishes polygons
implements `read_polygons(raw_dir)` in its module, yielding
`(raw_code, shapely geometry in WGS84)` for every finest-level polygon
(`countries/nl.py` reads them straight out of a GeoPackage with sqlite3,
`countries/no.py` from GeoJSON). `build_polygons.py` then skips the Voronoi
step, and the clipping step too unless the module provides a `mask()`
(`no.py` builds one from the N500 land-cover GML with the standard library's
XML parser: every area type except the sea surface, unioned). For GB a
third-party polygon set (for example the doogal.co.uk district and sector
KML, itself Voronoi-derived) could be wired in the same way, but it would
inherit the OS/Royal Mail terms plus the publisher's own.

## Refreshing after a Royal Mail update

Code-Point Open is republished each February, May, August and November.
Run `make distclean && make`, then `npm run build` and redeploy. Update the
copyright years in `web/config.js` and `pipeline/build_tiles.sh` once a year.
