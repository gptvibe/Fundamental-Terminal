# Derived Metrics Mart (PR2)

## What This Adds

This change introduces a persisted, SEC-first derived metrics mart in PostgreSQL.

- Table: `derived_metric_points`
- Grain: one row per `company_id`, `period_end`, `period_type`, `metric_key`
- Supported period types: `quarterly`, `annual`, `ttm`
- Queryable columns: company, period dates, period type, filing type, metric key/value
- JSONB columns are reserved for: `provenance`, `source_statement_ids`, `quality_flags`

The implementation remains cache-first:

- API routes serve cached/persisted rows immediately.
- If data is missing/stale, routes queue refresh in the existing job queue.
- Existing SSE status flow and `job_id` behavior are reused.

## API Endpoints

- `GET /api/companies/{ticker}/metrics`
  - query: `period_type=quarterly|annual|ttm` (default `ttm`)
  - query: `max_periods` (default 24)
- `GET /api/companies/{ticker}/metrics/summary`
  - query: `period_type=quarterly|annual|ttm` (default `ttm`)

Both routes return:

- `company`
- refresh metadata (`refresh`, `staleness_reason`)
- timestamps (`last_metrics_check`, `last_financials_check`, `last_price_check`)

## Metric Registry

All derived metrics are computed through one central registry in `app/services/derived_metrics_mart.py`.

### Base values

- `revenue`
- `gross_profit`
- `operating_income`
- `net_income`
- `free_cash_flow`

### Growth and margins

- `revenue_growth`
- `eps_growth`
- `gross_margin`
- `operating_margin`
- `net_margin`
- `fcf_margin`

### Returns and profitability

- `roic_proxy`
- `roe`
- `roa`

### Balance sheet and coverage

- `debt_to_equity`
- `debt_to_assets`
- `interest_coverage_proxy`
- `current_ratio`
- `cash_ratio`

### Bank metrics

- `net_interest_margin`
- `provision_burden`
- `asset_quality_ratio`
- `cet1_ratio`
- `tier1_capital_ratio`
- `total_capital_ratio`
- `core_deposit_ratio`
- `uninsured_deposit_ratio`
- `tangible_book_value_per_share`
- `roatce`

### Capital allocation and dilution

- `dilution_trend`
- `shares_cagr`
- `sbc_to_revenue`
- `dividend_yield_proxy`
- `buyback_yield_proxy`
- `shareholder_yield`

### Working capital quality

- `dso_days`
- `dio_days`
- `dpo_days`
- `cash_conversion_cycle_days`
- `accrual_ratio`
- `cash_conversion_ratio`

### Segment and filing quality

- `segment_concentration`
- `geography_concentration`
- `filing_lag_days`
- `stale_period_flag`
- `restatement_flag`

## Provenance and Quality

Every metric row includes:

- `provenance`
  - `formula_version`
  - `unit`
  - `statement_type`
  - `statement_source`
  - `price_source`
  - `period_type`
- `source_statement_ids`
  - statement IDs used in the calculation (single or trailing set for TTM)
- `quality_flags`
  - examples: `segment_data_unavailable`, `segment_data_partial`, `missing_price_context`, `restatement_detected`

## Proxy Labels

Where exact SEC-native values are not directly available, metrics are intentionally named as proxies:

- `roic_proxy`
- `interest_coverage_proxy`
- `dividend_yield_proxy`
- `buyback_yield_proxy`
- `filing_lag_days` may use a last-updated proxy when direct filing date is unavailable

## Cadence Integrity

Metrics are computed within each cadence independently.

- No silent mixing between quarterly, annual, and TTM series.
- TTM is computed from trailing four quarterly periods.

## Regulated Bank Inputs

For issuers classified as banks or bank holding companies, the metrics mart prefers cached `canonical_bank_regulatory` statements over SEC canonical rows.

- Banks use FDIC BankFind quarterly financials / call-report-derived fields.
- Bank holding companies can use an official FR Y-9C JSON import configured through `FEDERAL_RESERVE_Y9C_JSON_URL` or `FEDERAL_RESERVE_Y9C_JSON_PATH`.
- Provenance stays on the same response envelope and continues to expose `source_mix`, `as_of`, `last_refreshed_at`, and confidence flags.
