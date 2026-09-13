"""Netherlands: official PC6 polygons from Statistics Netherlands (CBS), whose
"Kerncijfers per postcode" GeoPackage carries the geometry of every PC6 area as
Esri Nederland derives it from BAG addresses. Coarser levels (PC5, PC4, PC2)
are dissolved from the PC6 polygons. Place names for PC4 come from GeoNames."""
import csv
import io
import os
import struct
import sys
import urllib.request
import zipfile

import numpy as np

CODE = "nl"
NAME = "Netherlands"
LEVELS = [
    {"id": "pc2", "name": "Regions (2 digits)", "threshold": 0},
    {"id": "pc4", "name": "Districts (PC4)", "threshold": 8},
    {"id": "pc5", "name": "Sectors (PC5)", "threshold": 11},
    {"id": "pc6", "name": "Postcodes (PC6)", "threshold": 13},
]
POINT_LEVEL = None          # the PC6 polygon is the finest level; nothing is drawn as points
SHARD_LEVEL = "pc4"         # PC5 and PC6 codes are searched from units.bin, one slice per PC4
SHARDED_LEVELS = ["pc5", "pc6"]
DENSITY_LEVEL = "pc4"       # the density readout counts PC6 codes per km² of the PC4 area
POINT_NOUN = "postcodes"
ATTRIBUTION = ("Postcodegebieden: &copy; CBS / Esri Nederland (CC BY 4.0) &middot; "
               "Place names: GeoNames (CC BY 4.0)")
LICENCE = "CC BY 4.0 (CBS 'Kerncijfers per postcode' PC6 geometry by Esri Nederland; GeoNames place names)"

PC6_URL = "https://download.cbs.nl/postcode/2026-cbs_pc6_2025_v1.zip"
GEONAMES_URL = "https://download.geonames.org/export/zip/NL.zip"
TABLE = "cbs_pc6_2025"


def parse(raw):
    s = raw.replace(" ", "").upper()
    if len(s) != 6 or not (s[:4].isdigit() and s[0] != "0" and s[4:].isalpha()):
        return None
    return {"code": s, "pc2": s[:2], "pc4": s[:4], "pc5": s[:5], "pc6": s}


def download(raw_dir):
    for url, name in ((PC6_URL, "pc6.zip"), (GEONAMES_URL, "geonames-nl.zip")):
        path = os.path.join(raw_dir, name)
        if os.path.exists(path):
            continue
        print(f"nl: downloading {url}", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 postcodemap-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".part", path)
    gpkg = _gpkg(raw_dir)
    if not os.path.exists(gpkg):
        print("nl: extracting the GeoPackage", file=sys.stderr)
        with zipfile.ZipFile(os.path.join(raw_dir, "pc6.zip")) as z:
            z.extract(f"{TABLE}_v1.gpkg", raw_dir)


def _gpkg(raw_dir):
    return os.path.join(raw_dir, f"{TABLE}_v1.gpkg")


def _transformer():
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)  # RD New -> WGS84


# GeoPackage geometry blob: 'GP', version, flags, srs_id (4), optional envelope, then WKB.
_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def _split_blob(blob):
    flags = blob[3]
    env = (flags >> 1) & 7
    little = flags & 1
    return env, little, 8 + _ENVELOPE_BYTES[env]


def read_units(raw_dir):
    """One point per PC6: the centre of its polygon's envelope (from the blob
    header, no geometry parsing). Used for sample selection, counts and parents."""
    import sqlite3
    tr = _transformer()
    con = sqlite3.connect(_gpkg(raw_dir))
    codes, xs, ys = [], [], []
    for pc, blob in con.execute(f"select postcode6, geom from {TABLE}"):
        env, little, off = _split_blob(blob)
        if env == 0:
            continue
        minx, maxx, miny, maxy = struct.unpack(("<" if little else ">") + "4d", blob[8:40])
        codes.append(pc); xs.append((minx + maxx) / 2); ys.append((miny + maxy) / 2)
    lon, lat = tr.transform(np.array(xs), np.array(ys))
    for pc, lo, la in zip(codes, lon, lat):
        yield pc, float(lo), float(la)


def read_polygons(raw_dir, batch=20000):
    """Yields (raw PC6, shapely (Multi)Polygon in WGS84) for every PC6 area."""
    import shapely
    import sqlite3
    tr = _transformer()
    con = sqlite3.connect(_gpkg(raw_dir))
    codes, blobs = [], []

    def flush():
        geoms = shapely.from_wkb([b[_split_blob(b)[2]:] for b in blobs])
        geoms = shapely.transform(geoms, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))
        yield from zip(codes, geoms)
        codes.clear(); blobs.clear()

    for pc, blob in con.execute(f"select postcode6, geom from {TABLE}"):
        codes.append(pc); blobs.append(blob)
        if len(codes) >= batch:
            yield from flush()
    yield from flush()


def names(raw_dir):
    """PC4 -> place name from GeoNames (tab-separated: country, postcode, place, ...)."""
    out = {}
    with zipfile.ZipFile(os.path.join(raw_dir, "geonames-nl.zip")) as z, z.open("NL.txt") as f:
        for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t"):
            if len(row) > 2 and row[1].isdigit() and len(row[1]) == 4:
                out.setdefault(row[1], row[2])
    return {"pc4": out}
