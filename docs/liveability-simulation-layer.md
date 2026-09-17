# The Simulation Layer — Confidence Bands Without Parameter Bloat

**Premise:** sophistication is not more parameters. It is **honest variance**. A model that reports a band and decomposes where the band comes from looks scientific because it *is* — and it costs maybe 120 lines more than the deterministic version.

The trick: **move uncertainty from the user to the data.** Every extra user slider is a guess you made them make. Every uncertainty you derive from history or published scenarios is rigour you can defend.

---

## 1. Universe: OECD-core only

Tightening to **18 countries** (OECD + CH, which is the natural set for this bracket):

DE CH AT NL BE LU IE GB FR SE NO DK FI IS IT ES PT CZ PL

**Why this is the right cut:** inside this set, data quality, currency convertibility, rule of law and reporting standards are comparable. You never have to answer "is this number real?" — so the band you report is about the *future*, not about the *data*. **A confidence interval on bad data is a lie with error bars.**

Drop US/CA/AU/NZ/JP/KR to a v2 tier: they matter, but they add FX regimes, citizenship-based taxation and visa gates that break the clean framing.

**Corollary:** no language-friction model needed. English is professional-grade in all 18, so it reduces to a 0/1 `local_language_needed` flag.

---

## 2. The minimum user set: 10 fields

| # | Input | Why it must be asked |
|---|---|---|
| 1 | Age | Horizon → controls magnitude and the schedule |
| 2 | Current country | Baseline |
| 3 | Gross annual income | Primary driver |
| 4 | Investable net worth | The term that flips the answer (crossover ≈ €300k) |
| 5 | Annual spending | Biggest lever on the sign |
| 6 | **Equity share of portfolio** | **Reveals risk aversion** — see below. Far better than asking |
| 7 | **Children: count + ages** | Drives cost *and the schedule* (childcare ends at school age) |
| 8 | Local job needed? (Y/N) | Determines whether the wage ratio applies at all |
| 9 | **Minimum lifestyle floor** | A hard constraint, not a weight — stops "recommend Dubai at any price" |
| 10 | **One slider: accumulate ↔ live well** | Collapses 7 preference sliders to 1 axis |

**The one methodological upgrade worth making:** **derive risk aversion from the equity share, do not ask for it.** Someone holding 70% equities has revealed their risk appetite; asking them to rate it 1–5 produces noise and inconsistency. This is standard portfolio-choice calibration and it is *both* more rigorous and one less question. γ = 1 + 4 × equity_share is a defensible mapping (γ≈3.8 at 70/30).

---

## 3. The value function — the thing that earns the "sciency" label

Do not maximise expected wealth. **Maximise expected CRRA utility and report the certainty equivalent.** The certainty equivalent is the number to display because it is in euros and already risk-adjusted:

```
U  = Σ β^t · [ p_t · u(local_consumption_t) + λ · q_t · wellbeing ]
u(c) = c^(1−γ) / (1−γ)                     # CRRA
CE = [ (1−γ) · E[U] ]^(1/(1−γ))            # certainty equivalent, in euros
```

Now you can say, correctly and defensibly:

> *"Switzerland: certainty-equivalent +€840k, with a 5–95% band of +€120k to +€2.1M."*

That is a sentence no liveability index can produce, and it is the direct consequence of simulating rather than scoring. **Report CE, not E[W].** The gap between them *is* the risk premium, and showing it is the whole point.

---

## 4. Where the uncertainty comes from — 5 sources, all derivable

Critically, **four of the five are estimated from data, not assumed.** That is what makes the bands credible.

| # | Source | Distribution | Where the parameter comes from |
|---|---|---|---|
| 1 | **Market returns** | Student-t, ν≈4 (fat tails) | Country equity/bond vol & correlation from JST R6 (1870–2020) — **18 countries, exactly our universe** |
| 2 | **Inflation** | Historical σ by country | CPI from JST/WDI. Matters enormously via the real-return term |
| 3 | **FX** | Random walk, σ from realised | **The one non-euro members need:** CH, GB, SE, NO, DK, IS, CZ, PL. Free from FRED/BIS |
| 4 | **Wage growth** | σ by country + income percentile | OECD/ILO earnings dispersion. Use the *dispersion*, not a point forecast |
| 5 | **Policy regime change** | Hazard ≈ 5%/yr, flips a country's tax row | **Calibrate from observed churn**: the tax research found 15 corrections / 13 jurisdictions / 21 months |

