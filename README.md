# 2026-spring-college-financial-health

Replication of *Predicting College Closures and Financial Distress* by Robert Kelchen, Dubravka Ritter, and Douglas Webber (FEDS 2025-003).

## Current Status

| Task | Status |
|---|---|
| Table 4 — Closure trends by sector (1996–2023) | **Complete** — 6,398/6,411 institutions matched (13-inst gap from College Scorecard supplementation) |
| Panel construction (institution-year, 2002–2022) | **Complete** — 150,207 rows, 76 features |
| Table 5 — Predictive accuracy (AUC by model type) | **Functional** — AUC 0.73–0.77 vs paper 0.87–0.90; gap due to data access differences |
| Model packaging for external use | Complete — `scripts/predict_new_data.py` |
| Identify already-closed colleges | Complete — `analysis/closed_colleges.csv` |

## Quick Start

```bash
make install          # install dependencies (uv)
make download-ipeds   # download IPEDS surveys (2002–2023, ~20 min)
make download-peps    # download PEPS closed school list
python scripts/replicate_table4.py   # replicate Table 4
python scripts/build_panel.py        # build institution-year panel
python scripts/replicate_table5.py   # replicate Table 5 (requires panel)
```

## Repository Structure

```
scripts/
  download_ipeds.py       Download IPEDS surveys (Finance F1A/F2/F3, Enrollment, HR, IC)
  replicate_table4.py     Table 4: closure trends by sector since 1996
  build_panel.py          Build institution-year panel with financial/enrollment features
  replicate_table5.py     Table 5: AUC comparison across 6 model variants
  predict_new_data.py     Apply fitted XGBoost model to new institution data
  identify_closed_colleges.py  Export list of already-closed institutions

data/raw/
  ipeds/                  IPEDS survey CSVs (downloaded by scripts)
  peps/                   PEPS closed school list
  ipeds/ic9596_a.csv      IPEDS 1995-96 IC directory (needed for Table 4)

analysis/
  panel/institution_year_panel.parquet   Main analysis panel
  replicated_tables/                     Output tables (CSV)
  closed_colleges.csv                    Already-closed institutions
  models/                                Fitted XGBoost model files

docs/
  variable_inventory.md     Complete variable catalog with sources and transformations
  data_sources.md           Download instructions for all data sources
  table4_replication.md     Methodology notes and output for Table 4
  table5_replication.md     Methodology notes, AUC results, and gap analysis for Table 5
  human_work.md             What requires manual steps vs. automation
```

## Data Sources

| Source | Coverage | Notes |
|---|---|---|
| IPEDS Finance (F1A/F2/F3) | 2002–2022 | Public=GASB(F2), NP=FASB(F1A), FP=FASB-corp(F3) |
| IPEDS Enrollment (12-mo) | 2002–2022 | Old format 2002–2011, new EAPCAT format 2012+ |
| IPEDS HD (Institutional Directory) | 2002–2022, +1995-96 | Sector, OPEID, state |
| PEPS (Closed Schools) | 1984–2024 | Main-campus closures only (OPEID ends in "00") |

## Documents

- **`docs/variable_inventory.md`** — Complete catalog of ~42 base variables with sources, transformations, and coverage notes
- **`docs/data_sources.md`** — Per-source download instructions and API key requirements
- **`docs/table4_replication.md`** — Table 4 output, paper comparison, and methodology
- **`docs/table5_replication.md`** — Table 5 AUC results, paper comparison, and gap analysis
- **`docs/human_work.md`** — Manual steps and API keys needed
