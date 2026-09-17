"""Liveability MVP model — self-contained for the dashboard image.

Mirrors `scripts/liveability_model.py`, which is the canonical version and loads
the same data from `dbt/seeds/country_profile_mvp.csv`. This module embeds the
curated 19-row profile so the dashboard container needs no extra volume mount
(build context is ./dashboard). Keep the two in sync when editing.

Design: docs/liveability-mvp.md, docs/liveability-simulation-layer.md.
"""
from __future__ import annotations

# --- curated country profile: source/licence per field in docs/data ---
COUNTRY_CSV = """\
country_iso3,country_name,latitude,longitude,currency,currency_eur_peg,wedge_mid,wedge_high,cap_tax,exit_tax_flag,exit_tax_threshold_eur,price_level,child_cost_pct,english_ok,quality_of_life,climate_risk,confidence,source_tax,source_price,verified_by
DEU,Germany,52.5235,13.4115,EUR,1.000,0.456,0.458,0.26375,1,500000,1.000,0.100,0,68,22,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent+human
CHE,Switzerland,46.948,7.44821,CHF,1.062,0.258,0.288,0.130,0,0,1.620,0.400,1,86,18,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent+human
AUT,Austria,48.2201,16.3798,EUR,1.000,0.470,0.480,0.275,0,0,1.030,0.120,1,74,22,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
NLD,Netherlands,52.3738,4.89095,EUR,1.000,0.420,0.495,0.360,0,0,1.150,0.240,1,75,24,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
BEL,Belgium,50.8371,4.36761,EUR,1.000,0.520,0.550,0.300,0,0,1.090,0.140,1,71,22,medium,estimate,WB PA.NUS.PPP/FCRF 2024,human
LUX,Luxembourg,49.61,6.1296,EUR,1.000,0.400,0.440,0.210,0,0,1.250,0.090,1,73,20,medium,estimate,WB PA.NUS.PPP/FCRF 2024,human
IRL,Ireland,53.3441,-6.26749,EUR,1.000,0.480,0.520,0.330,0,0,1.280,0.260,1,72,20,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
GBR,United Kingdom,51.5002,-0.126236,GBP,1.170,0.400,0.470,0.240,0,0,1.100,0.230,1,70,22,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
FRA,France,48.8566,2.35097,EUR,1.000,0.500,0.550,0.314,1,800000,1.050,0.140,0,72,24,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
SWE,Sweden,59.3327,18.0645,SEK,0.088,0.450,0.520,0.300,0,0,1.080,0.110,1,78,16,medium,estimate,WB PA.NUS.PPP/FCRF 2024,human
NOR,Norway,59.9138,10.7387,NOK,0.086,0.400,0.470,0.220,1,260000,1.320,0.150,1,82,16,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
DNK,Denmark,55.6763,12.5681,DKK,0.134,0.480,0.550,0.420,0,0,1.220,0.120,1,80,18,medium,estimate,WB PA.NUS.PPP/FCRF 2024,human
FIN,Finland,60.1608,24.9525,EUR,1.000,0.450,0.520,0.340,0,0,1.100,0.120,1,79,17,medium,estimate,WB PA.NUS.PPP/FCRF 2024,human
ISL,Iceland,64.1353,-21.8952,ISK,0.0067,0.380,0.440,0.220,0,0,1.500,0.120,1,76,19,low,estimate,WB PA.NUS.PPP/FCRF 2024,human
ITA,Italy,41.8955,12.4823,EUR,1.000,0.440,0.470,0.260,0,0,0.950,0.120,0,66,28,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
ESP,Spain,40.4167,-3.70327,EUR,1.000,0.390,0.470,0.210,0,0,0.850,0.110,0,69,30,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
PRT,Portugal,38.7072,-9.13552,EUR,1.000,0.420,0.480,0.280,0,0,0.780,0.100,0,67,28,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
CZE,Czechia,50.0878,14.4205,CZK,0.040,0.410,0.430,0.000,0,0,0.720,0.120,0,65,24,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent
POL,Poland,52.26,21.02,PLN,0.233,0.380,0.420,0.190,1,860000,0.620,0.120,0,62,26,high,tax-regime-matrix-2025-2026.md,WB PA.NUS.PPP/FCRF 2024,agent"""

"""Liveability MVP — lifecycle recommendation model.

Design: docs/liveability-mvp.md and docs/liveability-simulation-layer.md.

Deliberately a single file with no database dependency so it can be validated
against the worked example before any warehouse wiring.

Core idea: the decision is two-country (home vs alternative) and the headline
output is not a country but an *optimal switch year* — the point at which
compounding makes relocating worthwhile.

    net_income(c)  = gross * wage_index(c) * (1 - wedge(c))
    local_spend(c) = spend * price_level(c) + kids * child_cost_pct(c) * gross * price_level(c)
    save(c)        = net_income(c) - local_spend(c)
    W(T)           = W0 * prod(1+r) + sum save(c_t) * (1+r_c_t)^(T-t)

with the asset mix fixed and the after-tax real return derived from the
country's capital-tax rate and inflation — no country-specific return input.
"""
import csv
import io
from dataclasses import dataclass, field

