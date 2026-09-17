/* ============================================================================
   Deutschland · Macro Pulse — client
   ----------------------------------------------------------------------------
   D3-driven dashboard over the FastAPI endpoints in ../main.py. Everything is
   rendered from data; the only hardcoded value is the palette (shared look).
   ========================================================================== */
"use strict";

/* ---------------------------------------------------------------- palette */
const C = {
  gold:   "#f6b94b",
  gold2:  "#ffd98a",
  blue:   "#5b8cff",
  violet: "#9d8cff",
  teal:   "#4dd6c1",
  rose:   "#ff7aa2",
  green:  "#3ddc84",
  red:    "#ff6b6b",
  text:   "#f4f6fb",
  muted:  "#9aa4b8",
  faint:  "#5f6b82",
  grid:   "rgba(255,255,255,0.055)",
  border: "rgba(255,255,255,0.08)",
  band:   "#8ea2ff",
};

/* ------------------------------------------------- ECB policy corridor ----
   The corridor is the ribbon between two standing facilities. The MRO is the
   rate the ECB actually steers, so it carries the solid line while the deposit
   facility (floor) and the marginal lending facility (ceiling) are dashed, and
   the space between them is shaded. Roles come from the API; the look lives
   here. */
const CORRIDOR = {
  floor:   { name: "Deposit (floor)",            color: "#4dd6c1", dashed: true  },
  mid:     { name: "MRO (main)",                 color: "#f6b94b", dashed: false },
  ceiling: { name: "Marginal lending (ceiling)", color: "#ff7aa2", dashed: true  },
};
const BAND = { color: C.band, opacity: 0.13 };

/* Maturity ramp for the term-structure fan: short end cool → long end warm. It
   encodes *where on the curve* a line sits, not its identity — the tooltip
   carries the numbers. */
const RAMP = [C.teal, C.blue, C.violet, C.gold, C.rose];

/* ---------------------------------------------------------------- helpers */
const $ = (sel) => document.querySelector(sel);
const fmtNum = (v, d = 2) => {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
};
const fmtPct = (v, d = 2) => `${v >= 0 ? "" : ""}${fmtNum(v, d)}%`;
function parseISO(iso) {
  const p = iso.slice(0, 10).split("-").map(Number);
  return new Date(p[0], (p[1] || 1) - 1, p[2] || 1);
}
const fmtDate = (v) => {
  const d = v instanceof Date ? v : parseISO(v);
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
};

const tooltipEl = $("#tooltip");
function showTooltip(html, x, y) {
  tooltipEl.innerHTML = html;
  tooltipEl.classList.add("is-visible");
  const r = tooltipEl.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
  if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
  tooltipEl.style.left = left + "px";
  tooltipEl.style.top = top + "px";
}
function hideTooltip() { tooltipEl.classList.remove("is-visible"); }

function chartSize(sel) {
  const node = sel.node();
  return { width: node.clientWidth || 640, height: node.clientHeight || 360 };
}

/* ------------------------------------------------------- corridor helpers */
/* API legs ({role, series_id, values}) -> drawable series, look filled in. */
function corridorLegs(legs) {
  return (legs || [])
    .filter(l => l && l.values && l.values.length)
    .map(l => {
      const look = CORRIDOR[l.role] || {};
      return {
        role: l.role,
        name: look.name || l.series_id || l.role,
        color: look.color || C.muted,
        dashed: !!look.dashed,
        values: l.values,
      };
    });
}

/* The shaded area spans floor -> ceiling; names have to survive the round trip
   through timeChart, so they are read back off the built series. */
function corridorBand(series) {
  const floor = series.find(s => s.role === "floor");
  const ceiling = series.find(s => s.role === "ceiling");
  if (!floor || !ceiling) return null;
  return { from: floor.name, to: ceiling.name, color: BAND.color, opacity: BAND.opacity };
}

/* Forward-fill two change-point series onto their merged date grid so an area
   can be drawn between them: rows are [date, lower, upper]. Policy rates do not
   share timestamps (each one moves only at its own meeting), and this is what
   lets the ribbon span the true corridor at every x instead of lurching between
   whichever two observations happen to line up. */
function alignStep(a, b) {
  const dates = Array.from(new Set(a.concat(b).map(p => +p[0]))).sort((m, n) => m - n);
  const rows = [];
  let lo = null, hi = null, i = 0, j = 0;
  for (const t of dates) {
    while (i < a.length && +a[i][0] <= t) lo = a[i++][1];
    while (j < b.length && +b[j][0] <= t) hi = b[j++][1];
    if (lo != null && hi != null) rows.push([new Date(t), lo, hi]);
  }
  return rows;
}

