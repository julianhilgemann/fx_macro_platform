"""Volatility → probability pipeline, adapted from ``volatility_pipeline.py``.

The reference script at the repo root takes an OHLC DataFrame and prints a
report. This module is the same chain, restructured for the Streamlit app:

* every step returns plain Python/NumPy objects (no printing, no Streamlit),
  so the module stays importable by tests and by the page;
* the input is a **single priced series from the warehouse** (``obs_date`` /
  ``value``), which is close-only — the reference's range estimators need true
  OHLC bars, so they are exposed separately and are reported as unavailable
  unless genuine bars (or explicitly-flagged synthetic bars) are supplied;
* the GARCH fit can be restricted to a trailing window so a 25-year daily
  series still fits in a second or two;
* the backtest reproduces the reference's three-way comparison: simulated t
  intervals vs. variance aggregation with normal quantiles vs. naive flat √T.

Stage map (mirrors the reference's ``report()``):

    returns      → log_returns / period_returns
    estimators   → rolling_vol, ewma_vol, yang_zhang, garman_klass, parkinson
    diagnostics  → diagnose, acf/pacf, qq data
    fit          → select_model (BIC over GARCH-t / GJR-t / GJR-skewt)
    structure    → structure (persistence, σ∞, half-life, σ today)
    horizon      → horizon_sigma (mean-reverting aggregation vs. √T)
    events       → add_events
    distribution → distribution (simulation, term structure, quantiles)
    validation   → backtest + kupiec + christoffersen + PIT
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from arch import arch_model
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.tsa.stattools import acf as _acf
from statsmodels.tsa.stattools import pacf as _pacf

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

ANN = float(np.sqrt(252))  # annualisation for daily bars; see periods_per_year()

#: BIC-ranked specifications, escalating in the tail/leverage treatment.
SPECS: dict[str, dict[str, Any]] = {
    "GARCH(1,1) normal": dict(p=1, o=0, q=1, dist="normal"),
    "GARCH(1,1) t": dict(p=1, o=0, q=1, dist="t"),
    "GJR(1,1,1) t": dict(p=1, o=1, q=1, dist="t"),
    "GJR(1,1,1) skew-t": dict(p=1, o=1, q=1, dist="skewt"),
}

#: default specification used for the walk-forward backtest (reference hard-codes this)
BACKTEST_SPEC = "GJR(1,1,1) t"


# --------------------------------------------------------------------------- #
# 1. Price → returns
# --------------------------------------------------------------------------- #
def log_returns(close: pd.Series) -> pd.Series:
    """r_t = ln(P_t / P_{t-1}). Infinite if the level goes non-positive."""
    out = np.log(close).diff()
    return out.replace([np.inf, -np.inf], np.nan).dropna()


def period_returns(close: pd.Series) -> tuple[pd.Series, str]:
    """Log returns when the level is safely positive, else simple returns.

    Yields, spreads and policy rates go negative or hit zero, and ``log`` is
    undefined there — the reference gets away with log returns because it is
    fed a price. The pipeline down-streams are scale-agnostic either way.
    """
    s = pd.Series(close).astype(float).dropna()
    if len(s) > 1 and float(s.min()) > 0:
        return log_returns(s), "log"
    return s.diff().replace([np.inf, -np.inf], np.nan).dropna(), "simple"


def periods_per_year(index: pd.Index, floor: float = 2.0) -> float:
    """Observation rate per calendar year implied by the index.

    Counts observations rather than inferring from the median gap: business-daily
    data lands on the equity convention (≈252) instead of 365, monthly resampling
    on 12, and so on. A pure calendar span is used, so it is independent of how
    pandas represents timestamps internally.
    """
    idx = pd.DatetimeIndex(index)
    if len(idx) < 3:
        return 252.0
    span_days = (idx.max() - idx.min()) / np.timedelta64(1, "D")
    if not np.isfinite(span_days) or span_days <= 0:
        return 252.0
    years = float(span_days) / 365.25
    return max(float(floor), (len(idx) - 1) / years)


def ann_factor(index: pd.Index) -> float:
    """√(periods per year) — the multiplier that annualises a per-period σ."""
    return float(np.sqrt(periods_per_year(index)))


# --------------------------------------------------------------------------- #
# 2. Estimating σ
# --------------------------------------------------------------------------- #
def rolling_vol(r: pd.Series, n: int = 20) -> pd.Series:
    """Zero-mean close-to-close σ, in per-period units. Over short windows the
    sample mean is noise, so the mean is not subtracted."""
    return r.rolling(n).apply(lambda x: np.sqrt((x**2).mean()), raw=True)


def ewma_vol(r: pd.Series, lam: float = 0.94) -> pd.Series:
    """RiskMetrics recursion v_t = λv_{t-1} + (1-λ)r²_{t-1}, per-period units."""
    x = np.asarray(r, dtype=float)
    v = np.empty(len(x))
    if len(x) == 0:
        return pd.Series(dtype=float)
    v[0] = float(np.var(x))
    for i in range(1, len(x)):
        v[i] = lam * v[i - 1] + (1 - lam) * x[i - 1] ** 2
    return pd.Series(np.sqrt(v), index=r.index)


def parkinson(ohlc: pd.DataFrame, n: int = 20) -> pd.Series:
    """High–low range σ. Needs true bars; scale 1/(4 ln 2)."""
    hl = np.log(ohlc["high"] / ohlc["low"]) ** 2
    return np.sqrt(hl.rolling(n).mean() / (4 * np.log(2)))


def garman_klass(ohlc: pd.DataFrame, n: int = 20) -> pd.Series:
    """Parkinson + open/close term. Needs true bars."""
    o, h, l, c = (np.log(ohlc[k]) for k in ("open", "high", "low", "close"))
    rs = 0.5 * (h - l) ** 2 - (2 * np.log(2) - 1) * (c - o) ** 2
    return np.sqrt(rs.rolling(n).mean())


def yang_zhang(ohlc: pd.DataFrame, n: int = 20) -> pd.Series:
    """Overnight + Rogers-Satchell + open-to-close. Needs true OHLC bars."""
    o, h, l, c = (np.log(ohlc[k]) for k in ("open", "high", "low", "close"))
    ro, oc = o - c.shift(1), c - o
    rs = (h - c) * (h - o) + (l - c) * (l - o)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    var = (
        ro.rolling(n).var()
        + k * oc.rolling(n).var()
        + (1 - k) * rs.rolling(n).mean()
    )
    return np.sqrt(var.clip(lower=0))


def synthetic_ohlc(close: pd.Series, span: int = 5) -> pd.DataFrame:
    """Fabricate OHLC bars from a close-only series (explicitly a proxy).

    The bar range is the close's own rolling k-bar range, so the high–low is
    mechanically derived from close-to-close moves: it carries no intraday
    information, and range estimators built on it are biased and too smooth.
    Only useful to show the shape of the estimator — never for inference.
    """
    s = pd.Series(close).astype(float)
    roll_hi = s.rolling(span, min_periods=1).max()
    roll_lo = s.rolling(span, min_periods=1).min()
    return pd.DataFrame(
        {
            "open": s.shift(1).fillna(s),
            "high": np.maximum.reduce([roll_hi.to_numpy(), s.to_numpy()]),
            "low": np.minimum.reduce([roll_lo.to_numpy(), s.to_numpy()]),
            "close": s,
        },
        index=s.index,
    ).dropna()


def ohlc_report(ohlc: pd.DataFrame) -> dict:
    """Sanity summary for real bars: identity violations are data errors."""
    o, h, l, c = (ohlc[k] for k in ("open", "high", "low", "close"))
    bad = ((h < l) | (h < np.maximum(o, c)) | (l > np.minimum(o, c))).sum()
    return {
        "n_bars": int(len(ohlc)),
        "bad_bars": int(bad),
        "mean_high_low_pct": float((h / l - 1).mean() * 100),
    }


def estimator_table(r: pd.Series, ohlc: pd.DataFrame | None, ann: float,
                    n: int = 20, lam: float = 0.94) -> pd.DataFrame:
    """The reference's "four estimates of the same hidden quantity", extended.

    ``value`` is the *current* reading (annualised), ``series`` the full path.
    Works in per-period units and multiplies by ``ann`` at the end, so it is
    correct for any sampling frequency.
    """
    have_ohlc = ohlc is not None and len(ohlc) > n + 2
    rows: list[dict[str, Any]] = []

    def add(name: str, series: pd.Series, needs_bars: bool = False):
        if series is None or len(series) == 0 or not np.isfinite(series.dropna()).any():
            return
        ann_series = series * ann
        rows.append(
            {
                "estimator": name,
                "series": ann_series,
                "value": float(series.dropna().iloc[-1] * ann),
                "needs_bars": needs_bars,
            }
        )

    add(f"{n}p close-to-close", rolling_vol(r, n))
    add(f"{n}p close-to-close (sample sd)", r.rolling(n).std())
    add(f"EWMA (λ={lam:g})", ewma_vol(r, lam))
    if have_ohlc:
        add(f"{n}p Parkinson", parkinson(ohlc, n), True)
        add(f"{n}p Garman-Klass", garman_klass(ohlc, n), True)
        add(f"{n}p Yang-Zhang", yang_zhang(ohlc, n), True)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 3. Diagnostics
# --------------------------------------------------------------------------- #
def _safe_p(fn, *a, **kw) -> float:
    try:
        v = float(fn(*a, **kw))
        return v if np.isfinite(v) else float("nan")
    except Exception:  # noqa: BLE001 — diagnostics must never break the page
        return float("nan")


def acf_data(r: pd.Series, nlags: int = 40) -> dict:
    """ACF of returns and of squared returns (the clustering signal)."""
    nlags = int(min(nlags, max(1, len(r) // 2 - 1)))
    return {
        "lags": list(range(nlags + 1)),
        "r": [float(x) for x in _acf(r, nlags=nlags, fft=True)],
        "r2": [float(x) for x in _acf(r**2, nlags=nlags, fft=True)],
        "band": float(1.96 / np.sqrt(len(r))),
    }


def qq_data(x: np.ndarray, dist: str = "normal", df: float | None = None) -> dict:
    """Theoretical vs. empirical quantiles for a QQ plot."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return {"theoretical": [], "empirical": []}
    probs = (np.arange(1, len(x) + 1) - 0.5) / len(x)
    if dist == "t":
        theo = stats.t.ppf(probs, df if df and df > 2 else 5.0)
    else:
        theo = stats.norm.ppf(probs)
    return {"theoretical": theo.tolist(), "empirical": np.sort(x).tolist()}


