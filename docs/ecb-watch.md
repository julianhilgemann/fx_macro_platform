# ECB Watch — short-term euro rates and market-implied policy probabilities

> Status: **implemented and running.** Ingest → dbt → Streamlit, with a
> third-party cross-check wired in as a scoring series rather than a source of
> truth. Verified end to end against live data; every number quoted below is a
> real value read back out of the warehouse.

## 1. The two questions this answers

1. **Where is the euro money market right now?** The level, dispersion and
   volume of the euro risk-free overnight rate, and the very short end of the
   OIS curve. A *backward-looking* measurement problem.
2. **What does the market expect the ECB to do at its next meetings?** A
   probability distribution over the deposit facility rate (DFR) after each
   scheduled Governing Council decision. A *forward-looking* inference problem.

These are different in kind, use different instruments, and — importantly — are
computed from different inputs. Conflating them is the single easiest way to get
this wrong, so the platform keeps them in separate series and separate marts.

## 2. Why this is not simply "FedWatch for the euro"

CME's FedWatch tool decomposes **30-day Fed Funds futures**. The euro equivalent
decomposes **dated €STR futures** — contracts that settle on the compounded
€STR over one ECB reserve maintenance period, so a single contract isolates a
single policy decision. That is the trade-accurate input.

The ECB and the Bundesbank do not publish it. What the official APIs actually
offer was established by direct probing, not assumption:

| Source | Dataset / series | Forward-looking? | Cadence | Available? |
|---|---|---|---|---|
| ECB Data Portal | `EST` — €STR headline + compounded 1W/1M/3M/6M/12M | **No** — compounded averages are realized | Daily | ✅ free, no key |
| ECB Data Portal | `FM/D.U2.EUR.4F.KR.DFR.LEV` — DFR | n/a (policy level) | Daily | ✅ free, no key |
| ECB Data Portal | `MMSR` — OIS weighted average rate, buckets 1M…2Y | **Yes**, but bucketed | ~6-weekly, lagged | ✅ free, no key |
| ECB Data Portal | `EMMS` — extended money market stats (`INT_DER_TYPE=OIS`) | Yes, annual aggregates | Annual | ✅ free, no key |
| ECB Data Portal | Survey of Monetary Analysts (`SMA`) | Would be | — | ❌ **no SDMX dataflow exists** |
| ECB Data Portal | €STR futures / meeting-dated OIS quotes | Yes, exact | — | ❌ not published |
| Bundesbank | `BBIG1/…EOSWAP…` — EONIA swap index (1W…12M) | Yes | Monthly | ⚠️ **discontinued 2014-06** |
| Bundesbank | `BBMMB/D.EU000A2X2A25.WT` — €STR | No (mirror of ECB) | Daily | ✅ (redundant) |
| ecb-watch.eu | `/probabilities` — dated €STR futures (their metadata: `EMP` / `FEMP`) | Yes, exact | Daily | ⚠️ third-party, keyless |

**Conclusion.** A fully official, meeting-dated OIS curve does not exist as a
public API. The platform therefore builds the best official approximation it
can (MMSR buckets), and carries the futures-based third-party number alongside
it purely to *measure the size of that approximation*. That measurement is
`fct_ecb_probability_crosscheck`.

## 3. The instruments, and why they behave the way they do

### 3.1 €STR

The euro short-term rate is the volume-weighted trimmed mean of unsecured
overnight borrowing by euro-area financial corporations, published by the ECB
each TARGET business day for the previous day. It is the euro risk-free
overnight rate and the successor to EONIA.

### 3.2 The corridor, and why €STR sits *below* the floor

The ECB steers short rates through a corridor: **deposit facility rate (floor) –
main refinancing rate (middle) – marginal lending rate (ceiling)**. A naive
expectation is that €STR should pin to the DFR. It does not: €STR has
consistently fixed **roughly 6–9 bp below the DFR**.

The reason is institutional, and it matters for the maths below. Only banks can
park cash at the ECB's deposit facility. Money market funds and other non-bank
lenders cannot, so their alternative to lending unsecured overnight is holding
cash at zero (or near-zero) remuneration. They therefore lend *below* the floor
rather than not at all, which drags the fixing under the DFR. The corridor
bounds behaviour but does not pin the fixing.

### 3.3 OIS and the expectation identity

An overnight index swap exchanges a fixed rate for the compounded overnight
rate over a term. Because it is collateralized and settles against a risk-free
overnight rate, it carries negligible credit or funding premium — which is
exactly what makes it a clean read on expected policy.

For a single-curve, continuously-compounded world, the fair OIS rate to maturity
$T$ satisfies