/* ---------------------------------------------------------------- loader */
async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}

/* ------------------------------------------------------------ chart shell --
   Large charts are self-sizing: they read their container's client box, so the
   only honest way to redraw one at a different size is to run its own draw
   closure again. Each chart therefore registers how to draw itself, which is
   what the lightbox below re-invokes after moving the node to full view. */
const REDRAW = new Map();   // chart container id -> draw closure

function attachExpand(id) {
  const node = document.getElementById(id);
  if (!node || node.querySelector(":scope > .chart-expand")) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "chart-expand";
  btn.title = "Expand chart";
  btn.setAttribute("aria-label", "Expand chart to full view");
  btn.innerHTML =
    '<svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" ' +
    'stroke-width="1.4" stroke-linecap="round">' +
    '<circle cx="7" cy="7" r="4.4" />' +
    '<line x1="10.4" y1="10.4" x2="14.2" y2="14.2" />' +
    "</svg>";
  btn.addEventListener("click", (ev) => { ev.stopPropagation(); openLightbox(id); });
  node.appendChild(btn);
}

/* Register a chart's draw closure, draw it, and give it the magnifier. */
function registerChart(id, draw) {
  REDRAW.set(id, draw);
  draw();
  attachExpand(id);
}

/* Draw a time series into #id, remember how, and give it the magnifier. */
function chart(id, cfg) {
  const sel = d3.select("#" + id);
  registerChart(id, () => timeChart(sel, cfg));
}

/* Redraw a chart at its container's current size. The draw closure is pure — it
   clears the container, which takes the magnifier with it — so every redraw that
   happens outside registerChart() goes through here to put the affordance back. */
function redrawChart(id) {
  REDRAW.get(id)?.();
  attachExpand(id);
}

let lightboxOpen = null;   // { id, parent, next }

function openLightbox(id) {
  const node = document.getElementById(id);
  if (!node || lightboxOpen) return;
  const card = node.closest(".card");

  $("#lightboxTitle").textContent = card?.querySelector("h2")?.textContent || "";
  $("#lightboxSub").textContent = card?.querySelector(".card-sub")?.textContent || "";

  // remember the exact slot so closing puts the chart back where it was
  lightboxOpen = { id, parent: node.parentNode, next: node.nextSibling };
  $("#lightboxPanel").appendChild(node);
  $("#lightbox").classList.add("is-open");
  $("#lightbox").setAttribute("aria-hidden", "false");
  document.body.classList.add("is-lightbox");

  // after layout, so chartSize() reads the panel's real box
  requestAnimationFrame(() => redrawChart(id));
}

function closeLightbox() {
  if (!lightboxOpen) return;
  const { id, parent, next } = lightboxOpen;
  lightboxOpen = null;
  const node = document.getElementById(id);
  if (node) parent.insertBefore(node, next);   // back into its card, same slot

  $("#lightbox").classList.remove("is-open");
  $("#lightbox").setAttribute("aria-hidden", "true");
  document.body.classList.remove("is-lightbox");
  hideTooltip();
  redrawChart(id);                             // redraw at card size
}

$("#lightboxClose").addEventListener("click", closeLightbox);
$("#lightbox").addEventListener("mousedown", (ev) => {
  // only the dimmed backdrop dismisses — clicks inside the panel are the chart's
  if (ev.target === $("#lightbox")) closeLightbox();
});
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") closeLightbox();
});

/* ---------------------------------------------------------------- KPI tiles */
let selectedId = "de10y";
let kpiData = [];

function renderKpis(snapshot) {
  kpiData = snapshot.kpis;
  const grid = d3.select("#kpiGrid");
  grid.selectAll(".kpi").data(kpiData).join("div")
    .attr("class", d => (d.corridor && d.corridor.length ? "kpi is-corridor" : "kpi"))
    .style("--i", (d, i) => i)
    .on("click", (ev, d) => selectKpi(d.id))
    .each(function (d) { buildKpi(this, d); });
  updateActive();
}

function selectKpi(id) {
  if (selectedId === id) return;
  selectedId = id;
  updateActive();
  const kpi = kpiData.find(k => k.id === id);
  if (kpi) renderHero(kpi);
}

function updateActive() {
  d3.selectAll("#kpiGrid .kpi").classed("is-active", d => d.id === selectedId);
}

