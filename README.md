# FINOPS INTELLIGENCE

Financial Operations, Risk & Process Analytics Platform — preprocessing and descriptive analytics MVP.

## Run the pipeline

From the project root:

```bash
python backend/data_pipeline.py
```

Outputs are written to `backend/output/`:

- `processed_transactions.csv`: deterministic extract capped at 250,000 rows for a future API/dashboard. Metrics are calculated from all valid source rows.
- `summary.json`: dashboard-ready business, fraud, trend, high-value, and process metrics.
- `process_analysis.csv`: stage-level process/SLA analysis.
- `inspection.json`: source row/column, missingness, type, fraud, and numeric-statistics inspection.

## Data provenance and assumptions

PaySim is a **synthetic** financial transaction dataset. It is not real J.P. Morgan or real banking data and should not be represented as such.

Fields loaded from the original CSV include `step`, `type`, `amount`, `nameOrig`, `oldbalanceOrg`, `newbalanceOrig`, `nameDest`, `oldbalanceDest`, `newbalanceDest`, `isFraud`, and `isFlaggedFraud`.

The pipeline derives `transaction_hour`, `transaction_amount_log`, `amount_bucket`, `balance_change_origin`, `balance_change_destination`, `transaction_category`, and a validation flag from those source fields. `transaction_hour` uses PaySim's documented hourly `step` index modulo 24.

PaySim does **not** contain operational timestamps, processing times, departments, staffing costs, settlement durations, or service-level agreements. The process-analysis layer therefore creates clearly labeled `DERIVED/SIMULATED` assumptions for processing time, department, SLA target/breach rate, and operational cost. These are deterministic analytical proxies intended to demonstrate process-improvement and cost/benefit reasoning; they are not observed banking operations.

No fraud model is trained in this stage. Fraud fields are used only for descriptive analytics; model training is intentionally reserved for the next step.

## Risk Modeling

Run the fraud-risk engine from the project root:

```bash
python backend/risk_model.py
```

The engine trains a Random Forest because it handles nonlinear relationships between transaction amount/type/time features, works well with mixed numeric and categorical inputs after one-hot encoding, and provides usable global feature importance for an explainable portfolio demo. The fitted preprocessing-plus-model pipeline is saved to `models/risk_model.joblib`; evaluation metrics are saved to `backend/output/risk_metrics.json`; and a deterministic 250,000-row scored extract is saved to `backend/output/risk_scored_transactions.csv`.

Prediction features are limited to information plausibly available at transaction time: `amount`, `transaction_hour`, `transaction_amount_log`, `type`, `amount_bucket`, and `transaction_category`. The target `isFraud`, `isFlaggedFraud`, balance fields, customer identifiers, and other post-outcome or leakage-prone fields are excluded. The model uses `class_weight="balanced_subsample"` to address PaySim's extreme class imbalance. No observations are duplicated or oversampled before the stratified train/test split.

Accuracy is not the primary metric because a model can achieve high accuracy by predicting nearly every transaction as legitimate. Precision, recall, F1, ROC-AUC, PR-AUC, and the confusion matrix are reported instead.

The dashboard risk bands are configurable probability thresholds:

- **LOW**: `risk_score < 0.30`
- **MEDIUM**: `0.30 <= risk_score < 0.70`
- **HIGH**: `risk_score >= 0.70`

The reusable `predict_transaction_risk(transaction)` function returns a fraud probability, risk band, and importance-based active risk factors. These risk scores are analytical predictions on synthetic PaySim data and are not real banking decisions or regulatory model outputs.
