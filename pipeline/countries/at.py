"""Austria: every address from BEV's Adressregister carries its PLZ, so PLZ
polygons are derived from 2.5 M address points. Names come from RTR's open
postcode list; the land mask is the union of Statistik Austria's municipalities."""
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

CODE = "at"
NAME = "Austria"
LEVELS = [
    {"id": "zone", "name": "Zones (1 digit)", "threshold": 0},
    {"id": "region", "name": "Regions (2 digits)", "threshold": 8},
    {"id": "plz", "name": "Postcodes", "threshold": 10},
]
POINT_LEVEL = None  # addresses are not shown; the PLZ polygon is the finest level
SHARD_LEVEL = None
POINT_NOUN = "addresses"  # what the density readout counts
ATTRIBUTION = (
    "&copy; Österreichisches Adressregister, data of the record date 01.04.2026 (BEV) &middot; "
    "Postleitzahlen: RTR-GmbH, CC BY 4.0 &middot; Datenquelle: Statistik Austria"
)
LICENCE = "CC BY 4.0 (BEV Adressregister; RTR postcode list; Statistik Austria municipalities)"

ADDRESSES_URL = "https://data.bev.gv.at/download/Adressregister/Adresse_Relationale_Tabellen_Stichtagsdaten.zip"
PLZ_LIST_URL = "https://data.rtr.at/api/v1/tables/plz.csv"
GEMEINDEN_URL = ("https://www.statistik.gv.at/gs-open/GEODATA/ows?service=WFS&version=1.0.0&request=GetFeature"
                 "&typeName=GEODATA:STATISTIK_AUSTRIA_GEM_20260101&outputFormat=SHAPE-ZIP&format_options=CHARSET:UTF-8")


def parse(raw):
    s = raw.strip()
    if len(s) != 4 or not s.isdigit():
        return None
    return {"code": s, "zone": s[0], "region": s[:2], "plz": s}


def download(raw_dir):
    for url, name in ((ADDRESSES_URL, "adressregister.zip"), (PLZ_LIST_URL, "plz.csv"), (GEMEINDEN_URL, "gemeinden.zip")):
        path = os.path.join(raw_dir, name)
        if os.path.exists(path):
            continue
        print(f"at: downloading {url}", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 postcodemap-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".part", path)


def read_units(raw_dir):
    """One point per address; the 'code' is its PLZ. Coordinates are Gauss-Krüger
    in one of three meridian strips (EPSG 31254/31255/31256), given per row."""
    import numpy as np
    from pyproj import Transformer

    trs = {e: Transformer.from_crs(f"EPSG:{e}", "EPSG:4326", always_xy=True) for e in ("31254", "31255", "31256")}
    with zipfile.ZipFile(os.path.join(raw_dir, "adressregister.zip")) as z, z.open("ADRESSE.csv") as f:
        r = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";")
        hdr = next(r)
        ip, irw, ihw, ie = hdr.index("PLZ"), hdr.index("RW"), hdr.index("HW"), hdr.index("EPSG")
        batch = {e: ([], [], []) for e in trs}
        for row in r:
            e = row[ie]
            if e not in batch or not row[irw] or not row[ihw]:
                continue
            b = batch[e]
            b[0].append(row[ip]); b[1].append(float(row[irw])); b[2].append(float(row[ihw]))
            if len(b[0]) >= 200000:
                yield from _flush(trs[e], b)
        for e, b in batch.items():
            yield from _flush(trs[e], b)


def _flush(tr, b):
    if not b[0]:
        return
    lon, lat = tr.transform(np.array(b[1]), np.array(b[2]))
    for pc, lo, la in zip(b[0], lon, lat):
        yield pc, float(lo), float(la)
    b[0].clear(); b[1].clear(); b[2].clear()


import numpy as np  # noqa: E402  (used in _flush)


def names(raw_dir):
    out = {}
    with open(os.path.join(raw_dir, "plz.csv"), encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("gueltigbis"):
                continue
            out.setdefault(row["plz"], row["ort"])
    return out


def mask(raw_dir):
    """Union of the municipalities (EPSG:31287) as one WGS84 GeoJSON feature."""
    out = os.path.join(raw_dir, "mask.geojson")
    if os.path.exists(out):
        return out
    import shapefile
    import shapely
    from pyproj import Transformer

    with zipfile.ZipFile(os.path.join(raw_dir, "gemeinden.zip")) as z:
        shp = next(n for n in z.namelist() if n.endswith(".shp"))
        base = shp[:-4]
        rdr = shapefile.Reader(shp=io.BytesIO(z.read(shp)), shx=io.BytesIO(z.read(base + ".shx")), dbf=io.BytesIO(z.read(base + ".dbf")))
        geoms = [shapely.from_geojson(json.dumps(s.__geo_interface__)) for s in rdr.shapes()]
    land = shapely.make_valid(shapely.union_all([shapely.make_valid(g) for g in geoms]))
    tr = Transformer.from_crs("EPSG:31287", "EPSG:4326", always_xy=True)
    land = shapely.transform(land, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))
    with open(out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"NAME": "Austria"}, "geometry": json.loads(shapely.to_geojson(land))}]}, f)
    return out
