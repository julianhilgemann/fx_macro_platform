"""Volatility Studio — the volatility → probability pipeline, per selected series.

Pick any warehouse series, and the page runs the chain from
``volatility_pipeline.py`` end to end on it: returns → σ estimators →
diagnostics → BIC-selected GARCH → mean-reverting horizon σ → simulated
distribution → walk-forward interval backtest.

Everything analytical lives in :mod:`volatility`; this file is presentation
plus the Streamlit cache layer. The visuals follow the reference report
(``volatility-report.html``): estimator fan chart, ACF of r and r², QQ plots,
term-structure decomposition, terminal-distribution densities, PIT histogram,
coverage bars and out-of-sample intervals.
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
from scipy import stats

import volatility as V
from data import load_catalog, load_observations
from statsmodels.stats.diagnostic import het_arch as _het_arch
from forecast import prepare_series

st.set_page_config(
    page_title="Volatility Studio — σ → probability",
    page_icon="🌊",
    layout="wide",
)

# --------------------------------------------------------------------------- #
# Style — same palette as the other pages, plus the report's measure/truth pair
# --------------------------------------------------------------------------- #
C_BLUE, C_ORANGE, C_GREEN, C_AMBER = "#2563eb", "#ea580c", "#059669", "#d97706"
C_SLATE, C_RED, C_PURPLE = "#64748b", "#dc2626", "#7c3aed"
C_TRUTH = "#A4342B"  # the report's "truth/normal-theory" red
C_MEASURE = "#1B5FA8"  # the report's "measure" blue

PLOT = dict(template="plotly_white", hovermode="x unified")
MARGIN = dict(l=10, r=10, t=50, b=10)

# sidebar label -> volatility.SPECS key ("auto" escalates by BIC)
SPEC_LABELS = {"Auto — escalate by BIC": "auto", **{k: k for k in V.SPECS}}


def fmt_pct(x, digits: int = 1) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return "—"
    return "—" if not np.isfinite(f) else f"{f * 100:.{digits}f}%"


def fmt_num(x, digits: int = 2) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(f):
        return "—"
    if abs(f) >= 10_000:
        return f"{f:,.0f}"
    return f"{f:,.{digits}f}"


def fmt_p(p) -> str:
    try:
        f = float(p)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(f):
        return "—"
    if f < 1e-4:
        return f"{f:.1e}"
    return f"{f:.3f}"



def metric_row(items: list[tuple[str, str, str]]) -> None:
    """Render a strip of value/label cards (the report's readout row)."""
    cols = st.columns(len(items))
    for col, (value, label, colour) in zip(cols, items):
        col.markdown(
            f"<div style='padding:2px 0 8px'>"
            f"<div style='font-size:1.45rem;font-weight:600;color:{colour};"
            f"line-height:1.15'>{value}</div>"
            f"<div style='font-size:0.78rem;color:#6B7681'>{label}</div></div>",
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- #
# Cache layer
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300, show_spinner=False)
def get_catalog() -> pd.DataFrame:
    return load_catalog()


@st.cache_data(ttl=300, show_spinner=False)
def get_series(series_id: str, lo: str | None, hi: str | None) -> pd.DataFrame:
    obs = load_observations(series_id)
    if obs.empty:
        return obs
    if lo:
        obs = obs[obs.obs_date >= pd.Timestamp(lo)]
    if hi:
        obs = obs[obs.obs_date <= pd.Timestamp(hi)]
    return obs


@st.cache_data(ttl=600, show_spinner=False, max_entries=24)
def fit_bundle(prices: pd.Series, win: int, spec: str, est_window: int,
               lam: float, synth_bars: int, ohlc: pd.DataFrame | None) -> dict:
    """Everything that depends on the estimation window but *not* on H.

    Estimators, diagnostics, the GARCH fit, structural params and the
    conditional-σ path. Cached by value, so moving the horizon slider does not
    refit the model.
    """
    s = pd.Series(prices).astype(float).dropna()
    ann = V.ann_factor(s.index)
    ppy = V.periods_per_year(s.index)
    r, kind = V.period_returns(s)
    r_win = r.iloc[-int(win):] if win else r

    bars = ohlc
    bars_source = "provided" if ohlc is not None else "none"
    if bars is None and synth_bars and synth_bars > 1:
        bars = V.synthetic_ohlc(s, synth_bars)
        bars_source = "synthetic"

    fit = V.fit_model(r_win, spec=spec)
    stx = V.structure(fit.res, ppy)
    zres = (fit.res.resid / fit.res.conditional_volatility).dropna()
    return {
        "ann": ann,
        "ppy": ppy,
        "returns": r,
        "fit_returns": r_win,
        "return_kind": kind,
        "diagnostics": V.diagnose(r_win),
        "model": fit.name,
        "bic_table": fit.bic_table,
        "fit_failures": fit.failures,
        "structure": stx,
        "cond_vol": fit.res.conditional_volatility * ann,
        "cond_vol_index": fit.res.conditional_volatility.index,
        "estimators": V.estimator_table(r_win, bars, ann, est_window, lam),
        "acf": V.acf_data(r_win),
        "qq_raw": V.qq_data(r_win.values / (r_win.std() or 1.0), "normal"),
        "qq_resid_norm": V.qq_data(zres.values, "normal"),
        "qq_resid_t": V.qq_data(zres.values, "t", stx.get("nu")),
        "residuals": {
            "excess_kurtosis": V._safe_p(stats.kurtosis, zres),
            "arch_lm_p": V._safe_p(lambda: _het_arch(zres, nlags=10)[1]),
            "skew": V._safe_p(stats.skew, zres),
            "n": int(len(zres)),
        },
        "bars_source": bars_source,
        "bars_info": V.ohlc_report(bars) if bars is not None else None,
        "n_fit": int(len(r_win)),
        "restricted": bool(win and len(r) > len(r_win)),
    }


@st.cache_data(ttl=600, show_spinner=False, max_entries=48)
def horizon_bundle(prices: pd.Series, win: int, spec: str, H: int, nsim: int,
                   n_events: int, event_move: float) -> dict:
    """The forward-looking half: σ path, events and the simulated distribution."""
    s = pd.Series(prices).astype(float).dropna()
    ann = V.ann_factor(s.index)
    ppy = V.periods_per_year(s.index)
    r, _ = V.period_returns(s)
    r_win = r.iloc[-int(win):] if win else r
    fit = V.fit_model(r_win, spec=spec)
    stx = V.structure(fit.res, ppy)
    hz = V.horizon_sigma(fit.res, H, ppy, st=stx)
    dist = V.distribution(fit.res, H, nsim=nsim, S0=float(s.iloc[-1]), sigma_H=hz["sigma_H"])
    ev = V.add_events(hz["sigma_H"], n_events, event_move, ann) if n_events else None
    return {
        "horizon": hz,
        "distribution": dist,
        "events": ev,
        "ann": ann,
        "drift": {
            "mu_ann": float(r_win.mean() * ppy),
            "se_ann": float(r_win.std() * np.sqrt(ppy) / np.sqrt(max(len(r_win) / ppy, 1e-9))),
            "contribution_over_H": float(r_win.mean() * H),
            "sigma_over_H": hz["sigma_H"],
            "years": float(len(r_win) / ppy),
        },
        "model": fit.name,
    }


@st.cache_data(ttl=600, show_spinner=False, max_entries=8)
def backtest_bundle(prices: pd.Series, win: int, H: int, start: int, nsim: int,
                    max_windows: int, spec: str = V.BACKTEST_SPEC) -> dict:
    s = pd.Series(prices).astype(float).dropna()
    r, _ = V.period_returns(s)
    r_win = r.iloc[-int(win):] if win else r
    bt = V.backtest(r_win, H=H, start=start, win=min(win, 1000), nsim=nsim,
                    spec=spec, max_windows=max_windows)
    bt.attrs["H"] = H
    return {
        "table": bt,
        "summary": V.backtest_summary(bt, levels=(0.90, 0.50)),
        "n_available": int(bt.attrs.get("n_available", len(bt))),
        "truncated": bool(bt.attrs.get("truncated", False)),
    }


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def fig_history(s: pd.Series, est_start: pd.Timestamp | None, title: str,
                unit: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name="Level",
                             line=dict(color=C_BLUE, width=1.4)))
    if est_start is not None:
        fig.add_vrect(x0=est_start, x1=s.index[-1], fillcolor=C_AMBER, opacity=0.07,
                      line_width=0)
        fig.add_vline(x=est_start, line_dash="dash", line_color=C_AMBER,
                      annotation_text="estimation window", annotation_position="top left",
                      annotation_font_size=11)
    fig.update_layout(title=title, yaxis_title=unit or "value", height=340,
                      margin=dict(l=10, r=10, t=56, b=10), showlegend=False,
                      **PLOT)
    return fig