def diagnose(r: pd.Series, nlags: int = 20) -> dict:
    """Is a volatility model warranted at all, and how fat are the tails?"""
    r = pd.Series(r).dropna()
    lb_r = _safe_p(lambda: acorr_ljungbox(r, lags=[nlags], return_df=True)["lb_pvalue"].iloc[0])
    lb_r2 = _safe_p(lambda: acorr_ljungbox(r**2, lags=[nlags], return_df=True)["lb_pvalue"].iloc[0])
    return {
        "n": int(len(r)),
        "mean_period": float(r.mean()),
        "sd_period": float(r.std()),
        "excess_kurtosis": _safe_p(stats.kurtosis, r),
        "skew": _safe_p(stats.skew, r),
        "jarque_bera_p": _safe_p(lambda: stats.jarque_bera(r).pvalue),
        "ljungbox_r_p": lb_r,
        "ljungbox_r2_p": lb_r2,
        "arch_lm_p": _safe_p(lambda: het_arch(r, nlags=10)[1]),
        "vol_rel_se": float(1 / np.sqrt(2 * nlags)),
        "nlags": int(nlags),
    }


# --------------------------------------------------------------------------- #
# 4. Fitting
# --------------------------------------------------------------------------- #
@dataclass
class Fit:
    """A fitted GARCH-family model plus everything derived from it."""

    name: str
    res: Any
    r100: pd.Series
    bic_table: pd.DataFrame
    failures: dict[str, str] = field(default_factory=dict)


