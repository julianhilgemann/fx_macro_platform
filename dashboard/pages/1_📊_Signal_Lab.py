"""Signal Lab — in-depth time-series econometrics page of the FX Macro suite.

Takes any macro series from the warehouse and dissects it along every axis:

* transformation of the signal (level, difference, % change, log-return,
  index/base, z-score, STL components, seasonally-adjusted)
* calendar & performance metrics (MoM/QoQ/YoY/MTD/YTD, annual performance)
* decomposition (STL / classical additive / multiplicative) with strength stats
* cyclicality (ACF/PACF, Ljung-Box, seasonal subseries, cycle profiles,
  year x period heatmaps, lag-scatter plots)
* frequency domain (periodogram, Welch PSD, dominant-period peaks, Morlet
  wavelet scalogram, spectral band shares)
* time filtering (HP, Baxter-King, Christiano-Fitzgerald, Butterworth
  low/high/band-pass, centred MA, EMA) with frequency responses — the filtered
  slice can be pushed through every other tab
* distribution & risk (KDE vs normal, QQ, rolling moments, drawdown, ridge
  plots, by-cycle violins)
* multi-series correlation maps (levels & returns matrices, rolling
  correlations, lead-lag cross-correlograms)

Every tab is rendered inside a guard: one section failing (e.g. a transform
producing degenerate values) degrades to an error card instead of taking the
whole page down, and all analytics sanitise infs/NaNs before scipy/statsmodels.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import lab
from data import (
    load_catalog,
    load_observations,
    load_series_grains,
    load_series_transforms,
)
from forecast import prepare_series

st.set_page_config(
    page_title="Signal Lab — Time-Series Econometrics",
    page_icon="📡",
    layout="wide",
)

# --------------------------------------------------------------------------- #
# dbt-mart wiring: grains & transforms precomputed in the warehouse
# --------------------------------------------------------------------------- #
GRAIN_ORDER = ["day", "week", "month", "quarter", "year"]
GRAIN_PERIOD = {"day": 7, "week": 52, "month": 12, "quarter": 4, "year": 1}
GRAIN_LABEL = {
    "day": "daily", "week": "weekly", "month": "monthly",
    "quarter": "quarterly", "year": "yearly",
}
# runtime transform kind -> dbt transform name (STL kinds stay runtime-only)
DWH_TRANSFORMS = {
    "level": "level",
    "diff": "diff",
    "pct": "pct_change",
    "log": "log_level",
    "logdiff": "log_return",
    "index": "index_100",
    "zscore": "zscore",
}

# --------------------------------------------------------------------------- #
# Shared style
# --------------------------------------------------------------------------- #
C_BLUE, C_ORANGE, C_GREEN, C_AMBER = "#2563eb", "#ea580c", "#059669", "#d97706"
C_SLATE, C_RED, C_PURPLE = "#64748b", "#dc2626", "#7c3aed"


def fmt(x) -> str:
    if x is None:
        return "—"
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not np.isfinite(f):
        return "—"
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    if abs(f) >= 1:
        return f"{f:,.2f}"
    return f"{f:.4g}"


def pct(x) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return "—"
    return "—" if not np.isfinite(f) else f"{f:+.2f}%"


def layout(fig: go.Figure, title: str | None = None, height: int = 380,
           xaxis_title: str = "", yaxis_title: str = "", unified: bool = True,
           legend: bool = True, **kwargs) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=10, r=10, t=46 if title else 16, b=10),
        title=dict(text=title, font=dict(size=15)) if title else None,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        hovermode="x unified" if unified else None,
        showlegend=legend,
        **kwargs,
    )
    return fig


def guarded(name: str, fn) -> None:
    """Run a tab body; degrade to an error card instead of killing the page."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — isolate tab failures
        st.error(f"**{name}** hit a problem with this configuration: `{exc}`")
        st.caption(
            "The rest of the page is unaffected — try another transform, filter or "
            "a wider window. (NaN/inf-safe guards drop degenerate points.)"
        )


# --------------------------------------------------------------------------- #
# Cached loaders / computations
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300, show_spinner=False)
def get_catalog() -> pd.DataFrame:
    return load_catalog()


@st.cache_data(ttl=300, show_spinner=False)
def get_obs(series_id: str) -> pd.DataFrame:
    return load_observations(series_id)


@st.cache_data(show_spinner=False)
def cached_decompose(s: pd.Series, period: int, method: str) -> dict:
    return lab.decompose(s, period, method)


@st.cache_data(show_spinner=False)
def cached_acf(s: pd.Series, nlags: int) -> dict:
    return lab.acf_pacf(s, nlags)


@st.cache_data(show_spinner=False)
def cached_periodogram(s: pd.Series) -> dict:
    return lab.periodogram(s)


@st.cache_data(show_spinner=False)
def cached_welch(s: pd.Series, nperseg: int) -> dict:
    return lab.welch_psd(s, nperseg)


@st.cache_data(show_spinner=False)
def cached_wavelet(s: pd.Series, dt: float, n_scales: int) -> dict:
    return lab.morlet_wavelet(s, dt=dt, n_scales=n_scales)


@st.cache_data(show_spinner=False)
def cached_filter(s: pd.Series, kind: str, params: dict) -> dict:
    return lab.filter_series(s, kind, params)


@st.cache_data(ttl=300, show_spinner=False)
def get_grains(series_id: str) -> list[str]:
    """Grains available in the dbt mart for a series ([] when not built)."""
    try:
        df = load_series_grains(series_id)
    except Exception:
        return []
    if df.empty:
        return []
    return sorted(df["grain"].unique().tolist(), key=GRAIN_ORDER.index)


@st.cache_data(ttl=300, show_spinner=False)
def get_grain_df(series_id: str, grain: str) -> pd.DataFrame:
    try:
        df = load_series_grains(series_id)
    except Exception:
        return pd.DataFrame(columns=["grain", "period_date", "value"])
    return df[df["grain"] == grain]


@st.cache_data(ttl=300, show_spinner=False)
def get_transform_df(series_id: str, grain: str, transform: str) -> pd.DataFrame:
    try:
        return load_series_transforms(series_id, grain, transform)
    except Exception:
        return pd.DataFrame(columns=["period_date", "value"])


