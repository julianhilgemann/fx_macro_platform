"""
Volatility → probability pipeline.

Point it at a DataFrame with columns [open, high, low, close] indexed by date.
Returns a distribution, not a direction.

    pip install arch statsmodels pandas numpy scipy
    # real data: pip install yfinance;  df = yf.download("CL=F", period="10y")

Commodity futures: use a back-adjusted continuous series, or drop roll dates.
The gap between contract months is not a return.
"""
from __future__ import annotations
import numpy as np, pandas as pd, warnings
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
from arch import arch_model

warnings.filterwarnings("ignore")
ANN = np.sqrt(252)


# ---------------------------------------------------------------- estimators
def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close).diff().dropna()


def rolling_vol(r: pd.Series, n: int = 20) -> pd.Series:
    """Zero-mean close-to-close. Over short windows the sample mean is noise."""
    return r.rolling(n).apply(lambda x: np.sqrt((x ** 2).mean()), raw=True) * ANN


def yang_zhang(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Overnight + Rogers-Satchell + open-to-close. Needs true OHLC bars."""
    o, h, l, c = (np.log(df[k]) for k in ("open", "high", "low", "close"))
    ro, oc = o - c.shift(1), c - o
    rs = (h - c) * (h - o) + (l - c) * (l - o)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    return np.sqrt(ro.rolling(n).var() + k * oc.rolling(n).var()
                   + (1 - k) * rs.rolling(n).mean()) * ANN


def ewma_vol(r: pd.Series, lam: float = 0.94) -> pd.Series:
    """RiskMetrics. Exponential weights beat equal-weighted windows for σ_today."""
    v = np.empty(len(r)); v[0] = r.var()
    x = r.values
    for i in range(1, len(r)):
        v[i] = lam * v[i - 1] + (1 - lam) * x[i - 1] ** 2
    return pd.Series(np.sqrt(v * 252), index=r.index)


# ---------------------------------------------------------------- diagnostics
def diagnose(r: pd.Series) -> dict:
    return {
        "n": len(r),
        "excess_kurtosis": float(stats.kurtosis(r)),
        "skew": float(stats.skew(r)),
        "ljungbox_r_p": float(acorr_ljungbox(r, lags=[20], return_df=True)["lb_pvalue"].iloc[0]),
        "ljungbox_r2_p": float(acorr_ljungbox(r ** 2, lags=[20], return_df=True)["lb_pvalue"].iloc[0]),
        "arch_lm_p": float(het_arch(r, nlags=10)[1]),
        "vol_rel_se_20d": float(1 / np.sqrt(2 * 20)),
    }


def select_model(r: pd.Series):
    """Escalate specification; BIC decides. Returns (name, fitted result, table)."""
    r100 = r * 100
    specs = {"GARCH-normal": dict(p=1, o=0, q=1, dist="normal"),
             "GARCH-t":      dict(p=1, o=0, q=1, dist="t"),
             "GJR-t":        dict(p=1, o=1, q=1, dist="t"),
             "GJR-skewt":    dict(p=1, o=1, q=1, dist="skewt")}
    fits, tbl = {}, {}
    for name, kw in specs.items():
        res = arch_model(r100, mean="Constant", vol="GARCH", **kw).fit(disp="off")
        fits[name], tbl[name] = res, {"loglik": res.loglikelihood, "bic": res.bic}
    best = min(tbl, key=lambda k: tbl[k]["bic"])
    return best, fits[best], tbl


def structure(res) -> dict:
    """Long-run level and half-life. Both are weakly identified - treat as
    order-of-magnitude, since they divide by (1 - persistence)."""
    p = res.params
    a = p.get("alpha[1]", 0.0); g = p.get("gamma[1]", 0.0); b = p.get("beta[1]", 0.0)
    persist = a + g / 2 + b
    h_inf = (p["omega"] / (1 - persist)) / 1e4
    return {"alpha": float(a), "gamma": float(g), "beta": float(b),
            "nu": float(p.get("nu", np.nan)),
            "persistence": float(persist),
            "sigma_inf_ann": float(np.sqrt(h_inf * 252)),
            "half_life_days": float(np.log(0.5) / np.log(persist)),
            "sigma_today_ann": float(res.conditional_volatility.iloc[-1] / 100 * ANN)}


# ---------------------------------------------------------------- forecasting
def horizon_sigma(res, H: int) -> dict:
    """Aggregate the mean-reverting variance path. Naive sqrt(T) overstates
    after a spike and understates in a calm regime."""
    var_path = res.forecast(horizon=H, reindex=False).variance.values[-1] / 1e4
    sig_now = res.conditional_volatility.iloc[-1] / 100
    return {"sigma_H": float(np.sqrt(var_path.sum())),
            "sigma_H_naive": float(sig_now * np.sqrt(H)),
            "term_structure_ann": (np.sqrt(var_path * 252)).tolist()}


def add_events(sigma_H: float, n_events: int, typical_abs_move: float) -> float:
    """GARCH cannot see the calendar. sigma_event from E|x| = sigma*sqrt(2/pi)."""
    return float(np.sqrt(sigma_H ** 2 + n_events * (typical_abs_move * np.sqrt(np.pi / 2)) ** 2))


def distribution(res, S0: float, H: int, nsim: int = 50_000) -> dict:
    """The only step that answers path-dependent questions."""
    paths = res.forecast(horizon=H, method="simulation", simulations=nsim,
                         reindex=False).simulations.values[-1] / 100
    px = S0 * np.exp(np.cumsum(paths, axis=1))
    term = px[:, -1]
    return {
        "quantiles": {q: float(np.percentile(term, q)) for q in (1, 5, 25, 50, 75, 95, 99)},
        "P_up_10": float((term > S0 * 1.10).mean()),
        "P_down_10": float((term < S0 * 0.90).mean()),
        "P_touch_down_15": float((px.min(axis=1) < S0 * 0.85).mean()),
        "P_touch_up_15": float((px.max(axis=1) > S0 * 1.15).mean()),
        "E_abs_move": float(np.abs(term / S0 - 1).mean()),
        "terminal": term,
    }


# ---------------------------------------------------------------- validation
def backtest(df: pd.DataFrame, H: int = 5, start: int = 750, win: int = 1000,
             nsim: int = 10_000) -> pd.DataFrame:
    """Disjoint windows only (step == H), otherwise the breach tests are invalid.
    At H=20, ten years gives <100 windows - not enough to reject a bad model."""
    r100 = log_returns(df.close) * 100
    px, rows = df.close, []
    for t0 in range(start, len(r100) - H, H):
        hist = r100.iloc[max(0, t0 - win):t0]
        real = np.log(px.iloc[t0 + H] / px.iloc[t0])
        res = arch_model(hist, mean="Constant", vol="GARCH",
                         p=1, o=1, q=1, dist="t").fit(disp="off")
        sg = np.sqrt(res.forecast(horizon=H, reindex=False).variance.values[-1].sum() / 1e4)
        term = res.forecast(horizon=H, method="simulation", simulations=nsim,
                            reindex=False).simulations.values[-1].sum(axis=1) / 100
        lo, hi = np.percentile(term, [5, 95])
        rows.append({"t0": t0, "real": real,
                     "pit": float((term < real).mean()),
                     "breach90_sim": int(real < lo or real > hi),
                     "breach90_norm": int(abs(real) > 1.645 * sg)})
    return pd.DataFrame(rows)


def kupiec(breaches: int, n: int, p: float = 0.10) -> float:
    """Unconditional coverage: is the breach RATE right?"""
    if breaches in (0, n): return float("nan")
    ph = breaches / n
    ll = -2 * ((n - breaches) * np.log(1 - p) + breaches * np.log(p)
               - (n - breaches) * np.log(1 - ph) - breaches * np.log(ph))
    return float(1 - stats.chi2.cdf(ll, 1))


def christoffersen(b: np.ndarray) -> float:
    """Independence: do breaches CLUSTER? Clustering means the model is too slow."""
    b = np.asarray(b); n = {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}
    for i in range(1, len(b)): n[(b[i - 1], b[i])] += 1
    n00, n01, n10, n11 = n[(0, 0)], n[(0, 1)], n[(1, 0)], n[(1, 1)]
    if n01 + n11 == 0 or n00 + n01 == 0 or n10 + n11 == 0: return float("nan")
    p01, p11 = n01 / (n00 + n01), n11 / (n10 + n11)
    p = (n01 + n11) / len(b[1:])
    lg = lambda c, q: c * np.log(q) if c and 0 < q < 1 else 0.0
    l1 = lg(n00, 1 - p01) + lg(n01, p01) + lg(n10, 1 - p11) + lg(n11, p11)
    l0 = lg(n00 + n10, 1 - p) + lg(n01 + n11, p)
    return float(1 - stats.chi2.cdf(-2 * (l0 - l1), 1))


# ---------------------------------------------------------------- entry point
def report(df: pd.DataFrame, H: int = 60, run_backtest: bool = True) -> dict:
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
    r = log_returns(df.close)
    S0 = float(df.close.iloc[-1])

    diag = diagnose(r)
    name, res, tbl = select_model(r)
    st = structure(res)
    hz = horizon_sigma(res, H)
    dist = distribution(res, S0, H)

    zres = (res.resid / res.conditional_volatility).dropna()
    resid_ok = {"excess_kurtosis": float(stats.kurtosis(zres)),
                "arch_lm_p": float(het_arch(zres, nlags=10)[1])}

    yrs = len(r) / 252
    drift = {"mu_hat": float(r.mean() * 252),
             "se": float(r.std() * ANN / np.sqrt(yrs)),
             "contribution_over_H": float(r.mean() * H),
             "sigma_over_H": hz["sigma_H"]}

    print(f"n={diag['n']}  S0={S0:.2f}  excess kurtosis={diag['excess_kurtosis']:.1f}  "
          f"ARCH-LM p={diag['arch_lm_p']:.1e}")
    print(f"model={name}  persistence={st['persistence']:.4f}  "
          f"sigma_today={st['sigma_today_ann']:.1%}  sigma_inf={st['sigma_inf_ann']:.1%}  "
          f"half-life={st['half_life_days']:.0f}d")
    print(f"H={H}d  sigma={hz['sigma_H']:.2%}  (naive sqrt-T would say {hz['sigma_H_naive']:.2%})")
    print(f"90% interval [{dist['quantiles'][5]:.2f}, {dist['quantiles'][95]:.2f}]  "
          f"P(+10%)={dist['P_up_10']:.1%}  P(touch -15%)={dist['P_touch_down_15']:.1%}")
    print(f"drift {drift['mu_hat']:.1%} +/- {1.96*drift['se']:.1%} p.a. -> contributes "
          f"{drift['contribution_over_H']:.2%} vs sigma {hz['sigma_H']:.2%}")
    print(f"residual check: excess kurtosis {resid_ok['excess_kurtosis']:.1f}, "
          f"ARCH-LM p={resid_ok['arch_lm_p']:.2f} (want > 0.05)")

    out = {"diagnostics": diag, "model": name, "bic_table": tbl, "structure": st,
           "horizon": hz, "distribution": {k: v for k, v in dist.items() if k != "terminal"},
           "drift": drift, "residuals": resid_ok}

    if run_backtest:
        bt = backtest(df, H=5)
        for col in ("breach90_sim", "breach90_norm"):
            x, n = int(bt[col].sum()), len(bt)
            out.setdefault("backtest", {})[col] = {
                "coverage": 1 - x / n, "n_windows": n,
                "kupiec_p": kupiec(x, n), "independence_p": christoffersen(bt[col].values)}
            print(f"backtest {col}: coverage {1-x/n:.1%} over {n} disjoint 5d windows, "
                  f"Kupiec p={kupiec(x,n):.3f}, independence p={christoffersen(bt[col].values):.3f}")
    return out


if __name__ == "__main__":
    # replace with real data, e.g.
    #   import yfinance as yf
    #   df = yf.download("CL=F", period="10y", auto_adjust=False)
    #   df.columns = [c.lower() for c in df.columns.get_level_values(0)]
    df = pd.read_csv("series.csv", index_col=0, parse_dates=True)
    report(df, H=60)
