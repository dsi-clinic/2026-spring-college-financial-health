# Data Collection: Human Work Required

Summary of which data sources are fully automated vs. require manual steps.
Run `make download-all` to kick off everything that is automated.

---

## Status by Source

| Source | Works? | What you need to do |
|---|---|---|
| **SAIPE** (Census poverty) | Fully automated | Nothing — `make download-saipe` just works |
| **IPEDS** (enrollment, HR, finance, IC) | Fully automated | Nothing — `make download-ipeds` works. Finance files lag 1 year (e.g. FY2022 data is in the FY2021 file); the script handles this automatically |
| **BLS LAUS** (unemployment) | Fully automated | Nothing for a test run. Full run (~3,200 counties) takes ~15 min |
| **College Scorecard** (HCM, sector) | Needs API key | 5 min: sign up at [api.data.gov/signup](https://api.data.gov/signup/), add `SCORECARD_API_KEY=...` to `.env` |
| **BEA** (county income/population) | Needs API key | 5 min: sign up at [apps.bea.gov/api/signup](https://apps.bea.gov/api/signup/), add `BEA_API_KEY=...` to `.env` |
| **PEPS** (closed schools) | Fully automated | Nothing — `make download-peps` now works via legacy ed.gov URL (19,758 closures back to 1984) |
| **FRC** (composite scores) | Manual required | Download year-by-year Excel files (2006–2020) from [studentaid.gov/data-center/school/composite-scores](https://studentaid.gov/data-center/school/composite-scores), save as `data/raw/frc/frc_{year}.xlsx` |

---

## What Needs Human Work

### Free API Keys (5 min each)

1. **College Scorecard** — [api.data.gov/signup](https://api.data.gov/signup/)
   - Fill out the form, key arrives by email instantly
   - Add `SCORECARD_API_KEY=your_key` to `.env`
   - Then run `make download-scorecard`

2. **BEA** — [apps.bea.gov/api/signup](https://apps.bea.gov/api/signup/)
   - Register with your email, key arrives by email
   - Add `BEA_API_KEY=your_key` to `.env`
   - Then run `make download-bea`

### Manual Downloads (no script can do this)

3. **FRC composite scores**
   - Go to [studentaid.gov/data-center/school/composite-scores](https://studentaid.gov/data-center/school/composite-scores)
   - Download one Excel file per year for 2006–2020
   - Save each as `data/raw/frc/frc_{year}.xlsx` (e.g. `frc_2015.xlsx`)
   - Note: FRC covers private institutions only (~37% of never-closed institutions have this data)

---

## Summary

- **4 sources**: zero work, run immediately (`make download-all` handles them)
- **2 sources**: 5-minute free API key signup, then fully automated
- **1 source**: manual download from studentaid.gov required (FRC composite scores only)

---

## What Comes After Data Collection

Completing the human work above gets all raw data in place, but there is a significant data engineering layer before any table can be replicated.

### Table 4 — Trends in Closures by Institution Type

**Can start almost immediately** once PEPS is downloaded. Table 4 counts closures by sector (public/nonprofit/for-profit, 2-year/4-year) over time. It only needs:
- PEPS (manual download above)
- IPEDS Institutional Characteristics (already automated)

This is a straightforward groupby once the data is in hand.

### Table 6 — Feature Importance from Predictive Models

**Not yet — raw data alone is not enough.** Even with all sources downloaded, the following data engineering work is required first:

1. **IPEDS–PEPS crosswalk** — IPEDS uses `UnitID`, PEPS uses `OPEID`. These don't map 1-to-1. NCES publishes a crosswalk file that must be applied to link the two datasets.

2. **FASB vs. GASB Finance harmonization** — Public institutions report under GASB (F2 files), private institutions under FASB (F1A/F3 files). The same concepts (e.g. "total revenue") live in different columns across these formats and must be reconciled into unified variables.

3. **Derived variables** — None of the key model inputs exist in the raw files. Everything must be computed:
   - Operating margin = (total revenue − total expenses) / total revenue
   - Days cash on hand (DCOH)
   - EBIDA (earnings before interest, depreciation, amortization)
   - Debt-to-assets (leverage)
   - Unrestricted net assets
   - Revenue and expense share ratios (tuition %, instructional %, etc.)

4. **Lags and rolling windows** — L2/L3/L4/L5 lags for most variables; YOY percent changes; 5-year rolling max for enrollment/revenue decline flags; 3-of-5-year persistent negative margin; 3 consecutive years of >5% enrollment drops.

5. **CPI adjustment** — All dollar values must be deflated to 2023 dollars before computing ratios or changes.

6. **Panel construction** — All sources must be merged into a single institution-year panel (~110,000 never-closed observations + ~1,263 closed observations).

**The next milestone after finishing data collection is a set of data processing scripts** — one per source to clean and standardize, then a merge/build script to construct the panel. That is what unlocks both tables.
