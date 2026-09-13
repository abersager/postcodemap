#!/usr/bin/env python3
"""Tile one country's polygons, boundary lines, labels and points with tippecanoe.

    python pipeline/build_tiles.py <cc> <polygons_dir> <units.csv> --out <dir> [--tmp <dir>]

Writes <out>/boundaries.pmtiles (all polygon levels, their `<id>_labels`
layers and, for polygons clipped to a land mask, `<id>_lines` boundary layers
that leave out the coast; unclipped official polygons are outlined directly by
the app) and, for countries with a point level, <out>/points.pmtiles.

Zoom ranges follow the country's default thresholds with two levels of
headroom below (thresholds can be lowered in config without re-tiling) and
nothing beyond z12 for polygons or z13 for points: MapLibre overzooms the
last level, which is exact for points and straight Voronoi edges. A level
whose threshold lies above z12 (NL PC6 at 13) is tiled at z12 only. Label
features carry just the code, hover and click read the polygon's properties.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import countries  # noqa: E402

POLY_MAX = 12
POINT_Z = 13


def run(args):
    print("+", " ".join(a if " " not in a else repr(a) for a in args), file=sys.stderr, flush=True)
    subprocess.run(args, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("country")
    ap.add_argument("polygons")
    ap.add_argument("units")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tmp")
    a = ap.parse_args()
    mod = countries.get(a.country)
    tmp = a.tmp or os.path.join(os.path.dirname(a.units), "tiles")
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    derived = not hasattr(mod, "read_polygons")
    lines = countries.clipped(mod)
    attr = mod.ATTRIBUTION + (" &middot; Postcode polygons are derived (Voronoi of unit points), not official." if derived else "")
    common = ["--force", "--no-tile-size-limit", "--no-feature-limit", f"--attribution={attr}"]

    parts = []
    levels = mod.LEVELS
    for i, lvl in enumerate(levels):
        minz = POLY_MAX if lvl["threshold"] > POLY_MAX else max(0, lvl["threshold"] - 2)
        maxz = POLY_MAX if i > 0 else max(levels[1]["threshold"] + 2, 6) if len(levels) > 1 else POLY_MAX
        lid = lvl["id"]
        poly, lines_pm, labels = (os.path.join(tmp, f"{lid}{s}.pmtiles") for s in ("", "_lines", "_labels"))
        run(["tippecanoe", *common, "--detect-shared-borders", "--simplification=4", "-o", poly, "-l", lid, f"-Z{minz}", f"-z{maxz}", os.path.join(a.polygons, f"{lid}.geojsonl")])
        run(["tippecanoe", *common, "-r1", "-y", "code", "-o", labels, "-l", f"{lid}_labels", f"-Z{minz}", f"-z{maxz}", os.path.join(a.polygons, f"{lid}_labels.geojsonl")])
        parts += [poly, labels]
        if lines:
            run(["tippecanoe", *common, "--simplification=4", "-o", lines_pm, "-l", f"{lid}_lines", f"-Z{minz}", f"-z{maxz}", os.path.join(a.polygons, f"{lid}_lines.geojsonl")])
            parts.append(lines_pm)
    # tile-join has its own 500 KB tile limit (-pk lifts it) and silently drops features beyond it
    run(["tile-join", "--force", "-pk", "-o", os.path.join(a.out, "boundaries.pmtiles"), f"--name={mod.NAME} postcode boundaries{' (derived)' if derived else ''}", f"--attribution={attr}", *parts])

    if mod.POINT_LEVEL:
        z = max(POINT_Z, mod.POINT_LEVEL["threshold"])
        run(["tippecanoe", *common, "-r1", "-o", os.path.join(a.out, "points.pmtiles"), "-l", "points", f"-Z{z}", f"-z{z}", f"-B{z}",
             f"--name={mod.NAME} unit postcode points", "-y", "code", *[x for l in levels for x in ("-y", l["id"])], a.units])
    for f in os.listdir(a.out):
        p = os.path.join(a.out, f)
        print(f"{p}: {os.path.getsize(p) / 1e6:.1f} MB", file=sys.stderr)


if __name__ == "__main__":
    main()
