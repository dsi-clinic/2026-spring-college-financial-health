"""
Replication of Table 5: Predictive Accuracy for Linear Regression and XGBoost Models
Kelchen, Ritter & Webber (2025), FEDS 2025-003

Table 5 structure (9 columns):
  Sample | Model | Controls | Pred Closures (pt) | AUC (pt) | N (pt) | Pred Closures (3yr) | AUC (3yr) | N (3yr)

Model rows:
  A  Linear Probability          Select Continuous   Non-missing sample
  B  Linear Probability – LASSO  Select Continuous   Non-missing → expanded
  C  Linear Probability          Select Binned       Full sample
  D  Gradient Boosting           Select Binned       Full sample
  E  Gradient Boosting           Select Continuous   Full sample
  F  Gradient Boosting           All                 Full sample

Plus Federal Metrics rows (2006–2020 sub-sample only, requires FRC data):
  G  Linear Probability          Federal Metrics     Full sample
  H  Gradient Boosting           Federal Metrics     Full sample

Samples:
  2002–2023: all available institution-years
  2006–2020: sub-sample with federal accountability metrics

Train/test split: 75/25 by institution (stratified by ever-closed status).
Predicted Closures: count at the Youden's J optimal threshold.

NOTE: Private institutions only (sectors 4–9). HCM2 not available; Federal Metrics
rows use FRC composite score only.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV, LinearRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
import xgboost as xgb

PANEL_PATH = Path("analysis/panel/institution_year_panel.parquet")
OUTPUT_DIR = Path("analysis/replicated_tables")
FRC_DIR = Path("manual_data/frc/raw")

# Private sectors: nonprofit (4,5,6) and for-profit (7,8,9)
PRIVATE_SECTORS = [4, 5, 6, 7, 8, 9]

# --- Feature sets ---
SELECT_CONTINUOUS = [
    "operating_margin_l2", "operating_margin_l3",
    "dcoh_l2", "dcoh_l3",
    "debt_to_assets_l2", "debt_to_assets_l3",
    "unrestricted_na_ratio_l2", "unrestricted_na_ratio_l3",
    "rev_share_tuition_l2", "rev_share_tuition_l3",
    "enroll_yoy", "enroll_yoy_l2", "enroll_yoy_l3",
    "enroll_l2", "enroll_l3",
]

BINNED_VARS = [
    "operating_margin_l2", "dcoh_l2", "debt_to_assets_l2", "unrestricted_na_ratio_l2",
    "rev_share_tuition_l2", "enroll_yoy",
]

EXTENDED_VARS = [
    "operating_margin", "dcoh", "unrestricted_na_ratio", "rev_share_tuition",
    "exp_share_instruction", "exp_share_scholarships", "exp_share_interest",
    "exp_share_depreciation", "debt_to_ebida",
    "rev_decline_10pct", "enroll_decline_10pct",
    "persistent_neg_margin", "consec_enroll_decline_3yr",
    "total_rev_real", "total_rev_real_l2", "total_rev_real_l3",
    "enroll_l2", "enroll_l3",
]


def load_panel() -> pd.DataFrame:
    """
    Load panel, filter to private institutions, create lead outcomes.

    Lead outcomes (at year T):
      closed_in_year_lead1   = institution will close in year T+1
      closed_within_3yr_lead = institution will close in T+1, T+2, or T+3
    """
    panel = pd.read_parquet(PANEL_PATH)
    panel = panel[panel["sector"].isin(PRIVATE_SECTORS)].copy()
    panel = panel[panel["year"] <= 2020].copy()

    panel = panel.sort_values(["unitid", "year"])
    panel["closed_in_year_lead1"] = (
        panel.groupby("unitid")["closed_in_year"]
        .shift(-1).fillna(0).astype("Int8")
    )
    panel["closed_within_3yr_lead"] = (
        panel.groupby("unitid")["closed_within_3yr"]
        .shift(-1).fillna(0).astype("Int8")
    )

    panel["year_num"] = panel["year"].copy()
    panel = pd.get_dummies(panel, columns=["sector"], prefix="sec", dtype=float)
    panel = pd.get_dummies(panel, columns=["stabbr"], prefix="st", dtype=float)
    panel = pd.get_dummies(panel, columns=["year"], prefix="yr", dtype=float)

    return panel


def load_frc() -> pd.DataFrame:
    """
    Load FRC composite scores for 2006–2021.
    Returns DataFrame with columns: opeid (8-char zero-padded), frc_score, year.
    """
    frames = []
    for year in range(2006, 2022):
        path = FRC_DIR / f"frc_{year}.xls"
        if not path.exists():
            continue
        try:
            df = pd.read_excel(path, header=3)
            cols = df.columns.tolist()
            # Column 0 = OPE ID, last column = composite score
            df = df.rename(columns={cols[0]: "opeid_raw", cols[-1]: "frc_score"})
            df = df[["opeid_raw", "frc_score"]].copy()
            # Drop non-data rows (notes, blanks that slipped past header)
            df = df[pd.to_numeric(df["opeid_raw"], errors="coerce").notna()].copy()
            df["opeid"] = (
                df["opeid_raw"].astype(float).astype(int).astype(str).str.zfill(8)
            )
            df["frc_score"] = pd.to_numeric(df["frc_score"], errors="coerce")
            df = df.dropna(subset=["frc_score"])
            df["year"] = year
            frames.append(df[["opeid", "frc_score", "year"]])
        except Exception as e:
            print(f"  Warning: FRC {year}: {e}")
    if not frames:
        return pd.DataFrame(columns=["opeid", "frc_score", "year"])
    return pd.concat(frames, ignore_index=True)


def merge_frc(panel: pd.DataFrame, frc: pd.DataFrame) -> pd.DataFrame:
    """Merge FRC scores into panel by (opeid, year). Panel must have 'opeid' and 'year_num'."""
    if frc.empty:
        panel["frc_score"] = np.nan
        return panel
    # Normalize opeid in panel: strip .0 suffix and zero-pad to 8 chars
    panel = panel.copy()
    panel["_opeid_str"] = (
        panel["opeid"].astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(8)
    )
    frc_lookup = frc.rename(columns={"year": "year_num"})
    merged = panel.merge(
        frc_lookup[["opeid", "year_num", "frc_score"]],
        left_on=["_opeid_str", "year_num"],
        right_on=["opeid", "year_num"],
        how="left",
        suffixes=("", "_frc"),
    )
    # Drop helper columns
    merged = merged.drop(columns=["_opeid_str"] + [c for c in merged.columns if c.endswith("_frc")])
    return merged


def get_sector_dummies(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c.startswith("sec_")]


def get_state_dummies(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c.startswith("st_")]


def get_year_dummies(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c.startswith("yr_")]


def make_binned_features(df: pd.DataFrame, fit_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Replace BINNED_VARS with quartile dummies + missing indicator."""
    source = fit_df if fit_df is not None else df
    result = df.copy()
    for var in BINNED_VARS:
        if var not in df.columns:
            continue
        result[f"{var}_missing"] = df[var].isna().astype(float)
        src_vals = source[var].dropna()
        q25, q50, q75 = src_vals.quantile([0.25, 0.5, 0.75])
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
    """Split 75/25 by institution, stratified by ever-closed."""
    inst = panel.groupby("unitid")[outcome].max().reset_index()
    inst.columns = ["unitid", "ever_closed"]
    train_units, test_units = train_test_split(
        inst["unitid"], test_size=test_size, random_state=random_state,
        stratify=inst["ever_closed"],
    )
    return panel["unitid"].isin(train_units), panel["unitid"].isin(test_units)


