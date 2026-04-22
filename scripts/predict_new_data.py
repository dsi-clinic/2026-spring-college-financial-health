"""
Apply the fitted XGBoost closure-risk model to new institution data.

Usage:
    uv run python scripts/predict_new_data.py --input my_institutions.csv --output predictions.csv

Input CSV must contain institution-year rows with the columns listed in REQUIRED_COLS
(see below). Missing values are allowed — XGBoost handles them natively.

Output CSV contains the input rows plus two added columns:
  closure_prob_1yr     Probability of closing in the next 1 year (Panel A model)
  closure_prob_3yr     Probability of closing within the next 3 years (Panel B model)

The model is the XGBoost (All Controls, F) variant from replicate_table5.py.
It must be trained first by running:
    uv run python scripts/replicate_table5.py

Models are saved to:
  analysis/models/xgb_close_1yr.json
  analysis/models/xgb_close_3yr.json
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

MODEL_DIR = Path("analysis/models")
PANEL_PATH = Path("analysis/panel/institution_year_panel.parquet")

# Columns the model was trained on (SELECT_CONTINUOUS + EXTENDED_VARS)
# Sector and year dummies are NOT included here (caller provides raw sector/year,
# we create dummies internally). State dummies are omitted for out-of-sample use.
FEATURE_COLS = [
    # Financial lags (L2, L3)
    "operating_margin_l2", "operating_margin_l3",
    "dcoh_l2", "dcoh_l3",
    "debt_to_assets_l2", "debt_to_assets_l3",
    "unrestricted_na_ratio_l2", "unrestricted_na_ratio_l3",
    "rev_share_tuition_l2", "rev_share_tuition_l3",
    # Enrollment
    "enroll_yoy", "enroll_yoy_l2", "enroll_yoy_l3",
    "enroll_l2", "enroll_l3",
    # Current-year financial (NaN = didn't file = risk signal)
    "operating_margin", "dcoh", "unrestricted_na_ratio", "rev_share_tuition",
    "exp_share_instruction", "exp_share_scholarships", "exp_share_interest",
    "exp_share_depreciation", "debt_to_ebida",
    # Binary indicators
    "rev_decline_10pct", "enroll_decline_10pct",
    "persistent_neg_margin", "consec_enroll_decline_3yr",
    # Size
    "total_rev_real", "total_rev_real_l2", "total_rev_real_l3",
]

# Human-readable column descriptions
REQUIRED_COLS = {
    "unitid": "IPEDS unit ID (numeric)",
    "sector": "IPEDS sector code: 4=NP4yr, 5=NP2yr, 6=NP<2yr, 7=FP4yr, 8=FP2yr, 9=FP<2yr",
    "year": "Survey year (e.g. 2022)",
}
OPTIONAL_COLS = {k: "float, NaN if missing" for k in FEATURE_COLS}


def load_models() -> tuple[xgb.Booster, xgb.Booster]:
    """Load fitted models from disk. Raises FileNotFoundError if not yet trained."""
    path_1yr = MODEL_DIR / "xgb_close_1yr.json"
    path_3yr = MODEL_DIR / "xgb_close_3yr.json"
    missing = [p for p in [path_1yr, path_3yr] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Model files not found: {[str(p) for p in missing]}\n"
            "Train them first by running:\n"
            "  uv run python scripts/replicate_table5.py"
        )
    m1 = xgb.Booster()
    m1.load_model(str(path_1yr))
    m3 = xgb.Booster()
    m3.load_model(str(path_3yr))
    return m1, m3


def _make_sector_dummies(df: pd.DataFrame) -> pd.DataFrame:
    """Add sector dummy columns (sec_4 … sec_9) from the sector column."""
    for s in [4, 5, 6, 7, 8, 9]:
        df[f"sec_{s}"] = (df["sector"] == s).astype(float)
    return df


def _get_feature_matrix(df: pd.DataFrame, fitted_feature_names: list[str]) -> xgb.DMatrix:
    """Build DMatrix from input df, aligning to fitted feature names.

    NOTE: Year dummy columns (yr_*) are not added here — they will be NaN for
    out-of-sample institutions, which XGBoost handles natively via its missing-value
    path. This is acceptable and consistent with how the model was exported.
    """
    df = _make_sector_dummies(df)

    for col in fitted_feature_names:
        if col not in df.columns:
            df[col] = np.nan

    X = df[fitted_feature_names].astype(float)
    X = X.replace([np.inf, -np.inf], np.nan)
    return xgb.DMatrix(X)


def predict(input_path: Path, output_path: Path) -> None:
    """Load input CSV, add predictions, save to output."""
    print(f"Loading input: {input_path}")
    df = pd.read_csv(input_path, encoding="utf-8", low_memory=False)
    print(f"  {len(df):,} rows, {df.shape[1]} columns")

    # Validate required columns
    for col in ["unitid", "sector", "year"]:
        if col not in df.columns:
            print(f"ERROR: Required column '{col}' not found in input.", file=sys.stderr)
            sys.exit(1)

    print("Loading models...")
    m1, m3 = load_models()
    feat_names_1 = m1.feature_names
    feat_names_3 = m3.feature_names

    print("Computing features...")
    dmat_1 = _get_feature_matrix(df, feat_names_1)
    dmat_3 = _get_feature_matrix(df, feat_names_3)

    print("Predicting...")
    df["closure_prob_1yr"] = m1.predict(dmat_1)
    df["closure_prob_3yr"] = m3.predict(dmat_3)

    print(f"\nPrediction summary:")
    print(f"  Median 1yr risk: {df['closure_prob_1yr'].median():.4f}")
    print(f"  Median 3yr risk: {df['closure_prob_3yr'].median():.4f}")
    print(f"  Institutions with 1yr risk > 5%: {(df['closure_prob_1yr'] > 0.05).sum()}")
    print(f"  Institutions with 1yr risk > 10%: {(df['closure_prob_1yr'] > 0.10).sum()}")

    df.to_csv(output_path, index=False)
    print(f"\nSaved predictions to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Apply XGBoost closure-risk model to institution data"
    )
    parser.add_argument("--input", type=Path, required=True,
                        help="Input CSV with institution-year data")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output CSV with added prediction columns")
    parser.add_argument("--describe", action="store_true",
                        help="Print column requirements and exit")
    args = parser.parse_args()

    if args.describe:
        print("Required columns:")
        for col, desc in REQUIRED_COLS.items():
            print(f"  {col}: {desc}")
        print("\nOptional feature columns (NaN if missing):")
        for col, desc in list(OPTIONAL_COLS.items())[:5]:
            print(f"  {col}: {desc}")
        print(f"  ... and {len(OPTIONAL_COLS)-5} more (see FEATURE_COLS in script)")
        print(f"\nTo generate the full panel from IPEDS data, run:")
        print(f"  uv run python scripts/build_panel.py")
        print(f"  (then use analysis/panel/institution_year_panel.parquet as your input)")
        sys.exit(0)

    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    predict(args.input, args.output)


if __name__ == "__main__":
    main()