function buildKpi(node, d) {
  const el = d3.select(node);
  el.html("");

  // layers: sparkline (z0) → shade gradient (z1) → text content (z2)
  if (d.corridor && d.corridor.length) corridorSpark(el, d.spark, d.corridor);
  else if (d.spark && d.spark.length > 1) sparkline(el, d.spark, d.color);
  el.append("div").attr("class", "k-shade");
  const content = el.append("div").attr("class", "k-content");

  const valueColor = d.tone === "curve"
    ? (d.value < 0 ? C.red : C.green)
    : d.tone === "inflation"
      ? (d.value > 2 ? C.gold : C.green)
      : C.text;

  const label = content.append("div").attr("class", "k-label");
  label.append("span").text(d.label);
  label.append("span").attr("class", "k-date").text(d.last_date ? fmtDate(d.last_date) : "no data");

  const vline = content.append("div").attr("class", "k-value").style("color", valueColor);
  vline.append("span").text(fmtNum(d.value, d.decimals));
  if (d.unit) vline.append("span").attr("class", "k-unit").text(d.unit);

  if (d.tone === "curve") {
    const state = d.value < 0 ? "inverted" : d.value > 0 ? "normal" : "flat";
    vline.append("span").attr("class", "k-unit")
      .style("color", d.value < 0 ? C.red : d.value > 0 ? C.green : C.muted)
      .text(` · ${state}`);
  }

  const deltas = content.append("div").attr("class", "k-deltas");
  addDelta(deltas, "1m", d.delta_1m, d.decimals);
  addDelta(deltas, "1y", d.delta_1y, d.decimals);
}

function addDelta(parent, tag, val, decimals) {
  const cls = val == null ? "flat" : val > 0 ? "up" : val < 0 ? "down" : "flat";
  const sign = val == null ? "" : val > 0 ? "▲ " : val < 0 ? "▼ " : "• ";
  parent.append("span").attr("class", `delta ${cls}`)
    .html(`<span class="tag">${tag}</span> ${sign}${fmtNum(Math.abs(val ?? 0), decimals)}`);
}

function sparkline(el, points, color) {
  const wrap = el.append("div").attr("class", "k-spark");
  const svg = wrap.append("svg").attr("viewBox", "0 0 100 34").attr("preserveAspectRatio", "none");
  const vals = points.map(p => +p[1]);
  const x = d3.scaleLinear().domain([0, points.length - 1]).range([0, 100]);
  const y = d3.scaleLinear().domain(d3.extent(vals)).range([30, 4]);
  const line = d3.line().x((p, i) => x(i)).y(p => y(p[1])).curve(d3.curveMonotoneX);
  const area = d3.area().x((p, i) => x(i)).y0(34).y1(p => y(p[1])).curve(d3.curveMonotoneX);

  const gradId = `sg-${Math.random().toString(36).slice(2)}`;
  svg.append("defs").append("linearGradient").attr("id", gradId)
    .attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 1)
    .selectAll("stop").data([[0, color, 0.5], [1, color, 0]]).join("stop")
    .attr("offset", d => d[0]).attr("stop-color", d => d[1]).attr("stop-opacity", d => d[2]);

  svg.append("path").attr("d", area(points)).attr("fill", `url(#${gradId})`);
  svg.append("path").attr("d", line(points)).attr("fill", "none")
    .attr("stroke", color).attr("stroke-width", 1.4).attr("vector-effect", "non-scaling-stroke");
}

/* Tile-sized version of the corridor chart: shaded ribbon, dashed floor and
   ceiling, solid MRO. Same 100×34 space as the plain sparkline, but x has to be
   a real time scale — the three legs step on different dates, so an index-based
   axis would shear the ribbon. `points` is the tile's own spark and only fixes
   the window. */
function corridorSpark(el, points, payload) {
  const legs = corridorLegs(payload);
  const floor = legs.find(l => l.role === "floor");
  const ceiling = legs.find(l => l.role === "ceiling");
  if (!legs.length || !points || points.length < 2) return;

  const wrap = el.append("div").attr("class", "k-spark is-corridor");
  const svg = wrap.append("svg").attr("viewBox", "0 0 100 34").attr("preserveAspectRatio", "none");

  const x = d3.scaleTime()
    .domain(d3.extent(points.map(p => parseISO(p[0]))))
    .range([0, 100]);
  const values = legs.flatMap(l => l.values.map(p => +p[1]));
  const y = d3.scaleLinear().domain(d3.extent(values)).range([30, 3]);

  legs.forEach(l => { l.pts = l.values.map(p => [parseISO(p[0]), +p[1]]); });

  if (floor && ceiling) {
    svg.append("path").datum(alignStep(floor.pts, ceiling.pts))
      .attr("d", d3.area().x(d => x(d[0])).y0(d => y(d[1])).y1(d => y(d[2])).curve(d3.curveStepAfter))
      .attr("fill", BAND.color).attr("opacity", 0.20).attr("stroke", "none");
  }
  legs.forEach(l => {
    svg.append("path").datum(l.pts)
      .attr("d", d3.line().x(p => x(p[0])).y(p => y(p[1])).curve(d3.curveStepAfter))
      .attr("fill", "none").attr("stroke", l.color)
      .attr("stroke-width", l.dashed ? 1.1 : 1.7)
      .attr("stroke-dasharray", l.dashed ? "3 2.2" : null)
      .attr("vector-effect", "non-scaling-stroke");
  });
}

