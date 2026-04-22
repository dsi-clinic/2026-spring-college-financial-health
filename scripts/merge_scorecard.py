"""
Extract enrollment and financial proxy data from College Scorecard historical bulk files.

Source: data/raw/scorecard/historical/College_Scorecard_Raw_Data_03232026.zip
Output: data/raw/scorecard/scorecard_panel.parquet

Each Scorecard MERGED{Y}_{Y+1}_PP.csv maps to IPEDS year Y.
Columns extracted per institution-year:
  unitid       IPEDS unit ID (merge key)
  year         IPEDS-equivalent year (MERGED{Y}_{Y+1} → year=Y)
  sc_enroll    Undergrad headcount (UGDS)
  sc_tuitfte   Tuition revenue per FTE (TUITFTE) — financial proxy
  sc_inexpfte  Instructional expenditure per FTE (INEXPFTE) — financial proxy
  sc_pctpell   Share of students receiving Pell grants (PCTPELL)
"""

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ZIP_PATH = Path("data/raw/scorecard/historical/College_Scorecard_Raw_Data_03232026.zip")
OUT_PATH = Path("data/raw/scorecard/scorecard_panel.parquet")

PANEL_YEARS = list(range(2002, 2023))

# Columns to extract from each MERGED file
SC_COLS = {
    "UNITID":    "unitid",
    "UGDS":      "sc_enroll",
    "TUITFTE":   "sc_tuitfte",
    "INEXPFTE":  "sc_inexpfte",
    "PCTPELL":   "sc_pctpell",
}

NA_VALUES = {"NA", "NULL", "PrivacySuppressed", ""}


def scorecard_filename(year: int) -> str:
    """Map IPEDS year Y to Scorecard filename MERGED{Y}_{Y+1 mod 100:02d}_PP.csv."""
    return f"MERGED{year}_{(year + 1) % 100:02d}_PP.csv"


def load_year(zf: zipfile.ZipFile, year: int) -> pd.DataFrame:
    fname = scorecard_filename(year)
    if fname not in zf.namelist():
        print(f"  {year}: {fname} not in zip — skipping")
        return pd.DataFrame()

    with zf.open(fname) as f:
        df = pd.read_csv(
            io.TextIOWrapper(f, encoding="latin1"),
            usecols=list(SC_COLS.keys()),
            low_memory=False,
            na_values=list(NA_VALUES),
            keep_default_na=False,
        )

    df = df.rename(columns=SC_COLS)
    df["year"] = year
    df["unitid"] = pd.to_numeric(df["unitid"], errors="coerce").astype("Int64")
    for col in ["sc_enroll", "sc_tuitfte", "sc_inexpfte", "sc_pctpell"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Rows with no unitid are unusable
    df = df.dropna(subset=["unitid"])
    # Drop rows where enrollment is clearly erroneous (negative)
    df.loc[df["sc_enroll"] < 0, "sc_enroll"] = np.nan

    n = len(df)
    n_enroll = df["sc_enroll"].notna().sum()
    n_tuit = df["sc_tuitfte"].notna().sum()
    print(f"  {year}: {n:,} institutions  sc_enroll={n_enroll:,}  sc_tuitfte={n_tuit:,}")
    return df


def main():
    if not ZIP_PATH.exists():
        raise FileNotFoundError(
            f"Scorecard zip not found: {ZIP_PATH}\n"
            "Download from https://collegescorecard.ed.gov/data/ → All Data Files"
        )

    print(f"Reading {ZIP_PATH.name}...")
    frames = []
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for year in PANEL_YEARS:
            df = load_year(zf, year)
            if not df.empty:
                frames.append(df)

    if not frames:
        raise RuntimeError("No Scorecard data extracted — check zip contents")

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["unitid", "year"]).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT_PATH, index=False)

    print(f"\nSaved: {OUT_PATH}")
    print(f"  Rows: {len(panel):,}")
    print(f"  Years: {panel['year'].min()}–{panel['year'].max()}")
    print(f"  Unique institutions: {panel['unitid'].nunique():,}")
    print(f"  sc_enroll coverage: {panel['sc_enroll'].notna().mean():.1%}")
    print(f"  sc_tuitfte coverage: {panel['sc_tuitfte'].notna().mean():.1%}")
    print(f"  sc_inexpfte coverage: {panel['sc_inexpfte'].notna().mean():.1%}")
    print(f"  sc_pctpell coverage: {panel['sc_pctpell'].notna().mean():.1%}")


if __name__ == "__main__":
    main()
