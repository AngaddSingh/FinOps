"""Explainable Random Forest fraud-risk engine for FinOps Intelligence.

This module intentionally excludes PaySim balance fields, fraud flags, and any
post-outcome information from prediction features.  It trains on the original
PaySim rows after the shared preprocessing/feature-engineering step.

Run from the project root:
    python backend/risk_model.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

try:
    from .data_pipeline import DATA_PATH, OUTPUT_DIR, clean_and_engineer_features, load_data
except ImportError:  # Supports direct execution: python backend/risk_model.py
    from data_pipeline import DATA_PATH, OUTPUT_DIR, clean_and_engineer_features, load_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "risk_model.joblib"
RISK_METRICS_PATH = OUTPUT_DIR / "risk_metrics.json"
RISK_SCORED_PATH = OUTPUT_DIR / "risk_scored_transactions.csv"

RANDOM_STATE = 42
MAX_MODEL_ROWS = 1_000_000
SCORED_SAMPLE_ROWS = 250_000

# Easy-to-modify business thresholds. These are application risk bands, not
# calibrated regulatory cutoffs.
LOW_RISK_THRESHOLD = 0.30
HIGH_RISK_THRESHOLD = 0.70

# Deliberately limited to information plausibly available at transaction time.
# isFraud, isFlaggedFraud, balance fields, and customer identifiers are excluded.
NUMERIC_FEATURES = ["amount", "transaction_hour", "transaction_amount_log"]
CATEGORICAL_FEATURES = ["type", "amount_bucket", "transaction_category"]
PREDICTION_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def select_model_sample(df: pd.DataFrame) -> pd.DataFrame:
    """Keep all fraud rows and a reproducible sample of legitimate rows.

    This is a compute-management step, not oversampling: no duplicate fraud
    rows are created, and train/test splitting happens after this selection.
    """
    if len(df) <= MAX_MODEL_ROWS:
        return df
    fraud = df[df["isFraud"] == 1]
    legitimate = df[df["isFraud"] == 0]
    legitimate_budget = max(MAX_MODEL_ROWS - len(fraud), 0)
    legitimate = legitimate.sample(n=min(legitimate_budget, len(legitimate)), random_state=RANDOM_STATE)
    return pd.concat([fraud, legitimate], ignore_index=True).sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)


def build_model() -> Pipeline:
    """Create the preprocessing and Random Forest pipeline."""
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])
    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    preprocessor = ColumnTransformer([
        ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
    ])
    # balanced_subsample gives each tree class-aware weights without duplicating
    # observations and is appropriate for PaySim's extreme class imbalance.
    classifier = RandomForestClassifier(
        n_estimators=120,
        max_features="sqrt",
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        # Single-process execution is intentional for restricted desktop
        # environments where joblib worker creation can fail with WinError 5.
        n_jobs=1,
        random_state=RANDOM_STATE,
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", classifier)])


def risk_level(risk_score: float) -> str:
    """Map a fraud probability to the dashboard's configurable risk band."""
    if risk_score < LOW_RISK_THRESHOLD:
        return "LOW"
    if risk_score < HIGH_RISK_THRESHOLD:
        return "MEDIUM"
    return "HIGH"


def _feature_importance_records(model: Pipeline, top_n: int = 10) -> list[dict[str, Any]]:
    preprocessor = model.named_steps["preprocessor"]
    classifier = model.named_steps["classifier"]
    names = preprocessor.get_feature_names_out()
    importances = classifier.feature_importances_
    order = np.argsort(importances)[::-1][:top_n]
    return [
        {"feature": str(names[index]), "importance": float(importances[index])}
        for index in order
    ]