def fit_model(r: pd.Series, spec: str = "auto") -> Fit:
    """Fit one specification, or escalate with BIC as the referee.

    ``r`` is a per-period return *level* (not annualised); it is scaled by 100
    for the optimiser, exactly as the reference does, so ω is O(1e-2).
    """
    names = list(SPECS) if spec == "auto" else [spec]
    r100 = pd.Series(r, dtype=float).dropna() * 100.0
    fits: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    for name in names:
        try:
            res = arch_model(r100, mean="Constant", vol="GARCH", **SPECS[name]).fit(
                disp="off", show_warning=False
            )
        except Exception as exc:  # noqa: BLE001 — report, don't crash
            failures[name] = f"{type(exc).__name__}: {exc}"
            continue
        fits[name] = res
        bic = -2 * res.loglikelihood + len(res.params) * np.log(len(r100))
        rows.append(
            {"specification": name, "loglik": float(res.loglikelihood),
             "bic": float(bic), "aic": float(res.aic)}
        )
    if not fits:
        raise RuntimeError(
            "every GARCH specification failed to converge: "
            + "; ".join(failures.values())
        )
    table = pd.DataFrame(rows).sort_values("bic").reset_index(drop=True)
    best = str(table.iloc[0]["specification"])
    return Fit(name=best, res=fits[best], r100=r100, bic_table=table, failures=failures)


