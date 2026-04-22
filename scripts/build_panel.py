"""
Build Institution-Year Panel for Table 5 Replication
Kelchen, Ritter & Webber (2025), FEDS 2025-003

Creates analysis/panel/institution_year_panel.parquet with one row per
institution-year covering 2002–2022, including:
  - Financial variables (operating margin, DCOH, debt, etc.)
  - Enrollment (12-month headcount)
  - Institutional characteristics (sector, state)
  - Closure outcomes (closed_in_year, closed_within_3yr)
  - L2 and L3 lagged versions of key financial/enrollment variables

IMPORTANT — IPEDS FILE LABEL INVERSION:
  The download script labels are inverted from standard NCES naming:
    finance_fasb_f1a_{year}.csv  →  PUBLIC institutions  (GASB accounting)
    finance_gasb_f2_{year}.csv   →  PRIVATE NONPROFIT    (FASB accounting)
    finance_fasb_f3_{year}.csv   →  FOR-PROFIT           (FASB corporate)
  This script loads each file and merges on control/sector from HD data
  rather than trusting the filename label.

CPI base year: 2022 (all dollar values adjusted to 2022 dollars).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from utils import normalize_opeid

# --- Paths ---
IPEDS_DIR = Path("data/raw/ipeds")
PEPS_FILE = Path("data/raw/peps/closedschoolsearch.xls")
SCORECARD_PATH = Path("data/raw/scorecard/scorecard_panel.parquet")
OUTPUT_DIR = Path("analysis/panel")

# --- Year range ---
PANEL_YEARS = list(range(2002, 2023))  # 2002–2022 (finance data available)

# --- CPI-U annual averages (base 1982-84=100), used for 2022-dollar adjustment ---
CPI_U = {
    2002: 179.9, 2003: 184.0, 2004: 188.9, 2005: 195.3,
    2006: 201.6, 2007: 207.3, 2008: 215.3, 2009: 214.5,
    2010: 218.1, 2011: 224.9, 2012: 229.6, 2013: 233.0,
    2014: 236.7, 2015: 237.0, 2016: 240.0, 2017: 245.1,
    2018: 251.1, 2019: 255.7, 2020: 258.8, 2021: 271.0,
    2022: 292.7,
}
CPI_BASE_YEAR = 2022  # all values adjusted to 2022 dollars

# --- Sector groupings ---
PUBLIC_SECTORS = [1, 2, 3]
NONPROFIT_SECTORS = [4, 5, 6]
FORPROFIT_SECTORS = [7, 8, 9]
PRIVATE_SECTORS = NONPROFIT_SECTORS + FORPROFIT_SECTORS  # for prediction model


# ---------------------------------------------------------------------------
# Finance column mappings
# ---------------------------------------------------------------------------
# finance_fasb_f1a = PUBLIC institutions (GASB accounting)
# Confirmed via data investigation (2022 file).
F1A_MAP = {
    # Each value is a single column or list of fallbacks (first found in file wins).
    "total_rev":         "f1a18",              # consistent across all years
    "total_exp":         ["f1a31", "f1c151"],  # f1a31 from 2008+; f1c151 pre-2008
    "rev_tuition":       "f1a01",
    "cash":              "f1b01",
    "sti":               "f1b02",
    # Long-term debt: split into current/non-current from 2008+; single column pre-2008
    "lt_debt_curr":      ["f1b04a", "f1b04"],  # use f1b04 as full proxy pre-2008
    "lt_debt_noncurr":   "f1b04b",             # absent pre-2008 → NaN (treated as 0)
    "total_assets":      "f1d01",
    "unrestricted_na":   "f1d04",              # unrestricted net position
    "exp_instr_op":      "f1c011",
    "exp_instr_nop":     "f1c012",
    "exp_scholar_op":    "f1c121",
    "exp_scholar_nop":   "f1c122",
    "exp_interest":      "f1c19in",            # available 2016+; absent earlier → NaN
    "exp_depreciation":  "f1c19dp",            # available 2016+; absent earlier → NaN
}

# finance_gasb_f2 = PRIVATE NONPROFIT institutions (FASB accounting)
# Confirmed via Harvard data investigation (2022 file).
F2_MAP = {
    "total_rev":         "f2a18",   # total revenues (confirmed: Harvard $5.87B)
    "total_exp":         "f2e131",  # total expenses (confirmed: Harvard $5.43B)
    "total_assets":      "f2a01",   # total assets (confirmed: Harvard $62B)
    "unrestricted_na":   "f2h01",   # net assets without donor restrictions
    "cash":              "f2d01",   # cash and cash equivalents
    "sti":               "f2d05",   # short-term investments
    "lt_debt":           "f2d16",   # long-term notes/bonds payable
    "exp_instr_nr":      "f2e011",  # instruction, without donor restrictions
    "exp_instr_wr":      "f2e012",  # instruction, with donor restrictions
    "exp_interest":      "f2e121",  # interest expense, without restrictions
    "exp_interest_wr":   "f2e122",  # interest expense, with restrictions
}

# finance_fasb_f3 = FOR-PROFIT institutions (FASB corporate accounting)
# Column semantics are messier for F3; mappings are best-guess from data inspection.
# f3a01 = total revenues (all sources incl. investment gains)
# Operating net income approximated as f3g05 - f3g01 (change in net assets/equity)
F3_MAP = {
    "total_rev":         "f3a01",   # total revenues (including non-operating)
    "rev_tuition":       "f3a01a",  # tuition and fees, gross
    "total_assets":      "f3d01",   # total assets
    "cash_sti":          "f3d02",   # cash + short-term investments
    "lt_debt":           "f3d03",   # long-term debt
    "exp_instruction":   "f3c01",   # instruction expense
    "exp_depreciation":  "f3c17",   # depreciation expense
    "exp_interest":      "f3c16",   # interest expense
    "net_assets_begin":  "f3g01",   # net assets at beginning of year
    "net_assets_end":    "f3g05",   # net assets at end of year
}


def load_hd(year: int) -> pd.DataFrame:
    """Load IPEDS HD file; return unitid, opeid, sector, stabbr, instnm."""
    path = IPEDS_DIR / f"hd_{year}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="latin1", low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    df["opeid"] = normalize_opeid(df["opeid"])
    df["sector"] = pd.to_numeric(df["sector"], errors="coerce")
    cols = ["unitid", "opeid", "instnm", "stabbr", "sector"]
    return df[[c for c in cols if c in df.columns]].copy()


def _load_finance_file(path: Path, col_map: dict) -> pd.DataFrame:
    """
    Load one finance CSV; return unitid + mapped canonical columns as float.

    col_map values may be a string (single column) or a list of strings (first
    found in the file wins — handles year-specific column name changes).
    """
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="latin1", low_memory=False)
    df.columns = df.columns.str.strip().str.lower()

    # Resolve col_map: for list values, pick the first candidate present in file
    resolved: dict[str, str] = {}  # canonical_name -> source_col
    for canonical, candidates in col_map.items():
        if isinstance(candidates, str):
            candidates = [candidates]
        for src in candidates:
            if src in df.columns:
                resolved[canonical] = src
                break  # use first found

    # Keep only unitid + resolved source columns
    src_cols = set(resolved.values())
    keep_cols = [c for c in df.columns if c == "unitid" or c in src_cols]
    df = df[keep_cols].copy()

    # Coerce to numeric
    for c in df.columns:
        if c != "unitid":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Rename source → canonical
    rename = {src: can for can, src in resolved.items()}
    df = df.rename(columns=rename)
    df["unitid"] = pd.to_numeric(df["unitid"], errors="coerce").astype("Int64")
    return df


def load_finance(year: int) -> pd.DataFrame:
    """
    Load and harmonize finance data for one year across all three survey types.
    Returns one row per institution with canonical column names.
    All dollar values are NOMINAL (CPI adjustment happens later in main()).
    """
    f1a = _load_finance_file(IPEDS_DIR / f"finance_fasb_f1a_{year}.csv", F1A_MAP)
    f2 = _load_finance_file(IPEDS_DIR / f"finance_gasb_f2_{year}.csv", F2_MAP)
    f3 = _load_finance_file(IPEDS_DIR / f"finance_fasb_f3_{year}.csv", F3_MAP)

    def _col(df: pd.DataFrame, col: str, default=0) -> pd.Series:
        """Get a column from df, returning a series of `default` if absent."""
        return df[col] if col in df.columns else pd.Series(default, index=df.index)

    # F1A: derive combined columns
    if not f1a.empty:
        f1a["cash_sti"] = _col(f1a, "cash") + _col(f1a, "sti")
        f1a["lt_debt"] = _col(f1a, "lt_debt_curr") + _col(f1a, "lt_debt_noncurr")
        f1a["exp_instruction"] = _col(f1a, "exp_instr_op") + _col(f1a, "exp_instr_nop")
        f1a["exp_scholarships"] = _col(f1a, "exp_scholar_op") + _col(f1a, "exp_scholar_nop")
        f1a = f1a.drop(columns=[c for c in ["cash", "sti", "lt_debt_curr", "lt_debt_noncurr",
                                              "exp_instr_op", "exp_instr_nop",
                                              "exp_scholar_op", "exp_scholar_nop"] if c in f1a.columns])

    # F2: derive combined columns
    if not f2.empty:
        f2["cash_sti"] = _col(f2, "cash") + _col(f2, "sti")
        f2["exp_instruction"] = _col(f2, "exp_instr_nr") + _col(f2, "exp_instr_wr")
        f2["exp_interest"] = _col(f2, "exp_interest", np.nan).fillna(0) + _col(f2, "exp_interest_wr").fillna(0)
        f2 = f2.drop(columns=[c for c in ["cash", "sti", "exp_instr_nr", "exp_instr_wr",
                                            "exp_interest_wr"] if c in f2.columns])

    # F3: derive total_exp from change in net assets (best approximation)
    if not f3.empty:
        na_begin = _col(f3, "net_assets_begin", np.nan)
        na_end = _col(f3, "net_assets_end", np.nan)
        f3["total_exp"] = _col(f3, "total_rev", np.nan) - (na_end - na_begin)
        f3 = f3.drop(columns=[c for c in ["net_assets_begin", "net_assets_end"] if c in f3.columns])

    # Stack all three files (one row per UNITID, no duplicates expected)
    frames = [df for df in [f1a, f2, f3] if not df.empty]
    if not frames:
        return pd.DataFrame(columns=["unitid"])
    fin = pd.concat(frames, ignore_index=True, sort=False)
    # Deduplicate: keep first occurrence (each institution appears in exactly one file)
    fin = fin.drop_duplicates(subset="unitid", keep="first")
    return fin


def load_enrollment(year: int) -> pd.DataFrame:
    """
    Load total student headcount enrollment. Returns DataFrame with unitid + enroll.

    Format changed in 2012:
      2012+: 12-month enrollment file, EAPCAT=10000 = total headcount
      2010–2011: fall enrollment file, EFTOTLT at EFALEVEL=1 = total headcount
      2002–2009: fall enrollment file, old format (EFRACE columns, sum by level)
                 — for now returns empty for these years (enrollment NaN)
    """
    _EMPTY_ENR = pd.DataFrame(columns=["unitid", "enroll"])

    # --- 2012+ new format ---
    if year >= 2012:
        path = IPEDS_DIR / f"enrollment_12mo_{year}.csv"
        if not path.exists():
            return _EMPTY_ENR
        df = pd.read_csv(path, encoding="latin1", low_memory=False)
        df.columns = df.columns.str.strip().str.lower()
        if "eapcat" not in df.columns:
            return _EMPTY_ENR
        total = df[df["eapcat"] == 10000][["unitid", "eaptot"]].copy()
        total = total.rename(columns={"eaptot": "enroll"})

    # --- 2010–2011: fall enrollment with EFTOTLT ---
    elif year >= 2010:
        path = IPEDS_DIR / f"fall_enrollment_{year}.csv"
        if not path.exists():
            return _EMPTY_ENR
        df = pd.read_csv(path, encoding="latin1", low_memory=False)
        df.columns = df.columns.str.strip().str.lower()
        if "eftotlt" not in df.columns or "efalevel" not in df.columns:
            return _EMPTY_ENR
        total = df[df["efalevel"] == 1][["unitid", "eftotlt"]].copy()
        total = total.rename(columns={"eftotlt": "enroll"})

    # --- 2002–2009: 12-month enrollment, old format ---
    # Older EAP files use FTPT/FUNCTCD/FSTAT structure.
    # FTPT=3 (total), FUNCTCD=10 (all students), FSTAT=0 (all status) → EAPTOT = total headcount
    else:
        path = IPEDS_DIR / f"enrollment_12mo_{year}.csv"
        if not path.exists():
            return _EMPTY_ENR
        df = pd.read_csv(path, encoding="latin1", low_memory=False)
        df.columns = df.columns.str.strip().str.lower()
        needed = {"ftpt", "functcd", "fstat", "eaptot", "unitid"}
        if not needed.issubset(df.columns):
            return _EMPTY_ENR
        total = df[
            (df["ftpt"] == 3) & (df["functcd"] == 10) & (df["fstat"] == 0)
        ][["unitid", "eaptot"]].copy()
        total = total.rename(columns={"eaptot": "enroll"})

    total["unitid"] = pd.to_numeric(total["unitid"], errors="coerce").astype("Int64")
    total["enroll"] = pd.to_numeric(total["enroll"], errors="coerce")
    return total


def load_peps() -> pd.DataFrame:
    """Load PEPS closed schools. Returns opeid + closed_year (integer)."""
    df = pd.read_excel(PEPS_FILE, engine="xlrd", header=30)
    df.columns = ["closed_date", "opeid", "school_name", "location",
                  "address", "city", "state", "zip", "country"]
    df = df.dropna(subset=["opeid"])
    df["closed_date"] = pd.to_datetime(df["closed_date"].astype(str).str.strip(), errors="coerce")
    df = df.dropna(subset=["closed_date"])
    df["opeid"] = normalize_opeid(df["opeid"])
    df = df[df["opeid"].str.endswith("00")]
    df["closed_year"] = df["closed_date"].dt.year
    return df[["opeid", "closed_year"]].drop_duplicates("opeid")


def cpi_deflator(year: int) -> float:
    """Return multiplier to convert nominal year-Y dollars to 2022 dollars."""
    return CPI_U[CPI_BASE_YEAR] / CPI_U.get(year, CPI_U[CPI_BASE_YEAR])


def load_scorecard() -> pd.DataFrame:
    """
    Load the pre-built Scorecard panel (from merge_scorecard.py).
    Returns empty DataFrame if the file doesn't exist.
    Columns: unitid, year, sc_enroll, sc_tuitfte, sc_inexpfte, sc_pctpell
    """
    if not SCORECARD_PATH.exists():
        print("  (Scorecard panel not found — run scripts/merge_scorecard.py first)")
        return pd.DataFrame(columns=["unitid", "year"])
    return pd.read_parquet(SCORECARD_PATH)


def build_panel() -> pd.DataFrame:
    """Assemble the full institution-year panel."""
    print("Loading PEPS closures...")
    peps = load_peps()
    peps_set = set(peps["opeid"])
    closed_year_map = dict(zip(peps["opeid"], peps["closed_year"]))
    print(f"  {len(peps_set):,} closed institutions in PEPS")

    print("Loading College Scorecard panel...")
    sc_panel = load_scorecard()
    sc_cols = ["unitid", "sc_enroll", "sc_tuitfte", "sc_inexpfte", "sc_pctpell"]
    has_scorecard = not sc_panel.empty
    if has_scorecard:
        print(f"  {len(sc_panel):,} Scorecard institution-year rows")

    rows = []
    for year in PANEL_YEARS:
        print(f"Year {year}...", end=" ", flush=True)
        hd = load_hd(year)
        fin = load_finance(year)
        enr = load_enrollment(year)

        if hd.empty:
            print("(HD missing, skip)")
            continue

        # Merge IPEDS sources
        df = hd.merge(fin, on="unitid", how="left")
        df = df.merge(enr, on="unitid", how="left")
        df["year"] = year

        # Merge Scorecard: supplement enrollment and add financial proxies
        if has_scorecard:
            sc_yr = sc_panel[sc_panel["year"] == year][
                [c for c in sc_cols if c in sc_panel.columns]
            ]
            df = df.merge(sc_yr, on="unitid", how="left")
            # Fill IPEDS enrollment gaps with Scorecard undergrad headcount
            df["enroll"] = df["enroll"].fillna(df["sc_enroll"])
        else:
            for col in sc_cols[1:]:  # skip unitid
                df[col] = np.nan

        # Closure status: has this institution ever appeared in PEPS?
        df["closed_year_peps"] = df["opeid"].map(closed_year_map)
        df["is_closed"] = df["opeid"].isin(peps_set)

        # Outcome 1: closed in this specific year
        df["closed_in_year"] = (df["closed_year_peps"] == year).astype("Int8")

        # Outcome 2: closed within 3 years (i.e., closed in year t, t+1, or t+2)
        df["closed_within_3yr"] = (
            (df["closed_year_peps"] >= year) & (df["closed_year_peps"] <= year + 2)
        ).astype("Int8")

        rows.append(df)
        print(f"{len(df):,} rows")

    panel = pd.concat(rows, ignore_index=True)
    panel = panel.sort_values(["unitid", "year"]).reset_index(drop=True)
    return panel


def add_derived_variables(panel: pd.DataFrame) -> pd.DataFrame:
    """Compute financial ratios and derived variables. CPI-adjust dollar columns first."""
    print("\nApplying CPI adjustment to 2022 dollars...")
    dollar_cols = [
        "total_rev", "total_exp", "rev_tuition", "cash_sti", "lt_debt",
        "total_assets", "unrestricted_na", "exp_instruction", "exp_scholarships",
        "exp_interest", "exp_depreciation",
        # Scorecard per-FTE dollar values (nominal → 2022 dollars)
        "sc_tuitfte", "sc_inexpfte",
    ]
    deflators = panel["year"].map(cpi_deflator)
    for col in dollar_cols:
        if col in panel.columns:
            panel[f"{col}_real"] = panel[col] * deflators

    print("Computing financial ratios...")
    nan = pd.Series(np.nan, index=panel.index)
    def sc(col): return panel.get(col, nan)  # safe column fetch with NaN default

    rev       = sc("total_rev_real")
    exp       = sc("total_exp_real")
    assets    = sc("total_assets_real")
    cash_sti  = sc("cash_sti_real")
    lt_debt   = sc("lt_debt_real")
    unrestr   = sc("unrestricted_na_real")
    tuition   = sc("rev_tuition_real")
    exp_instr = sc("exp_instruction_real")
    exp_schol = sc("exp_scholarships_real")
    exp_int   = sc("exp_interest_real")
    exp_dep   = sc("exp_depreciation_real")

    # Operating margin — guard zero revenue
    safe_rev = rev.replace(0, np.nan)
    panel["operating_margin"] = (rev - exp) / safe_rev

    # Days cash on hand: cash / (total_exp / 365) — guard zero expenses
    daily_exp = exp.replace(0, np.nan) / 365
    panel["dcoh"] = cash_sti / daily_exp

    # Debt ratios — guard zero denominators to avoid inf (common in sectors 6/9
    # where total_assets is reported as 0 rather than missing)
    safe_assets = assets.replace(0, np.nan)
    panel["debt_to_assets"] = (lt_debt / safe_assets).clip(0, 20)
    panel["unrestricted_na_ratio"] = unrestr / safe_assets

    # Revenue shares — guard zero revenue
    safe_rev = rev.replace(0, np.nan)
    panel["rev_share_tuition"] = tuition / safe_rev

    # Expense shares — guard zero expenses
    safe_exp = exp.replace(0, np.nan)
    panel["exp_share_instruction"] = exp_instr / safe_exp
    panel["exp_share_scholarships"] = exp_schol / safe_exp
    panel["exp_share_interest"] = exp_int / safe_exp
    panel["exp_share_depreciation"] = exp_dep / safe_exp

    # EBIDA = operating income + interest + depreciation + amortization
    # Using: EBIDA = (rev - exp) + exp_interest + exp_depreciation
    panel["ebida"] = (rev - exp) + exp_int.fillna(0) + exp_dep.fillna(0)
    safe_ebida = panel["ebida"].replace(0, np.nan)
    panel["debt_to_ebida"] = lt_debt / safe_ebida

    # Clip extreme ratios to [-5, 5] for operating margin, [0, 10] for DCOH
    panel["operating_margin"] = panel["operating_margin"].clip(-5, 5)
    panel["dcoh"] = panel["dcoh"].clip(0, 3650)  # max 10 years of cash

    return panel


def add_enrollment_changes(panel: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year enrollment change and rolling indicators."""
    print("Computing enrollment changes...")
    panel = panel.sort_values(["unitid", "year"])

    panel["enroll_prev"] = (
        panel.set_index(["unitid", "year"])
        .groupby("unitid")["enroll"]
        .shift(1)
        .values
    )
    panel["enroll_yoy"] = (panel["enroll"] - panel["enroll_prev"]) / panel["enroll_prev"]
    panel["enroll_yoy"] = panel["enroll_yoy"].clip(-1, 2)

    return panel


