# Sovereign Credit Ratings as FREE Data — Verified Access Report
All URLs curl-verified. Date of checks: this session.

## 1. Trading Economics API — FREE TIER IS DEAD
- Base: `https://api.tradingeconomics.com/`
- Ratings endpoint: `https://api.tradingeconomics.com/ratings?c=guest:guest&f=json`
  → **HTTP 410 GONE**. Body: *"We are sorry, but the guest account has been discontinued. Please subscribe to a plan at https://tradingeconomics.com/api/pricing.aspx"*
- Country variant `https://api.tradingeconomics.com/ratings/country/united%20states?c=guest:guest&f=json` → also **410**.
- Pricing: `https://tradingeconomics.com/api/pricing.aspx` (HTTP 200). Tiers are JS-rendered; no free tier listed.
- **FREE FALLBACK THAT WORKS (scrape):** `https://tradingeconomics.com/country-list/rating` → HTTP 200, 306 KB HTML table. Headers `Country | S&P | DBRS | TE`; 184 data rows, **167 with an S&P rating**. ToS: `https://tradingeconomics.com/terms` (200). Scraping is ToS-risky.

## 2. Fitch / Moody's / S&P
| Item | URL | Result |
|---|---|---|
| Fitch RSS | `https://www.fitchratings.com/rss`, `/rss/commentary`, `/rss/rating-actions` | HTTP 200 but `content-type: text/html`, body is Next.js shell → **soft-404, NOT a feed** |
| Moody's RSS | `https://www.moodys.com/rss/ratings`, `https://ratings.moodys.com/rss` | HTTP 200 `text/html`, HTML app shell → **soft-404** |
| S&P RSS | `https://www.spglobal.com/ratings/en/rss`, `/ratings/rss/ratings-news` | **HTTP 403** bot-blocked → **UNVERIFIED** |
| Fitch free research | `https://www.fitchratings.com/research/sovereigns` (200), `https://www.fitchratings.com/search/?query=&filter=commentary` (200) | HTML only |
| Moody's | `https://www.moodys.com/ratings-and-research` (200) | PAID product, price on request |
| S&P RatingsDirect | `https://www.spglobal.com/ratings/en/products-benefits/product-detail/ratingsdirect` | **HTTP 403 — UNVERIFIED by curl**; PAID, price on request |

**Only free bulk file:** SEC Rule 17g-7 NRSRO rating history (XBRL) at
`https://xbrl.sec.gov/rocr/2015/ratings-2015-03-31.zip` → **HTTP 200, application/zip, 14,491 bytes, real XBRL** (verified by download+unzip).
**But 2016–2026 all return 404** (`/rocr/2016/…` … `/rocr/2026/ratings-2026-03-31.zip`). One historical snapshot only → **dead end as a time series**.
SEC pages: `https://www.sec.gov/structureddata/rocr-publication-guide` (200), `https://www.sec.gov/structureddata` (200), `https://www.sec.gov/ocr` (200). `/structureddata/nrsro-ratings-history` → 404.

## 3. World Government Bonds
- **Correct URL: `https://www.worldgovernmentbonds.com/world-credit-ratings/`** → HTTP 200, 27,870 bytes, contains S&P/Moody's/Fitch/DBRS entries.
- `https://www.worldgovernmentbonds.com/country-credit-ratings/` → **404** (the obvious guess is wrong).
- **robots.txt allows scraping**: `https://www.worldgovernmentbonds.com/robots.txt` → `User-agent: *` / `Disallow:` (empty). Sitemap: `http://www.worldgovernmentbonds.com/sitemap_index.xml`
- **No public API.** Free to view, ad-supported.

## 4. Datasets (all URLs verified 200)
| Repo | Stars | Licence | Last push | Note |
|---|---|---|---|---|
| `https://github.com/maxonlinux/ratings-history` | 12 | AGPL-3.0 | 2024-10-01 | Best: downloads Fitch, Moody's, KBRA, Morningstar DBRS, Demotech, JCR, Egan-Jones → CSV; uses SEC NRSRO files |
| `https://github.com/ffrodslaw/ratings_scraper` | 2 | none | 2022-02-14 | "Downloading sovereign credit ratings" |
| `https://github.com/amalbuquerque/SovereignRatingDifferences` | 3 | none | 2018-04-29 | Stale |
| `https://github.com/mattdburke/ngfs-credit-ratings` | 1 | none | 2026-07-16 | NGFS climate-scenario ratings |

Kaggle: `https://www.kaggle.com/datasets/baptistef4st/moody-ratings-mean-centered` (200) is **corporate**, not sovereign. GitHub API search "sovereign credit ratings" = 28 repos, max 3 stars. **No mature, maintained free sovereign-ratings dataset exists.**

## 5. The Proxy Question
- **JPMorgan EMBI / EMBI+ / EMBI Global = PAID + licence-restricted.** Official doc verified: `https://www.jpmorgan.com/content/dam/jpm/cib/complex/content/markets/index-research/Global-Index-Research-Product-Guide-2022.pdf` → HTTP 200 `application/pdf`. `https://www.jpmorgan.com/insights/markets/indices` → 200. Redistribution prohibited.
- **FRED has NO EMBI series.** Tested `EMBI`, `EMBIG`, `EMBIUSD`, `EMBIPLUS` → **all HTTP 404**.
- **FRED ICE BofA series that DO work** (fredgraph CSV 200, data current to **2026-09-16**):
  - `https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLEMCBPIOAS` — ICE BofA **EM Corporate Plus OAS** ✅
  - `BAMLEMHBHYCRPIOAS` (EM HY Corporate Plus OAS) ✅, `BAMLHE00EHYIOAS` (Euro HY OAS) ✅, `BAMLEM1BRRAAA2ACRPIOAS` ✅, `BAMLEMRACRPIASIAOAS` ✅
  - Sovereign-specific IDs `BAMLEMSSOAS`, `BAMLEMSOVOAS`, `BAMLEMSSOVOAS`, `BAMLEMSOVSPOAS` → **all 404**. **FRED carries no EM sovereign OAS.**
- **World Bank: NO rating indicator** in the full 20,000-indicator list (`https://api.worldbank.org/v2/indicator?format=json&per_page=20000`). Verified proxies: `IQ.CPA.DEBT.XQ` (CPIA debt policy rating 1–6, 265 obs), `IQ.ICR.RISK.XQ` (ICRG composite risk rating), `DT.DOD.DECT.CD` (external debt stocks), `GC.DOD.TOTL.GD.ZS`.
- **IMF DataMapper: NO rating/spread indicator** (`https://www.imf.org/external/datamapper/api/v1/indicators`, 132 indicators, HTTP 200).
- **World Bank IDS API verified:** `https://api.worldbank.org/v2/country/ZMB/indicator/DT.DOD.DECT.CD?format=json&per_page=3&date=2022` → HTTP 200, real value (Zambia 28,423,406,214.6), `lastupdated: 2026-07-13`.

## CONCLUSION
**Works today:** (1) WGB `world-credit-ratings/` — free HTML, robots.txt permits. (2) TE `country-list/rating` — free HTML scrape, 167 countries. (3) FRED `BAMLEMCBPIOAS` — free daily CSV, EM corporate (not sovereign) OAS. (4) WB/IMF debt + CPIA/ICRG governance proxies — free, annual, low frequency.
**Dead ends:** TE `guest:guest` API (410, permanently gone); all three agencies' RSS (soft-404/403); SEC NRSRO bulk (2015 only); FRED EMBI (does not exist); any official WB/IMF rating column (does not exist). **No free, machine-readable, current sovereign rating or EMBI-equivalent spread feed exists.**