def structure(res, ppy: float = 252.0) -> dict:
    """Long-run level and half-life.

    Both divide by (1 − persistence), so they are weakly identified: treat them
    as order-of-magnitude, exactly as the reference warns. ``arch`` works in
    percent per period, so σ comes back per-period and is annualised with
    ``√ppy`` for the ``*_ann`` keys.
    """
    ann = float(np.sqrt(ppy))
    p = res.params
    a = float(p.get("alpha[1]", 0.0) or 0.0)
    g = float(p.get("gamma[1]", 0.0) or 0.0)
    b = float(p.get("beta[1]", 0.0) or 0.0)
    persist = a + g / 2 + b
    omega = float(p.get("omega", np.nan))
    h_inf = omega / (1 - persist) / 1e4 if persist < 1 else np.nan
    half_life = float(np.log(0.5) / np.log(persist)) if 0 < persist < 1 else np.nan
    sig_today = float(res.conditional_volatility.iloc[-1])
    sig_inf = float(np.sqrt(h_inf)) if np.isfinite(h_inf) else np.nan
    return {
        "alpha": a,
        "gamma": g,
        "beta": b,
        "nu": float(p.get("nu", np.nan) or np.nan),
        "lambda_skew": float(p.get("lambda", np.nan) or np.nan),
        "persistence": float(persist),
        # per-period σ in percent (daily for daily bars)
        "sigma_today": sig_today,
        "sigma_inf": sig_inf,
        # the same two quantities annualised, for comparison with the estimators
        "sigma_today_ann": float(sig_today * ann),
        "sigma_inf_ann": float(sig_inf * ann) if np.isfinite(sig_inf) else np.nan,
        "half_life_periods": half_life,
    }


def horizon_sigma(res, H: int, ppy: float = 252.0, st: dict | None = None) -> dict:
    """Aggregate the mean-reverting variance path.

    Naive √T overstates after a spike and understates in a calm regime — the
    single most useful correction in the chain. ``st`` avoids refitting the
    structural summary when the caller already has it. Everything public here
    is annualised with ``√ppy``.
    """
    H = int(max(1, H))
    ann = float(np.sqrt(ppy))
    st = st if st is not None else structure(res, ppy)
    sig_now = st["sigma_today"] / ann  # back to per-period
    f = res.forecast(horizon=H, reindex=False)
    var_path = np.asarray(f.variance.values[-1], dtype=float) / 1e4
    # unconditional/h∞ path implied by the variance recursion itself, so the
    # long-run curve is exactly the model's own mean reversion
    persist = st["persistence"]
    hinf_var = (st["sigma_inf"] / ann) ** 2 if np.isfinite(st["sigma_inf"]) else np.nan
    if np.isfinite(hinf_var) and 0 < persist < 1:
        var_hinf = hinf_var + persist ** (np.arange(H)) * (sig_now**2 - hinf_var)
    else:
        var_hinf = np.full(H, np.nan)
    # annualise the aggregate: √(Σ h_period) × √(periods per year)
    sigma_H = float(np.sqrt(max(var_path.sum(), 0.0)) * ann)
    sigma_H_naive = float(sig_now * np.sqrt(H) * ann)
    return {
        "H": H,
        "sigma_H": sigma_H,
        "sigma_H_naive": sigma_H_naive,
        "correction_pct": float((1 - sigma_H / sigma_H_naive) * 100) if sigma_H_naive else np.nan,
        "term_structure": np.sqrt(np.maximum(var_path, 0)) * ann,
        "term_structure_longrun": np.sqrt(np.maximum(var_hinf, 0)) * ann,
        "sigma_today": st["sigma_today_ann"],
        "sigma_inf": st["sigma_inf_ann"],
    }