def _top_risk_factors(model: Pipeline, row: pd.DataFrame, top_n: int = 3) -> list[str]:
    """Return transparent active-feature explanations.

    These are feature-importance-based indicators, not causal explanations or
    SHAP values. Categorical factors are reported when their one-hot value is
    active; numeric factors are reported with their transaction value.
    """
    preprocessor = model.named_steps["preprocessor"]
    classifier = model.named_steps["classifier"]
    transformed = preprocessor.transform(row)
    values = transformed.toarray()[0] if hasattr(transformed, "toarray") else transformed[0]
    names = preprocessor.get_feature_names_out()
    importances = classifier.feature_importances_
    active = np.where((values != 0) & (importances > 0))[0]
    ranked = active[np.argsort((np.abs(values[active]) * importances[active]))[::-1]]
    factors: list[str] = []
    for index in ranked:
        name = str(names[index]).replace("numeric__", "").replace("categorical__", "")
        factors.append(name)
        if len(factors) >= top_n:
            break
    return factors or ["No material active risk factor identified"]


def _prepare_prediction_row(transaction: Mapping[str, Any] | pd.Series) -> pd.DataFrame:
    """Create the six model inputs from a raw transaction-like mapping."""
    row = dict(transaction)
    amount = float(row.get("amount", 0.0))
    step = int(row.get("step", 0))
    transaction_type = str(row.get("type", "PAYMENT"))
    category_map = {
        "PAYMENT": "payment", "TRANSFER": "funds_movement",
        "CASH_OUT": "funds_movement", "CASH_IN": "deposit", "DEBIT": "debit",
    }
    if "transaction_hour" not in row:
        row["transaction_hour"] = step % 24
    if "transaction_amount_log" not in row:
        row["transaction_amount_log"] = float(np.log1p(max(amount, 0.0)))
    if "amount_bucket" not in row:
        row["amount_bucket"] = pd.cut(
            pd.Series([amount]), bins=[-np.inf, 100, 1_000, 10_000, 100_000, np.inf],
            labels=["very_low", "low", "medium", "high", "very_high"],
        ).astype("string").iloc[0]
    if "transaction_category" not in row:
        row["transaction_category"] = category_map.get(transaction_type, "other")
    return pd.DataFrame([{feature: row.get(feature) for feature in PREDICTION_FEATURES}])


