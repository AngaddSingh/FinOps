"""FastAPI application for the FinOps Intelligence MVP backend."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .decision_engine import calculate_decisions


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_output_dir() -> Path:
    """Resolve output directory across local dev, Uvicorn, and Vercel serverless environments."""
    candidates = [
        PROJECT_ROOT / "backend" / "output",
        Path(__file__).resolve().parent / "output",
        Path.cwd() / "backend" / "output",
        Path.cwd() / "output",
        Path("/var/task/backend/output"),
        Path("/var/task/output"),
    ]
    for candidate in candidates:
        if (candidate / "summary.json").exists():
            return candidate
    return candidates[0]


app = FastAPI(title="FinOps Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next: Any) -> Response:
    """Ensure API responses are never cached by browsers."""
    response: Response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@lru_cache(maxsize=1)
def load_artifacts() -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    """Load existing pipeline artifacts once per server process."""
    output_dir = get_output_dir()
    summary_path = output_dir / "summary.json"
    risk_metrics_path = output_dir / "risk_metrics.json"
    process_path = output_dir / "process_analysis.csv"

    missing = [str(path) for path in [summary_path, risk_metrics_path, process_path] if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Required analytics artifacts are missing: {', '.join(missing)}")
    with summary_path.open(encoding="utf-8") as handle:
        summary = json.load(handle)
    with risk_metrics_path.open(encoding="utf-8") as handle:
        risk_metrics = json.load(handle)
    process_df = pd.read_csv(process_path)
    return summary, risk_metrics, process_df


def _json_safe(value: Any) -> Any:
    """Convert Pandas/NumPy values in endpoint payloads into JSON-safe values."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def _artifacts_or_503() -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    try:
        return load_artifacts()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Analytics artifacts unavailable: {exc}") from exc


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    """Return portfolio-level transaction and fraud overview metrics."""
    summary, risk_metrics, _ = _artifacts_or_503()
    metrics = summary["metrics"]
    risk = risk_metrics["risk_analytics"]
    return _json_safe({
        "total_transactions": metrics["total_transactions"],
        "total_transaction_value": metrics["total_transaction_value"],
        "fraud_count": metrics["fraud_count"],
        "fraud_rate": metrics["fraud_rate"],
        "high_risk_count": risk["high_risk_transaction_count"],
        "medium_risk_count": risk["medium_risk_transaction_count"],
        "low_risk_count": risk["low_risk_transaction_count"],
        "transaction_type_distribution": metrics["transaction_volume_by_type"],
        "transaction_trend": metrics["transaction_trends_by_step"],
    })


@app.get("/api/risk")
def risk() -> dict[str, Any]:
    """Return risk segmentation, model quality, and explainability metrics."""
    _, risk_metrics, _ = _artifacts_or_503()
    return _json_safe({
        "risk_distribution": risk_metrics["risk_analytics"]["risk_distribution"],
        "risk_by_transaction_type": risk_metrics["risk_analytics"]["risk_by_transaction_type"],
        "fraud_rate_by_transaction_type": [
            {
                "type": item["type"],
                "fraud_rate": item["fraud_rate"],
                "fraud_count": item["fraud_count"],
                "transaction_count": item["transaction_count"],
            }
            for item in risk_metrics["risk_analytics"]["risk_by_transaction_type"]
        ],
        "top_high_risk_transactions": risk_metrics["risk_analytics"]["top_high_risk_transactions"],
        "model_metrics": {
            key: risk_metrics[key]
            for key in ["model", "precision", "recall", "f1", "roc_auc", "pr_auc", "confusion_matrix"]
        },
        "top_feature_importances": risk_metrics["top_10_feature_importance"],
    })


@app.get("/api/process")
def process() -> dict[str, Any]:
    """Return stage-level simulated process metrics and bottleneck analysis."""
    summary, _, process_df = _artifacts_or_503()
    stages = process_df.to_dict(orient="records")
    total_transactions = int(process_df["transaction_count"].iloc[0])
    total_processing_time = float(
        (process_df["average_processing_time_minutes"] * process_df["transaction_count"]).sum()
    )
    weighted_sla_breach_rate = float(
        (process_df["sla_breach_rate"] * process_df["transaction_count"]).sum()
        / process_df["transaction_count"].sum()
    )
    return _json_safe({
        "process_stages": stages,
        "processing_time_by_stage": [
            {
                "stage": row["stage"],
                "average_processing_time_minutes": row["average_processing_time_minutes"],
                "p95_processing_time_minutes": row["p95_processing_time_minutes"],
            }
            for row in stages
        ],
        "total_processing_time_minutes": total_processing_time,
        "bottleneck_stage": summary["identified_bottleneck"],
        "process_efficiency_metrics": {
            "average_end_to_end_processing_time_minutes": float(process_df["average_processing_time_minutes"].sum()),
            "weighted_sla_breach_rate": weighted_sla_breach_rate,
            "total_simulated_operational_cost": float(process_df["simulated_total_operational_cost"].sum()),
            "transaction_count": total_transactions,
            "assumption_status": "DERIVED/SIMULATED",
        },
        "data_notice": "Processing times, costs, departments, and SLA measures are simulated analytical assumptions.",
    })


@app.get("/api/decisions")
def decisions() -> dict[str, Any]:
    """Return calculated scenario comparisons and the score-based recommendation."""
    summary, risk_metrics, process_df = _artifacts_or_503()
    try:
        return _json_safe(calculate_decisions(summary, risk_metrics, process_df))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Decision analysis failed: {exc}") from exc


FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

