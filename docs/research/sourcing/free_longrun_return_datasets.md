# FREE Long-Run Cross-Country RETURN Datasets — Verified Access Report

All status codes are live `curl` checks from this session (Sept 2026). "UNVERIFIED" = I could not confirm it resolves.

---

## 1. Baron & Wilson, "Returns to Building" / "The Economics of Building"
**NO FREE REPLICATION PACKAGE FOUND. UNVERIFIED.**
- `https://business.cornell.edu/faculty-research/faculty/mdb327/` → **200**, but page lists only generic research links; **no data/appendix link**.
- No Dataverse/Zenodo/journal-archive deposit located.
- **Verdict: treat as NOT publicly available.** Use instead → **JST Macrohistory** (item 10), which covers housing + equity + bond + bill returns.

## 2. Barclays Equity Gilt Study
**PAID / CLIENT-GATED. No free full edition.**
- Exact page: `https://www.ib.barclays/news-and-events/equity-gilt-study-2025.html` → **200**. Page text confirms: *"Clients of Barclays Investment Bank can log in to Barclays Live to read the complete report."*
- **Cost path: Barclays Live institutional client login only — no public purchase price.** Older editions (2012/2013) circulate free on third-party sites with unverifiable provenance — do not rely on them.

## 3. OECD Long-Term Interest Rates — ✅ FULLY VERIFIED
- **Dataflow:** `OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0`
- **WORKING bulk URL (HTTP 200, 1,319 rows, 47 countries):**
  `https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/.A.IRLT.PA._Z._Z._Z._Z.N?startPeriod=1990&format=csvfile`
- **Critical key detail:** 9 dimensions in order — `REF_AREA.FREQ.MEASURE.UNIT_MEASURE.ACTIVITY.ADJUSTMENT.TRANSFORMATION.TIME_HORIZ.METHODOLOGY`. **METHODOLOGY must be `N`, not `_Z`** — using `_Z` silently returns `NoResultsFound`. Wrong key count → `"Not enough key values in query, expecting 9 got 5"`.
- **Codes:** `IRLT` (long-term), `IR3TIB` (3-month interbank), `IRSTCI` (short-term). `FREQ` = A/M/Q.
- **Explorer:** `https://data-explorer.oecd.org/` → **200**. **Licence:** free, OECD terms. **Lag:** ~1 month.
- **Pain points:** IP-level rate limiting returns **403 "exceeded the number of requests currently permitted"**; needs `Accept: application/vnd.sdmx.data+csv;version=1.0.0`. **Gives YIELDS, not total returns.**

## 4. Global Financial Data
**PAID — confirmed. Pricing URL UNVERIFIED.**
`https://globalfinancialdata.com/` → **200**, but it is a single-page site whose only links are `#anchors` + a contact form. **`/pricing` → 404, `/subscribe` → 404, `/order` → 404**, and all legacy Joomla paths → 404. **Pricing is quote/contact-based.**

## 5. LSEG / Refinitiv Datastream
**PAID — confirmed.** `https://www.lseg.com/en/data-analytics/financial-data/pricing-and-market-data` → **200**.
- **Datastream product page URL: UNVERIFIED** — `https://www.lseg.com/en/data-analytics/products/datastream` → **404**.

## 6. Free Equity Index APIs
- **Stooq — ⚠️ NOT usable headlessly.** `https://stooq.com/q/d/l/?s=%5Espx&i=d` → **HTTP 200 but body is a JavaScript proof-of-work challenge, NOT CSV** (same on `stooq.pl`). Format is right; the response is bot-gated.
- **Yahoo chart API (unofficial, ToS-restricted):** `https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1mo&interval=1d` → **HTTP 429** from this IP. Endpoint shape is correct but throttled/blocked here.
- **EODHD — ✅** `https://eodhd.com/api/eod/AAPL.US?api_token=demo&fmt=csv` → **200** (demo token works). Pricing: `https://eodhd.com/pricing` → **200**. Free tier limits **UNVERIFIED** (not fetched).

