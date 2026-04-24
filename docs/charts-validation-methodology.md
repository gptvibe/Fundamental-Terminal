# Charts Validation Methodology

This framework validates the chart and driver forecast engines using a representative synthetic basket and reproducible checks.

## Basket Design

The validation basket covers six requested profiles:

- megacap tech
- cyclical industrial
- retailer
- capital-light software
- bank/financial
- biotech/high-volatility edge case

Each case defines multi-year statement history, operating profile assumptions, dilution path, and holdout next-year targets for benchmark comparisons.

## Regression Approach

A golden snapshot is stored in tests/golden/charts_driver_forecast_golden.json and includes key engine outputs per ticker:

- engine mode and routing
- base next-year revenue
- base next-year EPS
- base next-year growth
- guidance anchor

The regression test compares current outputs to this snapshot exactly. Use scripts/run_charts_validation.py --write-golden only when intentionally accepting model changes.

## Property and Identity Checks

Checks include:

- reported/projected separation by year boundaries
- revenue/operating-income sanity
- EPS identity: net income divided by diluted shares
- FCF identity: operating cash flow minus capex
- override clipping bounds enforcement
- sensitivity matrix shape (5x5) and monotonicity by growth and margin axes

## Baseline Benchmarks

For each case, model outputs are compared to:

- last-value carry-forward
- trailing CAGR extrapolation
- management guidance baseline when available

The summary reports per-case absolute percentage errors and aggregate beat counts.

## Output Artifacts

Running scripts/run_charts_validation.py emits:

- artifacts/performance/charts_validation_summary.json
- artifacts/performance/charts_validation_summary.md

These are intended for CI logs, release checks, and driver model change reviews.
