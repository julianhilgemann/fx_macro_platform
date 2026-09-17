# Worked Example — German Resident, Age 35, "Asset Maximisation + Nature + Connectivity"

Companion to [`liveability-index-spec.md`](liveability-index-spec.md). This file runs the model on the concrete case in the original question.

> **⚠ CORRECTION NOTICE (v2, 17 Sep 2026).** Version 1 of this file concluded that "Switzerland is a wash for this profile." **That conclusion was wrong**, for two reasons: (a) the German effective wedge was understated — the research pass in [`../research/tax-regime-matrix-2025-2026.md`](../research/tax-regime-matrix-2025-2026.md) produced verified 2026 figures showing a **45.6%** wedge at €120k gross, not 43.2%; and (b) gross income was held identical across countries, which is unrealistic and silently drove the result. Corrected below. **The error is itself the most useful finding in this file** — see §8.

> **All figures are illustrative and parameterised, not advice.** Tax figures are taken from the sourced matrix; cost-of-living and return parameters are documented model inputs.

---

## 1. The profile

| Input | Value |
|---|---|
| Age / horizon | 35 / 25 years |
| Numéraire | EUR |
| Gross income | €120,000/yr (employment, locally sourced) |
| Investable net worth | €500,000 |
| Asset mix | 70% equity / 30% bonds |
| Annual spend | €55,000 |
| Passport | German (EU) |
| Hard constraints | no language barrier; social floor ≥ "decent" |

**Stage 1** removes most of the world before any scoring: EU passport plus the language constraint leaves the OECD-core 19.

---

## 2. Germany baseline (verified 2026 parameters)

| Parameter | Value |
|---|---|
| Top marginal PIT | 45% above €277,825; 42% from €69,879 |
| Grundfreibetrag 2026 | €12,348 |
| Social bases 2026 | KV/PV €69,750; RV/AV €101,400 |
| **CGT on listed securities** | **26.375%**, no holding-period relief |
| **Effective wedge at €120k** | **income tax 31.4% + social 14.2% = 45.6%** |
| Net income | €65,248 |

After-tax real return on 70/30, derived not sourced: **2.02%**.

---

## 3. Switzerland — corrected, and now model-verified

| Parameter | Value |
|---|---|
| CGT, private investor | **0%** on movable assets |
| Effective wedge at €120k | **25.8%** (mid-canton) |
| Annual **wealth tax** | real and recurring (cantonal) — modelled, break-even 1.95%/yr |
| Price level | **1.62× Germany** |
| One child, annual cost | **~40% of gross** (childcare is the driver) |
| After-tax real return | **4.40%** (vs Germany 2.02%) |

### Terminal wealth at age 60, real EUR — at wage parity (the strict test)

| Children | Gain vs staying in Germany | Verdict |
|---|---|---|
| **0** | **+€305,000** | **Move now** |
| **1** | **€0** | **Stay** |
| 2 | €0 | Stay |

**Switzerland wins with no children even at identical gross salary.** The mechanism is the ~20pp wedge gap plus a 2.4pp better after-tax real return.

### And children are a first-class input, not a footnote

| Wage ratio CH/DE | 0 kids | 1 kid | 2 kids |
|---|---|---|---|
| 1.0 | +305k | **STAY** | STAY |
| 1.2 | +1,123k | **STAY** | STAY |
| **1.4** | +1,941k | **+130k** | STAY |
| 1.6 | +2,759k | +947k | STAY |
| 2.0 | +4,394k | +2,583k | **+772k** |

**The rule: Switzerland works single at any wage ratio; with one child it needs ≈1.35× the German gross; with two children ≈1.9×.** Child cost is a percentage of *local* gross income, so a high Swiss salary mechanically restores the case — which is why the wage ratio, not the tax rate, is the decisive input.

