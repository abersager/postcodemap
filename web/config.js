// All tunables for the map live here.
//
// Zoom thresholds: a level is shown from its threshold up to the next one.
//   area     : zoom <  thresholds.district
//   district : thresholds.district <= zoom < thresholds.sector
//   sector   : thresholds.sector   <= zoom < thresholds.unit
//   unit     : zoom >= thresholds.unit
// The tiles carry each level over a wider zoom range than these defaults
// (areas z0-12, districts z5-14, sectors z8-14, units z12-14, overzoomed
// beyond) so you can move thresholds freely inside those ranges without
// re-tiling. See pipeline/build_tiles.sh if you need to go further.
export default {
  thresholds: { district: 8, sector: 11, unit: 13 },

  // Where the PMTiles archives and the search index are served from. Relative
  // paths resolve against the page URL; use absolute URLs to host the (large)
  // tiles on object storage while the app sits on GitHub Pages.
  tiles: {
    boundaries: "tiles/boundaries.pmtiles",
    units: "tiles/units.pmtiles",
  },
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

  initialBounds: [-8.7, 49.8, 1.9, 60.9], // whole UK
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
