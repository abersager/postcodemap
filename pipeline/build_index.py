#!/usr/bin/env python3
"""Build a country's static search index and its meta.json for the app.

    python pipeline/build_index.py <cc> <polygons_dir> <units.csv> --out <dir>

  <out>/meta.json      country description consumed by the app (levels, thresholds,
                       bounds, attribution, point level, shard level, density level)
  <out>/index.json     {"<level id>": {code: [minx, miny, maxx, maxy, units, km2, name?]}, ...}
                       for every polygon level except the SHARDED_LEVELS
  <out>/units.bin      one gzipped JSON slice per SHARD_LEVEL code, concatenated;
                       index.json["shards"] maps shard code -> [offset, length] so
                       the app fetches one slice with a range request. A slice is
                       {"<level id>": {code: value}} where value is [lon, lat] for
                       the point level (GB unit postcodes) or [minx, miny, maxx, maxy]
                       for a sharded polygon level (NL PC5/PC6)
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
    sharded = list(getattr(mod, "SHARDED_LEVELS", []) or [])
    shard_level = mod.SHARD_LEVEL if (mod.POINT_LEVEL or sharded) else None

    tables = {l: read_level(os.path.join(a.polygons, f"{l}.geojsonl")) for l in level_ids}
    index = {l: tables[l] for l in level_ids if l not in sharded}
    bounds = [180, 90, -180, -90]
    for row in tables[level_ids[0]].values():
        bounds = [min(bounds[0], row[0]), min(bounds[1], row[1]), max(bounds[2], row[2]), max(bounds[3], row[3])]

    added = 0
    shards = defaultdict(lambda: defaultdict(dict))  # shard code -> level id -> code -> value
    if shard_level:
        by_level = {l: defaultdict(list) for l in level_ids}
        with open(a.units, newline="") as f:
            for row in csv.DictReader(f):
                pt = [round(float(row["lon"]), 5), round(float(row["lat"]), 5)]
                shard = shards[row[shard_level]]
                if mod.POINT_LEVEL:
                    shard[mod.POINT_LEVEL["id"]][row["code"]] = pt
                for l in sharded:
                    if row[l] in tables[l]:
                        shard[l][row[l]] = tables[l][row[l]][:4]
                for l in level_ids:
                    if l not in sharded and row[l] not in index[l]:
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
            if l in sharded:
                continue
            for code, pts in by_level[l].items():
                index[l][code] = bbox_of(pts) + [len(pts), 0]
                added += 1
        print(f"build_index[{a.country}]: {len(shards)} shards packed into units.bin ({os.path.getsize(os.path.join(a.out, 'units.bin')) / 1e6:.1f} MB), {added} polygon-less codes indexed from points", file=sys.stderr)

    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"), ensure_ascii=False)

    meta = {
        "code": mod.CODE, "name": mod.NAME,
        "levels": [{"id": l["id"], "name": l["name"], "threshold": l["threshold"]} for l in mod.LEVELS],
        "pointLevel": mod.POINT_LEVEL, "shardLevel": shard_level, "shardedLevels": sharded,
        "densityLevel": getattr(mod, "DENSITY_LEVEL", None) or level_ids[-1],
        "pointNoun": getattr(mod, "POINT_NOUN", (mod.POINT_LEVEL or {}).get("noun", "points")),
        "bounds": [round(b, 4) for b in bounds],
        "attribution": mod.ATTRIBUTION, "licence": mod.LICENCE,
        "official": hasattr(mod, "read_polygons"),
        "counts": {l: len(tables[l]) for l in level_ids},
        "hasPoints": bool(mod.POINT_LEVEL), "hasShards": bool(shard_level),
    }
    with open(os.path.join(a.out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print(f"build_index[{a.country}]: {sum(len(tables[l]) for l in level_ids)} codes, bounds {meta['bounds']}", file=sys.stderr)


if __name__ == "__main__":
    main()