def safe_auc(y_true, y_score) -> float | None:
    """Return AUC or None if both classes not present."""
    y_true = np.asarray(y_true).astype(float)
    if len(np.unique(y_true[~np.isnan(y_true)])) < 2:
        return None
    valid = ~(np.isnan(y_true) | np.isnan(y_score))
    if valid.sum() < 10:
        return None
    return roc_auc_score(y_true[valid], y_score[valid])


def n_predicted_youden(y_true: np.ndarray, y_score: np.ndarray) -> int:
    """
    Count predicted positives at the Youden's J optimal threshold.
    Applied to all non-NaN predictions (including test rows where y_true may be 0 or 1).
    """
    valid = ~(np.isnan(y_true) | np.isnan(y_score))
    if valid.sum() < 10 or len(np.unique(y_true[valid])) < 2:
        return 0
    fpr, tpr, thresholds = roc_curve(y_true[valid], y_score[valid])
    threshold = thresholds[np.argmax(tpr - fpr)]
    non_nan_scores = y_score[~np.isnan(y_score)]
    return int((non_nan_scores >= threshold).sum())


def _clean(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(float)
    arr[np.isposinf(arr) | np.isneginf(arr)] = np.nan
    return arr


def run_ols(X_train, y_train, X_test) -> np.ndarray:
    X_train = _clean(X_train)
    X_test = _clean(X_test)
    valid_tr = (~np.isnan(X_train).any(axis=1)) & (~np.isnan(y_train))
    model = LinearRegression()
    model.fit(X_train[valid_tr], y_train[valid_tr])
    valid_te = ~np.isnan(X_test).any(axis=1)
    preds = np.full(len(X_test), np.nan)
    preds[valid_te] = model.predict(X_test[valid_te])
    return preds


def run_lasso_ols(X_train, y_train, X_test, X_test_full, all_feature_names) -> np.ndarray:
    X_train = _clean(X_train)
    X_test_full = _clean(X_test_full)
    valid = (~np.isnan(X_train).any(axis=1)) & (~np.isnan(y_train))
    lasso = LassoCV(cv=5, random_state=42, max_iter=5000, n_jobs=-1)
    lasso.fit(X_train[valid], y_train[valid])
    selected_mask = lasso.coef_ != 0
    if selected_mask.sum() == 0:
        selected_mask = np.ones(len(lasso.coef_), dtype=bool)
    ols = LinearRegression()
    ols.fit(X_train[valid][:, selected_mask], y_train[valid])
    X_sel = X_test_full[:, selected_mask]
    valid_test = ~np.isnan(X_sel).any(axis=1)
    preds = np.full(len(X_sel), np.nan)
    preds[valid_test] = ols.predict(X_sel[valid_test])
    return preds


def run_xgboost(X_train, y_train, X_test, scale_pos_weight: float | None = None):
    X_train = _clean(X_train)
    X_test = _clean(X_test)
    valid = ~np.isnan(y_train)
    X_tr = X_train[valid]
    y_tr = y_train[valid].astype(int)

    n_val = max(100, int(0.1 * len(y_tr)))
    rng = np.random.default_rng(42)
    val_idx = rng.choice(len(y_tr), size=n_val, replace=False)
    train_idx = np.setdiff1d(np.arange(len(y_tr)), val_idx)

    dtrain = xgb.DMatrix(X_tr[train_idx], label=y_tr[train_idx])
    dval = xgb.DMatrix(X_tr[val_idx], label=y_tr[val_idx])
    dtest = xgb.DMatrix(X_test)

    xgb_params = {
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "seed": 42,
        "nthread": -1,
        "eval_metric": "logloss",
        "objective": "binary:logistic",
    }
    if scale_pos_weight is not None:
        xgb_params["scale_pos_weight"] = scale_pos_weight

    booster = xgb.train(
        xgb_params, dtrain,
        num_boost_round=400,
        evals=[(dval, "val")],
        early_stopping_rounds=30,
        verbose_eval=False,
    )
    return booster.predict(dtest), booster


def _fmt_auc(auc) -> str:
    return f"{auc:.1%}" if auc is not None else "N/A"


def run_models(
    panel: pd.DataFrame,
    outcome: str,
    sample_label: str,
    train_mask=None,
    test_mask=None,
) -> tuple[list[dict], pd.Series, pd.Series]:
    """
    Run models A–F for one outcome and sample.
    Returns (results, train_mask, test_mask) so the caller can reuse the same split.
    """
    print(f"\n  Outcome: {outcome}  |  Sample: {sample_label}")
    print(f"  Panel rows: {len(panel):,}  |  Positive rate: {panel[outcome].mean():.3%}")

    if train_mask is None or test_mask is None:
        train_mask, test_mask = train_test_split_by_institution(panel, outcome)

    train = panel[train_mask].copy()
    test = panel[test_mask].copy()

    sec_dummies = get_sector_dummies(panel)
    yr_dummies = get_year_dummies(panel)

    n_neg = (train[outcome] == 0).sum()
    n_pos = (train[outcome] == 1).sum()
    spw = n_neg / max(n_pos, 1)

    results = []

    # ---- Model A: OLS, Select Continuous ----
    feats_a = [f for f in SELECT_CONTINUOUS + sec_dummies + yr_dummies if f in panel.columns]
    X_tr = train[feats_a].values
    y_tr = train[outcome].values.astype(float)
    X_te = test[feats_a].values
    y_te = test[outcome].values.astype(float)

    preds_a = run_ols(X_tr, y_tr, X_te)
    valid_a = ~np.isnan(preds_a)
    auc_a = safe_auc(y_te[valid_a], preds_a[valid_a])
    n_obs_a = int(valid_a.sum())
    n_close_a = int(y_te[valid_a].sum())
    n_pred_a = n_predicted_youden(y_te[valid_a], preds_a[valid_a])
    print(f"    A  OLS/Continuous:       AUC={_fmt_auc(auc_a)}  N={n_obs_a:,}  pred={n_pred_a}  actual={n_close_a}")
    results.append(dict(
        model_type="Linear Probability", controls="Select Continuous", letter="A",
        outcome=outcome, sample=sample_label,
        auc=auc_a, n_obs=n_obs_a, n_predicted=n_pred_a, n_closures=n_close_a,
    ))

    # ---- Model B: LASSO→OLS, Select Continuous ----
    feats_b = [f for f in SELECT_CONTINUOUS + sec_dummies + yr_dummies if f in panel.columns]
    X_tr_b = train[feats_b].values
    X_te_b = test[feats_b].values

    preds_b = run_lasso_ols(X_tr_b, y_tr, X_te_b, X_te_b, feats_b)
    valid_b = ~np.isnan(preds_b)
    auc_b = safe_auc(y_te[valid_b], preds_b[valid_b])
    n_obs_b = int(valid_b.sum())
    n_close_b = int(y_te[valid_b].sum())
    n_pred_b = n_predicted_youden(y_te[valid_b], preds_b[valid_b])
    print(f"    B  LASSO→OLS/Continuous: AUC={_fmt_auc(auc_b)}  N={n_obs_b:,}  pred={n_pred_b}  actual={n_close_b}")
    results.append(dict(
        model_type="Linear Probability – LASSO", controls="Select Continuous", letter="B",
        outcome=outcome, sample=sample_label,
        auc=auc_b, n_obs=n_obs_b, n_predicted=n_pred_b, n_closures=n_close_b,
    ))

    # ---- Model C: OLS, Select Binned ----
    train_binned = make_binned_features(train, fit_df=train)
    test_binned = make_binned_features(test, fit_df=train)

    binned_cols = [c for c in train_binned.columns
                   if any(c.startswith(v + "_q") or c.startswith(v + "_miss") for v in BINNED_VARS)]
    binned_lags = [f for f in train_binned.columns
                   if any(f == v for v in SELECT_CONTINUOUS if v not in BINNED_VARS)]
    feats_c = [f for f in binned_cols + binned_lags + sec_dummies + yr_dummies
               if f in train_binned.columns]

    X_tr_c = np.nan_to_num(train_binned[feats_c].values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    y_tr_c = train_binned[outcome].values.astype(float)
    X_te_c = np.nan_to_num(test_binned[feats_c].values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    y_te_c = test_binned[outcome].values.astype(float)

    preds_c = run_ols(X_tr_c, y_tr_c, X_te_c)
    auc_c = safe_auc(y_te_c, preds_c)
    n_obs_c = len(y_te_c)
    n_close_c = int(y_te_c.sum())
    n_pred_c = n_predicted_youden(y_te_c, preds_c)
    print(f"    C  OLS/Binned:           AUC={_fmt_auc(auc_c)}  N={n_obs_c:,}  pred={n_pred_c}  actual={n_close_c}")
    results.append(dict(
        model_type="Linear Probability", controls="Select Binned", letter="C",
        outcome=outcome, sample=sample_label,
        auc=auc_c, n_obs=n_obs_c, n_predicted=n_pred_c, n_closures=n_close_c,
    ))

    # ---- Model D: XGBoost, Select Binned ----
    preds_d, _ = run_xgboost(X_tr_c, y_tr_c, X_te_c, scale_pos_weight=spw)
    auc_d = safe_auc(y_te_c, preds_d)
    n_pred_d = n_predicted_youden(y_te_c, preds_d)
    print(f"    D  XGB/Binned:           AUC={_fmt_auc(auc_d)}  N={n_obs_c:,}  pred={n_pred_d}  actual={n_close_c}")
    results.append(dict(
        model_type="Gradient Boosting", controls="Select Binned", letter="D",
        outcome=outcome, sample=sample_label,
        auc=auc_d, n_obs=n_obs_c, n_predicted=n_pred_d, n_closures=n_close_c,
    ))

    # ---- Model E: XGBoost, Select Continuous ----
    X_tr_e = train[feats_a].values
    X_te_e = test[feats_a].values
    preds_e, _ = run_xgboost(X_tr_e, y_tr, X_te_e, scale_pos_weight=spw)
    auc_e = safe_auc(y_te, preds_e)
    n_obs_e = len(y_te)
    n_close_e = int(y_te.sum())
    n_pred_e = n_predicted_youden(y_te, preds_e)
    print(f"    E  XGB/Continuous:       AUC={_fmt_auc(auc_e)}  N={n_obs_e:,}  pred={n_pred_e}  actual={n_close_e}")
    results.append(dict(
        model_type="Gradient Boosting", controls="Select Continuous", letter="E",
        outcome=outcome, sample=sample_label,
        auc=auc_e, n_obs=n_obs_e, n_predicted=n_pred_e, n_closures=n_close_e,
    ))

    # ---- Model F: XGBoost, All Controls ----
    all_feats = [f for f in SELECT_CONTINUOUS + EXTENDED_VARS + sec_dummies + yr_dummies
                 if f in panel.columns]
    X_tr_f = train[all_feats].values
    X_te_f = test[all_feats].values
    preds_f, booster_f = run_xgboost(X_tr_f, y_tr, X_te_f, scale_pos_weight=spw)
    auc_f = safe_auc(y_te, preds_f)
    n_pred_f = n_predicted_youden(y_te, preds_f)
    print(f"    F  XGB/All Controls:     AUC={_fmt_auc(auc_f)}  N={n_obs_e:,}  pred={n_pred_f}  actual={n_close_e}")
    results.append(dict(
        model_type="Gradient Boosting", controls="All", letter="F",
        outcome=outcome, sample=sample_label,
        auc=auc_f, n_obs=n_obs_e, n_predicted=n_pred_f, n_closures=n_close_e,
        _booster_f=booster_f, _feats_f=all_feats,
    ))

    return results, train_mask, test_mask


def run_federal_metrics(
    panel: pd.DataFrame,
    outcome: str,
    sample_label: str,
    train_mask: pd.Series,
    test_mask: pd.Series,
) -> list[dict]:
    """
    Run Federal Metrics models (OLS + XGBoost) using FRC composite score.
    Subset to rows where frc_score is available.
    Uses the same institution-level train/test split as run_models().
    """
    if "frc_score" not in panel.columns or panel["frc_score"].isna().all():
        print(f"    FRC: No data — skipping Federal Metrics rows")
        return []

    sec_dummies = get_sector_dummies(panel)
    yr_dummies = get_year_dummies(panel)
    frc_feats = [f for f in ["frc_score"] + sec_dummies + yr_dummies if f in panel.columns]

    # Apply same institution split, then restrict to FRC-available rows
    train_all = panel[train_mask].copy()
    test_all = panel[test_mask].copy()

    train_frc = train_all[train_all["frc_score"].notna()].copy()
    test_frc = test_all[test_all["frc_score"].notna()].copy()

    if len(test_frc) < 50 or test_frc[outcome].sum() == 0:
        print(f"    FRC: Insufficient test data — skipping")
        return []

    print(f"    FRC test rows: {len(test_frc):,}  closures: {int(test_frc[outcome].sum())}")

    results = []
    y_tr = train_frc[outcome].values.astype(float)
    y_te = test_frc[outcome].values.astype(float)
    X_tr = train_frc[frc_feats].values.astype(float)
    X_te = test_frc[frc_feats].values.astype(float)

    n_neg = (train_frc[outcome] == 0).sum()
    n_pos = (train_frc[outcome] == 1).sum()
    spw = n_neg / max(n_pos, 1)

    # G: OLS, Federal Metrics
    preds_g = run_ols(X_tr, y_tr, X_te)
    valid_g = ~np.isnan(preds_g)
    auc_g = safe_auc(y_te[valid_g], preds_g[valid_g])
    n_obs_g = int(valid_g.sum())
    n_close_g = int(y_te[valid_g].sum())
    n_pred_g = n_predicted_youden(y_te[valid_g], preds_g[valid_g])
    print(f"    G  OLS/FedMetrics:       AUC={_fmt_auc(auc_g)}  N={n_obs_g:,}  pred={n_pred_g}")
    results.append(dict(
        model_type="Linear Probability", controls="Federal Metrics", letter="G",
        outcome=outcome, sample=sample_label,
        auc=auc_g, n_obs=n_obs_g, n_predicted=n_pred_g, n_closures=n_close_g,
    ))

    # H: XGBoost, Federal Metrics
    X_tr_h = np.nan_to_num(X_tr.astype(float), nan=0.0)
    X_te_h = np.nan_to_num(X_te.astype(float), nan=0.0)
    preds_h, _ = run_xgboost(X_tr_h, y_tr, X_te_h, scale_pos_weight=spw)
    auc_h = safe_auc(y_te, preds_h)
    n_obs_h = len(y_te)
    n_pred_h = n_predicted_youden(y_te, preds_h)
    print(f"    H  XGB/FedMetrics:       AUC={_fmt_auc(auc_h)}  N={n_obs_h:,}  pred={n_pred_h}")
    results.append(dict(
        model_type="Gradient Boosting", controls="Federal Metrics", letter="H",
        outcome=outcome, sample=sample_label,
        auc=auc_h, n_obs=n_obs_h, n_predicted=n_pred_h, n_closures=int(y_te.sum()),
    ))

    return results


def print_paper_style_table(all_results: list[dict]) -> None:
    """
    Print results in the exact 9-column format of Table 5 in the paper.
    Columns: Sample | Model | Controls |
             Pred Closures (pt) | AUC (pt) | N (pt) |
             Pred Closures (3yr) | AUC (3yr) | N (3yr)
    """
    OUT_A = "closed_in_year_lead1"
    OUT_B = "closed_within_3yr_lead"

    # Build lookup: (sample, letter, outcome) -> result dict
    lookup = {}
    for r in all_results:
        key = (r["sample"], r["letter"], r["outcome"])
        lookup[key] = r

    # Determine row order per sample
    sample_order = {}
    for r in all_results:
        s = r["sample"]
        if s not in sample_order:
            sample_order[s] = []
        key = (r["letter"], r["controls"])
        if key not in sample_order[s]:
            sample_order[s].append(key)

    hdr1 = f"{'Sample':<12} {'Model':<28} {'Controls':<20}"
    hdr2 = f"{'Pred Closures':>14} {'AUC':>8} {'N':>8}  {'Pred Closures':>14} {'AUC':>8} {'N':>8}"
    hdr3 = f"{'':12} {'':28} {'':20} {'(point in time)':>31}  {'(within 3 yrs)':>31}"
    sep = "─" * (12 + 28 + 20 + 31 + 2 + 31)

    print(f"\n{'Table 5 – Predictive Accuracy for Linear Regression and XGBoost Models':^{len(sep)}}")
    print(sep)
    print(hdr3)
    print(hdr1 + hdr2)
    print(sep)

    for s_idx, (sample, row_keys) in enumerate(sample_order.items()):
        if s_idx > 0:
            print()
        sample_shown = False
        for letter, controls in row_keys:
            r_a = lookup.get((sample, letter, OUT_A))
            r_b = lookup.get((sample, letter, OUT_B))
            if r_a is None and r_b is None:
                continue
            model_type = (r_a or r_b)["model_type"]
            sample_str = sample if not sample_shown else ""
            sample_shown = True

            def fmt_a(r):
                if r is None:
                    return f"{'—':>14} {'—':>8} {'—':>8}"
                pred = f"{r['n_predicted']:,}" if r['n_predicted'] else "—"
                auc = _fmt_auc(r["auc"])
                n = f"{r['n_obs']:,}"
                return f"{pred:>14} {auc:>8} {n:>8}"

            row = (f"{sample_str:<12} {model_type:<28} {controls:<20}"
                   f"  {fmt_a(r_a)}  {fmt_a(r_b)}")
            print(row)
    print(sep)


def build_csv(all_results: list[dict]) -> pd.DataFrame:
    """Build flat CSV matching the 9-column structure."""
    OUT_A = "closed_in_year_lead1"
    OUT_B = "closed_within_3yr_lead"

    seen = set()
    rows = []
    for r in all_results:
        key = (r["sample"], r["letter"])
        if key in seen:
            continue
        seen.add(key)

        r_a = next((x for x in all_results if x["sample"] == r["sample"]
                    and x["letter"] == r["letter"] and x["outcome"] == OUT_A), None)
        r_b = next((x for x in all_results if x["sample"] == r["sample"]
                    and x["letter"] == r["letter"] and x["outcome"] == OUT_B), None)

        rows.append({
            "Sample": r["sample"],
            "Model": r["model_type"],
            "Controls": r["controls"],
            "Pred_Closures_pt": r_a["n_predicted"] if r_a else None,
            "AUC_pt": _fmt_auc(r_a["auc"]) if r_a else None,
            "N_pt": r_a["n_obs"] if r_a else None,
            "Pred_Closures_3yr": r_b["n_predicted"] if r_b else None,
            "AUC_3yr": _fmt_auc(r_b["auc"]) if r_b else None,
            "N_3yr": r_b["n_obs"] if r_b else None,
        })
    return pd.DataFrame(rows)


def main():
    print("Loading panel...")
    panel = load_panel()
    print(f"  {len(panel):,} rows, {panel['unitid'].nunique():,} institutions")
    print(f"  Years: {panel['year_num'].min()}–{panel['year_num'].max()}")
    print(f"  closed_in_year_lead1=1: {(panel['closed_in_year_lead1']==1).sum():,}")
    print(f"  closed_within_3yr_lead=1: {(panel['closed_within_3yr_lead']==1).sum():,}")

    print("\nLoading FRC scores...")
    frc = load_frc()
    if frc.empty:
        print("  No FRC data found — Federal Metrics rows will be skipped")
    else:
        print(f"  FRC rows: {len(frc):,} across {frc['year'].nunique()} years "
              f"({frc['year'].min()}–{frc['year'].max()})")
    panel = merge_frc(panel, frc)
    frc_cov = panel["frc_score"].notna().mean()
    print(f"  FRC coverage in panel: {frc_cov:.1%}")

    outcomes = ["closed_in_year_lead1", "closed_within_3yr_lead"]
    all_results = []

    # ── Sample 1: 2002–2023 (full) ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("SAMPLE: 2002–2023 (full)")
    print(f"{'='*60}")
    full_panel = panel.copy()

    for outcome in outcomes:
        results, tr_mask, te_mask = run_models(full_panel, outcome, "2002–2023")
        # Store masks for reuse (both outcomes use same institution split for comparability)
        if outcome == outcomes[0]:
            tr_mask_full = tr_mask
            te_mask_full = te_mask
        all_results.extend(results)

    # ── Sample 2: 2006–2020 ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("SAMPLE: 2006–2020")
    print(f"{'='*60}")
    sub_panel = panel[panel["year_num"] >= 2006].copy()
    print(f"  Sub-panel rows: {len(sub_panel):,}")

    for outcome in outcomes:
        # Federal Metrics first (paper order)
        fed_results = run_federal_metrics(
            sub_panel, outcome, "2006–2020",
            tr_mask_full.reindex(sub_panel.index, fill_value=False),
            te_mask_full.reindex(sub_panel.index, fill_value=False),
        )
        all_results.extend(fed_results)

        results, _, _ = run_models(sub_panel, outcome, "2006–2020")
        all_results.extend(results)

    # ── Print paper-style table ───────────────────────────────────────────────
    print_paper_style_table(all_results)

    # ── Paper targets for comparison ─────────────────────────────────────────
    print(f"\n{'Paper targets (Kelchen, Ritter & Webber 2025):':}")
    paper_rows = [
        # 2002-2023
        ("2002–2023","A","Linear Probability",      "Select Continuous","16","78.7%","2,990","32","81.8%","2,062"),
        ("2002–2023","B","Linear Probability–LASSO","Select Continuous","35","83.4%","3,415","59","84.4%","2,353"),
        ("2002–2023","C","Linear Probability",      "Select Binned",    "327","75.6%","20,596","1,172","76.2%","18,073"),
        ("2002–2023","D","Gradient Boosting",       "Select Binned",    "267","76.9%","20,596","1,073","80.6%","18,073"),
        ("2002–2023","E","Gradient Boosting",       "Select Continuous","253","80.6%","20,596","1,060","82.8%","18,073"),
        ("2002–2023","F","Gradient Boosting",       "All",              "231","81.8%","20,596","1,023","86.8%","18,073"),
        # 2006-2020
        ("2006–2020","G","Linear Probability",      "Federal Metrics",  "158","76.5%","10,331","586","78.8%","9,107"),
        ("2006–2020","H","Gradient Boosting",       "Federal Metrics",  "257","77.4%","16,800","978","79.5%","14,240"),
        ("2006–2020","A","Linear Probability",      "Select Continuous","16","78.7%","2,990","32","81.8%","2,062"),
        ("2006–2020","B","Linear Probability–LASSO","Select Continuous","35","83.3%","3,414","59","84.4%","2,352"),
        ("2006–2020","C","Linear Probability",      "Select Binned",    "291","75.9%","16,800","1,037","77.4%","14,240"),
        ("2006–2020","D","Gradient Boosting",       "Select Binned",    "234","78.5%","16,800","940","82.2%","14,240"),
        ("2006–2020","E","Gradient Boosting",       "Select Continuous","219","81.5%","16,800","930","83.7%","14,240"),
        ("2006–2020","F","Gradient Boosting",       "All",              "197","83.1%","16,800","893","88.6%","14,240"),
    ]
    sep = "─" * 123
    print(sep)
    print(f"{'Sample':<12} {'Model':<28} {'Controls':<20}  {'Pred':>6} {'AUC':>7} {'N':>8}  {'Pred':>6} {'AUC':>7} {'N':>8}")
    print(sep)
    prev_sample = None
    for row in paper_rows:
        s, _, m, c, pa, au_a, n_a, pb, au_b, n_b = row
        if s != prev_sample and prev_sample is not None:
            print()
        prev_sample = s
        s_str = s if (row == paper_rows[0] or paper_rows[paper_rows.index(row)-1][0] != s) else ""
        print(f"{s_str:<12} {m:<28} {c:<20}  {pa:>6} {au_a:>7} {n_a:>8}  {pb:>6} {au_b:>7} {n_b:>8}")
    print(sep)

    # ── Save outputs ──────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "replicated_table5.csv"
    build_csv(all_results).to_csv(csv_path, index=False)
    print(f"\nSaved: {csv_path}")

    # Save XGBoost All-Controls models
    model_dir = Path("analysis/models")
    model_dir.mkdir(parents=True, exist_ok=True)
    for r in all_results:
        if r.get("letter") == "F" and r.get("sample") == "2002–2023" and "_booster_f" in r:
            outcome_key = r["outcome"]
            suffix = "1yr" if "lead1" in outcome_key else "3yr"
            booster = r["_booster_f"]
            booster.feature_names = r["_feats_f"]
            save_path = model_dir / f"xgb_close_{suffix}.json"
            booster.save_model(str(save_path))
            print(f"Saved model: {save_path}")


if __name__ == "__main__":
    main()