/* ---------------------------------------------------------------- hero chart */
let heroCache = null; // { id, hist }

async function renderHero(kpi) {
  $("#heroTitle").textContent = kpi.label;
  $("#heroSubtitle").textContent = kpi.subtitle;
  $("#heroHint").textContent = `Showing ${kpi.label} · as of ${kpi.last_date ? fmtDate(kpi.last_date) : "—"}`;

  const meta = d3.select("#heroMeta");
  meta.html("");
  const vColor = kpi.tone === "curve" ? (kpi.value < 0 ? C.red : C.green)
    : kpi.tone === "inflation" ? (kpi.value > 2 ? C.gold : C.green) : C.text;
  const v = meta.append("div").attr("class", "hm-value").style("color", vColor);
  v.append("span").text(fmtNum(kpi.value, kpi.decimals));
  if (kpi.unit) v.append("span").style("font-size", "14px").style("color", C.muted).text(" " + kpi.unit);
  const deltas = meta.append("div").attr("class", "hm-deltas");
  addDelta(deltas, "1m", kpi.delta_1m, kpi.decimals);
  addDelta(deltas, "1y", kpi.delta_1y, kpi.decimals);

  try {
    let hist = heroCache && heroCache.id === kpi.id ? heroCache.hist : null;
    if (!hist) {
      hist = await getJSON(`/api/indicator/${kpi.id}`);
      heroCache = { id: kpi.id, hist };
    }
    registerChart("heroChart", () => drawHeroChart(kpi, hist));
  } catch (err) {
    console.error("hero chart:", err);
    d3.select("#heroChart").html(`<div class="surface-hint">Failed to load ${kpi.label} — ${err.message}</div>`);
  }
}

function drawHeroChart(kpi, hist) {
  const pctSuffix = (kpi.unit || "")[0] === "%" ? "%" : "";
  const legs = corridorLegs(hist.corridor);
  if (legs.length > 1) {
    // corridor indicators get the whole corridor, not just their own series
    timeChart(d3.select("#heroChart"), {
      series: legs,
      band: corridorBand(legs),
      curve: d3.curveStepAfter,
      refLines: hist.ref || [],
      yFormat: v => fmtNum(v, kpi.decimals) + pctSuffix,
    });
    return;
  }
  timeChart(d3.select("#heroChart"), {
    series: [{ name: kpi.label, color: hist.color || kpi.color, values: hist.data.map(o => [o.date, o.value]), area: true }],
    refLines: hist.ref || [],
    yFormat: v => fmtNum(v, kpi.decimals) + pctSuffix,
  });
}

