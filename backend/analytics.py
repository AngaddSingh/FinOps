"""Business analytics for the PaySim FinOps Intelligence MVP.

All metrics are calculated from the PaySim synthetic transaction dataset.
This module deliberately does not train a fraud model.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate_business_analytics(df: pd.DataFrame) -> dict[str, Any]:
    """Return dashboard-ready descriptive metrics for a cleaned dataset."""
    total_transactions = int(len(df))
    total_value = float(df["amount"].sum())
    fraud_count = int(df["isFraud"].sum())
    fraud_rate = float(fraud_count / total_transactions) if total_transactions else 0.0

    by_type = (
        df.groupby("type", dropna=False, observed=False)
        .agg(transaction_count=("amount", "size"), transaction_value=("amount", "sum"), average_amount=("amount", "mean"))
        .reset_index()
        .sort_values("transaction_count", ascending=False)
    )
    by_type_records = [
        {key: (int(value) if isinstance(value, (np.integer,)) else float(value) if isinstance(value, (np.floating,)) else value)
         for key, value in row.items()}
        for row in by_type.to_dict(orient="records")
    ]

    trend = (
        df.groupby("step", as_index=False)
        .agg(transaction_count=("amount", "size"), transaction_value=("amount", "sum"), fraud_count=("isFraud", "sum"))
        .sort_values("step")
    )
    trend_records = [
        {key: (int(value) if isinstance(value, (np.integer,)) else float(value) if isinstance(value, (np.floating,)) else value)
         for key, value in row.items()}
        for row in trend.to_dict(orient="records")
    ]

    high_value_threshold = float(df["amount"].quantile(0.99)) if total_transactions else 0.0
    high_value = df[df["amount"] >= high_value_threshold]
    high_value_stats = {
        "threshold_99th_percentile": high_value_threshold,
        "transaction_count": int(len(high_value)),
        "total_value": float(high_value["amount"].sum()),
        "average_amount": float(high_value["amount"].mean()) if len(high_value) else 0.0,
        "fraud_count": int(high_value["isFraud"].sum()),
        "fraud_rate": float(high_value["isFraud"].mean()) if len(high_value) else 0.0,
    }

    return {
        "total_transactions": total_transactions,
        "total_transaction_value": total_value,
        "average_transaction_amount": float(df["amount"].mean()) if total_transactions else 0.0,
        "median_transaction_amount": float(df["amount"].median()) if total_transactions else 0.0,
        "transaction_types": sorted(df["type"].dropna().unique().tolist()),
        "transaction_volume_by_type": by_type_records,
        "transaction_value_by_type": [
            {"type": record["type"], "transaction_value": record["transaction_value"]}
            for record in by_type_records
        ],
        "fraud_count": fraud_count,
        "fraud_rate": fraud_rate,
        "fraud_distribution": {"legitimate": total_transactions - fraud_count, "fraudulent": fraud_count},
        "transaction_trends_by_step": trend_records,
        "high_value_transaction_statistics": high_value_stats,
    }


def create_process_analysis(df: pd.DataFrame, fraud_rate: float) -> tuple[pd.DataFrame, str]:
    """Build a deterministic, explicitly simulated process/SLA layer.

    PaySim has no operational timestamps, staff costs, departments, or SLAs.
    The values below are analytical assumptions, not observations of a real bank.
    """
    # DERIVED/SIMULATED: complexity proxies use transaction type and observed fraud rate.
    complexity = {"PAYMENT": 1.00, "CASH_IN": 0.85, "CASH_OUT": 1.25, "TRANSFER": 1.40, "DEBIT": 1.05}
    type_complexity = df["type"].map(complexity).fillna(1.0).astype(float)
    amount_complexity = np.clip(np.log1p(df["amount"]) / 12.0, 0.0, 1.5)
    risk_complexity = 1.0 + (df["isFraud"].astype(float) * 0.75) + (fraud_rate * 2.0)
    workload_index = type_complexity * (1.0 + amount_complexity * 0.25) * risk_complexity

    stages = [
        ("Transaction Initiated", "Payments Operations", 0.5, 1.0, 0.018),
        ("Verification", "Payments Operations", 2.0, 4.0, 0.032),
        ("Risk Assessment", "Financial Crime Operations", 5.0, 8.0, 0.055),
        ("Approval", "Payments Operations", 3.5, 6.0, 0.040),
        ("Settlement", "Treasury Operations", 2.5, 5.0, 0.027),
    ]
    # DERIVED/SIMULATED: targets and unit costs are illustrative assumptions.
    unit_costs = {
        "Transaction Initiated": 0.08, "Verification": 0.22,
        "Risk Assessment": 0.48, "Approval": 0.30, "Settlement": 0.35,
    }
    sample = pd.DataFrame({"workload_index": workload_index})
    if len(sample) > 250_000:
        sample = sample.sample(n=250_000, random_state=42)

    records: list[dict[str, Any]] = []
    for stage, department, base_time, sla_target, breach_proxy in stages:
        simulated_time = base_time * (0.85 + sample["workload_index"] * 0.15)
        average = float(simulated_time.mean())
        p95 = float(simulated_time.quantile(0.95))
        # DERIVED/SIMULATED: SLA breach rate is a modeled threshold comparison.
        breach_rate = max(float((simulated_time > sla_target).mean()), breach_proxy * (1.0 + fraud_rate * 10.0))
        cost_per_transaction = unit_costs[stage] * float(sample["workload_index"].mean())
        records.append({
            "stage_order": len(records) + 1,
            "stage": stage,
            "department": department,
            "transaction_count": int(len(df)),
            "average_processing_time_minutes": average,
            "p95_processing_time_minutes": p95,
            "sla_target_minutes": sla_target,
            "sla_breach_rate": min(breach_rate, 1.0),
            "simulated_operational_cost_per_transaction": cost_per_transaction,
            "simulated_total_operational_cost": cost_per_transaction * len(df),
            "assumption_status": "DERIVED/SIMULATED",
        })

    process_df = pd.DataFrame(records)
    bottleneck = str(process_df.loc[process_df["average_processing_time_minutes"].idxmax(), "stage"])
    return process_df, bottleneck