# Fixed asset mix (70/30 default per the MVP spec) and nominal EUR returns.
MIX = {"equity": 0.70, "bond": 0.30}
NOMINAL = {"equity": 0.070, "bond": 0.025}
# Effective tax treatment of each sleeve, relative to the country's headline
# capital-income rate. Bonds are taxed at the headline rate; private equity
# gains are often exempt or deferred (CH, CZ, NZ), so a country-specific
# `equity_tax_mult` scales the headline rate for the equity sleeve.
EQUITY_TAX_MULT = {"CHE": 0.0, "CZE": 0.0, "POL": 0.5, "LUX": 0.5}


@dataclass
class Country:
    iso3: str
    name: str
    latitude: float
    longitude: float
    currency: str
    fx_to_eur: float
    wedge_mid: float
    wedge_high: float
    cap_tax: float
    exit_tax: bool
    exit_tax_threshold: float
    price_level: float
    child_cost_pct: float
    english_ok: bool
    quality_of_life: float
    climate_risk: float
    confidence: str

    @property
    def equity_tax(self) -> float:
        return self.cap_tax * EQUITY_TAX_MULT.get(self.iso3, 1.0)

    def after_tax_real_return(self, inflation: float) -> float:
        """Derived, not sourced: after-tax nominal return, deflated."""
        nom = sum(
            w * NOMINAL[a] * (1 - (self.equity_tax if a == "equity" else self.cap_tax))
            for a, w in MIX.items()
        )
        return (1 + nom) / (1 + inflation) - 1


@dataclass
class Profile:
    age: int = 35
    home: str = "DEU"
    gross_income: float = 120_000.0
    net_worth: float = 500_000.0
    annual_spend: float = 55_000.0
    capital_mobile: float = 1.0      # share of capital that can relocate
    children: int = 0
    horizon: int = 25
    needs_local_job: bool = True
    wage_index: dict[str, float] = field(default_factory=dict)
    inflation: dict[str, float] = field(default_factory=dict)
    # Only used when the capital is NOT mobile: the home country's rate applies.
    home_inflation: float = 0.021


def load_countries(csv_text: str = COUNTRY_CSV) -> dict[str, Country]:
    """Parse the curated country profile (embedded so the dashboard image is self-contained)."""
    out: dict[str, Country] = {}
    with io.StringIO(csv_text) as fh:
        for r in csv.DictReader(fh):
            out[r["country_iso3"]] = Country(
                iso3=r["country_iso3"],
                name=r["country_name"],
                latitude=float(r["latitude"]),
                longitude=float(r["longitude"]),
                currency=r["currency"],
                fx_to_eur=float(r["currency_eur_peg"]),
                wedge_mid=float(r["wedge_mid"]),
                wedge_high=float(r["wedge_high"]),
                cap_tax=float(r["cap_tax"]),
                exit_tax=r["exit_tax_flag"] == "1",
                exit_tax_threshold=float(r["exit_tax_threshold_eur"]),
                price_level=float(r["price_level"]),
                child_cost_pct=float(r["child_cost_pct"]),
                english_ok=r["english_ok"] == "1",
                quality_of_life=float(r["quality_of_life"]),
                climate_risk=float(r["climate_risk"]),
                confidence=r["confidence"],
            )
    return out


def effective_return(country: Country, p: Profile, home_country: Country | None = None) -> float:
    """Return on capital when resident in `country`.

    `capital_mobile` is a property of the CAPITAL, not of the destination. The
    immobile sleeve must keep earning at HOME tax rates and HOME inflation no
    matter where the person lives — otherwise relocating appears to lower the
    tax on money that never moved.
    """
    r_dest = country.after_tax_real_return(p.inflation.get(country.iso3, p.home_inflation))
    if p.capital_mobile >= 1.0 or home_country is None:
        return r_dest
    r_home = home_country.after_tax_real_return(p.home_inflation)
    if p.capital_mobile <= 0.0:
        return r_home
    return p.capital_mobile * r_dest + (1 - p.capital_mobile) * r_home


