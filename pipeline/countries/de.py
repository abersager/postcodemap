"""Germany: postcode (PLZ) polygons from OpenStreetMap. Deutsche Post owns the
PLZ system and sells its boundaries; the only open set is the community-drawn
`boundary=postal_code` relations in OpenStreetMap, taken here from the
yetzt/postleitzahlen release (an Overpass extract, one feature per PLZ).

The data is ODbL (share-alike), unlike every other country's. It stays a
separate archive and search index, so the rest of the site remains under its
own licences; the German tileset and index are themselves ODbL. The polygons
already stop at the coast and border, so no land mask is needed. There are
no open address points, so counts are postcodes and the app applies no
density shift for Germany. Place names come from GeoNames (CC BY 4.0)."""
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

CODE = "de"
NAME = "Germany"
LEVELS = [
    {"id": "zone", "name": "Zones (1 digit)", "threshold": 0},
    {"id": "region", "name": "Regions (2 digits)", "threshold": 6},
    {"id": "area", "name": "Areas (3 digits)", "threshold": 8},
    {"id": "plz", "name": "Postcodes", "threshold": 10},
]
POINT_LEVEL = None          # the PLZ polygon is the finest level
SHARD_LEVEL = None
POINT_NOUN = "postcodes"    # read_units yields one point per PLZ
DENSITY_LEVEL = False       # no address data: no density readout or zoom shift
ATTRIBUTION = ("Postleitzahlgebiete: &copy; OpenStreetMap contributors (ODbL) &middot; "
               "Place names: GeoNames (CC BY 4.0)")
LICENCE = ("ODbL 1.0 (postcode boundaries from OpenStreetMap via yetzt/postleitzahlen; "
           "this country's tiles and index are a derivative database under ODbL); place names GeoNames CC BY 4.0")

RELEASE = "2026.02"         # https://github.com/yetzt/postleitzahlen/releases
POLYGONS_URL = f"https://github.com/yetzt/postleitzahlen/releases/download/{RELEASE}/postleitzahlen.geojson.br"
GEONAMES_URL = "https://download.geonames.org/export/zip/DE.zip"
FILES = ((POLYGONS_URL, "postleitzahlen.geojson.br"), (GEONAMES_URL, "geonames-de.zip"))


def parse(raw):
    s = raw.strip()
    if len(s) != 5 or not s.isdigit():
        return None
    return {"code": s, "zone": s[0], "region": s[:2], "area": s[:3], "plz": s}


def download(raw_dir):
    for url, name in FILES:
        path = os.path.join(raw_dir, name)
        if os.path.exists(path):
            continue
        print(f"de: downloading {url}", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 postcodemap-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".part", path)


def _features(raw_dir):
    """Streams the features of the (500 MB decoded) GeoJSON one at a time
    instead of materialising the whole document."""
    import brotli
    with open(os.path.join(raw_dir, "postleitzahlen.geojson.br"), "rb") as f:
        text = brotli.decompress(f.read()).decode("utf-8")
    dec = json.JSONDecoder()
    i = text.index("[", text.index('"features"')) + 1
    while True:
        while text[i] in " \t\r\n,":
            i += 1
        if text[i] == "]":
            return
        ft, i = dec.raw_decode(text, i)
        yield ft


def _rings(geometry):
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for poly in polys:
        yield poly[0]


def read_units(raw_dir):
    """One point per PLZ: the centre of its polygon's envelope (used for
    sample selection, counts and the level hierarchy)."""
    for ft in _features(raw_dir):
        xs, ys = [], []
        for ring in _rings(ft["geometry"]):
            xs.extend(p[0] for p in ring)
            ys.extend(p[1] for p in ring)
        if xs:
            yield ft["properties"]["postcode"], (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def read_polygons(raw_dir):
    """Yields (PLZ, shapely (Multi)Polygon in WGS84); a PLZ mapped as several
    relations yields several features, which build_polygons unions."""
    import shapely
    for ft in _features(raw_dir):
        yield ft["properties"]["postcode"], shapely.from_geojson(json.dumps(ft["geometry"]))


def names(raw_dir):
    """PLZ -> place name from GeoNames (tab-separated: country, postcode,
    place, ...). Rural postcodes list every village and cities list their
    quarters ("Dresden", "Dresden Innere Altstadt"); the shortest name is
    kept, which is the town or the main village."""
    out = {}
    with zipfile.ZipFile(os.path.join(raw_dir, "geonames-de.zip")) as z, z.open("DE.txt") as f:
        for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t"):
            if len(row) > 2 and parse(row[1]) and row[2] and (row[1] not in out or len(row[2]) < len(out[row[1]])):
                out[row[1]] = row[2]
    return {"plz": out}
