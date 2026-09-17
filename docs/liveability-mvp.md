# The 80/20 MVP — Minimum Viable Decision Engine

**One page of maths, 8 user inputs, 12 numbers per country, 1 output.** Everything else in this repo is reference material. This is the build.

---

## 1. The insight that makes it small

Three things my own worked example proved, which collapse the scope:

**1. The decision is two-country, not 45-country.** You compare *home* against *alternatives*. A 15-country ranking is a leaderboard nobody acts on. "Keep what you have, or move here" is a decision. **Ship 15 countries, present 2 numbers per country, never a podium.**

**2. Precision on cost of living is mostly wasted.** Cost of living enters the model in exactly **one term** — it scales the part of income you *spend*, and only the local-spend fraction. In the worked example, Swiss prices cost −€1.1M and cut both ways against a +€764k wedge and +€687k capital term. The drivers are the **wedge ratio**, the **return gap**, and **childcare**. Get those three roughly right and the answer holds; get rent wrong by 10% and nothing flips.

**3. On 25 years, any persistent annual gap dominates everything.** 2pp for 25 years is 1.64× terminal wealth. So the model is really just: *what is the persistent annual difference, and does it survive friction?* That is a spreadsheet, not a platform.

**Corollary:** you do not need a Monte Carlo engine for v1. You need one closed-form number per country plus a break-even table. Add variance in v2 when someone asks "but what if markets fall?"

---

## 2. What the user gives you — exactly 8 fields

| # | Input | Why it can't be defaulted |
|---|---|---|
| 1 | **Age** | Sets horizon → controls magnitude, and the timing optimum |
| 2 | **Current country** | The baseline everything is measured against |
| 3 | **Gross annual income** (home currency) | Primary driver |
| 4 | **Investable net worth** | The term that flips the recommendation (worked example: crossover ≈ €300k) |
| 5 | **Annual spending** | Single biggest lever on the sign — most people know this |
| 6 | **Share of capital that is mobile** | 0–100%. Illegal/expensive to move = taxed at home rates. **Erases most of the tax advantage and must be asked.** |
| 7 | **Children (0–3)** | Flips Switzerland (−€1.9M at wage parity with one child) |
| 8 | **One slider: "more money ↔ better life" (1–5)** | The only preference you need. Collapses nature/connectivity/climate/social/culture into one axis. |

**Deliberately NOT asked:** languages (the friction model was over-engineered — replace with a curated per-country `english_ok` flag), risk tolerance (v2), asset mix (use a sane 70/30 default), current salary-vs-remote (ask *only* "do you need a local job?" — one boolean).

**That's the whole form.** If it takes more than 90 seconds to complete, the product fails.

---

## 3. What you look up — 12 numbers per country

Every one of these is a **static row in a CSV**, hand-checked once. No live API is required for v1.

| # | Field | Free source | Notes |
|---|---|---|---|
| 1 | `wedge` — effective tax+social on €-at-your-income | OECD Tax Database + national law | **Income-dependent.** Store 2 points (mid/high earner) or a tiny function. Verified figures exist for 21 countries already. |
| 2 | `cap_tax` — effective rate on a 70/30 portfolio | national law (verified matrix) | Blend of CGT + dividend. Hand-curated, effective-dated. |
| 3 | `kappa` — price level vs home | **WB `PA.NUS.PPP` ÷ `PA.NUS.FCRF`** | Free, CC BY 4.0, no curation. |
| 4 | `kid_cost` — one child, % of gross, net of subsidy | **OECD Family Database** + national fee schedules | The swing factor. ~6% DE, ~28% CH. |
| 5 | `real_return` — after-tax real return on 70/30 | `cap_tax` + long-run returns + CPI | Derive, don't source. |
| 6 | `wage_index` — comparable gross salary vs home | WB GDP pc PPP as proxy, OR curated ratio | **The biggest unknown and the biggest lever.** Start with GDP pc PPP ratio; let users override. |
| 7 | `childcare_years_remaining` | derived from youngest child age | Optional — v2 |
| 8 | `exit_tax_flag` + `threshold` | verified tax matrix | Binary + threshold. €500k/fund for DE. |
| 9 | `social_floor` — 0–100 | WHO health spend × (1−OOP) × replacement rate | For the wellbeing axis. |
| 10 | `nature` — 0–100 | Protected area + forest + air quality | For the wellbeing axis. |
| 11 | `english_ok` | curated 0/1 | Replaces the entire language-friction model. |
| 12 | `climate_risk` — 0–100 | ND-GAIN (⚠ non-commercial) or Copernicus | For the wellbeing axis. |

**Nine of the twelve are already sitting in `docs/`.** This is a copy-and-verify job, not research. Expect **two focused days**.

---

## 4. The model — three lines

For each country, for each candidate **move year** `s` (0 = now, 1..T):