/* ---------------------------------------------------------------- time chart */
function timeChart(sel, cfg) {
  sel.html("");
  const { width, height } = chartSize(sel);
  const margin = { top: 18, right: 18, bottom: 30, left: 46 };
  const iw = width - margin.left - margin.right;
  const ih = height - margin.top - margin.bottom;

  const svg = sel.append("svg").attr("width", width).attr("height", height);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const series = cfg.series.map(s => ({
    name: s.name, color: s.color, area: s.area, dashed: s.dashed, width: s.width,
    pts: s.values.map(d => [parseISO(d[0]), +d[1]]).filter(p => isFinite(p[1])),
  }));

  const allDates = series.flatMap(s => s.pts.map(p => p[0]));
  const xExtent = d3.extent(allDates);
  const x = d3.scaleTime().domain(xExtent).range([0, iw]);

  let yMin = Infinity, yMax = -Infinity;
  series.forEach(s => s.pts.forEach(p => { yMin = Math.min(yMin, p[1]); yMax = Math.max(yMax, p[1]); }));
  (cfg.refLines || []).forEach(r => { yMin = Math.min(yMin, r.value); yMax = Math.max(yMax, r.value); });
  if (cfg.yDomain) { yMin = cfg.yDomain[0]; yMax = cfg.yDomain[1]; }
  const pad = (yMax - yMin) * 0.08 || 1;
  const y = d3.scaleLinear().domain([yMin - pad, yMax + pad]).nice().range([ih, 0]);

  const yFmt = cfg.yFormat || (v => fmtNum(v, 2));
  const xFmt = cfg.xFormat || (d => d3.timeFormat("%Y")(d));

  // corridor ribbon: shaded area between two series, drawn under the gridlines
  // so those stay crisp. The band's curve must match the series' so its edges
  // land exactly on the dashed floor / ceiling lines (see alignStep).
  if (cfg.band) {
    const under = series.find(s => s.name === cfg.band.from);
    const over = series.find(s => s.name === cfg.band.to);
    const rows = under && over ? alignStep(under.pts, over.pts) : [];
    if (rows.length > 1) {
      g.append("path").datum(rows).attr("class", "corridor-band")
        .attr("d", d3.area().x(d => x(d[0])).y0(d => y(d[1])).y1(d => y(d[2]))
          .curve(cfg.curve || d3.curveMonotoneX))
        .attr("fill", cfg.band.color || BAND.color)
        .attr("opacity", cfg.band.opacity == null ? BAND.opacity : cfg.band.opacity)
        .attr("stroke", "none");
    }
  }

  // horizontal gridlines + y axis
  const yTicks = y.ticks(5);
  g.selectAll("line.grid").data(yTicks).join("line")
    .attr("class", "grid")
    .attr("x1", 0).attr("x2", iw)
    .attr("y1", d => y(d)).attr("y2", d => y(d))
    .attr("stroke", C.grid);
  g.selectAll("text.ytick").data(yTicks).join("text")
    .attr("class", "ytick").attr("x", -8).attr("y", d => y(d))
    .attr("dy", "0.32em").attr("text-anchor", "end")
    .attr("fill", C.faint).style("font-size", "10.5px").style("font-variant-numeric", "tabular-nums")
    .text(d => yFmt(d));

  // x axis
  const xTicks = x.ticks(cfg.xTicks || 5);
  g.selectAll("text.xtick").data(xTicks).join("text")
    .attr("class", "xtick").attr("x", d => x(d)).attr("y", ih + 18)
    .attr("text-anchor", "middle").attr("fill", C.faint).style("font-size", "10.5px")
    .text(d => xFmt(d));

  // reference lines
  (cfg.refLines || []).forEach(r => {
    g.append("line").attr("x1", 0).attr("x2", iw)
      .attr("y1", y(r.value)).attr("y2", y(r.value))
      .attr("stroke", r.color || C.faint).attr("stroke-width", 1)
      .attr("stroke-dasharray", "4 4").attr("opacity", 0.7);
    g.append("text").attr("x", iw - 4).attr("y", y(r.value) - 4)
      .attr("text-anchor", "end").attr("fill", r.color || C.faint)
      .style("font-size", "10px").text(r.label || "");
  });

  // zero line when y crosses 0
  if (y(0) > 0 && y(0) < ih && !(cfg.yDomain)) {
    g.append("line").attr("x1", 0).attr("x2", iw)
      .attr("y1", y(0)).attr("y2", y(0))
      .attr("stroke", C.border).attr("stroke-width", 1);
  }

  // series
  const line = d3.line().x(p => x(p[0])).y(p => y(p[1])).curve(cfg.curve || d3.curveMonotoneX);
  const area = d3.area().x(p => x(p[0])).y0(y(0)).y1(p => y(p[1])).curve(cfg.curve || d3.curveMonotoneX);

  series.forEach(s => {
    const path = g.append("path").datum(s.pts)
      .attr("fill", "none").attr("stroke", s.color)
      .attr("stroke-width", s.width || (s.dashed ? 1.6 : 2.2))
      .attr("stroke-dasharray", s.dashed ? "5 4" : null)
      .attr("stroke-linejoin", "round").attr("stroke-linecap", "round")
      .attr("d", line);
    if (cfg.animate !== false) {
      const len = path.node().getTotalLength();
      path.attr("stroke-dasharray", `${len} ${len}`).attr("stroke-dashoffset", len)
        .transition().duration(900).ease(d3.easeCubicOut).attr("stroke-dashoffset", 0)
        .on("end", function () { d3.select(this).attr("stroke-dasharray", s.dashed ? "5 4" : null); });
    }
    if (s.area) {
      g.insert("path", ":first-child").datum(s.pts)
        .attr("fill", s.color).attr("opacity", 0.10).attr("d", area)
        .attr("stroke", "none");
    }
  });

  // crosshair + tooltip
  const overlay = g.append("rect").attr("width", iw).attr("height", ih)
    .attr("fill", "transparent").style("pointer-events", "all");
  const focus = g.append("line").attr("class", "focus-line").attr("y1", 0).attr("y2", ih)
    .attr("opacity", 0);
  const dots = g.append("g");
  const refPts = series.map(s => ({ s, idx: 0 }));

  overlay
    .on("mousemove", function (ev) {
      const [mx] = d3.pointer(ev);
      const d0 = x.invert(mx);
      const rows = [];
      series.forEach(s => {
        const i = d3.bisector(p => p[0]).center(s.pts, d0);
        const p = s.pts[Math.max(0, Math.min(s.pts.length - 1, i))];
        rows.push({ s, p });
      });
      if (!rows.length || !rows[0].p) return;
      const date = rows[0].p[0];
      // a 31-tenor fan would otherwise produce a 31-row tooltip taller than the
      // chart, so a chart can nominate the rows worth reading (cfg.tooltipKeys)
      const shown = cfg.tooltipKeys ? rows.filter(r => cfg.tooltipKeys.includes(r.s.name)) : rows;
      focus.attr("opacity", 1).attr("x1", x(date)).attr("x2", x(date));
      dots.selectAll("circle").data(shown).join("circle")
        .attr("cx", r => x(r.p[0])).attr("cy", r => y(r.p[1]))
        .attr("r", 3.4).attr("fill", r => r.s.color).attr("stroke", "#0a0d17").attr("stroke-width", 1.4);
      const html = `<div class="tt-row"><span class="tt-label">${fmtDate(date)}</span></div>` +
        shown.map(r => `<div class="tt-row"><span class="tt-label"><span class="tt-swatch" style="background:${r.s.color}"></span>${r.s.name}</span><span class="tt-value">${yFmt(r.p[1])}</span></div>`).join("");
      showTooltip(html, ev.clientX, ev.clientY);
    })
    .on("mouseleave", () => { focus.attr("opacity", 0); dots.selectAll("circle").remove(); hideTooltip(); });

  // colour-ramp legend, for charts where colour encodes a dimension rather than
  // a series identity (drawn in the top margin, above the plot)
  if (cfg.ramp) {
    const rw = 84, rh = 7;
    const rg = svg.append("g").attr("transform", `translate(${margin.left + iw - rw - 30}, 3)`);
    const gid = `ramp-${Math.random().toString(36).slice(2)}`;
    rg.append("defs").append("linearGradient").attr("id", gid)
      .attr("x1", 0).attr("y1", 0).attr("x2", 1).attr("y2", 0)
      .selectAll("stop").data(cfg.ramp.colors).join("stop")
      .attr("offset", (d, i, a) => i / (a.length - 1)).attr("stop-color", d => d);
    rg.append("rect").attr("width", rw).attr("height", rh).attr("rx", 3.5)
      .attr("fill", `url(#${gid})`).attr("opacity", 0.9);
    rg.append("text").attr("x", -6).attr("y", rh / 2).attr("dy", "0.32em")
      .attr("text-anchor", "end").attr("fill", C.faint).style("font-size", "10px")
      .text(cfg.ramp.from);
    rg.append("text").attr("x", rw + 6).attr("y", rh / 2).attr("dy", "0.32em")
      .attr("fill", C.faint).style("font-size", "10px").text(cfg.ramp.to);
  }
}

