// All tunables for the map live here.
//
// Zoom thresholds: a level is shown from its threshold up to the next one.
//   area     : zoom <  thresholds.district
//   district : thresholds.district <= zoom < thresholds.sector
//   sector   : thresholds.sector   <= zoom < thresholds.unit
//   unit     : zoom >= thresholds.unit
// The tiles carry areas z0-10, districts z6-12, sectors z9-12 and units at
// z13, and MapLibre overzooms beyond each range, so thresholds can move up
// freely (the density shift relies on that) but not below district 6,
// sector 9, unit 13 without re-tiling. See pipeline/build_tiles.sh.
export default {
  thresholds: { district: 8, sector: 11, unit: 13 },

  // Dense places need more zoom before the next level is readable. The
  // thresholds above are shifted up by log10(density / baseUnitsPerKm2),
  // capped at maxShift and rounded to 0.5, where density is the unit
  // postcodes per km2 of the district under the map centre. With the
  // defaults, a rural district (< 40/km2) gets no shift, a suburb (~400/km2)
  // +1 and central London (> 4000/km2) +2. Set enabled: false to disable.
  density: { enabled: true, baseUnitsPerKm2: 40, maxShift: 2 },

  // Where the PMTiles archives and the search index are served from. Relative
  // paths resolve against the page URL; use absolute URLs to host the (large)
  // tiles on object storage while the app sits on GitHub Pages.
  tiles: {
    boundaries: "tiles/boundaries.pmtiles",
    units: "tiles/units.pmtiles",
  },
  // Every N ms, while the page is visible, send a 1-byte range request to the
  // tile host so the pooled HTTP connection never sits idle. Some networks
  // (and GitHub Pages' CDN over HTTP/2) silently drop connections idle for
  // ~10 s, and the browser then needs 10-18 s to notice, so the first tiles
  // after any pause would stall. 0 disables. See README, "Performance".
  tileKeepAliveMs: 4000,

  searchIndex: "data/index.json",
  unitIndexDir: "data/units/", // + "<DISTRICT>.json"

  // Basemap: any MapLibre style URL. OpenFreeMap needs no key. To use
  // OS Open Zoomstack instead, set an OS Data Hub key and use e.g.
  // "https://api.os.uk/maps/vector/v1/vts/resources/styles?srs=3857&key=YOUR_KEY"
  // (and check its attribution requirements).
  basemap: {
    style: "https://tiles.openfreemap.org/styles/liberty",
    // Used only if the style above cannot be loaded (offline / blocked), so
    // labels still render on the blank fallback background.
    glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    fallbackBackground: "#e8ecef",
  },

  initialBounds: [-7.8, 49.8, 1.9, 60.9], // Great Britain incl. Shetland and the Hebrides
  fonts: ["Noto Sans Bold"],

  // Polygons are outline-only (fillOpacity 0); the invisible fill still
  // receives hover and click. hoverFillOpacity tints the hovered polygon.
  levels: {
    area:     { color: "#7b3294", fillOpacity: 0, lineWidth: 2.0, textSize: 16 },
    district: { color: "#c2185b", fillOpacity: 0, lineWidth: 1.5, textSize: 13 },
    sector:   { color: "#0571b0", fillOpacity: 0, lineWidth: 1.2, textSize: 12 },
    unit:     { color: "#e66101", circleRadius: 4, textSize: 11 },
  },
  hoverFillOpacity: 0.12,

  attribution:
    'Contains OS data &copy; Crown copyright and database right 2026 &middot; ' +
    'Contains Royal Mail data &copy; Royal Mail copyright and database right 2026 &middot; ' +
    'Contains ONS data &copy; Crown copyright and database right 2026, ' +
    '<a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">OGL v3</a> &middot; ' +
    'Postcode polygons are <a href="https://github.com/abersager/postcodemap/blob/main/docs/CAVEATS.md">derived, not official</a>',
};
