# Where Should I Live? — A Parsimonious, Personalised Country Scoring Model

**Status:** design proposal (v0.1)
**Scope:** how to score countries on macro, demographic and climate fundamentals, personalise that score to an individual, and turn it into an actionable relocation recommendation — using free data only.
**Consumer:** this platform (ingest → dbt → marts → API → dashboard). See [§11 Integration](#11-how-this-drops-into-this-platform).

---

## 1. The core design decision

Every published liveability index (EIU, Mercer, Monocle, Numbeo's Quality of Life) makes the same structural mistake for your use case: **it computes one ranking for an average person.** That is why they are simultaneously useful and useless. "Vienna is the most liveable city in the world" is a statement about a statistical artefact, not about you.

There are three defensible ways to fix that:

| Approach | Idea | Verdict |
|---|---|---|
| **A. Weighted-sum index** | Country scores × user weights | Interpretable, but hides the actual decision — wealth compounding is exponential, wellbeing is not, and a linear index cannot tell you *when* a trade-off pays off |
| **B. Lifecycle simulation** | Simulate the rest of your life in each country under uncertainty; rank by distributional outcomes | Correct, honest about uncertainty, and the only approach that captures "move there at 35, leave at 55" |
| **C. Regret / robust choice** | Rank by worst-case loss across scenarios, not by mean | The right frame when policy risk is the dominant uncertainty |

**Proposal: B as the engine, A as the presentation, C as the tie-breaker.** Concretely:

> A **two-stage funnel**. Stage 1 is a coarse, transparent, free-data gate that eliminates countries you legally, financially or personally cannot or should not choose (15–25 countries down to 8–12). Stage 2 is a Monte Carlo lifecycle simulation over those survivors, emitting a **Pareto frontier of (wealth, quality-adjusted life-years)** rather than a single league table. A weighted-sum score in [0, 100] is then fitted to the frontier for display, calibrated so that one point of score means the same thing on both axes.

The reason to insist on Stage 2: your example question — *"higher earning potential, fewer taxes than Germany, good social system, asset maximisation, great nature, good connectivity, climate dynamics"* — has **no scalar answer**. Some of those objectives are in direct tension (low tax ⇒ thin social system; great nature ⇒ weaker labour market; low tax + great nature + great connectivity ⇒ that country exists and is Switzerland or New Zealand, not Dubai). A single number would bury exactly the trade-off you are asking about. A frontier displays it.

### 1.1 The pivotal modelling insight

**Two different effects compete, they scale with different things, and which one wins is decided by the user's *wealth*, not their income.** Decomposing the Germany→Switzerland case (spec §3 has the numbers) at wage parity:

| Effect | Mechanism | Scales with | Worth over 25 yrs |
|---|---|---|---|
| **Labour-income wedge** | 45.6% vs 25.8% → ~€24k/yr more net income | **income** (linear) | **+€764k** |
| **Cost-of-living penalty** | κ ≈ 1.62× on €55k of spending | **spending** (linear) | **−€1,095k** |
| **Capital-income drag** | 26.375% vs 0% CGT → +2.2pp real return | **net worth** (multiplicative) | **+€687k** |

Net at €500k of capital: **+€235k**. The same decomposition across wealth levels:

| Starting net worth | Wedge term | Capital term | Net |
|---|---|---|---|
| €200,000 | −331k | +347k | **−105k** (stay in DE) |
| €500,000 | −331k | +687k | **+235k** (move) |
| €1,000,000 | −331k | +1,253k | +801k |
| €5,000,000 | −331k | +5,785k | **+5,333k** |

**The recommendation flips on net worth, holding everything else constant.** The wedge and price terms are both *linear* — they move a fixed annual cash flow — while the capital-tax drag is a *multiplicative* force on a growing stock. Below roughly **€300k of invested capital, the price penalty wins and the user should stay in Germany on pure wealth grounds**; above it, the compounding gap takes over.

This is the structurally important point, and it has three consequences:

1. **A single ranking cannot be correct for two users with the same income but different net worth.** Every published index ranks countries, implicitly, for one point in this space.
2. **The model's job is to find the crossover**, not the winner. The crossover is a number the user can act on ("accumulate to €X, then move").
3. **`income_geography` and the relative wage ratio are first-class inputs.** The wedge term is what finances the price penalty, so if the user can earn a Swiss salary while living somewhere cheaper — or command a wage ratio above 1.2 — the whole trade changes. Same person, same country, opposite recommendation.

Two further structural facts fall out:

- **Your residence choice matters more than where your capital sits, but only through the labour wedge.** A German resident with €500k pays 26.375% on capital income *because they are resident in Germany*, not because the money is there — so the first-order questions are (a) do I stay tax-resident, (b) what is the source-country treatment of the assets (US situs withholding, ETF domicile, Irish UCITS vs US-domiciled), and only then (c) which residence regime.
- **The exit tax is a planning variable, not a sunk cost.** Germany's §19(3) InvStG (JStG 2024, effective 1 Jan 2025) reaches private ETF holdings — but only above **€500k of acquisition cost in a single fund**, and it falls away retroactively under §6(3) AStG if the mover returns within 7 years. A €500k portfolio faces **€77,700 or €0** purely on how many positions it is split across. See §4.4.

The model must therefore carry **capital location, income geography, net worth and exit-tax position as separate dimensions**. This is the single most common error in expat decision-making and it is fully modelable from free data.

---

## 2. What is being modelled: two non-fungible capitals

Model the user as holding two stocks that cannot be converted into each other:

- **Financial capital** — fungible, compounds, and is the only thing that can be maximised. Accumulates in € (or a chosen numéraire).
- **Relational / locational capital** — non-fungible, depreciates on relocation, and is worth real money but is not saleable. Language, professional network, credential recognition, proximity to family, cultural fluency, health.

Every relocation trades some of the second for some of the first. A model that only sees money will always recommend Dubai; a model that only sees wellbeing will always recommend the place you already live. The whole point is to price the conversion rate **for you**.

---

## 3. The country universe — parsimonious by construction

Do not attempt 200 countries. Attempt **45**, in two tiers plus a watchlist. This covers ~90% of global GDP, ~70% of world population, and essentially all plausible destinations for someone with a German/EU passport and a professional income.

| Tier | n | Coverage requirement | Purpose |
|---|---|---|---|
| **T1 — Deep** | 23 | All ~60 fields, sub-national climate/nature where available | Full simulation, ranked output |
| **T2 — Light** | 23 | The 8-field strip only | Long-shot flags, "did you consider…", escape hatches |
| **Watch** | 10 | Ingest only, not scored | Future candidates, regime-change monitoring (e.g. a country that just passed an attractive regime) |

**T1 (23):** CH, NO, SE, DK, FI, NL, IE, AT, DE, CZ, EE, PL, PT, ES, IT, GR, CY, MT, AE, SG, NZ, GB
**T2 (22):** AU, CA, US, JP, KR, IS, BE, FR, LU, SI, SK, HU, RO, HR, BG, LT, LV, CL, UY, PA, CR, IL
**Watch (10):** GE, RS, AL, ME, TR, TH, VN, ID, MX, ZA

*Poland was promoted from T2 on **verified** grounds only: a **personal exit tax in force** (art. 30da PIT, PLN 4m, 19%), EU freedom of movement removing the visa gate entirely, and a deep labour market with strong connectivity. **⚠ A reported Polish lump-sum new-resident regime (PLN 200,000/yr on foreign income for up to 10 years) is an UNRESOLVED CONFLICT** — two research streams read the same sources and reached opposite conclusions. It is flagged as a live gap in the research matrix and **must not be relied on until checked against the statute.** If it holds, Poland rises materially; if not, it is still a T1 candidate on the other grounds.*

**Generalise that lesson: never promote a country on an unverified regime.** Regime facts are exactly the ones that (a) carry the largest effect on the answer and (b) are most often reported wrongly. Gate every promotion on a primary source, and let the flagged cell sit in the table as a gap rather than resolve it by preference.

Key design rule: **T1 should be defensible as a set.** If a country is in T1, a reasonable person should be able to argue it belongs in a top-10 for at least one archetype. That keeps the ranking honest.

**And treat language as continuous, not binary.** The `no_language_barrier` constraint eliminates on *social* integration, but professional life in Warsaw, Prague, Tallinn, Amsterdam and the Nordic capitals is substantially English-language. A binary flag wrongly deletes half of T1. Model it as the two-part friction term in §6.3 — a **professional** penalty (often near zero) and a **social** penalty (large) — because many people will trade the second for the first, and a model that cannot express that will give bad advice.

---

## 4. The parsimonious data strip

The minimal viable model is **10 raw fields per country-year**. Everything else is derived. Ten fields is small enough to hand-curate for 45 countries in a weekend, and large enough that the answer is not embarrassing.

### 4.1 Tier 0 — the 10-field minimum

| # | Field | Source (free) | Access |
|---|---|---|---|
| 1 | `gdp_pc_ppp` | World Bank WDI `NY.GDP.PCAP.PP.CD` | REST API, no key |
| 2 | `ppp_conv_factor` (private consumption) | World Bank WDI `PA.NUS.PRVT.PP` | REST API |
| 3 | `gross_cap_income_return` (equity + bond blend) | Damodaran / JST long-run data | CSV |
| 4 | `cap_income_tax_effective` | OECD Tax Database + national law | Hand-curated, annual |
| 5 | `gov_debt_gdp` | IMF WEO / WB `GC.DOD.TOTL.GD.ZS` | API |
| 6 | `old_age_dependency_2050` | UN WPP 2024 | Bulk CSV / API |
| 7 | `median_age` | UN WPP 2024 | Bulk CSV / API |
| 8 | `climate_risk_score` | ND-GAIN Country Index | Bulk CSV |
| 9 | `nature_score` | Protected Planet + Hansen tree cover + WHO air quality | Composite |
| 10 | `median_fixed_down_mbps` | Ookla Open Data (AWS S3) | S3, free, CC BY-NC |

That is genuinely global, genuinely free, and already differentiates countries correctly. The 10-field model will get the *ranking* broadly right and the *magnitudes* wrong. That is an acceptable v1.

### 4.2 Tier 1 — the standard strip (~26 fields)

Adds the fields that carry real explanatory weight:

**Macro & fiscal**
- `real_10y_yield` = nominal 10Y − breakeven inflation (both free: BIS / national debt agencies)
- `sovereign_spread` — as a free proxy for credit risk where ratings are paywalled
- `fx_vol_5y` — realised vol of local currency vs EUR/USD (free from your own FX data; **this platform already has the infrastructure**)
- `inflation_vol_10y`
- `terms_of_trade_trend` (UNCTAD / WB)

**Tax & regime** (the highest-value hand-curated block)
- `cap_gains_rate`, `dividend_rate`, `wealth_tax_rate`, `inherit_tax_rate`
- `remittance_or_territorial` (0/1) and `years_until_worldwide_taxation`
- `exit_tax_exposure` (0/1 + threshold) — critical for a German starting point
- `migrant_regime_present`, `migrant_regime_headline_rate`, `migrant_regime_years`
- `capital_controls_index` (Chinn-Ito)

**Demography & social**
- `net_migration_rate`, `fertility_rate`, `pop_growth_2050`
- `healthy_life_expectancy` (WHO HALE)
- `pension_replacement_rate` and `pension_system_sustainability` (OECD Pensions at a Glance + EC Ageing Report)
- `health_spend_pc_ppp`, `out_of_pocket_share`
- `gini`, `social_transfer_share_gdp`

**Climate & nature**
- `heat_days_above_35c_proj_2050` (WB CCKP)
- `water_stress_baseline_2030` (WRI Aqueduct 4.0)
- `crop_yield_change_2050`
- `coastal_flood_exposure_pop`
- `pm25_ugm3` (WHO / OpenAQ)
- `protected_area_pct`, `forest_cover_pct`, `bii` (biodiversity intactness)
- `renewable_share` (Ember API)

**Infrastructure**
- `median_mobile_down_mbps`, `pct_pop_5g`
- `electricity_reliability` (WB `IC.ELC.OUTG.ZS` or SAIDI)
- `english_proficiency_index` (EF EPI — free to read, verify redistribution terms)
- `visa_free_count` (Henley / Passport Index — free tier)

### 4.3 Where free data genuinely runs out

Be explicit about this, because it shapes the whole design:

| Want | Reality | Free workaround |
|---|---|---|
| **Tax & residency regimes** | No free machine-readable global source exists. OECD covers rates, not regimes; the actual qualifying tests, floors, durations and deferral mechanics live in national law. | **Hand-curate it, version it, source it.** This is the one block where a human must do the work. See [`../research/tax-regime-matrix-2025-2026.md`](../research/tax-regime-matrix-2025-2026.md) for a 21-jurisdiction worked example with inline primary sources, effective dates and an explicit confidence section. It is the highest-value table in the project and it cannot be scraped. |
| Cost of living (Numbeo) | Free tier is browse-only; API is paid and the licence restricts redistribution | **Solved for free: divide World Bank `PA.NUS.PPP` by `PA.NUS.FCRF`** to get a clean **CC BY 4.0 price-level index** with real country coverage. This is the free Numbeo substitute and it needs no curation. Add national rent indices only for the top candidates. ⚠ Prefer `PA.NUS.PPP` over `PA.NUS.PPPC.RF`, which is **404/invalid** and a very common copy-paste error. |
| **Childcare cost** — the MVP's swing factor | No free machine-readable global source | **OECD Family Database** (net childcare costs, CC BY 4.0) + national fee schedules, both public. This is the highest-value synthesis in the product and it is buildable. |
| Long-run real returns *by country* (UBS GIRY) | **Confirmed genuinely unfree** — the full book is UBS-IB-client-login only, no retail price, and the underlying Dimson-Marsh-Staunton database is not sold standalone | **Jordà-Schularick-Taylor R6** (18 countries, 1870–2020, equities/bonds/bills/**housing**) — but **CC BY-NC-SA, research only**. For a commercial product substitute Damodaran + Ken French + Maddison. ⚠ Damodaran has **no international annual-returns file** (the `histgr*` files are *growth*, not returns); use `ctryprem.xlsx` for equity risk premia. ⚠ JST column traps: no `rgdppc` (use `rgdpmad`), no `mortg` (use `tmort`). |
| Sovereign ratings (S&P/Moody's/Fitch) | **A genuine dead end.** Trading Economics guest API returns **410 "guest account has been discontinued"**; no agency publishes usable RSS; **FRED carries no EMBI/EM sovereign spread series at all** | Build a **market-implied proxy**: long-term yield (`IRLTLT01{ISO3}M156N`, no API key via `fredgraph.csv`, back to 1953) spread over US, plus World Bank CPIA `IQ.CPA.DEBT.XQ`, external debt `DT.DOD.DECT.CD` and reserves cover `FI.RES.TOTL.CD`. Arguably better than a letter rating anyway. |
| Liveability rankings (EIU, Mercer) | Paywalled; Mercer forbids public comparison | Don't use them. Build the index and *validate* against them where a free summary number exists. Not being allowed to copy them is a feature. |
| Sub-national climate/nature detail | Country averages hide everything that matters | Aqueduct does sub-national; store a **p10/p50/p90 across regions** instead of a country mean. ⚠ **World Bank CCKP is unusable from a script** — the entire `worldbank.org` host returns 403 `cf-mitigated: challenge` and a browser UA does not help. **Substitute `open-meteo`** (keyless, CC BY 4.0, archive + CMIP6 projections + air quality, verified working). |

The sub-national point is not a nicety. "Spain" is not a climate exposure; "Andalusia vs Galicia" is. Carrying a three-point distribution per country costs 2 extra fields and removes the single largest source of error in the whole model.

### 4.6 Sourcing reality check — what the verified inventory changed

A 193-URL sourcing pass (329 endpoints HTTP-probed; see [`sourcing/free_macro_data_inventory.md`](sourcing/free_macro_data_inventory.md)) reordered my build plan. The five findings that matter most:

1. **A silent-failure bug in a source I would have used.** The **UNESCO UIS API ignores the `indicators=` parameter** — three different indicator codes including a deliberately bogus one return the *byte-identical* 4.2 MB payload at HTTP 200. A pipeline would ingest the wrong series and never error. **Treat UIS as untrusted; use World Bank/UN WPP instead.** The general lesson: assert on payload content, not status codes.
2. **Rate limiting is an architectural constraint, not an afterthought.** IMF DataMapper 403s on bursts of ~6–10 calls then recovers after 20–60 s; **OECD returns 429 on *every* request in a burst** and has changed its `format` parameter (`jsondata` now 406s — use `csvfile`). Budget a token bucket with per-source backoff from day one, or the first full refresh will fail halfway and leave partial data.
3. **Three host migrations are live and breaking working code right now**: FAOSTAT's `fenixservices` API is dead (521) → `faostatservices.fao.org`; Copernicus CDS `/api/v2` retired → `/api`; WDPA's CloudFront pattern dead → a publicly-listable S3 bucket.
4. **Licence blockers must be warehouse metadata, not README prose.** **Ookla (CC BY-NC-SA), WHO GHO (NC-SA), JST R6 (NC-SA), Protected Planet (NC), IHME (NC), GPI (NC), Numbeo (no redistribution).** If this becomes a commercial product, four of them are load-bearing for the MVP as originally specified. Tag every row and let `dim_country_indicator` expose it.
5. **`fredgraph.csv` needs no API key** — `https://fred.stlouisfed.org/graph/fredgraph.csv?id=IRLTLT01DEM156N` — and quietly re-hosts OECD/BIS/World Bank international series. This is the cheapest route to long-run yields and removes a key-management task entirely.

### 4.4 The one field that pays for the whole project

If you build nothing else from Tier 1, build `exit_tax_exposure` properly — as a **rule, not a rate**. Germany's §19(3) InvStG (introduced by the JStG 2024, effective 1 Jan 2025) extended exit taxation to privately held **investment fund units, explicitly including ETFs**, on emigration. It applies to anyone unlimited-taxable in Germany for ≥7 of the last 12 years, deems a disposal at market value, taxes gains at 26.375% and **disallows losses**, but only in "weighty cases": **≥1% of a fund's units, or ≥€500,000 of acquisition cost in a single fund**.

For a €500,000 portfolio that threshold is worth **€77,700 of tax** — and it drops to **€0** by splitting across two funds. It grows with the portfolio (≈15.5% of starting wealth over a 25-year horizon), it can be paid in 7 interest-free instalments (§6(4) AStG, worth ≈€11,100 NPV), and it **falls away retroactively** if the mover returns to Germany within 7 years (extendable to 12) under §6(3) AStG.

Two modelling consequences, both non-obvious:

- **Binary threshold, not a rate.** The function is discontinuous in the individual's *position size per fund*, which is a decision variable under their control. A linear tax rate would get this wrong by construction.
- **Contingent, not sunk.** Because of the Rückkehrregelung, the exit tax is a liability that extinguishes with probability $P(\text{return})$ — a random variable the Monte Carlo can price and a spreadsheet cannot. This alone justifies the §7 simulation over any static index.

Same discipline applies to the destination side: Portugal IFICI, Greece's €100k flat tax (Art. 5A), Cyprus non-dom, the UK FIG regime and Italy's art. 24-bis flat tax are all **named regimes with a qualifying test, a duration and a minimum tax floor.** They must be modelled as switches with a `regime_closes` hazard rate, never as headline rates. Two rules that the research pass made non-negotiable:

- **The regime applies to foreign-source income only.** Greece's €100k flat tax and 5% dividend rate do nothing for a salary earned *in* Greece, which is taxed under the normal scale on top. This makes `income_geography` in §6.1 the highest-leverage field in the whole user profile — same person, same country, opposite recommendation.
- **Store regimes with effective dates, not as per-country columns.** See §4.5.

### 4.5 Tax regimes are a time series, not a cross-section

The sourced matrix in [`../research/tax-regime-matrix-2025-2026.md`](../research/tax-regime-matrix-2025-2026.md) turned up **ten material changes across ten jurisdictions in a 21-month window** (Italy €200k→€300k; Australia's CGT discount repealed from Jul 2027; Cyprus non-dom extension made paid; Netherlands 30%→27% and Box 3 reform stalled; Estonia's 24% rise scrapped; Czechia's CZK 40m test abolished; Canada's inclusion-rate hike cancelled; Switzerland's federal inheritance tax rejected but *Eigenmietwert* abolished; Germany's EU/EEA deferral abolished then partially restored, with ECJ C-430/25 pending; Spain referred to the CJEU) — **including three outright reversals.**

That is a churn rate of roughly one change per jurisdiction per year. Consequences:

1. **`fct_tax_regime` must be effective-dated** — `(iso3, regime_id, valid_from, valid_to, source_url, confidence)`. A country column refreshed annually will be silently wrong for months at a time, and the backtest in §9.3 will leak future information.
2. **`regime_closes` is calibratable, not a guess.** Estimate the hazard from the observed churn rather than picking 5%. The observed rate implies a materially higher hazard than the 5–7% I originally proposed.
3. **Confidence is a first-class attribute.** The research pass distinguishes primary-source-verified figures from absence-of-evidence findings (several "no exit tax" conclusions are negative findings, not positively cited provisions). A model that treats both as equal will be confidently wrong.
4. **Change detection should be an asset.** A Dagster asset that diffs the current regime table against the last snapshot and raises an Elementary alert on any change is cheap and is the single highest-value data-quality control in this project — because a regime change silently invalidates every recommendation built on it.

**The empirical case, from this project's own research pass:** the sourced matrix corrected **fifteen of my original premises**, including five wrong statutory citations (Netherlands art. 7.5 vs art. 4.16(1)(h); Australia's TAP at s 855-45 vs s 855-15; Japan's tourist departure levy mistaken for the gains exit tax; Norway's *Elopak* case miscited as an exit-tax ruling; Ireland's s.579A, which is a *trust attribution* rule, not emigration). Three of those errors were the kind that produce a *confident, specific, wrong* recommendation — "Japan is raising its exit tax" being the clearest. **An unsourced regime table is worse than no table, because it launders uncertainty into authority.** Budget for the curation accordingly: this block is a maintained human artefact with a review cadence, not a scrape.

**And the deepest lesson — whole codes get replaced.** **Italy repealed the entire TUIR (DPR 917/1986) by D.Lgs. 117/2026, operative 1 January 2027**, moving its exit tax from art. 166 to art. 193 and expanding it from four cases to five. No annual-refresh cadence catches that; only **effective-dated rows plus change detection** do. Equally, **Ireland's individual rule is a recapture on return** (s.29A TCA 1997, ≤5 years of assessment abroad), not a departure charge — a *timing* constraint, not an exit cost, which is a different thing to model and a different thing to advise on.

The design conclusion is uncomfortable but unavoidable: **a `regime_closes` hazard is necessary but not sufficient.** The model also needs an `regime_rewritten` event at a low rate that invalidates an entire jurisdiction's parameter set at once, because that is what actually happened here.

---

## 5. The derivation layer

Raw fields become ~12 derived indices, each normalised to **[0, 100] across the T1 universe for the reference year**, using a **robust z-score mapped through a logistic**, clipped at the 2nd/98th percentile:

```
idx(x) = 100 · σ( (x − median(x)) / (1.4826 · MAD(x)) / 1.7 )
```

Why robust + logistic rather than min-max: a single outlier (Norway, Singapore, Luxembourg) must not compress everyone else into 92–98. Min-max on 45 countries does exactly that and produces a leaderboard where everything looks identical.

### 5.1 The derived indices

| # | Index | Construction | Direction |
|---|---|---|---|
| 1 | **Real return, after tax** $\rho_i$ | $\sum_a w_a \, r_{a,i}^{gross}(1-\tau_{a,i}) - \pi_i - \text{friction}_i$ | ↑ |
| 2 | **Cost of living** $\kappa_i$ | ICP PPP conversion ÷ aggregator share, rebased to home = 100 | ↓ |
| 3 | **Tax burden** $\tau_i^{eff}$ | Share-weighted effective rate on a **typical user portfolio**, not the headline top rate | ↓ |
| 4 | **Fiscal capacity** | Inverse of (debt/GDP × aging multiplier × real rate) | ↑ |
| 5 | **Aging pressure** | Old-age dependency 2050 ÷ today, plus pension-system sustainability | ↓ |
| 6 | **Social floor** | Health spend pc PPP × (1 − out-of-pocket) × replacement rate × inverse Gini | ↑ |
| 7 | **Climate exposure** $C_i$ | Weighted hazard composite, **using the p90 across regions for a risk-averse user** | ↓ |
| 8 | **Nature** $N_i$ | 0.35·BII + 0.25·ln(protected area) + 0.2·forest + 0.2·air quality, penalised by population density | ↑ |
| 9 | **Connectivity** $K_i$ | 0.5·ln(fixed) + 0.3·ln(mobile) + 0.2·DC-region proximity (latency) | ↑ |
| 10 | **Openness** | Inverse capital controls + visa-free count + ease of residency | ↑ |
| 11 | **Institutional quality** | WGI mean + V-Dem liberal democracy + CPI, averaged (they correlate ~0.85; averaging kills idiosyncratic noise) | ↑ |
| 12 | **Friction for this person** $\phi_i$ | Language, credential recognition, network distance, family distance | ↓ |

### 5.2 Two transformations that carry most of the value

**(a) PPP → a personal cost-of-living index.**
$$
\kappa_i = \frac{\text{PPP}_{i}}{\text{PPP}_{home}} \times \frac{\text{basket}_i}{\text{basket}_{home}}, \qquad
\text{basket}_i = \alpha\, h_i + \beta\, s_i + (1-\alpha-\beta)
$$
with $h$ a housing index (the field where PPP is worst), $s$ services, and $\alpha,\beta$ set by the user's actual spending shares. A remote worker earning in CHF and spending 40% on housing gets a very different $\kappa$ than a retiree spending 15% on housing. This is where a "cost of living" number stops being a league-table statistic and becomes personal.

**(b) Fisher, consistently, with the currency drift.**
$$
1 + r^{real}_{i} = \frac{1 + r^{nominal}_{i}}{1 + \pi_i}, \qquad
\tilde{r}_{i \to home} = (1+r^{real}_i)(1 + \dot{e}_{i,home}) - 1
$$
where $\dot{e}$ is expected real FX drift. **This is where most expat calculators go wrong.** If you move to a country with 6% inflation and 8% nominal returns, your real return is 1.9%, not 8%. If the currency then depreciates by inflation differential (long-run PPP), the euro value of your wealth is flat — which is exactly right and rarely modelled.

**Parity check on this platform:** your `marts.fct_macro_series_*` already gives real yields, breakevens and FX vol for EUR/USD, EUR/GBP etc. The $\dot{e}$ term should be estimated from *your own* data rather than a hard-coded assumption. That is a genuine, non-trivial reuse of what you have built.

---

## 6. The personalisation layer

### 6.1 The user profile vector

```python
u = {
  "age": 35,
  "nominal_home": "DE",
  "currency": "EUR",
  "gross_income": 120_000,        # annual, home currency
  "income_type": "employment",    # employment | remote | business | pension | capital
  "income_geography": "local",    # local | foreign_remote | mixed   <-- decisive
  "net_worth": 500_000,
  "asset_mix": {"equity": 0.6, "bonds": 0.15, "real_estate": 0.15, "cash": 0.10},
  "capital_mobility": "mobile",   # mobile | locked | mixed
  "annual_spend_home": 55_000,
  "horizon_years": 25,
  "languages": {"de": "native", "en": "fluent", "es": "basic"},
  "passports": ["DE"],
  "health_status": "good",
  "family_ties": {"DE": "parents", "CH": "none"},   # distance penalty input
  "hard_constraints": {"no_language_barrier": True, "min_social_floor": 55},
  "preferences": {                 # 1..5 sliders — the only subjective input
    "wealth": 5, "nature": 5, "connectivity": 5,
    "climate_safety": 4, "social_system": 4, "culture": 3, "safety": 4
  },
  "risk_aversion": 3,             # 1..5 → drives p10-vs-median and p90 climate use
  "tax_ethics_shock": 0           # allow "I will not use a zero-tax haven"
}
```

Five fields do most of the work: `income_geography`, `capital_mobility`, `age`, `languages`, and `preferences`. Everything else is refinement.

### 6.2 Objective weights from subjective sliders — done defensibly

Do **not** just normalise the 1–5 sliders into weights. That makes the model double-count: a user who rates "nature" 5 will get a nature-heavy answer even if nature is objectively irrelevant to their stated goal. Instead:

$$
w_d^{obj} = \frac{\exp(\beta \cdot \tilde{x}_d)}{1 + \exp(\beta \cdot \tilde{x}_d)}, \qquad
w_d = \frac{\lambda\, w_d^{obj} + (1-\lambda)\, w_d^{subj}}{\sum_d \left(\lambda\, w_d^{obj} + (1-\lambda)\, w_d^{subj}\right)}
$$

where $\tilde{x}_d$ are the objective drivers (e.g. for wealth: $\rho$, $\tau^{eff}$, $\kappa$; for wellbeing: the social floor, climate, nature) and $\lambda \approx 0.6$. Then **clamp** each $w_d$ to $[w^{min}_d, w^{max}_d]$ where the bounds derive from `hard_constraints`, and renormalise. Hard constraints become weights of 1.0 or 0.0, not large numbers — this keeps the arithmetic sane.

### 6.3 Friction: pricing the non-fungible capital

$$
\phi_i = \underbrace{\phi^{lang}_i}_{\text{CEFR distance}} + \underbrace{\phi^{cred}_i}_{\text{credential recognition}} + \underbrace{\phi^{net}_i}_{\text{network}} + \underbrace{\phi^{fam}_i,\ \text{decays } e^{-t/3}}_{\text{family distance}}
$$

with concrete, non-arbitrary anchors:

- **Language:** $\phi^{lang}_i = \left(1 - \text{English proficiency}_i\right) \times L_{user} \times c_{lang}$, where $L_{user}$ is 0/0.5/1 for fluent/basic/none. $c_{lang}$ is calibrated as **one year of forgone income** for a genuine language barrier (UN/OECD migrant wage-penalty literature puts the earnings penalty of a language barrier at roughly 15–25% in the first years). Do not invent this number; cite a range and use the midpoint.
- **Credential recognition:** 0 for licensed professions (medicine, law, teaching) in non-mutual-recognition countries, small otherwise.
- **Status portability** — this is the variable most indices ignore and it matters enormously. Model it as $\phi^{status}_i = \max(0,\ s_{home} - s_i^{recognised}) \cdot \gamma$, where $s$ is a **vertical position measure** (percentile of the income distribution you occupy). Moving from the 92nd percentile in Germany to the 60th percentile in Singapore is a real, quantifiable loss of standing that converts directly into a utility penalty. Free proxies: income percentile implied by your income ÷ national income distribution (WID.world), plus a "professional prestige retention" flag for regulated professions.
- **Family distance:** gravity-style decay, $e^{-d/1500\text{km}}$, weighted by the strength of the tie.

Every one of these has an empirically anchored constant rather than a made-up one. That is what makes the score defensible rather than astrology.

---

## 7. The engine: lifecycle simulation

For each candidate country, simulate the rest of the user's life. **Two state variables, both stochastic.**

### 7.1 Financial accumulation

Let $W_t$ be net worth in the numéraire and $S_t$ real savings.

$$
W_{t+1} = \max\!\left(0,\ (W_t + S_t)\,(1 + \tilde{r}_i + \eta_t) - \text{move}_t - \text{shock}_t\right)
$$
$$
S_t = \underbrace{(\text{gross income}_t)\,(1 - \tau^{income}_i)}_{\text{after-tax income}} - \underbrace{\kappa_i \cdot \text{spend}_{home}}{\text{local spending in numéraire}}
$$

with:
- $\eta_t \sim$ fat-tailed (Student-t, ν≈4) **annual real return shock**, mean $\tilde{r}_i$, vol $\sigma_i$ taken from the actual asset mix and the country's historical return/vol — **not** a single global assumption. Where the local market is small, blend in the global factor and add an FX term.
- `move_t` = one-off relocation cost (shipping, deposits, double rent, exit tax crystallisation) concentrated in year 0.
- `shock_t` = Poisson-timed large losses: currency crisis, property crash, expropriation / capital controls, health event, war. Rate parameterised by the openness, FX-vol and climate-exposure indices. **This is what makes the model able to say "the median is great but the 10th percentile is bad", which is the whole reason for simulating.**

Income growth: $\text{gross income}_t$ grows with a **country-specific wage curve** (OECD/ILO earnings-by-age profiles) rather than a flat assumption, and is multiplied by a **labor-market depth factor** (can this person actually get this job here?) and a **language penalty** that decays over 3–5 years.

### 7.2 Wellbeing and survival

$$
\text{QALY} = \sum_{t=0}^{T} \mathbb{E}\!\left[\, _tp_x(\mathbf{H})\ \right] \cdot Q_i(\mathbf{C},\mathbf{N},\mathbf{K},\mathbf{S}) \cdot \delta^t
$$
- $_tp_x$ from country life tables, **modulated by health-system quality** (HALE/LE ratio) and by climate exposure (heat mortality, air quality).
- $Q_i$ = quality weight blending the derived indices by personal weights.
- $\delta$ = a pure time-preference discount, applied to *both* axes so the two remain commensurable.

### 7.3 Where the money stops being the point

The model's most important output is not a number. It is the **break-even multiple**:

$$
\text{required wealth premium} = \frac{\Delta\phi + \Delta(1-Q)}{w_{wealth}}
$$

i.e. *"how many extra € of terminal wealth would justify giving up the German social system, your language and your network?"* Rendering the trade-off as a **price** rather than a hidden weight is what makes the recommendation arguable in a good way.

### 7.4 Where path dependence actually lives

Note that $W_{t+1}$ has $\max(0,\cdot)$. This is not cosmetic — it makes wealth **path-dependent and absorbing near zero**. A sequence-of-returns problem (retiring into a bad decade) is invisible in a linear weighted index and obvious here. Combined with irreversible brownian-style relocation costs, it justifies the simulation rather than a closed form.

---

## 8. The scoring formula (Layer 5) — the "neat formula"

The parsimonious headline. One line, all terms interpretable, all derived above.

$$
\boxed{\;
\Phi_i(u) \;=\; \underbrace{\frac{1}{T}\sum_{t=0}^{T} \ln\!\left[\,c_{i,t}(u)\,\right]}_{\text{what you can consume}}
\;+\; \lambda \cdot \underbrace{\frac{1}{T}\sum_{t=0}^{T} Q_{i,t}(u)}_{\text{how well you live}}
\;-\; \underbrace{\phi_i(u)}_{\text{what it costs you to be there}}
\;-\; \gamma\,\underbrace{\text{CVaR}_{10\%}\!\left[\text{failure}_i\right]}_{\text{policy \& tail risk}}
\;}
$$

with $c_{i,t} = \dfrac{W_{i,t}/\kappa_i}{L_i}$ the real consumption available per unit of life expectancy, and $\lambda$ calibrated so that **a one-standard-deviation improvement on the wellbeing axis is worth a fixed percentage of lifetime consumption** (start at 15%, make it a slider, document it).

Then map to a legible score:

$$
\text{Score}_i = 100 \cdot \frac{\Phi_i - \Phi_{min}}{\Phi_{max} - \Phi_{min}}
$$

and report, alongside it, the four numbers that actually drive a decision:

| Output | What it answers |
|---|---|
| **ΔNet worth** vs staying home, at the horizon, median and p10 | "How much richer am I, and how bad is the bad case?" |
| **Years of life gained/lost** (HALE) | The health/climate axis, in units people understand |
| **Break-even cost of the move** | "This is worth €X to me" — makes the trade-off explicit |
| **Fragility** | Probability the answer flips if a named regime closes or a climate scenario worsens |

**Make it beautiful with three comparisons, not one ranking:**
1. **Pareto frontier** — plot terminal wealth (x) against QALY (y), one dot per country, home country marked. The frontier is the answer; everything inside it is dominated and should be shown greyed out.
2. **Tornado / break-even chart** — for the top 3, show which single assumption flips the winner.
3. **Scorecard radar** — the 7–9 derived indices for the top 3 vs home, so the user can disagree with a specific dimension rather than the whole result.

The honesty of (2) is what separates this from every liveability index in existence. If the winner flips on a ±0.5pp return assumption, **say so**.

---

## 9. Validation — how you know it is not astrology

An index nobody tests is a horoscope. Four cheap tests:

1. **Construct validity.** Do the pillars load on the intended factors? (PCA: expect ~3–4 factors — wealth, institutions/social, climate/nature. If you get 12, your indices are noise.)
2. **Known-groups test.** Does the model reproduce *observed* migration flows? Take OECD/UN bilateral migration stock data and check whether actual movers went to countries the model scores highly **for their likely profile**. This is the single strongest available validation and it is free. If the model says Norway but everyone moves to Switzerland, the friction terms are wrong.
3. **Backtest.** Run the model as of 2005 with data available then; did the top-quintile countries actually deliver on wealth and wellbeing by 2025? Use JST and WDI vintages.
4. **Ablation.** Drop each pillar and measure rank churn (Kendall τ). Pillars whose removal barely moves the ranking should be cut — that is how you get genuine parsimony rather than a 60-field pile.

**Anti-pattern to avoid:** do not validate against EIU/Mercer. You will end up reproducing their biases, and their methodology is not better than yours.

---

## 10. Three tiers of ambition

| Tier | Raw fields | Derived indices | Output | Build cost |
|---|---|---|---|---|
| **S — The Strip** | 10 | 7 | Static ranking per profile | ~1 weekend, hand-curated CSV |
| **M — Standard** | 26 | 12 | Monte Carlo, frontier, tornado | ~2–3 weeks with this platform's stack |
| **L — Full** | ~60 + sub-national | 12 + regional distributions | Path-dependent relocation *timing* ("move at 45, not 35") | a quarter, needs the regional data discipline |

**Recommendation: build S first and be honest that it is S.** Then let the ablation test from §9.4 decide which M fields to add. Adding fields before you have the ablation harness is how these projects become unmaintainable.

The most valuable single addition beyond S is **not** more countries or more fields. It is the **timing dimension** — because "where" is frequently the wrong question and "when" is the right one. Under most exit-tax and remittance regimes, the optimal answer is a *sequence*: accumulate under a territorial regime, crystallise, then relocate. That answer is invisible in any point-in-time index and falls straight out of the simulation in §7.

---

## 11. How this drops into this platform

The existing architecture already has every piece this needs. The mapping is nearly 1:1:

| Model component | Existing platform asset | Change required |
|---|---|---|
| Country-year raw fields | `ingest/` + `raw.source_fetch` | New clients: `worldbank`, `un_wpp`, `ndgain`, `aqueduct`, `ookla`, `ember`, `oecd`, `wid` |
| Series catalog | `dbt/seeds/series_catalog` + `dim_series` | Add `country`/`pillar`/`vintage` attributes; the schema already keys on country + category |
| Normalisation & derived indices | `dbt/models/intermediate/int_macro__*` | New `int_liveability__*` models; robust-z + logistic is pure SQL |
| Country panel & scores | `dbt/models/marts/fct_*` | `fct_country_pillar_score`, `dim_country`, `fct_country_scorecard` |
| Monte Carlo simulation | `dashboard/volatility.py` (GARCH, PIT, Kupiec/Christoffersen, disjoint-window walk-forward) | **Reuse the entire validation harness.** The simulation engine in Volatility Studio is structurally the same problem — you are already doing distributional forecasting with proper backtesting |
| Reusing *your* data as model input | `marts.fct_macro_series_grains`, `fct_macro_observation_latest` | Real yields, breakevens, FX vol for the $\dot{e}$ term — **use your own warehouse instead of hard-coding** |
| API | `api/routers/v1` | `GET /v1/countries`, `GET /v1/countries/{iso3}/scorecard`, `POST /v1/recommendations` (profile in, frontier out) |
| UI | `dashboard/pages/` (multipage Streamlit suite) | New `pages/4_🌍_Where_Should_I_Live.py` — profile sliders, frontier scatter, tornado |
| Quality gates | Elementary + singular dbt tests | Tests: index ∈ [0,100], weights sum to 1, no country-year gaps in T1, score monotone in each pillar |

Two specific notes:

1. **Ookla's CC BY-NC licence** is a non-commercial licence. Fine for personal analysis; flag it before anything commercial. Same discipline applies elsewhere — put licence metadata in `series_catalog` so `dim_series` can expose it. For a platform whose stated contract is "rebuildable from raw", licence provenance belongs in the catalog, not in a README.
2. **Vintage discipline.** WPP, ND-GAIN, Aqueduct and OECD all revise. The platform's `known_at` / `realtime_start` pattern is exactly right; the liveability inputs must use it too, or backtests in §9.3 will silently use future data and the validation will be worthless.

### 11.1 A grain problem you must decide before building

I checked the existing catalog: **110 series across exactly three `country` values — `DE`, `EA`, `US`** — and 17 `category` values (`fx`, `yield`, `inflation`, …). The liveability model needs **~45 countries × ~50 annual indicators**. That does not fit the current shape, and forcing it in would break both.

The clean resolution is **two marts, not one extended mart:**

| | Existing | New |
|---|---|---|
| Grain | `(series_id, observed_at)` — high-frequency time series | `(iso3, year)` — annual cross-sectional panel |
| Dimension | `dim_series` (110 rows) | `dim_country` (~45 rows), `dim_country_indicator` (~50 rows) |
| Fact | `fct_macro_observation` | `fct_country_indicator` |
| Derived | `fct_macro_series_*` | `fct_country_pillar_score`, `fct_country_scorecard` |

Reuse the **harness**, not the tables: `raw.source_fetch`, the vintage/`known_at` pattern, the Dagster asset-per-source convention, the Elementary tests, and the API envelope. The `country` field in `dim_series` should stay alpha-2 for FX/macro; `dim_country` should key on **ISO-3166 alpha-3** and carry an explicit alpha-2 mapping, because the two conventions will otherwise collide silently.

And the genuinely valuable cross-over: **`fx_vol_5y` and `real_10y_yield` should be computed from the existing time-series marts, not re-ingested.** That is the one place where the platform you already built is directly load-bearing for the new model — the $\dot{e}$ currency-drift term in §5.2(b) comes straight out of `fct_macro_series_transforms`, and it is the term most expat calculators get wrong.

---

## 12. Open questions for you

1. **Numéraire.** Max wealth *in EUR*, or in local purchasing power? These produce different winners and you have to pick one as the headline (the other becomes a secondary column).
2. **Whose utility?** A pure individual model, or a household (partner's career, children's schooling)? Household modelling roughly doubles the friction layer.
3. **λ calibration.** I propose "1 SD of wellbeing = 15% of lifetime consumption". That is a value judgement. Do you want it fixed, or exposed as the one honest slider?
4. **Political-risk appetite.** Should the model be allowed to recommend jurisdictions with weak rule of law if the numbers win? My default is a hard gate on the institutional-quality index, but that is a choice with consequences.
5. **Ethics filter.** A `tax_ethics_shock` field can exclude zero-tax regimes. Keep it, or is that the user's business alone?
