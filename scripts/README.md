# scripts/

Helper scripts for development, validation, and benchmarking. Run from the repo root with the virtualenv active.

## Validation & checks

| Script | Purpose |
|---|---|
| `check_architecture_boundaries.py` | Assert that inter-layer import boundaries are respected. |
| `check_migration_safety.py` | Verify Alembic migrations are safe to apply (no destructive column drops, etc.). |
| `check_frontend_routes.py` | Smoke-test key frontend routes against a running server. Accepts `--base-url` (default `http://localhost:3000`). |
| `verify_docker_healthchecks.py` | Parse checked-in compose files and fail if container health checks go missing, become expensive, or point at broken scripts/endpoints. |
| `run_charts_validation.py` | Run chart/driver-forecast validation and emit regression + benchmark reports. |
| `run_model_evaluation.py` | Run model evaluation harness and write results to `artifacts/model_eval/`. |
| `run_performance_regression_gate.py` | Compare current benchmark numbers against `performance_regression_baseline.json` and fail on regressions. |
| `verify_deployment_compat.py` | Pre-flight check before production deploys (env vars, DB connectivity, migration state). |

Run the Docker health-check verifier from the repo root:

```bash
python scripts/verify_docker_healthchecks.py
```

## Benchmarks

| Script | Purpose |
|---|---|
| `benchmark_api_routes.py` | End-to-end latency benchmark for key API routes. |
| `benchmark_derived_metrics_price_matching.py` | Latency for derived-metrics price-matching path. |
| `benchmark_hot_endpoints.py` | Throughput benchmark for hot-path endpoints. |
| `benchmark_incremental_price_refresh.py` | Benchmark incremental price-refresh pipeline. |
| `benchmark_market_profile_cache.py` | Market profile cache read/write latency. |
| `benchmark_model_computation.py` | Model computation pipeline throughput. |
| `benchmark_refresh_bootstrap_parallelism.py` | Parallelism benefit for refresh bootstrap. |
| `benchmark_refresh_service_reuse.py` | Service-reuse overhead in the refresh path. |

## Backfill / data utilities

| Script | Purpose |
|---|---|
| `backfill_model_cache.py` | Populate the model cache from scratch (run after a fresh DB restore). |

## Baseline snapshots

| File | Purpose |
|---|---|
| `model_evaluation_baseline.json` | Golden baseline for model evaluation results. |
| `performance_regression_baseline.json` | Golden baseline used by `run_performance_regression_gate.py`. |
