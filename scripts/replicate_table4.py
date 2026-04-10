"""
Replication of Table 4: Trends in Closures by Institution Type Among Colleges Open in 1996
Kelchen, Ritter & Webber (2025), FEDS 2025-003

Table 4 target:
    Sector              Open in 1996  Closed by 2006  Closed by 2016  Closed by 2023
    Public 4-year            778           0.3%            0.3%            0.3%
    Public 2-year          1,389           1.1%            1.6%            1.9%
    For-profit 4-year        332           1.8%           10.8%           24.1%
    For-profit 2-year      2,339          17.5%           29.4%           38.3%
    Nonprofit 4-year       1,715           1.7%            4.3%            7.3%
    Nonprofit 2-year         548          10.9%           18.1%           21.2%
    Total                  6,411           8.1%           12.7%           19.4%

Source: IPEDS, PEPS Closed School Reports, College Scorecard, 1996-2023.

METHODOLOGY NOTE:
    The paper uses institutions open in 1996, drawn from IPEDS 1996 data.
    IPEDS HD files on the NCES datacenter only go back to 2002; the 1996 file
    requires a manual download from https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx
    (select year 1995-96, Institutional Characteristics survey).

    This script uses two approaches:
      1. If data/raw/ipeds/hd_1996.csv exists (manual download): uses the exact 1996 universe
      2. Otherwise: reconstructs an approximate 1996 universe from HD2002 plus PEPS closures
         that occurred between 1996 and 2001 (institutions open in 1996 but gone by 2002).

    Sector codes in IPEDS HD (column: sector):
      1 = Public, 4-year or above
      2 = Public, 2-year
      3 = Public, less-than-2-year
      4 = Private nonprofit, 4-year or above
      5 = Private nonprofit, 2-year
      6 = Private nonprofit, less-than-2-year
      7 = Private for-profit, 4-year or above
      8 = Private for-profit, 2-year
      9 = Private for-profit, less-than-2-year
     99 = Sector unknown / not Title IV

    Table 4 groups:
      Public 4-year    = sector 1
      Public 2-year    = sector 2
      Nonprofit 4-year = sector 4
      Nonprofit 2-year = sector 5
      For-profit 4-year = sector 7
      For-profit 2-year = sector 8
      (sectors 3, 6, 9 = less-than-2-year; excluded from Table 4 like the paper)
"""

from pathlib import Path

import pandas as pd

# --- Paths ---
IPEDS_DIR = Path("data/raw/ipeds")
PEPS_FILE = Path("data/raw/peps/closedschoolsearch.xls")
OUTPUT_DIR = Path("analysis/replicated_tables")

# --- Sector mapping ---
SECTOR_LABELS = {
    1: "Public 4-year",
    2: "Public 2-year",
    4: "Nonprofit 4-year",
    5: "Nonprofit 2-year",
    7: "For-profit 4-year",
    8: "For-profit 2-year",
}
TABLE4_SECTORS = list(SECTOR_LABELS.keys())


def normalize_opeid(series: pd.Series) -> pd.Series:
    """Strip whitespace and zero-pad to 8 characters for consistent matching.

    Handles float representation (e.g. 2601100.0 from numeric CSV columns)
    by stripping trailing '.0' before zero-padding.
    """
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(8)
    )


