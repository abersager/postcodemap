#!/usr/bin/env python3
"""Read unit postcode centroids from an open source and write build/units.csv.

Output columns: postcode,area,district,sector,lon,lat  (WGS84, 6 dp)

Supported --format values
  codepoint  OS Code-Point Open zip (codepo_gb.zip). GB only. EPSG:27700 in.
  onspd      ONS Postcode Directory zip. UK. Uses the lat/long columns; drops
             terminated postcodes; drops Northern Ireland (BT) unless
             --include-ni is given (separate licence, see docs/CAVEATS.md).
  csv        Any CSV with header containing 'postcode' and lat/lon columns.
"""
import argparse
import csv
import io
import sys
import zipfile
from collections import Counter

from postcode import normalise

CODEPOINT_COLS = ["PC", "PQ", "EA", "NO", "CY", "RH", "LH", "CC", "DC", "WC"]


def iter_codepoint(path):
    from pyproj import Transformer
    import numpy as np

    tr = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv") and ("data/csv/" in n.lower())]
        if not names:
            sys.exit("No Data/CSV/*.csv files found in Code-Point Open zip")
        for name in sorted(names):
            rows, es, ns = [], [], []
            with z.open(name) as f:
                for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if len(row) < 4:
                        continue
                    pc, pq, e, n = row[0], row[1], row[2], row[3]
                    if pq == "90" or not e or not n:
                        continue  # no usable coordinates
                    rows.append(pc)
                    es.append(float(e))
                    ns.append(float(n))
            if rows:
                lon, lat = tr.transform(np.array(es), np.array(ns))
                for pc, lo, la in zip(rows, lon, lat):
                    yield pc, float(lo), float(la)


def iter_onspd(path, include_ni):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv") and "/data/" in n.lower() and "multi_csv" not in n.lower()]
        names = [n for n in names if n.split("/")[-1].upper().startswith("ONSPD_")]
        if not names:
            sys.exit("No Data/ONSPD_*.csv found in ONSPD zip")
        name = sorted(names, key=len)[0]
        with z.open(name) as f:
            r = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in r:
                if row.get("doterm"):
                    continue  # terminated
                pc = row["pcds"]
                if not include_ni and pc.startswith("BT"):
                    continue
                try:
                    lat, lon = float(row["lat"]), float(row["long"])
                except (ValueError, KeyError):
                    continue
                if lat > 90 or lat == 0:  # ONSPD uses 99.999999 for unknown
                    continue
                yield pc, lon, lat


def iter_csv(path):
    opener = (lambda p: zipfile.ZipFile(p).open(zipfile.ZipFile(p).namelist()[0])) if path.endswith(".zip") else (lambda p: open(p, "rb"))
    with opener(path) as f:
        r = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        cols = {c.lower(): c for c in r.fieldnames}
        pcc = next(cols[c] for c in cols if c in ("postcode", "pcds", "pcd"))
        latc = next(cols[c] for c in cols if c in ("lat", "latitude", "y"))
        lonc = next(cols[c] for c in cols if c in ("lon", "lng", "long", "longitude", "x"))
        for row in r:
            try:
                yield row[pcc], float(row[lonc]), float(row[latc])
            except ValueError:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--format", choices=["codepoint", "onspd", "csv"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--include-ni", action="store_true")
    ap.add_argument("--areas", help="Comma-separated postcode areas to keep (for quick sample builds)")
    a = ap.parse_args()

    keep = set(a.areas.upper().split(",")) if a.areas else None
    src = {"codepoint": lambda: iter_codepoint(a.input),
           "onspd": lambda: iter_onspd(a.input, a.include_ni),
           "csv": lambda: iter_csv(a.input)}[a.format]()

    stats = Counter()
    seen = set()
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["postcode", "area", "district", "sector", "lon", "lat"])
        for raw, lon, lat in src:
            stats["read"] += 1
            p = normalise(raw)
            if p is None:
                stats["unparseable"] += 1
                continue
            pc, area, district, sector = p
            if keep and area not in keep:
                continue
            if pc in seen:
                stats["duplicate"] += 1
                continue
            if not (-9 < lon < 3 and 49 < lat < 61.5):
                stats["out_of_range"] += 1
                continue
            seen.add(pc)
            w.writerow([pc, area, district, sector, f"{lon:.6f}", f"{lat:.6f}"])
            stats["written"] += 1
    print("build_points:", dict(stats), file=sys.stderr)


if __name__ == "__main__":
    main()