$$R(0,T) \;=\; \frac{1}{T}\int_0^T \mathbb{E}^{\mathbb{Q}}\!\left[r(s)\right] \mathrm{d}s$$

i.e. **an OIS rate is the market's expectation of the average overnight rate
over its life**. Two consequences the engine leans on:

- a change in the OIS curve at a given horizon is a change in expected policy;
- the average expected rate over a *specific window* is directly readable from
  the curve, provided you can query the curve at that window.

Caveat stated up front: $\mathbb{E}^{\mathbb{Q}}$ is the **risk-neutral**
expectation. Implied probabilities are risk-neutral, not real-world
frequencies — standard for this class of tool, and the reason they are read as
"market pricing", never as forecasts.

### 3.4 Compounded €STR is backward-looking — do not use it for expectations

The `EST` dataset also publishes compounded average rates at 1W, 1M, 3M, 6M and
12M. These compound the **realized** overnight fixings over the *trailing*
window. They are an excellent description of where the money market has been and
what cash actually earned; they contain **no** information about the future.
They are ingested, charted, and deliberately kept out of the probability model.

## 4. The calculation chain

Implemented in `dbt/models/marts/fct_ecb_meeting_probabilities.sql`. Five steps.

### 4.1 Piecewise-linear OIS curve

Seven official buckets with tenor in years:

| Bucket | 1M | 2M | 3M | 6M | 9M | 12M | 2Y |
|---|---|---|---|---|---|---|---|
| $t_j$ (y) | 0.0833 | 0.1667 | 0.25 | 0.50 | 0.75 | 1.00 | 2.00 |

For a target maturity $t$, the engine brackets it between adjacent buckets and
interpolates linearly:

$$r(t) = r_{lo} + (r_{hi}-r_{lo})\,\frac{t - t_{lo}}{t_{hi}-t_{lo}}$$

Outside the curve it **clamps** (flat extrapolation) rather than dropping the
meeting — a missing row on a dashboard is worse than a conservative one.

### 4.2 Maintenance-period midpoints

A Governing Council decision takes effect at the **start** of a reserve
maintenance period, and maintenance periods are delimited by consecutive
meetings. So the period opened by meeting $i$ is
$[d_i,\; d_{i+1})$ and the average overnight rate expected over it is, by §3.3,
the object of interest. Applying the **midpoint rule** (second-order accurate
for a smooth rate path) lets a single curve point stand in for that average:

$$m_i = d_i + \left\lfloor \tfrac{d_{i+1}-d_i}{2} \right\rfloor,\qquad
t_i = \frac{m_i - a}{365.25}$$

with $a$ the curve's as-of date.

### 4.3 Expected change per meeting

$$\Delta_1 = r(t_1) - \text{DFR},\qquad \Delta_i = r(t_i) - r(t_{i-1})$$

The first meeting is anchored on the **current DFR**, not on a previous curve
point: the period running from today to the first meeting is expected to average
the current policy rate. Meetings already decided are excluded — a meeting
between the curve snapshot and today is already baked into the DFR, and
including it would double-count the decision and mis-anchor every later meeting.

### 4.4 The 25bp decomposition

Policy moves are conventionally quoted in 25bp steps. Convert the expected
change into step units and split it between the two adjacent multiples:

$$s_i = \frac{\Delta_i}{0.25},\qquad f_i = \lfloor s_i \rfloor,\qquad q_i = s_i - f_i$$

$$X_i = \begin{cases} f_i & \text{w.p. } 1-q_i\\ f_i+1 & \text{w.p. } q_i\end{cases}$$

This is the standard FedWatch simplification, and it has a useful property worth
being explicit about: it is the **unique two-point distribution supported on
$\{f_i, f_i+1\}$ with the correct mean**. Hence
$\mathbb{E}[X_i]\cdot 0.25\text{ bp} = \Delta_i$ exactly — the discretization
reshapes the distribution but does **not** bias the expected move. It is not,
however, a true risk-neutral density: a real density would spread mass over
more than two outcomes. Changes are clamped to $\pm4$ steps ($\pm100$bp) as a
sanity bound on a stale input.

### 4.5 Convolution to a level distribution

The rate level after meeting $k$ is the anchor plus the sum of the per-meeting
steps:

$$L_k = \text{DFR} + 0.25 \cdot \sum_{i=1}^{k} X_i$$

and its distribution is the convolution of the per-meeting two-point laws:

$$\Pr\!\left[L_k = \text{DFR} + 0.25m\right]
= \sum_{\substack{x_1..x_k \in \{f_i,f_i+1\} \\ \sum x_i = m}} \;\prod_{i=1}^{k} \Pr[X_i = x_i]$$

