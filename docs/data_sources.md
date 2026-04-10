# Data Sources: Download Status and Instructions

Reference: Kelchen, Ritter & Webber (2025), FEDS 2025-003.
Variable inventory: `docs/variable_inventory.md`

Run `make download-all` to download all sources that have automated scripts.
Run `make help` to see all available commands.

---

## Quick Start

```bash
# 1. Install dependencies
make install

# 2. Set up API keys
cp .env.example .env
# Edit .env and add your API keys (see per-source instructions below)

# 3. Download everything
make download-all
```

---

## Source 1: IPEDS

| | |
|---|---|
| **Status** | Automated |
| **Make command** | `make download-ipeds` |
| **Script** | `scripts/download_ipeds.py` |
| **Output** | `data/raw/ipeds/` |
| **Years** | 2002–2023 |
| **API key needed** | No |

**What it downloads:**

| Survey | Description | IPEDS code |
|---|---|---|
| Finance (FASB) | Private nonprofit/for-profit financial statements | F{year}_F1A, F{year}_F3 |
| Finance (GASB) | Public institution financial statements | F{year}_F2 |
| Fall Enrollment | Enrollment by race, gender, level | EF{year}A |
| 12-Month Enrollment | Full-year enrollment counts | E12_{year} |
| Human Resources | Staff counts by type | S{year}_IS, S{year}_SIS |
| Institutional Characteristics | Sector, degree level, identifiers | IC{year} |

**Notes:**
- NCES hosts zip files at predictable URLs; no API key required.
- Some years may use slightly different naming conventions (e.g., `E12{year}` vs `E12_{year}`).
  If a file 404s, the script will report it. Use the manual fallback below.
- Finance data is split by accounting standard: FASB (private) vs GASB (public).

**Manual fallback:**
1. Go to https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx
2. Select the survey component and year
3. Download the zip, extract the CSV
4. Save to `data/raw/ipeds/{survey}_{year}.csv`

---

## Source 2: PEPS (Closed Schools)

| | |
|---|---|
| **Status** | Automated (with fallback) |
| **Make command** | `make download-peps` |
| **Script** | `scripts/download_peps.py` |
| **Output** | `data/raw/peps/closedschools.xlsx` |
| **Years** | 1996–2023 |
| **API key needed** | No |

**What it downloads:**
The PEPS closed school database: institutions that lost Title IV federal student aid eligibility (i.e., closed). Columns include OPEID, school name, state, and closure date.

**Notes:**
- The script tries several known Federal Student Aid URLs.
- The URL may change when ED updates the file; the script will print the failure clearly.
- PEPS data is matched to IPEDS via OPEID (institutions ending in "00" = main campus).

**Manual fallback:**
1. Go to https://studentaid.gov/data-center/school/peps300
   OR: https://www2.ed.gov/offices/OSFAP/PEPS/closedschools.html
2. Download the "Closed School Search" Excel file
3. Save to `data/raw/peps/closedschools.xlsx`

---

## Source 3: College Scorecard

| | |
|---|---|
| **Status** | Automated |
| **Make command** | `make download-scorecard` |
| **Script** | `scripts/download_scorecard.py` |
| **Output** | `data/raw/scorecard/scorecard_latest.json`, `scorecard_latest.csv` |
| **Years** | Latest snapshot + historical files (see below) |
| **API key needed** | **Yes** — `SCORECARD_API_KEY` in `.env` |

**Getting a key:**
1. Go to https://api.data.gov/signup/
2. Fill out the form (instant email with key)
3. Add `SCORECARD_API_KEY=your_key` to `.env`

**What it downloads:**
Institution-level fields including sector, predominant degree level, HCM2 status, OPEID, operating status.

**Notes:**
- The REST API returns the latest snapshot of all institutions (~7,000 records).
- For year-by-year historical data (2002–2023), download the full data files manually:
  1. Go to https://collegescorecard.ed.gov/data/
  2. Click "Download" → "All Data Files" → download the full zip
  3. Extract CSVs by year into `data/raw/scorecard/`
- HCM2 is the key accountability variable from the paper (Heightened Cash Monitoring Level 2).

---

## Source 4: FRC Composite Scores

| | |
|---|---|
| **Status** | Automated (with fallback) |
| **Make command** | `make download-frc` |
| **Script** | `scripts/download_frc.py` |
| **Output** | `manual_data/frc/raw/frc_{year}.xls` |
| **Years** | 2006–2021 |
| **Downloaded** | 2026-04-10 |
| **API key needed** | No |

