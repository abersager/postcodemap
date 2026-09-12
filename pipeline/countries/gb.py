"""Great Britain: OS Code-Point Open unit postcodes (optionally ONSPD or a CSV)."""
import csv
import io
import os
import re
import sys
import urllib.request
import zipfile

CODE = "gb"
NAME = "Great Britain"
LEVELS = [
    {"id": "area", "name": "Areas", "threshold": 0},
    {"id": "district", "name": "Districts", "threshold": 8},
    {"id": "sector", "name": "Sectors", "threshold": 11},
]
POINT_LEVEL = {"id": "unit", "name": "Units", "threshold": 13, "noun": "postcodes"}
SHARD_LEVEL = "district"
ATTRIBUTION = (
    "Contains OS data &copy; Crown copyright and database right 2026 &middot; "
    "Contains Royal Mail data &copy; Royal Mail copyright and database right 2026 &middot; "
    "Contains ONS data &copy; Crown copyright and database right 2026, "
    '<a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">OGL v3</a>'
)
LICENCE = "Open Government Licence v3 (OS Code-Point Open, ONS boundaries)"
CODEPOINT_URL = "https://api.os.uk/downloads/v1/products/CodePointOpen/downloads?area=GB&format=CSV&redirect"

_UNIT_RE = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?)([0-9][A-Z]{2})$")


def parse(raw):
    s = raw.upper().replace(" ", "").strip()
    m = _UNIT_RE.match(s)
    if not m:
        return None
    outward, inward = m.group(1), m.group(2)
    i = 0
    while i < len(outward) and outward[i].isalpha():
        i += 1
    return {"code": f"{outward} {inward}", "area": outward[:i], "district": outward, "sector": f"{outward} {inward[0]}"}


# --- downloads ---------------------------------------------------------------
def download(raw_dir):
    """Code-Point Open (unless SOURCE=onspd/csv points at a file) and the ONS coastline."""
    source = os.environ.get("SOURCE") or "codepoint"
    if source == "codepoint":
        _fetch(CODEPOINT_URL, os.path.join(raw_dir, "codepo_gb.zip"))
    coast = os.path.join(raw_dir, "coastline.geojson")
    if not os.path.exists(coast):
        try:
            from fetch_coastline import fetch
            fetch(coast, os.environ.get("COASTLINE_URL") or None)
        except Exception as e:  # the polygon step falls back to a point-derived mask
            print(f"gb: coastline unavailable ({e}); a point-derived mask will be used", file=sys.stderr)


def _fetch(url, path):
    if os.path.exists(path):
        return
    print(f"gb: downloading {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "postcodemap-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(path + ".part", path)


def mask(raw_dir):
    p = os.path.join(raw_dir, "coastline.geojson")
    return p if os.path.exists(p) and os.path.getsize(p) > 0 else None


# --- readers -----------------------------------------------------------------
def read_units(raw_dir):
    source = os.environ.get("SOURCE") or "codepoint"
    if source == "codepoint":
        yield from _iter_codepoint(os.path.join(raw_dir, "codepo_gb.zip"))
    elif source == "onspd":
        yield from _iter_onspd(os.environ.get("ONSPD_ZIP") or os.path.join(raw_dir, "onspd.zip"), os.environ.get("INCLUDE_NI") == "1")
    elif source == "csv":
        yield from _iter_csv(os.environ["CSV_FILE"])
    else:
        sys.exit(f"gb: unknown SOURCE={source}")


def _iter_codepoint(path):
    import numpy as np
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.lower().endswith(".csv") and "data/csv/" in n.lower())
        if not names:
            sys.exit("gb: no Data/CSV/*.csv files found in Code-Point Open zip")
        for name in names:
            rows, es, ns = [], [], []
            with z.open(name) as f:
                for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if len(row) < 4 or row[1] == "90" or not row[2] or not row[3]:
                        continue  # positional quality 90 = no coordinates
                    rows.append(row[0]); es.append(float(row[2])); ns.append(float(row[3]))
            if rows:
                lon, lat = tr.transform(np.array(es), np.array(ns))
                for pc, lo, la in zip(rows, lon, lat):
                    yield pc, float(lo), float(la)


def _iter_onspd(path, include_ni):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv") and "/data/" in n.lower()
                 and "multi_csv" not in n.lower() and n.split("/")[-1].upper().startswith("ONSPD_")]
        if not names:
            sys.exit("gb: no Data/ONSPD_*.csv found in ONSPD zip")
        with z.open(sorted(names, key=len)[0]) as f:
            for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")):
                if row.get("doterm"):
                    continue
                pc = row["pcds"]
                if not include_ni and pc.startswith("BT"):
                    continue
                try:
                    lat, lon = float(row["lat"]), float(row["long"])
                except (ValueError, KeyError):
                    continue
                if lat > 90 or lat == 0:
                    continue
                yield pc, lon, lat


def _iter_csv(path):
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
