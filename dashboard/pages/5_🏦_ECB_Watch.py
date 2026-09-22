"""ECB Watch — market-implied probabilities for ECB rate decisions.

Mirrors the reference tool (ecb-watch.eu): pick a Governing Council meeting and
read the market-implied distribution of the deposit facility rate afterwards, as
a bar chart plus a by-meeting probability table.

Two engines are shown side by side, and that is the point of the page:

* **local (official)** — ``marts.fct_ecb_meeting_probabilities``, built in dbt
  from the ECB's own MMSR euro OIS bucket curve. Free and official, but the
  input is bucket averages that lag live pricing by weeks, so the output is
  indicative.
* **ecb-watch** — the third-party feed, which prices *dated €STR futures*. This
  is the trade-accurate number, ingested purely so the local engine can be
  scored against it (``marts.fct_ecb_probability_crosscheck``).

Everything analytical happens in dbt; this page is presentation only, and reads
the warehouse as the SELECT-only ``platform_reader`` role.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import (
    load_ecb_probabilities,
    load_ecb_probability_crosscheck,
    load_ecb_short_rate_snapshot,
    load_observations,
)

st.set_page_config(
    page_title="ECB Watch — implied rate probabilities",
    page_icon="🏦",
    layout="wide",
)

NAVY = "#002b7f"   # the reference tool's bar colour
GREY = "#9aa3b2"
AMBER = "#d97706"
RED = "#dc2626"

SHORT_RATE_LABELS = {
    "ECB_ESTR": "€STR (overnight)",
    "ECB_ESTR_1W": "€STR compounded 1W",
    "ECB_ESTR_1M": "€STR compounded 1M",
    "ECB_ESTR_3M": "€STR compounded 3M",
    "ECB_ESTR_6M": "€STR compounded 6M",
    "ECB_ESTR_12M": "€STR compounded 12M",
    "ECB_ESTR_VOL": "€STR volume (EUR mn)",
    "ECB_ESTR_BANKS": "€STR active banks",
    "ECB_DFR": "ECB deposit facility rate",
}


def pct(x: float, digits: int = 1) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return "—"
    return "—" if pd.isna(f) else f"{f * 100:.{digits}f}%"


def rate(x: float) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return "—"
    return "—" if pd.isna(f) else f"{f:.2f}%"


@st.cache_data(ttl=300, show_spinner=False)
def _probabilities() -> pd.DataFrame:
    return load_ecb_probabilities()


@st.cache_data(ttl=300, show_spinner=False)
def _crosscheck() -> pd.DataFrame:
    return load_ecb_probability_crosscheck()


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot() -> pd.DataFrame:
    return load_ecb_short_rate_snapshot()


@st.cache_data(ttl=300, show_spinner=False)
def _estr_history(series_id: str) -> pd.DataFrame:
    return load_observations(series_id)


def _rate_columns(*frames: pd.DataFrame) -> list[float]:
    cols: set[float] = set()
    for df in frames:
        if not df.empty:
            cols.update(df["scenario_rate"].dropna().tolist())
    return sorted(cols)


def _distribution(df: pd.DataFrame, meeting: pd.Timestamp) -> pd.Series:
    """scenario_rate -> probability for one meeting."""
    sub = df[df["meeting_date"] == meeting]
    return sub.set_index("scenario_rate")["probability"]


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
probs = _probabilities()
cross = _crosscheck()
snap = _snapshot()

st.title("🏦 ECB Watch")
st.caption("Market-implied probabilities for ECB interest rate decisions")

if probs.empty:
    st.warning(
        "`marts.fct_ecb_meeting_probabilities` is empty. Land the ECB OIS series "
        "and run the dbt build first:\n\n"
        "```\ndocker compose exec dagster-daemon dagster asset materialize "
        "--select raw_ecb raw_ecbwatch fx_macro_dbt_assets\n```"
    )
    st.stop()

probs = probs.sort_values("meeting_date")
meetings = sorted(probs["meeting_date"].unique())
current_rate = float(probs["current_rate"].iloc[0])
curve_as_of = pd.Timestamp(probs["curve_as_of"].iloc[0])
staleness = int(probs["staleness_days"].iloc[0])

# --------------------------------------------------------------------------- #
# Header strip — the reference tool's "Current Deposit Facility Rate" block
# --------------------------------------------------------------------------- #
h1, h2, h3, h4 = st.columns(4)
h1.metric("Current deposit facility rate", rate(current_rate))

estr_row = snap[snap["series_id"] == "ECB_ESTR"] if not snap.empty else pd.DataFrame()
h2.metric(
    "€STR (latest fixing)",
    rate(estr_row["value"].iloc[0]) if not estr_row.empty else "—",
    help="Euro short-term rate — the euro risk-free overnight rate (ECB EST dataset).",
)

h3.metric("OIS curve as of", curve_as_of.strftime("%d %b %Y"))
h4.metric("Curve staleness", f"{staleness} days")

if staleness > 21:
    st.warning(
        f"The official OIS curve backing these probabilities is **{staleness} days "
        f"old** (last observation {curve_as_of:%d %b %Y}). MMSR publishes in coarse "
        "steps, so the local engine lags the market. Trust the bar *shape* and the "
        "ecb-watch cross-check, not the exact local number."
    )

# --------------------------------------------------------------------------- #
# Meeting selector + bar chart
# --------------------------------------------------------------------------- #
st.subheader("Implied rate probabilities")

labels = {m: pd.Timestamp(m).strftime("%B %d, %Y") for m in meetings}
choice = st.radio(
    "Meeting date",
    options=meetings,
    format_func=lambda m: labels[m],
    horizontal=True,
    label_visibility="collapsed",
)

dist = _distribution(probs, choice)
meeting_row = probs[probs["meeting_date"] == choice].iloc[0]

fig = go.Figure(
    go.Bar(
        x=[rate(r) for r in dist.index],
        y=[p * 100 for p in dist.values],
        marker_color=NAVY,
        text=[pct(p) for p in dist.values],
        textposition="inside",
        insidetextfont=dict(color="white", size=13),
        hovertemplate="%{x} → %{y:.1f}%<extra></extra>",
    )
)
fig.update_layout(
    template="plotly_white",
    height=420,
    yaxis=dict(title="Probability", range=[0, 100], ticksuffix="%"),
    xaxis=dict(title="Deposit facility rate after the meeting"),
    margin=dict(l=10, r=10, t=30, b=10),
    showlegend=False,
)
st.plotly_chart(fig, width="stretch")

# The reference tool's plain-language read-out.
no_change = float(dist.get(current_rate, 0.0))
direction = "no change"
if meeting_row["expected_change_bp"] > 1:
    direction = "a rate increase"
elif meeting_row["expected_change_bp"] < -1:
    direction = "a rate cut"
st.markdown(
    f"For the meeting on **{labels[choice]}**, the official OIS curve implies "
    f"**{pct(no_change)}** probability of **no change** "
    f"(expected move **{meeting_row['expected_change_bp']:+.0f} bp**, "
    f"i.e. {direction})."
)

# --------------------------------------------------------------------------- #
# By-meeting table — the reference tool's table, with both engines
# --------------------------------------------------------------------------- #
st.subheader("Implied rate probabilities by meeting")

rates = _rate_columns(probs)
table = pd.DataFrame(index=[labels[m] for m in meetings], columns=[rate(r) for r in rates], dtype=float)
for m in meetings:
    for r, p in _distribution(probs, m).items():
        table.loc[labels[m], rate(r)] = p * 100

st.caption(
    "Rows are meetings, columns the deposit facility rate afterwards. Values are "
    "probabilities in percent and sum to 100 across each row. "
    "**Bold** marks the most likely outcome."
)
st.dataframe(
    table.style.format("{:.1f}%", na_rep="—").apply(
        lambda row: [
            "font-weight: 700; color: #002b7f" if v == row.max() and pd.notna(v) else ""
            for v in row
        ],
        axis=1,
    ),
    width="stretch",
)

with st.expander("Per-meeting detail (expected move, curve input)"):
    detail = (
        probs.drop_duplicates("meeting_date")[
            ["meeting_date", "days_to_meeting", "expected_change_bp",
             "prob_higher_step", "period_ois_rate", "period_midpoint",
             "period_midpoint_years"]
        ]
        .rename(columns={
            "meeting_date": "Meeting",
            "days_to_meeting": "Days away",
            "expected_change_bp": "Expected move (bp)",
            "prob_higher_step": "P(upper 25bp step)",
            "period_ois_rate": "Interpolated OIS (%)",
            "period_midpoint": "Period midpoint",
            "period_midpoint_years": "Midpoint maturity (y)",
        })
        .reset_index(drop=True)
    )
    detail["P(upper 25bp step)"] = detail["P(upper 25bp step)"].map(pct)
    st.dataframe(detail, width="stretch")

# --------------------------------------------------------------------------- #
# Cross-check against the futures-based reference
# --------------------------------------------------------------------------- #
st.subheader("Cross-check against ecb-watch.eu")
st.caption(
    "ecb-watch decomposes **dated €STR futures** — the trade-accurate input no "
    "official API provides. The local engine interpolates the ECB MMSR OIS bucket "
    "curve. `Total variation` is how much probability mass must move to turn one "
    "distribution into the other: **0% = identical, 100% = opposite**."
)

if cross.empty:
    st.info(
        "No cross-check yet. Land the `ecbwatch` source and rebuild the marts to "
        "score the local engine."
    )
else:
    summary = (
        cross.groupby("meeting_date", as_index=False)
        .agg(
            total_variation_pp=("total_variation_pp", "max"),
            matched=("matched", "all"),
            source_last_updated=("source_last_updated", "first"),
            source_version=("source_version", "first"),
            source_data_sources=("source_data_sources", "first"),
        )
        .sort_values("meeting_date")
    )
    summary["Meeting"] = summary["meeting_date"].dt.strftime("%B %d, %Y")
    summary["Total variation"] = summary["total_variation_pp"].map(
        lambda v: "—" if pd.isna(v) else f"{v:.1f}%"
    )
    # "no" must mean the two engines disagree, not that the reference simply does
    # not cover this meeting — that is what a null distance marks.
    summary["All scenarios matched"] = [
        "—" if pd.isna(tv) else ("yes" if m else "no")
        for tv, m in zip(summary["total_variation_pp"], summary["matched"])
    ]
    st.dataframe(
        summary[["Meeting", "Total variation", "All scenarios matched",
                 "source_last_updated", "source_version", "source_data_sources"]],
        width="stretch",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Local (official OIS)**")
        local_tbl = pd.DataFrame(
            index=[labels[m] for m in meetings],
            columns=[rate(r) for r in rates],
            dtype=float,
        )
        for m in meetings:
            for r, p in _distribution(probs, m).items():
                local_tbl.loc[labels[m], rate(r)] = p * 100
        st.dataframe(local_tbl.style.format("{:.1f}%", na_rep="—"),
                     width="stretch")
    with c2:
        st.markdown("**ecb-watch (dated €STR futures)**")
        watch_tbl = (
            cross.assign(label=cross["meeting_date"].dt.strftime("%B %d, %Y"))
            .pivot_table(index="label", columns="scenario_rate",
                         values="ecbwatch_probability", aggfunc="sum")
            .reindex([labels[m] for m in meetings])
        )
        watch_tbl.columns = [rate(c) for c in watch_tbl.columns]
        st.dataframe((watch_tbl * 100).style.format("{:.1f}%", na_rep="—"),
                     width="stretch")

# --------------------------------------------------------------------------- #
# Short-term euro money market context
# --------------------------------------------------------------------------- #
st.subheader("Short-term euro money market")
st.caption(
    "The €STR compounded averages are **backward-looking** — they compound "
    "realised overnight fixings — so they describe where the money market is, "
    "not where it is expected to go. The forward-looking layer is the OIS curve."
)

if snap.empty:
    st.info("No €STR / OIS observations landed yet.")
else:
    ctx = snap.copy()
    ctx["Series"] = ctx["series_id"].map(SHORT_RATE_LABELS).fillna(ctx["series_id"])
    ctx["Latest"] = ctx.apply(
        lambda r: f"{r['value']:,.2f}" if r["series_id"] not in
        ("ECB_ESTR_VOL", "ECB_ESTR_BANKS") else f"{r['value']:,.0f}",
        axis=1,
    )
    ctx["As of"] = ctx["obs_date"].dt.strftime("%d %b %Y")
    st.dataframe(
        ctx[["Series", "Latest", "As of"]].sort_values("Series"),
        width="stretch",
        hide_index=True,
    )

    hist = _estr_history("ECB_ESTR")
    hist_3m = _estr_history("ECB_ESTR_3M")
    if not hist.empty:
        line = go.Figure()
        line.add_scatter(x=hist["obs_date"], y=hist["value"],
                         name="€STR (overnight)", line=dict(color=NAVY, width=2))
        if not hist_3m.empty:
            line.add_scatter(x=hist_3m["obs_date"], y=hist_3m["value"],
                             name="€STR compounded 3M",
                             line=dict(color=AMBER, width=1.6, dash="dot"))
        line.add_hline(y=current_rate, line=dict(color=RED, width=1, dash="dash"),
                       annotation_text="Deposit facility rate",
                       annotation_position="bottom right")
        line.update_layout(
            template="plotly_white", height=360,
            yaxis=dict(title="Rate (%)"),
            margin=dict(l=10, r=10, t=30, b=10),
            hovermode="x unified",
        )
        st.plotly_chart(line, width="stretch")

with st.expander("Method and caveats"):
    st.markdown(
        """