# --------------------------------------------------------------------------- #
# Tab renderers (each isolated by `guarded`)
# --------------------------------------------------------------------------- #
def render_overview(ctx: dict) -> None:
    s = ctx["analysis"]
    chain = ctx["chain"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", name=chain,
        line=dict(color=C_BLUE, width=1.5),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.07)",
    ))
    fig.add_annotation(
        x=s.index[-1], y=s.iloc[-1],
        text=f" {s.iloc[-1]:,.4g}", showarrow=False,
        xanchor="left", font=dict(color=C_BLUE, size=12),
    )
    layout(fig, title=f"Analysed series — {chain}", height=420,
           yaxis_title=ctx["meta"].unit or "value")
    fig.update_xaxes(rangeslider_visible=True)
    st.plotly_chart(fig, width="stretch")

    cal = lab.calendar_stats(s)
    stats = lab.summary_stats(s)
    statio = lab.stationarity(s)

    c = st.columns(6)
    c[0].metric("Last value", fmt(cal.get("last")))
    c[1].metric("MoM", pct(cal.get("mom_pct")))
    c[2].metric("QoQ", pct(cal.get("qoq_pct")))
    c[3].metric("YoY", pct(cal.get("yoy_pct")))
    c[4].metric("MTD", pct(cal.get("mtd_pct")))
    c[5].metric("YTD", pct(cal.get("ytd_pct")))

    c = st.columns(6)
    c[0].metric("Observations", f"{stats['n']:,}")
    c[1].metric("First", s.index.min().strftime("%Y-%m-%d"))
    c[2].metric("Last", s.index.max().strftime("%Y-%m-%d"))
    c[3].metric("Mean", fmt(stats["mean"]))
    c[4].metric("Std dev", fmt(stats["std"]))
    c[5].metric("Min / Max", f"{fmt(stats['min'])} / {fmt(stats['max'])}")

    c = st.columns(5)
    c[0].metric("Skewness", fmt(stats["skew"]))
    c[1].metric("Excess kurtosis", fmt(stats["kurt"]))
    c[2].metric("ADF p-value", fmt(statio["adf_pvalue"]),
                help="< 0.05 → reject unit root (stationary).")
    c[3].metric("KPSS p-value", fmt(statio["kpss_pvalue"]),
                help="≥ 0.05 → fail to reject stationarity.")
    c[4].metric("Jarque-Bera p", fmt(stats.get("jb_pvalue")),
                help="< 0.05 → reject normality.")
    st.caption(
        "Period-over-period / YoY / MTD / YTD changes are computed on the analysed "
        "series as displayed above (last value vs. the value at the earlier anchor)."
    )


def render_calendar(ctx: dict) -> None:
    s = ctx["analysis"]
    period = ctx["period"]
    st.markdown("#### Recent observations with period & year-over-year changes")
    rt = lab.recent_table(s, rows=14)
    st.dataframe(
        rt.style.format({
            "value": "{:,.3f}", "chg": "{:+,.3f}",
            "pop_pct": "{:+.2f}%", "yoy_pct": "{:+.2f}%",
        }, na_rep="—"),
        width="stretch",
    )

    ap = lab.annual_performance(s).dropna(subset=["pct"])
    if not ap.empty:
        fig = go.Figure()
        colors = [C_GREEN if v >= 0 else C_RED for v in ap["pct"]]
        fig.add_trace(go.Bar(
            x=ap["year"].astype(str), y=ap["pct"], marker_color=colors,
            text=[f"{v:+.1f}%" for v in ap["pct"]], textposition="outside",
        ))
        fig.add_hline(y=0, line_color="#94a3b8", line_width=1)
        layout(fig, title="Annual performance (% change, year-on-year)", height=320,
               yaxis_title="%", unified=False)
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### Seasonal structure")
    if len(s) >= 2 * period and period > 1:
        piv = lab.year_period_matrix(s, period)
        yoy = lab.yoy_matrix(piv, period)
        pos_axis = [f"P{i}" for i in piv.columns]

        col1, col2 = st.columns(2)
        with col1:
            fig = go.Figure(go.Heatmap(
                z=piv.values, x=pos_axis, y=[str(y) for y in piv.index],
                colorscale="Viridis", colorbar=dict(title="value"),
                hovertemplate="year %{y} · %{x}: %{z:,.3f}<extra></extra>",
            ))
            layout(fig, title="Year × cycle-position map (levels)", height=420, unified=False)
            st.plotly_chart(fig, width="stretch")
        with col2:
            fig = go.Figure(go.Heatmap(
                z=yoy.values, x=pos_axis, y=[str(y) for y in yoy.index],
                colorscale="RdBu", zmid=0, colorbar=dict(title="% yoy"),
                hovertemplate="year %{y} · %{x}: %{z:+.2f}%<extra></extra>",
            ))
            layout(fig, title="Year × cycle-position map (% YoY)", height=420, unified=False)
            st.plotly_chart(fig, width="stretch")

        cp = lab.cycle_profile(s, period)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=cp["pos"], y=cp["mean"] + cp["std"], mode="lines", line=dict(width=0),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=cp["pos"], y=cp["mean"] - cp["std"], mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor="rgba(37,99,235,0.12)", name="±1σ band",
        ))
        fig.add_trace(go.Scatter(
            x=cp["pos"], y=cp["mean"], mode="lines+markers",
            name="cycle average", line=dict(color=C_BLUE, width=2.4),
        ))
        fig.add_trace(go.Scatter(
            x=cp["pos"], y=cp["median"], mode="lines", name="median",
            line=dict(color=C_ORANGE, width=1.4, dash="dot"),
        ))
        layout(fig, title="Average cycle profile (mean ± 1σ)", height=320,
               xaxis_title=f"position within cycle (1…{period})", yaxis_title="value")
        st.plotly_chart(fig, width="stretch")

        best = cp.loc[cp["mean"].idxmax()]
        worst = cp.loc[cp["mean"].idxmin()]
        st.caption(
            f"Strongest position: **P{int(best['pos'])}** (mean {best['mean']:,.3f}) · "
            f"weakest: **P{int(worst['pos'])}** (mean {worst['mean']:,.3f}) · "
            f"seasonal swing {cp['mean'].max() - cp['mean'].min():,.3f}"
        )
    else:
        st.info("Not enough data for seasonal structure (need ≥ 2 full cycles).")