Because each meeting contributes at most two adjacent outcomes, the support
after $k$ meetings is at most $k+1$ contiguous 25bp levels. The engine
enumerates the paths exactly with an integer bitmask: bit $i-1$ of the mask
selects the lower or upper step for meeting $i$, and meeting $k$ enumerates
$2^k$ masks.

> **Why $2^k$ and not $2^N$.** Enumerating the full $N$-meeting space and
> summing per meeting counts each of meeting $k$'s prefixes $2^{N-k}$ times,
> inflating that meeting's mass by the same factor. This is not hypothetical —
> the first implementation did exactly that and produced meeting totals of
> 8, 4, 2, 1 instead of 1. The mask space is therefore per-meeting. Mass is
> computed in log space (`sum(ln p)`) and exponentiated, and probabilities are
> clamped to $[10^{-4}, 1-10^{-4}]$ to keep the sum finite.

### 4.6 Derived read-outs

| Quantity | Definition | Reading |
|---|---|---|
| `scenario_rate` | DFR $+ 0.25m$ | candidate DFR after the meeting |
| `probability` | $\Pr[L_k = \text{scenario}]$ | mass on that level |
| `expected_change_bp` | $100\,\Delta_k$ | implied move at that meeting |
| `prob_higher_step` | $q_k$ | probability of the upper of the two adjacent steps |
| `period_ois_rate` | $r(t_k)$ | the interpolated curve input |
| `staleness_days` | today $-$ curve as-of | the honest freshness clock |

### 4.7 Worked example — real values, build of 2026-09-22

Curve snapshot **2026-07-28** (56 days stale), buckets 1M 2.189 / 2M 2.210 /
3M 2.249 / 6M 2.356 / 9M 2.482 / 12M 2.488 / 2Y 2.546, DFR **2.50%**.

**Meeting 2026-10-29** (next: 2026-12-17, 49 days later):

- midpoint $= $ 2026-10-29 $+ \lfloor 49/2 \rfloor = $ **2026-11-22**; $t_1 = 117/365.25 = 0.3203$y
- brackets 3M (0.25) and 6M (0.50):
  $r = 2.249 + (2.356-2.249)\cdot\frac{0.3203-0.25}{0.25} = \mathbf{2.2791}$
- $\Delta_1 = 2.2791 - 2.5000 = \mathbf{-22.09}$ **bp**
- $s_1 = -0.8836 \Rightarrow f_1 = -1,\ q_1 = 0.1164$
- distribution: **2.25% w.p. 88.36%**, **2.50% w.p. 11.64%** ✔ matches the mart

**Meeting 2026-12-17** (next: 2027-02-04): midpoint 2027-01-10, $t_2 = 0.4545$y,
$r = 2.3365$, $\Delta_2 = 2.3365 - 2.2791 = +5.74$bp $\Rightarrow f_2 = 0,\ q_2 = 0.2297$.

Convolving the two (level after December):

| path | $X_1$ | $X_2$ | level | probability |
|---|---|---|---|---|
| 88.36% × 77.03% | −1 | 0 | 2.25 | **68.07%** |
| 88.36% × 22.97% | −1 | +1 | 2.50 | 20.30% |
| 11.64% × 77.03% | 0 | 0 | 2.50 | 8.97% |
| 11.64% × 22.97% | 0 | +1 | 2.75 | 2.67% |

giving the mart's 2.25 → **68.1%**, 2.50 → **29.3%**, 2.75 → **2.7%** (sum 1.000). ✔

## 5. What was implemented

```
ECB Data Portal ─┐
                 ├─► raw.source_fetch ─► dbt staging ─► intermediate ─► marts ─► Streamlit
ecb-watch.eu ────┘   (bitemporal,         (per source)   (union+dédup)   (fct_*)   :8501
                     byte-faithful)
```

### 5.1 Ingest

- `ingest/config.py` — series registry, single source of truth. **20 new
  official ECB series** (`ECB_ESTR*`, `ECB_DFR`, `EA_OIS_*`) plus
  `ECBWATCH_PROBS`, taking the platform from 110 to 131 series.
  `land_source()` iterates the registry, so new series need
  no code change beyond the config.
- `ingest/fetch.py` — new `fetch_ecbwatch` client and a **bounded retry** on
  5xx/429/connection errors for the ECB client. This is not defensive padding:
  the Data Portal returned repeated 500/504s while the MMSR series were being
  wired, and without retries a single flaky response lands a null payload for
  the day.
- `ingest/load.py` — `ecbwatch` added to the base-URL map; JSON payloads land
  verbatim, and the byte-faithful body is kept in `payload_raw` with a sha256.
