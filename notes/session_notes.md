# Session Notes — April 8, 2026

## Data Download Pipeline

- Reviewed `docs/variable_inventory.md` to identify all 7 data sources needed for the paper replication
- Went into planning mode and designed a full data download pipeline before writing any code
- Confirmed with user: `data/` gitignored, scripts guide on missing API keys, manual sources get a script + error message

## New Files Created

- `scripts/download_ipeds.py` — downloads Finance (FASB/GASB), Fall Enrollment, 12-Month Enrollment, HR/Staff, and Institutional Characteristics from NCES
- `scripts/download_peps.py` — downloads the PEPS closed schools database
- `scripts/download_scorecard.py` — downloads College Scorecard data via REST API
- `scripts/download_frc.py` — downloads FRC composite scores from studentaid.gov
- `scripts/download_bea.py` — downloads BEA county personal income and population via API
- `scripts/download_saipe.py` — downloads Census SAIPE county poverty rates via API
- `scripts/download_bls.py` — downloads BLS LAUS county unemployment rates via API
- `docs/data_sources.md` — per-source download instructions, API signup links, manual fallbacks
- `docs/human_work.md` — summary of what is automated vs. what requires human action, and what data engineering remains before replication
- `.env.example` — template for API keys

## Files Updated

- `pyproject.toml` — added `requests`, `python-dotenv`, `tqdm`, `openpyxl`, `xlrd`
- `Makefile` — added `download-ipeds`, `download-peps`, `download-scorecard`, `download-frc`, `download-bea`, `download-saipe`, `download-bls`, `download-all` targets
- `.gitignore` — added `data/` with `.gitkeep` exceptions to preserve directory structure
- `README.md` — added Quick Start section and summaries of all docs

## Bugs Found and Fixed

- **BLS series ID wrong**: generated 19-char IDs instead of 20-char — was using 7 zeros instead of 9 in the pattern `LAUCN{state}{county}000000000{measure}`. Fixed; BLS now returns data correctly.
- **IPEDS Finance URLs 404**: NCES releases Finance data with a 1-year lag (FY2022 data is in the `F2021_F1A.zip` file). Added fallback URL patterns for Finance (F1A, F2, F3) and 12-month enrollment (`EAP{year}` fallback). All now work.
- **BEA CSV write error**: some BEA rows contain an extra `NoteRef` field not present in all rows. Fixed by collecting all fieldnames across all rows before writing CSV.
- **PEPS URL 404**: `studentaid.gov/data-center/school/peps300` returns 404 — ED moved the file in 2024. Found working legacy URL at `ed.gov/sites/ed/files/offices/OSFAP/PEPS/docs/closedschoolsearch.xls`. Updated script and docs.
- **Wrong PEPS file**: user had manually downloaded a search-results export (8 recent closures) instead of the full historical database. Identified the issue, removed the bad file, downloaded the correct one.

## Data Successfully Downloaded

| Source | Records | Notes |
|---|---|---|
| SAIPE | 81,689 county-year rows | 1997–2022, all US counties |
| IPEDS | Verified for 2022 | Full 2002–2023 run still needed |
| BLS LAUS | 12,000 rows (test) | 50-county test; full run (~3,200 counties, ~15 min) still needed |
| PEPS | 19,758 closures | 1984–2023; 15,999 from 1996 onward |
| College Scorecard | 6,322 institutions | Latest snapshot; historical zip download still needed |
| BEA | 529,032 county-year rows | 1969–2022, personal income + population + per capita |

## Still Outstanding

- ~~**FRC composite scores**~~ — **Done** (2026-04-10). 16 files (frc_2006.xls through frc_2021.xls) manually downloaded and saved to `manual_data/frc/raw/`
- **IPEDS full run** — only 2022 was tested; run `make download-ipeds` for all years 2002–2023
- **BLS full run** — run `make download-bls` for all ~3,200 counties (~15 min)
- **College Scorecard historical data** — API returns latest snapshot only; full year-by-year data requires manual zip download from `collegescorecard.ed.gov/data/`

## Key Finding: What's Needed Before Replication

Completing data collection is not enough to replicate Tables 4 or 6. A data engineering phase is required first:

- **Table 4** (closure trends by sector): nearly ready once PEPS + IPEDS IC are in hand — straightforward groupby
- **Table 6** (feature importance from 5 models): requires full panel construction including:
  - IPEDS UnitID ↔ PEPS OPEID crosswalk
  - FASB vs. GASB Finance harmonization
  - Computing all derived variables (operating margin, DCOH, EBIDA, debt-to-assets, etc.)
  - Lags (L2–L5), rolling windows, YOY changes, CPI adjustment, log transforms, winsorization
  - Merging all sources into a single institution-year panel

---

## Table 4 Replication Attempt

### What Table 4 Contains
Trends in closures by institution type among colleges open in 1996. Six sector rows (public/nonprofit/for-profit × 2-year/4-year), showing count open in 1996 and % closed by 2006, 2016, 2023. Total: 6,411 institutions.

### New Files Created
- `scripts/replicate_table4.py` — full replication script for Table 4
- `data/raw/ipeds/hd_{2002..2023}.csv` — IPEDS institutional directory files downloaded for all years 2002–2023 (HD survey, contains sector, degree level, OPEID per institution)

### What We Learned
- **IPEDS HD (institutional directory) files** are the right source for sector and degree level — not the IC survey files downloaded earlier. HD has `sector` column (1-9 encoding public/nonprofit/for-profit × 4yr/2yr/<2yr), `opeid`, `iclevel`, `control`.
- **OPEID matching**: PEPS and IPEDS both use 8-digit OPEIDs. Must zero-pad to 8 chars (not strip leading zeros — some OPEIDs contain letters). Main campus = OPEID ending in `"00"`.
- **Logic confirmed correct**: public 2-year closure rate by 2006 matches the paper exactly (1.1%) once OPEID matching was fixed.
- **HD files only go back to 2002** on the NCES datacenter. The 1996 file requires manual download from [nces.ed.gov/ipeds/datacenter/DataFiles.aspx](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx) (select year 1995-96, Institutional Characteristics survey, save as `data/raw/ipeds/hd_1996.csv`).

### Why the Numbers Don't Match Yet
Without HD1996, the for-profit 2-year count is 189 (ours) vs 2,339 (paper) — because thousands of for-profit vocational schools closed between 1996 and 2002 and are missing from HD2002. The script automatically switches to the exact 1996 universe once `hd_1996.csv` is present.

### Bugs Fixed During Table 4 Work
- **OPEID stripping bug**: original script stripped leading zeros, which broke OPEIDs containing letters (e.g. `001055A1`). Fixed to zero-pad to 8 chars instead.
- **Main campus filter**: rewrote PEPS loader to filter on `opeid.endswith("00")` cleanly without re-reading the file.
