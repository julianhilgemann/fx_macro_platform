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
};

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

/* ---------------------------------------------------------------- loader */
async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}

/* ---------------------------------------------------------------- KPI tiles */
let selectedId = "de10y";
let kpiData = [];

function renderKpis(snapshot) {
  kpiData = snapshot.kpis;
  const grid = d3.select("#kpiGrid");
  grid.selectAll(".kpi").data(kpiData).join("div")
    .attr("class", "kpi")
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
  if (d.spark && d.spark.length > 1) sparkline(el, d.spark, d.color);
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
    drawHeroChart(kpi, hist);
  } catch (err) {
    console.error("hero chart:", err);
    d3.select("#heroChart").html(`<div class="surface-hint">Failed to load ${kpi.label} — ${err.message}</div>`);
  }
}

function drawHeroChart(kpi, hist) {
  const pctSuffix = (kpi.unit || "")[0] === "%" ? "%" : "";
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
    name: s.name, color: s.color, area: s.area, dashed: s.dashed,
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
      .attr("stroke-width", s.dashed ? 1.6 : 2.2)
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
      focus.attr("opacity", 1).attr("x1", x(date)).attr("x2", x(date));
      dots.selectAll("circle").data(rows).join("circle")
        .attr("cx", r => x(r.p[0])).attr("cy", r => y(r.p[1]))
        .attr("r", 3.4).attr("fill", r => r.s.color).attr("stroke", "#0a0d17").attr("stroke-width", 1.4);
      const html = `<div class="tt-row"><span class="tt-label">${fmtDate(date)}</span></div>` +
        rows.map(r => `<div class="tt-row"><span class="tt-label"><span class="tt-swatch" style="background:${r.s.color}"></span>${r.s.name}</span><span class="tt-value">${yFmt(r.p[1])}</span></div>`).join("");
      showTooltip(html, ev.clientX, ev.clientY);
    })
    .on("mouseleave", () => { focus.attr("opacity", 0); dots.selectAll("circle").remove(); hideTooltip(); });
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
    const [hicp, core, dfr, mro, mlf, de2, de5, de10, unrate, fx, gas] = await Promise.all([
      getJSON("/api/observations/ECB_HICP"),
      getJSON("/api/observations/ECB_HICP_CORE"),
      getJSON("/api/observations/ECBDFR?step=M"),
      getJSON("/api/observations/ECB_MRO?step=M"),
      getJSON("/api/observations/ECB_MLF?step=M"),
      getJSON("/api/observations/DE2Y?step=M"),
      getJSON("/api/observations/DE5Y?step=M"),
      getJSON("/api/observations/DE10Y?step=M"),
      getJSON("/api/observations/ECB_UNRATE"),
      getJSON("/api/observations/DEXUSEU?step=W"),
      getJSON("/api/observations/PNGASEUUSDM"),
    ]);
    const val = (d) => d.data.map(o => [o.date, o.value]);
    state.secondary = {
      hicp: val(hicp), core: val(core),
      dfr: val(dfr), mro: val(mro), mlf: val(mlf),
      de2: val(de2), de5: val(de5), de10: val(de10),
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
  renderBundYields(s.de2, s.de5, s.de10);
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

function renderCurveSnapshot(curve) {
  const latest = curve.latest.map(d => [d.maturity, d.value]);
  const prev = curve.one_year_ago_curve.map(d => [d.maturity, d.value]);
  const anchors = curve.latest_anchors.map(d => [d.maturity, d.value]);

  const el = d3.select("#curveSnapshot");
  el.html("");
  const { width, height } = chartSize(el);
  const margin = { top: 20, right: 20, bottom: 32, left: 46 };
  const iw = width - margin.left - margin.right, ih = height - margin.top - margin.bottom;
  const svg = el.append("svg").attr("width", width).attr("height", height);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const xs = latest.concat(prev).map(d => d[0]);
  const x = d3.scaleLinear().domain(d3.extent(xs)).range([0, iw]);
  const ymin = d3.min(latest.concat(prev).map(d => d[1])), ymax = d3.max(latest.concat(prev).map(d => d[1]));
  const pad = (ymax - ymin) * 0.1 || 0.2;
  const y = d3.scaleLinear().domain([ymin - pad, ymax + pad]).nice().range([ih, 0]);

  g.selectAll("line.grid").data(y.ticks(5)).join("line").attr("class", "grid")
    .attr("x1", 0).attr("x2", iw).attr("y1", d => y(d)).attr("y2", d => y(d)).attr("stroke", C.grid);
  g.selectAll("text.ytick").data(y.ticks(5)).join("text")
    .attr("x", -8).attr("y", d => y(d)).attr("dy", "0.32em").attr("text-anchor", "end")
    .attr("fill", C.faint).style("font-size", "10.5px").text(d => d + "%");

  const xlabels = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"];
  const xl = d3.scaleLinear().domain([0, 9]).range([0, iw]);
  g.selectAll("text.xtick").data(xlabels).join("text")
    .attr("x", (d, i) => x(curve.tenors[i].maturity)).attr("y", ih + 18)
    .attr("text-anchor", "middle").attr("fill", C.faint).style("font-size", "10px")
    .text(d => d);

  const line = d3.line().x(d => x(d[0])).y(d => y(d[1])).curve(d3.curveMonotoneX);
  const area = d3.area().x(d => x(d[0])).y0(y(0)).y1(d => y(d[1])).curve(d3.curveMonotoneX);

  // one year ago (dashed, muted)
  g.append("path").datum(prev).attr("d", line).attr("fill", "none")
    .attr("stroke", C.faint).attr("stroke-width", 1.8).attr("stroke-dasharray", "5 4");
  // today
  g.append("path").datum(latest).attr("d", area).attr("fill", C.gold).attr("opacity", 0.10).attr("stroke", "none");
  g.append("path").datum(latest).attr("d", line).attr("fill", "none")
    .attr("stroke", C.gold).attr("stroke-width", 2.4).attr("stroke-linejoin", "round");
  // anchors (real rates)
  g.selectAll("circle").data(anchors).join("circle")
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
}

function renderInflation(hicp, core) {
  timeChart(d3.select("#inflation"), {
    series: [
      { name: "HICP headline", color: C.gold, values: hicp, area: true },
      { name: "HICP core", color: C.blue, values: core },
    ],
    refLines: [{ value: 2, label: "2% target", color: C.faint }],
    yFormat: v => fmtNum(v, 1) + "%",
  });
}
function renderCorridor(dfr, mro, mlf) {
  timeChart(d3.select("#corridor"), {
    series: [
      { name: "Deposit (floor)", color: C.teal, values: dfr, area: true },
      { name: "MRO (mid)", color: C.gold, values: mro },
      { name: "Lending (ceiling)", color: C.rose, values: mlf },
    ],
    yFormat: v => fmtNum(v, 1) + "%",
  });
}
function renderBundYields(de2, de5, de10) {
  timeChart(d3.select("#bundYields"), {
    series: [
      { name: "10Y", color: C.gold, values: de10 },
      { name: "5Y", color: C.blue, values: de5 },
      { name: "2Y", color: C.violet, values: de2 },
    ],
    yFormat: v => fmtNum(v, 2) + "%",
    curve: d3.curveMonotoneX,
  });
}
function renderUnemployment(unrate) {
  timeChart(d3.select("#unemployment"), {
    series: [{ name: "EA unemployment", color: C.rose, values: unrate, area: true }],
    yFormat: v => fmtNum(v, 1) + "%",
  });
}
function renderFx(fx) {
  timeChart(d3.select("#fx"), {
    series: [{ name: "EUR/USD", color: C.blue, values: fx, area: true }],
    yFormat: v => fmtNum(v, 3),
  });
}
function renderEnergy(gas) {
  timeChart(d3.select("#energy"), {
    series: [{ name: "EU natural gas (USD/mmBtu)", color: C.teal, values: gas, area: true }],
    yFormat: v => fmtNum(v, 1),
  });
}

init();
