#!/usr/bin/env python3
"""Build the static search index consumed by the web app.

  <out>/index.json           {"areas":{code:[minx,miny,maxx,maxy]}, "districts":..., "sectors":...}
  <out>/units/<DISTRICT>.json {"SW1A 2AA":[lon,lat], ...}   one file per district
"""
import argparse
import csv
import json
import os
from collections import defaultdict


def bboxes(path):
    out = {}
    with open(path) as f:
        for line in f:
            p = json.loads(line)["properties"]
            out[p["code"]] = [p["minx"], p["miny"], p["maxx"], p["maxy"]]
    return out


def bbox_of(points):
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs), max(ys)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units")
    ap.add_argument("--polygons", required=True, help="directory with *_labels.geojsonl")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "units"), exist_ok=True)

    index = {lvl: bboxes(os.path.join(a.polygons, f"{lvl}.geojsonl")) for lvl in ("areas", "districts", "sectors")}
    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"))

    by_district = defaultdict(dict)
    with open(a.units, newline="") as f:
        for row in csv.DictReader(f):
            by_district[row["district"]][row["postcode"]] = [round(float(row["lon"]), 5), round(float(row["lat"]), 5)]
    added = 0
    for d, units in by_district.items():
        with open(os.path.join(a.out, "units", f"{d}.json"), "w") as f:
            json.dump(units, f, separators=(",", ":"))
        # A district (or sector) can lack a polygon when all its units share
        # coordinates with another district's units; keep it searchable.
        if d not in index["districts"]:
            index["districts"][d] = bbox_of(units.values())
            added += 1
        for s in {pc[: pc.index(" ") + 2] for pc in units}:
            if s not in index["sectors"]:
                index["sectors"][s] = bbox_of(v for pc, v in units.items() if pc.startswith(s))
                added += 1
    if added:
        with open(os.path.join(a.out, "index.json"), "w") as f:
            json.dump(index, f, separators=(",", ":"))
        print(f"build_index: {added} districts/sectors without polygons indexed from unit points")
    print(f"build_index: {sum(len(v) for v in index.values())} polygons, {len(by_district)} district unit files")


if __name__ == "__main__":
    main()
