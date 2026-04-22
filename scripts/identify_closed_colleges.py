"""
Identify already-closed colleges from PEPS data.

Cross-references PEPS closed school list with the IPEDS panel to add institution
characteristics (name, state, sector, last enrollment year, last known enrollment).

Output: analysis/closed_colleges.csv

This file is useful for:
  1. Validating predictions — confirmed closed schools should have high predicted risk
  2. Cleaning predictions — exclude already-closed schools from willmycollegesurvive.com
  3. Understanding closure patterns — which sectors/states close most often
"""

from pathlib import Path

import pandas as pd

from utils import normalize_opeid

PEPS_FILE = Path("data/raw/peps/closedschoolsearch.xls")
PANEL_PATH = Path("analysis/panel/institution_year_panel.parquet")
OUTPUT_PATH = Path("analysis/closed_colleges.csv")

# IPEDS sector labels
SECTOR_LABELS = {
    0: "Administrative unit / non-degree",
    1: "Public 4-year", 2: "Public 2-year", 3: "Public <2yr",
    4: "Nonprofit 4-year", 5: "Nonprofit 2-year", 6: "Nonprofit <2yr",
    7: "For-profit 4-year", 8: "For-profit 2-year", 9: "For-profit <2yr",
    99: "Unknown/Not Title IV",
}


def load_peps() -> pd.DataFrame:
    df = pd.read_excel(PEPS_FILE, engine="xlrd", header=30)
    df.columns = ["closed_date", "opeid", "school_name", "location",
                  "address", "city", "state", "zip", "country"]
    df = df.dropna(subset=["opeid"])
    df["closed_date"] = pd.to_datetime(df["closed_date"].astype(str).str.strip(), errors="coerce")
    df = df.dropna(subset=["closed_date"])
    df["opeid"] = normalize_opeid(df["opeid"])
    df["closed_year"] = df["closed_date"].dt.year
    df["is_main_campus"] = df["opeid"].str.endswith("00")
    return df


def load_panel_summary() -> pd.DataFrame:
    """Load the panel and compute per-institution summary statistics."""
    _COLS = ["unitid", "opeid", "instnm", "stabbr", "sector", "year", "enroll"]
    panel = pd.read_parquet(PANEL_PATH, columns=_COLS)
    panel["opeid"] = normalize_opeid(panel["opeid"])
    panel = panel.sort_values("year")

    latest = (
        panel.groupby("unitid")
        .last()
        .reset_index()[_COLS]
    )
    latest = latest.rename(columns={
        "stabbr": "state_abbr",
        "year": "last_ipeds_year",
        "enroll": "last_enroll",
        "instnm": "inst_name",
    })

    first = (
        panel.groupby("unitid")["year"]
        .first()
        .reset_index()
        .rename(columns={"year": "first_ipeds_year"})
    )

    return latest.merge(first, on="unitid", how="left")


def main():
    print("Loading PEPS closed school list...")
    peps = load_peps()
    print(f"  {len(peps):,} total closures in PEPS")
    print(f"  {peps['is_main_campus'].sum():,} main-campus closures (OPEID ends in '00')")
    print(f"  Year range: {peps['closed_year'].min()} – {peps['closed_year'].max()}")

    main_campus = peps[peps["is_main_campus"]].copy()

    print("\nLoading IPEDS panel for institution characteristics...")
    panel_summary = load_panel_summary()
    print(f"  {len(panel_summary):,} unique institutions in panel (2002–2022)")

    # Merge PEPS closures with panel data
    closed = main_campus.merge(
        panel_summary[["opeid", "unitid", "inst_name", "state_abbr", "sector",
                       "first_ipeds_year", "last_ipeds_year", "last_enroll"]],
        on="opeid",
        how="left",
    )

    # Add sector label
    closed["sector_label"] = closed["sector"].map(SECTOR_LABELS).fillna("Unknown")

    # Reorder columns
    closed = closed[[
        "opeid", "unitid", "school_name", "inst_name", "state", "state_abbr",
        "sector", "sector_label",
        "closed_date", "closed_year",
        "first_ipeds_year", "last_ipeds_year", "last_enroll",
        "city", "zip", "country",
    ]].sort_values(["closed_year", "state", "school_name"])

    print(f"\n{len(closed):,} main-campus closures cross-referenced with IPEDS")

    # Summary by sector
    print("\nClosures by sector (main campus, in IPEDS panel):")
    in_panel = closed[closed["unitid"].notna()]
    print(f"  {len(in_panel):,} of {len(closed):,} closures matched to IPEDS")
    sector_counts = (
        in_panel.groupby("sector_label")["opeid"]
        .count()
        .sort_values(ascending=False)
        .reset_index()
    )
    sector_counts.columns = ["sector", "closures"]
    print(sector_counts.to_string(index=False))

    # Summary by decade
    print("\nClosures by decade:")
    decade_counts = (
        closed.assign(decade=(closed["closed_year"] // 10 * 10).astype("Int64"))
        .groupby("decade")["opeid"]
        .count()
        .reset_index()
    )
    decade_counts.columns = ["decade", "closures"]
    print(decade_counts.dropna().to_string(index=False))

    # Top 10 states by closures
    print("\nTop 10 states by main-campus closures (all years):")
    print(closed["state"].value_counts().head(10).to_string())

    # Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    closed.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")

    # Print recent closures (post-2020) for reference
    recent = closed[closed["closed_year"] >= 2020].sort_values("closed_date", ascending=False)
    if len(recent) > 0:
        print(f"\n{len(recent)} main-campus closures since 2020:")
        print(recent[["school_name", "state", "sector_label", "closed_year", "last_enroll"]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
