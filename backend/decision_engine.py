"""Transparent decision-support calculations for the FinOps MVP.

All cost, savings, timing, and risk-change values in this module are
DERIVED/SIMULATED assumptions because PaySim contains no banking operations
cost or process-timing observations.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


ANNUALIZATION_FACTOR = 12  # DERIVED/SIMULATED: treats the PaySim period as a monthly run-rate.
AUTOMATION_IMPLEMENTATION_COST = 250_000.0  # DERIVED/SIMULATED currency units.
CAPACITY_IMPLEMENTATION_COST = 180_000.0  # DERIVED/SIMULATED currency units.
AUTOMATION_VERIFICATION_TIME_REDUCTION = 0.65
CAPACITY_RISK_TIME_REDUCTION = 0.20
AUTOMATION_SUPPORT_COST_PER_TRANSACTION = 0.03
CAPACITY_INCREMENTAL_COST_PER_TRANSACTION = 0.08


def _process_baseline(process_df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate the existing simulated process-analysis assumptions."""
    total_transactions = int(process_df["transaction_count"].iloc[0])
    process_df = process_df.copy()
    process_df["total_processing_minutes"] = (
        process_df["average_processing_time_minutes"] * process_df["transaction_count"]
    )
    return {
        "total_transactions": total_transactions,
        "total_processing_minutes": float(process_df["total_processing_minutes"].sum()),
        "total_operational_cost": float(process_df["simulated_total_operational_cost"].sum()),
        "average_processing_time_minutes": float(process_df["average_processing_time_minutes"].sum()),
        "stages": process_df,
    }


def _score_scenarios(scenarios: list[dict[str, Any]]) -> None:
    """Calculate comparable transparent scores; no recommendation is hard-coded."""
    max_improvement = max(item["projected_processing_time_improvement_percent"] for item in scenarios) or 1.0
    max_positive_savings = max(max(item["projected_annual_savings"], 0.0) for item in scenarios) or 1.0
    baseline_risk = scenarios[0]["risk_impact"]["projected_fraud_rate"]
    max_risk_reduction = max(
        max(baseline_risk - item["risk_impact"]["projected_fraud_rate"], 0.0)
        for item in scenarios
    ) or 1.0
    for item in scenarios:
        efficiency_score = item["projected_processing_time_improvement_percent"] / max_improvement
        cost_score = max(item["projected_annual_savings"], 0.0) / max_positive_savings
        risk_score = max(
            baseline_risk - item["risk_impact"]["projected_fraud_rate"], 0.0
        ) / max_risk_reduction
        item["decision_score"] = round(0.40 * efficiency_score + 0.35 * cost_score + 0.25 * risk_score, 6)
        item["score_components"] = {
            "efficiency_score": round(efficiency_score, 6),
            "cost_score": round(cost_score, 6),
            "risk_score": round(risk_score, 6),
            "weights": {"efficiency": 0.40, "cost": 0.35, "risk": 0.25},
        }


