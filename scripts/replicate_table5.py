"""
Replication of Table 5: Predictive Accuracy for Linear Regression and XGBoost Models
Kelchen, Ritter & Webber (2025), FEDS 2025-003

Table 5 shows AUC scores for 6 model variants across two closure outcomes:
  Panel A: Point-in-time closure (closed_in_year)
  Panel B: Closure within 3 years (closed_within_3yr)

Model rows:
  A  Linear Probability (OLS)   Select Continuous    Non-missing sample
  B  LASSO → OLS                Select Continuous    Non-missing → expanded
  C  Linear Probability (OLS)   Select Binned        Full sample
  D  XGBoost                    Select Binned        Full sample
  E  XGBoost                    Select Continuous    Full sample
  F  XGBoost                    All Controls         Full sample

Samples:
  Full (2002–2021): all available institution-years
  Sub (2006–2020):  sub-sample with federal accountability metrics (if available)

Train/test split: 75/25 by institution (stratified by ever-closed status).
AUC computed on 25% holdout.

NOTE: This replication uses private nonprofit and for-profit institutions only
(sectors 4-9), consistent with the paper's focus on closure risk for non-public schools.
Public institutions (sectors 1-3) are excluded because they almost never close.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV, LinearRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb

PANEL_PATH = Path("analysis/panel/institution_year_panel.parquet")
OUTPUT_DIR = Path("analysis/replicated_tables")

# Private sectors: nonprofit (4,5,6) and for-profit (7,8,9)
PRIVATE_SECTORS = [4, 5, 6, 7, 8, 9]

# --- Feature sets ---
# Select Continuous: use L2/L3 lags for financial metrics because institutions that
# are about to close often don't file their current-year IPEDS finance survey, but
# DO have data from 2-3 years prior. Enrollment has better current-year coverage.
SELECT_CONTINUOUS = [
    # Financial metrics: lagged (year T-2, T-3) — available even for near-closure institutions
    "operating_margin_l2", "operating_margin_l3",
    "dcoh_l2", "dcoh_l3",
    "debt_to_assets_l2", "debt_to_assets_l3",
    "unrestricted_na_ratio_l2", "unrestricted_na_ratio_l3",
    "rev_share_tuition_l2", "rev_share_tuition_l3",
    # Enrollment: current + lagged (better filing coverage than finance)
    "enroll_yoy", "enroll_yoy_l2", "enroll_yoy_l3",
    "enroll_l2", "enroll_l3",
]

# Variables to bin for Select Binned variant
BINNED_VARS = [
    "operating_margin_l2", "dcoh_l2", "debt_to_assets_l2", "unrestricted_na_ratio_l2",
    "rev_share_tuition_l2", "enroll_yoy",
]

# Additional variables for All Controls
# Current-year financial features included here for XGBoost (handles NaN natively;
# missing finance data is itself a risk signal — small/struggling institutions often
# stop filing IPEDS surveys before they formally close).
EXTENDED_VARS = [
    # Current-year financial (NaN = didn't file = risk signal for XGBoost)
    "operating_margin", "dcoh", "unrestricted_na_ratio", "rev_share_tuition",
    "exp_share_instruction", "exp_share_scholarships", "exp_share_interest",
    "exp_share_depreciation", "debt_to_ebida",
    # Rolling/binary indicators
    "rev_decline_10pct", "enroll_decline_10pct",
    "persistent_neg_margin", "consec_enroll_decline_3yr",
    # Institution size
    "total_rev_real", "total_rev_real_l2", "total_rev_real_l3",
    "enroll_l2", "enroll_l3",
]


def load_panel() -> pd.DataFrame:
    """
    Load and filter panel to private institutions.

    Creates lead outcomes: the prediction task uses year-T features to predict
    closure in years T+1 through T+3. This ensures institutions still have
    financial data in year T (they hadn't yet closed). Institutions that close
    in year T rarely file year-T IPEDS surveys, so year-T financial features
    would be missing; using lead outcomes avoids this data availability problem.

    Lead outcomes (at year T):
      closed_in_year_lead1   = institution will close in year T+1
      closed_within_3yr_lead = institution will close in T+1, T+2, or T+3
    """
    panel = pd.read_parquet(PANEL_PATH)
    panel = panel[panel["sector"].isin(PRIVATE_SECTORS)].copy()

    # Restrict to 2002–2020 (use 2021 as the last closure-check year, so features from 2020)
    panel = panel[panel["year"] <= 2020].copy()

    # Create lead outcomes: shift closed_in_year and closed_within_3yr backward by 1 year
    # so year-T row predicts year-(T+1) closure
    panel = panel.sort_values(["unitid", "year"])
    panel["closed_in_year_lead1"] = (
        panel.groupby("unitid")["closed_in_year"]
        .shift(-1)
        .fillna(0)
        .astype("Int8")
    )
    panel["closed_within_3yr_lead"] = (
        panel.groupby("unitid")["closed_within_3yr"]
        .shift(-1)
        .fillna(0)
        .astype("Int8")
    )

    # Keep year as numeric column; also make year dummies
    panel["year_num"] = panel["year"].copy()
    panel = pd.get_dummies(panel, columns=["sector"], prefix="sec", dtype=float)
    panel = pd.get_dummies(panel, columns=["stabbr"], prefix="st", dtype=float)
    panel = pd.get_dummies(panel, columns=["year"], prefix="yr", dtype=float)

    return panel


def get_sector_dummies(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c.startswith("sec_")]


def get_state_dummies(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c.startswith("st_")]


def get_year_dummies(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c.startswith("yr_")]


def make_binned_features(df: pd.DataFrame, fit_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Replace continuous variables in BINNED_VARS with quartile dummies + missing indicator.
    fit_df: if provided, compute quantile breakpoints from fit_df (train set) and apply to df.
    Returns df with binned features added and original continuous vars removed.
    """
    source = fit_df if fit_df is not None else df
    result = df.copy()

    for var in BINNED_VARS:
        if var not in df.columns:
            continue
        missing_col = f"{var}_missing"
        result[missing_col] = df[var].isna().astype(float)

        # Compute quartile breakpoints from source (training) data
        src_vals = source[var].dropna()
        q25, q50, q75 = src_vals.quantile([0.25, 0.5, 0.75])

        # Assign quartiles; NaN → Q1 (for full-sample models, missing gets a missing flag)
        vals = df[var].copy()
        result[f"{var}_q1"] = ((vals <= q25) & vals.notna()).astype(float)
        result[f"{var}_q2"] = ((vals > q25) & (vals <= q50) & vals.notna()).astype(float)
        result[f"{var}_q3"] = ((vals > q50) & (vals <= q75) & vals.notna()).astype(float)
        result[f"{var}_q4"] = ((vals > q75) & vals.notna()).astype(float)

        result = result.drop(columns=[var])

    return result


def train_test_split_by_institution(
    panel: pd.DataFrame, outcome: str, test_size: float = 0.25, random_state: int = 42
):
    """
    Split 75/25 by institution (unitid), stratified by ever-closed status.
    Returns (train_idx, test_idx) as boolean Series.
    """
    inst = panel.groupby("unitid")[outcome].max().reset_index()
    inst.columns = ["unitid", "ever_closed"]

    train_units, test_units = train_test_split(
        inst["unitid"],
        test_size=test_size,
        random_state=random_state,
        stratify=inst["ever_closed"],
    )
    train_mask = panel["unitid"].isin(train_units)
    test_mask = panel["unitid"].isin(test_units)
    return train_mask, test_mask


def safe_auc(y_true, y_score) -> float | None:
    """Return AUC or None if both classes not present."""
    y_true = np.asarray(y_true).astype(float)
    if len(np.unique(y_true[~np.isnan(y_true)])) < 2:
        return None
    valid = ~(np.isnan(y_true) | np.isnan(y_score))
    if valid.sum() < 10:
        return None
    return roc_auc_score(y_true[valid], y_score[valid])


def _clean(arr: np.ndarray) -> np.ndarray:
    """Replace inf/-inf with NaN in float array (NaN signals missing to OLS filter)."""
    arr = arr.astype(float)
    arr[np.isposinf(arr) | np.isneginf(arr)] = np.nan
    return arr


def run_ols(X_train, y_train, X_test) -> np.ndarray:
    """Fit OLS (LinearRegression) on non-missing rows; predict only on complete test rows."""
    X_train = _clean(X_train)
    X_test = _clean(X_test)
    valid_tr = (~np.isnan(X_train).any(axis=1)) & (~np.isnan(y_train))
    model = LinearRegression()
    model.fit(X_train[valid_tr], y_train[valid_tr])

    # Predict only where test features are fully observed
    valid_te = ~np.isnan(X_test).any(axis=1)
    preds = np.full(len(X_test), np.nan)
    preds[valid_te] = model.predict(X_test[valid_te])
    return preds


def run_lasso_ols(X_train, y_train, X_test, X_test_full, all_feature_names) -> np.ndarray:
    """
    LASSO-OLS: fit LassoCV to select features, then OLS on selected features.
    Returns predictions on X_test_full (expanded sample).
    """
    X_train = _clean(X_train)
    X_test = _clean(X_test)
    X_test_full = _clean(X_test_full)
    # Step 1: LASSO on non-missing rows only
    valid = (~np.isnan(X_train).any(axis=1)) & (~np.isnan(y_train))
    lasso = LassoCV(cv=5, random_state=42, max_iter=5000, n_jobs=-1)
    lasso.fit(X_train[valid], y_train[valid])

    # Step 2: identify selected features (non-zero coefficients)
    selected_mask = lasso.coef_ != 0
    if selected_mask.sum() == 0:
        # Fall back to all features if LASSO zeroed everything
        selected_mask = np.ones(len(lasso.coef_), dtype=bool)

    # Step 3: OLS on selected features (same non-missing rows)
    ols = LinearRegression()
    ols.fit(X_train[valid][:, selected_mask], y_train[valid])

    # Predict on expanded test set: rows non-missing for selected features only
    X_sel = X_test_full[:, selected_mask]
    valid_test = ~np.isnan(X_sel).any(axis=1)
    preds = np.full(len(X_sel), np.nan)
    preds[valid_test] = ols.predict(X_sel[valid_test])
    return preds


def run_xgboost(X_train, y_train, X_test, scale_pos_weight: float | None = None) -> np.ndarray:
    """
    Fit XGBoost classifier with native NaN handling.

    XGBoost handles NaN natively by learning the optimal imputation direction at
    each split, so we pass actual NaN values rather than substituting 0.
    Inf values are replaced with NaN so XGBoost treats them as missing.
    """
    X_train = _clean(X_train)  # inf → NaN; XGBoost handles NaN natively
    X_test = _clean(X_test)

    valid = ~np.isnan(y_train)
    params = dict(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        eval_metric="logloss",
        early_stopping_rounds=30,
    )
    if scale_pos_weight is not None:
        params["scale_pos_weight"] = scale_pos_weight

    X_tr = X_train[valid]
    y_tr = y_train[valid].astype(int)

    # 10% of training rows as internal validation for early stopping
    n_val = max(100, int(0.1 * len(y_tr)))
    rng = np.random.default_rng(42)
    val_idx = rng.choice(len(y_tr), size=n_val, replace=False)
    train_idx = np.setdiff1d(np.arange(len(y_tr)), val_idx)

    dtrain = xgb.DMatrix(X_tr[train_idx], label=y_tr[train_idx])
    dval = xgb.DMatrix(X_tr[val_idx], label=y_tr[val_idx])
    dtest = xgb.DMatrix(X_test)

    xgb_params = {
        "max_depth": params["max_depth"],
        "learning_rate": params["learning_rate"],
        "subsample": params["subsample"],
        "colsample_bytree": params["colsample_bytree"],
        "seed": params["random_state"],
        "nthread": params["n_jobs"],
        "eval_metric": params["eval_metric"],
        "objective": "binary:logistic",
    }
    if scale_pos_weight is not None:
        xgb_params["scale_pos_weight"] = scale_pos_weight

    booster = xgb.train(
        xgb_params,
        dtrain,
        num_boost_round=params["n_estimators"],
        evals=[(dval, "val")],
        early_stopping_rounds=params["early_stopping_rounds"],
        verbose_eval=False,
    )
    return booster.predict(dtest), booster


def run_models(panel: pd.DataFrame, outcome: str, sample_label: str) -> list[dict]:
    """
    Run all 6 model variants for one outcome and one sample.
    Returns list of result dicts.
    """
    print(f"\n  Outcome: {outcome}  |  Sample: {sample_label}")
    print(f"  Panel rows: {len(panel):,}  |  Positive rate: {panel[outcome].mean():.3%}")

    train_mask, test_mask = train_test_split_by_institution(panel, outcome)
    train = panel[train_mask].copy()
    test = panel[test_mask].copy()

    sec_dummies = get_sector_dummies(panel)
    yr_dummies = get_year_dummies(panel)

    # Compute scale_pos_weight for XGBoost (handles class imbalance)
    n_neg = (train[outcome] == 0).sum()
    n_pos = (train[outcome] == 1).sum()
    spw = n_neg / max(n_pos, 1)

    results = []

    # ---- Model A: OLS, Select Continuous ----
    feats_a = SELECT_CONTINUOUS + sec_dummies + yr_dummies
    feats_a = [f for f in feats_a if f in panel.columns]
    X_tr = train[feats_a].values
    y_tr = train[outcome].values.astype(float)
    X_te = test[feats_a].values
    y_te = test[outcome].values.astype(float)

    preds = run_ols(X_tr, y_tr, X_te)
    non_miss_te = ~np.isnan(preds)
    auc = safe_auc(y_te[non_miss_te], preds[non_miss_te])
    n_obs = int(non_miss_te.sum())
    n_close = int(y_te[non_miss_te].sum())
    print(f"    A  OLS/Continuous:       AUC={_fmt_auc(auc)}  N={n_obs:,}  closures={n_close}")
    results.append({"model": "A: OLS (Continuous)", "outcome": outcome, "sample": sample_label,
                    "auc": auc, "n_obs": n_obs, "n_closures": n_close})

    # ---- Model B: LASSO→OLS, Select Continuous ----
    feats_b = SELECT_CONTINUOUS + sec_dummies + yr_dummies
    feats_b = [f for f in feats_b if f in panel.columns]
    X_tr_b = train[feats_b].values
    X_te_b = test[feats_b].values

    preds_b = run_lasso_ols(X_tr_b, y_tr, X_te_b, X_te_b, feats_b)
    valid_b = ~np.isnan(preds_b)
    auc_b = safe_auc(y_te[valid_b], preds_b[valid_b])
    n_obs_b = int(valid_b.sum())
    n_close_b = int(y_te[valid_b].sum())
    print(f"    B  LASSO→OLS/Continuous: AUC={_fmt_auc(auc_b)}  N={n_obs_b:,}  closures={n_close_b}")
    results.append({"model": "B: LASSO-OLS (Continuous)", "outcome": outcome, "sample": sample_label,
                    "auc": auc_b, "n_obs": n_obs_b, "n_closures": n_close_b})

    # ---- Model C: OLS, Select Binned ----
    # Bin continuous variables using train-set quantiles
    # For OLS binned we want rows that have at least partial data; use the binned features
    # which set missing flag when original is NaN
    train_binned = make_binned_features(train, fit_df=train)
    test_binned = make_binned_features(test, fit_df=train)

    binned_cols = [c for c in train_binned.columns
                   if any(c.startswith(v + "_q") or c.startswith(v + "_miss")
                          for v in BINNED_VARS)]
    binned_lags = [f for f in train_binned.columns
                   if any(f == v for v in SELECT_CONTINUOUS if v not in BINNED_VARS)]
    feats_c = binned_cols + binned_lags + sec_dummies + yr_dummies
    feats_c = [f for f in feats_c if f in train_binned.columns]

    X_tr_c = np.nan_to_num(train_binned[feats_c].values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    y_tr_c = train_binned[outcome].values.astype(float)
    X_te_c = np.nan_to_num(test_binned[feats_c].values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    y_te_c = test_binned[outcome].values.astype(float)

    preds_c = run_ols(X_tr_c, y_tr_c, X_te_c)
    auc_c = safe_auc(y_te_c, preds_c)
    n_obs_c = len(y_te_c)
    n_close_c = int(y_te_c.sum())
    print(f"    C  OLS/Binned:           AUC={_fmt_auc(auc_c)}  N={n_obs_c:,}  closures={n_close_c}")
    results.append({"model": "C: OLS (Binned)", "outcome": outcome, "sample": sample_label,
                    "auc": auc_c, "n_obs": n_obs_c, "n_closures": n_close_c})

    # ---- Model D: XGBoost, Select Binned ----
    X_tr_d = X_tr_c  # already nan_to_num'd above
    X_te_d = X_te_c  # already nan_to_num'd above
    preds_d, _ = run_xgboost(X_tr_d, y_tr_c, X_te_d, scale_pos_weight=spw)
    auc_d = safe_auc(y_te_c, preds_d)
    print(f"    D  XGB/Binned:           AUC={_fmt_auc(auc_d)}  N={n_obs_c:,}  closures={n_close_c}")
    results.append({"model": "D: XGBoost (Binned)", "outcome": outcome, "sample": sample_label,
                    "auc": auc_d, "n_obs": n_obs_c, "n_closures": n_close_c})

    # ---- Model E: XGBoost, Select Continuous ----
    # Use NaN natively (nan_to_num inside run_xgboost)
    X_tr_e = train[feats_a].values
    X_te_e = test[feats_a].values
    preds_e, _ = run_xgboost(X_tr_e, y_tr, X_te_e, scale_pos_weight=spw)
    auc_e = safe_auc(y_te, preds_e)
    n_obs_e = len(y_te)
    n_close_e = int(y_te.sum())
    print(f"    E  XGB/Continuous:       AUC={_fmt_auc(auc_e)}  N={n_obs_e:,}  closures={n_close_e}")
    results.append({"model": "E: XGBoost (Continuous)", "outcome": outcome, "sample": sample_label,
                    "auc": auc_e, "n_obs": n_obs_e, "n_closures": n_close_e})

    # ---- Model F: XGBoost, All Controls ----
    all_feats = SELECT_CONTINUOUS + EXTENDED_VARS + sec_dummies + yr_dummies
    all_feats = [f for f in all_feats if f in panel.columns]
    X_tr_f = train[all_feats].values
    X_te_f = test[all_feats].values
    preds_f, booster_f = run_xgboost(X_tr_f, y_tr, X_te_f, scale_pos_weight=spw)
    auc_f = safe_auc(y_te, preds_f)
    print(f"    F  XGB/All Controls:     AUC={_fmt_auc(auc_f)}  N={n_obs_e:,}  closures={n_close_e}")
    results.append({"model": "F: XGBoost (All Controls)", "outcome": outcome, "sample": sample_label,
                    "auc": auc_f, "n_obs": n_obs_e, "n_closures": n_close_e,
                    "_booster_f": booster_f, "_feats_f": all_feats})

    return results


def _fmt_auc(auc) -> str:
    return f"{auc:.3f}" if auc is not None else "N/A"


def format_table(results: list[dict]) -> pd.DataFrame:
    """Format results into a Table 5 style output."""
    rows = []
    for r in results:
        auc_str = _fmt_auc(r["auc"])
        rows.append({
            "Model": r["model"],
            "Outcome": r["outcome"],
            "Sample": r["sample"],
            "AUC": auc_str,
            "N_obs": r["n_obs"],
            "N_closures": r["n_closures"],
        })
    return pd.DataFrame(rows)


def main():
    print("Loading panel...")
    panel = load_panel()
    print(f"  {len(panel):,} rows, {panel['unitid'].nunique():,} institutions (private sectors)")
    print(f"  Years: {panel['year_num'].min()}–{panel['year_num'].max()}")
    print(f"  closed_in_year_lead1=1: {(panel['closed_in_year_lead1']==1).sum():,}")
    print(f"  closed_within_3yr_lead=1: {(panel['closed_within_3yr_lead']==1).sum():,}")

    full_panel = panel.copy()

    all_results = []
    outcomes = ["closed_in_year_lead1", "closed_within_3yr_lead"]
    outcome_labels = {
        "closed_in_year_lead1": "Panel A: Point-in-Time Closure (1-yr lead)",
        "closed_within_3yr_lead": "Panel B: Closure Within 3 Years (1-yr lead)",
    }

    for outcome in outcomes:
        print(f"\n{'='*60}")
        print(f"{outcome_labels[outcome]}")
        print(f"{'='*60}")

        # Full sample: 2002–2021
        results = run_models(full_panel, outcome, "2002–2021 (full)")
        all_results.extend(results)

    # Format and print results
    df = format_table(all_results)
    print(f"\n{'='*60}")
    print("REPLICATION TABLE 5")
    print(f"{'='*60}")

    # Pivot to paper format: models as rows, outcome×sample as columns
    pivot = df.pivot_table(
        index="Model",
        columns=["Outcome", "Sample"],
        values="AUC",
        aggfunc="first",
    )
    print(pivot.to_string())

    # Print paper targets for comparison
    print(f"\n{'='*60}")
    print("PAPER TARGETS (Kelchen, Ritter & Webber 2025, Table 5)")
    print(f"{'='*60}")
    paper = pd.DataFrame([
        # Panel A: Point-in-Time Closure
        {"Model": "A: OLS (Continuous)",      "Panel": "A", "AUC_2002": "0.868", "AUC_2006": "0.880"},
        {"Model": "B: LASSO-OLS (Continuous)","Panel": "A", "AUC_2002": "0.875", "AUC_2006": "0.889"},
        {"Model": "C: OLS (Binned)",           "Panel": "A", "AUC_2002": "0.886", "AUC_2006": "0.901"},
        {"Model": "D: XGBoost (Binned)",       "Panel": "A", "AUC_2002": "0.893", "AUC_2006": "0.906"},
        {"Model": "E: XGBoost (Continuous)",   "Panel": "A", "AUC_2002": "0.893", "AUC_2006": "0.906"},
        {"Model": "F: XGBoost (All Controls)", "Panel": "A", "AUC_2002": "0.903", "AUC_2006": "0.922"},
        # Panel B: Closure Within 3 Years
        {"Model": "A: OLS (Continuous)",      "Panel": "B", "AUC_2002": "0.847", "AUC_2006": "0.862"},
        {"Model": "B: LASSO-OLS (Continuous)","Panel": "B", "AUC_2002": "0.857", "AUC_2006": "0.875"},
        {"Model": "C: OLS (Binned)",           "Panel": "B", "AUC_2002": "0.869", "AUC_2006": "0.882"},
        {"Model": "D: XGBoost (Binned)",       "Panel": "B", "AUC_2002": "0.872", "AUC_2006": "0.882"},
        {"Model": "E: XGBoost (Continuous)",   "Panel": "B", "AUC_2002": "0.872", "AUC_2006": "0.882"},
        {"Model": "F: XGBoost (All Controls)", "Panel": "B", "AUC_2002": "0.882", "AUC_2006": "0.900"},
    ])
    paper_piv = paper.pivot_table(index="Model", columns="Panel", values=["AUC_2002", "AUC_2006"], aggfunc="first")
    print(paper_piv.to_string())

    # Save full results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "replicated_table5.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")

    # Save XGBoost All-Controls models for use by predict_new_data.py
    model_dir = Path("analysis/models")
    model_dir.mkdir(parents=True, exist_ok=True)

    for r in all_results:
        if r["model"] == "F: XGBoost (All Controls)" and "_booster_f" in r:
            outcome_key = r["outcome"]
            suffix = "1yr" if "lead1" in outcome_key else "3yr"
            booster = r["_booster_f"]
            feat_names = r["_feats_f"]
            # Store feature names in booster for predict_new_data.py to recover
            booster.feature_names = feat_names
            save_path = model_dir / f"xgb_close_{suffix}.json"
            booster.save_model(str(save_path))
            print(f"Saved model to {save_path}")

    print(f"\nTo predict on new data:")
    print(f"  uv run python scripts/predict_new_data.py --input my_data.csv --output predictions.csv")


if __name__ == "__main__":
    main()