**Local engine (`fct_ecb_meeting_probabilities`)**

1. Take the latest official euro OIS rate per ECB MMSR bucket
   (`MM_SEGMENT = 'O'`, `DATA_TYPE_MM = 'WR'`) — 1M, 2M, 3M, 6M, 9M, 12M, 2Y.
2. A decision lands at the *start* of a reserve maintenance period, so
   interpolate the curve to the midpoint of `[meeting_i, meeting_{i+1})`.
3. Difference consecutive period rates to get the expected change at each
   meeting, anchored on the current deposit facility rate.
4. Split each change into adjacent 25bp steps and convolve the per-meeting
   splits into the distribution of the rate level after each meeting — the same
   core decomposition as the CME FedWatch tool.

**Why it is indicative, not tradeable**

MMSR reports *bucket averages* of traded OIS, not a meeting-dated swap curve,
and lags live pricing by roughly six to eight weeks in coarse steps. The
`Curve staleness` metric is the honest freshness clock.

**Why the cross-check exists**

Trade-accurate probabilities require dated €STR futures settlement prices from
an exchange (the ecb-watch feed names `EMP`/`FEMP` futures). Neither the ECB nor
the Bundesbank publishes those, so the fibres are ingested from ecb-watch.eu as
a scoring series — never as the platform's own source of truth.

**Broader note**: the ECB publishes no Survey of Monetary Analysts (SMA) SDMX
dataflow either, so survey-based rate expectations are not an option here.
        """
    )