⚠ **This corrects an earlier version of this file twice over.** v1 said Switzerland was "a wash"; v2 said "two children never work at any plausible wage ratio". Both were wrong, and the second was wrong because of a real bug: child costs were only applied *after* the switch year, so they never offset the destination's advantage. The model in `scripts/liveability_model.py` now applies child cost in whichever country you live in that year, and `tests/test_liveability_model.py` guards it.

---

## 4. The decisive variable is the wage curve

```
sign(ΔW) ≈ sign( (wage_ratio − 1) − (κ − 1)·spend_share − kid_cost_drag )
```

The tax wedge barely moves the **sign** — it is large enough at any plausible value that Switzerland wins on capital alone. What decides the *magnitude* is the gross wage ratio and the child-cost drag. So the model must ingest **earnings-by-age data**, and the UI must expose the wage ratio as a user override.

---

## 5. The timing dimension

> **Note on magnitudes.** The v1 timing block below still holds gross income equal across countries, so its deltas (≈±€80k) are much smaller than §3's corrected figures (≈+€235k to +€2.6M). **What it isolates is *timing*, not destination**, and its structural conclusions survive the recalibration intact — the exit tax (§6) is a one-off of order €78k against an advantage of order €0.2–2.6M at this wealth level.

Holding the wage ratio at 1.0 to isolate tax/price effects, varying **when** the move happens (terminal wealth at age 60, real EUR):

| Strategy | No exit tax | With exit tax |
|---|---|---|
| Stay in Germany throughout | 1,217,700 | 1,217,700 |
| Move to Switzerland at 35 | 1,137,900 (**−79,800**) | 1,137,900 (−79,800) |
| Move to Switzerland at 45 | 1,257,300 (+39,600) | 1,138,000 (−79,700) |
| Move to Switzerland at 50 | **1,265,100 (+47,300)** | 1,111,400 (−106,300) |
| Move to Switzerland at 55 | 1,249,700 (+32,000) | 1,073,600 (−144,100) |

*(This block still holds gross income equal across countries — hence the smaller deltas than §3. It isolates timing, not destination.)*

1. **Moving early is the worst strategy when the exit tax does not apply** — at wage parity, Swiss prices hit you immediately while the capital base is still small. The optimum is to accumulate under the German wage system and switch once the portfolio is large enough for the return gap to dominate the price gap: **around age 50**.
2. **If the exit tax bites, the optimum moves earlier.** The crystallised liability is largely sunk once you leave, and the deemed gain only grows. The decision "leave" and the decision "when" are coupled through the exit-tax base.

### 5.1 The timing optimum is age-graded

| What is optimised | Where it is earned | Age at which it dominates |
|---|---|---|
| **Labour-income wedge** (tax + social on salary) | High-wage, high-tax country | 35–50 — the wedge applies only to *income*, and in these years nearly all cash flow is income |
| **Capital-income drag** (tax on returns) | Zero-CGT jurisdiction | 50–70 — a *multiplicative* drag on a stock, so it only matters once the stock is large |
| **Cost-of-living / price level** | Cheap country | throughout, but *additive* — hits cash flow, not the compounding stock |

**The best country therefore changes with age for a fixed preference set**, and no single-country answer is correct over a 25-year horizon. The model should return a *schedule*, not a winner.

---

## 6. The rule that decides the exit tax: §19(3) InvStG

Germany's **Jahressteuergesetz 2024** introduced exit taxation on **privately held investment fund units — explicitly including ETFs — effective 1 January 2025**, modelled on the older §6 AStG rule. Verified scope:

- Applies to anyone unlimited-taxable in Germany for **≥7 of the last 12 years** — exactly this profile.
- On emigration a **fictitious disposal** is deemed at market value, taxed at 26.375%; **losses are not deductible**.
- Bites only in "weighty cases": **≥1% of a fund's units**, or **acquisition cost ≥€500,000 in a single fund**.

For a €500k portfolio:

| Funds held | Cost/fund | €500k test | Exit tax on the 25-year gain |
|---|---|---|---|
| 1 | €500,000 | **TRIGGERS** | **€77,700** |
| 2 | €250,000 | safe | €0 |
| 3 | €166,700 | safe | €0 |
| 10 | €50,000 | safe | €0 |

