# 2026-spring-college-financial-health

The purpose of this repo is to replicate the paper *Predicting College Closures and Financial Distress* by Robert Kelchen, Dubravka Ritter, and Douglas Webber (FEDS 2025-003).

## Quick Start

```bash
make install        # install dependencies
cp .env.example .env  # add your API keys (see docs/human_work.md)
make download-all   # download all data sources
```

## Documents

### `docs/variable_inventory.md`
Complete catalog of every variable used in the paper — ~42 base variables expanding to 70+ with lags and transformations. For each variable: data source, raw vs. derived, transformations applied (lags, log, CPI adjustment, quartile bins), and data coverage notes. The authoritative reference for what needs to be built when constructing the analysis panel.

### `docs/data_sources.md`
Per-source download instructions for all 7 data sources (IPEDS, PEPS, College Scorecard, FRC, BEA, SAIPE, BLS LAUS). Covers what each script downloads, API key signup links, and manual fallback steps for sources that can't be fully automated.

### `docs/human_work.md`
Summary of what is automated vs. what requires human action. Tracks API key requirements, manual download steps, and what data engineering work remains before replication of Tables 4 and 6 can begin.

### `notes/2026_04_01.md`
Notes from the first project meeting (April 1, 2026). Includes the to-do list, prompting guidelines for Claude Code, and goals for the data collection phase.



