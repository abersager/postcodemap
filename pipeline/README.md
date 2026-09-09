# Data pipeline

Reproducible build of every data file the app needs. Nothing generated is
committed; `make` regenerates it all from the live sources.

```
Code-Point Open zip ─┐
ONSPD zip (optional) ├─ build_points.py ──► data/build/units.csv
any postcode CSV    ─┘                          │
                                                ▼
ONS coastline GeoJSON ──────────────── build_polygons.py ──► data/build/polygons/*.geojsonl
(fetch_coastline.py, optional)                  │
                                                ▼
                                       build_tiles.sh ──► web/public/tiles/{boundaries,units}.pmtiles
                                       build_index.py ──► web/public/data/index.json + units/<DISTRICT>.json
```

## Tools

- Python 3.10+ with `pip install -r pipeline/requirements.txt` (numpy, scipy,
  shapely ≥ 2.0, pyproj).
- [tippecanoe](https://github.com/felt/tippecanoe) ≥ 2.17 (writes `.pmtiles`
  directly; 2.78 was used here). macOS: `brew install tippecanoe`. Linux:

  ```bash
  git clone --depth 1 https://github.com/felt/tippecanoe.git
  cd tippecanoe && make -j4 && sudo make install     # needs g++, make, libsqlite3-dev, zlib1g-dev
  ```
- `curl`, `make`.

## Targets

| Command                          | What it does                                                        |
|----------------------------------|---------------------------------------------------------------------|
| `make`                           | download → points → polygons → tiles → index, for all of GB         |
| `make sample SAMPLE_AREAS=SW,EH` | same, but only the listed areas (seconds instead of minutes)        |
| `make polygons` / `make tiles`   | run a single stage (make tracks what is stale)                      |
| `make clean`                     | delete generated data, keep downloads                               |
| `make distclean`                 | delete downloads too                                                |

Variables (set on the command line):

| Variable        | Default                                   | Notes                                                    |
|-----------------|-------------------------------------------|----------------------------------------------------------|
| `SOURCE`        | `codepoint`                               | `codepoint`, `onspd` or `csv`                            |
| `CODEPOINT_URL` | OS Downloads API CSV URL                  | no key needed                                            |
| `ONSPD_ZIP`     | `data/raw/onspd.zip`                      | download manually from the ONS Open Geography Portal     |
| `INCLUDE_NI`    | `0`                                       | `1` keeps BT postcodes from ONSPD (see licence caveat)   |
| `CSV_FILE`      |                                           | any `postcode,lat,lon` CSV or zip when `SOURCE=csv`      |
| `COASTLINE`     | `data/raw/coastline.geojson`              | clip mask; auto-fetched from ONS if missing              |
| `COASTLINE_URL` |                                           | explicit ArcGIS FeatureServer layer URL, e.g. a BFC layer|

## Stages

### 1. `build_points.py`

Reads the source, normalises each postcode to `OUTWARD INWARD`, drops rows
without coordinates (Code-Point Open positional quality 90; ONSPD lat 99.99),
drops terminated postcodes (ONSPD `doterm`), dedupes, derives the area,
district and sector codes and writes `units.csv` in WGS84. Code-Point Open
eastings/northings are transformed from EPSG:27700 with pyproj.

### 2. `build_polygons.py`

1. Projects every unit to EPSG:27700 and computes the Voronoi diagram of all
   distinct locations (scipy/Qhull; 1.7 M points take ~40 s). Sixteen sentinel
   points far outside the UK keep every real cell finite.
2. Where several units share one location, the sector with most units there
   owns the cell. Sectors whose units *all* coincide with another sector's
   (a handful of large-user postcodes in central London) get no polygon; they
   are listed in `report.json` and remain searchable through the unit index.
3. Cells are dissolved to sectors, sectors to districts, districts to areas
   with GEOS coverage unions (exact shared edges, so no slivers).
4. Every level is clipped to the land mask, cut into 25 km pieces for speed.
   The mask is the ONS country boundaries when available; otherwise a 1 km
   occupancy grid of the points dilated by 2 km (visibly blocky at the
   coast, flagged as `"mask": "grid"` in `report.json`). Unit locations that
   fall outside the mask get a 250 m buffer added so nothing disappears.
5. Writes newline-delimited GeoJSON per level, plus label points (centre of
   the largest inscribed circle of the biggest part) with the same
   properties: `code`, `level`, `units` (count), `minx/miny/maxx/maxy`
   (WGS84 bbox, used for click-to-zoom and search), `parent`, `area`,
   `district`.

### 3. `build_tiles.sh`

One tippecanoe run per layer, then `tile-join` into two archives:

- `boundaries.pmtiles`: `areas` (z0–12), `districts` (z5–14), `sectors`
  (z8–14) and the matching `*_labels` point layers. `--detect-shared-borders`
  keeps neighbouring polygons consistent when simplified.
- `units.pmtiles`: `units` points z12–14. Nothing is dropped from z13 up;
  at z12 the densest points are thinned only if a tile would exceed 500 KB.
  MapLibre overzooms z14 tiles for street-level views.

### 4. `build_index.py`

Static search index: `index.json` maps every area, district and sector code
to its bbox; `units/<DISTRICT>.json` maps each unit in that district to
`[lon, lat]`. The app loads a district file on demand when a unit-level
search is made.

## Timings (4 cores, 15 GB RAM, October 2017 test extract of 1.74 M postcodes)

| Stage           | Time   | Output                                  |
|-----------------|--------|-----------------------------------------|
| build_points    | 7 s    | units.csv, 1,738,088 rows (98 MB)       |
| build_polygons  | 105 s  | 10,819 sectors, 2,948 districts, 121 areas; 40 MB GeoJSON |
| build_tiles     | ~4 min | boundaries.pmtiles 69 MB, units.pmtiles 70 MB |
| build_index     | 20 s   | 2,958 district files, 57 MB             |

Peak memory is about 4 GB during the Voronoi step.

## Alternative polygon inputs

The app only needs `areas/districts/sectors.geojsonl` with the properties
listed above. If you prefer a third-party polygon set (for example the
doogal.co.uk district and sector KML, which is built by the same Voronoi
method), convert it to those files with `ogr2ogr -f GeoJSONSeq`, add the
properties, and run `make tiles index`. Note licensing: such files inherit
the OS/Royal Mail terms and add the publisher's own.

## Refreshing after a Royal Mail update

Code-Point Open is republished each February, May, August and November.
Run `make distclean && make`, then `npm run build` and redeploy. Update the
copyright years in `web/config.js` and `pipeline/build_tiles.sh` once a year.
