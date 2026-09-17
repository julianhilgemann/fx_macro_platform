# Source verification: Infrastructure/Connectivity + Cost-of-Living/Health/Education

All checks run 2026-09-17 with `curl -sIL -o /dev/null -w "%{http_code} %{size_download} %{content_type}\n" -m 40 "<url>"`,
adding `-A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"` on 403.
HEAD returns `size_download 0`; sizes below come from real GETs / `Content-Length`.

---

## 1. Ookla Open Data (Speedtest) — VERIFIED

- **Access**: S3 bucket `ookla-open-data` (region `us-west-2`), anonymous, no key.
  - Verified key: `https://ookla-open-data.s3.us-west-2.amazonaws.com/parquet/performance/type=fixed/year=2025/quarter=2/2025-04-01_performance_fixed_tiles.parquet` → `200 binary/octet-stream`
  - **Key pattern confirmed exactly** as stated: `parquet/performance/type={fixed|mobile}/year=YYYY/quarter=Q/YYYY-MM-DD_performance_{fixed|mobile}_tiles.parquet`
  - **Mobile is `type=mobile`** — confirmed via ListBucket: `?list-type=2&prefix=parquet/performance/type%3Dmobile/year%3D2024/&delimiter=/` returns `quarter=1..4`.
  - **Latest available: 2025 Q4** for both types → `.../year=2025/quarter=4/2025-10-01_performance_fixed_tiles.parquet`
- **Size**: 2025 Q1 fixed file `Content-Length: 350077086` (~350 MB per quarter per type → ~2.8 GB/year).
- **Update cadence**: quarterly. 2025 Q1 file `Last-Modified: Thu, 03 Apr 2025` → **~1-quarter lag, not 2**.
- **Licence**: **CC BY-NC-SA 4.0** (string confirmed in the AWS Registry page body) — **NON-COMMERCIAL**. Attribution to Ookla required; Ookla trademarks used under licence.
- **Granularity**: zoom-16 tiles, quadkey keyed.
- **Global Index**: `https://www.speedtest.net/global-index` → `200 text/html` — HTML only.
- **Free country-level API**: **NONE**. Could not verify any free Ookla country API.
- **Pain points**: NC licence blocks commercial reuse; ~350 MB/quarter/type; S3 listing pagination.

## 2. ITU DataHub / ICT Development Index — PARTIAL

- `https://datahub.itu.int/` → **`202 text/html`** with browser UA (Cloudflare interstitial); plain curl → **`403`**.
- `https://datahub.itu.int/api/` → **403**; `https://datahub.itu.int/data/api/` → **403**. **No public free API verified.**
- Bulk XLSX verified: `https://www.itu.int/en/ITU-D/Statistics/Documents/facts/ITU_regional_global_Key_ICT_indicator_aggregates_Nov_2025.xlsx` → `200 application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` (aggregates only).
- **COULD NOT VERIFY** the country-level bulk file: `ITU_Key_2005-2025_ICT_Data.xlsx`, `..._2024_...`, `..._2023_...` all **404**.
- **Pain points**: Cloudflare-blocked, JS SPA, XLSX/PDF-only, undocumented API.

## 3. TeleGeography Submarine Cable Map — VERIFIED (both)

- `https://www.submarinecablemap.com/api/v3/cable/cable-geo.json` → `200 application/json`
- `https://www.submarinecablemap.com/api/v3/landing-point/landing-point-geo.json` → `200 application/json`
- **Licence: COULD NOT VERIFY.** No explicit open licence / terms page found. Default is all-rights-reserved; reuse legally unclear. Attribute TeleGeography.

## 4. Data centre / cloud region locations

- `https://raw.githubusercontent.com/jsonmaur/aws-regions/master/regions.json` → `200 text/plain` (JSON; `name`, `full_name`, `code`, `zones`).
- `https://ip-ranges.amazonaws.com/ip-ranges.json` → `200 application/json` (official, authoritative).
- `https://www.peeringdb.com/api/fac` → `200 application/json`; **free, no key**. `/tos` → 404, **licence COULD NOT VERIFY**.
- Azure: `https://azure.microsoft.com/en-us/explore/global-infrastructure/geographies/` → `200 text/html` (HTML only). Retail pricing API `https://prices.azure.com/api/retail/prices` → `405` on a bare call (needs `$filter`); no clean region JSON found.
- GCP: `https://cloud.google.com/compute/docs/regions-zones` → `200 text/html`. `https://cloudbilling.googleapis.com/v1/services` → `403` (needs OAuth key). **COULD NOT VERIFY machine-readable region feed.**
- Cloudflare: `https://www.cloudflare.com/network/` → `200 text/html` (no JSON DC list). `https://api.cloudflare.com/client/v4/ips` → `200` (edge IPs, not DC locations).
- `https://www.datacentermap.com/` → **`429`** on first request — scraping blocked/unreliable.
- **Free APIs**: PeeringDB (yes), ip-ranges.json (yes), aws-regions GitHub (yes). Azure/GCP/Cloudflare(datacenters)/datacentermap: no verified free machine-readable API.

