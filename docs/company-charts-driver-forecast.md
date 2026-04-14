# Company Charts Driver Forecast

## Summary

The charts dashboard now prefers a driver-based "three-statement-lite" forecast engine for `/company/[ticker]/charts`.
When statement coverage is too thin, it explicitly falls back to the older guarded heuristic model instead of fabricating driver inputs.

## Migration Path

1. `build_company_charts_dashboard_response(...)` now loads annual statements, point-in-time-safe earnings-model diagnostics, and point-in-time-safe earnings releases.
2. `build_driver_forecast_bundle(...)` is attempted first.
3. If the driver bundle is available, the payload renders:
   - base / bull / bear revenue, growth, and EPS cases
   - base-case profit and cash-flow schedules
   - separate assumption and calculation cards
4. If the driver bundle is unavailable, the existing heuristic extrapolation path remains active and the payload shape stays valid.

## Core Formulas

- Revenue:
  `Revenue(t) = Revenue(t-1) * (1 + price growth + market growth + market-share change)`
  Year one can then be anchored toward management guidance and clipped by backlog or capacity constraints.
- Bottom-up revenue:
  When segment history exists, each segment is forecast separately and then summed back to company revenue before overlays.
- Operating income:
  `EBIT = Revenue - variable costs - semi-variable costs - fixed costs`
- Reinvestment:
  `Incremental reinvestment = Delta revenue / sales-to-capital + Delta working capital`
- Free cash flow:
  `FCF = Net income + D&A + SBC - Delta working capital - Capex`
- Diluted shares:
  `Diluted shares(t) = Diluted shares(t-1) * (1 + SBC dilution + acquisition / convert dilution - buyback retirement)`
- EPS:
  `EPS = Net income / diluted shares`

## Assumption Sources

- Price, market growth, market share, and segment growth are inferred from historical filing trends.
- Guidance uses the latest observable earnings-release midpoint at the selected `as_of`.
- Working-capital days come from `(current assets - current liabilities) / revenue * 365`.
- Sales-to-capital comes from `revenue / total assets`.
- SBC, buybacks, acquisitions, and converts feed the share-count bridge when disclosed.

## No-Lookahead Rule

- Financial statements are filtered with the existing `as_of` behavior.
- Earnings-model diagnostics are filtered by row materialization time.
- Earnings-release guidance is filtered by filing acceptance time, then filing date, then reported period timing as fallback.
- Historical charts snapshots must never use releases or derived model rows that were not observable at the requested `as_of`.

## Forecast Stability Notes

- The charts payload now labels the diagnostic as `Forecast Stability`, not `Forecast Reliability`.
- Stability is anchored to point-in-time walk-forward revenue backtests across 1Y, 2Y, and 3Y horizons.
- Horizon errors are combined as a weighted APE:
  `Weighted error = 50% * 1Y + 30% * 2Y + 20% * 3Y`
- Sector templates do not replace company evidence; they only define conservative error buckets for labeling the realized backtest as `tight`, `moderate`, `wide`, or `very_wide`.
- The final score starts from the empirical error bucket, then subtracts explicit penalties for:
  - short history
  - cyclicality
  - structural breaks
  - major M&A
  - accounting restatements
  - unstable diluted share count
  - wide bull/base/bear scenario dispersion
- Missing parser-confidence data is treated as a penalty, never as a boost.