/* ---------------------------------------------------------------- page init */
let state = { curve: null, secondary: null };

async function init() {
  try {
    const [snapshot, curve, meta] = await Promise.all([
      getJSON("/api/snapshot"),
      getJSON("/api/yield-curve"),
      getJSON("/api/meta"),
    ]);
    state.curve = curve;
    $("#footBuild").textContent = meta.warehouse_build
      ? `warehouse build ${fmtDate(meta.warehouse_build)}`
      : "";

    renderKpis(snapshot);
    renderHero(kpiData.find(k => k.id === selectedId));
    renderCurveSnapshot(curve);
  } catch (err) {
    console.error(err);
    const g = $("#kpiGrid");
    g.innerHTML = `<div class="card" style="grid-column:1/-1">Failed to load data — is the API up? (${err.message})</div>`;
    return;
  }

  // secondary charts (independent fetches, cached for responsive re-render)
  try {
    const [hicp, core, dfr, mro, mlf, unrate, fx, gas] = await Promise.all([
      getJSON("/api/observations/ECB_HICP"),
      getJSON("/api/observations/ECB_HICP_CORE"),
      getJSON("/api/observations/ECBDFR?step=M"),
      getJSON("/api/observations/ECB_MRO?step=M"),
      getJSON("/api/observations/ECB_MLF?step=M"),
      getJSON("/api/observations/ECB_UNRATE"),
      getJSON("/api/observations/DEXUSEU?step=W"),
      getJSON("/api/observations/PNGASEUUSDM"),
    ]);
    const val = (d) => d.data.map(o => [o.date, o.value]);
    state.secondary = {
      hicp: val(hicp), core: val(core),
      dfr: val(dfr), mro: val(mro), mlf: val(mlf),
      unrate: val(unrate), fx: val(fx), gas: val(gas),
    };
    renderSecondary(state.secondary);
  } catch (err) {
    console.error("secondary charts:", err);
  }
}