**And one thing you should NOT randomise: demographics.** UN WPP 2024 gives aging trajectories that are near-deterministic over a 25-year horizon. Simulating them would be false sophistication. **Apply them deterministically** and use the certainty in that dimension as the reason the band is narrow.

**Climate: scenario-conditioned, not sampled.** Run RCP 4.5 and 8.5 as two deterministic paths and show both. Sampling a climate trajectory would imply a probability distribution nobody believes.

**This is the key design claim:** you have exactly **five genuinely stochastic inputs**, four estimated from 150 years of data, one calibrated from observed legislative churn. That is defensible. Twenty user sliders is not.

**Implementation:** ~20,000 paths. Array-based, runs in seconds. That is the entire "engine."

---

## 5. Variance decomposition — the killer chart

Run the simulation with each source switched on and off, and present a **waterfall of where the uncertainty comes from**:

| Source | Share of total variance |
|---|---|
| Market returns | ~55% |
| FX (non-euro destinations) | ~20% |
| Policy regime change | ~15% |
| Wage growth dispersion | ~8% |
| Inflation | ~2% |

*(Illustrative shape — compute it on your data. The point is that it is computable, and it will surprise people: **policy risk dwarfs inflation**, and FX matters more than most users expect.)*

**This one table is the most convincing artefact in the product.** It says: we know exactly which assumption is driving your answer, and we're not hiding it. It also kills the most common objection ("your model is just assumptions") by showing you can *rank* your own assumptions.

---

## 6. The schedule as a distribution, not a point

Don't return "move at 47." Return **P(optimal move year = t)** across paths:

```
P(optimal year)   ▁▁▂▄▇█▇▄▂▁▁
                  35        50        60
```

Two outputs fall out that are worth the whole build:

1. **Stability window** — the range of years where ≥80% of paths agree. *"Anything between 46 and 53 gives you ≥95% of the benefit."* This converts a fragile point estimate into actionable advice, and it is exactly the "schedule with intervals" you asked for.
2. **The sequencing insight, discovered rather than asserted.** Because children's ages are an input, the simulation will *find* the pattern: **childcare costs are concentrated in the pre-school years, so the optimal schedule is often "accumulate where the wedge is low while children are young, relocate when they reach school age."** You don't have to encode that rule — it emerges. **That is genuine model value, and it is the thing that makes a professional trust the output.**

---

## 7. Presentation — the premium surface

Four charts, all standard, all defensible:

1. **Fan chart** — terminal wealth p5/p25/p50/p75/p95 over time, home vs top 2. The visual language of every serious risk report.
2. **Variance waterfall** — §5.
3. **P(optimal year) histogram** — §6.
4. **Break-even curve** — the one input that flips the answer, plotted. (In the worked example: wage ratio.)

Plus a **one-line verdict with the trade disclosed**, and an **assumptions panel** listing every parameter with its source and confidence flag.

**The honesty affordances are what read as premium.** Saying *"this recommendation flips if your Swiss salary is below 1.2× your German one"* signals command of the model. A confident single number signals the opposite to anyone sophisticated enough to be your user.

---

## 8. What this costs you

| Layer | Added effort |
|---|---|
| CRRA value function + certainty equivalent | 0.5 day |
| 5 stochastic sources wired to real historical data | 1.5 days (JST/WDI/FRED are already downloaded) |
| 20k-path vectorised simulation | 0.5 day |
| Variance decomposition + 4 charts | 1.5 days |

**~4 days on top of a ~6-day deterministic MVP.** Call it **10 days to a product that looks and behaves like a research instrument.**

And note it is *strictly additive*: the deterministic model is the base case of the simulation (1 path, no variance). Build it first, validate it, then wrap the simulation around it — never the other way round.

---

## 9. Discipline: what would make this pseudo-scientific

- ❌ **Simulating demographics.** They're near-deterministic; sampling them adds noise, not information.
- ❌ **Sampling climate.** Use scenarios. A sampled climate path is a probability claim you can't defend.
- ❌ **Correlating everything.** Five sources with a stated correlation matrix ≠ full Cholesky on 40 parameters. Keep it to the equity/bond/FX block.
- ❌ **Reporting a band without decomposing it.** An unexplained interval is decoration.
- ❌ **Ten thousand paths when 20k converges.** Show the convergence check once, then move on.
- ❌ **Hiding γ behind a slider.** Derive it from the equity share and say so.

The line between rigorous and pseudo-rigorous is not the number of parameters. It is **whether you can name the source and the size of every uncertainty in your own output.** §5 is how you prove you can.