- Synthetic mode produces a shape-correct ecb-watch payload so a `synthetic`
  run does not silently stage nothing.

### 5.2 dbt

| Model | Layer | Role |
|---|---|---|
| `stg_ecbwatch__probabilities` | staging | explodes the nested feed into `(fetch, meeting, scenario)`; retains **every vintage** |
| `fct_ecb_meeting_probabilities` | marts | the engine of §4 |
| `fct_ecb_probability_crosscheck` | marts | scores the engine against the reference |
| `ecb_meeting_calendar` | seed | Governing Council decision days (§5.3) |
| `series_catalog` | seed | 21 new rows; drives `dim_series` |

The generic EUR/older staging models needed no change: `stg_ecb__observations`
reads `TIME_PERIOD`/`OBS_VALUE` by name, so wide SDMX CSV drops straight in.

### 5.3 The meeting calendar is a seed, deliberately

The ECB publishes no machine-readable meeting calendar. `ecb_meeting_calendar.csv`
transcribes **decision days only** (Day 2 of each meeting) from the official
calendar, through December 2028. Non-monetary-policy and General Council
meetings are excluded — they carry no rate decision. The most recent past
decision day is retained as an anchor reference.

### 5.4 Serving

`dashboard/pages/5_🏦_ECB_Watch.py`, read-only as `platform_reader`, with
`dashboard/data.py` loaders returning plain DataFrames.

## 6. Reading the dashboard

**Header strip** — current DFR, latest €STR fixing, the OIS curve's as-of date,
and `Curve staleness` in days. Past 21 days the page raises a warning.
*Read the staleness first: it conditions everything below it.*

**Bar chart** — one bar per candidate DFR level after the selected meeting.
Heights are probabilities and **sum to 100%**. The caption sentence reports the
probability of *no change*, i.e. the mass sitting on the current DFR, plus the
expected move in bp.

**Implied rate probabilities by meeting** — rows are meetings, columns are rate
levels. Each row sums to 100% and the modal outcome is bold.

> **Interpretation trap.** A later row is the distribution of the rate *level*
> after that meeting — the cumulative path — **not** the distribution of that
> meeting's move in isolation. In the worked example December's 29.3% at 2.50%
> combines "cut in October, then hike" with "hold in October, then hold". To
> read a single meeting's own move, use `expected_change_bp` and
> `prob_higher_step` in the detail expander.

**Per-meeting detail** — expected move in bp, $q_k$, the interpolated OIS rate
that produced it, and the maintenance-period midpoint. This is the audit trail:
if a number looks wrong, it is traceable to one curve point and one date.

**Cross-check against ecb-watch.eu** — see §7.

**Short-term euro money market** — the €STR table and the €STR vs compounded-3M
chart against the DFR line. Use it for *level and liquidity*, not for
expectations (§3.4).

## 7. Validation — the cross-check metric

Total variation distance between the two distributions, in percentage points:

$$\mathrm{TV}(p,q) = \tfrac{1}{2}\sum_s \left|p(s)-q(s)\right| \;=\; 1 - \sum_s \min\!\left(p(s), q(s)\right)$$

over the **union** of the two supports. It is the minimum total probability mass
that must be relocated to turn one distribution into the other: **0% = the
engines agree exactly, 100% = they disagree completely.** A meeting the
reference does not cover yields `NULL`, not 50% — absent data is not
disagreement.

Observed, build of 2026-09-22:

| Meeting | Local (official OIS) | ecb-watch (dated €STR futures) | TV |
|---|---|---|---|
| 2026-10-29 | 2.25 → 88.4%, 2.50 → 11.6% | 2.50 → 50.0%, 2.75 → 50.0% | **88.4%** |
| 2026-12-17 | 2.25 → 68.1%, 2.50 → 29.3%, 2.75 → 2.7% | 2.50 → 5.5%, 2.75 → 50.0%, 3.00 → 44.5% | **91.8%** |
| 2027-02-04, 2027-03-18 | local only | — (outside their horizon) | `NULL` |

Worked check on the first row: the union is {2.25, 2.50, 2.75, 3.00};
$\sum|\Delta| = 0.884+0.384+0.5+0 = 1.768$, so TV $= 88.4\%$. Equivalently
$1-\sum\min = 1-0.116 = 88.4\%$.

**This divergence is the expected result, not a defect.** The official curve had
last printed **56 days earlier**, on 2026-07-28, when the market was pricing
cuts; by late September the market had flipped to pricing hikes. The two engines
are answering with inputs from different regimes. That is precisely the signal
the cross-check exists to quantify, and why the page warns above 21 days of
staleness rather than quietly printing a confident-looking number.