def calculate_decisions(
    summary: dict[str, Any],
    risk_metrics: dict[str, Any],
    process_df: pd.DataFrame,
) -> dict[str, Any]:
    """Return scenario projections and a calculated recommendation."""
    baseline = _process_baseline(process_df)
    risk_distribution = risk_metrics["risk_analytics"]["risk_distribution"]
    low_risk_count = int(risk_distribution["LOW"])
    total = baseline["total_transactions"]
    verification = process_df.loc[process_df["stage"] == "Verification"].iloc[0]
    risk_assessment = process_df.loc[process_df["stage"] == "Risk Assessment"].iloc[0]
    baseline_cost = baseline["total_operational_cost"]
    baseline_minutes = baseline["total_processing_minutes"]
    baseline_fraud_rate = float(risk_metrics["risk_analytics"]["fraud_rate"])

    scenarios = [{
        "scenario": "Current Process",
        "estimated_implementation_cost": 0.0,
        "projected_processing_time_improvement_minutes": 0.0,
        "projected_processing_time_improvement_percent": 0.0,
        "projected_operational_cost": baseline_cost,
        "projected_annual_operational_cost": baseline_cost * ANNUALIZATION_FACTOR,
        "projected_annual_savings": 0.0,
        "first_year_net_benefit": 0.0,
        "risk_impact": {
            "baseline_fraud_rate": baseline_fraud_rate,
            "projected_fraud_rate": baseline_fraud_rate,
            "fraud_rate_delta": 0.0,
            "interpretation": "Baseline risk posture.",
        },
        "assumption_status": "DERIVED/SIMULATED",
    }]

    automated_time_saved = (
        low_risk_count * float(verification["average_processing_time_minutes"])
        * AUTOMATION_VERIFICATION_TIME_REDUCTION
    )
    automated_cost_avoided = (
        low_risk_count * float(verification["simulated_operational_cost_per_transaction"])
        * AUTOMATION_VERIFICATION_TIME_REDUCTION
    )
    automated_support_cost = low_risk_count * AUTOMATION_SUPPORT_COST_PER_TRANSACTION
    automated_cost = baseline_cost - automated_cost_avoided + automated_support_cost
    automated_annual_savings = (baseline_cost - automated_cost) * ANNUALIZATION_FACTOR
    scenarios.append({
        "scenario": "Automate Low-Risk Verification",
        "estimated_implementation_cost": AUTOMATION_IMPLEMENTATION_COST,
        "projected_processing_time_improvement_minutes": automated_time_saved,
        "projected_processing_time_improvement_percent": automated_time_saved / baseline_minutes * 100,
        "projected_operational_cost": automated_cost,
        "projected_annual_operational_cost": automated_cost * ANNUALIZATION_FACTOR,
        "projected_annual_savings": automated_annual_savings,
        "first_year_net_benefit": automated_annual_savings - AUTOMATION_IMPLEMENTATION_COST,
        "risk_impact": {
            "baseline_fraud_rate": baseline_fraud_rate,
            "projected_fraud_rate": baseline_fraud_rate + 0.0002,
            "fraud_rate_delta": 0.0002,
            "interpretation": "DERIVED/SIMULATED slight control-risk increase from automating low-risk verification.",
        },
        "assumption_status": "DERIVED/SIMULATED",
    })

    capacity_time_saved = (
        total * float(risk_assessment["average_processing_time_minutes"])
        * CAPACITY_RISK_TIME_REDUCTION
    )
    capacity_variable_cost = total * CAPACITY_INCREMENTAL_COST_PER_TRANSACTION
    capacity_cost = baseline_cost + capacity_variable_cost
    capacity_annual_savings = (baseline_cost - capacity_cost) * ANNUALIZATION_FACTOR
    scenarios.append({
        "scenario": "Increase Manual Processing Capacity",
        "estimated_implementation_cost": CAPACITY_IMPLEMENTATION_COST,
        "projected_processing_time_improvement_minutes": capacity_time_saved,
        "projected_processing_time_improvement_percent": capacity_time_saved / baseline_minutes * 100,
        "projected_operational_cost": capacity_cost,
        "projected_annual_operational_cost": capacity_cost * ANNUALIZATION_FACTOR,
        "projected_annual_savings": capacity_annual_savings,
        "first_year_net_benefit": capacity_annual_savings - CAPACITY_IMPLEMENTATION_COST,
        "risk_impact": {
            "baseline_fraud_rate": baseline_fraud_rate,
            "projected_fraud_rate": max(baseline_fraud_rate - 0.0003, 0.0),
            "fraud_rate_delta": -0.0003,
            "interpretation": "DERIVED/SIMULATED risk reduction from additional manual review capacity.",
        },
        "assumption_status": "DERIVED/SIMULATED",
    })

    _score_scenarios(scenarios)
    recommended = max(scenarios, key=lambda item: item["decision_score"])
    return {
        "scenarios": scenarios,
        "recommended_scenario": recommended["scenario"],
        "recommendation_reason": (
            "Selected by the calculated weighted decision score: "
            "40% efficiency improvement, 35% annual savings, and 25% risk impact."
        ),
        "assumptions": {
            "status": "DERIVED/SIMULATED",
            "annualization_factor": ANNUALIZATION_FACTOR,
            "note": "PaySim contains no real operational costs, processing times, or annual financial run rate.",
        },
    }
