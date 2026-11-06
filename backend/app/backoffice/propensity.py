"""Lead propensity: probability that a lead activates, from facts known when the lead arrives.

Only profile and source features are used (no stage, dates, drop reason or outcome), so there is no
leakage from what happened later. Trained on smb_leads.csv; cross-validated AUC is reported, not assumed.
The score decides WHERE HUMAN EFFORT GOES (which stalled leads to call first). It never changes a price.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app import config

CATEGORICAL = ["lead_source", "segment", "preferred_language", "annual_turnover_band", "has_gstin", "has_udyam",
               "current_internet", "current_provider", "contact_role"]
NUMERIC = ["city_tier", "employee_count", "num_sites", "monthly_telecom_spend_inr", "n_interest"]


def _frame(df: pd.DataFrame, columns: Optional[list[str]] = None) -> pd.DataFrame:
    d = df.copy()
    d["n_interest"] = d.get("products_of_interest", pd.Series([""] * len(d))).fillna("").astype(str) \
        .apply(lambda s: len([x for x in s.split(";") if x]))
    for c in CATEGORICAL:
        d[c] = d.get(c, pd.Series(["unknown"] * len(d))).fillna("unknown").astype(str)
    for c in NUMERIC:
        d[c] = pd.to_numeric(d.get(c, pd.Series([np.nan] * len(d))), errors="coerce")
    X = pd.get_dummies(d[CATEGORICAL + NUMERIC], columns=CATEGORICAL, dtype=float)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    return X


@lru_cache(maxsize=1)
def _model():
    df = pd.read_csv(config.LEADS_CSV)
    X = _frame(df)
    y = (df["outcome"] == "Activated").astype(int).to_numpy()
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, random_state=7)
    m.fit(X, y)
    return m, list(X.columns), df, X


@lru_cache(maxsize=1)
def evaluation() -> dict:
    """Honest out-of-fold estimate: AUC and lift (share of activations found by calling the top-scored leads)."""
    m, cols, df, X = _model()
    y = (df["outcome"] == "Activated").astype(int).to_numpy()
    est = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, random_state=7)
    oof = cross_val_predict(est, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=7), method="predict_proba")[:, 1]
    order = np.argsort(-oof)
    lift = {}
    for pct in (10, 20, 30):
        top = order[: int(len(y) * pct / 100)]
        lift[f"top_{pct}pct_leads_capture_pct_of_activations"] = round(100 * float(y[top].sum() / y.sum()), 1)
        lift[f"top_{pct}pct_activation_rate_pct"] = round(100 * float(y[top].mean()), 1)
    return {"cv_auc": round(float(roc_auc_score(y, oof)), 3), "base_rate_pct": round(100 * float(y.mean()), 2),
            "n_leads": int(len(y)), **lift, "features": CATEGORICAL + NUMERIC,
            "note": "5-fold out-of-fold predictions; profile and source features only (no leakage)."}


def score_dataset() -> pd.Series:
    """Activation probability for every lead in smb_leads.csv, indexed by lead_id."""
    m, cols, df, X = _model()
    return pd.Series(m.predict_proba(X)[:, 1], index=df["lead_id"])


def score_one(profile: dict) -> float:
    """Score a live lead from whatever is known (missing fields are left empty)."""
    m, cols, _, _ = _model()
    return float(m.predict_proba(_frame(pd.DataFrame([profile]), cols))[:, 1][0])
