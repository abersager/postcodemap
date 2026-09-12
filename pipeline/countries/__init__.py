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
                  to POINT_LEVEL["noun"] or "points"
    ATTRIBUTION   HTML shown in the map's attribution control
    LICENCE       short licence statement for docs and meta.json
    download(raw_dir)            fetch source files (idempotent)
    read_units(raw_dir) -> iter  yields (raw_code, lon, lat) for every point
                                 (unit postcode or address); WGS84
    parse(raw_code) -> dict      {"code": normalised finest code, <level id>: code, ...}
                                 or None if the code is not valid/geographic
    names(raw_dir) -> dict       optional: finest-level code -> place name
    mask(raw_dir) -> path|None   optional: GeoJSON (WGS84) land polygons for clipping
"""
import importlib


def get(code):
    return importlib.import_module(f"countries.{code.lower()}")


def levels_all(mod):
    """Polygon levels plus the point level (if any), coarse to fine."""
    return list(mod.LEVELS) + ([mod.POINT_LEVEL] if mod.POINT_LEVEL else [])
