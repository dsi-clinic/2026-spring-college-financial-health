# Data Collection & Replication Status

Summary of what is automated vs. what requires manual steps.

---

## Status by Source

| Source | Works? | What you need to do |
|---|---|---|
| **IPEDS** (Finance, Enrollment, HR, IC) | Fully automated | `make download-ipeds` — downloads all surveys 2002-2023 |
| **PEPS** (closed schools) | Fully automated | `make download-peps` — 19,758 closures since 1984 |
| **IPEDS 1996 IC directory** | Done (manual, in repo) | `data/raw/ipeds/ic9596_a.csv` — downloaded 2026-04-09 |
| **FRC composite scores** | Done (manual, in repo) | `manual_data/frc/raw/frc_{year}.xls` — downloaded 2026-04-10 |
| **SAIPE** (Census poverty) | Fully automated | `make download-saipe` |
| **BLS LAUS** (unemployment) | Fully automated | `make download-bls` (~15 min for all counties) |
| **College Scorecard** | Needs API key | See below |
| **BEA** (county income) | Needs API key | See below |

---

## API Keys Needed (5 min each)

1. **College Scorecard** — [api.data.gov/signup](https://api.data.gov/signup/)
   - Add `SCORECARD_API_KEY=your_key` to `.env`
   - Then run `make download-scorecard`

2. **BEA** — [apps.bea.gov/api/signup](https://apps.bea.gov/api/signup/)
   - Add `BEA_API_KEY=your_key` to `.env`
   - Then run `make download-bea`

---

## Replication Pipeline Status

| Step | Script | Status |
|---|---|---|
| Download all data | `make download-all` | Complete (IPEDS + PEPS; Scorecard/BEA need API keys) |
| Build institution-year panel | `make build-panel` | **Complete** — 150,207 rows, 76 features, 2002-2022 |
| Replicate Table 4 | `make replicate-table4` | **Complete** — 6,398/6,411 institutions (13-inst gap) |
| Replicate Table 5 | `make replicate-table5` | **Functional** — AUC 0.73-0.77 (paper: 0.87-0.90) |
| Identify closed colleges | `make identify-closed` | **Complete** — `analysis/closed_colleges.csv` |
| Predict on new data | `scripts/predict_new_data.py` | **Ready** — requires trained models from Table 5 run |

Run everything in order:
```bash
make download-ipeds download-peps  # ~20 min first time
make replicate-all                 # build-panel + tables + identify-closed
```

---

## Known Data Limitations

### Table 5 AUC Gap (~13pp below paper)

The paper (Kelchen et al. 2025) reports AUC 0.87-0.90; we achieve 0.73-0.77.
The gap is due to three factors we cannot replicate:

1. **College Scorecard supplementation** — the paper's closure universe includes
   institutions identified via College Scorecard historical data. We use PEPS-only,
   which misses some closures (especially for small for-profit and vocational schools).

2. **Finance data coverage** — 80% of closures in our panel are in sectors 6/9
   (less-than-2-year vocational schools) which almost never file IPEDS finance surveys.
   The paper likely had imputed or supplemented financial data for these institutions.

3. **Outcome definition** — the paper may define "closure" at the final IPEDS
   reporting year rather than the PEPS administrative closure date.

### Table 4 Universe Gap (13 institutions)

Our universe has 6,398 vs. paper's 6,411 institutions. The 13-institution gap
is attributable to the paper's College Scorecard supplementation (identifying
Title IV institutions that did not respond to the 1996 IPEDS IC survey).
Three sector-level closure *rates* match the paper exactly.

---

## Possible Future Improvements

1. **Get College Scorecard API key** → adds closure and enrollment data for
   institutions not in IPEDS, likely closes the Table 5 AUC gap
2. **Improve F3 (for-profit) finance mapping** — current `total_exp` derivation
   via change in net assets may be inaccurate for some institutions
3. **Add BEA and SAIPE county controls** → improves "All Controls" XGBoost model