## 5. Electricity

- **Ember**: base `https://api.ember-energy.org/v1/...` confirmed. Keyless GET returns `{"detail":"No API key set"}` → **free API key REQUIRED**. Signup: `https://ember-energy.org/data/api/` → `200`.
  Bulk CSV verified: `https://storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/yearly_full_release_long_format.csv` → `200 text/csv`.
- **IEA**: bulk data paywalled under the IEA data services licence; **no free IEA API verified**.
- **Eurostat — ALL THREE VERIFIED `200 application/json`**:
  - Household electricity `nrg_pc_204`, non-household electricity `nrg_pc_205`, gas `nrg_pc_202`.
  - Exact working call: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_pc_204?format=JSON&geo=DE&nrg_cons=KWH2500-4999` (also verified with `nrg_pc_202?nrg_cons=GJ_20-199` and `nrg_pc_205?nrg_cons=MWH500-1999`). No key.
- **Global free electricity-price source**: Eurostat is EU-only. For global retail prices there is **no strong free source**; Ember covers generation, not retail price.

## 6. Internet censorship / freedom

- **Freedom House Freedom on the Net**: `https://freedomhouse.org/report/freedom-net` → `200 text/html`. **No `.xlsx`/`.csv` links in the page** — HTML-only; machine-readable **COULD NOT VERIFY**. Guessed PDF URL → `404`. `https://freedomhouse.org/country/scores` → `200 text/html`.
- **OONI — no key CONFIRMED**: `https://api.ooni.io/api/v1/measurements?limit=1` → `200 application/json`. Aggregation endpoint verified: `https://api.ooni.io/api/v1/aggregation?probe_cc=IR&test_name=web_connectivity&since=2024-01-01&until=2024-02-01` → `200 application/json`.
- **Cloudflare Radar — token REQUIRED, confirmed**: bare call returns HTTP `400` with `{"success":false,"errors":[{"code":9106,"message":"Missing X-Auth-Key, X-Auth-Email or Authorization headers"}]}`. Base `https://api.cloudflare.com/client/v4/radar/...`. Free token signup `https://dash.cloudflare.com/sign-up` (`403` to curl — browser-only). `https://radar.cloudflare.com/` → `200`; `/traffic/datasets` → **403 to curl**. **Bulk S3/R2 download COULD NOT VERIFY.**

## 7. Numbeo API

- `https://www.numbeo.com/api/doc.jsp` → `200`. Key required: `https://www.numbeo.com/api/city_prices?api_key=demo&query=Berlin` → `{"error":"invalid api_key= demo"}` (HTTP 200 with error body).
- Free tier is non-commercial / attribution-bound; paid tiers are per-request credit packs.
- **Blunt**: licence prohibits redistributing or republishing raw values. **The free tier is NOT usable in a commercial data platform.** Only derived indices with a paid licence.

## 8. World Bank ICP / PPP conversion factors — VERIFIED

- `PA.NUS.PPP` — PPP conversion factor, GDP (LCU per international $): DEU 2023 = `0.701054` → `200`
- `PA.NUS.PRVT.PP` — PPP conversion factor, households & NPISH final consumption: DEU 2023 = `0.702414` → `200`
- `PA.NUS.FCRF` — official exchange rate (LCU per US$) → `200`
- **`PA.NUS.PPPC.RF` → 404 INVALID** ("indicator was not found… deleted or archived"). Do not use.
- Call: `https://api.worldbank.org/v2/country/DEU/indicator/PA.NUS.PPP?format=json&per_page=1&date=2023`
- ICP portal `https://www.worldbank.org/en/programs/icp/data` → `200`; bulk/portal `https://databank.worldbank.org/source/icp-2021` → `200` (API `source=16`). **ICP 2021 is the current round.**

## 9. WHO GHO OData — VERIFIED, no key

Base `https://ghoapi.azureedge.net/api/{CODE}`. All `200`:

| Code | Indicator |
|---|---|
| `WHOSIS_000002` | Healthy life expectancy (HALE) at birth |
| `WHOSIS_000001` | Life expectancy at birth |
| `UHC_INDEX_REPORTED` | UHC Service Coverage Index (SDG 3.8.1) |
| `FINPROTECTION_CATA_TOT_10_POP` | SDG 3.8.2 >10% household spend on health |
| `HRH_26` | Physicians density (per 1000 population) |
| `HWF_0001` | Medical doctors (per **10,000** — different unit) |
| `GHED_OOPSCHE_SHA2011` | Out-of-pocket % of current health expenditure |
| `SDGOOP` | OOP % of total expenditure on health |

- **`UHC_SCI_INDEX` → 404 INVALID.** Use `UHC_INDEX_REPORTED`.
- **Pain point**: values are bundled strings, e.g. `"61.2 [60.7-61.8]"` — parsing required.