def load_hd(year: int) -> pd.DataFrame:
    """Load IPEDS HD file for a given year. Returns DataFrame with unitid, opeid, sector.

    For 1996, checks for ic9697_a.csv (IPEDS 1996-97 IC Directory, covers fall 1996)
    and ic9596_a.csv (1995-96), in addition to the standard hd_1996.csv name.
    ic9697_a.csv is preferred — "open in 1996" means fall 1996 = 1996-97 survey year.

    NOTE on 1996 sector encoding: the ic9596_a.csv file uses a different sector
    numbering scheme than modern HD files (ordered by level-first rather than control-first).
    We rebuild sector from `control` + `iclevel` to produce modern HD-compatible codes.
    The paper also groups less-than-2-year (iclevel=3) schools into the 2-year category,
    so iclevel=3 is mapped to the 2-year sector (e.g. for-profit <2yr → sector 8).
    """
    if year == 1996:
        candidates = [
            IPEDS_DIR / "hd_1996.csv",
            IPEDS_DIR / "ic9697_a.csv",
            IPEDS_DIR / "ic9596_a.csv",
        ]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise FileNotFoundError(
                f"Missing 1996 IPEDS file. Expected one of: {[str(p) for p in candidates]}"
            )
        df = pd.read_csv(path, encoding="latin1", low_memory=False)
        df.columns = df.columns.str.lower()
        df["opeid"] = normalize_opeid(df["opeid"])
        df["control"] = pd.to_numeric(df["control"], errors="coerce")
        df["iclevel"] = pd.to_numeric(df["iclevel"], errors="coerce")
        # Remap iclevel=3 (less-than-2-year) to iclevel=2 (treat as 2-year, matching paper)
        iclevel_mapped = df["iclevel"].replace(3, 2)
        # Build modern sector code: control + iclevel → sector 1-9
        # (1,1)→1, (1,2)→2, (2,1)→4, (2,2)→5, (3,1)→7, (3,2)→8
        ctrl_icl_map = {
            (1, 1): 1, (1, 2): 2,
            (2, 1): 4, (2, 2): 5,
            (3, 1): 7, (3, 2): 8,
        }
        df["sector"] = [
            ctrl_icl_map.get((int(c), int(i)), 99)
            if pd.notna(c) and pd.notna(i) else 99
            for c, i in zip(df["control"], iclevel_mapped)
        ]
        # Main campus filter: OPEID ending in "00"
        df = df[df["opeid"].str.endswith("00")].copy()
    else:
        path = IPEDS_DIR / f"hd_{year}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing: {path}")
        df = pd.read_csv(path, encoding="latin1", low_memory=False)
        df.columns = df.columns.str.lower()
        df["opeid"] = normalize_opeid(df["opeid"])
        df["sector"] = pd.to_numeric(df["sector"], errors="coerce")
    return df[["unitid", "opeid", "instnm", "stabbr", "sector"]].copy()


def load_peps() -> pd.DataFrame:
    """Load PEPS closed schools file. Returns DataFrame with opeid and closed_date."""
    df = pd.read_excel(PEPS_FILE, engine="xlrd", header=30)
    df.columns = ["closed_date", "opeid", "school_name", "location", "address", "city", "state", "zip", "country"]
    df = df.dropna(subset=["opeid"])
    df["closed_date"] = pd.to_datetime(df["closed_date"].astype(str).str.strip(), errors="coerce")
    df = df.dropna(subset=["closed_date"])
    df["opeid"] = normalize_opeid(df["opeid"])
    # Keep only main campus closures: OPEID ends in "00" (branch code = 00)
    df = df[df["opeid"].str.endswith("00")]
    return df[["opeid", "closed_date", "school_name", "state"]].copy()


def build_1996_universe(peps: pd.DataFrame) -> pd.DataFrame:
    """
    Build approximate 1996 institution universe.
    Uses HD2002 as the base, then adds institutions from PEPS that closed
    between 1996 and 2001 (open in 1996 but missing from HD2002).
    Returns DataFrame with opeid and sector.
    """
    hd2002 = load_hd(2002)

    # Institutions in PEPS that closed 1996-2001 — open in 1996 but not in HD2002
    early_closures = peps[
        (peps["closed_date"].dt.year >= 1996) & (peps["closed_date"].dt.year <= 2001)
    ].copy()

    # Try to find sector for early closures from any available HD year (2002 won't have them)
    # Fall back to sector = -1 (unknown) if not found
    early_closures = early_closures[~early_closures["opeid"].isin(hd2002["opeid"])]
    early_closures["sector"] = -1  # unknown sector for pre-2002 closures
    early_closures["unitid"] = None
    early_closures["instnm"] = early_closures["school_name"]
    early_closures["stabbr"] = early_closures["state"]

    combined = pd.concat(
        [hd2002, early_closures[["unitid", "opeid", "instnm", "stabbr", "sector"]]],
        ignore_index=True,
    )
    return combined