def terminal_wealth(
    country: Country,
    p: Profile,
    switch_year: int,
    home_country: Country | None = None,
) -> float:
    """Net worth at horizon if the move happens in `switch_year`.

    `switch_year=0` means move immediately. `switch_year=p.horizon` (or any value
    >= horizon) means never move — which is the correct way to compute the
    stay-home baseline.
    """
    home_country = home_country or country
    wage = p.wage_index.get(country.iso3, 1.0) if p.needs_local_job else 1.0
    wedge_here = country.wedge_mid if p.gross_income < 200_000 else country.wedge_high
    home_wedge = home_country.wedge_mid if p.gross_income < 200_000 else home_country.wedge_high

    net_here = p.gross_income * wage * (1 - wedge_here)
    net_home = p.gross_income * (1 - home_wedge)

    def annual_save(c: Country, net: float) -> float:
        # Child cost applies in WHICHEVER country you live in that year — it is
        # not a one-off relocation cost. child_cost_pct is already a LOCAL figure
        # (% of local gross), so it must NOT be scaled by price_level again.
        kids = p.children * c.child_cost_pct * p.gross_income
        return net - p.annual_spend * c.price_level - kids

    r_here = effective_return(country, p, home_country)
    r_home = effective_return(home_country, p, home_country)

    w = p.net_worth
    for t in range(p.horizon):
        if t < switch_year:
            w = (w + annual_save(home_country, net_home)) * (1 + r_home)
        else:
            w = (w + annual_save(country, net_here)) * (1 + r_here)
            if t == switch_year and country.exit_tax and w >= country.exit_tax_threshold:
                # One-off crystallisation friction on emigration.
                w -= 0.05 * w
    return w


# A move in the final years is not a real decision. Require this many years of
# destination residence for a schedule to count.
MIN_YEARS_AFTER_SWITCH = 3


def best_switch(country: Country, p: Profile, home: Country) -> tuple[int, float]:
    """Return (optimal switch year, terminal wealth) — the schedule.

    `switch_year == p.horizon` means never move, which is the correct default
    when relocating is not worth it.
    """
    last = max(0, p.horizon - MIN_YEARS_AFTER_SWITCH)
    best = max(
        ((s, terminal_wealth(country, p, s, home)) for s in range(last + 1)),
        key=lambda kv: kv[1],
    )
    if best[1] <= terminal_wealth(home, p, p.horizon, home):
        # Never beats staying: report "stay" rather than a late cosmetic move.
        return p.horizon, terminal_wealth(home, p, p.horizon, home)
    return best


def recommend(countries: dict[str, Country], p: Profile) -> list[dict]:
    """Rank alternatives by gain over staying home, plus the optimal schedule."""
    home = countries[p.home]
    # Baseline = never move. Using switch_year=0 would incorrectly apply the
    # HOME country's own row as if it were a destination.
    baseline = terminal_wealth(home, p, p.horizon, home)
    rows = []
    for iso, c in countries.items():
        if iso == p.home:
            continue
        s, w = best_switch(c, p, home)
        moving_wins = s < p.horizon
        rows.append(
            {
                "iso3": iso,
                "name": c.name,
                # Coordinates for the map. Only report a destination outcome when
                # moving there actually beats staying, otherwise every no-move row
                # would repeat the home baseline and look identical.
                "latitude": c.latitude,
                "longitude": c.longitude,
                "wealth": w if moving_wins else baseline,
                "gain": (w - baseline) if moving_wins else 0.0,
                "switch_year": s if moving_wins else p.horizon,
                "switch_age": (p.age + s) if moving_wins else None,
                "moving_wins": moving_wins,
                "confidence": c.confidence,
                "quality_of_life": c.quality_of_life,
                "price_level": c.price_level,
                "child_cost_pct": c.child_cost_pct,
                "wedge_mid": c.wedge_mid,
            }
        )
    rows.sort(key=lambda r: -r["gain"])
    return rows