```
net_income(c)   = gross × wage_index(c) × (1 − wedge(c))
local_spend(c)  = spend × kappa(c) + kids × kid_cost(c) × gross
save(c)         = net_income(c) − local_spend(c) − exit_tax_once(s)

W(T) = W0 × Π(1 + r_t)  +  Σ save(c_t) × (1 + r_{c_t})^(T−t)
         where c_t = home for t < s, destination for t ≥ s
         and   r    = capital_mobile × r_dest + (1 − capital_mobile) × r_home
```

Then:

```
score(c) = log(W(T))  +  λ × wellbeing(c)  −  friction_once(c)
```

**Three parameters, not three hundred.** `λ` (how much a point of life-quality is worth) is the one honest judgement call — start at "1 SD of wellbeing = 15% of terminal wealth", expose it, and never hide it.

**And the headline output is not a country — it's `s*`, the optimal switch year**, found by simply evaluating all `T` values of `s`. That is a loop over 25 numbers. It is free, and it produces the one output no index in the world produces:

> *"Stay in Germany until 50, then move to Switzerland. Worth €1.2M more than moving now, €0.4M more than never moving."*

---

## 5. What you show — one screen, four numbers per country

1. **Terminal wealth vs staying home** — median, and a low case (just `r − 2%`, no Monte Carlo)
2. **Break-even** — *"prices would have to be 2.04× Germany to cancel this"* / *"you need €X of capital before this works"*
3. **Optimal switch year** `s*` — the schedule
4. **One-line verdict with the trade disclosed** — *"Switzerland: +€1.4M, but you are buying it with a 1.6× price level and 28% child costs. With two children this inverts."*

Plus **one sensitivity bar** showing which single input flips the answer. In the worked example that bar said *wage ratio* — not tax. **Shipping that bar is what makes the product trustworthy, and it is 20 lines of code.**

---

## 6. Getting away for free — the commercial question answered

Decide this now, because it changes the ingest layer, not just a licence page:

**If personal tool / free product — build on everything as-is.** The 8 `blocked_commercial` fields (JST, ND-GAIN, Ookla ×2, WHO ×3, Protected Planet) are fine. Nothing to do.

**If you intend to charge — swap exactly four things:**

| Need | Blocked source | Free-commercial substitute |
|---|---|---|
| Long-run returns | JST R6 (NC-SA) | Damodaran `histretSP` (no strings) + Ken French + Maddison |
| Climate risk | ND-GAIN (NC) | Copernicus / open-meteo CMIP6 — **you're already switching to open-meteo anyway** |
| Broadband speed | Ookla (NC-SA) | ITU DataHub (public) — worse, but legal |
| Health | WHO GHO/GHED (NC-SA) | World Bank `SH.XPD.*` (CC BY 4.0) |

**Four substitutions, half a day.** My recommendation: **build the personal tool now, keep the ingest modular, and defer the swap until revenue is real.** Do not pre-optimise for a licence regime you may never need.

**And the good news on cost:** the entire MVP needs **one hand-curated table (tax regimes — already 21 countries, sourced and verified) plus six free bulk downloads.** There is no paid tier anywhere in the critical path.

---

## 7. Build order

| Step | Work | Effort |
|---|---|---|
| 1 | The 12-field × 15-country CSV, with `source` and `licence` per cell | 2 days |
| 2 | The model as a **single Python file** — function in, dict out. No database. | 1 day |
| 3 | Validate: reproduce the DE→CH worked example to within 10% | 0.5 day |
| 4 | A form with 8 inputs and one results screen (Streamlit is fine) | 2 days |
| 5 | The sensitivity bar | 0.5 day |

**Six days to something that genuinely advises.** No Dagster, no dbt, no Postgres, no API layer. All of that is already built if and when you need it — but the *product* starts as one CSV and one function.

---

## 8. What to cut, explicitly

- ❌ 45 countries → **15**
- ❌ Monte Carlo → **closed form + `r−2%` low case**
- ❌ Language friction model → **one `english_ok` flag**
- ❌ 7 preference sliders → **1**
- ❌ Country ranking → **home-vs-alternative, and an optimal year**
- ❌ Live APIs → **static CSV**
- ❌ Sub-national climate → **country-level** (v2)
- ❌ QALY/health-adjusted life years → **a simple wellbeing index** (v2)

**The one thing not to cut: the break-even table.** It is what separates this from every liveability index, and it is the cheapest part of the build.

---

## 9. Honest limits of the 80/20

It will be **wrong about magnitude and right about direction**. It cannot price: policy change (a regime closing in year 8), market sequence risk, currency crisis, or the value of your actual friends. It should say so on the results screen.

And the one input it will get most wrong is **`wage_index`** — what you can really earn abroad. Every sensitivity run in this project pointed there. **Ship a "what salary would you actually get?" override field, and let the user own that number.** That single affordance matters more than any amount of additional country data.