function renderSecondary(s) {
  renderInflation(s.hicp, s.core);
  renderCorridor(s.dfr, s.mro, s.mlf);
  renderBundYields(state.curve);   // the term structure rides on the curve payload
  renderUnemployment(s.unrate);
  renderFx(s.fx);
  renderEnergy(s.gas);
}

// responsive re-render (debounced): keeps tiles + hero chart filling the viewport
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    const kpi = kpiData.find(k => k.id === selectedId);
    if (kpi) renderHero(kpi);
    if (state.curve) renderCurveSnapshot(state.curve);
    if (state.secondary) renderSecondary(state.secondary);
  }, 160);
});

/* Yield-curve snapshot — a cross-section, not a time series. Every tenor is a
   real Bundesbank BBSIS term-structure observation, so nothing here is
   interpolated. The maturity axis is log-scaled because 0.5y..30y on a linear
   axis would squeeze the whole informative short end (0.5-5y) into the first
   15% of the width. The dots are the observed on-the-run bond yields (BBSSY):
   a different measure from the fitted curve, drawn for comparison. */
function renderCurveSnapshot(curve) {
  registerChart("curveSnapshot", () => drawCurveSnapshot(curve));
}

function drawCurveSnapshot(curve) {
  const pts = (rows) => (rows || []).filter(d => d.value != null).map(d => [d.maturity, d.value]);
  const latest = pts(curve.latest);
  const prev = pts(curve.one_year_ago_curve);
  const observed = pts(curve.latest_anchors);

  const el = d3.select("#curveSnapshot");
  el.html("");
  const { width, height } = chartSize(el);
  const margin = { top: 26, right: 20, bottom: 32, left: 46 };
  const iw = width - margin.left - margin.right, ih = height - margin.top - margin.bottom;
  const svg = el.append("svg").attr("width", width).attr("height", height);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLog().domain(d3.extent(latest.concat(prev).map(d => d[0]))).range([0, iw]);
  const vals = latest.concat(prev).map(d => d[1]);
  const ymin = d3.min(vals), ymax = d3.max(vals);
  const pad = (ymax - ymin) * 0.1 || 0.2;
  const y = d3.scaleLinear().domain([ymin - pad, ymax + pad]).nice().range([ih, 0]);

  g.selectAll("line.grid").data(y.ticks(5)).join("line").attr("class", "grid")
    .attr("x1", 0).attr("x2", iw).attr("y1", d => y(d)).attr("y2", d => y(d)).attr("stroke", C.grid);
  g.selectAll("text.ytick").data(y.ticks(5)).join("text")
    .attr("x", -8).attr("y", d => y(d)).attr("dy", "0.32em").attr("text-anchor", "end")
    .attr("fill", C.faint).style("font-size", "10.5px").text(d => d + "%");

  g.selectAll("text.xtick").data([[0.5, "6M"], [1, "1Y"], [2, "2Y"], [5, "5Y"], [10, "10Y"], [20, "20Y"], [30, "30Y"]])
    .join("text").attr("x", d => x(d[0])).attr("y", ih + 18)
    .attr("text-anchor", "middle").attr("fill", C.faint).style("font-size", "10px")
    .text(d => d[1]);

  const line = d3.line().x(d => x(d[0])).y(d => y(d[1])).curve(d3.curveMonotoneX);
  // fill down to the axis floor: y(0) sits well outside the plot box (yields are
  // nowhere near 0%) and would bleed out over the tick labels
  const area = d3.area().x(d => x(d[0])).y0(ih).y1(d => y(d[1])).curve(d3.curveMonotoneX);

  // one year ago (dashed, muted)
  g.append("path").datum(prev).attr("d", line).attr("fill", "none")
    .attr("stroke", C.faint).attr("stroke-width", 1.8).attr("stroke-dasharray", "5 4");
  // today
  g.append("path").datum(latest).attr("d", area).attr("fill", C.gold).attr("opacity", 0.10).attr("stroke", "none");
  g.append("path").datum(latest).attr("d", line).attr("fill", "none")
    .attr("stroke", C.gold).attr("stroke-width", 2.4).attr("stroke-linejoin", "round");
  // observed bond yields
  g.selectAll("circle").data(observed).join("circle")
    .attr("cx", d => x(d[0])).attr("cy", d => y(d[1]))
    .attr("r", 4).attr("fill", C.gold2).attr("stroke", "#0a0d17").attr("stroke-width", 1.5);

  // legend
  const leg = svg.append("g").attr("transform", `translate(${margin.left}, 12)`);
  const l1 = leg.append("g");
  l1.append("line").attr("x1", 0).attr("x2", 16).attr("y1", 0).attr("y2", 0)
    .attr("stroke", C.gold).attr("stroke-width", 2.4);
  l1.append("text").attr("x", 22).attr("y", 3).attr("fill", C.muted).style("font-size", "10.5px").text("today");
  const l2 = leg.append("g").attr("transform", "translate(80,0)");
  l2.append("line").attr("x1", 0).attr("x2", 16).attr("y1", 0).attr("y2", 0)
    .attr("stroke", C.faint).attr("stroke-width", 1.8).attr("stroke-dasharray", "5 4");
  l2.append("text").attr("x", 22).attr("y", 3).attr("fill", C.muted).style("font-size", "10.5px").text("1y ago");
  const l3 = leg.append("g").attr("transform", "translate(160,0)");
  l3.append("circle").attr("cx", 4).attr("cy", 0).attr("r", 4)
    .attr("fill", C.gold2).attr("stroke", "#0a0d17").attr("stroke-width", 1.4);
  l3.append("text").attr("x", 22).attr("y", 3).attr("fill", C.muted).style("font-size", "10.5px")
    .text("observed 2/5/10Y");
}