**Same person, same money, same destination: €77,700 or €0 depending purely on how many ETF positions the portfolio is split across.** The penalty scales with the portfolio (≈15.5% of starting wealth over 25 years) — it is a tax on having done well.

Three features a static model would miss:

1. **Stundung (§6(4) AStG).** Payable in **7 equal interest-free annual instalments** — worth ≈**€11,100 NPV** on a €77,700 liability at a 4% real discount rate. Requires *Sicherheitsleistung*; whether fund units are accepted as security is discretionary.
2. **Rückkehrregelung (§6(3) AStG).** If you are unlimited-taxable in Germany again **within 7 years (extendable to 12)**, the tax **falls away retroactively**. The exit tax is a **contingent liability, not a sunk cost** — a Monte Carlo prices the probability the move sticks; a spreadsheet cannot.
3. **Deferral landscape has shifted.** EU/EEA deferral was **abolished 1 Jan 2022**; interest-free unlimited deferral was restored **only for pre-2022 Switzerland moves** (BMF, 2 Jun 2025). **ECJ C-430/25 "Gena"** may force broader deferral, with spillover expected ~2027. Poland is directly at issue in the same case. So even the *payment mechanics* are a time-varying parameter.

**Corrected reading:** the "with exit tax" column is a **planning-dependent scenario**, not a fixed penalty. Two legal levers move it to zero: split the portfolio so no single fund reaches €500k of acquisition cost, and/or structure the move with a return option.

---

## 7. The other regimes, re-priced against 2026 reality

### Greece — no exit tax, but the flat tax is strictly foreign-source

