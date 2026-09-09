import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import CONFIG from "./config.js";

const LEVELS = ["area", "district", "sector", "unit"];
const SOURCE_LAYER = { area: "areas", district: "districts", sector: "sectors", unit: "units" };
const LABEL_LAYER = { area: "area_labels", district: "district_labels", sector: "sector_labels" };
const LINE_LAYER = { area: "area_lines", district: "district_lines", sector: "sector_lines" };

// zoom range [min, max) for each level, derived from the thresholds plus the
// current density shift (see CONFIG.density)
let densityShift = 0;
function zoomRange(level) {
  const t = CONFIG.thresholds, d = densityShift;
  return { area: [0, t.district + d], district: [t.district + d, t.sector + d], sector: [t.sector + d, t.unit + d], unit: [t.unit + d, 24] }[level];
}
function levelAt(zoom) {
  return LEVELS.find((l) => zoom < zoomRange(l)[1]) ?? "unit";
}

const abs = (p) => new URL(p, document.baseURI).href;

maplibregl.addProtocol("pmtiles", new Protocol().tile);

async function loadBasemapStyle() {
  try {
    const r = await fetch(CONFIG.basemap.style);
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn("Basemap style unavailable, using blank background:", e.message);
    return {
      version: 8,
      glyphs: CONFIG.basemap.glyphs,
      sources: {},
      layers: [{ id: "bg", type: "background", paint: { "background-color": CONFIG.basemap.fallbackBackground } }],
    };
  }
}

