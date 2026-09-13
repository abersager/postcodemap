"""Country modules.

Each module describes one country's postcode system and how to obtain its
open data. The generic pipeline scripts (download, build_points,
build_polygons, build_tiles, build_index) only talk to this interface:

    CODE          ISO 3166-1 alpha-2, lower case ("gb")
    NAME          display name
    LEVELS        list of polygon levels, coarse to fine:
                    {"id": "area", "name": "Areas", "threshold": 0}
                  `threshold` is the default zoom at which the app switches to
                  this level (the coarsest is always 0).
    POINT_LEVEL   {"id": "unit", "name": "Units", "threshold": 13, "noun": "postcodes"}
                  when the finest codes are rendered as points (GB unit
                  postcodes), else None. `noun` names what the points are, for
                  the density readout ("postcodes/km²", "addresses/km²").
    SHARD_LEVEL   level id used to shard the point search index (None if no points)
    POINT_NOUN    optional: what the points are, for the density readout; defaults
                  to POINT_LEVEL["noun"] or "points". "addresses" also tells
                  build_points that several points may share a code (no dedupe)
    ATTRIBUTION   HTML shown in the map's attribution control
    LICENCE       short licence statement for docs and meta.json
    download(raw_dir)            fetch source files (idempotent)
    read_units(raw_dir) -> iter  yields (raw_code, lon, lat) for every point
                                 (unit postcode or address); WGS84. For countries
                                 with official polygons: one representative point
                                 per finest code (used for sample selection, counts
                                 and the level hierarchy)
    parse(raw_code) -> dict      {"code": normalised finest code, <level id>: code, ...}
                                 or None if the code is not valid/geographic
    names(raw_dir) -> dict       optional: {<level id>: {code: place name}}
    mask(raw_dir) -> path|None   optional: GeoJSON (WGS84) land polygons; derived
                                 polygons are always clipped to it, official ones
                                 only when the module provides it (NO, whose
                                 polygons run out to sea; NL's already stop at the
                                 coast). Clipped polygons get `_lines` layers so
                                 the map never draws the coast

Countries with official polygons (NL, NO, DE) add:

    read_polygons(raw_dir) -> iter  yields (raw_code, shapely geometry in WGS84) for
                                    every finest-level polygon; build_polygons.py then
                                    skips the Voronoi derivation and dissolves the
                                    coarser levels from these
    SHARDED_LEVELS   optional: polygon levels too numerous for index.json (NL PC5/PC6);
                     their codes and bounding boxes go into units.bin, one gzipped slice
                     per SHARD_LEVEL code, like GB's unit postcodes
    DENSITY_LEVEL    optional: level whose units/km² drives the app's density shift
                     (default: the finest polygon level); False when the counts are
                     not a measure of density (DE, one point per postcode and no
                     addresses), which turns the readout and the shift off
"""
import importlib


def get(code):
    return importlib.import_module(f"countries.{code.lower()}")


def point_noun(mod):
    """What one row of read_units() is: "postcodes" (one point per code) or "addresses"."""
    return getattr(mod, "POINT_NOUN", None) or (mod.POINT_LEVEL or {}).get("noun") or "points"


def clipped(mod):
    """Whether the polygons are cut to a land mask (derived always; official only
    with a mask), and hence come with `_lines` layers instead of their own outline."""
    return not hasattr(mod, "read_polygons") or hasattr(mod, "mask")


def levels_all(mod):
    """Polygon levels plus the point level (if any), coarse to fine."""
    return list(mod.LEVELS) + ([mod.POINT_LEVEL] if mod.POINT_LEVEL else [])
