# Derived Metrics Timeseries (PR1)

## Scope

Adds a cache-first derived analytics layer on top of persisted canonical SEC financials and cached price history.

- Backend route: `GET /api/companies/{ticker}/metrics-timeseries`
	- query: `cadence=quarterly|annual|ttm` (optional)
	- query: `max_points=<1..200>` (optional, default 24)
- Frontend integration: financials workspace panel with cadence and metric selectors
- Source policy: SEC canonical statement cache + cached market profile only

The route never blocks on live upstream fetches. If data is stale or missing, the request returns cached (or empty) payload and queues refresh in the existing background queue.

## Response shape

Each series point includes:

- `cadence`: `quarterly`, `annual`, or `ttm`
- period metadata (`period_start`, `period_end`, `filing_type`)
- `metrics`: derived value set
- `provenance`: statement type/source, price source, formula version
- `quality`: coverage ratio, missing metrics, quality flags

Top-level response diagnostics include:

- `last_financials_check`
- `last_price_check`
- `staleness_reason`

## Metrics in v1

- Revenue growth
- Gross margin
- Operating margin
- Free cash flow margin
- ROIC proxy
- Leverage ratio
- Current ratio
- Share dilution
- SBC burden
- Buyback yield
- Dividend yield
- Working-capital days
- Accrual ratio
- Cash conversion
- Segment concentration (top-two segment revenue share when segment data exists)

## Quality flags

- `low_metric_coverage`
- `segment_data_unavailable`
- `missing_price_context`

## Notes

- TTM points are computed from trailing four quarterly filings when available.
- Buyback/dividend yields use the nearest cached close at or before the period end and diluted/share-outstanding proxy.
- This PR intentionally avoids new tables and keeps public routes stable, adding only a new typed route.
- Frontend panel listens to existing refresh SSE events and polls while job status is active so values update automatically after queued refreshes.