def add_events(sigma_H: float, n_events: int, typical_abs_move: float,
               ann: float = ANN) -> dict:
    """GARCH cannot see the calendar: σ_event from E|x| = σ√(2/π).

    ``typical_abs_move`` is the typical absolute *per-period return* (e.g. a
    4.5% CPI-day move on a daily series). Both sides are put in the same units
    — aggregate vega per period, then re-annualised — so the reported uplift is
    a genuine variance share, not a unit accident.
    """
    if not np.isfinite(sigma_H) or sigma_H <= 0 or ann <= 0:
        return {"n_events": int(n_events), "move": float(typical_abs_move),
                "sigma_event": np.nan, "sigma_total": np.nan, "uplift_pct": np.nan}
    s_ev = typical_abs_move * np.sqrt(np.pi / 2)
    var_diffusive = (sigma_H / ann) ** 2
    var_total = var_diffusive + n_events * s_ev**2
    total = float(np.sqrt(var_total) * ann)
    return {
        "n_events": int(n_events),
        "move": float(typical_abs_move),
        "sigma_event": float(s_ev),
        "sigma_total": total,
        "uplift_pct": float((total / sigma_H - 1) * 100),
    }


# --------------------------------------------------------------------------- #
# 5. Distribution
# --------------------------------------------------------------------------- #
QUANTILES = (1, 5, 25, 50, 75, 95, 99)


def distribution(res, H: int, nsim: int = 50_000, S0: float = 1.0,
                 ann: float = ANN, sigma_H: float | None = None) -> dict:
    """Simulate the horizon — the only step that answers path-dependent questions.

    Prices are expressed as simple returns on ``S0`` so the same object works
    for a spot price, a yield or a spread (where a multiplicative price is
    meaningless but a percentage move is not). ``sigma_H`` is the annualised
    aggregate from :func:`horizon_sigma`; it is only used to build the naive
    lognormal straw man.
    """
    H = int(max(1, H))
    f = res.forecast(horizon=H, method="simulation", simulations=int(nsim), reindex=False)
    paths = np.asarray(f.simulations.values[-1], dtype=float) / 100.0
    cum = np.cumsum(paths, axis=1)
    terminal = np.exp(cum[:, -1]) - 1.0
    terminal_px = S0 * np.exp(cum[:, -1])
    running_min = np.exp(np.minimum.accumulate(cum, axis=1)) - 1.0
    running_max = np.exp(np.maximum.accumulate(cum, axis=1)) - 1.0
    return {
        "H": H,
        "nsim": int(nsim),
        "S0": float(S0),
        "terminal_ret": terminal,
        "terminal_px": terminal_px,
        "median_path": np.exp(np.median(cum, axis=0)) - 1.0,
        "q05_path": np.exp(np.percentile(cum, 5, axis=0)) - 1.0,
        "q95_path": np.exp(np.percentile(cum, 95, axis=0)) - 1.0,
        "quantiles": {q: float(np.percentile(terminal, q) * 100) for q in QUANTILES},
        "P_up_10": float((terminal > 0.10).mean()),
        "P_down_10": float((terminal < -0.10).mean()),
        "P_within_10": float((np.abs(terminal) <= 0.10).mean()),
        "P_touch_down_15": float((running_min < -0.15).mean()),
        "P_touch_up_15": float((running_max > 0.15).mean()),
        "E_abs_move_pct": float(np.abs(terminal_px / S0 - 1).mean() * 100),
        "E_abs_move_ret": float(np.abs(terminal).mean()),
        "naive": _naive_lognormal(sigma_H, H),
    }