def fig_estimators(est: pd.DataFrame, cond_vol: pd.Series, cond_idx,
                   stx: dict) -> go.Figure:
    """The estimator fan: every σ estimate plus the GARCH conditional path."""
    fig = go.Figure()
    palette = [C_BLUE, C_SLATE, C_GREEN, C_AMBER, C_PURPLE, C_RED]
    for i, row in enumerate(est.to_dict("records")):
        fig.add_trace(go.Scatter(
            x=row["series"].index, y=row["series"].values, name=row["estimator"],
            line=dict(color=palette[i % len(palette)], width=1.3)))
    fig.add_trace(go.Scatter(
        x=cond_idx, y=cond_vol.values, name="GARCH conditional σ",
        line=dict(color=C_TRUTH, width=1.8)))
    if np.isfinite(stx["sigma_inf_ann"]):
        fig.add_hline(y=stx["sigma_inf_ann"], line_dash="dot", line_color=C_TRUTH,
                      opacity=0.6, annotation_text="σ∞ (long-run)",
                      annotation_font_size=11)
    fig.update_layout(
        title="Four estimates of the same hidden quantity (annualised σ)",
        yaxis_title="annualised σ", height=430,
        margin=dict(l=10, r=10, t=70, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        **PLOT)
    return fig


def fig_current_bars(est: pd.DataFrame, stx: dict, hz_sigma: float) -> go.Figure:
    """Today's reading per estimator, against the conditional σ and σ∞."""
    rows = est.sort_values("value")
    fig = go.Figure(go.Bar(
        x=rows["value"].values, y=rows["estimator"].values, orientation="h",
        marker_color=[C_SLATE if r["estimator"].startswith(("Parkinson", "Garman", "Yang"))
                      else C_MEASURE for r in rows.to_dict("records")],
        text=[fmt_pct(v) for v in rows["value"].values], textposition="outside",
    ))
    if np.isfinite(stx["sigma_today_ann"]):
        fig.add_vline(x=stx["sigma_today_ann"], line_color=C_TRUTH, line_width=2,
                      annotation_text="GARCH σ today", annotation_font_size=11)
    if np.isfinite(stx["sigma_inf_ann"]):
        fig.add_vline(x=stx["sigma_inf_ann"], line_dash="dot", line_color=C_AMBER,
                      annotation_text="σ∞", annotation_font_size=11)
    if np.isfinite(hz_sigma):
        fig.add_vline(x=hz_sigma, line_dash="dash", line_color=C_GREEN,
                      annotation_text="horizon σ (H)", annotation_position="bottom right",
                      annotation_font_size=11)
    fig.update_layout(title="Volatility today: what each estimator says",
                      xaxis_title="annualised σ", height=340,
                      margin=dict(l=10, r=10, t=60, b=10), showlegend=False, **PLOT)
    return fig


def fig_acf(acf: dict) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, subplot_titles=(
        "ACF of returns — should be flat", "ACF of squared returns — clustering"))
    for col, key, colour in ((1, "r", C_BLUE), (2, "r2", C_ORANGE)):
        fig.add_trace(go.Bar(x=acf["lags"], y=acf[key], marker_color=colour,
                             name=key), row=1, col=col)
        fig.add_hline(y=acf["band"], line_dash="dash", line_color=C_SLATE,
                      row=1, col=col)
        fig.add_hline(y=-acf["band"], line_dash="dash", line_color=C_SLATE,
                      row=1, col=col)
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=60, b=10),
                      showlegend=False, **PLOT)
    fig.update_xaxes(title_text="lag")
    return fig