def render_decomposition(ctx: dict) -> None:
    s = ctx["prepared"]
    period = ctx["period"]
    method_label = st.radio(
        "Decomposition method",
        ["Auto", "STL (Loess)", "Classical additive", "Classical multiplicative"],
        horizontal=True,
    )
    method = {
        "Auto": "auto", "STL (Loess)": "stl",
        "Classical additive": "classical_add", "Classical multiplicative": "classical_mul",
    }[method_label]

    if period < 2:
        st.info(
            "Decomposition needs at least 2 periods per cycle — the **year** grain "
            "has no intra-year seasonality. Pick a finer grain (quarter/month/…) "
            "in the sidebar to decompose this series."
        )
        return

    try:
        comp = cached_decompose(s, period, method)
    except ValueError as exc:
        st.error(str(exc))
        comp = None

    if comp is None:
        return

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        subplot_titles=("Observed", "Trend", "Seasonal", "Residual"),
    )
    traces = [
        (s, C_BLUE), (comp["trend"], C_ORANGE),
        (comp["seasonal"], C_GREEN), (comp["resid"], C_SLATE),
    ]
    for i, (series, color) in enumerate(traces, start=1):
        fig.add_trace(go.Scatter(
            x=series.index, y=series.values, mode="lines",
            line=dict(color=color, width=1.2), showlegend=False,
        ), row=i, col=1)
    fig.update_layout(
        template="plotly_white", height=760,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, width="stretch")

    c = st.columns(4)
    c[0].metric("Method", comp["method"])
    c[1].metric("Trend strength F_t", fmt(comp["f_trend"]),
                help="1 − Var(resid)/Var(trend+resid) — near 1 ⇒ strong trend.")
    c[2].metric("Seasonal strength F_s", fmt(comp["f_seasonal"]),
                help="1 − Var(resid)/Var(seasonal+resid) — near 1 ⇒ strong seasonality.")
    c[3].metric("Residual σ", fmt(comp["resid_std"]))

    fig = go.Figure(go.Bar(
        x=["Trend", "Seasonal", "Residual"],
        y=[comp["trend_std"], comp["seasonal_std"], comp["resid_std"]],
        marker_color=[C_ORANGE, C_GREEN, C_SLATE],
        text=[f"{v:,.4g}" for v in (comp["trend_std"], comp["seasonal_std"], comp["resid_std"])],
        textposition="outside",
    ))
    layout(fig, title="Component volatility (std dev)", height=280,
           yaxis_title="std dev", unified=False)
    st.plotly_chart(fig, width="stretch")

    n = len(s)
    mid = (n // 2 // period) * period
    slice_ = comp["seasonal"].iloc[mid: mid + period].dropna()
    if len(slice_) > 1:
        fig = go.Figure(go.Scatter(
            x=np.arange(len(slice_)) + 1, y=slice_.values,
            mode="lines+markers", marker=dict(size=7, color=C_GREEN),
            line=dict(color=C_GREEN, width=2),
        ))
        fig.add_hline(y=0, line_color="#94a3b8", line_dash="dot")
        layout(fig, title=f"One full seasonal cycle (positions {mid + 1}–{mid + period})",
               height=260, xaxis_title="position in cycle", yaxis_title="seasonal deviation",
               unified=False, legend=False)
        st.plotly_chart(fig, width="stretch")


def render_cyclicality(ctx: dict) -> None:
    s = ctx["analysis"]
    period = ctx["period"]
    n = len(s)
    nlags = st.slider("Lags", 10, min(120, max(12, n // 2)), min(48, max(10, n // 4)))
    ac = cached_acf(s, nlags)

    fig = make_subplots(rows=1, cols=2, subplot_titles=("Autocorrelation (ACF)", "Partial autocorrelation (PACF)"))
    lags = ac["lags"]
    fig.add_trace(go.Bar(x=lags, y=ac["acf"], name="ACF", marker_color=C_BLUE), 1, 1)
    fig.add_trace(go.Bar(x=lags, y=ac["pacf"], name="PACF", marker_color=C_ORANGE), 1, 2)
    band = 1.96 / np.sqrt(max(1, n))
    for col in (1, 2):
        fig.add_hline(y=band, line_dash="dash", line_color="#94a3b8", row=1, col=col)
        fig.add_hline(y=-band, line_dash="dash", line_color="#94a3b8", row=1, col=col)
    fig.update_layout(
        template="plotly_white", height=340, showlegend=False,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, width="stretch")

    if ac.get("q_pvalues") is not None and len(ac["q_pvalues"]) > 1:
        qp = np.asarray(ac["q_pvalues"], dtype=float)
        qp_finite = np.isfinite(qp)
        fig = go.Figure(go.Bar(
            x=lags[1: len(qp) + 1], y=qp,
            marker_color=[C_SLATE if not ok else ("#94a3b8" if p >= 0.05 else C_RED)
                          for ok, p in zip(qp_finite, qp)],
            name="Ljung-Box p",
        ))
        fig.add_hline(y=0.05, line_color=C_RED, line_dash="dash")
        fig.add_annotation(x=2, y=0.08, text="5% level — bars below ⇒ significant autocorrelation",
                           showarrow=False, font=dict(size=10, color=C_RED))
        layout(fig, title="Ljung-Box test per lag (p-values)", height=260,
               xaxis_title="lag", unified=False, legend=False)
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### Lag scatter plots (linear dependence at selected lags)")
    chosen = sorted({1, 2, period, 2 * period})
    chosen = [l for l in chosen if l <= n - 2]
    if len(chosen) >= 2:
        rows = (len(chosen) + 1) // 2
        titles = []
        for l in chosen:
            a = s.iloc[l:].to_numpy(dtype=float)
            b = s.iloc[:-l].to_numpy(dtype=float)
            r = float(np.corrcoef(a, b)[0, 1]) if np.std(a) and np.std(b) else np.nan
            titles.append(f"lag {l} (r = {r:.3f})")
        fig = make_subplots(rows=rows, cols=2, subplot_titles=titles)
        for i, l in enumerate(chosen):
            r, c = i // 2 + 1, i % 2 + 1
            x, y = s.iloc[l:].values, s.iloc[:-l].values
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="markers",
                marker=dict(size=4, color=C_BLUE, opacity=0.45),
                showlegend=False,
            ), row=r, col=c)
            fig.update_xaxes(title_text="x(t)", row=r, col=c)
            fig.update_yaxes(title_text=f"x(t−{l})", row=r, col=c)
        fig.update_layout(template="plotly_white", height=300 * rows,
                          margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, width="stretch")

    if len(s) >= 2 * period and period > 1:
        st.markdown("#### Seasonal subseries — each cycle overlaid")
        piv = lab.seasonal_subseries(s, period)
        fig = go.Figure()
        mean_line = piv.mean(axis=0)
        for cyc in piv.index:
            fig.add_trace(go.Scatter(
                x=list(piv.columns), y=piv.loc[cyc].values, mode="lines",
                line=dict(color="#94a3b8", width=1), opacity=0.45,
                showlegend=False, hovertext=[str(cyc)] * len(piv.columns),
            ))
        fig.add_trace(go.Scatter(
            x=list(piv.columns), y=mean_line.values, mode="lines+markers",
            name="average cycle", line=dict(color=C_BLUE, width=3),
            marker=dict(size=6, color=C_BLUE),
        ))
        layout(fig, title="Seasonal subseries plot (grey = individual cycles, blue = average)",
               height=360, xaxis_title=f"position within cycle (1…{period})",
               yaxis_title="value")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Seasonal subseries need ≥ 2 full cycles in the analysed series.")


def render_frequency(ctx: dict) -> None:
    s = ctx["analysis"]
    period = ctx["period"]
    n = len(s)
    nperseg = st.slider("Welch segment length", 16, min(2048, max(32, n)), min(256, max(32, n)),
                        step=16, help="Longer segments ⇒ finer frequency resolution, more variance.")

    pgram = cached_periodogram(s)
    welch = cached_welch(s, nperseg)
    peaks = lab.dominant_peaks(pgram["freq"], pgram["power"], ctx["gap_days"], top=8)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pgram["freq"][pgram["freq"] > 0], y=pgram["power"][pgram["freq"] > 0],
        mode="lines", name="Periodogram",
        line=dict(color="#94a3b8", width=0.8),
    ))
    fig.add_trace(go.Scatter(
        x=welch["freq"][welch["freq"] > 0], y=welch["power"][welch["freq"] > 0],
        mode="lines", name=f"Welch (nperseg={nperseg})",
        line=dict(color=C_BLUE, width=2),
    ))
    for _, pk in peaks.head(3).iterrows():
        f0 = pk["frequency (cycles/sample)"]
        fig.add_vline(x=f0, line_dash="dot", line_color=C_ORANGE)
        fig.add_annotation(
            x=f0, y=1.0, yref="paper", text=f" ≈ {pk.iloc[2]:g}",
            showarrow=False, font=dict(size=10, color=C_ORANGE),
        )
    fig.update_xaxes(type="log", title="frequency (cycles per observation)")
    fig.update_yaxes(type="log", title="power spectral density")
    fig.update_layout(
        template="plotly_white", height=400,
        margin=dict(l=10, r=10, t=20, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Dominant cycles (spectral peaks)")
    if not peaks.empty:
        st.dataframe(peaks.style.format(
            {"period (samples)": "{:.2f}", "frequency (cycles/sample)": "{:.6f}",
             "power": "{:.3g}"},
            subset=["period (samples)", "frequency (cycles/sample)", "power"],
            na_rep="—",
        ), width="stretch")

        f, p = pgram["freq"], pgram["power"]
        m = np.isfinite(f) & np.isfinite(p) & (f > 0)
        ps = 1.0 / f[m]
        bands = {
            f"short (< {period * 0.75:g})": ps < period * 0.75,
            f"seasonal ({period * 0.75:g}–{period * 1.5:g})": (ps >= period * 0.75) & (ps <= period * 1.5),
            f"long (> {period * 1.5:g})": ps > period * 1.5,
        }
        total = p[m].sum()
        shares = {k: float(p[m][sel].sum() / total) * 100 if total else 0.0 for k, sel in bands.items()}
        fig = go.Figure()
        for k, share in shares.items():
            fig.add_trace(go.Bar(
                y=["spectral power"], x=[share], name=f"{k} · {share:.1f}%",
                orientation="h", marker_color=C_BLUE if "seasonal" in k else C_ORANGE if "long" in k else C_SLATE,
            ))
        layout(fig, title="Where does the power live? (periodogram band shares)",
               height=220, unified=False,
               barmode="stack", xaxis_title="% of total spectral power")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No spectral peaks detectable.")

    st.markdown("#### Wavelet scalogram — cycles that come and go")
    n_scales = st.slider("Wavelet scales", 32, 128, 96, step=8)
    wv = cached_wavelet(s, dt=ctx["gap_days"], n_scales=n_scales)
    fig = go.Figure(go.Heatmap(
        z=np.abs(wv["coef"]),
        x=wv["times"], y=wv["periods_cal"],
        colorscale="Turbo",
        colorbar=dict(title="|W(a,b)|"),
        hovertemplate="%{x|%Y-%m-%d} · period ≈ %{y:,.1f} "
                      + wv["unit"] + "<extra></extra>",
    ))
    fig.update_yaxes(type="log", title=f"period ({wv['unit']})")
    layout(fig, title="Morlet wavelet scalogram (warm = strong cycle at that period & time)",
           height=460, unified=False)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Pseudo-periods follow Torrence & Compo. The series is treated as uniformly "
        "spaced (business-day gaps are bridged), so daily cycles below a few days "
        "are approximate. Edge effects fade the cone of influence at both ends."
    )


def render_filters(ctx: dict) -> None:
    if ctx["filter_result"] is None:
        st.info(
            "No filter is active. Open **⏳ Time filtering** in the sidebar and pick a "
            "filter (HP, Baxter-King, Christiano-Fitzgerald, Butterworth, centred MA or "
            "EMA) — this tab will then show the pass band, its complement and the "
            "filter's frequency response. Use the sidebar radio to push the filtered "
            "slice through every other tab."
        )
        return

    fr = ctx["filter_result"]
    orig = lab.sanitize(ctx["filter_input"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=orig.index, y=orig.values, mode="lines", name="input series",
        line=dict(color="#94a3b8", width=1.2),
    ))
    fig.add_trace(go.Scatter(
        x=fr["pass"].index, y=fr["pass"].values, mode="lines",
        name=fr["pass_label"], line=dict(color=C_BLUE, width=2.4),
    ))
    fig.add_trace(go.Scatter(
        x=fr["comp"].index, y=fr["comp"].values, mode="lines",
        name=fr["comp_label"], line=dict(color=C_ORANGE, width=1.4, dash="dot"),
    ))
    layout(fig, title=f"Filter decomposition — {fr['pass_label']}", height=420)
    st.plotly_chart(fig, width="stretch")

    var_orig = float(np.nanvar(orig))
    if var_orig > 0:
        var_pass = float(np.nanvar(fr["pass"]))
        var_comp = float(np.nanvar(fr["comp"]))
        cov2 = var_orig - var_pass - var_comp
        parts = [("pass band", var_pass / var_orig * 100, C_BLUE),
                 ("complement", var_comp / var_orig * 100, C_ORANGE),
                 ("2·cov(pass, comp)", cov2 / var_orig * 100, C_SLATE)]
        fig = go.Figure()
        for name, share, color in parts:
            fig.add_trace(go.Bar(
                y=["variance"], x=[share], name=f"{name} · {share:+.1f}%",
                orientation="h", marker_color=color,
            ))
        layout(fig, title="Variance decomposition of the filtered split "
                         "(var(orig) = var(pass) + var(comp) + 2·cov)",
               height=220, unified=False, barmode="stack",
               xaxis_title="% of input variance")
        st.plotly_chart(fig, width="stretch")

    if fr["freq"] is not None:
        fig = go.Figure()
        f, m = fr["freq"], fr["mag"]
        ok = np.isfinite(f) & np.isfinite(m) & (f > 0)
        fig.add_trace(go.Scatter(
            x=1.0 / f[ok], y=m[ok], mode="lines", name="|H(f)|",
            line=dict(color=C_PURPLE, width=2),
        ))
        fig.update_xaxes(type="log", title="period (observations)")
        fig.update_yaxes(title="magnitude")
        layout(fig, title="Frequency response of the filter", height=300,
               unified=False, legend=False)
        st.plotly_chart(fig, width="stretch")


def render_distribution(ctx: dict) -> None:
    s = ctx["analysis"]
    period = ctx["period"]
    chain = ctx["chain"]
    # sanitize: pct_change of series that cross zero produces ±inf, which
    # would break scipy's finite checks downstream.
    rets = lab.sanitize(s.pct_change() * 100.0)

    col1, col2 = st.columns(2)
    with col1:
        dens = lab.density(s)
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=s.values, nbinsx=60, histnorm="probability density",
            name="histogram", marker_color="rgba(37,99,235,0.45)",
        ))
        if len(dens["x"]):
            fig.add_trace(go.Scatter(
                x=dens["x"], y=dens["kde"], mode="lines", name="KDE",
                line=dict(color=C_BLUE, width=2.4),
            ))
            fig.add_trace(go.Scatter(
                x=dens["x"], y=dens["normal"], mode="lines", name="normal fit (MLE)",
                line=dict(color=C_RED, width=1.6, dash="dash"),
            ))
        layout(fig, title=f"Density — {chain}", height=380, yaxis_title="density")
        st.plotly_chart(fig, width="stretch")

    with col2:
        dens2 = lab.density(rets)
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=rets.values, nbinsx=60, histnorm="probability density",
            name="histogram", marker_color="rgba(234,88,12,0.4)",
        ))
        if len(dens2["x"]):
            fig.add_trace(go.Scatter(
                x=dens2["x"], y=dens2["kde"], mode="lines", name="KDE",
                line=dict(color=C_ORANGE, width=2.4),
            ))
            fig.add_trace(go.Scatter(
                x=dens2["x"], y=dens2["normal"], mode="lines", name="normal fit (MLE)",
                line=dict(color=C_RED, width=1.6, dash="dash"),
            ))
        layout(fig, title="Density of period-over-period % changes", height=380,
               yaxis_title="density")
        st.plotly_chart(fig, width="stretch")

    st.caption(
        f"Skewness {fmt(lab.summary_stats(s)['skew'])} · excess kurtosis "
        f"{fmt(lab.summary_stats(s)['kurt'])} — fat tails show up as a KDE above the "
        "dashed normal in the wings."
    )

    col1, col2 = st.columns(2)
    with col1:
        qq = lab.qq_data(s)
        if len(qq["theoretical"]):
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=qq["theoretical"], y=qq["sample"], mode="markers",
                marker=dict(size=4, color=C_BLUE, opacity=0.5), name="quantiles",
            ))
            try:
                m_, b_ = np.polyfit(qq["theoretical"], qq["sample"], 1)
                fig.add_trace(go.Scatter(
                    x=qq["theoretical"], y=m_ * qq["theoretical"] + b_,
                    mode="lines", name="normal reference",
                    line=dict(color=C_RED, width=1.6, dash="dash"),
                ))
            except Exception:
                pass
            layout(fig, title="Q-Q plot vs normal", height=360,
                   xaxis_title="theoretical quantiles", yaxis_title="sample quantiles")
            st.plotly_chart(fig, width="stretch")
    with col2:
        dd = lab.drawdown(s)
        fig = go.Figure(go.Scatter(
            x=dd.index, y=dd.values * 100, mode="lines", name="drawdown",
            line=dict(color=C_RED, width=1.2), fill="tozeroy",
            fillcolor="rgba(220,38,38,0.22)",
        ))
        layout(fig, title=f"Drawdown from running peak (max {dd.min() * 100:.1f}%)",
               height=360, yaxis_title="%")
        st.plotly_chart(fig, width="stretch")

    window = st.slider("Rolling window", 10, min(504, max(20, len(s))),
                       min(252, max(20, len(s) // 4)))
    rm = lab.rolling_moments(s, window)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rm.index, y=rm["mean"] + rm["std"], mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=rm.index, y=rm["mean"] - rm["std"], mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor="rgba(37,99,235,0.12)", name="±1σ band",
    ))
    fig.add_trace(go.Scatter(
        x=rm.index, y=rm["mean"], mode="lines", name=f"rolling mean ({window})",
        line=dict(color=C_BLUE, width=2),
    ))
    fig.add_trace(go.Scatter(
        x=rm.index, y=rm["q05"], mode="lines", name="5th pct",
        line=dict(color=C_ORANGE, width=1, dash="dot"),
    ))
    fig.add_trace(go.Scatter(
        x=rm.index, y=rm["q95"], mode="lines", name="95th pct",
        line=dict(color=C_ORANGE, width=1, dash="dot"),
    ))
    layout(fig, title=f"Rolling location & spread ({window} obs)", height=340)
    st.plotly_chart(fig, width="stretch")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rm.index, y=rm["skew"], mode="lines", name="rolling skewness",
        line=dict(color=C_PURPLE, width=1.6),
    ))
    fig.add_trace(go.Scatter(
        x=rm.index, y=rm["kurt"], mode="lines", name="rolling excess kurtosis",
        line=dict(color=C_AMBER, width=1.6),
    ))
    fig.add_hline(y=0, line_color="#94a3b8")
    layout(fig, title=f"Rolling higher moments ({window} obs)", height=300,
           yaxis_title="moment")
    st.plotly_chart(fig, width="stretch")

    vol = rets.rolling(window, min_periods=max(5, window // 2)).std()
    fig = go.Figure(go.Scatter(
        x=vol.index, y=vol.values, mode="lines", name="rolling σ of % changes",
        line=dict(color=C_GREEN, width=1.8),
    ))
    layout(fig, title=f"Rolling volatility ({window} obs)", height=280,
           yaxis_title="σ (% points)")
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Ridge plot — distribution of values, one ridge per year")
    ridges = lab.ridge_data(s)
    if ridges:
        fig = go.Figure()
        n_ridges = len(ridges)
        for i, r in enumerate(ridges):
            color = lab.PALETTE[i % len(lab.PALETTE)]
            fig.add_trace(go.Scatter(
                x=r["x"], y=r["y"] + i, mode="lines", name=str(r["year"]),
                line=dict(color=color, width=1.2), fill="tonexty",
                fillcolor=f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.25)",
            ))
        fig.update_yaxes(
            tickvals=list(range(n_ridges)),
            ticktext=[str(r["year"]) for r in ridges],
            title="year",
        )
        layout(fig, title="Ridge plot — KDE per year, stacked",
               height=420, unified=False, yaxis_title="year")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Too few observations per year for a ridge plot.")

    if len(s) >= 2 * period and period > 1:
        bd = lab.by_cycle_box(s, period)
        fig = go.Figure()
        for pos in sorted(bd["pos"].unique()):
            vals = bd.loc[bd["pos"] == pos, "value"]
            color = lab.PALETTE[(int(pos) - 1) % len(lab.PALETTE)]
            fig.add_trace(go.Violin(
                y=vals, x=[f"P{int(pos)}"] * len(vals), name=f"P{int(pos)}",
                box_visible=True, meanline_visible=True, points=False,
                line_color=color, fillcolor=f"rgba(37,99,235,0.08)", width=0.9,
                showlegend=False,
            ))
        layout(fig, title="Distribution by position within the cycle",
               height=380, unified=False, yaxis_title="value")
        st.plotly_chart(fig, width="stretch")


def render_correlation(ctx: dict) -> None:
    if not ctx["companion_labels"]:
        st.info(
            "Pick **Companion series** in the sidebar (up to 6) to build correlation "
            "maps: level & %-change matrices, rolling correlations and lead-lag "
            "cross-correlograms against the primary series."
        )
        return

    companion_series: dict[str, pd.Series] = {}
    for label in ctx["companion_labels"]:
        sid = ctx["label_to_id"][label]
        cm = ctx["catalog"][ctx["catalog"].series_id == sid].iloc[0]
        cobs = get_obs(sid)
        if cobs.empty:
            continue
        if ctx["dwh_grain"]:
            # same precomputed grain as the primary series
            gdf = get_grain_df(sid, ctx["dwh_grain"])
            gdf = gdf[(gdf["period_date"] >= ctx["start"]) & (gdf["period_date"] <= ctx["end"])]
            if len(gdf) >= lab.MIN_POINTS:
                companion_series[f"{sid}"] = pd.Series(
                    gdf["value"].to_numpy(),
                    index=pd.to_datetime(gdf["period_date"]),
                    name="value",
                ).sort_index()
        else:
            cw = cobs[(cobs.obs_date >= ctx["start"]) & (cobs.obs_date <= ctx["end"])]
            cprepared, _, _ = prepare_series(cw, cm.frequency)
            if len(cprepared) >= lab.MIN_POINTS:
                companion_series[f"{sid}"] = cprepared

    if not companion_series:
        st.warning("No companion series had usable data in this window.")
        return

    aligned = lab.align_frame(ctx["analysis"], companion_series)
    aligned.columns = [f"{ctx['series_id']} (primary)", *companion_series.keys()]
    if len(aligned) < 10:
        st.warning(
            f"Only {len(aligned)} common observations after alignment — "
            "widen the window or pick companions with longer overlap."
        )
        st.stop()

    st.markdown(
        f"**Aligned frame:** {len(aligned):,} common observations. "
        + (f"Primary and companions share the precomputed **{ctx['dwh_grain']}** grain "
           "from the dbt mart; missing leading values are dropped."
           if ctx["dwh_grain"] else
           "Companions are re-indexed onto the primary calendar and forward-filled; "
           "missing leading values are dropped.")
    )
    with st.expander("Inspect aligned data (head)"):
        st.dataframe(aligned.head(12).style.format("{:,.3f}", na_rep="—"),
                     width="stretch")

    levels, rets = lab.corr_matrices(aligned)
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure(go.Heatmap(
            z=levels.values, x=list(levels.columns), y=list(levels.index),
            colorscale="RdBu", zmin=-1, zmax=1, zmid=0,
            text=np.round(levels.values, 2), texttemplate="%{text}",
            colorbar=dict(title="ρ"),
        ))
        layout(fig, title="Correlation map — levels", height=380, unified=False)
        st.plotly_chart(fig, width="stretch")
    with col2:
        fig = go.Figure(go.Heatmap(
            z=rets.values, x=list(rets.columns), y=list(rets.index),
            colorscale="RdBu", zmin=-1, zmax=1, zmid=0,
            text=np.round(rets.values, 2), texttemplate="%{text}",
            colorbar=dict(title="ρ"),
        ))
        layout(fig, title="Correlation map — % changes", height=380, unified=False)
        st.plotly_chart(fig, width="stretch")

    rw = st.slider("Rolling correlation window", 10, min(504, max(20, len(aligned))),
                   min(250, max(20, len(aligned) // 2)))
    rc = lab.rolling_corr(aligned, aligned.columns[0], rw)
    fig = go.Figure()
    for i, col in enumerate(rc.columns):
        fig.add_trace(go.Scatter(
            x=rc.index, y=rc[col], mode="lines", name=col,
            line=dict(color=lab.PALETTE[i % len(lab.PALETTE)], width=1.8),
        ))
    fig.add_hline(y=0, line_color="#94a3b8")
    layout(fig, title=f"Rolling correlation vs primary ({rw} obs)", height=380,
           yaxis_title="ρ")
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Lead-lag cross-correlogram")
    other_labels = [c for c in aligned.columns if c != aligned.columns[0]]
    lead_label = st.selectbox("Companion for lead-lag analysis", other_labels)
    max_lag_hi = min(60, max(6, len(aligned) // 20))
    max_lag = st.slider("Max lead/lag (periods)", 3, max_lag_hi, min(12, max_lag_hi))
    ll = lab.lead_lag_corr(aligned[aligned.columns[0]], aligned[lead_label], max_lag)
    colors = [
        C_BLUE if (np.isfinite(v) and v >= 0) else
        (C_RED if np.isfinite(v) else "#94a3b8")
        for v in ll["corr"]
    ]
    fig = go.Figure(go.Bar(
        x=ll["lag"], y=ll["corr"], marker_color=colors,
        name="cross-correlation",
    ))
    n_min = int(ll["n"].min()) if len(ll) else 10
    band = 1.96 / np.sqrt(max(1, n_min))
    fig.add_hline(y=band, line_dash="dash", line_color="#94a3b8")
    fig.add_hline(y=-band, line_dash="dash", line_color="#94a3b8")
    layout(
        fig, title=f"ρ( primary(t), {lead_label}(t−lag) ) — positive lag ⇒ companion leads",
        height=340, xaxis_title="lag (periods)", yaxis_title="ρ", unified=False,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Dashed lines: ±1.96/√n ({band:+.2f}) significance band — bars beyond it "
        "are significant at ~5%."
    )


# --------------------------------------------------------------------------- #
# Data loading & sidebar controls
# --------------------------------------------------------------------------- #
catalog = get_catalog()
if catalog.empty:
    st.error("No series found in the warehouse (`marts.dim_series`). Run the dbt build first.")
    st.stop()

catalog = catalog.fillna("")

with st.sidebar:
    st.header("📡 Signal Lab")
    st.caption("Econometric dissection of a single macro signal.")

    label_to_id = {
        f"{r.series_id} — {r.title}".strip(" —"): r.series_id for r in catalog.itertuples()
    }
    selected_label = st.selectbox("Macro series", list(label_to_id))
    series_id = label_to_id[selected_label]
    meta = catalog[catalog.series_id == series_id].iloc[0]

    obs = get_obs(series_id)
    if obs.empty:
        st.warning("This series has no observations yet.")

    lo = obs.obs_date.min() if not obs.empty else pd.Timestamp("2000-01-01")
    hi = obs.obs_date.max() if not obs.empty else pd.Timestamp.today().normalize()
    date_range = st.date_input(
        "Analysis window", value=(lo.date(), hi.date()),
        min_value=lo.date(), max_value=hi.date(),
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        start, end = lo, hi

    transform_label = st.selectbox("Series transform", list(lab.TRANSFORMS))
    kind = lab.TRANSFORMS[transform_label]
    base_ts = None
    if kind == "index":
        base_ts = pd.Timestamp(st.date_input(
            "Index base date", value=lo.date(), min_value=lo.date(), max_value=hi.date(),
        ))

    freq_label = str(meta.frequency).strip().upper()
    period_guess = 12 if freq_label.startswith("M") else 4 if freq_label.startswith("Q") \
        else 52 if freq_label.startswith("W") else 7

    with st.expander("⏳ Time filtering (applied after transform)", expanded=False):
        filter_label = st.selectbox("Filter", list(lab.FILTERS), index=0)
        fkind = lab.FILTERS[filter_label]
        params: dict = {}
        n_obs = len(obs)
        if fkind == "hp":
            defaults = lab.default_filter_params(fkind, period_guess)
            presets = [100.0, 1600.0, 14400.0, 129600.0, 270400.0, 1e6, 1e8, 1e10]
            lam = defaults["lambda"]
            idx = min(range(len(presets)), key=lambda i: abs(presets[i] - lam))
            params["lambda"] = st.selectbox("Smoothing λ", presets, index=idx)
        elif fkind == "bk":
            d = lab.default_filter_params(fkind, period_guess)
            params["low"] = st.slider("Low cut (periods)", 2, 200, int(d["low"]))
            params["high"] = st.slider("High cut (periods)", 3, 600, int(d["high"]))
            max_k = max(4, min(200, n_obs // 2 - 1))
            params["K"] = st.slider("Lead/lag K", 4, max(8, max_k), int(min(d["K"], max_k)))
        elif fkind == "cf":
            d = lab.default_filter_params(fkind, period_guess)
            params["low"] = st.slider("Low cut (periods)", 2, 200, int(d["low"]))
            params["high"] = st.slider("High cut (periods)", 3, 600, int(d["high"]))
        elif fkind in ("bw_low", "bw_high", "bw_band"):
            params["order"] = st.slider("Butterworth order", 2, 8, 4)
            if fkind == "bw_low":
                params["cutoff"] = st.slider("Cutoff period (samples)", 2, 600, 24)
            elif fkind == "bw_high":
                params["cutoff"] = st.slider("Cutoff period (samples)", 2, 600, 12)
            else:
                params["low"] = st.slider("Low cut (periods)", 2, 300, 6)
                params["high"] = st.slider("High cut (periods)", 3, 600, 32)
        elif fkind == "ma":
            params["window"] = st.slider("Window (periods)", 3, 301, 2 * period_guess + 1, step=2)
        elif fkind == "ema":
            params["span"] = st.slider("Span", 2, 200, period_guess)
        if fkind != "none":
            component = st.radio(
                "Feed downstream analysis with",
                ["pass band", "complement", "original (unfiltered)"],
                index=0,
            )
        else:
            component = "original (unfiltered)"

    grain_options = ["native (runtime)"] + get_grains(series_id)
    grain_choice = st.selectbox(
        "Data grain",
        grain_options,
        help="Resampled grains and their transforms are precomputed in the dbt "
             "marts (`fct_macro_series_grains` / `fct_macro_series_transforms`). "
             "`native` keeps the runtime calendar alignment.",
    )

    companion_labels = [l for l in label_to_id if label_to_id[l] != series_id]
    companions = st.multiselect(
        "Companion series (correlation lab)", companion_labels, max_selections=6,
        help="Aligned onto the primary calendar and used for correlation maps.",
    )

# --------------------------------------------------------------------------- #
# Analysis pipeline
# --------------------------------------------------------------------------- #
st.title("📡 Signal Lab — Time-Series Econometrics")
title = meta.title or series_id
st.caption(
    f"**{title}** · `{series_id}` · unit: {meta.unit or '—'} · frequency: "
    f"{meta.frequency or '—'} · category: {meta.category or '—'} · country: {meta.country or '—'}"
)

windowed = obs[(obs.obs_date >= start) & (obs.obs_date <= end)] if not obs.empty else obs
prepared, offset, period = prepare_series(windowed, meta.frequency)
if len(prepared) < lab.MIN_POINTS:
    st.error(
        f"Only {len(prepared)} observations in the selected window — "
        f"need ≥ {lab.MIN_POINTS}. Widen the window."
    )
    st.stop()

# --- dbt-mart grain override: resampled series precomputed in the warehouse ---
dwh_grain = None
if grain_choice != "native (runtime)":
    gdf = get_grain_df(series_id, grain_choice)
    gdf = gdf[(gdf["period_date"] >= start) & (gdf["period_date"] <= end)]
    if len(gdf) >= lab.MIN_POINTS:
        prepared = pd.Series(
            gdf["value"].to_numpy(),
            index=pd.to_datetime(gdf["period_date"]),
            name="value",
        ).sort_index()
        period = GRAIN_PERIOD[grain_choice]
        dwh_grain = grain_choice
    else:
        st.warning(
            f"Only {len(gdf)} {grain_choice}-grain observations in the window — "
            "falling back to the native grain."
        )

gap_days = lab.median_gap_days(prepared)
offset_name = GRAIN_LABEL.get(dwh_grain) or lab.offset_label(offset)

# --- transform: prefer the dbt-precomputed value, fall back to runtime ---
dwh_transform = DWH_TRANSFORMS.get(kind) if dwh_grain else None
analysis = None
dwh_used = False
if dwh_transform:
    tdf = get_transform_df(series_id, dwh_grain, dwh_transform)
    tdf = tdf[(tdf["period_date"] >= start) & (tdf["period_date"] <= end)]
    if len(tdf) >= lab.MIN_POINTS:
        analysis = pd.Series(
            tdf["value"].to_numpy(),
            index=pd.to_datetime(tdf["period_date"]),
            name="value",
        ).sort_index()
        dwh_used = True
        if kind == "index" and base_ts is not None:
            # dbt stores index_100 with base = series inception; rebase to the
            # chosen base date via the stored ratio.
            base_val = float(analysis.asof(pd.Timestamp(base_ts)))
            if np.isfinite(base_val) and base_val != 0:
                analysis = analysis / base_val * 100.0
            else:
                analysis = None
                dwh_used = False

if analysis is None:
    try:
        analysis = lab.transform_series(prepared, kind, base=base_ts, period=period)
    except ValueError as exc:
        st.warning(f"{exc} — falling back to the raw level.")
        analysis = prepared.astype(float)
        kind = "level"

filter_result = None
filter_input = analysis
if fkind != "none":
    try:
        filter_result = cached_filter(analysis, fkind, params)
    except ValueError as exc:
        st.warning(f"Filter skipped: {exc}")

comp_label = "original"
if filter_result is not None:
    if component == "pass band":
        analysis = lab.sanitize(filter_result["pass"])
        comp_label = filter_result["pass_label"]
    elif component == "complement":
        analysis = lab.sanitize(filter_result["comp"])
        comp_label = filter_result["comp_label"]

chain = transform_label
if dwh_grain:
    chain += f" · {dwh_grain} grain"
    chain += " (dbt mart)" if dwh_used else " (runtime — Loess/fallback not in SQL)"
if filter_result is not None and component != "original (unfiltered)":
    chain += f" → {filter_label} ({comp_label})"

st.markdown(
    f"**{len(prepared):,}** observations · {prepared.index.min():%Y-%m-%d} → "
    f"{prepared.index.max():%Y-%m-%d} · {offset_name} (period {period}, "
    f"{gap_days:g}-day spacing) · analysing **{chain}**"
)

if len(analysis) < lab.MIN_POINTS:
    st.error("The transformed/filtered series has too few usable points — relax the transform.")
    st.stop()

ctx = dict(
    prepared=prepared, analysis=analysis, offset=offset, period=period,
    gap_days=gap_days, meta=meta, series_id=series_id, title=title,
    filter_result=filter_result, filter_input=filter_input, fkind=fkind, params=params,
    companion_labels=companions, label_to_id=label_to_id,
    offset_name=offset_name, chain=chain, catalog=catalog, start=start, end=end,
    dwh_grain=dwh_grain,
)

# --------------------------------------------------------------------------- #
# Tabs (each body isolated so one failure cannot blank the page)
# --------------------------------------------------------------------------- #
tab_overview, tab_calendar, tab_decomp, tab_cycle, tab_freq, tab_filter, \
    tab_dist, tab_corr = st.tabs([
        "📌 Overview", "📅 Calendar & performance", "🧩 Decomposition",
        "🔄 Cyclicality", "🌊 Frequency domain", "🎚️ Filters",
        "📊 Distribution & risk", "🔗 Multi-series correlation",
    ])

with tab_overview:
    guarded("Overview", lambda: render_overview(ctx))
with tab_calendar:
    guarded("Calendar & performance", lambda: render_calendar(ctx))
with tab_decomp:
    guarded("Decomposition", lambda: render_decomposition(ctx))
with tab_cycle:
    guarded("Cyclicality", lambda: render_cyclicality(ctx))
with tab_freq:
    guarded("Frequency domain", lambda: render_frequency(ctx))
with tab_filter:
    guarded("Filters", lambda: render_filters(ctx))
with tab_dist:
    guarded("Distribution & risk", lambda: render_distribution(ctx))
with tab_corr:
    guarded("Multi-series correlation", lambda: render_correlation(ctx))
