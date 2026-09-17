# Verified Data-Sourcing Report — Long-Run Returns & Migration/Mobility

Every URL below was HTTP-checked this session (curl / web_fetch). Status codes and byte counts are actual.
UNVERIFIED = could not confirm.

## ⚠️ SEVEN TRAPS THAT SILENTLY BREAK PIPELINES

1. **Trading Economics free API is GONE.** `https://api.tradingeconomics.com/ratings?c=guest:guest&f=json` → **HTTP 410**, body: *"the guest account has been discontinued."*
2. **Stooq CSV is bot-gated.** `https://stooq.com/q/d/l/?s=^spx&i=d` → HTTP **200** but body is a JS proof-of-work challenge, **not CSV**. A status-code check passes this falsely.
3. **FRED ICE BofA OAS = rolling ~3-year window only.** `BAMLEMCBPIOAS` returns 796 rows, 2023-09-18→2026-09-16, even with `&cosd=1990-01-01`. Licensing truncation, not a date-window artifact.
4. **US Census API now requires a key.** Keyless calls return **HTTP 200 + HTML "Missing Key"** page — fails silently.
5. **UN dataportal API has NO migrant stock.** Its 86 indicators include only `TNetMigration` (id 65) and `TNetMigRT` (id 66) from WPP 2024. Migrant stock is XLSX-only.
6. **JST has no `rgdppc` variable.** Real names: `rgdpmad`, `rgdpbarro`. `mortg` doesn't exist either (use `tmort`).
7. **Henley / Arton / VisaIndex all ban scraping in their ToS** — see B1–B3.
8. **Bare curl's default UA is 403'd by UN DESA and OECD landing pages** (CloudFront/Cloudflare). Send a browser UA for HTML pages; the SDMX and file endpoints serve fine without one. Never scrape OECD/UN landing pages — use the SDMX/file endpoints.

---

## TOPIC A — LONG-RUN FINANCIAL RETURN DATA

**A1 · JST Macrohistory R6 — FREE** (CC BY-NC-SA 4.0; commercial resale/integration expressly forbidden)
- Hub: `https://www.macrohistory.net/database/` · Licence: `https://www.macrohistory.net/database/licence-terms/`
- STATA: `https://www.macrohistory.net/app/download/9834512469/JSTdatasetR6.dta` (200)
- EXCEL: `https://www.macrohistory.net/app/download/9834512569/JSTdatasetR6.xlsx` (200, 1,408,158 B — downloaded, parsed)
- Docs: `.../9834516169/JST_documentationR6.pdf` · `.../9918957869/JST_RORE_Documentation_R6.pdf`
- **Coverage: 18 countries × 1870–2020 annual** (2,718 data rows verified = 18×151). Countries: AUS BEL CAN CHE DEU DNK ESP FIN FRA GBR IRL ITA JPN NLD NOR PRT SWE USA.
- Verified vars: `eq_tr bond_tr bill_rate hpnom cpi tloans stir ltrate tmort thh tbus bdebt lev ltd noncore housing_tr housing_capgain housing_rent_rtn eq_capgain eq_dp eq_div_rtn bond_rate capital_tr risky_tr safe_tr crisisJST peg peg_base JSTtrilemmaIV` — all present. `rgdppc`/`mortg`/`hp`/`rreal` **absent**.
- **Pain:** NC licence blocks commercial use; the `?t=` param is an optional cache-buster.

**A2 · Shiller — FREE**, no open licence (disclaimer only, no CC grant)
- Page `https://shillerdata.com/` · Canonical file (200, 1,674,752 B, OLE2):
  `https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/70fec4f5-727f-4e53-b5f1-179af109c5fa/ie_data.xls`
- Shorter legacy path also 200 but **stale** (1,623,552 B): `.../downloads/ie_data.xls` — use the canonical one.
- Monthly S&P 500, dividends, earnings, CPI, GS10, CAPE + total-return CAPE, **Jan 1871–present, US only**. Opaque CDN URL can rotate.

