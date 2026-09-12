#!/usr/bin/env python3
"""Read a country's point data and write build/units.csv.

    python pipeline/build_points.py <cc> <raw_dir> --out units.csv [--areas SW,EH]

Output columns: code,<one column per polygon level>,lon,lat  (WGS84, 6 dp).
Every row is one point: a unit postcode (GB) or an address (AT), whose
finest code is `code`. --areas keeps only points whose coarsest level code
is in the list (for quick sample builds).
"""
import argparse
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import countries  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("country")
    ap.add_argument("raw_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--areas", help="Comma-separated coarsest-level codes to keep")
    a = ap.parse_args()
    mod = countries.get(a.country)
    level_ids = [l["id"] for l in mod.LEVELS]
    keep = set(a.areas.upper().split(",")) if a.areas else None
    stats = Counter()
    seen = set()
    dedupe = mod.POINT_LEVEL is not None  # unit postcodes must be unique; addresses need not be
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", *level_ids, "lon", "lat"])
        for raw, lon, lat in mod.read_units(a.raw_dir):
            stats["read"] += 1
            p = mod.parse(raw)
            if p is None:
                stats["unparseable"] += 1
                continue
            if keep and p[level_ids[0]] not in keep:
                continue
            if dedupe:
                if p["code"] in seen:
                    stats["duplicate"] += 1
                    continue
                seen.add(p["code"])
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                stats["out_of_range"] += 1
                continue
            w.writerow([p["code"], *(p[l] for l in level_ids), f"{lon:.6f}", f"{lat:.6f}"])
            stats["written"] += 1
    print(f"build_points[{a.country}]:", dict(stats), file=sys.stderr)


if __name__ == "__main__":
    main()
