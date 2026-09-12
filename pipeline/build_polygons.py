#!/usr/bin/env python3
"""Derive a country's postcode polygons from its unit points.

    python pipeline/build_polygons.py <cc> <raw_dir> units.csv --out <dir> [--report r.json] [--mask-cache c.pkl]

Method (all geometry in the country's working projection, output in WGS84):
  1. Voronoi diagram of every distinct point location (scipy / Qhull),
     bounded by far-away sentinel points so every cell is finite.
  2. Cells dissolved into the finest polygon level, then each level into the
     next coarser one, with GEOS coverage unions (the cells form an exact
     coverage).
  3. Each level clipped to a land mask: the country module's mask when
     available (coastline / national boundary), otherwise a dilated 1 km
     occupancy grid of the points. Points outside the mask get a small
     buffer added so no code disappears.
  4. Boundary lines between polygons (never the coast), label points and
     WGS84 bounding boxes are written alongside the polygons.

Outputs, per polygon level `<id>`: <out>/<id>.geojsonl, <id>_lines.geojsonl,
<id>_labels.geojsonl.
"""
import argparse
import csv
import json
import os
import pickle
import sys
import time
from collections import defaultdict

import numpy as np
import shapely
from pyproj import Transformer
from scipy.ndimage import binary_dilation
from scipy.spatial import Voronoi
from shapely import STRtree

sys.path.insert(0, os.path.dirname(__file__))
import countries  # noqa: E402

T0 = time.time()
MIN_HOLE_M2 = 4e6  # inland water bodies smaller than this are filled


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------
# projection: a local transverse Mercator centred on the data, in metres
# ----------------------------------------------------------------------------
class Proj:
    def __init__(self, lon, lat):
        lon0, lat0 = float(np.median(lon)), float(np.median(lat))
        crs = f"+proj=tmerc +lat_0={lat0:.4f} +lon_0={lon0:.4f} +k=0.9996 +x_0=500000 +y_0=0 +ellps=WGS84 +units=m +no_defs"
        self.fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self.inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    def to_local(self, geom):
        return shapely.transform(geom, lambda c: np.column_stack(self.fwd.transform(c[:, 0], c[:, 1])))

    def to_wgs(self, geom):
        return shapely.transform(geom, lambda c: np.round(np.column_stack(self.inv.transform(c[:, 0], c[:, 1])), 6))


# ----------------------------------------------------------------------------
# 1. load points
# ----------------------------------------------------------------------------
def load_units(path, level_ids):
    codes = {l: [] for l in level_ids}
    lon, lat = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            for l in level_ids:
                codes[l].append(row[l])
            lon.append(float(row["lon"]))
            lat.append(float(row["lat"]))
    return {l: np.array(v, dtype=object) for l, v in codes.items()}, np.array(lon), np.array(lat)


# ----------------------------------------------------------------------------
# 2. voronoi
# ----------------------------------------------------------------------------
def voronoi_cells(xy):
    uxy, inverse = np.unique(np.round(xy, 1), axis=0, return_inverse=True)
    inverse = inverse.ravel()
    n = len(uxy)
    log(f"voronoi: {len(xy)} points, {n} distinct locations")
    minx, miny = uxy.min(axis=0)
    maxx, maxy = uxy.max(axis=0)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    r = max(maxx - minx, maxy - miny) * 4 + 1e5
    ang = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    sentinels = np.column_stack([cx + r * np.cos(ang), cy + r * np.sin(ang)])
    vor = Voronoi(np.vstack([uxy, sentinels]))
    log("voronoi: qhull done, assembling polygons")
    verts = vor.vertices
    coords, ring_off, poly_off, bad = [], [0], [0], 0
    for i in range(n):
        reg = vor.regions[vor.point_region[i]]
        if not reg or -1 in reg or len(reg) < 3:
            bad += 1
            px, py = uxy[i]
            ring = np.array([[px - 1, py - 1], [px + 1, py - 1], [px + 1, py + 1], [px - 1, py + 1], [px - 1, py - 1]])
        else:
            ring = verts[reg + [reg[0]]]
        coords.append(ring)
        ring_off.append(ring_off[-1] + len(ring))
        poly_off.append(i + 1)
    if bad:
        log(f"voronoi: {bad} degenerate regions replaced by 2 m squares")
    cells = shapely.from_ragged_array(shapely.GeometryType.POLYGON, np.vstack(coords), (np.array(ring_off), np.array(poly_off)))
    if not shapely.is_valid(cells).all():
        cells = shapely.make_valid(cells)
    log("voronoi: polygons built")
    return uxy, inverse, cells


