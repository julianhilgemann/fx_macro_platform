# Upstream API Calls

How the platform fetches each series, and what the raw responses look like. The
series registry in [`ingest/config.py`](../ingest/config.py) is the single source
of truth; this doc explains the three providers behind it.

Each `Series` has a `source` (which client fetches it), a `series_id` (stable,
readable id used in the raw path + dbt pivot), and an optional `provider_key`
(the identifier the provider's API actually expects, when it differs).

Only **FRED needs a key** (`FRED_API_KEY` in `.env`). Bundesbank and ECB SDW are open.

---

## 1. FRED (spot, US rates/yields, ECB deposit rate)

- **Endpoint:** `https://api.stlouisfed.org/fred/series/observations`
- **Key:** required (`api_key`). Free: <https://fred.stlouisfed.org/docs/api/api_key.html>
- **Format:** JSON. Missing observations are the string `"."`.

```
https://api.stlouisfed.org/fred/series/observations
    ?series_id=DEXUSEU
    &api_key=YOUR_FRED_API_KEY
    &file_type=json
    &observation_start=2000-01-01
```

Response (trimmed):

```json
{ "count": 6925, "observations": [
    { "date": "2000-01-03", "value": "1.0155" },
    { "date": "2000-01-17", "value": "." }
] }
```

Parser: `parse_response` in [`ingest/parse.py`](../ingest/parse.py).

---

## 2. Bundesbank (daily German Bund yields)

Source #2 — FRED has no clean daily German 2Y, so the Bund legs come from the
Bundesbank statistics API (BBSSY flow = *daily yields of the most recently issued
federal securities*).

- **Endpoint:** `https://api.statistiken.bundesbank.de/rest/data/BBSSY/{key}`
- **Key:** none. **Format:** CSV (`format=csv&lang=en`). Missing values are `"."`.

```
https://api.statistiken.bundesbank.de/rest/data/BBSSY/D.REN.EUR.A610.000000WT0202.A?format=csv&lang=en
```

Key structure `D.REN.EUR.A6x0.000000WTmmss.A`: `A610`+`WT0202` = 2-year Schatz,
`A630`+`WT1010` = 10-year Anleihe.

Response: metadata header rows (`Comment`, `Decimals`, …) followed by data rows:

```
2014-01-02,0.21,
2014-01-04,.,No value available
2026-07-22,2.81,
```

Parser: `parse_bundesbank_csv` (keeps rows whose first column is an ISO date).

---

## 3. ECB SDW / Data Portal (ECB policy corridor)

Source #3 — the ECB key interest rate corridor. We already take the **deposit
facility rate (DFR, the floor)** from FRED as `ECBDFR`; ECB SDW supplies the
**main refinancing rate (MRO, mid)** and **marginal lending facility (MLF, ceiling)**.

- **Endpoint:** `https://data-api.ecb.europa.eu/service/data/{dataset}/{key}`
- **Key:** none. **Format:** CSV (`format=csvdata`). `startPeriod=YYYY-MM-DD` optional.

```
https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.MRR_FR.LEV?startPeriod=2000-01-01&format=csvdata
```

Dataset `FM` = financial market data. The SDMX key dimensions are
`FREQ.REF_AREA.CURRENCY.PROVIDER_FM.INSTRUMENT_FM.PROVIDER_FM_ID.DATA_TYPE_FM`:
`B.U2.EUR.4F.KR.MRR_FR.LEV` → business-freq, euro area, EUR, key rates (`KR`),
main refi fixed rate (`MRR_FR`), level (`LEV`). Ceiling is `MLFR`, floor is `DFR`.

**Change-point series:** ECB key rates return one row per rate change (not one per
day). The daily panel forward-fills them into step functions. Response is a wide
SDMX CSV; the parser reads `TIME_PERIOD` + `OBS_VALUE`:

```
KEY,...,TIME_PERIOD,OBS_VALUE,OBS_STATUS,...
FM.B.U2.EUR.4F.KR.MRR_FR.LEV,...,2026-06-17,2.40,A,...
```

Parser: `parse_ecb_sdmx_csv`. In `config.py` the `provider_key` includes the
dataset, e.g. `FM/B.U2.EUR.4F.KR.MRR_FR.LEV`.

> Note: ECB SDW also serves the euro-area AAA yield curve (dataset `YC`, e.g.
> `YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y`) — a viable daily German-ish yield source
> if the Bundesbank feed is ever unavailable.

---

## Series map

| Panel role | series_id | Source | Provider key / FRED id | Freq |
|---|---|---|---|---|
| eurusd_spot | `DEXUSEU` | FRED | `DEXUSEU` | daily |
| usd_broad_index | `DTWEXBGS` | FRED | `DTWEXBGS` | daily (2006+) |
| vix | `VIXCLS` | FRED | `VIXCLS` | daily |
| fed_funds_rate | `FEDFUNDS` | FRED | `FEDFUNDS` | monthly |
| fed_target_upper | `DFEDTARU` | FRED | `DFEDTARU` | daily (2008+) |
| fed_target_lower | `DFEDTARL` | FRED | `DFEDTARL` | daily (2008+) |
| ecb_policy_rate (DFR floor) | `ECBDFR` | FRED | `ECBDFR` | daily |
| ecb_mro_rate (mid) | `ECB_MRO` | ECB SDW | `FM/B.U2.EUR.4F.KR.MRR_FR.LEV` | change-point |
| ecb_mlf_rate (ceiling) | `ECB_MLF` | ECB SDW | `FM/B.U2.EUR.4F.KR.MLFR.LEV` | change-point |
| us_2y | `DGS2` | FRED | `DGS2` | daily |
| us_10y | `DGS10` | FRED | `DGS10` | daily |
| de_2y | `DE2Y` | Bundesbank | `D.REN.EUR.A610.000000WT0202.A` | daily (2014+) |
| de_10y | `DE10Y` | Bundesbank | `D.REN.EUR.A630.000000WT1010.A` | daily (2001+) |

Derived in `int_daily_panel.sql` (no fetch): `diff_2y`/`diff_10y` (US − Germany),
`us_2s10s`/`de_2s10s` (curve slopes), `policy_rate_spread` (fed funds − ECB DFR).

## Adding a series

1. Append a `Series(...)` to `SERIES` in `ingest/config.py` (set `provider_key`
   if the source id differs from your chosen `series_id`).
2. If it's a new source, add a fetch client in `ingest/fetch.py` (returning
   `(body, ext)`) and a parser in `ingest/parse.py`.
3. Add its `series_id` branch to the pivot in
   `dbt/models/intermediate/int_daily_panel.sql` (and a column to the API's
   `PanelRow` if it should appear in `/panel`).
