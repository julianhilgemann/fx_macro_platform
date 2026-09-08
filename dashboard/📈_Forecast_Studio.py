"""FX Macro Forecast Studio — Streamlit dashboard over the Postgres warehouse.

Pick a macro series from the DWH, visualise it, fit a time-series model with
walk-forward cross-validation and produce a multi-period forecast with
prediction intervals, error metrics and residual diagnostics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import load_catalog, load_observations
from forecast import MIN_POINTS, prepare_series, run_forecast

st.set_page_config(page_title="FX Macro Forecast Studio", page_icon="📈", layout="wide")

MODELS = {
    "Auto ARIMA (SARIMAX)": "arima",
    "Holt-Winters ETS": "ets",
    "Naive drift (baseline)": "naive",
}


# --------------------------------------------------------------------------- #
# Cached data loaders
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300, show_spinner=False)
def get_catalog() -> pd.DataFrame:
    return load_catalog()


@st.cache_data(ttl=300, show_spinner=False)
def get_obs(series_id: str) -> pd.DataFrame:
    return load_observations(series_id)


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def fmt(x) -> str:
    if x is None:
        return "—"
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if np.isnan(f):
        return "—"
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    if abs(f) >= 1:
        return f"{f:,.2f}"
    return f"{f:.4g}"


def forecast_figure(result, meta) -> go.Figure:
    fig = go.Figure()
    s = result.series
    ci = 1 - result.alpha

    fig.add_trace(
        go.Scatter(
            x=s.index, y=s.values, mode="lines", name="History",
            line=dict(color="#2563eb", width=1.4),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.fitted.index, y=result.fitted.values, mode="lines",
            name="In-sample fit", line=dict(color="#93c5fd", width=1, dash="dot"),
        )
    )

    fi = result.forecast_index
    fig.add_trace(
        go.Scatter(
            x=fi, y=result.forecast_upper, mode="lines", line=dict(width=0),
            showlegend=False, hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=fi, y=result.forecast_lower, mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor="rgba(249,115,22,0.18)",
            name=f"{ci:.0%} prediction interval",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=fi, y=result.forecast_mean, mode="lines", name="Forecast",
            line=dict(color="#ea580c", width=2.2),
        )
    )
    fig.add_vline(x=s.index[-1], line_dash="dot", line_color="#64748b")

    fig.update_layout(
        title=f"Forecast — {meta.title or meta.series_id} ({result.model_name})",
        yaxis_title=meta.unit or "value",
        template="plotly_white",
        height=460,
        margin=dict(l=10, r=10, t=92, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0),
    )
    return fig


def render_diagnostics(result) -> None:
    d = result.diagnostics
    st.markdown("**Test battery** (p-values; < 0.05 flags a violation):")
    rows = [
        ("ADF stationarity (level)", d.get("adf_pvalue"), "series stationary"),
        ("KPSS stationarity (level)", d.get("kpss_pvalue"), "series stationary"),
        ("Ljung-Box (residual autocorr.)", d.get("ljung_box_pvalue"), "no autocorrelation"),
        ("Jarque-Bera (residual normality)", d.get("jarque_bera_pvalue"), "residuals normal"),
        ("Engle ARCH (volatility clustering)", d.get("arch_lm_pvalue"), "no ARCH effects"),
    ]
    diag_df = pd.DataFrame(rows, columns=["Test", "p-value", "null hypothesis (p≥0.05)"])
    st.dataframe(diag_df.style.format({"p-value": "{:.4g}"}), width="stretch")
    st.caption(
        f"Durbin-Watson: {d.get('durbin_watson'):.3f} "
        "(2.0 ≈ no first-order autocorrelation)"
    )

    acf_vals = d.get("resid_acf", [])
    pacf_vals = d.get("resid_pacf", [])
    if acf_vals:
        lags = list(range(len(acf_vals)))
        band = 1.96 / np.sqrt(max(1, d.get("n", 1)))
        fig = go.Figure()
        fig.add_trace(go.Bar(x=lags, y=acf_vals, name="ACF", marker_color="#2563eb"))
        fig.add_trace(go.Bar(x=lags, y=pacf_vals, name="PACF", marker_color="#ea580c"))
        fig.add_hline(y=band, line_dash="dash", line_color="#94a3b8")
        fig.add_hline(y=-band, line_dash="dash", line_color="#94a3b8")
        fig.update_layout(
            title="Residual ACF / PACF",
            template="plotly_white", height=300,
            margin=dict(l=10, r=10, t=50, b=10),
            barmode="group",
        )
        st.plotly_chart(fig, width="stretch")

    resid = result.residuals.dropna()
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=resid.index, y=resid.values, mode="lines",
                              name="Residuals", line=dict(color="#475569", width=1)))
    fig2.add_hline(y=0, line_color="#94a3b8")
    fig2.update_layout(title="Residuals", template="plotly_white", height=240,
                       margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
    st.plotly_chart(fig2, width="stretch")

    fig3 = go.Figure()
    fig3.add_trace(go.Histogram(x=resid.values, nbinsx=40, name="Residuals",
                                marker_color="#2563eb"))
    fig3.update_layout(title="Residual histogram", template="plotly_white", height=240,
                       margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
    st.plotly_chart(fig3, width="stretch")


def render_cv(result) -> None:
    cv = result.cv_folds
    if cv.empty:
        st.info("No CV folds were produced.")
        return
    folds = []
    for k, g in cv.groupby("fold"):
        err = g["predicted"] - g["actual"]
        folds.append(
            {
                "fold": int(k),
                "obs": int(len(g)),
                "from": g["date"].min().date(),
                "to": g["date"].max().date(),
                "RMSE": float(np.sqrt(np.mean(err ** 2))),
                "MAE": float(np.mean(np.abs(err))),
            }
        )
    st.dataframe(pd.DataFrame(folds).round(4), width="stretch")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cv["date"], y=cv["actual"], mode="lines+markers",
                             name="Actual", line=dict(color="#2563eb", width=1.6)))
    fig.add_trace(go.Scatter(x=cv["date"], y=cv["predicted"], mode="lines+markers",
                             name="Predicted (OOS)",
                             line=dict(color="#ea580c", width=1.4, dash="dot")))
    fig.update_layout(title="Walk-forward out-of-sample predictions", template="plotly_white",
                      height=340, margin=dict(l=10, r=10, t=50, b=10),
                      hovermode="x unified")
    st.plotly_chart(fig, width="stretch")


def render_result(result, ci_level, meta) -> None:
    st.markdown("---")
    st.subheader("Forecast")
    fig = forecast_figure(result, meta)
    st.plotly_chart(fig, width="stretch")

    m = result.metrics
    st.subheader("Error metrics (walk-forward, out-of-sample)")
    cols = st.columns(6)
    cols[0].metric("RMSE", fmt(m.get("rmse")))
    cols[1].metric("MAE", fmt(m.get("mae")))
    cols[2].metric("MAPE %", fmt(m.get("mape")))
    cols[3].metric("sMAPE %", fmt(m.get("smape")))
    cols[4].metric("MASE", fmt(m.get("mase")))
    cols[5].metric("R² (OOS)", fmt(m.get("r2")))
    cols2 = st.columns(4)
    cols2[0].metric("MSE", fmt(m.get("mse")))
    cols2[1].metric("CV obs", str(m.get("n_obs", "—")))
    cols2[2].metric("AIC", fmt(result.aic))
    cols2[3].metric("BIC", fmt(result.bic))

    with st.expander("Model details", expanded=False):
        st.markdown(
            f"**Model:** `{result.model_name}` · **order:** "
            f"`{result.order}` · **seasonal:** `{result.seasonal_order}` · "
            f"**horizon:** {result.horizon} · **CI:** {ci_level:.0%}"
        )
        if result.model_name.startswith("SARIMAX"):
            st.markdown(f"**Selection IC (AIC):** {fmt(result.ic)}")
        st.code(result.summary_text, language="text")

    with st.expander("Model diagnostics", expanded=False):
        render_diagnostics(result)

    with st.expander("Cross-validation detail", expanded=False):
        render_cv(result)


# --------------------------------------------------------------------------- #
# Main flow
# --------------------------------------------------------------------------- #
catalog = get_catalog()
if catalog.empty:
    st.error("No series found in the warehouse (`marts.dim_series`). Run the dbt build first.")
    st.stop()

catalog = catalog.fillna("")

with st.sidebar:
    st.header("Controls")

    label_to_id = {
        f"{r.series_id} — {r.title}".strip(" —"): r.series_id for r in catalog.itertuples()
    }
    selected_label = st.selectbox("Macro series", list(label_to_id))
    series_id = label_to_id[selected_label]
    meta = catalog[catalog.series_id == series_id].iloc[0]

    obs = get_obs(series_id)
    if obs.empty:
        st.warning("This series has no observations yet.")
        obs = pd.DataFrame(columns=["obs_date", "value"])

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

    model_label = st.selectbox("Model", list(MODELS))
    model_kind = MODELS[model_label]
    horizon = st.slider("Forecast horizon (periods)", 1, 60, 12)

    ci_level = st.selectbox("Confidence level", [0.80, 0.90, 0.95, 0.99], index=2)
    alpha = 1 - ci_level

    monthly = str(meta.frequency).strip().upper().startswith("M")
    with st.expander("Advanced — cross-validation & model"):
        n_splits = st.slider("CV folds", 2, 12, 5)
        window_mode = st.radio(
            "CV scheme", ["Expanding (forward chaining)", "Rolling (sliding window)"], index=0
        )
        window = None
        if "Rolling" in window_mode:
            window = st.slider("Rolling window (obs)", 30, 1500, 252)
        seasonal = st.checkbox("Seasonal terms (auto-ARIMA)", value=monthly)
        max_p = st.slider("Max AR order (p)", 0, 4, 2)
        max_q = st.slider("Max MA order (q)", 0, 4, 2)
        max_d = st.slider("Max differencing (d)", 0, 2, 2)

    run = st.button("Run model", type="primary", width="stretch")

st.title("FX Macro Forecast Studio")
title = meta.title or series_id
st.caption(
    f"**{title}** · `{series_id}` · unit: {meta.unit or '—'} · frequency: "
    f"{meta.frequency or '—'} · category: {meta.category or '—'} · country: {meta.country or '—'}"
)

windowed = obs[(obs.obs_date >= start) & (obs.obs_date <= end)] if not obs.empty else obs
prepared, offset, period = prepare_series(windowed, meta.frequency)

st.markdown(
    f"**{len(prepared):,}** observations · {prepared.index.min():%Y-%m-%d} → "
    f"{prepared.index.max():%Y-%m-%d} · aligned to `{offset}` (gaps forward-filled)"
)

raw_fig = go.Figure()
raw_fig.add_trace(
    go.Scatter(
        x=prepared.index,
        y=prepared.values,
        mode="lines",
        name="History",
        line=dict(color="#2563eb", width=1.4),
    )
)
raw_fig.update_layout(
    title=f"{title} ({series_id})",
    xaxis_title="",
    yaxis_title=meta.unit or "value",
    template="plotly_white",
    height=380,
    margin=dict(l=10, r=10, t=50, b=10),
    hovermode="x unified",
    showlegend=False,
)
st.plotly_chart(raw_fig, width="stretch")

current_sig = (
    series_id, model_kind, horizon, ci_level, n_splits, window_mode,
    seasonal, max_p, max_q, max_d, start, end,
)

if run:
    if len(prepared) < MIN_POINTS:
        st.error(f"Only {len(prepared)} points in the selected window — need ≥ {MIN_POINTS}.")
    else:
        with st.spinner("Selecting orders, running walk-forward CV and refitting …"):
            try:
                result = run_forecast(
                    prepared,
                    offset,
                    period,
                    model_kind=model_kind,
                    horizon=horizon,
                    alpha=alpha,
                    n_splits=n_splits,
                    window=window,
                    max_p=max_p,
                    max_q=max_q,
                    max_d=max_d,
                    seasonal=seasonal,
                )
                st.session_state["result"] = result
                st.session_state["sig"] = current_sig
            except Exception as exc:  # noqa: BLE001 — surface any model failure
                st.error(f"Model failed: {exc}")
                st.session_state.pop("result", None)
                st.session_state.pop("sig", None)

result = st.session_state.get("result")
if result is not None and st.session_state.get("sig") == current_sig:
    render_result(result, ci_level, meta)