def dissolve(geoms, keys):
    groups = defaultdict(list)
    for g, k in zip(geoms, keys):
        groups[k].append(g)
    out, fallbacks = {}, 0
    for k, gs in groups.items():
        if len(gs) == 1:
            out[k] = gs[0]
            continue
        try:
            out[k] = shapely.coverage_union_all(gs)
        except Exception:
            out[k] = shapely.union_all(gs)
            fallbacks += 1
    if fallbacks:
        log(f"dissolve: {fallbacks} groups needed a slow (non-coverage) union")
    return out


# ----------------------------------------------------------------------------
# 3. mask
# ----------------------------------------------------------------------------
def fill_water(g):
    parts = []
    for p in shapely.get_parts(g):
        if p.geom_type != "Polygon":
            continue
        holes = [h for h in p.interiors if shapely.Polygon(h).area >= MIN_HOLE_M2]
        parts.append(shapely.Polygon(p.exterior, holes))
    return shapely.make_valid(shapely.union_all(parts))


def load_mask(path, proj, xy, cache=None):
    """Union of the mask features that contain at least one point (features
    with no points, e.g. Northern Ireland for Code-Point Open, are dropped).
    Prepared features are cached until the file or parameters change."""
    key = f"{os.path.getmtime(path)}:{os.path.getsize(path)}:v3:{MIN_HOLE_M2}"
    prepared = None
    if cache and os.path.exists(cache):
        with open(cache, "rb") as f:
            blob = pickle.load(f)
        if blob.get("key") == key:
            prepared = blob["features"]
            log("mask: using cached prepared mask")
    if prepared is None:
        with open(path) as f:
            gj = json.load(f)
        feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
        prepared = []
        for ft in feats:
            if not ft.get("geometry"):
                continue
            name = next((v for k, v in ft.get("properties", {}).items() if k.upper().endswith("NM") or k.upper() == "NAME"), "?")
            g = shapely.make_valid(shapely.from_geojson(json.dumps(ft["geometry"])))
            g = fill_water(shapely.make_valid(proj.to_local(g)))
            prepared.append((name, shapely.to_wkb(g)))
            log(f"mask: prepared {name}")
        if cache:
            with open(cache, "wb") as f:
                pickle.dump({"key": key, "features": prepared}, f)
    pts = shapely.points(xy[:: max(1, len(xy) // 200000)])
    keep, dropped = [], []
    for name, wkb in prepared:
        g = shapely.from_wkb(wkb)
        if shapely.intersects(g, pts).any():
            keep.append(g)
        else:
            dropped.append(name)
    if dropped:
        log(f"mask: dropping features with no points: {', '.join(dropped)}")
    if not keep:
        sys.exit("mask: no feature contains any point; wrong file or projection?")
    return shapely.make_valid(shapely.union_all(keep))


def grid_mask(xy, cell=1000.0, dilate=2):
    minx, miny = xy.min(axis=0) - cell * (dilate + 2)
    ix = ((xy[:, 0] - minx) // cell).astype(int)
    iy = ((xy[:, 1] - miny) // cell).astype(int)
    grid = np.zeros((ix.max() + dilate + 3, iy.max() + dilate + 3), dtype=bool)
    grid[ix, iy] = True
    grid = binary_dilation(grid, iterations=dilate)
    gx, gy = np.nonzero(grid)
    x0, y0 = minx + gx * cell, miny + gy * cell
    return shapely.coverage_union_all(shapely.box(x0, y0, x0 + cell, y0 + cell))


def subdivide(mask, size=25000.0):
    parts = shapely.get_parts(mask)
    tree = STRtree(parts)
    minx, miny, maxx, maxy = mask.bounds
    pieces = []
    for x in np.arange(np.floor(minx / size) * size, maxx, size):
        for y in np.arange(np.floor(miny / size) * size, maxy, size):
            cell = shapely.box(x, y, x + size, y + size)
            hits = tree.query(cell, predicate="intersects")
            if len(hits) == 0:
                continue
            p = shapely.intersection(shapely.union_all(parts[hits]), cell)
            if not p.is_empty:
                pieces.extend(shapely.get_parts(p))
    return np.array(pieces)


class Clipper:
    def __init__(self, pieces):
        self.pieces = pieces
        self.tree = STRtree(pieces)

    def clip(self, geom):
        hits = self.tree.query(geom, predicate="intersects")
        if len(hits) == 0:
            return None
        inter = [g for g in shapely.intersection(self.pieces[hits], geom) if not g.is_empty]
        if not inter:
            return None
        out = shapely.union_all(inter) if len(inter) > 1 else inter[0]
        polys = [g for g in shapely.get_parts(out) if g.geom_type == "Polygon" and g.area > 1]
        if not polys:
            return None
        return shapely.multipolygons(polys) if len(polys) > 1 else polys[0]


# ----------------------------------------------------------------------------
# 4. interior boundary lines
# ----------------------------------------------------------------------------
def interior_lines(polys, clipper):
    segs = []
    for g in polys.values():
        for ring in shapely.get_rings(shapely.get_parts(g)):
            c = shapely.get_coordinates(ring)
            segs.append(np.hstack([c[:-1], c[1:]]))
    segs = np.vstack(segs)
    flip = (segs[:, 0] > segs[:, 2]) | ((segs[:, 0] == segs[:, 2]) & (segs[:, 1] > segs[:, 3]))
    segs[flip] = segs[flip][:, [2, 3, 0, 1]]
    segs, counts = np.unique(np.round(segs, 3), axis=0, return_counts=True)
    shared = segs[counts > 1]
    if len(shared) == 0:
        return []
    lines = shapely.linestrings(shared.reshape(-1, 2, 2))
    li, pi = clipper.tree.query(lines, predicate="intersects")
    clipped = shapely.intersection(lines[li], clipper.pieces[pi])
    clipped = clipped[~shapely.is_empty(clipped)]
    parts = [g for g in shapely.get_parts(clipped) if g.geom_type == "LineString"]
    merged = shapely.line_merge(shapely.multilinestrings(parts)) if parts else shapely.MultiLineString()
    return [g for g in shapely.get_parts(merged) if g.length > 0]


# ----------------------------------------------------------------------------
# 5. output
# ----------------------------------------------------------------------------
def label_point(geom):
    parts = shapely.get_parts(geom)
    big = parts[np.argmax(shapely.area(parts))]
    tol = max(np.sqrt(big.area) / 100, 1.0)
    try:
        return shapely.get_point(shapely.maximum_inscribed_circle(big, tol), 0)
    except Exception:
        return big.representative_point()


def write_level(out_dir, level_id, polys, proj, counts, parent_of, names):
    n = 0
    with open(os.path.join(out_dir, f"{level_id}.geojsonl"), "w") as fp, open(os.path.join(out_dir, f"{level_id}_labels.geojsonl"), "w") as fl:
        for code in sorted(polys):
            g = polys[code]
            if g is None or g.is_empty:
                continue
            gw, lw = proj.to_wgs(g), proj.to_wgs(label_point(g))
            minx, miny, maxx, maxy = gw.bounds
            props = {"code": code, "level": level_id, "units": counts[code], "km2": round(g.area / 1e6, 3),
                     "minx": round(minx, 5), "miny": round(miny, 5), "maxx": round(maxx, 5), "maxy": round(maxy, 5)}
            if parent_of is not None:
                props["parent"] = parent_of[code]
            if names and code in names:
                props["name"] = names[code]
            fp.write(json.dumps({"type": "Feature", "properties": props, "geometry": json.loads(shapely.to_geojson(gw))}, separators=(",", ":")) + "\n")
            fl.write(json.dumps({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [lw.x, lw.y]}}, separators=(",", ":")) + "\n")
            n += 1
    log(f"wrote {n} {level_id} polygons")


def write_lines(out_dir, level_id, lines, proj):
    with open(os.path.join(out_dir, f"{level_id}_lines.geojsonl"), "w") as fp:
        for g in lines:
            fp.write(json.dumps({"type": "Feature", "properties": {"level": level_id}, "geometry": json.loads(shapely.to_geojson(proj.to_wgs(g)))}, separators=(",", ":")) + "\n")
    log(f"wrote {len(lines)} {level_id} boundary lines")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("country")
    ap.add_argument("raw_dir")
    ap.add_argument("units")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--mask-cache")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    mod = countries.get(a.country)
    level_ids = [l["id"] for l in mod.LEVELS]  # coarse -> fine
    finest = level_ids[-1]

    codes, lon, lat = load_units(a.units, level_ids)
    n = len(lon)
    log(f"loaded {n} points")
    proj = Proj(lon, lat)
    x, y = proj.fwd.transform(lon, lat)
    xy = np.column_stack([x, y])
    uxy, inverse, cells = voronoi_cells(xy)

    # cell -> finest code: the code with most points at that location wins
    votes = defaultdict(lambda: defaultdict(int))
    fine = codes[finest]
    for i in range(n):
        votes[inverse[i]][fine[i]] += 1
    cell_code = np.empty(len(uxy), dtype=object)
    for ci, v in votes.items():
        cell_code[ci] = max(v.items(), key=lambda kv: (kv[1], kv[0]))[0]
    no_territory = sorted(set(fine) - set(cell_code))
    if no_territory:
        log(f"{len(no_territory)} {finest} codes have no location of their own (all points shared with another code); no polygon")

    # parents and counts per level
    parent = {}  # level_id -> {code: parent code}
    counts = {l: defaultdict(int) for l in level_ids}
    for i in range(n):
        for j, l in enumerate(level_ids):
            counts[l][codes[l][i]] += 1
            if j > 0:
                parent.setdefault(l, {})[codes[l][i]] = codes[level_ids[j - 1]][i]

    polys = {finest: dissolve(cells, cell_code)}
    log(f"{len(polys[finest])} {finest}")
    for j in range(len(level_ids) - 2, -1, -1):
        child, lvl = level_ids[j + 1], level_ids[j]
        polys[lvl] = dissolve(list(polys[child].values()), [parent[child][c] for c in polys[child]])
        log(f"{len(polys[lvl])} {lvl}")

    mask_path = mod.mask(a.raw_dir) if hasattr(mod, "mask") else None
    if mask_path:
        log(f"mask: {mask_path}")
        mask = load_mask(mask_path, proj, uxy, a.mask_cache)
        mask_source = "country"
    else:
        log("no mask from the country module: building occupancy-grid mask (derived, blocky edges)")
        mask, mask_source = grid_mask(uxy), "grid"
    pieces = subdivide(mask)
    tree = STRtree(pieces)
    hit, _ = tree.query(shapely.points(uxy), predicate="intersects")
    outside = np.setdiff1d(np.arange(len(uxy)), hit)
    if len(outside):
        log(f"{len(outside)} point locations fall outside the mask; adding 250 m buffers")
        pieces = np.concatenate([pieces, shapely.buffer(shapely.points(uxy[outside]), 250, quad_segs=4)])
    clipper = Clipper(pieces)
    log(f"mask ready ({len(pieces)} pieces)")

    names = mod.names(a.raw_dir) if hasattr(mod, "names") else {}
    lost = {}
    for lvl in reversed(level_ids):
        write_lines(a.out, lvl, interior_lines(polys[lvl], clipper), proj)
        clipped = {k: clipper.clip(g) for k, g in polys[lvl].items()}
        lost[lvl] = [k for k, g in clipped.items() if g is None]
        log(f"clipped {lvl} ({len(lost[lvl])} lost)")
        write_level(a.out, lvl, clipped, proj, counts[lvl], parent.get(lvl), names if lvl == finest else None)

    if a.report:
        with open(a.report, "w") as f:
            json.dump({"country": a.country, "points": n, "distinct_locations": int(len(uxy)),
                       "polygons": {l: len(polys[l]) for l in level_ids}, "mask": mask_source,
                       "points_outside_mask": int(len(outside)), "lost": lost,
                       "codes_without_territory": no_territory, "seconds": round(time.time() - T0, 1)}, f, indent=1)
    log("done")


if __name__ == "__main__":
    main()