const map = new maplibregl.Map({
  container: "map",
  style: await loadBasemapStyle(),
  bounds: CONFIG.initialBounds,
  fitBoundsOptions: { padding: 20 },
  hash: true,
  attributionControl: false,
  maxZoom: 19,
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");

// Keep the legend above the attribution bar however many lines it wraps to.
{
  const legend = document.getElementById("legend");
  const attrib = document.querySelector(".maplibregl-ctrl-bottom-right");
  const place = () => { legend.style.bottom = `${Math.ceil(attrib.getBoundingClientRect().height) + 12}px`; };
  new ResizeObserver(place).observe(attrib);
  place();
}

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------
map.on("load", () => {
  map.addSource("boundaries", {
    type: "vector",
    url: "pmtiles://" + abs(CONFIG.tiles.boundaries),
    promoteId: { areas: "code", districts: "code", sectors: "code" },
    attribution: CONFIG.attribution,
  });
  map.addSource("units", {
    type: "vector",
    url: "pmtiles://" + abs(CONFIG.tiles.units),
    promoteId: { units: "postcode" },
  });

  for (const level of ["area", "district", "sector"]) {
    const s = CONFIG.levels[level];
    const [minzoom, maxzoom] = zoomRange(level);
    map.addLayer({
      id: `${level}-fill`, type: "fill", source: "boundaries", "source-layer": SOURCE_LAYER[level], minzoom, maxzoom,
      paint: {
        "fill-color": s.color,
        "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], CONFIG.hoverFillOpacity, s.fillOpacity],
      },
    });
    // Boundaries between polygons only; the coast is left to the basemap.
    map.addLayer({
      id: `${level}-line`, type: "line", source: "boundaries", "source-layer": LINE_LAYER[level], minzoom, maxzoom,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": s.color, "line-width": s.lineWidth, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: `${level}-label`, type: "symbol", source: "boundaries", "source-layer": LABEL_LAYER[level], minzoom, maxzoom,
      layout: { "text-field": ["get", "code"], "text-font": CONFIG.fonts, "text-size": s.textSize, "text-allow-overlap": false },
      paint: { "text-color": s.color, "text-halo-color": "#ffffff", "text-halo-width": 1.6 },
    });
  }

  const u = CONFIG.levels.unit;
  const [uMin] = zoomRange("unit");
  map.addLayer({
    id: "unit-circle", type: "circle", source: "units", "source-layer": "units", minzoom: uMin,
    paint: {
      "circle-radius": ["case", ["boolean", ["feature-state", "hover"], false], u.circleRadius + 3, u.circleRadius],
      "circle-color": u.color, "circle-stroke-color": "#fff", "circle-stroke-width": 1.2,
    },
  });
  map.addLayer({
    id: "unit-label", type: "symbol", source: "units", "source-layer": "units", minzoom: uMin,
    layout: {
      "text-field": ["get", "postcode"], "text-font": CONFIG.fonts, "text-size": u.textSize,
      "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true,
    },
    paint: { "text-color": "#7a3300", "text-halo-color": "#fff", "text-halo-width": 1.4 },
  });

  // Sector boundaries stay visible (thin) under the unit points for context.
  map.addLayer({
    id: "sector-context-line", type: "line", source: "boundaries", "source-layer": "sector_lines", minzoom: uMin,
    paint: { "line-color": CONFIG.levels.sector.color, "line-width": 1, "line-opacity": 0.5, "line-dasharray": [3, 2] },
  }, "unit-circle");

  // Outline of the last searched polygon, visible at any zoom the tiles cover.
  for (const level of ["area", "district", "sector"]) {
    map.addLayer({
      id: `${level}-highlight`, type: "line", source: "boundaries", "source-layer": SOURCE_LAYER[level],
      filter: ["==", ["get", "code"], ""],
      paint: { "line-color": "#111", "line-width": 3, "line-opacity": 0.85 },
    });
  }

  wireInteraction();
  updateLegend();
  map.on("moveend", updateDensityShift);
  updateDensityShift();
  startTileKeepAlive();
});

// Keep the tile host's connection warm (see CONFIG.tileKeepAliveMs).
function startTileKeepAlive() {
  if (!(CONFIG.tileKeepAliveMs > 0)) return;
  const url = abs(CONFIG.tiles.boundaries);
  setInterval(() => {
    if (document.visibilityState !== "visible") return;
    fetch(url, { headers: { Range: "bytes=0-0" }, cache: "no-store" }).then((r) => r.arrayBuffer()).catch(() => {});
  }, CONFIG.tileKeepAliveMs);
}

// Re-derive every layer's zoom range from the thresholds and the density shift.
function applyZoomRanges() {
  for (const level of ["area", "district", "sector"]) {
    const [lo, hi] = zoomRange(level);
    for (const suffix of ["fill", "line", "label"]) map.setLayerZoomRange(`${level}-${suffix}`, lo, hi);
  }
  const [uMin] = zoomRange("unit");
  for (const id of ["unit-circle", "unit-label", "sector-context-line"]) map.setLayerZoomRange(id, uMin, 24);
}

// Units per km2 of the smallest district whose bbox contains the map centre.
function densityAtCentre() {
  if (!index) return null;
  const { lng, lat } = map.getCenter();
  let best = null;
  for (const code in index.districts) {
    const e = index.districts[code];
    if (lng < e[0] || lng > e[2] || lat < e[1] || lat > e[3] || !e[5]) continue;
    const size = (e[2] - e[0]) * (e[3] - e[1]);
    if (!best || size < best.size) best = { code, size, density: e[4] / e[5] };
  }
  return best;
}

function updateDensityShift() {
  const cfg = CONFIG.density;
  let shift = 0, info = null;
  if (cfg?.enabled) {
    info = densityAtCentre();
    if (info) shift = Math.round(Math.min(cfg.maxShift, Math.max(0, Math.log10(info.density / cfg.baseUnitsPerKm2))) * 2) / 2;
  }
  densityEl.textContent = info ? `${info.code}: ${Math.round(info.density).toLocaleString()} postcodes/km²${shift ? `, levels shifted +${shift}` : ""}` : "";
  if (shift === densityShift) return;
  densityShift = shift;
  applyZoomRanges();
  updateLegend();
}
window.__map = map; // handy in the console

// ---------------------------------------------------------------------------
// Hover + click
// ---------------------------------------------------------------------------
let hovered = null; // { source, sourceLayer, id }
const hoverEl = document.getElementById("hover");

function setHover(next) {
  if (hovered) map.setFeatureState(hovered, { hover: false });
  hovered = next;
  if (hovered) map.setFeatureState(hovered, { hover: true });
}

function wireInteraction() {
  const interactive = [
    ["area-fill", "boundaries", "areas"], ["district-fill", "boundaries", "districts"],
    ["sector-fill", "boundaries", "sectors"], ["unit-circle", "units", "units"],
  ];
  for (const [layer, source, sourceLayer] of interactive) {
    map.on("mousemove", layer, (e) => {
      const f = e.features[0];
      if (!f) return;
      map.getCanvas().style.cursor = "pointer";
      if (!hovered || hovered.id !== f.id) setHover({ source, sourceLayer, id: f.id });
      const p = f.properties;
      hoverEl.textContent = p.units ? `${p.code} · ${p.units.toLocaleString()} postcodes` : p.postcode ?? p.code;
    });
    map.on("mouseleave", layer, () => {
      map.getCanvas().style.cursor = "";
      setHover(null);
      hoverEl.textContent = "";
    });
    map.on("click", layer, (e) => {
      const f = e.features[0];
      if (!f) return;
      if (layer === "unit-circle") {
        const [lng, lat] = f.geometry.coordinates;
        new maplibregl.Popup({ offset: 8 }).setLngLat([lng, lat])
          .setHTML(`<strong>${f.properties.postcode}</strong><br><small>${lat.toFixed(5)}, ${lng.toFixed(5)}</small>`).addTo(map);
        return;
      }
      zoomToBounds([f.properties.minx, f.properties.miny, f.properties.maxx, f.properties.maxy], f.properties.level);
    });
  }
}

// Fit a bbox, but make sure we land at least at the next level's minimum zoom
// so a click always reveals more detail.
function zoomToBounds(bbox, level) {
  const cam = map.cameraForBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40 });
  if (!cam) return;
  const next = LEVELS[LEVELS.indexOf(level) + 1];
  if (next) {
    const [lo, hi] = zoomRange(next);
    cam.zoom = Math.min(Math.max(cam.zoom, lo + 0.15), hi - 0.05);
  }
  map.flyTo({ ...cam, duration: 900 });
}