def add_lags(panel: pd.DataFrame, lag_cols: list[str], lags: list[int] = (2, 3)) -> pd.DataFrame:
    """Add lagged versions of specified columns (grouped by unitid)."""
    print(f"Adding lags {lags} for {len(lag_cols)} columns...")
    panel = panel.sort_values(["unitid", "year"])
    for col in lag_cols:
        if col not in panel.columns:
            continue
        for lag in lags:
            panel[f"{col}_l{lag}"] = panel.groupby("unitid")[col].shift(lag)
    return panel


def add_rolling_indicators(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Add binary rolling indicators:
      - rev_decline_10pct: revenue ≥10% below 5-yr rolling max
      - enroll_decline_10pct: enrollment ≥10% below 5-yr rolling max
      - persistent_neg_margin: ≥3 of past 5 years had negative operating margin
      - consec_enroll_decline_3yr: 3 consecutive years of >5% enrollment decline
    """
    print("Computing rolling indicators...")
    panel = panel.sort_values(["unitid", "year"])

    for _, var_col, out_col in [
        ("unitid", "total_rev_real", "rev_decline_10pct"),
        ("unitid", "enroll", "enroll_decline_10pct"),
    ]:
        if var_col not in panel.columns:
            continue
        rolling_max = panel.groupby("unitid")[var_col].transform(
            lambda x: x.shift(1).rolling(5, min_periods=1).max()
        )
        panel[out_col] = ((panel[var_col] < 0.9 * rolling_max) & rolling_max.notna()).astype("Int8")

    # Persistent negative margin: ≥3 of past 5 years negative
    if "operating_margin" in panel.columns:
        rolling_sum = panel.groupby("unitid")["operating_margin"].transform(
            lambda x: (x < 0).astype(float).shift(1).rolling(5, min_periods=3).sum()
        )
        panel["persistent_neg_margin"] = (rolling_sum >= 3).astype("Int8")

    # Consecutive enrollment decline: yoy < -5% for 3 consecutive years
    if "enroll_yoy" in panel.columns:
        rolling_sum3 = panel.groupby("unitid")["enroll_yoy"].transform(
            lambda x: (x < -0.05).astype(float).rolling(3, min_periods=3).sum()
        )
        panel["consec_enroll_decline_3yr"] = (rolling_sum3 >= 3).astype("Int8")

    return panel


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Build base panel ----
    panel = build_panel()
    print(f"\nBase panel: {len(panel):,} rows, {panel['unitid'].nunique():,} unique institutions")

    # ---- Derived variables ----
    panel = add_derived_variables(panel)
    panel = add_enrollment_changes(panel)

    # ---- Lag variables ----
    lag_targets = [
        "operating_margin", "dcoh", "debt_to_assets", "unrestricted_na_ratio",
        "rev_share_tuition", "exp_share_instruction", "exp_share_scholarships",
        "exp_share_interest", "debt_to_ebida",
        "enroll", "enroll_yoy",
        "total_rev_real", "total_exp_real",
        # Scorecard proxies
        "sc_tuitfte_real", "sc_inexpfte_real", "sc_pctpell",
    ]
    panel = add_lags(panel, lag_targets, lags=[2, 3])
    panel = add_rolling_indicators(panel)

    # ---- Sanity checks ----
    print("\n--- Sanity Checks ---")
    n_total = len(panel)
    print(f"Total rows: {n_total:,}")
    print(f"Years covered: {panel['year'].min()}–{panel['year'].max()}")
    print(f"Unique institutions: {panel['unitid'].nunique():,}")
    print(f"Rows with finance data: {panel['total_rev'].notna().sum():,} ({100*panel['total_rev'].notna().mean():.1f}%)")
    print(f"Rows with enrollment: {panel['enroll'].notna().sum():,} ({100*panel['enroll'].notna().mean():.1f}%)")

    closed_rows = panel[panel["is_closed"]]
    print(f"Rows for closed institutions: {len(closed_rows):,}")
    print(f"Institutions closed in year (closed_in_year=1): {(panel['closed_in_year']==1).sum():,}")
    print(f"Institutions with closure within 3yr: {(panel['closed_within_3yr']==1).sum():,}")

    print("\nMedian operating margin by sector:")
    sector_labels = {1:"Pub4yr",2:"Pub2yr",4:"NP4yr",5:"NP2yr",7:"FP4yr",8:"FP2yr"}
    for s, label in sector_labels.items():
        m = panel[panel["sector"]==s]["operating_margin"].median()
        n = (panel["sector"]==s).sum()
        print(f"  {label}: median={m:.3f}, n={n:,}")

    print("\nOperating margin distribution (all sectors):")
    print(panel["operating_margin"].describe())

    print("\nDCOH distribution:")
    print(panel["dcoh"].describe())

    # ---- Save ----
    out_path = OUTPUT_DIR / "institution_year_panel.parquet"
    panel.to_parquet(out_path, index=False)
    print(f"\nSaved to {out_path}")
    print(f"Columns: {list(panel.columns)}")


if __name__ == "__main__":
    main()