def _naive_lognormal(sigma_H: float, H: int) -> dict:
    """The straw man: hold today's σ flat over the horizon, normal innovations."""
    sd = float(sigma_H) if np.isfinite(sigma_H) else np.nan
    ok = np.isfinite(sd) and sd > 0
    q = {p: float(stats.norm.ppf(p / 100, 0.0, sd) * 100) if ok else np.nan
         for p in QUANTILES}
    return {
        "sd": sd,
        "quantiles": q,
        "P_up_10": float(1 - stats.norm.cdf(0.10, 0.0, sd)) if ok else np.nan,
        "P_down_10": float(stats.norm.cdf(-0.10, 0.0, sd)) if ok else np.nan,
    }


def distribution_frame(dist: dict, bins: int = 120) -> pd.DataFrame:
    """Histogram of simulated terminal returns, in percent."""
    x = np.asarray(dist["terminal_ret"], dtype=float) * 100
    lo, hi = np.nanpercentile(x, [0.2, 99.8])
    counts, edges = np.histogram(x, bins=bins, range=(lo, hi))
    centres = 0.5 * (edges[1:] + edges[:-1])
    # density so the naive lognormal pdf can be overlaid on the same axis
    width = edges[1] - edges[0]
    return pd.DataFrame({"ret_pct": centres, "density": counts / (counts.sum() * width)})


# --------------------------------------------------------------------------- #
# 6. Validation
# --------------------------------------------------------------------------- #
def kupiec(breaches: int, n: int, p: float = 0.10) -> float:
    """Unconditional coverage: is the breach RATE right?"""
    if n == 0 or breaches in (0, n):
        return float("nan")
    ph = breaches / n
    ll = -2 * (
        (n - breaches) * np.log(1 - p)
        + breaches * np.log(p)
        - (n - breaches) * np.log(1 - ph)
        - breaches * np.log(ph)
    )
    return float(1 - stats.chi2.cdf(ll, 1))


def christoffersen(b) -> float:
    """Independence: do breaches CLUSTER? Clustering means the model is too slow."""
    b = np.asarray(b, dtype=int)
    if len(b) < 3:
        return float("nan")
    n = {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}
    for i in range(1, len(b)):
        n[(int(b[i - 1]), int(b[i]))] += 1
    n00, n01, n10, n11 = n[(0, 0)], n[(0, 1)], n[(1, 0)], n[(1, 1)]
    if n01 + n11 == 0 or n00 + n01 == 0 or n10 + n11 == 0:
        return float("nan")
    p01, p11 = n01 / (n00 + n01), n11 / (n10 + n11)
    p = (n01 + n11) / len(b[1:])

    def lg(c, q):
        return c * np.log(q) if c and 0 < q < 1 else 0.0

    l1 = lg(n00, 1 - p01) + lg(n01, p01) + lg(n10, 1 - p11) + lg(n11, p11)
    l0 = lg(n00 + n10, 1 - p) + lg(n01 + n11, p)
    return float(1 - stats.chi2.cdf(-2 * (l0 - l1), 1))