**A3 · Damodaran — FREE**, effectively unrestricted (*"no strings attached"*; no formal licence text)
- Page `https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html` · File `https://pages.stern.nyu.edu/~adamodar/pc/datasets/histretSP.xls` (200, 527,872 B, data to 2025)
- S&P 500 TR, small cap, 3-mo T.Bill, 10-yr T.Bond, Baa, real estate, gold + $100 growth. **US ONLY.**
- **No international annual-returns file exists.** `histgrGlobal/Europe/emerging/Japan/China/India/Rest.xls` are historical **growth** rates, not returns. Country coverage only via `ctryprem.xlsx` (ERP, not realized returns). Updated annually, first two weeks of January.

**A4 · UBS (ex-CS) Global Investment Returns Yearbook — summary FREE, data NOT**
- 2026 summary PDF (200, 3,307,593 B): `https://www.ubs.com/content/dam/assets/wm/static/cio/documents/giry2026-summary-public.pdf`
- 2024 summary PDF (200): `https://www.ubs.com/content/dam/assets/ib/global/in-focus/doc/ubs-global-investment-returns-yearbook-2024-summary-edition.pdf`
- **Full book = UBS Investment Bank client login only** (`https://neo.ubs.com/shared/d2cLnscpx5zB1a`); page states verbatim *"Authorized clients of UBS Investment Bank can log in to UBS Neo for full access."* No retail price.
- 35 markets + 5 composites; 23 countries + all composites start 1900. Underlying DMS database is not sold standalone.

**A5 · Other free long-run sources**
- **OECD SDMX long rates — VERIFIED.** `https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/.A.IRLT.PA._Z._Z._Z._Z.N?startPeriod=1990&format=csvfile` (200, 1,319 rows, 47 countries). **9 dims required; METHODOLOGY must be `N`** — `_Z` silently returns NoResultsFound. Yields, not total returns. 403 rate-limits under load.
- **FRED hosts OECD LTR** as `IRLTLT01<ISO3>M156N` — US from 1953, DE 1956, GB 1960, updated to 2026-08. Free, no key: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=IRLTLT01USM156N`
- **Kenneth French — free, no key:** `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip` (200) + Developed/Europe/Japan/AsiaPac/Emerging ZIPs. **Factor/portfolio returns, NOT country total-return indices.**
- **Barclays Equity Gilt Study — NOT purchasable.** Gated behind Barclays Live institutional login; no public price.
- **Baron & Wilson "Returns to Building" — NO free replication package found.** Cornell page has no data link; no Dataverse/Zenodo deposit. Use JST instead.
- **Paid:** Global Financial Data (quote-based; no working pricing URL — UNVERIFIED), LSEG Datastream.
- **Broken/bot-gated:** Stooq (challenge), Yahoo `query1.finance.yahoo.com/v8/finance/chart/^GSPC` (429), Nasdaq Data Link API (403; docs 404).
- **EODHD:** `https://eodhd.com/api/eod/AAPL.US?api_token=demo&fmt=csv` (200 demo token works).
- **Eurostat:** `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_a` (200).
- **Complement:** Maddison 2023 `https://dataverse.nl/dataset.xhtml?persistentId=doi:10.34894/INZBF2` (200); WID `https://wid.world/data/` — **real API base is `https://rfap9nitz6.execute-api.eu-west-1.amazonaws.com/prod/`**, needs free key. **`https://wid.world/api/` is the WordPress CMS API — a trap.**

**A6 · Sovereign ratings — no free machine-readable feed exists. Be blunt.**
- **TE guest API dead (410).** Free scrape fallback: `https://tradingeconomics.com/country-list/rating` (200; 184 rows, 167 with S&P).
- **No agency RSS exists.** Fitch/Moody's `/rss` return HTTP 200 `text/html` app shells = soft-404. S&P `/ratings/en/rss` → 403 (UNVERIFIED). RatingsDirect is paid.
- **WGB:** real URL is `https://www.worldgovernmentbonds.com/world-credit-ratings/` (200); the intuitive `/country-credit-ratings/` is 404. robots.txt is `Disallow:` (empty) → scraping permitted.
- **SEC NRSRO bulk:** `https://xbrl.sec.gov/rocr/2015/ratings-2015-03-31.zip` (200, real ZIP) but 2016–2026 all 404 → single snapshot, dead end.
- **Datasets:** best is `https://github.com/maxonlinux/ratings-history` (AGPL-3.0, 12★). No mature sovereign dataset exists.
- **JPM EMBI = paid/licence-restricted.** FRED has **no** EMBI series (all 404) and no EM sovereign OAS. Only `BAMLEMCBPIOAS` works — **EM corporate, 3-yr window**.
- **World Bank has NO rating indicator** (full 20,000-indicator list checked); IMF DataMapper has none (132 indicators). Free proxies: `IQ.CPA.DEBT.XQ`, `IQ.ICR.RISK.XQ`, `DT.DOD.DECT.CD`.
- **Bottom line: no free, current, machine-readable sovereign-rating or EMBI-equivalent spread feed exists.** Closest: WGB + TE HTML scrapes; FRED corporate OAS as a weak spread proxy.

