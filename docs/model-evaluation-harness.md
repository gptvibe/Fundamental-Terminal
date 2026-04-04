# Model Evaluation Harness

The model evaluation harness backtests the valuation and earnings stack on historical snapshots only. It never evaluates a model on inputs that were not visible as of the snapshot cutoff.

It also includes an oil-overlay point-in-time suite that compares the base fair-value model against base-plus-oil-overlay for supported oil names.

## Covered models

- `dcf`
- `reverse_dcf`
- `residual_income`
- `roic`
- `earnings`

## Oil Overlay Point-In-Time Suite

- Suite key: `oil_overlay_point_in_time_v1`
- Models: `oil_overlay_base`, `oil_overlay_adjusted`
- Snapshot source: persisted `company_oil_scenario_overlay_snapshots` for historical-cache runs, or deterministic in-memory fixtures for CI
- Input rule: each snapshot uses only the SEC disclosures, EIA benchmark data, diluted shares, and base fair value that were visible at that cutoff
- Comparison output: sample count, improvement rate, MAE lift, and company-level summaries stored in run artifacts

The latest completed oil-overlay run is surfaced inside the Models oil panel with provenance, `as_of`, and confidence metadata so the UI can disclose how the overlay has performed historically.

## Historical snapshot rules

- Financial statements are filtered with the existing point-in-time visibility rules built from filing acceptance timestamps.
- Price history is clipped to the snapshot cutoff for the current signal and to a configurable forward horizon for realized outcomes.
- Earnings signals use persisted earnings model points and forward price windows only.
- Fixture-based gate runs use a labeled synthetic suite with a fixed risk-free-rate provider so CI deltas are deterministic.

## Metrics

Each model produces three primary monitoring dimensions:

- `calibration`: directional consistency between the predicted signal and the realized outcome.
- `stability`: mean absolute change in the predicted signal across adjacent historical snapshots.
- `error`: mean absolute error, RMSE, and mean signed error for the signal versus the realized outcome.

## Persistence

Completed runs are stored in PostgreSQL in `model_evaluation_runs` with:

- suite key and candidate/baseline labels
- model list and run configuration
- aggregated metrics and per-model deltas
- summary metadata and top-error artifacts

Oil-overlay runs also persist:

- comparison summaries for base versus overlay performance
- per-company oil overlay summaries in `artifacts.company_summaries`
- top-error samples for `oil_overlay_base` and `oil_overlay_adjusted`

The latest stored run is exposed at `/api/model-evaluations/latest` and includes provenance, `as_of`, `last_refreshed_at`, and confidence flags.

## CLI

Generate a deterministic fixture baseline without PostgreSQL persistence:

```bash
python scripts/run_model_evaluation.py --fixture historical_fixture_v1 --write-baseline scripts/model_evaluation_baseline.json
```

Run the gate against the checked-in baseline and persist the completed run:

```bash
python scripts/run_model_evaluation.py --fixture historical_fixture_v1 --baseline-file scripts/model_evaluation_baseline.json --fail-on-delta --persist
```

Generate a deterministic oil-overlay fixture run without PostgreSQL persistence:

```bash
python scripts/run_model_evaluation.py --evaluation-target oil_overlay --fixture oil_overlay_point_in_time_v1
```

Run the oil-overlay fixture suite against a baseline and persist the completed run:

```bash
python scripts/run_model_evaluation.py --evaluation-target oil_overlay --fixture oil_overlay_point_in_time_v1 --baseline-file scripts/model_evaluation_baseline.json --persist
```

Evaluate cached PostgreSQL companies instead of the fixture suite:

```bash
python scripts/run_model_evaluation.py --tickers AAPL,MSFT,NVDA --suite-key production_cache_backtest --candidate-label local_candidate --persist
```

Evaluate cached supported oil companies using persisted overlay snapshots instead of the general fixture suite:

```bash
python scripts/run_model_evaluation.py --evaluation-target oil_overlay --tickers XOM,CVX,OXY --suite-key oil_overlay_point_in_time_v1 --candidate-label local_oil_overlay --persist
```

## CI gate

`.github/workflows/ci.yml` runs the fixture suite against the checked-in baseline. Any change in the persisted metrics produces explicit deltas and fails the job until the baseline is intentionally updated.