import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import CONFIG from "./config.js";

const abs = (p) => new URL(p, document.baseURI).href;
const norm = (s) => s.toUpperCase().replace(/[^A-Z0-9]/g, "");

// ---------------------------------------------------------------------------
// Countries: meta.json describes levels, thresholds, bounds and attribution
// ---------------------------------------------------------------------------
const COUNTRIES = await Promise.all(CONFIG.countries.map(async (cc) => {
  const base = abs(`${CONFIG.countryBase}${cc}/`);
  const meta = await fetch(base + "meta.json").then((r) => (r.ok ? r.json() : Promise.reject(`${cc}: meta.json ${r.status}`)));
  // levels: polygon levels then the point level (if any); each with its threshold
  const levels = [...meta.levels.map((l) => ({ ...l, kind: "polygon" })), ...(meta.pointLevel ? [{ ...meta.pointLevel, kind: "point" }] : [])];
  const over = CONFIG.thresholds[cc] || {};
  for (const l of levels) if (over[l.id] !== undefined) l.threshold = over[l.id];
  return { cc, base, meta, levels, shift: 0, index: null };
}));
const byCode = Object.fromEntries(COUNTRIES.map((c) => [c.cc, c]));
let active = COUNTRIES[0];

// zoom range [min, max) of a level, including the country's density shift
function zoomRange(c, i) {
  const lo = i === 0 ? 0 : c.levels[i].threshold + c.shift;
  const hi = i + 1 < c.levels.length ? c.levels[i + 1].threshold + c.shift : 24;
  return [lo, hi];
}
const levelIndexAt = (c, zoom) => Math.max(0, c.levels.findIndex((_, i) => zoom < zoomRange(c, i)[1]) === -1 ? c.levels.length - 1 : c.levels.findIndex((_, i) => zoom < zoomRange(c, i)[1]));
const layerId = (c, i, part) => `${c.cc}-${c.levels[i].id}-${part}`;

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------
maplibregl.addProtocol("pmtiles", new Protocol().tile);

