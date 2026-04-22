"""
College closure risk prediction from IPEDS panel data.

This is the primary callable interface for the final deliverable:

    from college_risk import predict

    results = predict("analysis/panel/institution_year_panel.parquet", year=2022)
    print(results.head(20))

The model was trained on the IPEDS + College Scorecard panel built by
scripts/build_panel.py and scripts/replicate_table5.py. It can be applied
to any year in the panel, or to new data that has the same feature columns.

Output columns
--------------
unitid            IPEDS unit ID
instnm            Institution name
stabbr            State abbreviation
sector            IPEDS sector (4–9 = private)
year              The feature year (predictions are for T+1 and T+1–T+3 closures)
closure_prob_1yr  Probability of closing in the next 1 year  [0, 1]
closure_prob_3yr  Probability of closing within the next 3 years  [0, 1]

Notes
-----
- Predictions are only returned for private institutions (sectors 4–9) because
  the model was trained exclusively on that subset.
- Missing feature values are handled natively by XGBoost (no imputation needed).
- Year dummies for future years (not seen during training) are passed as NaN;
  XGBoost routes those rows through its missing-value path.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

MODEL_DIR = Path("analysis/models")
PANEL_PATH = Path("analysis/panel/institution_year_panel.parquet")

PRIVATE_SECTORS = [4, 5, 6, 7, 8, 9]


def _load_models() -> tuple[xgb.Booster, xgb.Booster]:
    m1, m3 = xgb.Booster(), xgb.Booster()
    for model, name in [(m1, "xgb_close_1yr.json"), (m3, "xgb_close_3yr.json")]:
        path = MODEL_DIR / name
        if not path.exists():
            raise FileNotFoundError(
                f"Model not found: {path}\n"
                "Train it first:  uv run python scripts/replicate_table5.py"
            )
        model.load_model(str(path))
    return m1, m3


def _build_dmatrix(df: pd.DataFrame, feature_names: list[str]) -> xgb.DMatrix:
    """Align df to model feature names, adding missing columns as NaN."""
    # Deduplicate while preserving order (guards against models saved with dup names)
    feature_names = list(dict.fromkeys(feature_names))
    for col in feature_names:
        if col not in df.columns:
            df[col] = np.nan
    X = df[feature_names].astype(float).replace([np.inf, -np.inf], np.nan)
    return xgb.DMatrix(X)


def predict(
    panel: "pd.DataFrame | Path | str" = PANEL_PATH,
    year: int | None = None,
    model_dir: "Path | str" = MODEL_DIR,
) -> pd.DataFrame:
    """
    Score institutions in the IPEDS panel for closure risk.

    Parameters
    ----------
    panel : DataFrame, Path, or str
        The institution-year panel produced by scripts/build_panel.py, supplied
        either as a pre-loaded DataFrame or a path to the parquet file.
    year : int or None
        If given, return predictions for that specific year only.
        If None, return predictions for all years in the panel.
    model_dir : Path or str
        Directory containing xgb_close_1yr.json and xgb_close_3yr.json.

    Returns
    -------
    DataFrame sorted by closure_prob_1yr descending.
    """
    global MODEL_DIR
    MODEL_DIR = Path(model_dir)

    # Load panel
    if not isinstance(panel, pd.DataFrame):
        panel = pd.read_parquet(panel)

    # Filter to private sectors (model was trained on these only)
    df = panel[panel["sector"].isin(PRIVATE_SECTORS)].copy()

    if year is not None:
        df = df[df["year"] == year].copy()
        if df.empty:
            raise ValueError(
                f"No private-sector rows found for year={year}. "
                f"Panel covers {panel['year'].min()}–{panel['year'].max()}."
            )

    # Sector dummies
    for s in PRIVATE_SECTORS:
        df[f"sec_{s}"] = (df["sector"] == s).astype(float)

    # Year dummies (NaN for years not in training data — XGBoost handles natively)
    for y in df["year"].unique():
        df[f"yr_{y}"] = 1.0
    # Zero out non-current years within each row
    yr_cols = [c for c in df.columns if c.startswith("yr_")]
    for col in yr_cols:
        yr_val = int(col.split("_")[1])
        df[col] = (df["year"] == yr_val).astype(float)

    # State dummies (present in training; NaN for unseen states is fine)
    for st in df["stabbr"].dropna().unique():
        df[f"st_{st}"] = (df["stabbr"] == st).astype(float)

    # Load models and predict
    m1, m3 = _load_models()
    dmat1 = _build_dmatrix(df.copy(), m1.feature_names)
    dmat3 = _build_dmatrix(df.copy(), m3.feature_names)

    df["closure_prob_1yr"] = m1.predict(dmat1)
    df["closure_prob_3yr"] = m3.predict(dmat3)

    keep = ["unitid", "instnm", "stabbr", "sector", "year",
            "closure_prob_1yr", "closure_prob_3yr"]
    out = df[[c for c in keep if c in df.columns]].copy()
    return out.sort_values("closure_prob_1yr", ascending=False).reset_index(drop=True)


def top_at_risk(
    panel: "pd.DataFrame | Path | str" = PANEL_PATH,
    year: int | None = None,
    n: int = 50,
    model_dir: "Path | str" = MODEL_DIR,
) -> pd.DataFrame:
    """
    Return the top-N institutions most at risk of closing.

    Convenience wrapper around predict(). Uses the most recent panel year
    if year is not specified.
    """
    if year is None:
        if isinstance(panel, pd.DataFrame):
            year = int(panel["year"].max())
        else:
            _p = pd.read_parquet(panel, columns=["year"])
            year = int(_p["year"].max())

    return predict(panel=panel, year=year, model_dir=model_dir).head(n)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Score institutions for closure risk from the IPEDS panel"
    )
    parser.add_argument("--panel", type=Path, default=PANEL_PATH,
                        help="Path to institution_year_panel.parquet")
    parser.add_argument("--year", type=int, default=None,
                        help="Score only this year (default: all years)")
    parser.add_argument("--top", type=int, default=None,
                        help="Print only the top-N highest-risk institutions")
    parser.add_argument("--output", type=Path, default=None,
                        help="Save results to this CSV path")
    args = parser.parse_args()

    results = predict(panel=args.panel, year=args.year)

    display = results.head(args.top) if args.top else results
    print(display.to_string(index=False))

    if args.output:
        results.to_csv(args.output, index=False)
        print(f"\nSaved {len(results):,} rows to {args.output}")
