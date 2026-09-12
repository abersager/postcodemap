#!/usr/bin/env python3
"""Download UK country boundaries (clipped to the coastline) from the ONS Open
Geography Portal as GeoJSON, for use as the polygon clip mask.

By default the newest "Countries (<month> <year>) Boundaries UK BGC" feature
service is discovered through the ArcGIS Online catalogue search (BGC =
generalised to 20 m, clipped to the coastline; ~10 MB). Pass --url to use a
specific FeatureServer layer URL (e.g. a BFC full-resolution layer) instead.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

SEARCH = "https://www.arcgis.com/sharing/rest/search"
UA = {"User-Agent": "postcodemap-pipeline/1.0"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def discover():
    q = 'title:"Countries" AND title:"Boundaries UK BGC" AND owner:ONSGeography_data AND type:"Feature Service"'
    params = {"q": q, "f": "json", "num": 20, "sortField": "modified", "sortOrder": "desc"}
    res = get_json(SEARCH + "?" + urllib.parse.urlencode(params))
    items = [i for i in res.get("results", []) if "UK BGC" in i.get("title", "") and i.get("url")]
    if not items:
        sys.exit("No ONS Countries UK BGC feature service found; pass --url explicitly")
    items.sort(key=lambda i: i.get("modified", 0), reverse=True)
    print(f"fetch_coastline: using '{items[0]['title']}'", file=sys.stderr)
    return items[0]["url"].rstrip("/") + "/0"


def fetch(out, url=None):
    layer = url.rstrip("/") if url else discover()
    params = {"where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson"}
    q = layer + "/query?" + urllib.parse.urlencode(params)
    print(f"fetch_coastline: GET {q}", file=sys.stderr)
    gj = get_json(q)
    if gj.get("type") != "FeatureCollection" or not gj.get("features"):
        raise RuntimeError(f"unexpected response from {q}: {str(gj)[:200]}")
    with open(out, "w") as f:
        json.dump(gj, f)
    print(f"fetch_coastline: {len(gj['features'])} features -> {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", help="FeatureServer layer URL (…/FeatureServer/0)")
    a = ap.parse_args()
    try:
        fetch(a.out, a.url)
    except Exception as e:  # network / policy / catalogue problems
        sys.exit(f"fetch_coastline: failed ({e}). Download the ONS 'Countries ... Boundaries UK BGC' GeoJSON manually to {a.out}, or pass --url.")


if __name__ == "__main__":
    main()