function setHighlight(level, code) {
  for (const l of ["area", "district", "sector"]) {
    if (map.getLayer(`${l}-highlight`)) map.setFilter(`${l}-highlight`, ["==", ["get", "code"], l === level ? code : ""]);
  }
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------
const zoomEl = document.getElementById("zoom");
const densityEl = document.getElementById("density");
function updateLegend() {
  const z = map.getZoom();
  const current = levelAt(z);
  for (const row of document.querySelectorAll("#legend .row")) {
    const level = row.dataset.level;
    const [a, b] = zoomRange(level);
    row.classList.toggle("active", level === current);
    row.style.color = level === current ? CONFIG.levels[level].color : "";
    row.querySelector("small").textContent = b >= 24 ? `z ≥ ${a}` : a === 0 ? `z < ${b}` : `z ${a}–${b}`;
    row.dataset.min = a;
  }
  zoomEl.textContent = `(zoom ${z.toFixed(1)})`;
}
map.on("zoom", updateLegend);
for (const row of document.querySelectorAll("#legend .row")) {
  row.style.cursor = "pointer";
  row.title = "Zoom to this level";
  row.addEventListener("click", () => map.easeTo({ zoom: zoomRange(row.dataset.level)[0] + 0.15 }));
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
const form = document.getElementById("search");
const input = document.getElementById("q");
const sugg = document.getElementById("suggestions");
const msg = document.getElementById("msg");

let index = null; // { areas: {code: bbox}, districts: {...}, sectors: {...} }
const indexReady = fetch(abs(CONFIG.searchIndex)).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
  .then((j) => { index = j; if (map.loaded()) updateDensityShift(); }).catch((e) => console.warn("Search index unavailable:", e));

const unitCache = new Map();
async function unitsOf(district) {
  if (!unitCache.has(district)) {
    unitCache.set(district, fetch(abs(CONFIG.unitIndexDir + district + ".json")).then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
  }
  return unitCache.get(district);
}

const norm = (s) => s.toUpperCase().replace(/[^A-Z0-9]/g, "");
const bboxOfPoints = (pts) => pts.reduce((b, [x, y]) => [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)], [Infinity, Infinity, -Infinity, -Infinity]);

// Resolve a fragment to { level, code, bbox, items? }. Tries the longest
// district prefix first so "SW1A2AA" is SW1A + 2AA, not SW1 + A2AA.
async function resolve(raw) {
  const q = norm(raw);
  if (!q || !index) return null;
  if (index.areas[q]) return { level: "area", code: q, bbox: index.areas[q] };
  for (let k = Math.min(4, q.length); k >= 2; k--) {
    const d = q.slice(0, k), rest = q.slice(k);
    if (!index.districts[d] && !index.sectors[`${d} ${rest[0]}`]) continue;
    if (rest === "") return { level: "district", code: d, bbox: index.districts[d] };
    if (rest.length === 1 && index.sectors[`${d} ${rest}`]) return { level: "sector", code: `${d} ${rest}`, bbox: index.sectors[`${d} ${rest}`] };
    if (rest.length >= 1 && rest.length <= 3) {
      const units = await unitsOf(d);
      const prefix = `${d} ${rest}`;
      const hits = Object.entries(units).filter(([pc]) => pc.startsWith(prefix));
      if (hits.length === 1) return { level: "unit", code: hits[0][0], point: hits[0][1] };
      if (hits.length > 1) return { level: "unit-prefix", code: prefix, bbox: bboxOfPoints(hits.map((h) => h[1])), items: hits.map((h) => h[0]) };
    }
  }
  // Fallback: "SW1" is not a district but is a prefix of SW10..SW1Y; fit them all.
  const all = prefixMatches(q, Infinity);
  if (!all.length) return null;
  const level = all[0].level;
  const same = all.filter((h) => h.level === level);
  const bbox = same.reduce((b, h) => [Math.min(b[0], h.bbox[0]), Math.min(b[1], h.bbox[1]), Math.max(b[2], h.bbox[2]), Math.max(b[3], h.bbox[3])], [Infinity, Infinity, -Infinity, -Infinity]);
  return { level, code: same.length === 1 ? same[0].code : "", bbox, matches: same.length };
}

function prefixMatches(q, limit = 8) {
  const out = [];
  if (!index) return out;
  for (const [level, table] of [["area", index.areas], ["district", index.districts], ["sector", index.sectors]]) {
    for (const code in table) {
      if (norm(code).startsWith(q)) out.push({ level, code, bbox: table[code] });
      if (out.length >= limit) return out;
    }
  }
  return out;
}

function goTo(hit) {
  msg.hidden = true;
  setHighlight(hit.level, hit.code);
  if (hit.level === "unit") {
    map.flyTo({ center: hit.point, zoom: Math.max(zoomRange("unit")[0] + 3, 16), duration: 1200 });
    new maplibregl.Popup({ offset: 8 }).setLngLat(hit.point).setHTML(`<strong>${hit.code}</strong>`).addTo(map);
    return;
  }
  const cam = map.cameraForBounds([[hit.bbox[0], hit.bbox[1]], [hit.bbox[2], hit.bbox[3]]], { padding: 60, maxZoom: 17 });
  if (!cam) return;
  const [lo] = zoomRange(hit.level === "unit-prefix" ? "unit" : hit.level);
  cam.zoom = Math.max(cam.zoom, lo + 0.15);
  map.flyTo({ ...cam, duration: 1200 });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  await indexReady;
  const hit = await resolve(input.value);
  hideSuggestions();
  if (!hit) {
    msg.textContent = index ? `No postcode matching “${input.value.trim()}”` : "Search index not built yet (run make)";
    msg.hidden = false;
    return;
  }
  goTo(hit);
});

let activeIdx = -1;
function hideSuggestions() { sugg.hidden = true; sugg.innerHTML = ""; activeIdx = -1; }
input.addEventListener("input", async () => {
  await indexReady;
  const q = norm(input.value);
  msg.hidden = true;
  if (q.length < 1) return hideSuggestions();
  const hits = prefixMatches(q, 8);
  if (!hits.length) return hideSuggestions();
  sugg.innerHTML = hits.map((h) => `<li data-code="${h.code}">${h.code}<small>${h.level}</small></li>`).join("");
  sugg.hidden = false;
  activeIdx = -1;
  for (const li of sugg.querySelectorAll("li")) li.addEventListener("mousedown", () => { input.value = li.dataset.code; form.requestSubmit(); });
});
input.addEventListener("keydown", (e) => {
  const items = [...sugg.querySelectorAll("li")];
  if (!items.length || sugg.hidden) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    activeIdx = (activeIdx + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items.forEach((li, i) => li.classList.toggle("active", i === activeIdx));
    input.value = items[activeIdx].dataset.code;
  } else if (e.key === "Escape") hideSuggestions();
});
input.addEventListener("blur", () => setTimeout(hideSuggestions, 150));
