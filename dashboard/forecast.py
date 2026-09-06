"""Time-series modelling for the FX/macro dashboard.

Implements the "best practice" loop end to end:

* calendar-aligned series preparation (business-day / month-start, forward-fill)
* walk-forward ("rolling origin") cross-validation — expanding or sliding window,
  always strictly out-of-sample (no leakage: models are re-fitted per fold)
* model zoo:
    - auto-ARIMA: AIC-selected SARIMAX orders (Box-Jenkins, optional seasonality)
    - Holt-Winters ETS (damped trend, additive seasonality)
    - naive-with-drift baseline (the benchmark the other models must beat)
* point forecast + prediction intervals (model-native where available)
* pooled out-of-sample error metrics: MSE, RMSE, MAE, MAPE, sMAPE, MASE, R²
* residual diagnostics: ADF/KPSS stationarity, Ljung-Box autocorrelation,
  Jarque-Bera normality, Engle's ARCH test, Durbin-Watson, ACF/PACF
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats as sps
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from statsmodels.stats.stattools import durbin_watson
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import acf, adfuller, kpss, pacf

MIN_POINTS = 14  # refuse to model anything shorter than this


# --------------------------------------------------------------------------- #
# Series preparation
# --------------------------------------------------------------------------- #
def detect_frequency(index: pd.DatetimeIndex, freq_label: str | None) -> tuple[str, int]:
    """Infer a pandas offset and seasonal period from label + observed dates.

    The catalog label is a hint; the dates decide. FRED "daily" policy rates
    (e.g. ECBDFR) are calendar-daily while spot/yields are business-daily, so a
    blanket "D → business days" would silently drop weekend observations.
    """
    label = (freq_label or "").strip().upper()
    if label.startswith("M"):
        return "MS", 12
    if label.startswith("Q"):
        return "QS", 4
    if label.startswith("W"):
        return "W", 52

    gaps = np.diff(index.asi8) / (1e9 * 86400.0)  # median spacing in days
    median_gap = float(np.median(gaps)) if gaps.size else 1.0
    if median_gap >= 27:
        return "MS", 12
    if median_gap >= 6:
        return "W", 52
    # daily: calendar (weekends present) vs business-day
    has_weekend = bool((index.dayofweek >= 5).any())
    return ("D", 7) if has_weekend else ("B", 5)


def prepare_series(obs: pd.DataFrame, freq_label: str | None) -> tuple[pd.Series, str, int]:
    """Sort, dedupe, calendar-align and forward-fill a series.

    Returns (series, offset, seasonal_period). Forward-fill reconstructs the
    step function for policy rates and carries yields/spot over non-trading days.
    """
    df = (
        obs[["obs_date", "value"]]
        .dropna()
        .sort_values("obs_date")
        .drop_duplicates("obs_date", keep="last")
    )
    idx = pd.DatetimeIndex(df["obs_date"])
    offset, period = detect_frequency(idx, freq_label)
    s = pd.Series(df["value"].to_numpy(), index=idx, dtype=float)
    full = pd.date_range(idx.min(), idx.max(), freq=offset)
    s = s.reindex(full).ffill()
    s = s.dropna()
    s.name = "value"
    return s, offset, period


# --------------------------------------------------------------------------- #
# Walk-forward cross-validation
# --------------------------------------------------------------------------- #
def walk_forward_splits(
    n: int,
    n_splits: int,
    horizon: int,
    window: int | None = None,
    min_initial: int = 30,
) -> list[tuple[int, int, int, int]]:
    """Return (train_start, train_end, test_start, test_end) index slices.

    ``window is None`` → expanding window (forward chaining); an int → rolling
    (sliding) window of that many observations. The test region always covers
    the most recent ``n_splits * horizon`` points, each fold forecasting the
    next ``horizon`` steps.
    """
    test_total = n_splits * horizon
    max_test = n - min_initial
    if test_total > max_test:
        n_splits = max(1, max_test // horizon)
        test_total = n_splits * horizon
    splits = []
    for k in range(n_splits):
        test_end = n - (n_splits - 1 - k) * horizon
        test_start = test_end - horizon
        train_end = test_start
        train_start = 0 if window is None else max(0, train_end - window)
        if train_end - train_start < min_initial:
            train_start = max(0, train_end - min_initial)
        splits.append((train_start, train_end, test_start, test_end))
    return splits


# --------------------------------------------------------------------------- #
# Model zoo
# --------------------------------------------------------------------------- #
class NaiveDrift:
    """Random walk with drift — the benchmark baseline."""

    name = "Naive drift (baseline)"

    def fit(self, y: pd.Series) -> "NaiveDrift":
        self._y = y
        self._resid = y.diff().dropna()
        self._drift = (float(y.iloc[-1]) - float(y.iloc[0])) / max(1, len(y) - 1)
        return self

    def point_forecast(self, horizon: int) -> np.ndarray:
        last = float(self._y.iloc[-1])
        return np.array([last + self._drift * (i + 1) for i in range(horizon)])

    def forecast_ci(self, horizon: int, alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        mean = self.point_forecast(horizon)
        sd = float(self._resid.std(ddof=1) or 0.0)
        z = sps.norm.ppf(1 - alpha / 2)
        steps = np.arange(1, horizon + 1)
        width = z * sd * np.sqrt(steps)
        return mean, mean - width, mean + width

    @property
    def fittedvalues(self) -> pd.Series:
        return self._y.shift(1)

    @property
    def residuals(self) -> pd.Series:
        return self._y - self.fittedvalues

    @property
    def aic(self) -> float:
        return float("nan")

    @property
    def bic(self) -> float:
        return float("nan")

    @property
    def summary_text(self) -> str:
        return (
            "Naive with drift (random-walk benchmark).\n"
            f"drift per period : {self._drift:.6g}\n"
            f"residual std     : {self._resid.std(ddof=1):.6g}\n"
        )


class ARIMAForecaster:
    """SARIMAX wrapper with fixed (or AIC-selected) orders."""

    def __init__(self, order, seasonal_order=(0, 0, 0, 0), trend=None):
        self.order = tuple(order)
        self.seasonal_order = tuple(seasonal_order)
        self.trend = trend
        self.name = (
            f"SARIMAX{self.order}"
            + (f"x{self.seasonal_order}" if any(self.seasonal_order) else "")
        )

    def fit(self, y: pd.Series) -> "ARIMAForecaster":
        kwargs = {}
        if self.trend is not None:
            kwargs["trend"] = self.trend
        self._model = SARIMAX(
            y,
            order=self.order,
            seasonal_order=self.seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
            **kwargs,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._res = self._model.fit(disp=False, maxiter=250)
        return self

    def point_forecast(self, horizon: int) -> np.ndarray:
        return np.asarray(self._res.forecast(horizon), dtype=float)

    def forecast_ci(self, horizon: int, alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        frame = self._res.get_forecast(horizon).summary_frame(alpha=alpha)
        return (
            np.asarray(frame["mean"], dtype=float),
            np.asarray(frame["mean_ci_lower"], dtype=float),
            np.asarray(frame["mean_ci_upper"], dtype=float),
        )

    @property
    def fittedvalues(self) -> pd.Series:
        return self._res.fittedvalues

    @property
    def residuals(self) -> pd.Series:
        return self._res.resid

    @property
    def aic(self) -> float:
        return float(self._res.aic)

    @property
    def bic(self) -> float:
        return float(self._res.bic)

    @property
    def summary_text(self) -> str:
        return self._res.summary().as_text()


class ETSForecaster:
    """Holt-Winters exponential smoothing with a damped additive trend."""

    def __init__(self, seasonal_periods: int | None = None):
        self.seasonal_periods = seasonal_periods
        self.name = "Holt-Winters ETS"

    def fit(self, y: pd.Series) -> "ETSForecaster":
        seasonal = "add" if self.seasonal_periods else None
        self._model = ExponentialSmoothing(
            y,
            trend="add",
            seasonal=seasonal,
            seasonal_periods=self.seasonal_periods,
            damped_trend=True,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._res = self._model.fit(optimized=True)
        return self

    def point_forecast(self, horizon: int) -> np.ndarray:
        return np.asarray(self._res.forecast(horizon), dtype=float)

    def forecast_ci(self, horizon: int, alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # ETS prediction intervals are simulation-based in statsmodels; fall back
        # to a normal interval off the residual variance if that fails.
        try:
            frame = self._res.get_forecast(horizon).summary_frame(alpha=alpha)
            return (
                np.asarray(frame["mean"], dtype=float),
                np.asarray(frame["mean_ci_lower"], dtype=float),
                np.asarray(frame["mean_ci_upper"], dtype=float),
            )
        except Exception:
            mean = self.point_forecast(horizon)
            sd = float(self.residuals.std(ddof=1) or 0.0)
            z = sps.norm.ppf(1 - alpha / 2)
            return mean, mean - z * sd, mean + z * sd

    @property
    def fittedvalues(self) -> pd.Series:
        return self._res.fittedvalues

    @property
    def residuals(self) -> pd.Series:
        return self._res.resid

    @property
    def aic(self) -> float:
        return float(self._res.aic)

    @property
    def bic(self) -> float:
        return float(self._res.bic)

    @property
    def summary_text(self) -> str:
        return str(self._res.summary())


# --------------------------------------------------------------------------- #
# Auto-ARIMA order selection
# --------------------------------------------------------------------------- #
def _determine_d(y: pd.Series, max_d: int) -> int:
    """Difference order via ADF until the series is stationary."""
    d = 0
    yy = y
    for _ in range(max_d):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                p = adfuller(yy, autolag="AIC")[1]
        except Exception:
            break
        if p < 0.05:
            break
        yy = yy.diff().dropna()
        d += 1
    return d


def select_arima_order(
    y: pd.Series,
    max_p: int = 2,
    max_q: int = 2,
    max_d: int = 2,
    seasonal: bool = False,
    period: int = 5,
    ic: str = "aic",
) -> dict:
    """AIC/BIC grid search over (p, d, q), optionally topping up seasonality.

    Trend is a constant for stationary levels and left out (or a drift term
    tried) after differencing — standard Box-Jenkins practice.
    """
    d0 = _determine_d(y, max_d)
    d_candidates = sorted({max(0, d0 - 1), d0, min(max_d, d0 + 1)})
    best: dict | None = None

    def consider(order, seasonal_order, trend):
        nonlocal best
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = SARIMAX(
                    y,
                    order=order,
                    seasonal_order=seasonal_order,
                    trend=trend,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                ).fit(disp=False, maxiter=250)
            score = res.aic if ic == "aic" else res.bic
            if best is None or score < best["ic"]:
                best = {
                    "ic": float(score),
                    "order": order,
                    "seasonal_order": seasonal_order,
                    "trend": trend,
                }
        except Exception:
            return

    for d in d_candidates:
        trends = ["c"] if d == 0 else ["n", "c"]
        for p in range(max_p + 1):
            for q in range(max_q + 1):
                for trend in trends:
                    consider((p, d, q), (0, 0, 0, 0), trend)

    if seasonal and best is not None:
        base = best["order"]
        for sd in (0, 1):
            consider(base, (1, sd, 1, period), best["trend"])

    return best or {
        "ic": np.nan,
        "order": (1, d0, 1),
        "seasonal_order": (0, 0, 0, 0),
        "trend": "c" if d0 == 0 else "n",
    }


# --------------------------------------------------------------------------- #
# Forecast orchestration
# --------------------------------------------------------------------------- #
@dataclass
class ForecastResult:
    series: pd.Series
    offset: str
    period: int
    model_name: str
    order: tuple
    seasonal_order: tuple
    ic: float
    aic: float
    bic: float
    horizon: int
    alpha: float
    fitted: pd.Series
    residuals: pd.Series
    forecast_index: pd.DatetimeIndex
    forecast_mean: np.ndarray
    forecast_lower: np.ndarray
    forecast_upper: np.ndarray
    metrics: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    cv_folds: pd.DataFrame = field(default_factory=pd.DataFrame)
    summary_text: str = ""


def build_forecaster(model_kind: str, order: dict, period: int) -> object:
    if model_kind == "ets":
        return ETSForecaster(seasonal_periods=period if order.get("seasonal") else None)
    if model_kind == "naive":
        return NaiveDrift()
    return ARIMAForecaster(
        order["order"],
        seasonal_order=order["seasonal_order"],
        trend=order["trend"],
    )


def _future_index(series: pd.Series, horizon: int, offset: str) -> pd.DatetimeIndex:
    return pd.date_range(series.index[-1], periods=horizon + 1, freq=offset)[1:]


def run_forecast(
    series: pd.Series,
    offset: str,
    period: int,
    model_kind: str = "arima",
    horizon: int = 12,
    alpha: float = 0.05,
    n_splits: int = 5,
    window: int | None = None,
    max_p: int = 2,
    max_q: int = 2,
    max_d: int = 2,
    seasonal: bool = False,
) -> ForecastResult:
    """Fit, cross-validate and forecast a series. Returns a ForecastResult."""
    if len(series) < MIN_POINTS:
        raise ValueError(f"series has {len(series)} points; need >= {MIN_POINTS}")

    # 1) Order selection (ARIMA) once on the full sample (disclosed); ETS/naive
    #    need none.
    order = {
        "order": (1, 1, 1),
        "seasonal_order": (0, 0, 0, 0),
        "trend": "n",
        "seasonal": seasonal,
    }
    if model_kind == "arima":
        order = select_arima_order(
            series,
            max_p=max_p,
            max_q=max_q,
            max_d=max_d,
            seasonal=seasonal,
            period=period,
        )
        order["seasonal"] = seasonal

    # 2) Walk-forward CV: re-fit parameters per fold, always out-of-sample.
    rows = []
    splits = walk_forward_splits(len(series), n_splits, horizon, window=window)
    for k, (ts, te, ss, se) in enumerate(splits):
        train = series.iloc[ts:te]
        test = series.iloc[ss:se]
        try:
            m = build_forecaster(model_kind, order, period).fit(train)
            pred = m.point_forecast(len(test))
        except Exception:
            pred = np.full(len(test), np.nan)
        for i in range(len(test)):
            rows.append(
                {
                    "fold": k + 1,
                    "date": test.index[i],
                    "actual": float(test.iloc[i]),
                    "predicted": float(pred[i]) if np.isfinite(pred[i]) else np.nan,
                }
            )
    cv = pd.DataFrame(rows)

    # 3) Final fit on the full sample.
    forecaster = build_forecaster(model_kind, order, period).fit(series)
    fitted = forecaster.fittedvalues.reindex(series.index)
    residuals = series - fitted

    fi = _future_index(series, horizon, offset)
    mean, lower, upper = forecaster.forecast_ci(horizon, alpha)

    metrics = forecast_metrics(cv["actual"].to_numpy(), cv["predicted"].to_numpy(), series, period)
    diagnostics = residual_diagnostics(series, residuals, forecaster.aic, forecaster.bic)

    return ForecastResult(
        series=series,
        offset=offset,
        period=period,
        model_name=forecaster.name,
        order=tuple(order["order"]),
        seasonal_order=tuple(order.get("seasonal_order", (0, 0, 0, 0))),
        ic=order.get("ic", np.nan),
        aic=forecaster.aic,
        bic=forecaster.bic,
        horizon=horizon,
        alpha=alpha,
        fitted=fitted,
        residuals=residuals,
        forecast_index=fi,
        forecast_mean=mean,
        forecast_lower=lower,
        forecast_upper=upper,
        metrics=metrics,
        diagnostics=diagnostics,
        cv_folds=cv,
        summary_text=forecaster.summary_text,
    )


# --------------------------------------------------------------------------- #
# Error metrics + diagnostics
# --------------------------------------------------------------------------- #
def _finite(a: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(a, dtype=float)
    p = np.asarray(p, dtype=float)
    mask = np.isfinite(a) & np.isfinite(p)
    return a[mask], p[mask]


def forecast_metrics(
    actual: np.ndarray, predicted: np.ndarray, train: pd.Series, period: int
) -> dict:
    a, p = _finite(actual, predicted)
    out = {"n_obs": int(len(a))}
    if len(a) < 2:
        return {**out, "rmse": np.nan, "mae": np.nan, "mape": np.nan,
                "smape": np.nan, "mase": np.nan, "r2": np.nan}

    err = p - a
    mse = float(np.mean(err ** 2))
    mae = float(np.mean(np.abs(err)))
    out["mse"] = mse
    out["rmse"] = float(np.sqrt(mse))
    out["mae"] = mae

    # MAPE with a guard against near-zero actuals.
    nz = np.abs(a) > 1e-8
    out["mape"] = float(100 * np.mean(np.abs(err[nz] / a[nz]))) if nz.any() else np.nan

    denom = np.abs(a) + np.abs(p)
    ok = denom > 1e-8
    out["smape"] = float(100 * np.mean(2 * np.abs(err[ok]) / denom[ok])) if ok.any() else np.nan

    # MASE: scaled by the in-sample (seasonal) naive error.
    s = max(1, period)
    naive_denom = float(np.mean(np.abs(train.to_numpy()[s:] - train.to_numpy()[:-s]))) if len(train) > s else float(np.mean(np.abs(np.diff(train.to_numpy()))))
    out["mase"] = float(mae / naive_denom) if naive_denom and naive_denom > 0 else np.nan

    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((a - np.mean(a)) ** 2))
    out["r2"] = float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan
    return out


def residual_diagnostics(
    series: pd.Series, residuals: pd.Series, aic: float, bic: float
) -> dict:
    resid = residuals.dropna()
    diag: dict = {"aic": aic, "bic": bic, "n": int(len(resid))}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            diag["adf_pvalue"] = float(adfuller(series, autolag="AIC")[1])
        except Exception:
            diag["adf_pvalue"] = np.nan
        try:
            diag["kpss_pvalue"] = float(kpss(series, regression="c", nlags="auto")[1])
        except Exception:
            diag["kpss_pvalue"] = np.nan

    if len(resid) > 2:
        lb_lag = min(10, max(1, len(resid) // 5))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                lb = acorr_ljungbox(resid, lags=[lb_lag], return_df=True)
            diag["ljung_box_pvalue"] = float(lb["lb_pvalue"].iloc[0])
        except Exception:
            diag["ljung_box_pvalue"] = np.nan
        try:
            diag["jarque_bera_pvalue"] = float(sps.jarque_bera(resid)[1])
        except Exception:
            diag["jarque_bera_pvalue"] = np.nan
        try:
            diag["durbin_watson"] = float(durbin_watson(resid))
        except Exception:
            diag["durbin_watson"] = np.nan
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                diag["arch_lm_pvalue"] = float(het_arch(resid)[1])
        except Exception:
            diag["arch_lm_pvalue"] = np.nan
        diag["resid_acf"] = list(np.asarray(acf(resid, nlags=min(20, len(resid) - 1), fft=True)))
        diag["resid_pacf"] = list(np.asarray(pacf(resid, nlags=min(20, len(resid) - 1))))
    else:
        diag.update(
            ljung_box_pvalue=np.nan, jarque_bera_pvalue=np.nan, durbin_watson=np.nan,
            arch_lm_pvalue=np.nan, resid_acf=[], resid_pacf=[],
        )
    return diag
