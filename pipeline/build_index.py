#!/usr/bin/env python3
"""Build a country's static search index and its meta.json for the app.

    python pipeline/build_index.py <cc> <polygons_dir> <units.csv> --out <dir>

  <out>/meta.json      country description consumed by the app (levels, thresholds,
                       bounds, attribution, point level, shard level)
  <out>/index.json     {"<level id>": {code: [minx, miny, maxx, maxy, units, km2, name?]}, ...}
  <out>/units.bin      for countries with a point level: the per-SHARD_LEVEL point
                       lists, each a gzipped JSON {"<point code>": [lon, lat], ...},
                       concatenated; index.json["shards"] maps shard code ->
                       [offset, length] so the app fetches one slice with a
                       range request (one file instead of thousands)
"""
import gzip
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import countries  # noqa: E402


def read_level(path):
    out = {}
    with open(path) as f:
        for line in f:
            p = json.loads(line)["properties"]
            row = [p["minx"], p["miny"], p["maxx"], p["maxy"], p["units"], p.get("km2", 0)]
            if p.get("name"):
                row.append(p["name"])
            out[p["code"]] = row
    return out


def bbox_of(points):
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs), max(ys)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("country")
    ap.add_argument("polygons")
    ap.add_argument("units")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    mod = countries.get(a.country)
    os.makedirs(a.out, exist_ok=True)
    level_ids = [l["id"] for l in mod.LEVELS]

    index = {l: read_level(os.path.join(a.polygons, f"{l}.geojsonl")) for l in level_ids}
    bounds = [180, 90, -180, -90]
    for row in index[level_ids[0]].values():
        bounds = [min(bounds[0], row[0]), min(bounds[1], row[1]), max(bounds[2], row[2]), max(bounds[3], row[3])]

    added = 0
    if mod.POINT_LEVEL:
        shards = defaultdict(dict)
        by_level = {l: defaultdict(list) for l in level_ids}
        with open(a.units, newline="") as f:
            for row in csv.DictReader(f):
                pt = [round(float(row["lon"]), 5), round(float(row["lat"]), 5)]
                shards[row[mod.SHARD_LEVEL]][row["code"]] = pt
                for l in level_ids:
                    if row[l] not in index[l]:
                        by_level[l][row[l]].append(pt)
        directory = {}
        with open(os.path.join(a.out, "units.bin"), "wb") as f:
            for shard in sorted(shards):
                blob = gzip.compress(json.dumps(shards[shard], separators=(",", ":")).encode(), mtime=0)
                directory[shard] = [f.tell(), len(blob)]
                f.write(blob)
        index["shards"] = directory
        # codes without a polygon (all their points shared with another code) stay searchable
        for l in level_ids:
            for code, pts in by_level[l].items():
                index[l][code] = bbox_of(pts) + [len(pts), 0]
                added += 1
        print(f"build_index[{a.country}]: {len(shards)} point shards packed into units.bin ({os.path.getsize(os.path.join(a.out, 'units.bin')) / 1e6:.1f} MB), {added} polygon-less codes indexed from points", file=sys.stderr)

    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"), ensure_ascii=False)

    meta = {
        "code": mod.CODE, "name": mod.NAME,
        "levels": [{"id": l["id"], "name": l["name"], "threshold": l["threshold"]} for l in mod.LEVELS],
        "pointLevel": mod.POINT_LEVEL, "shardLevel": mod.SHARD_LEVEL,
        "pointNoun": getattr(mod, "POINT_NOUN", (mod.POINT_LEVEL or {}).get("noun", "points")),
        "bounds": [round(b, 4) for b in bounds],
        "attribution": mod.ATTRIBUTION, "licence": mod.LICENCE,
        "counts": {l: len(index[l]) for l in level_ids},
        "hasPoints": bool(mod.POINT_LEVEL),
    }
    with open(os.path.join(a.out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print(f"build_index[{a.country}]: {sum(len(index[l]) for l in level_ids)} codes, bounds {meta['bounds']}", file=sys.stderr)


if __name__ == "__main__":
    main()
