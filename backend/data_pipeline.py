"""End-to-end PaySim preprocessing and analytics pipeline.

Run from the project root with: python backend/data_pipeline.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from .analytics import calculate_business_analytics, create_process_analysis
except ImportError:  # Supports direct execution: python backend/data_pipeline.py
    from analytics import calculate_business_analytics, create_process_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "PS_20174392719_1491204439457_log.csv"
OUTPUT_DIR = PROJECT_ROOT / "backend" / "output"
MAX_PROCESSED_ROWS = 250_000
REQUIRED_COLUMNS = [
    "step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud",
]


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load PaySim with compact, explicit dtypes."""
    dtypes = {
        "step": "int32", "type": "category", "amount": "float64",
        "nameOrig": "string", "oldbalanceOrg": "float64", "newbalanceOrig": "float64",
        "nameDest": "string", "oldbalanceDest": "float64", "newbalanceDest": "float64",
        "isFraud": "int8", "isFlaggedFraud": "int8",
    }
    if not path.exists():
        raise FileNotFoundError(f"PaySim CSV not found: {path}")
    df = pd.read_csv(path, dtype=dtypes)
    missing_required = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if missing_required:
        raise ValueError(f"Missing required PaySim columns: {missing_required}")
    return df


def inspect_data(df: pd.DataFrame) -> dict[str, Any]:
    """Capture source-data quality and distribution information."""
    numeric = df.select_dtypes(include=[np.number])
    return {
        "row_count": int(len(df)),
        "columns": df.columns.tolist(),
        "missing_values": {key: int(value) for key, value in df.isna().sum().items()},
        "transaction_types": {str(key): int(value) for key, value in df["type"].value_counts().items()},
        "fraud_distribution": {str(key): int(value) for key, value in df["isFraud"].value_counts().sort_index().items()},
        "basic_statistics": json.loads(numeric.describe().to_json()),
    }


def clean_and_engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Remove invalid records and create analytical features from source fields."""
    cleaned = df.drop_duplicates().copy()
    monetary = ["amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]
    cleaned = cleaned[(cleaned[monetary] >= 0).all(axis=1)].copy()
    cleaned = cleaned[cleaned["amount"].notna() & cleaned["type"].notna()].copy()
    if cleaned.empty:
        raise ValueError("No valid rows remain after cleaning")

    # PaySim's step is an hourly time index, so hour-of-day is step modulo 24.
    cleaned["transaction_hour"] = (cleaned["step"] % 24).astype("int8")
    cleaned["transaction_amount_log"] = np.log1p(cleaned["amount"])
    cleaned["amount_bucket"] = pd.cut(
        cleaned["amount"], bins=[-np.inf, 100, 1_000, 10_000, 100_000, np.inf],
        labels=["very_low", "low", "medium", "high", "very_high"],
    ).astype("string")
    cleaned["balance_change_origin"] = cleaned["oldbalanceOrg"] - cleaned["newbalanceOrig"]
    cleaned["balance_change_destination"] = cleaned["newbalanceDest"] - cleaned["oldbalanceDest"]
    category_map = {
        "PAYMENT": "payment", "TRANSFER": "funds_movement", "CASH_OUT": "funds_movement",
        "CASH_IN": "deposit", "DEBIT": "debit",
    }
    cleaned["transaction_category"] = cleaned["type"].map(category_map).fillna("other").astype("string")
    cleaned["source_row_validated"] = True
    cleaned.attrs["rows_removed_during_cleaning"] = int(len(df) - len(cleaned))
    return cleaned


def save_outputs(
    df: pd.DataFrame, inspection: dict[str, Any], metrics: dict[str, Any],
    process_df: pd.DataFrame, bottleneck: str,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Deterministic capped extract for API/dashboard development; metrics use all rows.
    export_df = df.sample(n=MAX_PROCESSED_ROWS, random_state=42) if len(df) > MAX_PROCESSED_ROWS else df
    export_df.to_csv(OUTPUT_DIR / "processed_transactions.csv", index=False)
    process_df.to_csv(OUTPUT_DIR / "process_analysis.csv", index=False)
    with (OUTPUT_DIR / "inspection.json").open("w", encoding="utf-8") as handle:
        json.dump(inspection, handle, indent=2, default=str)
    summary = {
        "dataset": "PaySim synthetic financial transaction dataset",
        "source_file": str(DATA_PATH.relative_to(PROJECT_ROOT)),
        "rows_processed": int(len(df)),
        "rows_removed_during_cleaning": int(df.attrs.get("rows_removed_during_cleaning", 0)),
        "processed_extract_rows": int(len(export_df)),
        "metrics": metrics,
        "process_analysis": process_df.to_dict(orient="records"),
        "identified_bottleneck": bottleneck,
        "operational_data_notice": "Processing times, departments, SLA metrics, and operational costs are DERIVED/SIMULATED analytical assumptions, not PaySim observations or real banking data.",
        "ml_status": "No fraud model trained in this preprocessing stage.",
    }
    with (OUTPUT_DIR / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)


def run_pipeline() -> dict[str, Any]:
    raw = load_data()
    inspection = inspect_data(raw)
    cleaned = clean_and_engineer_features(raw)
    metrics = calculate_business_analytics(cleaned)
    process_df, bottleneck = create_process_analysis(cleaned, metrics["fraud_rate"])
    save_outputs(cleaned, inspection, metrics, process_df, bottleneck)
    return {"inspection": inspection, "metrics": metrics, "bottleneck": bottleneck}


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps({
        "rows_processed": result["metrics"]["total_transactions"],
        "fraud_rate": result["metrics"]["fraud_rate"],
        "top_transaction_types": result["metrics"]["transaction_volume_by_type"][:5],
        "bottleneck": result["bottleneck"],
        "output_directory": str(OUTPUT_DIR),
    }, indent=2))
