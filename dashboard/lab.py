"""Signal Lab — pure-computation toolkit for deep time-series analysis.

Everything the Streamlit "Signal Lab" page renders is computed here, kept free
of Streamlit imports so the module stays unit-testable and reusable. Coverage:

* transformations (level / diff / % change / log / log-return / index / z-score
  and STL-based components / seasonally-adjusted series)
* calendar & performance metrics (MoM, QoQ, YoY, MTD, YTD, annual performance)
* decomposition (STL for odd periods, classical moving-average otherwise)
  with Hyndman trend/seasonality strength measures
* cyclicality (ACF/PACF, Ljung-Box per lag, cycle profiles, seasonal subseries,
  year x period heatmaps, lag-scatter helpers)
* frequency domain (periodogram, Welch PSD, dominant-period peaks,
  Morlet-wavelet scalogram via FFT convolution)
* time-domain filters (Hodrick-Prescott, Baxter-King, Christiano-Fitzgerald,
  Butterworth low/high/band-pass, centred MA, EMA) with frequency responses
* distribution & risk (KDE, normal fits, QQ data, rolling moments, drawdown,
  ridge-plot data, by-cycle box data)
* multi-series correlation (alignment, level/return matrices, rolling corr,
  lead-lag cross-correlation)
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import signal as spsig
from scipy import stats as sps
from statsmodels.tsa.filters.bk_filter import bkfilter
from statsmodels.tsa.filters.cf_filter import cffilter
from statsmodels.tsa.filters.hp_filter import hpfilter
from statsmodels.tsa.seasonal import STL, seasonal_decompose
from statsmodels.tsa.stattools import acf, adfuller, kpss, pacf

MIN_POINTS = 8  # refuse to analyse anything shorter than this
MIN_CYCLES = 2  # need at least two full seasonal cycles for seasonal work

PALETTE = [
    "#2563eb", "#ea580c", "#059669", "#d97706",
    "#7c3aed", "#dc2626", "#0891b2", "#65a30d",
]

OFFSET_LABELS = {
    "MS": "monthly", "QS": "quarterly", "W": "weekly",
    "D": "daily", "B": "business-daily",
}

# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def sanitize(s: pd.Series) -> pd.Series:
    """Replace ±inf with NaN and drop missing values — finite-only series."""
    if isinstance(s, pd.Series):
        return s.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    return pd.Series(np.asarray(s, dtype=float)).replace(
        [np.inf, -np.inf], np.nan).dropna()


def _finite(x: np.ndarray) -> np.ndarray:
    return np.asarray(x, dtype=float)[np.isfinite(x)]


def period_for_offset(offset: str) -> int:
    """Seasonal period implied by a pandas offset alias."""
    base = (offset or "").split("-")[0]
    return {"MS": 12, "QS": 4, "W": 52, "D": 7, "B": 5}.get(base, 1)


def offset_label(offset: str) -> str:
    base = (offset or "").split("-")[0]
    return OFFSET_LABELS.get(base, offset or "?")


def median_gap_days(s: pd.Series) -> float:
    """Median calendar spacing of the (regular) index, in days."""
    if len(s) < 2:
        return 1.0
    gaps = np.diff(s.index.asi8) / (1e9 * 86400.0)
    return float(np.median(gaps)) or 1.0


def period_to_calendar(period_samples: float, gap_days: float) -> tuple[float, str]:
    """Convert a period measured in samples to calendar units (value, unit)."""
    days = period_samples * gap_days
    if days >= 365:
        return days / 365.25, "years"
    if days >= 28:
        return days / 30.44, "months"
    if days >= 7:
        return days / 7, "weeks"
    return days, "days"


# --------------------------------------------------------------------------- #
# Transformations
# --------------------------------------------------------------------------- #
TRANSFORMS = {
    "Level": "level",
    "First difference": "diff",
    "% change (period-over-period)": "pct",
    "Log level": "log",
    "Log difference (≈ returns, %)": "logdiff",
    "Index (base = 100)": "index",
    "Z-score": "zscore",
    "Seasonally adjusted (STL)": "sa",
    "STL trend component": "stl_trend",
    "STL seasonal component": "stl_seasonal",
    "STL residual component": "stl_resid",
}


def transform_series(
    s: pd.Series,
    kind: str,
    base: pd.Timestamp | None = None,
    period: int | None = None,
) -> pd.Series:
    """Apply a transformation to a level series. Returns a new Series."""
    s = sanitize(s)
    if kind == "level":
        out = s.copy()
    elif kind == "diff":
        out = s.diff()
    elif kind == "pct":
        out = s.pct_change() * 100.0
    elif kind == "log":
        if (s <= 0).any():
            raise ValueError("log transform requires strictly positive values")
        out = np.log(s)
    elif kind == "logdiff":
        if (s <= 0).any():
            raise ValueError("log transform requires strictly positive values")
        out = np.log(s).diff() * 100.0
    elif kind == "index":
        base_val = float(s.asof(pd.Timestamp(base))) if base is not None else float(s.iloc[0])
        if not np.isfinite(base_val) or base_val == 0:
            raise ValueError("index base value is zero or missing — pick another base date")
        out = s / base_val * 100.0
    elif kind == "zscore":
        out = (s - s.mean()) / (s.std(ddof=1) or np.nan)
    elif kind in ("sa", "stl_trend", "stl_seasonal", "stl_resid"):
        if period is None:
            gap = median_gap_days(s)
            has_weekend = bool((s.index.dayofweek >= 5).any())
            period = (4 if gap >= 80 else 12 if gap >= 27 else 52 if gap >= 6
                      else 7 if has_weekend else 5)
        comp = decompose(s, period)
        out = {
            "sa": s - comp["seasonal"],
            "stl_trend": comp["trend"],
            "stl_seasonal": comp["seasonal"],
            "stl_resid": comp["resid"],
        }[kind]
    else:
        raise ValueError(f"unknown transform {kind!r}")
    return sanitize(out)


# --------------------------------------------------------------------------- #
# Decomposition
# --------------------------------------------------------------------------- #
def decompose(s: pd.Series, period: int, method: str = "auto",
              robust: bool = True) -> dict:
    """Trend/seasonal/residual decomposition.

    ``method``: "auto" (STL for odd periods, classical otherwise — STL needs an
    odd seasonal period), "stl", "classical_add", "classical_mul". Also reports
    Hyndman's strength-of-trend/seasonality (additive scale only).
    """
    s = sanitize(s)
    if method == "stl" and period % 2 == 0:
        raise ValueError("STL requires an odd seasonal period (monthly/quarterly "
                         "series need the classical decomposition)")
    use_stl = method == "stl" or (method == "auto" and period % 2 == 1)
    if use_stl:
        if len(s) < 2 * period + 1:
            raise ValueError(f"STL needs at least {2 * period + 1} observations "
                             f"(got {len(s)})")
        res = STL(s, period=period, robust=robust).fit()
        trend, seasonal, resid = res.trend, res.seasonal, res.resid
        label = "STL (Loess)"
        resid = s - trend - seasonal
    else:
        model = "multiplicative" if method == "classical_mul" else "additive"
        res = seasonal_decompose(
            s, model=model, period=period,
            two_sided=True, extrapolate_trend="freq",
        )
        trend, seasonal = res.trend, res.seasonal
        resid = (s / trend / seasonal) if model == "multiplicative" else (s - trend - seasonal)
        label = f"classical {model} (moving average)"
    trend = trend.reindex(s.index)
    seasonal = seasonal.reindex(s.index)
    resid = resid.reindex(s.index)

    if method == "classical_mul":
        f_trend = f_seasonal = np.nan
    else:
        def strength(comp: pd.Series, resid_s: pd.Series) -> float:
            denom = np.nanvar(comp) + np.nanvar(resid_s)
            if not np.isfinite(denom) or denom == 0:
                return np.nan
            return float(max(0.0, 1.0 - np.nanvar(resid_s) / denom))

        f_trend = strength(trend, resid)
        f_seasonal = strength(seasonal, resid)

    return {
        "method": label,
        "trend": trend,
        "seasonal": seasonal,
        "resid": resid,
        "f_trend": f_trend,
        "f_seasonal": f_seasonal,
        "seasonal_std": float(np.nanstd(seasonal)),
        "trend_std": float(np.nanstd(trend)),
        "resid_std": float(np.nanstd(resid)),
    }


# --------------------------------------------------------------------------- #
# Seasonal structure helpers
# --------------------------------------------------------------------------- #
def cycle_positions(s: pd.Series, period: int) -> np.ndarray:
    """Position inside the cycle (1..period) for a regular series."""
    n = len(s)
    return (np.arange(n) % period) + 1


def seasonal_subseries(s: pd.Series, period: int) -> pd.DataFrame:
    """Pivot: one row per cycle (labelled by its start year), columns 1..period."""
    s = sanitize(s)
    pos = cycle_positions(s, period)
    cyc = (np.arange(len(s)) // period)
    df = pd.DataFrame({"cycle": cyc, "pos": pos, "value": s.to_numpy()})
    piv = df.pivot_table(index="cycle", columns="pos", values="value", aggfunc="mean")
    starts = s.index[::period][: len(piv)]
    labels = [f"{ts.year}" if not pd.isna(ts) else f"c{i}" for i, ts in enumerate(starts)]
    piv.index = labels[: len(piv)]
    return piv


def cycle_profile(s: pd.Series, period: int) -> pd.DataFrame:
    """Mean / median / quartiles per position inside the cycle."""
    s = sanitize(s)
    pos = cycle_positions(s, period)
    df = pd.DataFrame({"pos": pos, "value": s.to_numpy()})
    return df.groupby("pos")["value"].agg(
        mean="mean", std="std", q25=lambda x: np.quantile(x, 0.25),
        median="median", q75=lambda x: np.quantile(x, 0.75),
        n="count",
    ).reset_index()


def year_period_matrix(s: pd.Series, period: int) -> pd.DataFrame:
    """Year x cycle-position matrix of average values (levels)."""
    s = sanitize(s)
    pos = cycle_positions(s, period)
    df = pd.DataFrame({"year": s.index.year, "pos": pos, "value": s.to_numpy()})
    piv = df.pivot_table(index="year", columns="pos", values="value", aggfunc="mean")
    return piv.sort_index()


def yoy_matrix(piv: pd.DataFrame, period: int) -> pd.DataFrame:
    """Year x position matrix of % change vs the same position one year earlier."""
    if len(piv) < 2:
        return piv * np.nan
    out = piv.pct_change(periods=1, fill_method=None) * 100.0
    return out.replace([np.inf, -np.inf], np.nan)


# --------------------------------------------------------------------------- #
# Cyclicality: ACF/PACF & friends
# --------------------------------------------------------------------------- #
def acf_pacf(s: pd.Series, nlags: int) -> dict:
    s = sanitize(s)
    nlags = min(nlags, max(1, len(s) - 2))
    out: dict = {}
    try:
        res = acf(s, nlags=nlags, fft=True, alpha=0.05, qstat=True)
        out["acf"] = np.asarray(res[0])
        out["conf"] = np.asarray(res[1])
        out["qstat"] = np.asarray(res[2])
        out["q_pvalues"] = np.asarray(res[3])
    except Exception:
        out["acf"] = np.asarray(acf(s, nlags=nlags, fft=True))
        out["conf"] = None
        out["qstat"] = None
        out["q_pvalues"] = None
    try:
        pacf_res = pacf(s, nlags=nlags, alpha=0.05)
        out["pacf"] = np.asarray(pacf_res[0])
        out["pacf_conf"] = np.asarray(pacf_res[1])
    except Exception:
        out["pacf"] = np.asarray(pacf(s, nlags=nlags))
        out["pacf_conf"] = None
    out["lags"] = np.arange(nlags + 1)
    return out


def stationarity(s: pd.Series) -> dict:
    s = sanitize(s)
    out = {"adf_pvalue": np.nan, "kpss_pvalue": np.nan}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            out["adf_pvalue"] = float(adfuller(s, autolag="AIC")[1])
        except Exception:
            pass
        try:
            out["kpss_pvalue"] = float(kpss(s, regression="c", nlags="auto")[1])
        except Exception:
            pass
    return out


# --------------------------------------------------------------------------- #
# Frequency domain
# --------------------------------------------------------------------------- #
def _detrend(s: pd.Series) -> np.ndarray:
    x = sanitize(s).to_numpy(dtype=float)
    if len(x) < 3:
        return x - x.mean()
    t = np.arange(len(x))
    coef = np.polyfit(t, x, 1)
    return x - np.polyval(coef, t)


def periodogram(s: pd.Series) -> dict:
    """Classical periodogram of the linearly detrended series."""
    x = _detrend(s)
    freq, power = spsig.periodogram(x, detrend=False)
    return {"freq": freq, "power": power}


def welch_psd(s: pd.Series, nperseg: int) -> dict:
    x = _detrend(s)
    nperseg = int(min(max(nperseg, 8), len(x)))
    freq, power = spsig.welch(x, nperseg=nperseg, detrend=False)
    return {"freq": freq, "power": power}


def dominant_peaks(freq: np.ndarray, power: np.ndarray, gap_days: float,
                   top: int = 8) -> pd.DataFrame:
    """Top spectral peaks with periods in samples and calendar units."""
    f = np.asarray(freq, dtype=float)
    p = np.asarray(power, dtype=float)
    mask = np.isfinite(f) & np.isfinite(p) & (f > 0)
    f, p = f[mask], p[mask]
    if len(f) < 3:
        return pd.DataFrame()
    if np.all(p <= 0):
        return pd.DataFrame()
    threshold = float(np.nanmax(p)) * 0.02
    idx, _ = spsig.find_peaks(p, height=threshold, distance=2)
    if len(idx) == 0:
        idx = np.array([int(np.argmax(p))])
    order = np.argsort(p[idx])[::-1][:top]
    rows = []
    for i in order:
        pi = idx[i]
        period_samples = 1.0 / f[pi]
        cal, unit = period_to_calendar(period_samples, gap_days)
        rows.append({
            "peak": i + 1,
            "period (samples)": round(period_samples, 2),
            f"period ({unit})": round(cal, 2),
            "frequency (cycles/sample)": round(float(f[pi]), 6),
            "power": float(p[pi]),
        })
    return pd.DataFrame(rows)


def morlet_wavelet(s: pd.Series, dt: float = 1.0, n_scales: int = 80,
                   w0: float = 6.0) -> dict:
    """Continuous Morlet wavelet transform via FFT convolution.

    Returns the complex coefficient matrix (scales x time) with pseudo-periods
    in samples and calendar units (Torrence & Compo convention).
    """
    x = _detrend(s)
    if len(x) < 4 or not np.all(np.isfinite(x)):
        raise ValueError("wavelet needs ≥ 4 finite observations")
    n = len(x)
    n_scales = int(min(max(n_scales, 8), n // 2))
    scales = np.logspace(np.log10(2.0), np.log10(max(2.0, n / 2.0)), n_scales)
    fft_x = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, d=dt)
    coef = np.zeros((n_scales, n), dtype=complex)
    for i, a in enumerate(scales):
        # F[psi(t/a)/sqrt(a)](w) = sqrt(a) * pi^(-1/4) * sqrt(2 pi) * exp(-(a w - w0)^2 / 2)
        psi_hat = np.sqrt(a) * np.pi ** -0.25 * np.sqrt(2 * np.pi) * np.exp(
            -0.5 * (2 * np.pi * a * freqs - w0) ** 2
        )
        psi_hat[freqs <= 0] = 0.0
        coef[i] = np.fft.irfft(fft_x * np.conj(psi_hat), n=n)
    # pseudo-period of the Morlet at scale a (Torrence & Compo 1998)
    fourier_factor = 4 * np.pi / (w0 + np.sqrt(2 + w0 ** 2))
    periods_samples = scales * fourier_factor
    gap = median_gap_days(s)
    cal = np.array([period_to_calendar(p, gap)[0] for p in periods_samples])
    return {
        "coef": coef,
        "scales": scales,
        "periods_samples": periods_samples,
        "periods_cal": cal,
        "gap_days": gap,
        "unit": period_to_calendar(periods_samples[-1], gap)[1],
        "times": s.index,
    }


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #
FILTERS = {
    "None": "none",
    "Hodrick-Prescott": "hp",
    "Baxter-King band-pass": "bk",
    "Christiano-Fitzgerald band-pass": "cf",
    "Butterworth low-pass": "bw_low",
    "Butterworth high-pass": "bw_high",
    "Butterworth band-pass": "bw_band",
    "Centred moving average": "ma",
    "EMA (exponential smoothing)": "ema",
}


def default_filter_params(kind: str, period: int) -> dict:
    """Sensible defaults for each filter given the seasonal period."""
    hp_map = {4: 1600.0, 12: 129600.0, 52: 270400.0, 7: 1e6, 5: 1e6}
    low = {4: 2, 12: 6, 52: 13, 7: 7, 5: 5}.get(period, 6)
    high = {4: 8, 12: 32, 52: 104, 7: 365, 5: 260}.get(period, 32)
    k = {4: 12, 12: 24, 52: 52, 7: 45, 5: 45}.get(period, 24)
    return {
        "hp": {"lambda": hp_map.get(period, 129600.0)},
        "bk": {"low": low, "high": high, "K": k},
        "cf": {"low": low, "high": high},
        "bw_low": {"cutoff": max(4, period * 2)},
        "bw_high": {"cutoff": max(2, period)},
        "bw_band": {"low": max(2, period // 2), "high": max(4, period * 2)},
        "ma": {"window": 2 * period + 1},
        "ema": {"span": max(3, period)},
        "none": {},
    }[kind]


def _freq_response_ma(window: int, npoints: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    w = np.linspace(1e-6, np.pi, npoints)
    mag = np.abs(np.sin(w * window / 2) / (window * np.sin(w / 2)))
    freq = w / (2 * np.pi)  # cycles per sample
    return freq, mag


def filter_series(s: pd.Series, kind: str, params: dict | None = None) -> dict:
    """Apply a time-domain filter; return pass band, complement and response.

    For HP/BK/CF the pass band is the cyclical component and the complement the
    trend; for smoothing filters the pass band is the smooth and the complement
    the high-frequency residual. ``freq``/``mag`` hold the (theoretical)
    frequency response when available.
    """
    s = sanitize(s)
    params = params or {}
    if kind == "none" or not kind:
        return {
            "pass": s.copy(), "comp": s * np.nan,
            "pass_label": "original", "comp_label": "—",
            "freq": None, "mag": None, "kind": "none",
        }
    freq = mag = None

    if kind == "hp":
        lam = float(params.get("lambda", 129600.0))
        cycle, trend = hpfilter(s, lamb=lam)
        passband, comp = cycle, trend
        pass_label, comp_label = "cycle (pass band)", "trend (complement)"
    elif kind == "bk":
        low, high = float(params["low"]), float(params["high"])
        if not (2 <= low < high):
            raise ValueError("Baxter-King needs 2 ≤ low < high (periods)")
        k = int(params.get("K", 24))
        need = 2 * k + 1
        if len(s) <= need:
            raise ValueError(f"Baxter-King needs > {need} observations (got {len(s)}) — lower K")
        cycle = bkfilter(s, low=low, high=high, K=k)
        passband, comp = pd.Series(cycle, index=s.index), s - cycle
        pass_label, comp_label = f"band {low:g}–{high:g} periods", "complement"
    elif kind == "cf":
        low, high = float(params["low"]), float(params["high"])
        if not (2 <= low < high):
            raise ValueError("Christiano-Fitzgerald needs 2 ≤ low < high (periods)")
        cycle, trend = cffilter(s, low=low, high=high, drift=False)
        passband, comp = cycle, trend
        pass_label, comp_label = f"band {low:g}–{high:g} periods", "trend (complement)"
    elif kind in ("bw_low", "bw_high", "bw_band"):
        order = int(params.get("order", 4))
        if kind == "bw_low":
            cut = max(2.0, float(params["cutoff"]))
            wn = 2.0 / cut  # cutoff period in samples -> normalised freq (Nyquist=1)
            btype = "lowpass"
            pass_label, comp_label = f"low-pass (≤ {cut:g} periods)", "high-frequency residual"
        elif kind == "bw_high":
            cut = max(2.0, float(params["cutoff"]))
            wn = 2.0 / cut
            btype = "highpass"
            pass_label, comp_label = f"high-pass (≥ {cut:g} periods)", "low-frequency trend"
        else:
            low = max(2.0, float(params["low"]))
            high = max(low + 1.0, float(params["high"]))
            wn = [2.0 / high, 2.0 / low]
            btype = "bandpass"
            pass_label, comp_label = f"band {low:g}–{high:g} periods", "complement"
        wn = min(wn, 0.99) if np.isscalar(wn) else [min(w, 0.99) for w in wn]
        sos = spsig.butter(order, wn, btype=btype, output="sos")
        passband = pd.Series(spsig.sosfiltfilt(sos, s.to_numpy()), index=s.index)
        comp = s - passband
        w, h = spsig.sosfreqz(sos, worN=2048)
        freq = w / (2 * np.pi)  # cycles per sample
        mag = np.abs(h)
    elif kind == "ma":
        window = int(params.get("window", 13))
        if window % 2 == 0:
            window += 1
        passband = s.rolling(window, center=True, min_periods=max(3, window // 2)).mean()
        comp = s - passband
        pass_label, comp_label = f"{window}-period centred MA", "high-frequency residual"
        freq, mag = _freq_response_ma(window)
    elif kind == "ema":
        span = float(params.get("span", 12))
        passband = s.ewm(span=span, adjust=False).mean()
        comp = s - passband
        pass_label, comp_label = f"EMA (span {span:g})", "high-frequency residual"
    else:
        raise ValueError(f"unknown filter {kind!r}")

    return {
        "pass": passband, "comp": comp,
        "pass_label": pass_label, "comp_label": comp_label,
        "freq": freq, "mag": mag, "kind": kind,
    }


# --------------------------------------------------------------------------- #
# Distribution & risk
# --------------------------------------------------------------------------- #
def summary_stats(s: pd.Series) -> dict:
    s = sanitize(s)
    if s.empty:
        return {"n": 0, "mean": np.nan, "std": np.nan, "min": np.nan, "max": np.nan,
                "skew": np.nan, "kurt": np.nan, "q05": np.nan, "q95": np.nan,
                "jb_pvalue": np.nan}
    out = {
        "n": int(len(s)), "mean": float(s.mean()), "std": float(s.std(ddof=1)),
        "min": float(s.min()), "max": float(s.max()),
        "skew": float(s.skew()), "kurt": float(s.kurt()),
        "q05": float(s.quantile(0.05)), "q95": float(s.quantile(0.95)),
    }
    try:
        out["jb_pvalue"] = float(sps.jarque_bera(s)[1])
    except Exception:
        out["jb_pvalue"] = np.nan
    return out


def density(s: pd.Series, npoints: int = 300) -> dict:
    """KDE of the series plus a normal fit (MLE) on the same grid."""
    x = _finite(sanitize(s).to_numpy(dtype=float))
    out = {"n": len(x)}
    if len(x) < 2 or float(np.std(x)) == 0:
        return {**out, "x": np.array([]), "kde": np.array([]), "normal": np.array([])}
    grid = np.linspace(float(x.min()), float(x.max()), npoints)
    out["x"] = grid
    out["kde"] = sps.gaussian_kde(x)(grid)
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    out["normal"] = sps.norm.pdf(grid, mu, sd)
    out["mu"], out["sd"] = mu, sd
    return out


def qq_data(s: pd.Series) -> dict:
    x = _finite(sanitize(s).to_numpy(dtype=float))
    if len(x) < 4 or float(np.std(x)) == 0:
        return {"theoretical": np.array([]), "sample": np.array([])}
    (osm, osr), _ = sps.probplot(x, dist="norm")
    return {"theoretical": np.asarray(osm), "sample": np.asarray(osr)}


def rolling_moments(s: pd.Series, window: int) -> pd.DataFrame:
    s = sanitize(s)
    window = int(min(max(window, 10), max(10, len(s))))
    r = s.rolling(window, min_periods=max(5, window // 2))
    return pd.DataFrame({
        "mean": r.mean(), "std": r.std(ddof=0),
        "skew": r.skew(), "kurt": r.kurt(),
        "q05": s.rolling(window, min_periods=max(5, window // 2)).quantile(0.05),
        "q95": s.rolling(window, min_periods=max(5, window // 2)).quantile(0.95),
    })


def drawdown(s: pd.Series) -> pd.Series:
    s = sanitize(s)
    return s / s.cummax() - 1.0


def ridge_data(s: pd.Series, min_obs: int = 5, npoints: int = 200) -> list[dict]:
    """Per-year KDEs for a ridge plot. Returns [{year, x, y}, ...]."""
    s = sanitize(s)
    years = sorted(s.index.year.unique())
    groups = [s[s.index.year == y].to_numpy(dtype=float) for y in years]
    kept = [(y, g) for y, g in zip(years, groups)
            if len(g) >= min_obs and float(np.std(g)) > 0]
    if not kept:
        return []
    lo = float(min(g.min() for _, g in kept))
    hi = float(max(g.max() for _, g in kept))
    grid = np.linspace(lo, hi, npoints)
    out = []
    for y, g in kept:
        out.append({"year": y, "x": grid, "y": sps.gaussian_kde(g)(grid)})
    return out


def by_cycle_box(s: pd.Series, period: int) -> pd.DataFrame:
    s = sanitize(s)
    pos = cycle_positions(s, period)
    df = pd.DataFrame({"pos": pos, "value": s.to_numpy()})
    return df


# --------------------------------------------------------------------------- #
# Calendar & performance metrics
# --------------------------------------------------------------------------- #
def _asof(s: pd.Series, ts: pd.Timestamp) -> float:
    """Value at (or before) a timestamp; NaN when nothing precedes it."""
    v = s.asof(ts)
    return float(v) if pd.notna(v) else np.nan


def calendar_stats(s: pd.Series) -> dict:
    """Last value with MoM/QoQ/YoY/MTD/YTD changes (levels and %)."""
    s = sanitize(s)
    if s.empty:
        return {"n": 0, "last": np.nan}
    out: dict = {"n": int(len(s))}
    last = float(s.iloc[-1])
    out["last"] = last
    out["last_date"] = s.index[-1]

    def chg(name: str, base_ts: pd.Timestamp) -> None:
        b = _asof(s, base_ts)
        if not np.isfinite(b) or b == 0:
            out[name] = out[f"{name}_pct"] = np.nan
            return
        out[name] = last - b
        out[f"{name}_pct"] = (last / b - 1.0) * 100.0

    prev = float(s.iloc[-2]) if len(s) >= 2 else np.nan
    out["prev"] = prev
    out["pop"] = last - prev if np.isfinite(prev) else np.nan
    out["pop_pct"] = (last / prev - 1.0) * 100.0 if np.isfinite(prev) and prev != 0 else np.nan

    d = s.index[-1]
    chg("mom", d - pd.DateOffset(months=1))
    chg("qoq", d - pd.DateOffset(months=3))
    chg("yoy", d - pd.DateOffset(years=1))
    chg("ytd", pd.Timestamp(year=d.year, month=1, day=1) - pd.Timedelta(days=1))
    chg("mtd", pd.Timestamp(year=d.year, month=d.month, day=1) - pd.Timedelta(days=1))
    return out


def recent_table(s: pd.Series, rows: int = 14) -> pd.DataFrame:
    """Recent observations with period-over-period and YoY % changes."""
    s = sanitize(s)
    tail = s.tail(rows)
    out = pd.DataFrame({"date": tail.index, "value": tail.to_numpy()})
    out["chg"] = tail.diff()
    out["pop_pct"] = tail.pct_change() * 100.0

    def _yoy(v: float, d: pd.Timestamp) -> float:
        b = _asof(s, d - pd.DateOffset(years=1))
        return (v / b - 1.0) * 100.0 if np.isfinite(b) and b != 0 else np.nan

    out["yoy_pct"] = [_yoy(v, d) for v, d in zip(tail.to_numpy(), tail.index)]
    for col in ("chg", "pop_pct", "yoy_pct"):
        out[col] = out[col].replace([np.inf, -np.inf], np.nan)
    return out


def annual_performance(s: pd.Series) -> pd.DataFrame:
    """Yearly % performance (last obs of year vs last obs of prior year)."""
    s = sanitize(s)
    if s.empty:
        return pd.DataFrame(columns=["year", "last", "pct"])
    last_of = s.groupby(s.index.year).last()
    rows = []
    for y in last_of.index:
        prev = _asof(s, pd.Timestamp(year=int(y) - 1, month=12, day=31))
        val = float(last_of.loc[y])
        pct = (val / prev - 1.0) * 100.0 if np.isfinite(prev) and prev != 0 else np.nan
        rows.append({"year": int(y), "last": val, "pct": pct})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Multi-series correlation
# --------------------------------------------------------------------------- #
def align_frame(primary: pd.Series, others: dict[str, pd.Series]) -> pd.DataFrame:
    """Align companions onto the primary grid (forward-fill), keep common rows."""
    primary = sanitize(primary)
    df = pd.DataFrame({primary.name or "primary": primary})
    for name, s in others.items():
        s = sanitize(s).sort_index()
        aligned = s.reindex(s.index.union(primary.index)).ffill().reindex(primary.index)
        df[name] = aligned
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def corr_matrices(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Correlation matrices of levels and of period-over-period % changes."""
    df = df.replace([np.inf, -np.inf], np.nan)
    levels = df.corr()
    rets = df.pct_change().replace([np.inf, -np.inf], np.nan).dropna().corr()
    return levels, rets