**What it downloads:**
Financial Responsibility Composite (FRC) scores for private nonprofit and for-profit institutions. Scores range from -1.0 to 3.0; below 1.5 triggers additional scrutiny.

**Notes:**
- Per the paper: only ~37% of never-closed institutions and ~5% of closed institutions have FRC data.
- FRC applies only to private institutions (nonprofit and for-profit); public institutions are excluded.
- URL stability on studentaid.gov is uncertain; older years may have moved.

**Manual fallback:**
1. Go to https://studentaid.gov/data-center/school/composite-scores
   OR: https://catalog.data.gov/dataset/composite-scores-for-private-non-profit-and-proprietary-institutions
2. Download the Excel file for each year (2006–2021)
3. Save as `manual_data/frc/raw/frc_{year}.xls` (e.g., `frc_2015.xls`)

---

## Source 5: BEA County Data

| | |
|---|---|
| **Status** | Automated |
| **Make command** | `make download-bea` |
| **Script** | `scripts/download_bea.py` |
| **Output** | `data/raw/bea/bea_cainc1_all_counties.json`, `.csv` |
| **Years** | 1969–2022 (BEA county data starts at 1969, not 1967) |
| **API key needed** | **Yes** — `BEA_API_KEY` in `.env` |

**Getting a key:**
1. Go to https://apps.bea.gov/api/signup/
2. Register with your email (instant approval)
3. Add `BEA_API_KEY=your_key` to `.env`

**What it downloads:**
CAINC1 table: county-level personal income, population, and per capita personal income for all US counties.

**Notes:**
- Variable inventory lists 1967 as the start year, but BEA CAINC1 county data begins at 1969.
- The combined CSV has columns: series (personal_income / population / per_capita_personal_income), GeoFips, GeoName, TimePeriod, DataValue.

---

## Source 6: Census SAIPE

| | |
|---|---|
| **Status** | Automated |
| **Make command** | `make download-saipe` |
| **Script** | `scripts/download_saipe.py` |
| **Output** | `data/raw/saipe/saipe_{year}.json`, `saipe_all_years.csv` |
| **Years** | 1997–2022 |
| **API key needed** | No (optional key for higher rate limits) |

**Getting an optional key:**
1. Go to https://api.census.gov/data/key_signup.html
2. Add `CENSUS_API_KEY=your_key` to `.env`

**What it downloads:**
County-level poverty rate, number in poverty, and median household income from the Census Small Area Income and Poverty Estimates program.

**Notes:**
- No key required for up to 500 queries/day; the full 1997–2022 download uses ~26 queries.
- Variables: `SAEPOVRTALL_PT` (poverty rate), `SAEPOVALL_PT` (poverty count), `SAEMHI_PT` (median income).
- This is typically the first script to run to verify the setup since it needs no API key.

---

## Source 7: BLS LAUS

| | |
|---|---|
| **Status** | Automated |
| **Make command** | `make download-bls` |
| **Script** | `scripts/download_bls.py` |
| **Output** | `data/raw/bls/bls_laus_county_unemployment.json`, `.csv` |
| **Years** | 1990–2022 |
| **API key needed** | No (optional key for higher batch limits) |

**Getting an optional key:**
1. Go to https://www.bls.gov/developers/
2. Register for v2 API access
3. Add `BLS_API_KEY=your_key` to `.env`

**What it downloads:**
Annual average unemployment rate for all ~3,200 US counties (LAUS series ending in `03`).

**Notes:**
- Without a key: 25 series per batch (v1). With key: 50 series per batch (v2). The full download takes ~130 batches either way.
- The script gets county FIPS codes from the Census API automatically.
- Filter on `period == "M13"` (annual average) when merging with institution data.
- Test with `--limit-counties 50` to verify the script works before the full run.

---

## Summary: What Needs Work

| Source | Automated? | Key Required? | Known Issues |
|---|---|---|---|
| IPEDS | Yes | No | Some file names may vary by year; script reports failures |
| PEPS | Mostly | No | URL may change; manual fallback documented above |
| College Scorecard | Yes | Yes (free) | API gives latest snapshot; full historical = manual zip download |
| FRC Scores | Mostly | No | Older years (pre-2015) may have broken URLs |
| BEA | Yes | Yes (free) | County data starts 1969, not 1967 |
| SAIPE | Yes | No | Fully automated, good starting point |
| BLS LAUS | Yes | No | ~130 API batches; takes ~15 min without key |
