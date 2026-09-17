# Migration/Mobility Official Statistics — Verified Access Report
Verified 2026-09-17 via curl. `curl` default UA is blocked by UN/OECD — use a browser UA.

## 1. UN DESA International Migrant Stock 2024
- **Landing**: `https://www.un.org/development/desa/pd/content/international-migrant-stock` — 200 w/ browser UA; **403 w/ curl default UA** (CloudFront).
- **Bulk XLSX (all VERIFIED 200, MIME application/vnd.openxmlformats...sheet)**, prefix `https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/`:
  - `undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx` — 6,005,287 B (origin×destination matrix)
  - `undesa_pd_2024_ims_stock_by_sex_and_destination.xlsx` — 541,936 B
  - `undesa_pd_2024_ims_stock_by_sex_and_origin.xlsx` — 231,809 B
- **No CSV published** (page grepped for `.csv`: zero hits). XLSX only — pain point.
- **Years (verified from file bytes)**: 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2024. 8 points, NOT annual; no 2019/2021/2022/2023.
- **Coverage**: 233 countries/areas; by sex; origin AND destination. Doc code `POP/DB/MIG/Stock/Rev.2024`.
- **Licence**: CC BY 3.0 IGO (stated inside XLSX).
- **Data dictionary**: no standalone URL — dictionary is the `Migrant notes` sheet (67 rows) inside each XLSX. Standalone metadata URL **UNVERIFIED**.
- **UNPD dataportal API**: base `https://population.un.org/dataportalapi/api/v1/indicators` — 200, 86 indicators. **CRITICAL: contains NO migrant-stock indicator.** Only id 65 `TNetMigration` (Total net-migration) and 66 `TNetMigRT`. API root `/api/v1/` → 404. Data path `/api/v1/data/indicators/65?...` → **404 (UNVERIFIED)**. Migrant stock is **bulk-download only**.

## 2. OECD International Migration Outlook (IMO)
- Latest: *IMO 2025*, 49th ed., DOI `10.1787/ae26c893-en`.
- Landing `https://www.oecd.org/en/publications/international-migration-outlook-2025_ae26c893-en.html`; full report `.../full-report.html`; iLibrary `https://www.oecd-ilibrary.org/en/publications/international-migration-outlook-2025_ae26c893-en/full-report.html`.
- **All three return 403 (Cloudflare) to curl AND web_fetch → URLs UNVERIFIED by direct fetch**; existence corroborated via search index only. Chapter-level HTML is free-to-read; full PDF is subscription-gated.

## 3. OECD DIOC / IMD / SDMX
- **DIOC and DIOC-E no longer exist as separate dataflows** — searched all 1,548 dataflows across all agencies: zero DIOC hits. Absorbed into IMD.
- **SDMX base** `https://sdmx.oecd.org/public/rest/` — VERIFIED. **`format=json-structure-2.0.0` required** (`format=jsondata` → 406).
- Dataflow list: `https://sdmx.oecd.org/public/rest/dataflow/all/all/latest?format=json-structure-2.0.0` — 200, 10.4 MB.
- Migration dataflows (agency `OECD.ELS.IMD`, all v1.0): `DSD_MIG@DF_MIG` (International migration database), `DSD_MIG_F@DF_MIG_POPF` (foreign-born stocks), `DSD_MIG@DF_MIG_EMP_EDU`, `DSD_MIG@DF_MIG_NUP_SEX`, `DSD_MIG_INT@DF_MIG_INT_PER`/`_TEMP`. Also `OECD.CFE.EDS:DSD_REG_MIGRANT@DF_MIGR_STOCK`, `DSD_REG_DEMO@DF_MIGR_FLOW`.
- **VERIFIED data (200, real CSV)**:
  - `https://sdmx.oecd.org/public/rest/data/OECD.ELS.IMD,DSD_MIG@DF_MIG,1.0/all?format=csvfile` — 74,842,729 B
  - `https://sdmx.oecd.org/public/rest/data/OECD.ELS.IMD,DSD_MIG_F@DF_MIG_POPF,1.0/all?format=csvfile` — 16,081,764 B
- **Pain**: the classic `AGENCY,DSD,VER/DF` form → 404. Must use joined SDMX-3.0 ID `DSD_MIG@DF_MIG`.
- Dims: REF_AREA, CITIZENSHIP, FREQ, MEASURE, SEX, BIRTH_PLACE, EDUCATION_LEV, UNIT_MEASURE, TIME_PERIOD (POPF: BIRTH_COUNTRY).
- **MEASURE codes**: IMD = B11, B12, B13, B15, B16. POPF = B14 (foreign-born stock).
- Coverage 38 REF_AREA (OECD members), to 2024. **No API key.** `data-explorer.oecd.org` → 200 (deep-link UNVERIFIED).

## 4. Eurostat
- **VERIFIED 200** `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/<CODE>?format=JSON&lang=EN`:
  - `migr_pop1ctz` = Population on 1 Jan by age, sex and **citizenship** (dims: citizen) — upd 2026-08-10
  - `migr_pop3ctb` = Population on 1 Jan by age, sex and **country of birth** ← **the foreign-born dataset** — upd 2026-08-10
  - `migr_asyappctza` (asylum applicants) — upd 2026-09-03; `migr_resfirst` (first permits) — upd 2026-09-11; also `migr_reschange`, `migr_resvalid`, `migr_resfam`, `migr_resoth`.
- **404 — DO NOT EXIST**: `migr_pop8ctz`, `migr_resid` (`ERR_NOT_FOUND_4 ... not available for dissemination`), `migr_eirapctz`, `migr_resnew`.
- **`lfsa_pganws` = citizenship + labour status, NOT foreign-born** — the usual assumption is wrong.
- `migr_asypenctzm` → 413 (too large, must filter).
- **Bulk TSV VERIFIED**: `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/<CODE>?format=TSV&compressed=false` — `migr_pop1ctz` 72,970,303 B; `migr_pop3ctb` 67,295,551 B. SDMX 2.1 XML default also 200. No key.

## 5. US Census ACS foreign-born
- **MAJOR CORRECTION: an API key is now REQUIRED.** `acs1` (2023) and `acs5` (2022) both 302 → `https://api.census.gov/data/missing_key.html`: *"A valid key must be included with each data API request."* The "500 queries/day without a key" allowance is **no longer true**.
- Endpoint: `https://api.census.gov/data/{year}/acs/{acs1|acs5}?get=NAME,B05002_001E,B05002_013E&for=state:06&key=KEY`
- **Keyless-still-works**: metadata `https://api.census.gov/data/2023/acs/acs1/variables/B05002_001E.json` → **200** (verified).
- Tables: B05002 (Place of Birth by Nativity/Citizenship), B16005 (Nativity by Language), DP02 profile. B16005/DP02 exact variable codes **UNVERIFIED** (blocked by missing key).