---

## TOPIC B — MIGRATION, MOBILITY, PASSPORT/VISA

**B1 · Henley — free to view, LEGALLY UNUSABLE for automation**
- Ranking `https://www.henleyglobal.com/passport-index/ranking` (200). ToS `https://www.henleyglobal.com/terms-of-use` (200) states verbatim: *"Use any robot, spider, scraper, or other automated means to access the website for any purpose."* → **PROHIBITED.** No API. GMR is form-gated (no PDF).
- Two traps: `henleypassportindex.com/robots.txt` **is not a robots.txt** (serves SPA HTML); the SPA returns **HTTP 200 for every path**, so status proves nothing. Per-passport URL pattern: **UNVERIFIED**.
- An internal API host exists (`https://api.henleypassportindex.com/api/v2/hpi`) and returns Laravel JSON route-errors, but every route I tried 404s and the same-origin `/api/hpi/*` returns the SPA shell → not reachable.

**B2 · Arton Capital Passport Index — blocked**
- `https://www.passportindex.org/byRank.php` → **403 Cloudflare JS challenge** (UNVERIFIED). robots.txt allows all but `/*.php/*`. No free API, no official CSV found (UNVERIFIED).

**B3 · VisaIndex + free matrices**
- `https://visaindex.com/` (200); robots.txt fully permissive, but ToS `https://visaindex.com/terms` **bans robots AND manual copying**.
- **Usable free matrices:** `https://github.com/imorte/passport-index-data` — MIT, 83★, **199 countries / 39,601 corridors**, updated Feb 2026. Tidy CSV: `https://raw.githubusercontent.com/imorte/passport-index-data/main/passport-index-tidy.csv` (1,108,357 B). Also `xpressmike/visa-matrix` (CC-BY-SA-4.0, 39,402 corridors **with per-cell provenance + confidence** — best for QA) and `ilyankou/passport-index-dataset` (MIT, archived, 2019–2025).
- **Caveat:** imorte and ilyankou both derive from passportindex.org — not independent; agreement is not validation.
- **DEMIG VISA (Oxford):** 237 nationalities × 214 countries, **1973–2013**, free — `https://www.migrationinstitute.org/data/demig-data/demig-visa-data`; XLSX 27,639,271 B verified.
- **Wikidata has NO visa-requirement property** (property search returned zero). No SPARQL route. OWID visa-free pages 404. Timatic (IATA) and sherpa° are paid.

**B4 · OECD migration — VERIFIED WORKING (free, no key)**
- **Foreign-born stock by birth country:** `https://sdmx.oecd.org/public/rest/data/OECD.ELS.IMD,DSD_MIG_F@DF_MIG_POPF,1.0/all?startPeriod=2020&format=csvfile` → 200, **44,618 rows**; dims `REF_AREA, BIRTH_COUNTRY, SEX, EDUCATION_LEV, UNIT_MEASURE` → a free destination×origin matrix.
- **International Migration Database:** `.../OECD.ELS.IMD,DSD_MIG@DF_MIG,1.0/all?...` → 200, 185,130 rows (`CITIZENSHIP` dim).
- **Standardised permanent inflows:** `.../OECD.ELS.IMD,DSD_MIG_INT@DF_MIG_INT_PER,1.0/all?...` → 200, 842 rows. Temporary: `DSD_MIG_INT@DF_MIG_INT_TEMP`.
- Regional foreign-born: `OECD.CFE.EDS,DSD_REG_MIGRANT@DF_MIGR_STOCK,1.0`. Free licence; ~1-year lag. 38 OECD REF_AREAs, through 2024.
- **DIOC / DIOC-E no longer exist as separate dataflows** — searched all 1,548 OECD dataflows: zero DIOC hits. Absorbed into IMD.
- **URL-form trap:** the conventional `AGENCY,DSD,VER/DF` form 404s ("Could not find Dataflow"). You must use the joined SDMX-3.0 id `DSD_MIG@DF_MIG`. Also `format=jsondata` → 406; use `format=json-structure-2.0.0` for structure, `format=csvfile` for data. IMO 2025 landing pages (DOI `10.1787/ae26c893-en`) return **403 to both curl and web_fetch** — UNVERIFIED by direct fetch.