def backtest(
    r: pd.Series,
    H: int = 5,
    start: int = 750,
    win: int = 1000,
    nsim: int = 2_000,
    spec: str = BACKTEST_SPEC,
    levels: tuple[float, ...] = (0.90, 0.50),
    max_windows: int | None = 300,
    progress=None,
) -> pd.DataFrame:
    """Disjoint-window walk-forward backtest (step == H, as the reference insists).

    For every window three interval methods are scored out-of-sample:

    ``sim_t``     simulate the fitted model and take empirical quantiles
    ``var_norm``  aggregate the variance forecast, use normal quantiles
    ``naive``     flat √T scaling of today's conditional σ, normal quantiles

    PIT is computed from the simulated terminal distribution (its uniformity is
    the sharpest single test of the whole chain). ``spec`` defaults to the
    reference's GJR-t regardless of which specification the report selected —
    the point is to score one fixed model, not the BIC winner.
    """
    r = pd.Series(r, dtype=float).dropna()
    n = len(r)
    lo_q, hi_q = (1 - max(levels)) / 2, 1 - (1 - max(levels)) / 2
    starts = list(range(int(start), n - H, max(1, int(H))))
    truncated = False
    if max_windows and len(starts) > max_windows:
        # keep the most recent windows — the interesting regime
        starts = starts[-int(max_windows):]
        truncated = True
    rows: list[dict[str, Any]] = []
    for k, t0 in enumerate(starts):
        hist = r.iloc[max(0, t0 - win):t0] * 100.0
        if len(hist) < 100:
            continue
        real = float(r.iloc[t0:t0 + H].sum())
        try:
            res = arch_model(hist, mean="Constant", vol="GARCH", **SPECS[spec]).fit(
                disp="off", show_warning=False
            )
            var_path = np.asarray(
                res.forecast(horizon=H, reindex=False).variance.values[-1]
            ) / 1e4
            sims = np.asarray(
                res.forecast(horizon=H, method="simulation", simulations=int(nsim),
                             reindex=False).simulations.values[-1]
            ) / 100.0
        except Exception:  # noqa: BLE001 — skip a window that will not converge
            continue
        term = sims.sum(axis=1)
        sd_sim = float(np.std(term))
        lo_sim, hi_sim = np.percentile(term, [lo_q * 100, hi_q * 100])
        sg = float(np.sqrt(var_path.sum()))
        sg_now = float(res.conditional_volatility.iloc[-1] / 100)
        sg_naive = sg_now * np.sqrt(H)
        row: dict[str, Any] = {
            "t0": int(t0),
            "date": r.index[t0],
            "real": real,
            "pit": float((term < real).mean()) if sd_sim > 0 else np.nan,
            "sim_lo90": float(lo_sim), "sim_hi90": float(hi_sim),
            "var_lo90": float(-1.645 * sg), "var_hi90": float(1.645 * sg),
            "naive_lo90": float(-1.645 * sg_naive), "naive_hi90": float(1.645 * sg_naive),
            "sigma_H": sg,
            "sigma_naive": sg_naive,
        }
        for method, lo, hi in (
            ("sim_t", lo_sim, hi_sim),
            ("var_norm", -1.645 * sg, 1.645 * sg),
            ("naive", -1.645 * sg_naive, 1.645 * sg_naive),
        ):
            row[f"breach90_{method}"] = int(real < lo or real > hi)
        for method, sd in (("sim_t", sd_sim), ("var_norm", sg), ("naive", sg_naive)):
            z = abs(real) / sd if sd > 0 else np.nan
            row[f"breach50_{method}"] = int(np.isfinite(z) and z > 0.6745)
        rows.append(row)
        if progress is not None and (k % 25 == 0 or k == len(starts) - 1):
            progress((k + 1) / max(1, len(starts)))
    bt = pd.DataFrame(rows)
    bt.attrs["truncated"] = truncated
    bt.attrs["n_available"] = len(list(range(int(start), n - H, max(1, int(H)))))
    return bt


def backtest_summary(bt: pd.DataFrame, levels: tuple[float, ...] = (0.90, 0.50)) -> pd.DataFrame:
    """Coverage + Kupiec + Christoffersen per method and nominal level."""
    if bt.empty:
        return pd.DataFrame()
    labels = {"sim_t": "GARCH, simulated t", "var_norm": "GARCH var + normal",
              "naive": "naive flat √T"}
    rows = []
    for lvl in levels:
        tag = f"{int(lvl * 100)}"
        for method, label in labels.items():
            col = f"breach{tag}_{method}"
            if col not in bt.columns:
                continue
            x = int(bt[col].sum())
            n = int(bt[col].notna().sum())
            rows.append(
                {
                    "H": int(bt.attrs.get("H", 0)) or None,
                    "method": label,
                    "nominal": lvl,
                    "actual": 1 - x / n if n else np.nan,
                    "n_windows": n,
                    "breaches": x,
                    "kupiec_p": kupiec(x, n, 1 - lvl) if n else np.nan,
                    "independence_p": christoffersen(bt[col].values),
                }
            )
    out = pd.DataFrame(rows)
    if "H" in out.columns and out["H"].isna().all():
        out = out.drop(columns=["H"])
    return out