def fig_qq(qq: dict, title: str, colour: str) -> go.Figure:
    th, em = np.asarray(qq["theoretical"]), np.asarray(qq["empirical"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=th, y=em, mode="markers", name="empirical",
                             marker=dict(color=colour, size=3, opacity=0.55)))
    if len(th) > 1:
        lo, hi = float(np.min(th)), float(np.max(th))
        fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines",
                                 name="45° line",
                                 line=dict(color=C_SLATE, dash="dash", width=1)))
    fig.update_layout(title=title, xaxis_title="theoretical", yaxis_title="empirical",
                      height=300, margin=dict(l=10, r=10, t=56, b=10),
                      showlegend=False, **PLOT)
    return fig


def fig_cond_vol(cond_vol: pd.Series, cond_idx, est: pd.DataFrame,
                 stx: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cond_idx, y=cond_vol.values,
                             name="GARCH conditional σ",
                             line=dict(color=C_TRUTH, width=1.6)))
    roll = est[est["estimator"].str.startswith(("20p close-to-close", "60p close-to-close"))]
    if not roll.empty:
        row = roll.iloc[0]
        fig.add_trace(go.Scatter(x=row["series"].index, y=row["series"].values,
                                 name=row["estimator"],
                                 line=dict(color=C_BLUE, width=1.1)))
    ew = est[est["estimator"].str.startswith("EWMA")]
    if not ew.empty:
        fig.add_trace(go.Scatter(x=ew.iloc[0]["series"].index, y=ew.iloc[0]["series"].values,
                                 name=ew.iloc[0]["estimator"],
                                 line=dict(color=C_GREEN, width=1.1)))
    if np.isfinite(stx["sigma_inf_ann"]):
        fig.add_hline(y=stx["sigma_inf_ann"], line_dash="dot", line_color=C_AMBER,
                      annotation_text="σ∞", annotation_font_size=11)
    fig.update_layout(title="Conditional σ through time — the spike, and its decay",
                      yaxis_title="annualised σ", height=380,
                      margin=dict(l=10, r=10, t=60, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      **PLOT)
    return fig


def fig_bic(tbl: pd.DataFrame, best: str) -> go.Figure:
    d = tbl.sort_values("bic")
    colours = [C_GREEN if s == best else C_SLATE for s in d["specification"]]
    fig = go.Figure(go.Bar(x=d["bic"].values, y=d["specification"].values,
                           orientation="h", marker_color=colours,
                           text=[f"{b:,.1f}" for b in d["bic"].values],
                           textposition="outside"))
    fig.update_layout(title="BIC by specification — lower is better",
                      xaxis_title="BIC", height=280,
                      margin=dict(l=10, r=10, t=56, b=10), showlegend=False, **PLOT)
    fig.update_xaxes(rangemode="tozero")
    return fig


def fig_term_structure(hz: dict, ev: dict | None, stx: dict) -> go.Figure:
    ts = np.asarray(hz["term_structure"])
    tsl = np.asarray(hz["term_structure_longrun"])
    x = np.arange(1, len(ts) + 1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=ts, name="fitted model",
                             line=dict(color=C_MEASURE, width=2)))
    fig.add_trace(go.Scatter(x=x, y=tsl, name="mean-reversion path (persistence ^ h)",
                             line=dict(color=C_TRUTH, width=1.6, dash="dash")))
    fig.add_trace(go.Scatter(x=x, y=np.full(len(x), hz["sigma_today"]), name="σ today (flat)",
                             line=dict(color=C_AMBER, width=1.2, dash="dot")))
    if np.isfinite(stx["sigma_inf_ann"]) and np.isfinite(tsl).any():
        fig.add_trace(go.Scatter(x=x, y=np.full(len(x), stx["sigma_inf_ann"]), name="σ∞",
                                 line=dict(color=C_SLATE, width=1, dash="dot")))
    if ev is not None and np.isfinite(ev["sigma_total"]):
        fig.add_hline(y=ev["sigma_total"], line_color=C_PURPLE, line_width=1.5,
                      annotation_text=f"+{ev['n_events']} events → σ_H",
                      annotation_font_size=11)
    fig.update_layout(
        title=f"Volatility term structure — σ_h for h = 1…{hz['H']}",
        xaxis_title="horizon h (periods)", yaxis_title="annualised σ", height=400,
        margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), **PLOT)
    return fig


def fig_term_bars(hz: dict, ev: dict | None, ann: float) -> go.Figure:
    """Per-period variance budget: diffusive (GARCH) plus event contributions."""
    ts = np.asarray(hz["term_structure"])
    var = ts**2
    x = np.arange(1, len(var) + 1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=var, name="diffusive (GARCH)", marker_color=C_MEASURE))
    if ev is not None and np.isfinite(ev.get("sigma_event", np.nan)):
        n = int(ev["n_events"])
        # spread the event variance over the first n periods of the horizon
        extra = np.zeros_like(var)
        per = (ev["sigma_event"] * ann) ** 2
        extra[: min(n, len(var))] = per
        fig.add_trace(go.Bar(x=x, y=extra, name=f"event variance ({n} events)",
                             marker_color=C_PURPLE))
    fig.update_layout(title="Variance budget over the horizon",
                      xaxis_title="horizon h (periods)",
                      yaxis_title="variance contribution (σ²)",
                      barmode="stack", height=320,
                      margin=dict(l=10, r=10, t=56, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      **PLOT)
    return fig


def fig_distribution(dist: dict, unit: str) -> go.Figure:
    """Simulated terminal distribution vs. the naive lognormal straw man."""
    frame = V.distribution_frame(dist)
    naive = dist["naive"]
    sd = naive["sd"]
    fig = make_subplots(rows=1, cols=2, subplot_titles=(
        "Terminal return distribution (density)", "Cumulative — where the tails differ"))
    fig.add_trace(go.Scatter(x=frame["ret_pct"], y=frame["density"], mode="lines",
                             name=f"GARCH simulation ({dist['nsim']:,} paths)",
                             fill="tozeroy", fillcolor="rgba(27,95,168,0.18)",
                             line=dict(color=C_MEASURE, width=1.6)), row=1, col=1)
    if np.isfinite(sd) and sd > 0:
        xs = np.linspace(*np.percentile(np.asarray(dist["terminal_ret"]) * 100, [0.2, 99.8]), 300)
        fig.add_trace(go.Scatter(x=xs, y=stats.norm.pdf(xs, 0, sd * 100), mode="lines",
                                 name="naive lognormal", line=dict(color=C_RED, width=1.6)),
                      row=1, col=1)
    term = np.sort(np.asarray(dist["terminal_ret"]) * 100)
    cdf = np.arange(1, len(term) + 1) / len(term)
    fig.add_trace(go.Scatter(x=term, y=cdf, mode="lines", name="GARCH simulation",
                             line=dict(color=C_MEASURE, width=1.8)), row=1, col=2)
    if np.isfinite(sd) and sd > 0:
        xs = np.linspace(term[0], term[-1], 300)
        fig.add_trace(go.Scatter(x=xs, y=stats.norm.cdf(xs / 100, 0, sd), mode="lines",
                                 name="naive lognormal",
                                 line=dict(color=C_RED, width=1.6, dash="dash")),
                      row=1, col=2)
        fig.add_hline(y=0.05, line_dash="dot", line_color=C_SLATE, row=1, col=2)
        fig.add_hline(y=0.50, line_dash="dot", line_color=C_SLATE, row=1, col=2)
        fig.add_hline(y=0.95, line_dash="dot", line_color=C_SLATE, row=1, col=2)
    fig.update_xaxes(title_text="return over horizon (%)", row=1, col=1)
    fig.update_xaxes(title_text="return over horizon (%)", row=1, col=2)
    fig.update_yaxes(title_text="density", row=1, col=1)
    fig.update_yaxes(title_text="cumulative probability", row=1, col=2)
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=60, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0),
                      hovermode="x", template="plotly_white")
    return fig