**B5 · UN DESA International Migrant Stock 2024 — FREE, XLSX only (all 200, verified)**
- Hub: `https://www.un.org/development/desa/pd/content/international-migrant-stock`
- Destination: `https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/undesa_pd_2024_ims_stock_by_sex_and_destination.xlsx` (541,936 B)
- Origin: `.../undesa_pd_2024_ims_stock_by_sex_and_origin.xlsx` (231,809 B)
- **Origin × Destination:** `.../undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx` (**6,005,287 B**)
- **Coverage: 233 countries/areas, by sex, origin and destination — but only 8 TIME POINTS, NOT annual.** Years read from the actual file bytes: **1990, 1995, 2000, 2005, 2010, 2015, 2020, 2024** (no 2019/2021/2022/2023). Doc code `POP/DB/MIG/Stock/Rev.2024`. Licence **CC BY 3.0 IGO** (stated inside the workbook). Key facts PDF: `.../undesa_pd_2025_intlmigstock_2024_key_facts_and_figures_advance-unedited.pdf`
- **API:** dataportal base `https://population.un.org/dataportalapi/api/v1/` serves WPP **net migration only** (ids 65/66), NOT stock. Content page 403s bare curl (needs browser UA); file URLs serve fine. **No CSV exists** (zero `.csv` links on the page).
- **No standalone data dictionary URL** — the dictionary is the "Migrant notes" sheet inside each XLSX.
- **Bonus free API route for stock:** World Bank WDI mirrors it — `https://api.worldbank.org/v2/country/WLD;USA;DEU/indicator/SM.POP.TOTL?format=json&date=1990:2024` (200, no key, 35 years).

**B6 · Expat / foreign-born beyond UN DESA**
- **Eurostat (free, no key):** foreign-born = `migr_pop3ctb` (dimension `c_birth`) → `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/migr_pop3ctb?format=JSON&lang=EN` (200, 5.2 MB). Citizenship = `migr_pop1ctz` (dim `citizen`, 200, 4.9 MB). Asylum = `migr_asyappctza` (200). Residence permits = `migr_resfirst`, `migr_reschange`, `migr_resvalid`. All updated 2026-08/09.
- **`migr_pop8ctz` and `migr_resid` are 404** ("ERR_NOT_FOUND_4 … not available for dissemination") — do not use. **`lfsa_pganws` exists but is citizenship + labour status, NOT foreign-born** — a common wrong assumption.
- **Bulk TSV:** `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/<CODE>?format=TSV&compressed=false` (migr_pop1ctz 72,970,303 B; migr_pop3ctb 67,295,551 B). `migr_asypenctzm` → 413 (too large; must filter).
- **US Census ACS:** `https://api.census.gov/data/2023/acs/acs5?get=NAME,B05002_001E,B05002_013E&for=state:*` — **key now REQUIRED** (keyless 302-redirects to `missing_key.html`: *"A valid key must be included with each data API request."*). The old "keyless up to 500 queries/day" premise is **no longer true**. Variables verified keylessly via `.../acs5/variables/B05002_001E.json`: `B05002_001E` total, `B05002_013E` foreign-born, `B05002_014E` naturalized. Also `B16005`, `DP02`.
- National statistics offices remain the only source for many bilateral stocks; no harmonised free aggregator beyond OECD/Eurostat/UN.