# --------------------------------------------------------------------------- #
# 7. Entry point
# --------------------------------------------------------------------------- #
def report(
    close: pd.Series,
    *,
    H: int = 60,
    win: int = 1500,
    est_window: int = 20,
    lam: float = 0.94,
    nsim: int = 20_000,
    spec: str = "auto",
    ann: float | None = None,
    ohlc: pd.DataFrame | None = None,
    synth_bars: int = 0,
    n_events: int = 0,
    event_move: float = 0.0,
) -> dict:
    """Run the whole chain on one priced series. Returns a plain dict of results.

    Parameters mirror the reference's ``report()``; ``win`` restricts the GARCH
    fit to the trailing ``win`` periods (``None`` = full history), and ``ann``
    overrides the annualisation factor inferred from the index.
    """
    s = pd.Series(close).astype(float).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if len(s) < 60:
        raise ValueError(f"need at least 60 observations, got {len(s)}")

    ann = float(ann) if ann else ann_factor(s.index)
    ppy = periods_per_year(s.index)
    r, ret_kind = period_returns(s)
    r_all = r
    r = r.iloc[-int(win):] if win else r
    if len(r) < 60:
        raise ValueError(f"estimation window too short: {len(r)} periods")

    bars = ohlc
    bars_source = "provided"
    if bars is None and synth_bars and synth_bars > 1:
        bars = synthetic_ohlc(s, synth_bars)
        bars_source = "synthetic"
    elif bars is None:
        bars_source = "none"

    diag = diagnose(r)
    fit = fit_model(r, spec=spec)
    res = fit.res
    st = structure(res, ppy)
    hz = horizon_sigma(res, H, ppy, st=st)
    ev = add_events(hz["sigma_H"], n_events, event_move, ann) if n_events else None
    dist = distribution(res, H, nsim=nsim, S0=float(s.iloc[-1]),
                        sigma_H=hz["sigma_H"])

    zres = (res.resid / res.conditional_volatility).dropna()
    resid_ok = {
        "excess_kurtosis": _safe_p(stats.kurtosis, zres),
        "arch_lm_p": _safe_p(lambda: het_arch(zres, nlags=10)[1]),
        "skew": _safe_p(stats.skew, zres),
        "n": int(len(zres)),
    }
    yrs = len(r) / ppy
    drift = {
        "mu_period": float(r.mean()),
        "mu_ann": float(r.mean() * ppy),
        "se_ann": float(r.std() * np.sqrt(ppy) / np.sqrt(max(yrs, 1e-9))),
        "contribution_over_H": float(r.mean() * H),
        "sigma_over_H": hz["sigma_H"],
        "years": float(yrs),
        "periods_per_year": float(ppy),
    }
    sig_today = st["sigma_today_ann"]
    return {
        "series": s,
        "returns": r_all,
        "fit_returns": r,
        "return_kind": ret_kind,
        "restricted": bool(win and len(r_all) > len(r)),
        "ann": ann,
        "periods_per_year": ppy,
        "model": fit.name,
        "fit": res,
        "bic_table": fit.bic_table,
        "fit_failures": fit.failures,
        "diagnostics": diag,
        "structure": st,
        "horizon": hz,
        "events": ev,
        "distribution": dist,
        "drift": drift,
        "residuals": resid_ok,
        "residual_z": zres,
        "estimators": estimator_table(r, bars, ann, est_window, lam),
        "acf": acf_data(r),
        "qq_raw": qq_data(r.values / (r.std() or 1.0), "normal"),
        "qq_resid_norm": qq_data(zres.values, "normal"),
        "qq_resid_t": qq_data(zres.values, "t", st.get("nu")),
        "cond_vol": res.conditional_volatility * ann,
        "bars_source": bars_source,
        "bars_info": ohlc_report(bars) if bars is not None else None,
        "readout": {
            "last": float(s.iloc[-1]),
            "sigma_today": sig_today,
            "sigma_inf": st["sigma_inf_ann"],
            "sigma_H": hz["sigma_H"],
            "sigma_H_naive": hz["sigma_H_naive"],
            "persistence": st["persistence"],
            "half_life": st["half_life_periods"],
        },
    }