async function loadBasemapStyle() {
  try {
    const r = await fetch(CONFIG.basemap.style);
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn("Basemap style unavailable, using blank background:", e.message);
    return { version: 8, glyphs: CONFIG.basemap.glyphs, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": CONFIG.basemap.fallbackBackground } }] };
  }
}

const allBounds = COUNTRIES.reduce((b, c) => [Math.min(b[0], c.meta.bounds[0]), Math.min(b[1], c.meta.bounds[1]), Math.max(b[2], c.meta.bounds[2]), Math.max(b[3], c.meta.bounds[3])], [180, 90, -180, -90]);
const map = new maplibregl.Map({
  container: "map", style: await loadBasemapStyle(),
  bounds: CONFIG.initialBounds || allBounds, fitBoundsOptions: { padding: 20 },
  hash: true, attributionControl: false, maxZoom: 19,
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");
{ // keep the legend above the attribution bar however many lines it wraps to
  const legend = document.getElementById("legend"), attrib = document.querySelector(".maplibregl-ctrl-bottom-right");
  const place = () => { legend.style.bottom = `${Math.ceil(attrib.getBoundingClientRect().height) + 12}px`; };
  new ResizeObserver(place).observe(attrib); place();
}

map.on("load", () => {
  for (const c of COUNTRIES) addCountry(c);
  wireInteraction();
  updateActiveCountry();
  map.on("moveend", updateActiveCountry);
  map.on("zoom", updateLegend);
  startTileKeepAlive();
});

function addCountry(c) {
  const polys = c.levels.filter((l) => l.kind === "polygon");
  map.addSource(`${c.cc}-boundaries`, {
    type: "vector", url: "pmtiles://" + c.base + "boundaries.pmtiles",
    promoteId: Object.fromEntries(polys.map((l) => [l.id, "code"])), attribution: c.meta.attribution,
  });
  if (c.meta.hasPoints) map.addSource(`${c.cc}-points`, { type: "vector", url: "pmtiles://" + c.base + "points.pmtiles", promoteId: { points: "code" } });

  c.levels.forEach((lvl, i) => {
    const [minzoom, maxzoom] = zoomRange(c, i);
    if (lvl.kind === "polygon") {
      const s = CONFIG.levelStyles[Math.min(i, CONFIG.levelStyles.length - 1)];
      map.addLayer({ id: layerId(c, i, "fill"), type: "fill", source: `${c.cc}-boundaries`, "source-layer": lvl.id, minzoom, maxzoom,
        paint: { "fill-color": s.color, "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], CONFIG.hoverFillOpacity, CONFIG.fillOpacity] } });
      map.addLayer({ id: layerId(c, i, "line"), type: "line", source: `${c.cc}-boundaries`, "source-layer": `${lvl.id}_lines`, minzoom, maxzoom,
        layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": s.color, "line-width": s.lineWidth, "line-opacity": 0.9 } });
      map.addLayer({ id: layerId(c, i, "label"), type: "symbol", source: `${c.cc}-boundaries`, "source-layer": `${lvl.id}_labels`, minzoom, maxzoom,
        layout: { "text-field": ["get", "code"], "text-font": CONFIG.fonts, "text-size": s.textSize },
        paint: { "text-color": s.color, "text-halo-color": "#ffffff", "text-halo-width": 1.6 } });
    } else {
      const u = CONFIG.pointStyle;
      const finest = polys[polys.length - 1];
      map.addLayer({ id: layerId(c, i, "context"), type: "line", source: `${c.cc}-boundaries`, "source-layer": `${finest.id}_lines`, minzoom,
        paint: { "line-color": CONFIG.levelStyles[Math.min(polys.length - 1, 3)].color, "line-width": 1, "line-opacity": 0.5, "line-dasharray": [3, 2] } });
      map.addLayer({ id: layerId(c, i, "circle"), type: "circle", source: `${c.cc}-points`, "source-layer": "points", minzoom,
        paint: { "circle-radius": ["case", ["boolean", ["feature-state", "hover"], false], u.circleRadius + 3, u.circleRadius], "circle-color": u.color, "circle-stroke-color": "#fff", "circle-stroke-width": 1.2 } });
      map.addLayer({ id: layerId(c, i, "label"), type: "symbol", source: `${c.cc}-points`, "source-layer": "points", minzoom,
        layout: { "text-field": ["get", "code"], "text-font": CONFIG.fonts, "text-size": u.textSize, "text-offset": [0, 0.9], "text-anchor": "top", "text-optional": true },
        paint: { "text-color": "#7a3300", "text-halo-color": "#fff", "text-halo-width": 1.4 } });
    }
  });
  // outline of the last searched polygon, at any zoom the tiles cover
  polys.forEach((lvl, i) => map.addLayer({ id: layerId(c, i, "highlight"), type: "line", source: `${c.cc}-boundaries`, "source-layer": lvl.id,
    filter: ["==", ["get", "code"], ""], paint: { "line-color": "#111", "line-width": 3, "line-opacity": 0.85 } }));
}

function applyZoomRanges(c) {
  c.levels.forEach((lvl, i) => {
    const [lo, hi] = zoomRange(c, i);
    const parts = lvl.kind === "polygon" ? ["fill", "line", "label"] : ["context", "circle", "label"];
    for (const p of parts) map.setLayerZoomRange(layerId(c, i, p), lo, lvl.kind === "polygon" ? hi : 24);
  });
}

function startTileKeepAlive() {
  if (!(CONFIG.tileKeepAliveMs > 0) || !COUNTRIES.length) return;
  const url = COUNTRIES[0].base + "boundaries.pmtiles";
  setInterval(() => { if (document.visibilityState === "visible") fetch(url, { headers: { Range: "bytes=0-0" }, cache: "no-store" }).then((r) => r.arrayBuffer()).catch(() => {}); }, CONFIG.tileKeepAliveMs);
}

// ---------------------------------------------------------------------------
// Active country (under the map centre) and density shift
// ---------------------------------------------------------------------------
const inBounds = (b, lng, lat) => lng >= b[0] && lng <= b[2] && lat >= b[1] && lat <= b[3];
function updateActiveCountry() {
  const { lng, lat } = map.getCenter();
  let next = COUNTRIES.find((c) => inBounds(c.meta.bounds, lng, lat));
  if (!next) { // nearest by bbox centre
    next = COUNTRIES.map((c) => ({ c, d: Math.hypot((c.meta.bounds[0] + c.meta.bounds[2]) / 2 - lng, (c.meta.bounds[1] + c.meta.bounds[3]) / 2 - lat) })).sort((a, b) => a.d - b.d)[0].c;
  }
  active = next;
  updateLegend();
  updateDensityShift();
}

function densityAtCentre(c) {
  if (!c.index) return null;
  const finest = c.levels.filter((l) => l.kind === "polygon").slice(-1)[0];
  const table = c.index[finest.id];
  const { lng, lat } = map.getCenter();
  let best = null;
  for (const code in table) {
    const e = table[code];
    if (!inBounds(e, lng, lat) || !e[5]) continue;
    const size = (e[2] - e[0]) * (e[3] - e[1]);
    if (!best || size < best.size) best = { code, size, density: e[4] / e[5] };
  }
  return best;
}

function updateDensityShift() {
  const cfg = CONFIG.density, c = active;
  let shift = 0, info = null;
  if (cfg?.enabled) {
    info = densityAtCentre(c);
    if (info) shift = Math.round(Math.min(cfg.maxShift, Math.max(0, Math.log10(info.density / cfg.baseUnitsPerKm2))) * 2) / 2;
  }
  const noun = c.meta.pointNoun || "points";
  densityEl.textContent = info ? `${info.code}: ${Math.round(info.density).toLocaleString()} ${noun}/km²${shift ? `, levels shifted +${shift}` : ""}` : "";
  if (shift === c.shift) return;
  c.shift = shift;
  applyZoomRanges(c);
  updateLegend();
}

// ---------------------------------------------------------------------------
// Hover, click, highlight
// ---------------------------------------------------------------------------
let hovered = null;
const hoverEl = document.getElementById("hover");
function setHover(next) {
  if (hovered) map.setFeatureState(hovered, { hover: false });
  hovered = next;
  if (hovered) map.setFeatureState(hovered, { hover: true });
}
const describe = (p) => (p.name ? `${p.code} ${p.name}` : p.code) + (p.units ? ` · ${p.units.toLocaleString()}` : "");

function wireInteraction() {
  for (const c of COUNTRIES) c.levels.forEach((lvl, i) => {
    const layer = layerId(c, i, lvl.kind === "polygon" ? "fill" : "circle");
    const source = lvl.kind === "polygon" ? `${c.cc}-boundaries` : `${c.cc}-points`;
    const sourceLayer = lvl.kind === "polygon" ? lvl.id : "points";
    map.on("mousemove", layer, (e) => {
      const f = e.features[0];
      if (!f) return;
      map.getCanvas().style.cursor = "pointer";
      if (!hovered || hovered.id !== f.id || hovered.sourceLayer !== sourceLayer) setHover({ source, sourceLayer, id: f.id });
      hoverEl.textContent = describe(f.properties);
    });
    map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; setHover(null); hoverEl.textContent = ""; });
    map.on("click", layer, (e) => {
      const f = e.features[0];
      if (!f) return;
      if (lvl.kind === "point") {
        const [lng, lat] = f.geometry.coordinates;
        new maplibregl.Popup({ offset: 8 }).setLngLat([lng, lat]).setHTML(`<strong>${f.properties.code}</strong><br><small>${lat.toFixed(5)}, ${lng.toFixed(5)}</small>`).addTo(map);
        return;
      }
      zoomToBounds(c, [f.properties.minx, f.properties.miny, f.properties.maxx, f.properties.maxy], i);
    });
  });
}

// Fit a bbox, landing inside the next level's zoom range so a click always reveals more detail.
function zoomToBounds(c, bbox, i) {
  const cam = map.cameraForBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40 });
  if (!cam) return;
  if (i + 1 < c.levels.length) {
    const [lo, hi] = zoomRange(c, i + 1);
    cam.zoom = Math.min(Math.max(cam.zoom, lo + 0.15), hi - 0.05);
  }
  map.flyTo({ ...cam, duration: 900 });
}

function setHighlight(c, levelId, code) {
  for (const k of COUNTRIES) k.levels.forEach((lvl, i) => {
    if (lvl.kind === "polygon") map.setFilter(layerId(k, i, "highlight"), ["==", ["get", "code"], k === c && lvl.id === levelId ? code : ""]);
  });
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------
const zoomEl = document.getElementById("zoom");
const densityEl = document.getElementById("density");
const rowsEl = document.getElementById("rows");
const countryEl = document.getElementById("country");
function updateLegend() {
  const c = active, z = map.getZoom(), current = levelIndexAt(c, z);
  countryEl.textContent = c.meta.name;
  rowsEl.innerHTML = c.levels.map((lvl, i) => {
    const [a, b] = zoomRange(c, i);
    const range = b >= 24 ? `z ≥ ${a}` : a === 0 ? `z < ${b}` : `z ${a}–${b}`;
    const color = lvl.kind === "polygon" ? CONFIG.levelStyles[Math.min(i, 3)].color : CONFIG.pointStyle.color;
    return `<div class="row${i === current ? " active" : ""}" data-i="${i}" style="${i === current ? `color:${color}` : ""}" title="Zoom to this level"><span class="swatch"></span>${lvl.name}<small>${range}</small></div>`;
  }).join("");
  for (const row of rowsEl.querySelectorAll(".row")) row.addEventListener("click", () => map.easeTo({ zoom: zoomRange(c, +row.dataset.i)[0] + 0.15 }));
  zoomEl.textContent = `(zoom ${z.toFixed(1)})`;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
const form = document.getElementById("search");
const input = document.getElementById("q");
const sugg = document.getElementById("suggestions");
const msg = document.getElementById("msg");

const indexReady = Promise.all(COUNTRIES.map((c) => fetch(c.base + "index.json").then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
  .then((j) => { c.index = j; if (c === active && map.loaded()) updateDensityShift(); }).catch((e) => console.warn(`${c.cc}: search index unavailable:`, e))));

// Point lists live in one file per country (units.bin): gzipped JSON slices
// addressed by index.json["shards"], fetched with a range request.
const shardCache = new Map();
async function unitsOf(c, shard) {
  const key = `${c.cc}/${shard}`;
  if (!shardCache.has(key)) shardCache.set(key, (async () => {
    const loc = c.index?.shards?.[shard];
    if (!loc) return {};
    try {
      const r = await fetch(c.base + "units.bin", { headers: { Range: `bytes=${loc[0]}-${loc[0] + loc[1] - 1}` } });
      if (r.status !== 206 && r.status !== 200) return {};
      let buf = await r.arrayBuffer();
      if (r.status === 200) buf = buf.slice(loc[0], loc[0] + loc[1]); // server ignored the range
      const text = await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
      return JSON.parse(text);
    } catch (e) { console.warn("units shard", key, e); return {}; }
  })());
  return shardCache.get(key);
}
const bboxOfPoints = (pts) => pts.reduce((b, [x, y]) => [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)], [Infinity, Infinity, -Infinity, -Infinity]);
const polyLevels = (c) => c.levels.filter((l) => l.kind === "polygon");

// Resolve a fragment to { c, level, code, bbox } or { c, level: point, code, point } etc.
async function resolve(raw) {
  const q = norm(raw);
  if (!q) return null;
  const order = [active, ...COUNTRIES.filter((c) => c !== active)];
  // 1. exact match on any polygon code, finest level first, active country first
  for (const c of order) {
    if (!c.index) continue;
    for (const lvl of [...polyLevels(c)].reverse()) {
      const hit = Object.keys(c.index[lvl.id]).find((code) => norm(code) === q);
      if (hit) return { c, level: lvl, code: hit, bbox: c.index[lvl.id][hit].slice(0, 4) };
    }
  }
  // 2. point codes: the longest shard code that prefixes the query names the shard file
  for (const c of order) {
    if (!c.index || !c.meta.hasPoints) continue;
    const shards = Object.keys(c.index[c.meta.shardLevel]).filter((code) => q.startsWith(norm(code))).sort((a, b) => b.length - a.length);
    for (const shard of shards.slice(0, 2)) {
      const units = await unitsOf(c, shard);
      const hits = Object.entries(units).filter(([code]) => norm(code).startsWith(q));
      if (hits.length === 1) return { c, level: c.levels[c.levels.length - 1], code: hits[0][0], point: hits[0][1] };
      if (hits.length > 1) return { c, level: c.levels[c.levels.length - 1], code: "", bbox: bboxOfPoints(hits.map((h) => h[1])), matches: hits.length };
    }
  }
  // 3. prefix of polygon codes: fit them all at the most specific matching level
  const all = prefixMatches(q, Infinity);
  if (!all.length) return null;
  const { c, level } = all[0];
  const same = all.filter((h) => h.c === c && h.level === level);
  const bbox = same.reduce((b, h) => [Math.min(b[0], h.bbox[0]), Math.min(b[1], h.bbox[1]), Math.max(b[2], h.bbox[2]), Math.max(b[3], h.bbox[3])], [Infinity, Infinity, -Infinity, -Infinity]);
  return { c, level, code: same.length === 1 ? same[0].code : "", bbox, matches: same.length };
}

function prefixMatches(q, limit = 8) {
  const out = [];
  for (const c of [active, ...COUNTRIES.filter((c) => c !== active)]) {
    if (!c.index) continue;
    for (const lvl of polyLevels(c)) {
      for (const code in c.index[lvl.id]) {
        if (norm(code).startsWith(q)) out.push({ c, level: lvl, code, bbox: c.index[lvl.id][code].slice(0, 4), name: c.index[lvl.id][code][6] });
        if (out.length >= limit) return out;
      }
    }
  }
  return out;
}

function goTo(hit) {
  msg.hidden = true;
  setHighlight(hit.c, hit.level.id, hit.code);
  if (hit.point) {
    map.flyTo({ center: hit.point, zoom: Math.max(zoomRange(hit.c, hit.c.levels.length - 1)[0] + 3, 16), duration: 1200 });
    new maplibregl.Popup({ offset: 8 }).setLngLat(hit.point).setHTML(`<strong>${hit.code}</strong>`).addTo(map);
    return;
  }
  const cam = map.cameraForBounds([[hit.bbox[0], hit.bbox[1]], [hit.bbox[2], hit.bbox[3]]], { padding: 60, maxZoom: 17 });
  if (!cam) return;
  cam.zoom = Math.max(cam.zoom, zoomRange(hit.c, hit.c.levels.indexOf(hit.level))[0] + 0.15);
  map.flyTo({ ...cam, duration: 1200 });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  await indexReady;
  const hit = await resolve(input.value);
  hideSuggestions();
  if (!hit) {
    msg.textContent = COUNTRIES.some((c) => c.index) ? `No postcode matching “${input.value.trim()}”` : "Search index not built yet (run make)";
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
  if (!q) return hideSuggestions();
  const hits = prefixMatches(q, 8);
  if (!hits.length) return hideSuggestions();
  sugg.innerHTML = hits.map((h) => `<li data-code="${h.code}">${h.code}${h.name ? ` <span class="name">${h.name}</span>` : ""}<small>${h.level.name.toLowerCase()} · ${h.c.cc.toUpperCase()}</small></li>`).join("");
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

window.__map = map; window.__countries = COUNTRIES; // handy in the console
