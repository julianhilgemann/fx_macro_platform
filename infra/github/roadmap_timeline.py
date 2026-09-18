#!/usr/bin/env python3
"""Render the roadmap as a self-contained interactive timeline (HTML).

Prototype view of research/plane-roadmap-proposal.json: every module as a bar on
a real date axis, grouped by theme, with its tickets shown as load inside.

IMPORTANT — what this does and does not claim:
  Modules carry real start/target dates. Individual tickets do NOT have their own
  dates; each inherits its module's window. So a ticket is never positioned by
  date here. Instead:
    * the BAR is the module's real schedule,
    * the CHIPS are the module's tickets ordered by priority and sized by
      estimate, i.e. effort, not timing,
    * the LOAD STRIP at the top sums estimate points of modules in flight per
      week, which is derived from the real windows and shows concurrency.

Usage:
    python roadmap_timeline.py [--out PATH] [--open]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
PROPOSAL = PROJECT_ROOT / "research" / "plane-roadmap-proposal.json"
DEFAULT_OUT = PROJECT_ROOT / "reports" / "roadmap-timeline.html"

PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
PRIORITY_COLOR = {
    "urgent": "#f85149",
    "high": "#db6d28",
    "medium": "#d29922",
    "low": "#6e7681",
    "none": "#484f58",
}
STATUS_COLOR = {
    "in-progress": "#3fb950",
    "planned": "#388bfd",
    "completed": "#8957e5",
    "paused": "#d29922",
    "cancelled": "#6e7681",
}


def iso(value: str) -> date:
    return date.fromisoformat(value)


def build_data(proposal: dict) -> dict:
    modules = proposal["modules"]
    items = proposal["work_items"]

    by_module: dict[str, list[dict]] = defaultdict(list)
    for w in items:
        by_module[w["module"]].append(w)

    # Theme -> modules, in start-date order.
    themes: dict[str, list[dict]] = defaultdict(list)
    for m in modules:
        themes[m["initiative"]].append(m)

    start = min(iso(m["start_date"]) for m in modules if m.get("start_date"))
    end = max(iso(m["target_date"]) for m in modules if m.get("target_date"))
    total_days = (end - start).days + 1

    # Concurrency: estimate points in flight per week, from the real windows.
    load: list[dict] = []
    cursor = start
    while cursor <= end:
        week_end = min(cursor + timedelta(days=6), end)
        pts = 0
        for m in modules:
            ms, mt = iso(m["start_date"]), iso(m["target_date"])
            # Window overlap with [cursor, week_end]
            if ms <= week_end and mt >= cursor:
                pts += sum(w.get("estimate_points") or 0 for w in by_module[m["name"]])
        load.append({"week": cursor.isoformat(), "points": pts})
        cursor = week_end + timedelta(days=1)

    out_modules = []
    for theme, mods in themes.items():
        for m in sorted(mods, key=lambda x: (x["start_date"], x["name"])):
            kids = sorted(
                by_module[m["name"]],
                key=lambda w: (PRIORITY_ORDER.get(w.get("priority", "none"), 9), w["name"]),
            )
            ms, mt = iso(m["start_date"]), iso(m["target_date"])
            out_modules.append(
                {
                    "theme": theme,
                    "name": m["name"],
                    "status": m.get("state", "planned"),
                    "start": m["start_date"],
                    "target": m["target_date"],
                    "left_pct": (ms - start).days / total_days * 100,
                    "width_pct": max(((mt - ms).days + 1) / total_days * 100, 0.6),
                    "days": (mt - ms).days + 1,
                    "points": sum(w.get("estimate_points") or 0 for w in kids),
                    "tickets": [
                        {
                            "name": w["name"],
                            "priority": w.get("priority", "none"),
                            "points": w.get("estimate_points") or 0,
                            "labels": w.get("labels", []),
                            "evidence": w.get("evidence", ""),
                            "desc": (w.get("description_markdown") or "").strip()[:600],
                        }
                        for w in kids
                    ],
                }
            )

    # Month gridlines. The first month is usually only partially covered (the
    # span starts mid-month), so it is clamped to 0 rather than dropped —
    # otherwise the opening days have no axis label at all.
    months: list[dict] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        offset = max((cur - start).days, 0)
        months.append({"label": cur.strftime("%b %Y"), "left_pct": offset / total_days * 100})
        cur = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_days": total_days,
        "today_pct": max(0.0, min(100.0, (date.today() - start).days / total_days * 100)),
        "months": months,
        "load": load,
        "modules": out_modules,
        "totals": {
            "tickets": len(items),
            "modules": len(modules),
            "themes": len(themes),
            "points": sum(w.get("estimate_points") or 0 for w in items),
            "by_priority": {
                k: sum(1 for w in items if (w.get("priority") or "none") == k)
                for k in ("urgent", "high", "medium", "low")
            },
            "by_status": {
                k: sum(1 for m in modules if m.get("state") == k)
                for k in ("in-progress", "planned", "completed")
            },
        },
    }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FX Macro Platform — Roadmap Timeline</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2128; --border:#30363d;
    --text:#c9d1d9; --muted:#8b949e; --dim:#6e7681;
    --urgent:#f85149; --high:#db6d28; --medium:#d29922; --low:#6e7681;
    --inprog:#3fb950; --planned:#388bfd; --done:#8957e5;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
  .wrap{max-width:1500px;margin:0 auto;padding:28px 22px 80px}
  h1{font-size:21px;margin:0 0 4px;font-weight:600}
  .sub{color:var(--muted);font-size:13px;margin-bottom:18px}
  .sub b{color:var(--text);font-weight:600}

  .kpis{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}
  .kpi{background:var(--panel);border:1px solid var(--border);border-radius:8px;
       padding:9px 13px;min-width:104px}
  .kpi .n{font-size:19px;font-weight:600;line-height:1.2}
  .kpi .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}

  .toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
  .toolbar .lbl{font-size:12px;color:var(--muted);margin-right:2px}
  button.chip{background:var(--panel);color:var(--text);border:1px solid var(--border);
       border-radius:999px;padding:4px 12px;font-size:12px;cursor:pointer;transition:.12s}
  button.chip:hover{border-color:var(--dim)}
  button.chip.on{background:#1f6feb22;border-color:#1f6feb;color:#79c0ff}

  .card{background:var(--panel);border:1px solid var(--border);border-radius:10px;
        overflow:hidden;margin-bottom:26px}
  .card h2{font-size:13px;margin:0;padding:11px 15px;border-bottom:1px solid var(--border);
           color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.05em}
  .note{padding:10px 15px;font-size:12px;color:var(--muted);border-bottom:1px solid var(--border);
        background:#0f141a}
  .note b{color:var(--text)}

  /* load strip */
  .load{display:flex;align-items:flex-end;gap:2px;height:78px;padding:10px 15px 0}
  .load .bar{flex:1;background:linear-gradient(180deg,#388bfd,#1f6feb);border-radius:2px 2px 0 0;
             min-height:2px;position:relative;cursor:default;transition:.12s}
  .load .bar:hover{filter:brightness(1.35)}
  .load-x{display:flex;justify-content:space-between;padding:0 15px 12px;
          font-size:10px;color:var(--dim)}

  /* gantt */
  .grid{position:relative;padding:0 0 6px}
  .axis{position:relative;height:26px;margin-left:var(--labelw);border-bottom:1px solid var(--border)}
  .axis .m{position:absolute;top:6px;font-size:11px;color:var(--muted);
           border-left:1px solid #21262d;padding-left:5px;height:20px;white-space:nowrap}
  .theme-row{display:flex;align-items:center;background:#12171e;border-top:1px solid var(--border);
             border-bottom:1px solid var(--border);margin-top:2px}
  .theme-row .t{font-size:11px;color:#79c0ff;font-weight:600;letter-spacing:.04em;
                padding:7px 15px;text-transform:uppercase}
  .theme-row .c{color:var(--dim);font-size:11px;margin-left:auto;padding-right:15px}

  .row{display:flex;align-items:stretch;border-bottom:1px solid #1b2027}
  .row:hover{background:#12171e}
  .row.hidden{display:none}
  .lab{width:var(--labelw);flex:0 0 var(--labelw);padding:9px 12px 9px 15px;
       border-right:1px solid var(--border)}
  .lab .nm{font-size:12.5px;line-height:1.35}
  .lab .mt{font-size:11px;color:var(--muted);margin-top:3px;display:flex;gap:8px;flex-wrap:wrap}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;
       vertical-align:middle}
  .track{position:relative;flex:1;min-height:44px}
  .track .mline{position:absolute;top:0;bottom:0;width:1px;background:#1b2027}
  .bar{position:absolute;top:11px;height:22px;border-radius:5px;cursor:pointer;
       display:flex;align-items:center;padding:0 7px;overflow:hidden;white-space:nowrap;
       font-size:11px;color:#fff;border:1px solid #ffffff22;transition:.12s}
  .bar:hover{filter:brightness(1.25);box-shadow:0 0 0 2px #ffffff22}
  .bar .bt{font-weight:600;font-size:11px;overflow:hidden;text-overflow:ellipsis}
  .bar.dim{opacity:.22}
  .today{position:absolute;top:0;bottom:0;width:2px;background:#f85149;z-index:5;pointer-events:none}
  .today::after{content:"today";position:absolute;top:-16px;left:-14px;font-size:9px;
                color:#f85149;letter-spacing:.05em}

  /* tickets */
  .tk{display:none;padding:4px 0 12px calc(var(--labelw) + 2px)}
  .tk.open{display:block}
  .tklist{display:flex;flex-wrap:wrap;gap:6px;padding:6px 0 0}
  .tkchip{display:flex;align-items:center;gap:6px;background:var(--panel2);
          border:1px solid var(--border);border-radius:6px;padding:4px 9px;font-size:11.5px;
          cursor:pointer;max-width:100%}
  .tkchip:hover{border-color:var(--dim);background:#22272e}
  .tkchip .p{width:6px;height:6px;border-radius:50%;flex:0 0 6px}
  .tkchip .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:430px}
  .tkchip .e{color:var(--muted);font-size:10.5px;flex:0 0 auto}
  .detail{display:none;margin-top:8px;background:#0f141a;border:1px solid var(--border);
          border-radius:8px;padding:12px 14px;font-size:12.5px;max-width:940px}
  .detail.open{display:block}
  .detail h4{margin:0 0 6px;font-size:13px}
  .detail .meta{color:var(--muted);font-size:11px;margin-bottom:8px;display:flex;gap:12px;flex-wrap:wrap}
  .detail pre{white-space:pre-wrap;word-wrap:break-word;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;
              color:#adbac7;margin:0;max-height:280px;overflow:auto}
  .lg{display:flex;gap:16px;flex-wrap:wrap;font-size:11.5px;color:var(--muted);padding:10px 15px;
      border-top:1px solid var(--border)}
  .lg span{display:flex;align-items:center;gap:6px}
</style></head><body><div class="wrap">
<h1>FX Macro Platform — Roadmap Timeline</h1>
<div class="sub">__SUBTITLE__</div>
<div class="kpis">__KPIS__</div>

<div class="card">
  <h2>Concurrent load — estimate points in flight per week</h2>
  <div class="note">Derived from the real module windows: for each week, the summed
  estimates of every module whose start→target range covers it. Peaks are weeks where
  several modules run at once.</div>
  <div class="load" id="load"></div>
  <div class="load-x"><span>__START__</span><span>__END__</span></div>
</div>

<div class="card">
  <h2>Module schedule — click a bar to show its tickets</h2>
  <div class="note"><b>Modules have real dates; tickets do not.</b> Each bar is a module's
  start→target window. Tickets inherit that window, so they are listed as load inside it —
  never positioned by date. Chip length is not time.</div>
  <div class="toolbar" style="padding:12px 15px 0">
    <span class="lbl">priority</span>
    <button class="chip on" data-f="urgent">urgent</button>
    <button class="chip on" data-f="high">high</button>
    <button class="chip on" data-f="medium">medium</button>
    <button class="chip on" data-f="low">low</button>
    <span class="lbl" style="margin-left:10px">status</span>
    <button class="chip on" data-f="in-progress">in&nbsp;progress</button>
    <button class="chip on" data-f="planned">planned</button>
  </div>
  <div class="grid" id="grid"><div class="axis" id="axis"></div></div>
  <div class="lg">
    <span><i class="dot" style="background:var(--inprog)"></i>in progress</span>
    <span><i class="dot" style="background:var(--planned)"></i>planned</span>
    <span><i class="dot" style="background:var(--urgent)"></i>urgent</span>
    <span><i class="dot" style="background:var(--high)"></i>high</span>
    <span><i class="dot" style="background:var(--medium)"></i>medium</span>
    <span><i class="dot" style="background:var(--low)"></i>low</span>
  </div>
</div>
</div>
<script>
const DATA = __DATA__;
const PCOL = {urgent:'#f85149',high:'#db6d28',medium:'#d29922',low:'#6e7681',none:'#484f58'};
const SCOL = {'in-progress':'#3fb950','planned':'#388bfd','completed':'#8957e5',
              'paused':'#d29922','cancelled':'#6e7681'};

// axis
const axis = document.getElementById('axis');
DATA.months.forEach(m=>{
  const d=document.createElement('div'); d.className='m'; d.style.left=m.left_pct+'%';
  d.textContent=m.label; axis.appendChild(d);
});

// load strip
const loadEl=document.getElementById('load');
const maxPts=Math.max(...DATA.load.map(w=>w.points),1);
DATA.load.forEach(w=>{
  const b=document.createElement('div'); b.className='bar';
  b.style.height=Math.max(4,(w.points/maxPts)*100)+'%';
  b.title=`week of ${w.week} — ${w.points} points in flight`;
  loadEl.appendChild(b);
});

// rows
const grid=document.getElementById('grid');
let currentTheme=null, currentRow=null;
DATA.modules.forEach((m,i)=>{
  if(m.theme!==currentTheme){
    currentTheme=m.theme;
    const tr=document.createElement('div'); tr.className='theme-row';
    const cnt=DATA.modules.filter(x=>x.theme===m.theme);
    tr.innerHTML=`<div class="t">${m.theme}</div>
      <div class="c">${cnt.length} modules · ${cnt.reduce((a,b)=>a+b.tickets.length,0)} tickets ·
      ${cnt.reduce((a,b)=>a+b.points,0)} pts</div>`;
    grid.appendChild(tr);
  }
  const row=document.createElement('div');
  row.className='row'; row.dataset.prio=m.tickets.map(t=>t.priority).join(',');
  row.dataset.status=m.status;
  const pts=m.tickets.reduce((a,b)=>a+b.points,0);
  row.innerHTML=`<div class="lab">
      <div class="nm">${m.name}</div>
      <div class="mt"><span><i class="dot" style="background:${SCOL[m.status]||'#666'}"></i>${m.status}</span>
        <span>${m.start} → ${m.target}</span><span>${m.days}d</span>
        <span>${m.tickets.length} tickets · ${pts} pts</span></div>
    </div>
    <div class="track"></div>`;
  const track=row.querySelector('.track');
  DATA.months.forEach(mm=>{
    const l=document.createElement('div'); l.className='mline'; l.style.left=mm.left_pct+'%';
    track.appendChild(l);
  });
  const bar=document.createElement('div');
  bar.className='bar'; bar.style.left=m.left_pct+'%'; bar.style.width=m.width_pct+'%';
  bar.style.background=(SCOL[m.status]||'#388bfd')+'cc';
  bar.innerHTML=`<span class="bt">${m.tickets.length} tickets · ${pts} pts</span>`;
  bar.title=`${m.name}\n${m.start} → ${m.target} (${m.days} days)\n${m.tickets.length} tickets, ${pts} points`;
  track.appendChild(bar);
  grid.appendChild(row);

  const tk=document.createElement('div'); tk.className='tk';
  const list=document.createElement('div'); list.className='tklist';
  m.tickets.forEach(t=>{
    const chip=document.createElement('div'); chip.className='tkchip'; chip.dataset.prio=t.priority;
    chip.innerHTML=`<i class="p" style="background:${PCOL[t.priority]||'#484f58'}"></i>
      <span class="n">${t.name.replace(/</g,'&lt;')}</span>
      <span class="e">${t.points}p</span>`;
    const det=document.createElement('div'); det.className='detail';
    det.innerHTML=`<h4>${t.name.replace(/</g,'&lt;')}</h4>
      <div class="meta"><span>priority: <b style="color:${PCOL[t.priority]}">${t.priority}</b></span>
        <span>estimate: <b>${t.points}</b> pts</span>
        <span>module: ${m.name}</span>
        <span>labels: ${(t.labels||[]).join(', ')||'—'}</span>
        <span>evidence: ${(t.evidence||'—').replace(/</g,'&lt;')}</span></div>
      <pre>${(t.desc||'(no description)').replace(/</g,'&lt;')}</pre>`;
    chip.onclick=()=>{const o=det.classList.contains('open');
      document.querySelectorAll('.detail.open').forEach(d=>d.classList.remove('open'));
      if(!o){det.classList.add('open');}};
    const holder=document.createElement('div');
    holder.appendChild(chip); holder.appendChild(det);
    list.appendChild(holder);
  });
  tk.appendChild(list);
  grid.appendChild(tk);

  bar.onclick=()=>tk.classList.toggle('open');
});

// today marker
document.querySelectorAll('.track').forEach(t=>{
  const el=document.createElement('div'); el.className='today';
  el.style.left=DATA.today_pct+'%'; t.appendChild(el);
});

// filters
const active={urgent:true,high:true,medium:true,low:true,'in-progress':true,planned:true};
document.querySelectorAll('button.chip').forEach(btn=>{
  btn.onclick=()=>{
    const f=btn.dataset.f; active[f]=!active[f]; btn.classList.toggle('on',active[f]);
    document.querySelectorAll('.row').forEach(row=>{
      const prios=(row.dataset.prio||'').split(',');
      const pOk=prios.some(p=>active[p]);
      const sOk=active[row.dataset.status]!==false && (row.dataset.status!=='planned'||active.planned)
                 && (row.dataset.status!=='in-progress'||active['in-progress']);
      row.classList.toggle('hidden', !(pOk&&sOk));
    });
    // ticket chips within an open module
    document.querySelectorAll('.tkchip').forEach(c=>{
      c.style.display=active[c.dataset.prio]?'':'none';
    });
  };
});
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--open", action="store_true", help="open the result in a browser")
    args = ap.parse_args()

    proposal = json.loads(PROPOSAL.read_text())
    data = build_data(proposal)
    t = data["totals"]

    kpis = [
        (t["tickets"], "tickets"),
        (t["modules"], "modules"),
        (t["themes"], "themes"),
        (t["points"], "points"),
        (t["by_priority"]["urgent"], "urgent"),
        (t["by_status"]["in-progress"], "in progress"),
        (t["by_status"]["planned"], "planned"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="n">{n}</div><div class="l">{l}</div></div>' for n, l in kpis
    )
    subtitle = (
        f"<b>{data['start']}</b> → <b>{data['end']}</b> · {data['total_days']} days · "
        f"{t['tickets']} tickets across {t['modules']} modules and {t['themes']} themes · "
        f"{t['points']} estimated points"
    )

    page = (
        PAGE.replace("__DATA__", json.dumps(data))
        .replace("__KPIS__", kpi_html)
        .replace("__SUBTITLE__", subtitle)
        .replace("__START__", data["start"])
        .replace("__END__", data["end"])
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page)
    print(f"wrote {args.out}  ({args.out.stat().st_size / 1024:.0f} KB)")
    print(f"  {data['start']} → {data['end']} ({data['total_days']} days)")
    print(f"  {len(data['modules'])} modules, {t['tickets']} tickets, {t['points']} points")
    peak = max(data["load"], key=lambda w: w["points"])
    print(f"  peak concurrency: week of {peak['week']} — {peak['points']} points in flight")
    if args.open:
        import webbrowser

        webbrowser.open(f"file://{args.out}")


if __name__ == "__main__":
    main()