def map_points(countries: dict[str, Country], p: Profile) -> dict:
    """Map payload for a filled country map (choropleth).

    Lives in the model module rather than the page so the map data path is
    covered by tests — a missing attribute here previously broke the page.

    Returns `z` (colour value per country), `customdata` (pre-formatted HTML
    tooltips) and `text` (short label), all aligned with `locations` (ISO3).
    """
    res = recommend(countries, p)
    home = countries[p.home]
    points = []
    for r in res:
        worth = r["gain"] > 0
        if worth:
            verdict = f"<b>Worth moving to</b><br>best age to move: {r['switch_age']}"
            gain_line = f"Gain vs staying put: <b>€{r['gain']:+,.0f}</b><br>"
            worth_line = f"Net worth at horizon: <b>€{r['wealth']:,.0f}</b><br>"
        else:
            verdict = "<b>Not worth moving to</b>"
            gain_line = "Gain vs staying put: <b>none</b><br>"
            worth_line = f"Your net worth if you stay: <b>€{r['wealth']:,.0f}</b><br>"
        tip = (
            f"<b>{r['name']}</b><br>"
            f"{'—' * 18}<br>"
            f"{worth_line}"
            f"{gain_line}"
            f"{verdict}<br>"
            f"{'—' * 18}<br>"
            f"Income tax + social: {r['wedge_mid'] * 100:.1f}%<br>"
            f"Cost of living: {r['price_level']:.2f}× home<br>"
            f"Cost of 1 child: {r['child_cost_pct'] * 100:.0f}% of salary<br>"
            f"Quality of life: {r['quality_of_life']:.0f}/100<br>"
            f"Data confidence: {r['confidence']}"
        )
        points.append({
            "iso3": r["iso3"],
            "name": r["name"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "gain": r["gain"],
            "worth": worth,
            "z": r["gain"] if worth else 0.0,
            "hover": tip,
        })
    # Short in-map annotation: the gain, so the map is readable without hovering.
    for q in points:
        q["text"] = f"{q['gain'] / 1000:,.0f}k" if q["worth"] else ""
    return {
        "points": points,
        "locations": [q["iso3"] for q in points],
        "z": [q["z"] for q in points],
        "customdata": [q["hover"] for q in points],
        "text": [q["text"] for q in points],
        "top_gain": max((q["gain"] for q in points), default=0.0) or 1.0,
        "home": {
            "name": home.name,
            "iso3": home.iso3,
            "latitude": home.latitude,
            "longitude": home.longitude,
        },
    }


def _defaults() -> tuple[dict[str, Country], Profile]:
    countries = load_countries()
    # wage_index = comparable gross salary vs Germany. First-pass proxy is the
    # GDP-per-capita-PPP ratio (World Bank, 2024). This is the model's weakest
    # input and the biggest lever — the UI must expose it as a user override.
    p = Profile(
        inflation={
            "CHE": 0.011, "DEU": 0.021, "AUT": 0.022, "CZE": 0.023, "POL": 0.032,
            "ESP": 0.025, "PRT": 0.023, "ITA": 0.020, "NLD": 0.023, "IRL": 0.021,
            "FRA": 0.019, "BEL": 0.023, "LUX": 0.021, "GBR": 0.026, "SWE": 0.019,
            "NOR": 0.017, "DNK": 0.019, "FIN": 0.018, "ISL": 0.026,
        },
        wage_index={
            "DEU": 1.00, "CHE": 1.50, "AUT": 1.02, "NLD": 1.10, "BEL": 1.04,
            "LUX": 1.60, "IRL": 1.50, "GBR": 0.95, "FRA": 0.95, "SWE": 1.05,
            "NOR": 1.60, "DNK": 1.15, "FIN": 0.98, "ISL": 1.15, "ITA": 0.85,
            "ESP": 0.75, "PRT": 0.62, "CZE": 0.62, "POL": 0.55,
        },
    )
    return countries, p


if __name__ == "__main__":
    countries, p = _defaults()
    home = countries[p.home]
    base = terminal_wealth(home, p, p.horizon, home)

    print(f"Home {home.name}: W({p.horizon}) = EUR {base:,.0f}")
    print(f"  after-tax real return {home.after_tax_real_return(p.inflation['DEU'])*100:.2f}%")
    print()
    print(f"{'country':<14}{'W25':>14}{'gain':>14}{'move age':>10}{'conf':>8}")
    for r in recommend(countries, p)[:8]:
        print(
            f"{r['name']:<14}{r['wealth']:>14,.0f}{r['gain']:>+14,.0f}"
            f"{r['switch_age']:>10}{r['confidence']:>8}"
        )

    print("\n--- VALIDATION (controlled: wage parity, isolates tax & price) ---")
    ch = countries["CHE"]
    for kids in (0, 1, 2):
        # wage_index=CHE 1.0 strips the wage differential so only tax/price act.
        pp = Profile(**{**p.__dict__, "children": kids, "wage_index": {"CHE": 1.0}})
        b = terminal_wealth(home, pp, pp.horizon, home)
        s, w = best_switch(ch, pp, home)
        print(
            f"  wage parity, children={kids}: CH gain = EUR {w - b:+,.0f}"
            f"  (switch age {pp.age + s})"
        )
    print("  expect: children=0 positive (~+0.2-0.4M), children>=1 NEGATIVE")
    print("  reference (worked example): +235k at 0 kids, negative at 1 kid")

    print("\n--- SCHEDULE: with the real wage differential ---")
    chg = countries["CHE"]
    for kids in (0, 1, 2):
        pp = Profile(**{**p.__dict__, "children": kids})
        b = terminal_wealth(home, pp, pp.horizon, home)
        s, w = best_switch(chg, pp, home)
        print(
            f"  CH wage 1.5x, children={kids}: gain EUR {w - b:+,.0f}"
            f"  -> {'MOVE at ' + str(pp.age + s) if w > b else 'STAY'}"
        )
