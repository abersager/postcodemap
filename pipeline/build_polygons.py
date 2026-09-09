#!/usr/bin/env python3
"""Derive sector, district and area polygons from unit postcode centroids.

Method (all geometry in EPSG:27700 metres, output in WGS84):
  1. Voronoi diagram of every distinct unit centroid (scipy / Qhull), bounded
     by far-away sentinel points so every real cell is finite.
  2. Cells dissolved into sectors, sectors into districts, districts into
     areas with GEOS coverage unions (the cells form an exact coverage).
  3. Each level clipped to a land mask: the ONS country boundaries when
     --coastline is given, otherwise a dilated 1 km occupancy grid of the
     points themselves. Points that fall outside the mask (piers, generalised
     coast) get a small buffer added to the mask so no postcode disappears.
  4. Label points (pole of inaccessibility of the largest part) and WGS84
     bounding boxes are written as properties.

Outputs newline-delimited GeoJSON: <out>/{areas,districts,sectors}.geojsonl
and <out>/{areas,districts,sectors}_labels.geojsonl.
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
import shapely
from pyproj import Transformer
from scipy.ndimage import binary_dilation
from scipy.spatial import Voronoi
from shapely import STRtree

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", file=sys.stderr, flush=True)


TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def to_wgs(geom):
    return shapely.transform(geom, lambda c: np.round(np.column_stack(TO_WGS.transform(c[:, 0], c[:, 1])), 6))


# ----------------------------------------------------------------------------
# 1. load points
# ----------------------------------------------------------------------------
def load_units(path):
    pcs, sectors, lon, lat = [], [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            pcs.append(row["postcode"])
            sectors.append(row["sector"])
            lon.append(float(row["lon"]))
            lat.append(float(row["lat"]))
    x, y = TO_BNG.transform(np.array(lon), np.array(lat))
    return pcs, np.array(sectors), np.column_stack([x, y])


# ----------------------------------------------------------------------------
# 2. voronoi
# ----------------------------------------------------------------------------
def voronoi_cells(xy):
    """Return (unique_xy, inverse, cells) where cells[i] is the finite Voronoi
    polygon of unique point i."""
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
    coords, ring_off, poly_off = [], [0], [0]
    bad = 0
    for i in range(n):
        reg = vor.regions[vor.point_region[i]]
        if not reg or -1 in reg or len(reg) < 3:
            bad += 1
            reg = None
        if reg is None:  # tiny square around the point so it still exists
            px, py = uxy[i]
            ring = np.array([[px - 1, py - 1], [px + 1, py - 1], [px + 1, py + 1], [px - 1, py + 1], [px - 1, py - 1]])
        else:
            ring = verts[reg + [reg[0]]]
        coords.append(ring)
        ring_off.append(ring_off[-1] + len(ring))
        poly_off.append(i + 1)
    if bad:
        log(f"voronoi: {bad} degenerate regions replaced by 2 m squares")
    allc = np.vstack(coords)
    cells = shapely.from_ragged_array(shapely.GeometryType.POLYGON, allc, (np.array(ring_off), np.array(poly_off)))
    # Qhull orientation is not guaranteed; make rings CCW so unions behave.
    cells = shapely.make_valid(cells) if not shapely.is_valid(cells).all() else cells
    log("voronoi: polygons built")
    return uxy, inverse, cells


def dissolve(geoms, keys):
    """Union geometries sharing a key. Returns dict key -> geometry."""
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
def load_coastline(path):
    with open(path) as f:
        gj = json.load(f)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    geoms = [shapely.from_geojson(json.dumps(ft["geometry"])) for ft in feats if ft.get("geometry")]
    g = shapely.union_all([shapely.make_valid(x) for x in geoms])
    g = shapely.transform(g, lambda c: np.column_stack(TO_BNG.transform(c[:, 0], c[:, 1])))
    return shapely.make_valid(g)


def grid_mask(xy, cell=1000.0, dilate=2):
    minx, miny = xy.min(axis=0) - cell * (dilate + 2)
    ix = ((xy[:, 0] - minx) // cell).astype(int)
    iy = ((xy[:, 1] - miny) // cell).astype(int)
    grid = np.zeros((ix.max() + dilate + 3, iy.max() + dilate + 3), dtype=bool)
    grid[ix, iy] = True
    grid = binary_dilation(grid, iterations=dilate)
    gx, gy = np.nonzero(grid)
    x0 = minx + gx * cell
    y0 = miny + gy * cell
    squares = shapely.box(x0, y0, x0 + cell, y0 + cell)
    return shapely.coverage_union_all(squares)


def subdivide(mask, size=25000.0):
    """Cut the mask into grid pieces so clipping only touches nearby geometry."""
    parts = shapely.get_parts(mask)
    tree = STRtree(parts)
    minx, miny, maxx, maxy = mask.bounds
    xs = np.arange(np.floor(minx / size) * size, maxx, size)
    ys = np.arange(np.floor(miny / size) * size, maxy, size)
    pieces = []
    for x in xs:
        for y in ys:
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
        inter = shapely.intersection(self.pieces[hits], geom)
        inter = [g for g in inter if not g.is_empty]
        out = shapely.union_all(inter) if len(inter) > 1 else inter[0]
        # drop any stray lines/points from the intersection
        polys = [g for g in shapely.get_parts(out) if g.geom_type == "Polygon" and g.area > 1]
        if not polys:
            return None
        return shapely.multipolygons(polys) if len(polys) > 1 else polys[0]


# ----------------------------------------------------------------------------
# 4. output
# ----------------------------------------------------------------------------
def label_point(geom):
    parts = shapely.get_parts(geom)
    big = parts[np.argmax(shapely.area(parts))]
    tol = max(np.sqrt(big.area) / 100, 1.0)
    try:
        line = shapely.maximum_inscribed_circle(big, tol)
        return shapely.get_point(line, 0)
    except Exception:
        return big.representative_point()


def write_level(out_dir, level, polys, parent_of, counts, extra_props):
    poly_path = os.path.join(out_dir, f"{level}.geojsonl")
    lab_path = os.path.join(out_dir, f"{level}_labels.geojsonl")
    n = 0
    with open(poly_path, "w") as fp, open(lab_path, "w") as fl:
        for code in sorted(polys):
            g = polys[code]
            if g is None or g.is_empty:
                continue
            gw = to_wgs(g)
            lw = to_wgs(label_point(g))
            minx, miny, maxx, maxy = gw.bounds
            props = {"code": code, "level": level[:-1], "units": counts[code],
                     "minx": round(minx, 5), "miny": round(miny, 5), "maxx": round(maxx, 5), "maxy": round(maxy, 5)}
            props.update(extra_props(code))
            if parent_of:
                props["parent"] = parent_of(code)
            fp.write(json.dumps({"type": "Feature", "properties": props, "geometry": json.loads(shapely.to_geojson(gw))}, separators=(",", ":")) + "\n")
            fl.write(json.dumps({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [lw.x, lw.y]}}, separators=(",", ":")) + "\n")
            n += 1
    log(f"wrote {n} {level}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units")
    ap.add_argument("--out", required=True)
    ap.add_argument("--coastline", help="GeoJSON (WGS84) land polygons used as clip mask")
    ap.add_argument("--report", help="Write a JSON build report here")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    pcs, sectors, xy = load_units(a.units)
    log(f"loaded {len(pcs)} units")
    uxy, inverse, cells = voronoi_cells(xy)

    # cell -> sector. Several units can share one location (large buildings,
    # PO boxes); the sector with most units there claims the cell.
    votes = defaultdict(lambda: defaultdict(int))
    for i in range(len(pcs)):
        votes[inverse[i]][sectors[i]] += 1
    cell_sector = np.empty(len(uxy), dtype=object)
    for ci, v in votes.items():
        cell_sector[ci] = max(v.items(), key=lambda kv: (kv[1], kv[0]))[0]
    no_territory = sorted(set(sectors) - set(cell_sector))
    if no_territory:
        log(f"{len(no_territory)} sectors have no location of their own (all units share coordinates with another sector); no polygon for them")

    counts = defaultdict(int)
    for s in sectors:
        counts[s] += 1
        d = s.split(" ")[0]
        counts[d] += 1
        counts[area_of(d)] += 1

    log("dissolving sectors")
    sec = dissolve(cells, cell_sector)
    log(f"{len(sec)} sectors")
    dis = dissolve(list(sec.values()), [k.split(" ")[0] for k in sec])
    log(f"{len(dis)} districts")
    are = dissolve(list(dis.values()), [area_of(k) for k in dis])
    log(f"{len(are)} areas")

    # mask
    mask_source = "grid"
    if a.coastline:
        log("loading coastline")
        mask = load_coastline(a.coastline)
        mask_source = "coastline"
    else:
        log("no coastline given: building occupancy-grid mask (derived, blobby coast)")
        mask = grid_mask(uxy)
    pieces = subdivide(mask)
    tree = STRtree(pieces)
    inside = np.zeros(len(uxy), dtype=bool)
    hit_pts, _ = tree.query(shapely.points(uxy), predicate="intersects")
    inside[hit_pts] = True
    outside = np.nonzero(~inside)[0]
    if len(outside):
        log(f"{len(outside)} point locations fall outside the mask; adding 250 m buffers")
        pieces = np.concatenate([pieces, shapely.buffer(shapely.points(uxy[outside]), 250, quad_segs=4)])
    clipper = Clipper(pieces)
    log(f"mask ready ({len(pieces)} pieces)")

    def clip_all(d):
        out, lost = {}, []
        for k, g in d.items():
            c = clipper.clip(g)
            if c is None:
                lost.append(k)
            out[k] = c
        return out, lost

    sec_c, lost_s = clip_all(sec)
    log(f"clipped sectors ({len(lost_s)} lost)")
    dis_c, lost_d = clip_all(dis)
    log(f"clipped districts ({len(lost_d)} lost)")
    are_c, lost_a = clip_all(are)
    log(f"clipped areas ({len(lost_a)} lost)")

    write_level(a.out, "areas", are_c, None, counts, lambda c: {})
    write_level(a.out, "districts", dis_c, area_of, counts, lambda c: {"area": area_of(c)})
    write_level(a.out, "sectors", sec_c, lambda c: c.split(" ")[0], counts,
                lambda c: {"area": area_of(c.split(" ")[0]), "district": c.split(" ")[0]})

    if a.report:
        with open(a.report, "w") as f:
            json.dump({"units": len(pcs), "distinct_locations": int(len(uxy)), "sectors": len(sec), "districts": len(dis),
                       "areas": len(are), "mask": mask_source, "points_outside_mask": int(len(outside)),
                       "lost": {"sectors": lost_s, "districts": lost_d, "areas": lost_a},
                       "sectors_without_territory": no_territory,
                       "seconds": round(time.time() - T0, 1)}, f, indent=1)
    log("done")


def area_of(district):
    i = 0
    while i < len(district) and district[i].isalpha():
        i += 1
    return district[:i]


if __name__ == "__main__":
    main()
