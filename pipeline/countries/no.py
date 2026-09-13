"""Norway: official postcode polygons ("Postnummerområder", boundaries maintained
by Posten Norge, published by Kartverket on Geonorge). The polygons run out to
sea, so they are clipped to the land areas of Kartverket's N500 map data; unit
counts come from the Matrikkelen address register. All three are CC BY 4.0
and download without a login. Svalbard and Jan Mayen have postcodes but lie
outside the N500 extent, so their polygons stay unclipped."""
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

CODE = "no"
NAME = "Norway"
LEVELS = [
    {"id": "zone", "name": "Zones (1 digit)", "threshold": 0},
    {"id": "region", "name": "Regions (2 digits)", "threshold": 7},
    {"id": "postnr", "name": "Postcodes", "threshold": 10},
]
POINT_LEVEL = None          # addresses are not shown; the postcode polygon is the finest level
SHARD_LEVEL = None
POINT_NOUN = "addresses"    # what read_units yields and the density readout counts
ATTRIBUTION = ("Postnummerområder: &copy; Kartverket / Posten Norge (CC BY 4.0) &middot; "
               "Addresses (Matrikkelen) and coastline (N500): &copy; Kartverket (CC BY 4.0)")
LICENCE = "CC BY 4.0 (Kartverket: Postnummerområder with boundaries from Posten Norge, Matrikkelen addresses, N500 Kartdata land areas)"

GEONORGE = "https://nedlasting.geonorge.no/geonorge/Basisdata"
POLYGONS_URL = f"{GEONORGE}/Postnummeromrader/GeoJSON/Basisdata_0000_Norge_4258_Postnummeromrader_GeoJSON.zip"
ADDRESSES_URL = f"{GEONORGE}/MatrikkelenAdresse/CSV/Basisdata_0000_Norge_4258_MatrikkelenAdresse_CSV.zip"
N500_URL = f"{GEONORGE}/N500Kartdata/GML/Basisdata_0000_Norge_25833_N500Kartdata_GML.zip"
FILES = ((POLYGONS_URL, "postnummeromrader.zip"), (ADDRESSES_URL, "adresser.zip"), (N500_URL, "n500.zip"))


def parse(raw):
    s = raw.strip()
    if len(s) != 4 or not s.isdigit():
        return None
    return {"code": s, "zone": s[0], "region": s[:2], "postnr": s}


def download(raw_dir):
    for url, name in FILES:
        path = os.path.join(raw_dir, name)
        if os.path.exists(path):
            continue
        print(f"no: downloading {url}", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 postcodemap-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".part", path)


def _member(zpath, suffix):
    with zipfile.ZipFile(zpath) as z:
        return next(n for n in z.namelist() if n.endswith(suffix))


def read_units(raw_dir):
    """One point per address (road and cadastral addresses alike), with its
    postcode. Coordinates are ETRS89 geographic (EPSG:4258), treated as WGS84."""
    zpath = os.path.join(raw_dir, "adresser.zip")
    with zipfile.ZipFile(zpath) as z, z.open(_member(zpath, ".csv")) as f:
        r = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";")
        hdr = next(r)
        ip, ilat, ilon = hdr.index("postnummer"), hdr.index("Nord"), hdr.index("Øst")
        for row in r:
            if row[ip] and row[ilat] and row[ilon]:
                yield row[ip], float(row[ilon]), float(row[ilat])


def _features(raw_dir):
    zpath = os.path.join(raw_dir, "postnummeromrader.zip")
    with zipfile.ZipFile(zpath) as z, z.open(_member(zpath, ".geojson")) as f:
        data = json.load(f)
    # the file holds two collections: the areas and their boundary lines
    return data["postnummeromrader.postnummeromrade"]["features"]


def read_polygons(raw_dir):
    """Yields (postcode, shapely Polygon in WGS84); a few postcodes come as
    several features, which build_polygons unions."""
    import shapely
    for ft in _features(raw_dir):
        yield ft["properties"]["postnummer"], shapely.from_geojson(json.dumps(ft["geometry"]))


_SMALL = {"i", "og", "på", "ved", "av", "under", "over"}


def _title(s):
    words = s.lower().split()
    return " ".join(w if (i and w in _SMALL) else w[:1].upper() + w[1:] for i, w in enumerate(words))


def names(raw_dir):
    """Postcode -> place name ('poststed', upper case in the source)."""
    out = {}
    for ft in _features(raw_dir):
        p = ft["properties"]
        if p.get("poststed"):
            out.setdefault(p["postnummer"], _title(p["poststed"]))
    return {"postnr": out}


GML = "{http://www.opengis.net/gml/3.2}"
SEA = "Havflate"


def mask(raw_dir):
    """Land: every N500 land-cover area except the sea surface (lakes, rivers
    and glaciers count as land), unioned into one WGS84 GeoJSON feature. N500
    is EPSG:25833 and covers the mainland only."""
    out = os.path.join(raw_dir, "mask.geojson")
    if os.path.exists(out):
        return out
    import shapely
    from pyproj import Transformer

    zpath = os.path.join(raw_dir, "n500.zip")
    polys = []
    with zipfile.ZipFile(zpath) as z, z.open(_member(zpath, "N500Arealdekke_GML.gml")) as f:
        for _, el in ET.iterparse(f):
            if el.tag != GML + "featureMember":
                continue
            feat = el[0]
            if feat.tag.split("}")[1] != SEA:
                for surface in feat.iter(GML + "Surface"):
                    for patch in surface.iter(GML + "PolygonPatch"):
                        rings = [_ring(r) for r in patch.iter(GML + "LinearRing")]
                        if rings:
                            polys.append(shapely.Polygon(rings[0], rings[1:]))
            el.clear()
    print(f"no: mask from {len(polys)} N500 land-cover areas", file=sys.stderr)
    polys = shapely.make_valid(np.array(polys, dtype=object))
    try:
        land = shapely.coverage_union_all(polys)
        if not land.is_valid:
            raise ValueError("invalid coverage union")
    except Exception:
        land = shapely.union_all(polys)
    tr = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
    land = shapely.transform(land, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))
    with open(out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"NAME": "Norway"}, "geometry": json.loads(shapely.to_geojson(land))}]}, f)
    return out


def _ring(ring):
    pos = ring.find(GML + "posList")
    return np.array(pos.text.split(), dtype=float).reshape(-1, 2)