def compute_table4(universe: pd.DataFrame, peps: pd.DataFrame, label: str) -> pd.DataFrame:
    """Compute Table 4 counts and closure rates."""
    cutoff_years = [2006, 2016, 2023]

    rows = []
    for sector_code, sector_label in SECTOR_LABELS.items():
        group = universe[universe["sector"] == sector_code]
        n_open = len(group)
        row = {"Sector": sector_label, "Open": n_open}

        for yr in cutoff_years:
            closed = peps[peps["closed_date"].dt.year <= yr]
            n_closed = group["opeid"].isin(closed["opeid"]).sum()
            row[f"Closed by {yr}"] = f"{100 * n_closed / n_open:.1f}%" if n_open > 0 else "—"
        rows.append(row)

    # Total row
    total_group = universe[universe["sector"].isin(TABLE4_SECTORS)]
    n_total = len(total_group)
    total_row = {"Sector": "Total", "Open": n_total}
    for yr in cutoff_years:
        closed = peps[peps["closed_date"].dt.year <= yr]
        n_closed = total_group["opeid"].isin(closed["opeid"]).sum()
        total_row[f"Closed by {yr}"] = f"{100 * n_closed / n_total:.1f}%" if n_total > 0 else "—"
    rows.append(total_row)

    df = pd.DataFrame(rows)
    print(f"\n{'='*70}")
    print(f"Table 4 Replication — {label}")
    print(f"{'='*70}")
    print(df.to_string(index=False))

    # Save to analysis/replicated_tables/
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "replicated_table4.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")
    return df


def main():
    print("Loading PEPS closed schools...")
    peps = load_peps()
    print(f"  {len(peps):,} main-campus closures loaded (1996+ filter applied below)")

    # --- Approach 1: Use HD1996 / ic9596_a.csv if present ---
    hd1996_path = next(
        (p for p in [IPEDS_DIR / "hd_1996.csv", IPEDS_DIR / "ic9697_a.csv", IPEDS_DIR / "ic9596_a.csv"] if p.exists()),
        None,
    )
    if hd1996_path is not None:
        print("\nUsing HD1996 (exact 1996 universe)...")
        universe_1996 = load_hd(1996)
        universe_1996 = universe_1996[universe_1996["sector"].isin(TABLE4_SECTORS)]
        peps_from_1996 = peps[peps["closed_date"].dt.year >= 1996]
        compute_table4(universe_1996, peps_from_1996, "Exact 1996 universe (HD1996)")
    else:
        print("\nHD1996 not found — using HD2002 + PEPS 1996-2001 as approximate 1996 universe.")
        print("To use the exact 1996 universe:")
        print("  1. Go to https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx")
        print("  2. Select year 1995-96, Institutional Characteristics survey")
        print("  3. Download and save as data/raw/ipeds/hd_1996.csv")

        # --- Approach 2: Approximate 1996 universe from HD2002 ---
        print("\nBuilding approximate 1996 universe from HD2002 + PEPS 1996-2001 closures...")
        universe_approx = build_1996_universe(peps)
        universe_approx_filtered = universe_approx[universe_approx["sector"].isin(TABLE4_SECTORS)]
        peps_from_1996 = peps[peps["closed_date"].dt.year >= 1996]

        n_unknown = (universe_approx["sector"] == -1).sum()
        if n_unknown > 0:
            print(f"  Note: {n_unknown} pre-2002 closures have unknown sector and are excluded from sector rows.")

        compute_table4(universe_approx_filtered, peps_from_1996, "Approximate 1996 universe (HD2002 + PEPS 1996-2001)")

    print("\n\nPaper targets (Table 4):")
    paper = pd.DataFrame([
        {"Sector": "Public 4-year",     "Open": 778,   "Closed by 2006": "0.3%",  "Closed by 2016": "0.3%",  "Closed by 2023": "0.3%"},
        {"Sector": "Public 2-year",     "Open": 1389,  "Closed by 2006": "1.1%",  "Closed by 2016": "1.6%",  "Closed by 2023": "1.9%"},
        {"Sector": "For-profit 4-year", "Open": 332,   "Closed by 2006": "1.8%",  "Closed by 2016": "10.8%", "Closed by 2023": "24.1%"},
        {"Sector": "For-profit 2-year", "Open": 2339,  "Closed by 2006": "17.5%", "Closed by 2016": "29.4%", "Closed by 2023": "38.3%"},
        {"Sector": "Nonprofit 4-year",  "Open": 1715,  "Closed by 2006": "1.7%",  "Closed by 2016": "4.3%",  "Closed by 2023": "7.3%"},
        {"Sector": "Nonprofit 2-year",  "Open": 548,   "Closed by 2006": "10.9%", "Closed by 2016": "18.1%", "Closed by 2023": "21.2%"},
        {"Sector": "Total",             "Open": 6411,  "Closed by 2006": "8.1%",  "Closed by 2016": "12.7%", "Closed by 2023": "19.4%"},
    ])
    print(paper.to_string(index=False))


if __name__ == "__main__":
    main()
