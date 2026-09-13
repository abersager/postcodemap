// All tunables for the map live here.
export default {
  // Countries to load; each needs web/public/countries/<cc>/ built by `make COUNTRY=<cc>`.
  // Every country's tiles are added to the map at once; MapLibre only fetches
  // tiles inside each archive's bounds, so unused countries cost one small
  // header request each.
  countries: ["gb", "at"],
  // Where each country's files are served from (+ "<cc>/meta.json" etc.).
  // Relative for local builds; the Cloudflare deploy sets VITE_COUNTRY_BASE to
  // the versioned R2 prefix, e.g. https://data.postcodemap.net/v/<ver>/countries/
  countryBase: import.meta.env.VITE_COUNTRY_BASE || "countries/",

  // Zoom thresholds come from each country's meta.json (see pipeline/countries/).
  // Override per country and level id here, e.g. { gb: { district: 8, sector: 11, unit: 13 } }.
  // A level is shown from its threshold up to the next level's threshold.
  // Tiles cover each level from two zooms below its default threshold up to
  // z12 (points at z13), overzoomed beyond, so thresholds can move up freely
  // but not below (default - 2) without re-tiling (pipeline/build_tiles.py).
  thresholds: {},

  // Dense places need more zoom before the next level is readable: the active
  // country's thresholds are shifted up by log10(density / baseUnitsPerKm2),
  // capped at maxShift and rounded to 0.5, where density is points per km²
  // (unit postcodes for GB, addresses for AT) of the finest polygon under the
  // map centre. Set enabled: false to disable.
  density: { enabled: true, baseUnitsPerKm2: 40, maxShift: 2 },

  // Every N ms, while the page is visible, send a 1-byte range request to the
  // tile host so the pooled HTTP connection never sits idle (some network paths
  // silently drop idle connections and the browser then stalls 10-18 s on the
  // next request). 0 disables. See README, "Performance".
  tileKeepAliveMs: 4000,

  // Basemap: any MapLibre style URL. OpenFreeMap needs no key.
  basemap: {
    style: "https://tiles.openfreemap.org/styles/liberty",
    glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    fallbackBackground: "#e8ecef",
  },

  // Initial view: null fits all loaded countries; or [west, south, east, north].
  initialBounds: null,
  fonts: ["Noto Sans Bold"],

  // Polygon levels are styled by depth (coarsest first); points have their own style.
  levelStyles: [
    { color: "#7b3294", lineWidth: 2.0, textSize: 16 },
    { color: "#c2185b", lineWidth: 1.5, textSize: 13 },
    { color: "#0571b0", lineWidth: 1.2, textSize: 12 },
    { color: "#1b7837", lineWidth: 1.0, textSize: 11 },
  ],
  pointStyle: { color: "#e66101", circleRadius: 4, textSize: 11 },
  fillOpacity: 0,          // polygons are outline-only; the invisible fill still takes hover/click
  hoverFillOpacity: 0.12,
};