def fig_cone(s: pd.Series, dist: dict, H: int) -> go.Figure:
    """History plus the simulated median path and 5/95 path band."""
    fig = go.Figure()
    hist = s.iloc[-min(len(s), 4 * H + 60):]
    fig.add_trace(go.Scatter(x=hist.index, y=hist.values, name="history",
                             line=dict(color=C_BLUE, width=1.4)))
    future = pd.bdate_range(hist.index[-1], periods=H + 1,
                            freq=pd.tseries.frequencies.to_offset(
                                pd.infer_freq(s.index[-40:]) or "B"))[1:]
    if len(future) != H:
        future = pd.date_range(hist.index[-1], periods=H + 1, freq="D")[1:]
    S0 = float(s.iloc[-1])
    fig.add_trace(go.Scatter(x=future, y=S0 * (1 + dist["q95_path"]), mode="lines",
                             line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=future, y=S0 * (1 + dist["q05_path"]), mode="lines",
                             line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(27,95,168,0.18)",
                             name="90% path band"))
    fig.add_trace(go.Scatter(x=future, y=S0 * (1 + dist["median_path"]), mode="lines",
                             name="median simulated path",
                             line=dict(color=C_MEASURE, width=2)))
    fig.update_layout(title=f"Where the price could go over {H} periods (percentile cone)",
                      yaxis_title="level", height=380,
                      margin=dict(l=10, r=10, t=60, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      **PLOT)
    return fig


def fig_pit(bt: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not bt.empty:
        n_bins = 20
        fig.add_trace(go.Histogram(x=bt["pit"].dropna(), nbinsx=n_bins,
                                   marker_color=C_MEASURE, name="PIT"))
        fig.add_hline(y=len(bt) / n_bins, line_dash="dot", line_color=C_SLATE,
                      annotation_text="uniform", annotation_font_size=11)
    fig.update_layout(title="PIT histogram — uniform means honest intervals",
                      xaxis_title="PIT (realised quantile of the forecast)",
                      yaxis_title="count", height=320,
                      margin=dict(l=10, r=10, t=56, b=10), showlegend=False, **PLOT)
    return fig


def fig_coverage(summary: pd.DataFrame) -> go.Figure:
    """Actual coverage per method, with the nominal levels as reference lines."""
    fig = go.Figure()
    if summary.empty:
        fig.update_layout(title="Coverage — no windows", height=320,
                          template="plotly_white")
        return fig
    for lvl, colour in ((0.90, C_MEASURE), (0.50, C_ORANGE)):
        d = summary[summary["nominal"] == lvl]
        if d.empty:
            continue
        fig.add_trace(go.Bar(
            x=d["method"], y=d["actual"], name=f"nominal {lvl:.0%}",
            marker_color=colour, text=[fmt_pct(v) for v in d["actual"]],
            textposition="outside"))
        fig.add_hline(y=lvl, line_dash="dash", line_color=colour, opacity=0.8,
                      annotation_text=f"nominal {lvl:.0%}",
                      annotation_position="right", annotation_font_size=11)
    fig.update_layout(title="Coverage: actual vs. nominal, per interval method",
                      yaxis_title="actual coverage", height=340,
                      margin=dict(l=10, r=10, t=56, b=10), barmode="group",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      template="plotly_white")
    fig.update_yaxes(range=[0, 1.12])
    return fig


def fig_oos_intervals(bt: pd.DataFrame) -> go.Figure:
    """Out-of-sample 90% intervals vs. what actually happened."""
    fig = go.Figure()
    if bt.empty:
        fig.update_layout(title="Out-of-sample intervals — no windows", height=360)
        return fig
    x = bt["date"]
    fig.add_trace(go.Scatter(x=x, y=bt["sim_hi90"], mode="lines",
                             line=dict(color=C_MEASURE, width=1, dash="dot"),
                             name="simulated t 90% band"))
    fig.add_trace(go.Scatter(x=x, y=bt["sim_lo90"], mode="lines",
                             line=dict(color=C_MEASURE, width=1, dash="dot"),
                             showlegend=False, fill="tonexty",
                             fillcolor="rgba(27,95,168,0.10)"))
    fig.add_trace(go.Scatter(x=x, y=bt["var_hi90"], mode="lines",
                             line=dict(color=C_GREEN, width=1), name="var + normal 90%"))
    fig.add_trace(go.Scatter(x=x, y=bt["var_lo90"], mode="lines",
                             line=dict(color=C_GREEN, width=1), showlegend=False))
    breached = (bt[bt["breach90_sim"].astype(bool)]
                if "breach90_sim" in bt.columns else bt.iloc[[]])
    fig.add_trace(go.Scatter(x=bt["date"], y=bt["real"], mode="markers",
                             name="realised", marker=dict(color=C_BLUE, size=5)))
    if not breached.empty:
        fig.add_trace(go.Scatter(x=breached["date"], y=breached["real"], mode="markers",
                                 name="sim-t breach", marker=dict(color=C_RED, size=9,
                                                                  symbol="x")))
    fig.update_layout(title="Out-of-sample intervals (disjoint windows)",
                      yaxis_title="horizon return", height=380,
                      margin=dict(l=10, r=10, t=56, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      **PLOT)
    return fig


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
catalog = get_catalog()
if catalog.empty:
    st.error("No series found in the warehouse (`marts.dim_series`). Run the dbt build first.")
    st.stop()
catalog = catalog.fillna("")

st.title("🌊 Volatility Studio")
st.caption(
    "The volatility → probability pipeline: returns → σ estimators → diagnostics → "
    "BIC-selected GARCH → mean-reverting horizon σ → simulated distribution → "
    "interval backtest. Reference: `volatility_pipeline.py`."
)

with st.sidebar:
    st.header("Controls")

    freq_opts = sorted({str(f).upper() for f in catalog.frequency if str(f).strip()})
    want_daily = st.toggle("Daily / business-daily series only", value=True,
                           help="GARCH annualisation assumes one observation ≈ one trading day. "
                                "Monthly and quarterly series still work, but horizons are periods.")
    pool = catalog
    if want_daily:
        pool = catalog[catalog.frequency.astype(str).str.upper().isin(["D", "B", "DAILY"])]
        if pool.empty:
            pool = catalog

    search = st.text_input("Filter by id or title", "").strip().lower()
    if search:
        mask = (pool.series_id.str.lower().str.contains(search, regex=False)
                | pool.title.str.lower().str.contains(search, regex=False))
        filtered = pool[mask]
    else:
        filtered = pool
    if filtered.empty:
        st.warning("No series match that filter; showing all.")
        filtered = pool

    label_to_id = {
        f"{r.series_id} — {r.title}".strip(" —"): r.series_id
        for r in filtered.itertuples()
    }
    selected_label = st.selectbox("Macro series", list(label_to_id))
    series_id = label_to_id[selected_label]
    meta = catalog[catalog.series_id == series_id].iloc[0]

    obs_all = get_series(series_id, None, None)
    if obs_all.empty:
        st.error("This series has no observations yet.")
        st.stop()

    lo, hi = obs_all.obs_date.min(), obs_all.obs_date.max()
    date_range = st.date_input("Analysis window", value=(lo.date(), hi.date()),
                               min_value=lo.date(), max_value=hi.date())
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        start, end = lo, hi

    st.markdown("**Model & estimation**")
    spec_label = st.selectbox("GARCH specification", list(SPEC_LABELS),
                              index=0, help="Auto escalates by BIC through the reference's four specs.")
    est_window = st.slider("Estimator window (periods)", 5, 120, 20, step=5)
    lam = st.slider("EWMA λ", 0.80, 0.995, 0.94, step=0.005, format="%.3f")
    # the fit window can never exceed the observations actually available
    max_win = int(max(120, len(obs_all)))
    if max_win > 140:
        fit_win = st.slider("GARCH fit window (trailing periods)", 120, max_win,
                            int(min(max_win, 1500)), step=20,
                            help="Fitting 25 years of dailies is slow and mixes regimes; "
                                 "1 500 periods ≈ 6 years is the reference's choice of patience.")
    else:
        fit_win = max_win
        st.caption(f"GARCH fit window: all {max_win} periods (series is short).")

    st.markdown("**Horizon**")
    H = st.slider("Horizon H (periods)", 1, 250, 60, step=5)
    nsim = st.select_slider("Simulation paths", [2_000, 5_000, 20_000, 50_000], value=20_000)

    with st.expander("Events the model cannot see"):
        n_events = st.slider("Scheduled events in the horizon", 0, 10, 0)
        event_move = st.slider("Typical |move| per event", 0.0, 0.15, 0.045, step=0.005,
                               format="%.3f")

    with st.expander("Range estimators (need OHLC bars)"):
        st.caption("The warehouse is close-only, so Parkinson / Garman-Klass / Yang-Zhang "
                   "are unavailable unless bars are supplied.")
        synth_bars = st.slider("Synthesise bars from the close (span)", 0, 20, 0, step=1,
                               help="0 = off. A proxy only: the bar range is the close's own "
                                    "rolling range, so it carries no intraday information.")

    with st.expander("Backtest"):
        run_bt = st.checkbox("Run walk-forward backtest", value=False,
                             help="Refits the GJR-t model on every disjoint window. "
                                  "Updates on button press.")
        bt_H = st.slider("Backtest window H (periods)", 1, 60, 5, step=1)
        bt_max = st.slider("Max windows", 20, 400, 150, step=10)
        bt_nsim = st.select_slider("Paths per window", [500, 1_000, 2_000, 5_000], value=1_000)

st.markdown(
    f"**{meta.title or series_id}** · `{series_id}` · unit: {meta.unit or '—'} · "
    f"frequency: {meta.frequency or '—'} · category: {meta.category or '—'} · "
    f"country: {meta.country or '—'}"
)

windowed = obs_all[(obs_all.obs_date >= start) & (obs_all.obs_date <= end)]
if len(windowed) < 60:
    st.error(f"Only {len(windowed)} observations in the selected window — need ≥ 60.")
    st.stop()

prepared, offset, period = prepare_series(windowed, meta.frequency)
if len(prepared) < 60:
    st.error(f"After calendar alignment only {len(prepared)} points remain — need ≥ 60.")
    st.stop()

# `period` is the *seasonal* period (7 for daily), so frequency is judged from
# the observed observation rate instead.
if V.periods_per_year(prepared.index) < 100:
    st.warning(
        f"This series is not daily (aligned to `{offset}`, ~{V.periods_per_year(prepared.index):.0f} "
        "periods/year). The maths is period-based, so σ is annualised with the observed rate; "
        "GARCH horizons are in periods, not trading days."
    )

est_start = prepared.index[max(0, len(prepared) - int(fit_win))]
st.markdown(
    f"**{len(prepared):,}** observations · {prepared.index.min():%Y-%m-%d} → "
    f"{prepared.index.max():%Y-%m-%d} · aligned to `{offset}` · "
    f"GARCH fitted on the trailing **{min(fit_win, len(prepared)):,}** periods "
    f"(from {est_start:%Y-%m-%d})"
)

st.plotly_chart(
    fig_history(prepared, est_start, f"{meta.title or series_id} ({series_id})",
                meta.unit or "value"),
    width="stretch",
)

# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
try:
    with st.spinner("Fitting GARCH family and selecting by BIC …"):
        bundle = fit_bundle(prepared, int(fit_win), SPEC_LABELS[spec_label],
                            int(est_window), float(lam), int(synth_bars), None)
except Exception as exc:  # noqa: BLE001 — surface any fit failure as a card
    st.error(f"GARCH fit failed: {exc}")
    st.stop()

stx = bundle["structure"]
resid = bundle["residuals"]

with st.spinner("Aggregating the horizon and simulating paths …"):
    hz_bundle = horizon_bundle(prepared, int(fit_win), SPEC_LABELS[spec_label], int(H),
                               int(nsim), int(n_events), float(event_move))
hz = hz_bundle["horizon"]
dist = hz_bundle["distribution"]
ev = hz_bundle["events"]
drift = hz_bundle["drift"]

st.session_state.setdefault("vol_bt", None)
# Disjoint windows need data before the first forecast, so start well inside the
# sample; the window itself is capped at 1 000 periods like the reference.
bt_start = int(max(120, min(750, len(prepared) // 2)))
# "auto" selects a different spec per window, which would make the walk-forward
# comparison inconsistent — fall back to the reference's fixed GJR-t.
bt_spec = SPEC_LABELS[spec_label] if SPEC_LABELS[spec_label] != "auto" else V.BACKTEST_SPEC
bt_sig = (series_id, int(prepared.index.asi8[0]), int(prepared.index.asi8[-1]),
          int(fit_win), int(bt_H), int(bt_max), int(bt_nsim), bt_spec)
bt_state = st.session_state.get("vol_bt")
bt_valid = bool(bt_state and bt_state.get("sig") == bt_sig)
if run_bt and not bt_valid:
    with st.spinner(f"Backtesting: refitting on every disjoint {bt_H}-period window …"):
        try:
            st.session_state["vol_bt"] = {
                "sig": bt_sig,
                "data": backtest_bundle(prepared, int(fit_win), int(bt_H), bt_start,
                                        int(bt_nsim), int(bt_max), bt_spec),
            }
        except Exception as exc:  # noqa: BLE001
            st.session_state["vol_bt"] = {"sig": bt_sig, "data": None, "error": str(exc)}
    bt_state = st.session_state.get("vol_bt")

# --------------------------------------------------------------------------- #
# 0. Readout
# --------------------------------------------------------------------------- #
metric_row([
    (fmt_num(prepared.iloc[-1], 2), f"last level ({meta.unit or 'value'})", "#14181C"),
    (fmt_pct(stx["sigma_today_ann"]), "σ today (annualised)", C_TRUTH),
    (fmt_pct(stx["sigma_inf_ann"]), "σ∞ long-run", C_SLATE),
    (fmt_pct(hz["sigma_H"]), f"σ over H={H} periods", C_MEASURE),
    (fmt_pct(hz["sigma_H_naive"]), "naive √T would say", C_AMBER),
    (fmt_num(stx["persistence"], 4), "persistence", "#14181C"),
])
metric_row([
    (f"{dist['quantiles'][5]:+.1f}% – {dist['quantiles'][95]:+.1f}%",
     f"90% interval, {H} periods", C_MEASURE),
    (fmt_pct(dist["P_up_10"]), "P(+10% or more)", C_MEASURE),
    (fmt_pct(dist["P_down_10"]), "P(−10% or more)", C_MEASURE),
    (fmt_pct(dist["P_touch_down_15"]), "P(touch −15% at any point)", C_MEASURE),
    (fmt_pct(dist["E_abs_move_pct"] / 100), "E|move|", C_SLATE),
    (fmt_num(stx["half_life_periods"], 1) + "p", "half-life of a shock", C_SLATE),
])
if bundle["restricted"]:
    st.caption(
        f"σ∞ and the half-life divide by (1 − persistence), so they are weakly identified — "
        f"treat them as orders of magnitude. Persistence here is {stx['persistence']:.4f} "
        f"(fitted on {bundle['n_fit']:,} periods)."
    )

st.markdown("---")

# --------------------------------------------------------------------------- #
# 1. Estimating σ
# --------------------------------------------------------------------------- #
st.subheader("1 · Four estimates of the same hidden quantity")
st.markdown(
    "Volatility is never observed — it is inferred, and the inference is noisy: the "
    "relative standard error of a 20-period estimate is 1/√(2n) ≈ "
    f"{fmt_pct(bundle['diagnostics']['vol_rel_se'])}. Equal weights over a fixed window "
    "are the problem; exponential weights are the fix."
)
if bundle["bars_source"] == "none":
    st.info(
        "Only close-to-close and EWMA estimators are available: the warehouse stores one "
        "value per date, so there are no true OHLC bars for Parkinson / Garman-Klass / "
        "Yang-Zhang. Turn on *Synthesise bars from the close* in the sidebar to preview "
        "them — flagged as a proxy, not a measurement."
    )
else:
    info = bundle["bars_info"] or {}
    if bundle["bars_source"] == "synthetic":
        st.warning(
            f"Range estimators are computed on **synthetic** bars (rolling span, "
            f"mean high–low {info.get('mean_high_low_pct', float('nan')):.2f}%). The range "
            "is derived from closes, so these numbers are illustrative only."
        )
    elif info.get("bad_bars"):
        st.warning(f"{info['bad_bars']:,} malformed bars (high/low/close ordering) in the input.")

col_a, col_b = st.columns([3, 2])
col_a.plotly_chart(fig_estimators(bundle["estimators"], bundle["cond_vol"],
                                  bundle["cond_vol_index"], stx), width="stretch")
col_b.plotly_chart(fig_current_bars(bundle["estimators"], stx, hz["sigma_H"]),
                   width="stretch")
with st.expander("Estimator readings (annualised)"):
    tbl = bundle["estimators"][["estimator", "value", "needs_bars"]].copy()
    tbl["value"] = tbl["value"].map(lambda v: fmt_pct(v, 2))
    tbl["needs_bars"] = np.where(tbl["needs_bars"], "true OHLC bars", "close only")
    st.dataframe(tbl.rename(columns={"estimator": "estimator", "value": "σ today",
                                     "needs_bars": "input"}),
                 width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# 2. Diagnostics
# --------------------------------------------------------------------------- #
st.subheader("2 · Is a volatility model warranted?")
d = bundle["diagnostics"]
flag = "clustering present — GARCH is appropriate" if (
    np.isfinite(d["ljungbox_r2_p"]) and d["ljungbox_r2_p"] < 0.05
) else "no clustering detected — GARCH may just add parameters"
st.markdown(
    f"Two autocorrelation functions decide this: returns should show nothing, squared "
    f"returns slow decay. Here Ljung-Box on squared returns gives p = "
    f"{fmt_p(d['ljungbox_r2_p'])} and ARCH-LM(10) p = {fmt_p(d['arch_lm_p'])} — **{flag}**."
)
c1, c2 = st.columns([3, 2])
c1.plotly_chart(fig_acf(bundle["acf"]), width="stretch")
with c2:
    st.markdown("**Shape of the innovations**")
    st.dataframe(
        pd.DataFrame([
            {"statistic": "excess kurtosis (returns)", "value": fmt_num(d["excess_kurtosis"], 2),
             "reference": "0 under normality"},
            {"statistic": "skew (returns)", "value": fmt_num(d["skew"], 2), "reference": "0"},
            {"statistic": "Jarque-Bera p", "value": fmt_p(d["jarque_bera_p"]),
             "reference": "> 0.05 → normal"},
            {"statistic": "Ljung-Box p (returns)", "value": fmt_p(d["ljungbox_r_p"]),
             "reference": "> 0.05 → no autocorr."},
            {"statistic": "Ljung-Box p (r²)", "value": fmt_p(d["ljungbox_r2_p"]),
             "reference": "< 0.05 → clustering"},
            {"statistic": "ARCH-LM(10) p", "value": fmt_p(d["arch_lm_p"]),
             "reference": "< 0.05 → ARCH effects"},
        ]),
        width="stretch", hide_index=True,
    )
    st.markdown(
        f"After dividing by the fitted conditional σ, excess kurtosis falls "
        f"{fmt_num(d['excess_kurtosis'], 1)} → {fmt_num(resid['excess_kurtosis'], 1)} and "
        f"ARCH-LM p = {fmt_p(resid['arch_lm_p'])} "
        f"({'good' if (resid['arch_lm_p'] or 0) > 0.05 else 'still some structure left'})."
    )

q1, q2, q3 = st.columns(3)
q1.plotly_chart(fig_qq(bundle["qq_raw"], "Raw returns vs. normal", C_BLUE), width="stretch")
q2.plotly_chart(fig_qq(bundle["qq_resid_norm"], "Standardised residuals vs. normal", C_GREEN),
                width="stretch")
nu = stx.get("nu")
q3.plotly_chart(fig_qq(bundle["qq_resid_t"],
                       f"Standardised residuals vs. t(ν={fmt_num(nu, 2)})", C_ORANGE),
                width="stretch")

# --------------------------------------------------------------------------- #
# 3. Fit
# --------------------------------------------------------------------------- #
st.subheader("3 · Let the information criterion choose the specification")
st.latex(r"h_t = \omega + (\alpha + \gamma \mathbf{1}[r_{t-1} < 0])\,r^2_{t-1} + \beta h_{t-1},"
         r"\qquad r_t = \sqrt{h_t}\,\varepsilon_t,\quad \varepsilon_t \sim t(\nu)")
f1, f2 = st.columns([2, 3])
f1.plotly_chart(fig_bic(bundle["bic_table"], bundle["model"]), width="stretch")
with f2:
    bic = bundle["bic_table"].copy()
    bic["loglik"] = bic["loglik"].map(lambda v: f"{v:,.1f}")
    bic["bic"] = bic["bic"].map(lambda v: f"{v:,.1f}")
    bic["aic"] = bic["aic"].map(lambda v: f"{v:,.1f}")
    st.dataframe(bic, width="stretch", hide_index=True)
    st.markdown(
        f"**Selected:** `{bundle['model']}` — the leverage sign is an empirical question: "
        "equities usually show higher σ after down moves, energy and agriculturals often "
        "spike on upside supply shocks."
    )
    if bundle["fit_failures"]:
        st.caption("Specifications that did not converge: "
                   + "; ".join(bundle["fit_failures"].keys()))

p1, p2 = st.columns([3, 2])
p1.plotly_chart(fig_cond_vol(bundle["cond_vol"], bundle["cond_vol_index"],
                             bundle["estimators"], stx), width="stretch")
with p2:
    st.markdown("**What was recovered**")
    st.dataframe(pd.DataFrame([
        {"parameter": "α (ARCH)", "value": fmt_num(stx["alpha"], 4)},
        {"parameter": "γ (leverage)", "value": fmt_num(stx["gamma"], 4)},
        {"parameter": "β (GARCH)", "value": fmt_num(stx["beta"], 4)},
        {"parameter": "ν (tail index)", "value": fmt_num(stx["nu"], 2)},
        {"parameter": "persistence α+γ/2+β", "value": fmt_num(stx["persistence"], 4)},
        {"parameter": "σ∞ (long-run, ann.)", "value": fmt_pct(stx["sigma_inf_ann"])},
        {"parameter": "half-life", "value": fmt_num(stx["half_life_periods"], 1) + " periods"},
        {"parameter": "σ today (ann.)", "value": fmt_pct(stx["sigma_today_ann"])},
    ]), width="stretch", hide_index=True)
    st.caption(
        "Every structural parameter is estimated to within a few percent, but persistence "
        "enters σ∞ and the half-life through 1/(1 − p) — a small error there becomes a large "
        "error in both. Treat them as order-of-magnitude."
    )

# --------------------------------------------------------------------------- #
# 4. Horizon
# --------------------------------------------------------------------------- #
st.subheader(f"4 · The spike decays — √T scaling overstates a {H}-period horizon")
st.latex(r"\mathbb{E}[h_{t+h}] = h_\infty + p^{\,h-1}(h_{t+1} - h_\infty),"
         r"\qquad \sigma^2(t,H) = \sum_{h=1}^{H}\mathbb{E}[h_{t+h}]")
st.markdown(
    f"Today's conditional σ is **{fmt_pct(stx['sigma_today_ann'])}** against a long-run "
    f"**{fmt_pct(stx['sigma_inf_ann'])}**. Holding today's level flat across {H} periods "
    f"assumes the spike never subsides; the model aggregates to **{fmt_pct(hz['sigma_H'])}** "
    f"versus **{fmt_pct(hz['sigma_H_naive'])}** for naive √T — a "
    f"{fmt_pct(abs(hz['correction_pct']) / 100)} "
    f"{'overstatement' if hz['correction_pct'] > 0 else 'understatement'}."
)
h1, h2 = st.columns(2)
h1.plotly_chart(fig_term_structure(hz, ev, stx), width="stretch")
h2.plotly_chart(fig_term_bars(hz, ev, hz_bundle["ann"]), width="stretch")

if ev is not None:
    st.markdown(
        f"**Events the model cannot see.** {ev['n_events']} event(s) at a typical "
        f"{fmt_pct(ev['move'])} absolute move imply σ_event ≈ {fmt_pct(ev['sigma_event'])} "
        f"per period, taking the horizon σ from {fmt_pct(hz['sigma_H'])} to "
        f"**{fmt_pct(ev['sigma_total'])}** ({ev['uplift_pct']:+.2f}% uplift). This is what the "
        "options market does mechanically, which is why implied vol rises into an event and "
        "collapses right after it."
    )

st.markdown(
    f"**Drift is unknowable and barely matters.** μ̂ = {drift['mu_ann']:+.2%} p.a. ± "
    f"{1.96 * drift['se_ann']:.2%} over {drift['years']:.1f} years of data — the interval "
    f"spans zero and more. Its contribution over the horizon is "
    f"{drift['contribution_over_H']:+.2%} against σ = {drift['sigma_over_H']:.2%}, so below "
    "roughly a year put your effort into the second moment, where estimation converges."
)

# --------------------------------------------------------------------------- #
# 5. Distribution
# --------------------------------------------------------------------------- #
st.subheader(f"5 · Simulate, because the aggregate has no closed form")
st.markdown(
    f"{dist['nsim']:,} simulated paths answer both the terminal distribution and the "
    "path-dependent questions. The naive lognormal holds today's σ flat and uses normal "
    "innovations — it is wider in the body and thinner in the tail."
)
g1, g2 = st.columns([3, 2])
g1.plotly_chart(fig_cone(prepared, dist, H), width="stretch")
g2.plotly_chart(fig_distribution(dist, meta.unit or "value"), width="stretch")

qtab = pd.DataFrame([
    {"statement": f"{q}th percentile", "GARCH": f"{dist['quantiles'][q]:+.2f}%",
     "naive lognormal": (
         f"{dist['naive']['quantiles'][q]:+.2f}%"
         if np.isfinite(dist["naive"]["quantiles"][q]) else "—")}
    for q in V.QUANTILES
] + [
    {"statement": "P(return ≥ +10%)", "GARCH": fmt_pct(dist["P_up_10"]),
     "naive lognormal": fmt_pct(dist["naive"]["P_up_10"])},
    {"statement": "P(return ≤ −10%)", "GARCH": fmt_pct(dist["P_down_10"]),
     "naive lognormal": fmt_pct(dist["naive"]["P_down_10"])},
    {"statement": "P(within ±10%)", "GARCH": fmt_pct(dist["P_within_10"]),
     "naive lognormal": "—"},
    {"statement": "P(touches −15% at any point)", "GARCH": fmt_pct(dist["P_touch_down_15"]),
     "naive lognormal": "—"},
    {"statement": "P(touches +15% at any point)", "GARCH": fmt_pct(dist["P_touch_up_15"]),
     "naive lognormal": "—"},
    {"statement": "E|move|", "GARCH": fmt_pct(dist["E_abs_move_pct"] / 100),
     "naive lognormal": "—"},
])
st.dataframe(qtab, width="stretch", hide_index=True)
st.caption(
    "A price is one number; what you want is this object. It is a distribution, not an edge — "
    "the option chain publishes the market's forward-looking version of the same thing."
)

# --------------------------------------------------------------------------- #
# 6. Validation
# --------------------------------------------------------------------------- #
st.subheader("6 · None of it counts until the intervals are backtested")
if not run_bt:
    st.info(
        "Switch on **Backtest → Run walk-forward backtest** in the sidebar. Every window is "
        "disjoint (step == H) so the breach tests are valid: Kupiec tests the breach *rate*, "
        "Christoffersen tests whether breaches *cluster*. Three interval methods are scored — "
        "simulated t, variance aggregation with normal quantiles, and naive flat √T."
    )
elif bt_state is None or bt_state.get("data") is None:
    err = (bt_state or {}).get("error", "unknown error")
    st.error(f"The backtest could not run: {err}")
else:
    bd = bt_state["data"]
    bt = bd["table"]
    if bt.empty:
        st.warning(
            "No window produced a converging fit — shorten H, raise the max windows, or "
            "widen the estimation window."
        )
    else:
        st.caption(
            f"Walk-forward on `{bt_spec}`, refitted per window, disjoint step == {bt_H}, "
            f"estimation window ≤ 1 000 periods."
        )
        if bd["truncated"]:
            st.caption(
                f"Showing the most recent {len(bt):,} of {bd['n_available']:,} disjoint "
                "windows (max-windows cap). The reference's warning applies: at H = 20 a "
                "decade of dailies buys fewer than 100 independent windows."
            )
        v1, v2 = st.columns(2)
        v1.plotly_chart(fig_pit(bt), width="stretch")
        v2.plotly_chart(fig_coverage(bd["summary"]), width="stretch")
        st.plotly_chart(fig_oos_intervals(bt), width="stretch")

        summ = bd["summary"].copy()
        summ["nominal"] = summ["nominal"].map(lambda v: f"{v:.0%}")
        summ["actual"] = summ["actual"].map(lambda v: fmt_pct(v))
        summ = summ.rename(columns={
            "method": "method", "nominal": "nominal", "actual": "actual",
            "n_windows": "windows", "breaches": "breaches",
            "kupiec_p": "Kupiec p", "independence_p": "independence p"})
        st.dataframe(summ, width="stretch", hide_index=True)
        st.caption(
            "Simulating with t innovations can produce worse coverage than aggregating the "
            "variance with normal quantiles: over multi-period horizons the central limit "
            "theorem pulls the sum of fat-tailed innovations back toward normality faster "
            "than the GARCH feedback fattens it."
        )

st.markdown("---")
st.caption(
    "Adapted from `volatility_pipeline.py` (`arch` GARCH family, statsmodels diagnostics, "
    "SciPy distributions). Close-only series cannot support the reference's range "
    "estimators; everything else runs unchanged."
)