## 10. OECD Health — VERIFIED (one working pattern) + rate limits

- Working data call: `https://sdmx.oecd.org/public/rest/data/OECD.ELS.HD,DSD_SHA@DF_SHA,1.1/.?startPeriod=2020&endPeriod=2020&format=csvfilewithlabels` → `200`, **226,004,633 bytes for a single year**.
- Dataflow IDs (agency `OECD.ELS.HD`): `DSD_SHA@DF_SHA` v1.1 (Health expenditure and financing), `DSD_HEALTH_STAT@DF_HEALTH_STATUS`, `DSD_HEALTH_STAT@DF_LE` (Life expectancy), `DSD_HEALTH_STAT@DF_MORTALITY`, `DSD_HCQO@DF_HCQO`.
- **Rate-limit behaviour (pain point)**: `format=sdmx-json` / `format=json` → **406**, only `json-structure-2.0.0` accepted. An unfiltered `lastNObservations=1` request **timed out at 60 s** after three rapid requests. Space requests (`sleep 5`), always filter by period, expect 429/timeouts. Payloads are enormous.

## 11. UNESCO UIS — CRITICAL FINDING

- **The `indicators=` parameter is SILENTLY IGNORED.** `indicators=CR.1`, `indicators=LR.AG15T99` and `indicators=ZZZ.BOGUS` all return the **identical** payload (records with `indicatorId` `10403`/`10404`) with HTTP `200`. It fails silently — do not trust it.
- No key needed. Verified `200`: `https://api.uis.unesco.org/api/public/definitions/indicators` (5,063 indicators).
- Valid codes confirmed present in the definitions dump: `CR.1`, `LR.AG15T99`, `LR.AG15T24`, `X.PPP.FSGOV`.
- **Invalid**: `XGNP.FFN.FSGOV` (not in definitions).
- Bulk endpoint `https://api.uis.unesco.org/api/public/data/download?...` → **404, does not exist**. Swagger paths → 404.
- **Bulk download COULD NOT VERIFY** (page is JS-driven, no file links). Licence likely CC BY-SA but **unverified**.

## 12. OECD PISA — data VERIFIED, portal blocked

- Direct files all `200` (bypass the oecd.org 403): `https://webfs.oecd.org/pisa2022/STU_QQQ_SPSS.zip`, `STU_QQQ_SAS.zip`, `SCH_QQQ_SPSS.zip`, `TCH_QQQ_SPSS.zip`, `STU_COG_SPSS.zip`.
- Plain `STU_QQQ.csv` → 404: **CSV is not published, SPSS/SAS only**.
- Portal `https://www.oecd.org/en/data/datasets/pisa-2022-database.html` → **403 to curl** (browser-only).
- Free; OECD terms, non-commercial with attribution. **PISA SDMX dataflow COULD NOT VERIFY.**

## 13. IHME Global Burden of Disease

- `https://ghdx.healthdata.org/gbd-results-tool` → `200`; `https://vizhub.healthdata.org/gbd-results/` → `200`.
- **Registration REQUIRED** (free) for GBD Results Tool extracts. **No public REST API verified** (`api.healthdata.org` did not resolve → `000`).
- Free GHDx bulk route exists but is a manual request flow.
- **Licence: CC BY-NC 4.0** — non-commercial. Effectively paywalled for a commercial product.

## 14. Mercer / EIU liveability — paywalled

- Mercer Cost of Living: `mobilityexchange.mercer.com` (paid). EIU Global Liveability Index: `eiu.com/n/campaigns/global-liveability-index` (paid). No free data.
- **Best free proxies**:
  - **Numbeo** (see §7 — free tier not commercial-safe).
  - **OECD Better Life Index — dataflow VERIFIED**: `DSD_HSL@DF_HSL_CWB` (agency `OECD.WISE.WDP`, "Current well-being"), plus `DSD_HSL@DF_HSL_CWB_INEQ`. Call: `https://sdmx.oecd.org/public/rest/data/OECD.WISE.WDP,DSD_HSL@DF_HSL_CWB,1.0/.?format=csvfilewithlabels`.
  - **UNDP HDI bulk — VERIFIED `200`**: `https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Statistical_Annex_HDI_Table.xlsx` (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`); page `https://hdr.undp.org/data-center/documentation-and-downloads` → `200`. Licence **CC BY 3.0 IGO**.

---

## Explicitly NOT verified

ITU country-level bulk XLSX · TeleGeography licence/terms · PeeringDB licence · Azure & GCP machine-readable region feeds · Cloudflare Radar bulk S3/R2 dataset · Freedom House machine-readable data · UIS bulk download and `indicators` filtering · OECD PISA SDMX dataflow.

## Commercial-use red flags

Ookla (CC BY-NC-SA 4.0) · IHME GBD (CC BY-NC 4.0) · Numbeo (no redistribution of raw values) · IEA bulk (paywalled).
