"""Data Ops — selective, interactive refresh of warehouse series.

Everything on this page goes through the owner-only API (`POST /ops/...`), which
queues a **Dagster** run; Dagster ingests the series and runs the dedicated dbt
transform so the fresh rows reach the marts the other pages read.

* pick a series → **Refresh this series** (one series, ingest + dbt)
* **Update everything** → full ingest + full dbt build, regardless of the 06:00
  schedule
* live step log + status while a run executes, with a link into the Dagster UI

The page never touches Postgres or Dagster directly (no ingest/dbt imports): it
is a client of the API, exactly like a remote caller would be.
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timezone

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://api:8000").rstrip("/")
OPS_KEY = os.getenv("OPS_API_KEY", "")
DAGSTER_UI = os.getenv("DAGSTER_UI_URL", "http://127.0.0.1:3000").rstrip("/")

POLL_SECONDS = 2.0
POLL_TIMEOUT_S = float(os.getenv("OPS_POLL_TIMEOUT", "900"))

st.set_page_config(page_title="Data Ops — refresh series", page_icon="🔄", layout="wide")

C_BLUE, C_GREEN, C_AMBER, C_RED, C_SLATE = (
    "#2563eb", "#059669", "#d97706", "#dc2626", "#64748b")

STATUS_COLOR = {
    "SUCCESS": C_GREEN, "FAILURE": C_RED, "CANCELED": C_SLATE,
    "QUEUED": C_AMBER, "STARTED": C_BLUE, "STARTING": C_BLUE,
    "NOT_STARTED": C_SLATE, "CANCELING": C_AMBER, "MANAGED": C_SLATE,
}

TODAY = datetime.now(timezone.utc).date()


# --------------------------------------------------------------------------- #
# API client (thin)
# --------------------------------------------------------------------------- #
class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def _request(method: str, path: str, *, params: dict | None = None,
             timeout: float = 30.0) -> dict | list:
    url = f"{API_BASE}{path}"
    try:
        resp = requests.request(
            method, url, params=params, timeout=timeout,
            headers={"X-Ops-Key": OPS_KEY, "Accept": "application/json"},
        )
    except requests.RequestException as exc:
        raise ApiError(0, f"cannot reach the API at {API_BASE}: {exc}") from exc
    if resp.status_code >= 400:
        detail = resp.text[:400]
        try:
            body = resp.json()
            detail = body.get("detail") or body.get("message") or detail
            if isinstance(detail, list):  # pydantic validation error
                detail = "; ".join(str(d.get("msg", d)) for d in detail)
        except ValueError:
            pass
        raise ApiError(resp.status_code, str(detail))
    return resp.json()


def api_health() -> dict:
    return _request("GET", "/ops/health", timeout=10.0)


def api_series() -> list[dict]:
    return _request("GET", "/ops/series", timeout=30.0).get("data", [])


def api_refresh(series_id: str) -> dict:
    return _request("POST", f"/ops/refresh/{series_id}", timeout=30.0)


def api_refresh_all() -> dict:
    return _request("POST", "/ops/refresh-all", timeout=30.0)


def api_run(run_id: str, events: bool = True) -> dict:
    return _request("GET", f"/ops/runs/{run_id}", params={"events": events}, timeout=30.0)


def api_runs(limit: int = 12) -> list[dict]:
    return _request("GET", "/ops/runs", params={"limit": limit}, timeout=30.0)


def api_terminate(run_id: str) -> dict:
    return _request("POST", f"/ops/runs/{run_id}/terminate", timeout=30.0)


# --------------------------------------------------------------------------- #
# Presentation helpers
# --------------------------------------------------------------------------- #
def age_label(v) -> str:
    """Human age of a date, relative to today (UTC)."""
    if not v:
        return "never"
    try:
        d = date.fromisoformat(str(v)[:10])
    except ValueError:
        return str(v)
    days = (TODAY - d).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 45:
        return f"{days} days ago"
    return f"~{days // 30} months ago"


def status_badge(status: str) -> str:
    colour = STATUS_COLOR.get(status, C_SLATE)
    return (
        f"<span style='background:{colour};color:#fff;padding:2px 10px;"
        f"border-radius:10px;font-size:0.75rem;font-weight:600'>{status}</span>"
    )


def step_table(events: list[dict]) -> pd.DataFrame:
    """One row per event, newest last — the run's live step log."""
    keep = {"ExecutionStepStart", "ExecutionStepSuccess", "ExecutionStepFailure",
            "RunFailure", "Engine", "StepMaterialization", "AssetMaterializationPlanned",
            "LogMessage"}
    rows = []
    for e in events:
        if e.get("type") not in keep:
            continue
        msg = e.get("message") or ""
        level = (e.get("level") or "").upper()
        if e.get("type") == "LogMessage" and level not in ("ERROR", "WARNING"):
            continue
        rows.append({
            "time": (e.get("timestamp") or "")[11:19],
            "step": e.get("step") or "",
            "event": e.get("type") or "",
            "message": msg[:220],
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
st.session_state.setdefault("run_id", None)
st.session_state.setdefault("run_label", None)
st.session_state.setdefault("polling", False)
st.session_state.setdefault("finished_run", None)
st.session_state.setdefault("queued", [])       # series queued for "update stale"
st.session_state.setdefault("queue_total", 0)
st.session_state.setdefault("queue_done", 0)


def start_run(submit, label: str) -> None:
    try:
        resp = submit()
    except ApiError as exc:
        st.error(f"Could not queue the run — {exc}")
        return
    st.session_state.update(
        run_id=resp["run_id"], run_label=label, polling=True, finished_run=None)
    st.rerun()


# --------------------------------------------------------------------------- #
# Header + preflight
# --------------------------------------------------------------------------- #
st.title("🔄 Data Ops")
st.caption(
    "Selectively pull the newest version of a series and rebuild its dbt transform, "
    "or kick off the whole pipeline. Every action queues a **Dagster** run — the "
    "orchestrator stays the only writer."
)

if not OPS_KEY:
    st.error(
        "`OPS_API_KEY` is not set in this dashboard container, so the owner-only "
        "`/ops` endpoints will reject every call. Set it in `.env` and recreate the "
        "`api` and `dashboard` services."
    )

try:
    health = api_health()
    dg_health = health.get("dagster", {})
    api_ok, dg_ok = True, bool(dg_health.get("reachable"))
except ApiError as exc:
    health, dg_health, api_ok, dg_ok = {}, {}, False, False
    st.error(f"Ops API not usable: {exc}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ops API", "reachable" if api_ok else "unreachable")
c2.metric("Dagster", "reachable" if dg_ok else "unreachable")
c3.metric("API base", API_BASE)
c4.metric("Dagster UI", "linked" if dg_ok else "—")
if dg_ok:
    st.caption(
        f"Dagster webserver `{dg_health.get('url')}` · [open the Dagster UI]({DAGSTER_UI}) "
        "for full run history and logs."
    )
elif api_ok:
    st.warning(
        f"The ops API is up but cannot reach Dagster: {dg_health.get('error', 'unknown')}. "
        "Check that the `dagster-webserver` service is running."
    )

if not (api_ok and dg_ok):
    st.stop()

# --------------------------------------------------------------------------- #
# Catalog + freshness
# --------------------------------------------------------------------------- #
try:
    series = api_series()
except ApiError as exc:
    st.error(f"Could not load the series catalog: {exc}")
    st.stop()

catalog = pd.DataFrame(series)
if catalog.empty:
    st.warning("No series are configured in `ingest.config.SERIES`.")
    st.stop()

fresh = catalog.copy()
fresh["age_days"] = fresh["last_obs_date"].map(
    lambda v: (TODAY - date.fromisoformat(str(v)[:10])).days if v else None)
# "stale" = no observation, or nothing newer than a week (daily-ish cadence).
fresh["stale"] = fresh["age_days"].isna() | (fresh["age_days"] > 7)

st.subheader("1 · What the warehouse currently holds")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Series configured", f"{len(fresh):,}")
m2.metric("In the warehouse", f"{int(fresh['in_warehouse'].sum()):,}")
m3.metric("Stale (> 7 days)", f"{int(fresh['stale'].sum()):,}")
newest = fresh["last_obs_date"].dropna().max()
m4.metric("Newest observation", str(newest)[:10] if newest else "—")

with st.expander("Series freshness table", expanded=False):
    fc1, fc2, fc3 = st.columns([2, 2, 1])
    sources = sorted(fresh["source"].unique())
    pick_sources = fc1.multiselect("Source", sources, default=sources)
    freqs = sorted(fresh["frequency"].dropna().unique())
    pick_freqs = fc2.multiselect("Frequency", freqs, default=freqs)
    only_stale = fc3.checkbox("Only stale", value=False)

    view = fresh[fresh["source"].isin(pick_sources) & fresh["frequency"].isin(pick_freqs)]
    if only_stale:
        view = view[view["stale"]]
    show = view[["series_id", "title", "source", "frequency", "last_obs_date",
                 "age_days", "n_obs", "stale"]].copy()
    show["last_obs_date"] = show["last_obs_date"].fillna("never")
    show = show.rename(columns={
        "series_id": "series", "last_obs_date": "last observation",
        "age_days": "age (days)", "n_obs": "observations", "stale": "stale",
        "title": "title", "source": "source", "frequency": "freq"})
    st.dataframe(show, width="stretch", hide_index=True,
                 column_config={"stale": st.column_config.CheckboxColumn("stale")})
    st.caption(
        f"{len(view):,} of {len(fresh):,} series shown. "
        "A series is marked stale when it has no observation, or none newer than 7 days."
    )

# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
st.subheader("2 · Refresh")

a1, a2 = st.columns([3, 2])

with a1:
    labels = {
        f"{r.series_id} — {r.title or r.source}".strip(" —") + f"  ({age_label(r.last_obs_date)})":
            r.series_id
        for r in fresh.sort_values(["stale", "series_id"], ascending=[False, True]).itertuples()
    }
    chosen_label = st.selectbox("Series to refresh", list(labels))
    chosen = labels[chosen_label]
    sel = fresh[fresh.series_id == chosen].iloc[0]
    st.markdown(
        f"`{chosen}` · source **{sel.source}** · {sel.frequency} · "
        f"last observation **{sel.last_obs_date or 'never'}** ({age_label(sel.last_obs_date)}) · "
        f"{int(sel.n_obs) if pd.notna(sel.n_obs) else 0:,} stored observations"
    )
    busy = st.session_state["polling"]
    if st.button(f"⬇︎ Refresh {chosen} now", type="primary", width="stretch",
                 disabled=busy):
        start_run(lambda: api_refresh(chosen), f"refresh {chosen}")
    st.caption(
        "Fetches this series from its provider into `raw.source_fetch`, then runs the "
        "dedicated dbt transform chain so the marts (and every other page) see it."
    )

with a2:
    st.markdown("**Update everything**")
    st.caption(
        "All sources (FRED, ECB, Bundesbank, ecb-watch) then the **full** dbt build — the same "
        "work as the 06:00 schedule, on demand."
    )
    if st.button("⟳ Trigger full pipeline", width="stretch", disabled=st.session_state["polling"]):
        start_run(api_refresh_all, "full pipeline refresh")

    stale_ids = list(fresh[fresh["stale"]]["series_id"])
    n_stale = len(stale_ids)
    if st.button(f"↻ Refresh all stale ({n_stale})", width="stretch",
                 disabled=st.session_state["polling"] or not n_stale):
        # Sequential single-series refreshes: each one is its own Dagster run, so
        # a failure in one does not abort the rest.
        st.session_state.update(queued=stale_ids, queue_total=n_stale, queue_done=0)
        st.rerun()
    if n_stale and st.session_state["queued"]:
        st.caption(f"Queue: {st.session_state['queue_done']}/{st.session_state['queue_total']} done.")
    if not n_stale:
        st.caption("Nothing is stale right now.")

# --------------------------- bulk queue driver ----------------------------- #
if st.session_state["queued"] and not st.session_state["polling"]:
    nxt = st.session_state["queued"][0]
    start_run(lambda: api_refresh(nxt), f"refresh {nxt} (bulk)")

# --------------------------------------------------------------------------- #
# Live run
# --------------------------------------------------------------------------- #
st.subheader("3 · Run progress")

run_id = st.session_state["run_id"]
if not run_id:
    st.info("No run in this session yet — pick a series above and hit refresh.")
else:
    label = st.session_state.get("run_label") or run_id
    try:
        run = api_run(run_id)
    except ApiError as exc:
        st.error(f"Could not read run {run_id}: {exc}")
        run = None

    if run:
        is_running = run["is_running"]
        st.markdown(
            f"{status_badge(run['status'])} &nbsp; **{label}** &nbsp;·&nbsp; "
            f"job `{run['job_name']}` · run `{run['run_id'][:8]}` · "
            f"[open in Dagster]({run.get('dagster_url') or DAGSTER_UI})",
            unsafe_allow_html=True,
        )

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Status", run["status"])
        p2.metric("Steps succeeded", run.get("steps_succeeded") or 0)
        p3.metric("Steps failed", run.get("steps_failed") or 0)
        started = run.get("start_time")
        elapsed = "—"
        if started:
            try:
                t0 = datetime.fromisoformat(started)
                t1 = datetime.fromisoformat(run["end_time"]) if run.get("end_time") \
                    else datetime.now(timezone.utc)
                elapsed = f"{(t1 - t0).total_seconds():.0f}s"
            except ValueError:
                elapsed = "—"
        p4.metric("Elapsed", elapsed)

        events = run.get("events") or []
        if events:
            st.dataframe(step_table(events), width="stretch", hide_index=True,
                         height=280)
        else:
            st.caption("No step events yet — the run may still be queued.")

        b1, b2, b3 = st.columns([1, 1, 3])
        if is_running:
            if b1.button("■ Terminate", disabled=False):
                try:
                    api_terminate(run_id)
                    st.warning("Terminate requested.")
                except ApiError as exc:
                    st.error(f"Could not terminate: {exc}")
            b2.caption("Polling every 2s …")
        else:
            if b3.button("Acknowledge & clear"):
                st.session_state.update(run_id=None, run_label=None, polling=False)
                st.rerun()

        # --- completion handling ------------------------------------------- #
        if not is_running and st.session_state["polling"]:
            st.session_state["polling"] = False
            st.session_state["finished_run"] = run["run_id"]
            if run["status"] == "SUCCESS":
                # pop this series off the bulk queue and continue
                q = st.session_state["queued"]
                if q:
                    st.session_state["queued"] = q[1:]
                    st.session_state["queue_done"] += 1
            else:
                st.session_state["queued"] = []  # stop the bulk queue on failure
            st.rerun()

        if is_running and st.session_state["polling"]:
            time.sleep(POLL_SECONDS)
            st.rerun()

    if st.session_state.get("finished_run") == run_id and run and not run["is_running"]:
        if run["status"] == "SUCCESS":
            st.success(
                f"Run finished successfully — `{label}`. The marts now include the "
                "newest data this provider returned; reload the page to see it."
            )
        else:
            st.error(
                f"Run finished with status **{run['status']}**. Open the Dagster run for "
                "the failing step's full log — usually the provider HTTP status is there."
            )
        if st.button("Reload catalog & freshness"):
            st.cache_data.clear()
            st.session_state.update(run_id=None, run_label=None, finished_run=None)
            st.rerun()

# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
with st.expander("Recent triggerable runs", expanded=False):
    try:
        hist = pd.DataFrame(api_runs(limit=15))
    except ApiError as exc:
        st.error(f"Could not list runs: {exc}")
        hist = pd.DataFrame()
    if hist.empty:
        st.caption("No runs of the triggerable jobs yet.")
    else:
        hist = hist.rename(columns={
            "run_id": "run", "job_name": "job", "status": "status",
            "start_time": "started", "end_time": "ended"})
        hist["run"] = hist["run"].str[:8]
        st.dataframe(hist[["run", "job", "status", "started", "ended"]],
                     width="stretch", hide_index=True)