def predict_transaction_risk(
    transaction: Mapping[str, Any] | pd.Series,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    """Predict one transaction's fraud probability and explainable factors."""
    artifact = joblib.load(model_path)
    model = artifact["model"] if isinstance(artifact, dict) else artifact
    row = _prepare_prediction_row(transaction)
    score = float(model.predict_proba(row)[0, 1])
    return {
        "risk_score": score,
        "risk_level": risk_level(score),
        "top_risk_factors": _top_risk_factors(model, row),
    }


def _risk_analytics(scored: pd.DataFrame) -> dict[str, Any]:
    """Calculate dashboard metrics from scores generated for every row."""
    total = len(scored)
    high = scored[scored["risk_level"] == "HIGH"]
    medium = scored[scored["risk_level"] == "MEDIUM"]
    low = scored[scored["risk_level"] == "LOW"]
    by_type = scored.groupby("type", observed=False).agg(
        transaction_count=("amount", "size"),
        transaction_volume=("amount", "sum"),
        fraud_count=("isFraud", "sum"),
        high_risk_count=("risk_level", lambda values: int((values == "HIGH").sum())),
        average_risk_score=("risk_score", "mean"),
    ).reset_index()
    by_type["fraud_rate"] = by_type["fraud_count"] / by_type["transaction_count"]
    top = high.nlargest(20, "risk_score")[
        ["step", "type", "amount", "nameOrig", "nameDest", "isFraud", "risk_score", "risk_level"]
    ]
    return {
        "total_transactions": int(total),
        "fraud_count": int(scored["isFraud"].sum()),
        "fraud_rate": float(scored["isFraud"].mean()),
        "high_risk_transaction_count": int(len(high)),
        "medium_risk_transaction_count": int(len(medium)),
        "low_risk_transaction_count": int(len(low)),
        "risk_distribution": {"LOW": int(len(low)), "MEDIUM": int(len(medium)), "HIGH": int(len(high))},
        "high_risk_transaction_volume": float(high["amount"].sum()),
        "risk_by_transaction_type": json.loads(by_type.to_json(orient="records")),
        "top_high_risk_transactions": json.loads(top.to_json(orient="records")),
    }


def train_and_evaluate() -> dict[str, Any]:
    """Train, evaluate, score all rows, and save all requested artifacts."""
    raw = load_data(DATA_PATH)
    engineered = clean_and_engineer_features(raw)
    model_data = select_model_sample(engineered)
    X = model_data[PREDICTION_FEATURES]
    y = model_data["isFraud"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_STATE, stratify=y,
    )

    model = build_model()
    model.fit(X_train, y_train)
    test_probability = model.predict_proba(X_test)[:, 1]
    test_prediction = (test_probability >= HIGH_RISK_THRESHOLD).astype(int)
    matrix = confusion_matrix(y_test, test_prediction, labels=[0, 1])
    metrics = {
        "model": "RandomForestClassifier",
        "features_used": PREDICTION_FEATURES,
        "excluded_features": [
            "isFraud", "isFlaggedFraud", "oldbalanceOrg", "newbalanceOrig",
            "oldbalanceDest", "newbalanceDest", "nameOrig", "nameDest",
        ],
        "class_imbalance_strategy": "class_weight=balanced_subsample; no pre-split oversampling",
        "random_state": RANDOM_STATE,
        "model_sample_rows": int(len(model_data)),
        "training_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "training_fraud_count": int(y_train.sum()),
        "test_fraud_count": int(y_test.sum()),
        "precision": float(precision_score(y_test, test_prediction, zero_division=0)),
        "recall": float(recall_score(y_test, test_prediction, zero_division=0)),
        "f1": float(f1_score(y_test, test_prediction, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, test_probability)),
        "pr_auc": float(average_precision_score(y_test, test_probability)),
        "confusion_matrix": matrix.tolist(),
        "risk_thresholds": {
            "LOW": f"risk_score < {LOW_RISK_THRESHOLD}",
            "MEDIUM": f"{LOW_RISK_THRESHOLD} <= risk_score < {HIGH_RISK_THRESHOLD}",
            "HIGH": f"risk_score >= {HIGH_RISK_THRESHOLD}",
        },
        "top_10_feature_importance": _feature_importance_records(model, top_n=10),
        "synthetic_data_notice": "PaySim is synthetic data; risk results are for portfolio demonstration only.",
    }

    # Score every cleaned transaction for complete analytics; only a capped
    # extract is persisted to keep the dashboard artifact manageable.
    scored = engineered.copy()
    scored["risk_score"] = model.predict_proba(scored[PREDICTION_FEATURES])[:, 1]
    scored["risk_level"] = scored["risk_score"].map(risk_level)
    metrics["risk_analytics"] = _risk_analytics(scored)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": model,
        "features_used": PREDICTION_FEATURES,
        "risk_thresholds": {"low": LOW_RISK_THRESHOLD, "high": HIGH_RISK_THRESHOLD},
        "top_10_feature_importance": metrics["top_10_feature_importance"],
    }, MODEL_PATH)
    with RISK_METRICS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, default=str)

    export_columns = [
        "step", "type", "amount", "nameOrig", "nameDest", "isFraud",
        "transaction_hour", "transaction_amount_log", "amount_bucket",
        "transaction_category", "risk_score", "risk_level",
    ]
    export = scored.sample(n=SCORED_SAMPLE_ROWS, random_state=RANDOM_STATE) if len(scored) > SCORED_SAMPLE_ROWS else scored
    export[export_columns].to_csv(RISK_SCORED_PATH, index=False)
    return metrics


if __name__ == "__main__":
    result = train_and_evaluate()
    analytics = result["risk_analytics"]
    print(json.dumps({
        "features_used": result["features_used"],
        "training_samples": result["training_samples"],
        "test_samples": result["test_samples"],
        "precision": result["precision"],
        "recall": result["recall"],
        "f1": result["f1"],
        "roc_auc": result["roc_auc"],
        "pr_auc": result["pr_auc"],
        "high_risk_transactions": analytics["high_risk_transaction_count"],
        "top_5_features": result["top_10_feature_importance"][:5],
        "model_path": str(MODEL_PATH),
        "metrics_path": str(RISK_METRICS_PATH),
        "scored_sample_path": str(RISK_SCORED_PATH),
    }, indent=2))