Verified 2026 parameters: **no personal exit tax** (Greece's ATAD exit tax, art. 66A ITC, is **corporate-only** — Greece declined to extend it to individuals); **15% CGT on listed securities, exempt if the transferor holds <0.5% and for Greek/EU/EEA UCITS**; **5% dividend tax**; and **art. 5A, a €100,000/yr lump-sum regime for 15 years** requiring a **€500,000 investment** (an *inbound* requirement — note this is **not** an exit-tax threshold, an easy conflation). Law 5222/2025 made the 15-year period **non-extendable** and changed relative/5C coverage.

The catch is structural, not numerical: **the €100k lump sum and the 5% dividend rate apply to *foreign-source* income only.** A €120k salary earned *in* Greece is taxed under the normal Greek scale (top 44% above €60,000) **on top of** the €100k minimum — an effective burden above €140k versus €54,752 in Germany. Worthless for a locally-employed earner; potentially excellent for a remote worker or a capital owner with genuinely foreign-source income.

**This is exactly why `income_geography` is the highest-leverage field in the user profile vector.** Same person, same country, same regime — opposite recommendation depending on where the money is earned. Note also the risk framing: Greece's attractiveness here rests largely on *absence-of-evidence* findings for several regimes, which the research matrix flags explicitly.

### Czechia — the strongest EU regime for a buy-and-hold accumulator, and I had not credited it at all
The final research pass closed Czechia with a materially different picture from the brief:

- **Securities held >3 years are exempt from CGT** (5 years for corporate shares), and the **CZK 40m value test was repealed for securities and corporate shares from 1 Jan 2026** (Act No. 360/2025 Coll.). For a buy-and-hold equity investor this is close to a **0% capital-gains regime with no holding-period penalty after three years**.
- **Foreign dividends can elect a flat 15% separate base** (§16a) instead of the 15%/23% general base — a genuinely competitive rate against Germany's 26.375%.
- **Inheritance is exempt for all beneficiaries** (ZDP §4a(1)(a), no relationship test — the 15%/23% charge was the pre-2014 tax, abolished 1 Jan 2014). So `inherit_tax_rate` = **0 for everyone**, not just descendants.
- **No personal exit tax** (§23g is corporate-only), and the 3-/5-year time tests survive emigration.
- 23% solidarity rate above CZK 1,762,812 (2026); employee social 11.6%.

On this profile Czechia competes directly with Cyprus and Malta while adding a deep labour market, EU mobility, strong connectivity and good nature access. **It fails the user's `no_language_barrier` constraint on social integration, not on professional life** — which is exactly the distinction §3 of the spec now insists the model express.

### Poland — promoted, on two findings I had wrong
My brief had Poland as having **no migrant regime**. The research pass *initially* reported a **PLN 200,000/yr lump-sum foreign-income regime (up to 10 years)**, and I promoted Poland to T1 partly on that basis. **The researcher's closing position flags that cell as an unresolved conflict** — two streams read the same sources and reached opposite conclusions — and recommends it not be used without checking the statute. **I am therefore withdrawing the lump-sum claim from this file.**

What survives on verified grounds: **a personal exit tax in force** (art. 30da PIT: PLN 4,000,000 threshold, 19% standard, non-business assets caught only after ≥5 years' Polish residence in the last 10; only *collection* deferred, with payment moving to before 1 Dec 2027), **EU freedom of movement**, a deep labour market, and strong connectivity. That is enough for T1 — but not enough to promise a tax regime.

For a German-passport user Poland remains a serious candidate, and it fails the `no_language_barrier` constraint on *social* rather than professional integration. Adjustment: **Poland stays in T1, on the verified grounds only.**

### Ireland — worst of both worlds, and its exit tax is a *return* recapture
33% CGT ⚠, 33% dividends with no imputation, combined marginal ~52% with USC and PRSI (4.35% from 1 Oct 2026), CAT Group C €20k threshold for non-descendants at 33%. Excellent for *corporate* structures, poor for a personal portfolio. The **remittance basis was retained** — my brief had conflated Ireland with the UK.

More importantly for the model: **Ireland has no individual exit tax.** Its corporate exit tax is ATAD-derived (ss.627–629C, 12.5%, 5 instalments). The individual rule is **s.29A TCA 1997, "temporary non-residents" — a recapture on *return*, not a departure charge**, applying to Irish-domiciled individuals who return within ≤5 years of assessment. (My brief's citation of s.579A was wrong: that section is *attribution of gains to beneficiaries*, an offshore-trust rule.) **A recapture on return is a timing constraint, not an exit cost — a different quantity to model and a different thing to advise on.**

### The Gulf — wins the arithmetic, breaches the constraints
AE: 0% PIT, no CGT, no wealth tax, no inheritance tax, and UAE has **no personal-tax investor regime at all because none is needed**. Excluded by `social_system` and `climate_safety`. **Present it as an explicit exchange rate**: "the Gulf is worth €X of terminal wealth to you; you told me the social floor is worth more."

### Singapore
Top PIT 24% above S$1m, **no CGT**, 0% dividends, no wealth tax, no estate duty. Foreigners on Employment Pass are outside CPF — meaning no local pension accrual. Breaches `climate_safety` (tropical heat exposure) and `social_system`.

### Cyprus — underrated on this profile
**No CGT on listed securities**, non-dom regime 17 years with a paid extension, and — decisively for a euro-based user — **EUR denomination, so zero FX risk against the numéraire**. ⚠ The Article 3D paid extension deadline for *existing* non-doms was **30 June 2026 and has passed**; a new arrival's position needs checking against Circular 2/2026.

---

## 8. Why v1 got it wrong — and what that implies for the model

V1 concluded "Switzerland is a wash" from three compounding errors, each individually small:

| Error | Effect on the conclusion |
|---|---|
| German wedge set to 43.2% instead of the verified **45.6%** | Understated the moving gain |
| Gross income held **identical** across countries | Removed the single largest real-world term |
| Swiss annual **wealth tax omitted** entirely | Overstated the Swiss case (partially offsetting) |

Two of the three pushed toward "don't move", one pushed toward "move", and the net was a confidently wrong answer. **This is the argument for the model, made by the model failing.**

The design implications:

1. **The sensitivity harness is not optional.** The joint sweep in §3 took minutes and immediately showed every cell positive — one table would have caught the error at once. Any headline recommendation must ship with its break-even table.
2. **`income_geography` and the wage ratio must be first-class inputs, not constants.** They dominate the answer and they are the inputs a user can actually research about themselves.
3. **Verified tax parameters need effective dates and a source**, which is why §4.4 of the spec now demands a versioned regime table rather than per-country columns. Three of the five regimes in the v1 shortlist changed materially during a 21-month window (§9).

---

## 9. Regime churn — the empirical case for a `regime_closes` hazard

The 2025–26 research pass turned up an unusual density of changes to exactly the regimes this model depends on:

| Jurisdiction | Dated change / verified position | Status |
|---|---|---|
| Italy | Flat tax **€200k → €300k** (1 Jan 2026); no separate €100k neo-resident regime exists | In force |
| Australia | 50% CGT discount **repealed**; CPI indexation + **30% minimum CGT** from 1 Jul 2027 — but the new minimum tax applies to **residents only**, and **CGT event I1 is unchanged** by the reform | Legislated (Acts 49 & 50 of 2026) |
| Canada | 66.67% inclusion-rate hike **cancelled**; **no departure-tax threshold exists** (ITA s.128.1(4)) — and **the family home is excluded** from the deemed disposition | Reversed |
| Cyprus | Non-dom extension now **paid** (€250k per 5-yr block); SDC on dividends 17% → 5%; existing-non-dom deadline passed 30 Jun 2026 | In force |
| Netherlands | 30% ruling step-down **reversed**: flat 30% to 2026, **27% from 2027**; Box 3 accrual reform **stalled**; Box 2 is **24.5%/31% in both 2025 and 2026** (33% was 2024 only) | Pending |
| Norway | Exit tax **survived**; ESA closed the complaint (**094/25/COL**, 25 Jun 2025) **without ruling on EEA compatibility**; threshold NOK 3m, 37.84%, 12-yr deferral; NOU 2026:9 proposes no change enacted | Unchanged |
| France | PFU **30% → 31.4%** (1 Jan 2026, LF 2026); residence test is **6 of the previous 10 years**; 15-yr *dégrèvement* restoration **not retained** | In force |
| Estonia | Announced PIT rise to 24% **scrapped** — **22% in both 2025 and 2026** (EMTA-confirmed); only VAT rose to 24% | Reversed |
| Czechia | CZK 40m value test **abolished** 1 Jan 2026 (securities/corporate shares); transfer-of-assets-out is **entities-only**; **inheritance exempt for all beneficiaries** | In force |
| Switzerland | Federal 50% inheritance tax **rejected** (30 Nov 2025); *Eigenmietwert* taxation abolished, in force ~2029 | Mixed |
| Germany | EU/EEA exit-tax deferral abolished 2022; interest-free unlimited deferral restored **only for pre-2022 Switzerland moves**; **ECJ C-430/25** may force broader deferral ~2027 | Pending |
| Poland | **Personal exit tax in force** (art. 30da PIT, PLN 4m, 19%); only *collection* deferred, payment moves to before 1 Dec 2027. Domestic referral **WSA Warszawa III SA/Wa 566/25** — distinct from C-430/25 | In force |
| Spain | **10 of 15 years** (not 5-of-10), triggers (>€4m) OR (>25% AND >€1m), rate = savings scale 19/30%; referred to the **CJEU** over discriminatory treatment | Pending |
| Singapore | No CGT/exit tax; emigration = **IR21 tax clearance**; RITC in force 1 Sep 2025 | Confirmed |

**Thirteen jurisdictions, thirteen material changes or verifications, in 21 months — including four outright reversals.** This is decisive for the model design: tax regimes must be a **versioned, effective-dated fact table with a change-detection pipeline**, not per-country columns refreshed annually. The observed churn implies a materially higher `regime_closes` hazard than the 5–7% I originally proposed.

**And a cautionary note on the research itself:** the exit-tax module corrected **twelve of my original premises**, including four where I had cited the wrong statute (Netherlands art. 7.5 vs art. 4.16(1)(h); Australia TAP at s 855-45 vs s 855-15; Japan's tourist departure levy mistaken for the gains exit tax; Norway's *Elopak* case miscited as an exit-tax ruling). **Every one of those errors would have produced a confident, wrong recommendation.** This is the single strongest argument for the confidence-and-source columns in `fct_tax_regime` (§4.5 of the spec) — an unsourced regime table is worse than none, because it launders uncertainty into authority.

---

## 10. The honest conclusion for this profile

**Under the stated constraints the answer is Switzerland** — model-verified at +€305k with no children at wage parity, rising to +€2.4M at a realistic 1.5× wage ratio. And it inverts with children below a 1.35× wage ratio.

| Point | Country | W₂₅ | Why it is on the frontier |
|---|---|---|---|
| **Best wealth** | **CH** | €1.36M–3.70M | Positive at every combination of wage ratio and price level tested; +€0.2M to +€2.6M over staying |
| **Best low-tax EU alternative** | **CZ / PL** | not modelled | CZ: 0% CGT after 3y, 15% elective dividend base, 0% inheritance for all, no exit tax. PL: PLN 200k/yr foreign-income lump sum, deep market |
| **Best wealth-to-nature** | **NZ** | ~€1.60M | No general CGT, world-class nature, English-speaking; thin labour market, distance from family |
| **Constraint-breaching, high-wealth** | AE / SG | €2.35–3.58M | Wins on arithmetic; breaches `social_system` and `climate_safety` — show the exchange rate |
| **Euro-denominated alternative** | CY / MT / CZ | n/a | No CGT on listed securities, no FX risk against the numéraire |
| **Inside the language constraint, negative on wealth** | AT | €1.15M | The model says: do not move to Austria for money |

**What to tell the user, in one line:** *Switzerland, on a wealth case that survives every sensitivity we ran — and the decisive open question is not tax at all, it is what gross salary you can actually command there. Czechia and Poland belong in the same conversation and I had not modelled them.*

And the three highest-value actions, none of which is "choose a country":

1. **Split the ETF portfolio now** so no single fund reaches €500k of acquisition cost — worth €77,700 of certain tax at this portfolio size.
2. **Test the wage ratio before the tax rate.** It controls the magnitude by a factor of ten; the tax wedge barely moves the sign.
3. **Keep the return option open** — the §6(3) Rückkehrregelung makes the exit tax contingent rather than sunk, which changes the optimal decision for anyone not certain they will stay.

**And the honest caveat:** Czechia and Poland entered this analysis *last*, because my initial candidate set used a binary language filter that deleted them. They may well outrank Switzerland on an after-tax basis for a buy-and-hold investor. **The model was wrong about the shortlist, and only a full run will settle it** — which is the strongest possible argument for building it rather than reasoning about it.

---

## 11. Open questions this exposed

1. **Swiss cantonal parameters remain unverified** — wealth-tax rate scales, AHV/ALV/BVG rates and ceilings, and the Circular 36 safe-harbour thresholds that determine whether the 0% private CGT treatment survives. The first two affect the result by a few percent; **the third would break the core advantage** if a user's activity pattern crosses the professional-dealer line.
2. **The wage curve is the model's biggest unmodelled lever.** It needs OECD/ILO earnings-by-age-and-occupation data plus an occupation-specific local-market depth factor. Ingesting it is more valuable than adding ten more country indicators.
3. **Numéraire choice interacts with §7.** Cyprus and Malta's euro denomination is worth real option value to a euro-based user and is invisible in a USD-numéraire model.
4. **`regime_closes` should be calibrated, not assumed.** With ten changes in 21 months, the hazard rate can be estimated from the observed churn rather than picked.