## 8. Known biases and limitations

Honest inventory — several are structural, not fixable by better code:

1. **Anchor mismatch (structural, ~6–9bp).** The OIS curve references €STR,
   which fixes 6–9bp *below* the DFR (§3.2), but $\Delta_1$ is computed against
   the DFR level. This injects a bias of a fraction of a 25bp step into the
   first meeting. Anchoring on €STR, or modelling the €STR–DFR spread
   explicitly, would remove it.
2. **MMSR is a realized average, not a quote.** Bucket values are
   transaction-weighted averages of OIS *actually traded* during the reporting
   window by euro-area reporting banks — not a point-in-time market quote. This
   is a second-order approximation on top of the bucket and midpoint ones.
3. **Publication lag and coarseness.** ~6–8 weeks, in ~6-weekly steps. This
   dominates the error budget (§7).
4. **Bucket resolution.** Seven points to 2Y, flat-extrapolated at the ends;
   meeting midpoints are interpolated rather than observed.
5. **25bp grid.** Assumes moves are multiples of 25bp. True for recent cycles,
   not universally — the ECB cut by 10bp in 2019. A 10bp move would be split
   across the grid and misreported.
6. **Risk-neutral, not physical.** §3.3. No term- or risk-premium adjustment,
   and no convexity adjustment to the expectation identity.
7. **Two-point support.** §4.4 — correct mean, understated dispersion.
8. **Cross-check dependency.** `ecb-watch.eu` is an undocumented third-party
   endpoint with no SLA. It is a *scoring* series; nothing downstream depends on
   it for correctness, and its own `version` / `data_sources` / `last_updated`
   metadata is carried through to the mart so freshness is auditable.

## 9. Operating it

```bash
# land the new series only (retries built in)
docker compose exec -T dagster-webserver \
  /opt/app/.venv/bin/dagster asset materialize -m orchestration.definitions \
  --select raw_ecb raw_ecbwatch

# rebuild the whole graph
.venv/bin/dbt build --project-dir dbt --profiles-dir dbt
```

**After adding dbt models, regenerate the manifest.** The Dagster dbt assets
read `manifest.json` from the shared `dbt_target` volume, so a rebuilt image
alone does not surface new models in the asset graph:

```bash
docker compose exec -T dagster-webserver /opt/app/.venv/bin/dbt parse \
  --project-dir /opt/app/dbt --profiles-dir /opt/app/dbt
docker compose restart dagster-webserver dagster-daemon
```

Known sharp edges are recorded in `agents/notes.md` (#25, #26): the manifest
volume, `bash -l` dropping the image's `PATH` so `dbt` resolves only via the
explicit `.venv` path, and `dagster asset materialize` needing `-m`.

Freshness is measurable, not assumed: `staleness_days` and `curve_as_of` are on
every probability row, and Elementary runs data tests over the whole mart chain.

## 10. Roadmap

- **Trade-accurate probabilities:** ingest dated €STR futures settlement prices
  (Eurex `EMP`/`FEMP`, or a vendor). This replaces the §4.1–4.2 approximation
  with the actual object ecb-watch decomposes, and should collapse the §7 TV
  distance to single digits. Requires a market-data agreement.
- **Finer official curve:** EIOPA publishes €STR-based risk-free term structures
  (monthly, many maturities) derived from OIS. Useful to refine §4.1 between
  buckets — at the cost of a monthly cadence.
- **Expectation drift history:** staging already retains every ecb-watch
  vintage, so "how has the implied probability of a hike moved?" is a mart away.
- **Alerting:** warn when `total_variation_pp` breaches a threshold, or when
  `staleness_days` exceeds a budget — the two failure modes that actually matter.
- **Anchor fix:** item 1 of §8; small, self-contained, removes a known bias.

## 11. References

- ECB, *Euro short-term rate (€STR)* — method and compounded averages:
  <https://www.ecb.europa.eu/stats/euro-short-term-rates/html/index.en.html>
- ECB Data Portal, dataset `EST`:
  <https://data.ecb.europa.eu/data/datasets/EST/dashboard>
- ECB, *Money Market Statistical Reporting (MMSR)* — the OIS buckets.
- ECB, *Governing Council meeting calendar* (source of the seed):
  <https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html>
- ECB, *The ECB Survey of Monetary Analysts (SMA)* — published as documents,
  **no SDMX dataflow**.
- CME Group, *FedWatch Tool* — the decomposition this mirrors:
  <https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html>
- ecb-watch.eu — <https://ecb-watch.eu/> (third-party cross-check only).