def rolling_corr(df: pd.DataFrame, base: str, window: int) -> pd.DataFrame:
    df = df.replace([np.inf, -np.inf], np.nan)
    base_s = df[base]
    window = int(min(max(window, 10), max(10, len(df))))
    out = pd.DataFrame(index=df.index)
    for col in df.columns:
        if col == base:
            continue
        out[col] = base_s.rolling(window, min_periods=max(5, window // 2)).corr(df[col])
    return out


def lead_lag_corr(x: pd.Series, y: pd.Series, max_lag: int) -> pd.DataFrame:
    """Cross-correlation of y against x at lags -max..+max.

    Positive lag = y leads x by ``lag`` periods (corr(x[t], y[t-lag])).
    """
    x = sanitize(x); y = sanitize(y)
    df = pd.concat([x, y], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    xx, yy = df.iloc[:, 0], df.iloc[:, 1]
    rows = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = xx[lag:], yy[: len(yy) - lag]
        else:
            a, b = xx[: lag], yy[-lag:]
        a = _finite(a.to_numpy(dtype=float))
        b = _finite(b.to_numpy(dtype=float))
        n = min(len(a), len(b))
        if n < 10:
            rows.append({"lag": lag, "corr": np.nan, "n": n})
            continue
        corr = float(np.corrcoef(a[:n], b[:n])[0, 1]) if np.std(a[:n]) and np.std(b[:n]) else np.nan
        rows.append({"lag": lag, "corr": corr, "n": n})
    return pd.DataFrame(rows)