## 7. Kenneth French Data Library — ✅ VERIFIED, all ZIPs HTTP 200
Base: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/<FILE>`
- `F-F_Research_Data_Factors_CSV.zip` ✅ · `F-F_Research_Data_5_Factors_2x3_CSV.zip` ✅ · `F-F_Momentum_Factor_CSV.zip` ✅
- `Developed_3_Factors_CSV.zip` ✅ · `Developed_ex_US_3_Factors_CSV.zip` ✅ · `Europe_3_Factors_CSV.zip` ✅ · `Japan_3_Factors_CSV.zip` ✅ · `Asia_Pacific_ex_Japan_3_Factors_CSV.zip` ✅ · `Emerging_5_Factors_CSV.zip` ✅
- Landing: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html` ✅
- **⚠️ Explicitly: these are US + developed/emerging PORTFOLIO/FACTOR returns — NOT country-level total return indices.** Free, no key, monthly.

## 8. MSCI — free factsheets, no bulk ✅
`https://www.msci.com/end-of-day-data-search` ✅ · `https://www.msci.com/index-performance` ✅ · `https://www.msci.com/real-time-index-data-search` ✅ · `https://www.msci.com/index-solutions` ✅ (all 200). Free per-index lookups; **no bulk download, no API on free tier.**

## 9. Nasdaq Data Link — ⚠️ PARTIAL
`https://data.nasdaq.com/` ✅ · `https://data.nasdaq.com/publishers/QDL` ✅ · `https://data.nasdaq.com/search?filters=%5B%22Free%22%5D` ✅.
- **API blocked:** `https://data.nasdaq.com/api/v3/datasets/FRED/GDP.json` → **403 bot-challenge page**.
- **Docs URL UNVERIFIED:** `docs.data.nasdaq.com` and `/v1.0/docs/*` → **404**. Many free datasets retired 2023–24.

## 10. Other genuinely free long-run return/series sources
- **JST Macrohistory — the strongest free substitute:** `https://www.macrohistory.net/database/` ✅ **200**. Equity/bond/bill/**housing** returns, ~18 countries, 1870–2020, free, no key. **Best answer to items 1 & 2.**
- **Eurostat:** `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_a` ✅ **200** (`irt_lt_mcby_a` = long-term govt bond yields). Browser: `https://ec.europa.eu/eurostat/databrowser/view/irt_lt_mcby_a/default/table` ✅
- **BIS:** `https://data.bis.org/` ✅; `https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0` ✅. **Long-term-rates dataflow id UNVERIFIED** (`WS_LONG_RATES` → 404).

## Macro complements
- **Maddison Project 2023 — ✅:** `https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/maddison-project-database-2023` ✅ and Dataverse NL `https://dataverse.nl/dataset.xhtml?persistentId=doi:10.34894/INZBF2` ✅ (API: `https://dataverse.nl/api/datasets/:persistentId/?persistentId=doi:10.34894/INZBF2` ✅).
- **WID.world — ✅ free, key required.** Data: `https://wid.world/data/` ✅ · bulk: `https://wid.world/bulk_download/` ✅ · codes: `https://wid.world/codes-dictionary/` ✅.
  **REST API base:** `https://rfap9nitz6.execute-api.eu-west-1.amazonaws.com/prod/` (from official CRAN `wid` package source). Returns **403 "Missing Authentication Token"** without a key; free key via `widr::wid_set_key()`.
  **⚠️ Trap: `https://wid.world/api/` is the WordPress CMS API, NOT the data API.**

---
### Bottom line
Genuinely free and machine-readable: **OECD SDMX (yields), Kenneth French, JST Macrohistory (returns incl. housing), Eurostat, Maddison, WID (with key), MSCI factsheets (manual)**. Paywalled: **Barclays EGS, GFD, LSEG Datastream**. Broken/bot-gated: **Stooq CSV, Yahoo (429), Nasdaq Data Link API**. **No free Baron & Wilson package exists.**
