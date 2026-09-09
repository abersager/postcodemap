#!/usr/bin/env bash
# Tile the derived polygons and unit points into two PMTiles archives.
#
#   boundaries.pmtiles  areas, districts, sectors polygons, their interior
#                       boundary lines and label points               ~ tens of MB
#   units.pmtiles       1.7M unit centroids at z13                   ~ 20 MB
#
# Zoom ranges cover the app's thresholds (web/config.js) plus the density shift
# of up to +2. Nothing is tiled beyond z12 for boundaries or z13 for units:
# MapLibre overzooms the last level, which is exact for points and straight
# Voronoi edges, and it keeps the archives small. Small matters on GitHub
# Pages, whose CDN fetches a whole file on a cold range request. Lower the
# thresholds below the -Z values here and you must widen them and re-tile.
set -euo pipefail
POLY_DIR=${1:?polygons dir}
UNITS_CSV=${2:?units csv}
OUT_DIR=${3:?output dir}
TMP=${TMP_DIR:-$(dirname "$UNITS_CSV")/tiles}
mkdir -p "$OUT_DIR" "$TMP"

ATTR='Contains OS data &copy; Crown copyright and database right 2026. Contains Royal Mail data &copy; Royal Mail copyright and database right 2026. Contains ONS data &copy; Crown copyright and database right 2026, Open Government Licence v3.0. Postcode polygons are derived (Voronoi of unit centroids), not official.'

common=(--force --detect-shared-borders --no-tile-size-limit --no-feature-limit --attribution="$ATTR")

tippecanoe "${common[@]}" -o "$TMP/areas.pmtiles"     -l areas     -Z0 -z10 --simplification=4 "$POLY_DIR/areas.geojsonl"
tippecanoe "${common[@]}" -o "$TMP/districts.pmtiles" -l districts -Z6 -z12 --simplification=4 "$POLY_DIR/districts.geojsonl"
tippecanoe "${common[@]}" -o "$TMP/sectors.pmtiles"   -l sectors   -Z9 -z12 --simplification=4 "$POLY_DIR/sectors.geojsonl"
lines=(--force --no-tile-size-limit --no-feature-limit --simplification=4 --attribution="$ATTR")
tippecanoe "${lines[@]}" -o "$TMP/area_lines.pmtiles"     -l area_lines     -Z0 -z10 "$POLY_DIR/areas_lines.geojsonl"
tippecanoe "${lines[@]}" -o "$TMP/district_lines.pmtiles" -l district_lines -Z6 -z12 "$POLY_DIR/districts_lines.geojsonl"
tippecanoe "${lines[@]}" -o "$TMP/sector_lines.pmtiles"   -l sector_lines   -Z9 -z12 "$POLY_DIR/sectors_lines.geojsonl"
tippecanoe --force -r1 --no-tile-size-limit --no-feature-limit -o "$TMP/area_labels.pmtiles"     -l area_labels     -Z0 -z10 "$POLY_DIR/areas_labels.geojsonl"
tippecanoe --force -r1 --no-tile-size-limit --no-feature-limit -o "$TMP/district_labels.pmtiles" -l district_labels -Z6 -z12 "$POLY_DIR/districts_labels.geojsonl"
tippecanoe --force -r1 --no-tile-size-limit --no-feature-limit -o "$TMP/sector_labels.pmtiles"   -l sector_labels   -Z9 -z12 "$POLY_DIR/sectors_labels.geojsonl"

tile-join --force -o "$OUT_DIR/boundaries.pmtiles" --name="UK postcode boundaries (derived)" --attribution="$ATTR" \
  "$TMP/areas.pmtiles" "$TMP/districts.pmtiles" "$TMP/sectors.pmtiles" \
  "$TMP/area_lines.pmtiles" "$TMP/district_lines.pmtiles" "$TMP/sector_lines.pmtiles" \
  "$TMP/area_labels.pmtiles" "$TMP/district_labels.pmtiles" "$TMP/sector_labels.pmtiles"

# Units: every point, tiled at z13 only and overzoomed by MapLibre beyond it.
tippecanoe --force -o "$OUT_DIR/units.pmtiles" -l units -Z13 -z13 -B13 -r1 \
  --no-feature-limit --no-tile-size-limit \
  --name="UK unit postcode centroids" --attribution="$ATTR" \
  -y postcode -y sector -y district -y area "$UNITS_CSV"

ls -la "$OUT_DIR"