function renderInflation(hicp, core) {
  chart("inflation", {
    series: [
      { name: "HICP headline", color: C.gold, values: hicp, area: true },
      { name: "HICP core", color: C.blue, values: core },
    ],
    refLines: [{ value: 2, label: "2% target", color: C.faint }],
    yFormat: v => fmtNum(v, 1) + "%",
  });
}
function renderCorridor(dfr, mro, mlf) {
  const legs = corridorLegs([
    { role: "floor", values: dfr },
    { role: "mid", values: mro },
    { role: "ceiling", values: mlf },
  ]);
  chart("corridor", {
    series: legs,
    band: corridorBand(legs),
    curve: d3.curveStepAfter, // policy rates hold, then step — never ramp
    yFormat: v => fmtNum(v, 1) + "%",
  });
}
/* The whole term structure through time: one line per BBSIS tenor, colour-ramped
   from the short end (cool) to the long end (warm). The card used to carry only
   the three observed BBSSY quotes; the fitted curve is real at every tenor, so
   the fan shows the curve's shape through the cycle — an inversion reads as the
   short-end lines crossing above the long end.

   Reads straight off the curve payload's monthly `surface` (314 month-ends × 31
   tenors), which the page already fetches for the snapshot card — no extra
   requests, and every point comes from one consistent vintage. */
function renderBundYields(curve) {
  if (!curve) return;
  const ramp = d3.scaleSequential(d3.interpolateRgbBasis(RAMP)).domain([0.5, 30]);
  const series = curve.tenors.map((t, j) => ({
    name: t.label,
    color: ramp(t.maturity),
    width: 1.2,   // 31 lines: any thicker and the fan becomes a slab
    values: curve.dates
      .map((d, i) => [d, curve.surface[i][j]])
      .filter(p => p[1] != null),   // +null would coerce to a 0% line
  })).filter(s => s.values.length > 1);

  chart("bundYields", {
    series,
    tooltipKeys: ["6M", "1Y", "2Y", "5Y", "10Y", "30Y"],
    ramp: { from: "6M", to: "30Y", colors: RAMP },
    animate: false,   // 31 concurrent draw-on transitions is just noise
    yFormat: v => fmtNum(v, 2) + "%",
    curve: d3.curveMonotoneX,
  });
}
function renderUnemployment(unrate) {
  chart("unemployment", {
    series: [{ name: "EA unemployment", color: C.rose, values: unrate, area: true }],
    yFormat: v => fmtNum(v, 1) + "%",
  });
}
function renderFx(fx) {
  chart("fx", {
    series: [{ name: "EUR/USD", color: C.blue, values: fx, area: true }],
    yFormat: v => fmtNum(v, 3),
  });
}
function renderEnergy(gas) {
  chart("energy", {
    series: [{ name: "EU natural gas (USD/mmBtu)", color: C.teal, values: gas, area: true }],
    yFormat: v => fmtNum(v, 1),
  });
}

init();
