# Screener Backend v1

## Scope

This adds the first official-source-only screener backend for Fundamental Terminal.

It stays inside the current product boundaries:

- SEC-first and official/public-source-only.
- No Yahoo dependency.
- Persisted-data-first.
- Thin routers with screening logic in services.
- `app.main` remains the compatibility boundary for public API handlers.

The backend does not introduce a new generic market-terminal surface. It is a narrow read model for cross-sectional issuer screening from already persisted official data.

## Endpoints

### `GET /api/screener/filters`

Returns the initial filter catalog, ranking definitions, sort defaults, and product notes for the official screener surface.

### `POST /api/screener/search`

Executes a cross-sectional screen over the latest persisted period for each company in the requested cadence.

Request body:

```json
{
  "period_type": "ttm",
  "ticker_universe": ["AAPL", "MSFT"],
  "filters": {
    "revenue_growth_min": 0.1,
    "operating_margin_min": 0.15,
    "fcf_margin_min": 0.1,
    "leverage_ratio_max": 1.0,
    "dilution_max": 0.03,
    "sbc_burden_max": 0.05,
    "shareholder_yield_min": 0.02,
    "max_filing_lag_days": 50,
    "exclude_restatements": true,
    "exclude_stale_periods": true,
    "excluded_quality_flags": ["filing_lag_proxy_from_last_updated"]
  },
  "sort": {
    "field": "revenue_growth",
    "direction": "desc"
  },
  "limit": 50,
  "offset": 0
}
```

## Backing Data

The screener does not create a separate persistence table in v1.

It reads from persisted official datasets that already exist in the repo:

- `derived_metric_points`
  - latest per-company rowset for the requested cadence
  - powers revenue growth, operating margin, FCF margin, leverage, dilution, SBC burden, filing lag, stale-period flags, and latest-period restatement flags
- `models`
  - latest persisted `capital_allocation` model run per company
  - powers the official-only shareholder-yield proxy
- `financial_restatements`
  - powers persisted restatement history counts and latest restatement metadata

This keeps the screener cache-first and aligned with the current ingestion and refresh pipeline.

## Initial Filters

v1 supports these filter families:

- revenue growth
- operating margin
- FCF margin
- leverage
  - mapped to `debt_to_equity`
- dilution
  - mapped to `dilution_trend`
- SBC burden
  - mapped to `sbc_to_revenue`
- shareholder yield
  - mapped to the persisted `capital_allocation.shareholder_yield` official proxy
- restatement flags
  - latest-period `restatement_flag`
  - persisted `financial_restatements` history
- filing lag and filing quality flags
  - `filing_lag_days`
  - `stale_period_flag`
  - explicit `excluded_quality_flags`

## Explainable Rankings

Each search result now includes five explainable ranking outputs:

- `quality`
- `value`
- `capital_allocation`
- `dilution_risk`
- `filing_risk`

Each ranking payload exposes:

- `score`
  - weighted 0-100 composite
- `rank`
  - ordinal rank within the candidate universe
- `percentile`
  - percentile rank within the candidate universe
- `score_directionality`
  - `higher_is_better` or `higher_is_worse`
- `components[]`
  - raw metric value
  - source key
  - weight
  - component directionality
  - normalized component score
  - component confidence notes
- `confidence_notes[]`
  - score-level notes about reweighted missing inputs, proxy usage, stale cache state, or inherited quality flags

### Ranking Universe

All ranking outputs are computed against the candidate universe before threshold filters are applied.

That keeps ranks stable for a given:

- `period_type`
- `ticker_universe`

The API exposes this as `universe_basis="candidate_universe_pre_filter"`.

### Ranking Method

The method is intentionally simple and inspectable:

1. Read the latest persisted component values for each company.
2. Convert each component into a cross-sectional percentile across the candidate universe.
3. Apply the component's declared directionality:
   - `higher_increases_score`
   - `lower_increases_score`
4. Blend the component percentiles with fixed weights into a 0-100 score.
5. Rank the resulting score across the same candidate universe.

Missing components do not zero the score. Their weights are redistributed over the available components and the response emits `missing_components_reweighted:<component_keys>`.

If a component has no cross-sectional dispersion, its contribution is neutralized to `50` and the response emits `flat_cross_sectional_distribution`.

### Ranking Definitions

#### `quality`

- revenue growth: `0.30`, `higher_increases_score`
- operating margin: `0.30`, `higher_increases_score`
- FCF margin: `0.25`, `higher_increases_score`
- leverage: `0.15`, `lower_increases_score`

#### `value`

- shareholder yield: `0.40`, `higher_increases_score`
- FCF margin: `0.25`, `higher_increases_score`
- operating margin: `0.15`, `higher_increases_score`
- leverage: `0.20`, `lower_increases_score`

This is intentionally a price-free value proxy. It does not use market multiples because the official screener has no official equity-price feed.

#### `capital_allocation`

- shareholder yield: `0.45`, `higher_increases_score`
- dilution: `0.30`, `lower_increases_score`
- SBC burden: `0.25`, `lower_increases_score`

#### `dilution_risk`

- dilution: `0.50`, `higher_increases_score`
- SBC burden: `0.35`, `higher_increases_score`
- shareholder yield: `0.15`, `lower_increases_score`

Higher score means higher dilution risk.

#### `filing_risk`

- filing lag days: `0.40`, `higher_increases_score`
- stale period flag: `0.20`, `higher_increases_score`
- latest-period restatement flag: `0.20`, `higher_increases_score`
- persisted restatement count: `0.20`, `higher_increases_score`

Higher score means higher filing and accounting risk.

### Ranking Metadata Endpoint

`GET /api/screener/filters` now returns the machine-readable ranking model used by the search endpoint.

That payload includes:

- score labels and descriptions
- score directionality
- component weights
- component directionality
- source keys
- ranking confidence-note policy

The ranking definitions in the metadata endpoint and the runtime ranking outputs are both driven from the same backend constants in `app/services/screener.py`.

## Official-Only Shareholder Yield

The existing derived-metrics mart includes a `shareholder_yield` field that depends on market-cap context and can pull in Yahoo-backed price data.

The screener cannot use that field because this backend is strict official-only by design.

Instead, it uses the latest persisted `capital_allocation` model output:

- source key: `capital_allocation.shareholder_yield`
- source tier: `derived_from_official`
- underlying inputs: official filing payouts and the model's official market-cap proxy

That keeps the screener backend Yahoo-free even when the rest of the workspace is not running with `STRICT_OFFICIAL_MODE=true`.

## Provenance and Metadata

Both screener endpoints return the standard provenance envelope:

- `provenance`
- `as_of`
- `last_refreshed_at`
- `source_mix`
- `confidence_flags`

The screener-specific contract always includes:

- `official_source_only`

Possible additional confidence flags include:

- `stale_metrics_present`
- `partial_shareholder_yield_coverage`
- `restatement_flags_present`
- `screener_universe_empty`

Each result row also exposes:

- the screened period end
- metrics refresh time
- shareholder-yield model timestamp
- aggregated filing-quality flags
- persisted restatement summary metadata
- explainable ranking payloads for quality, value, capital allocation, dilution risk, and filing risk

## Ranking Sort Fields

The screener still supports the original metric sort fields and now also accepts:

- `quality_score`
- `value_score`
- `capital_allocation_score`
- `dilution_risk_score`
- `filing_risk_score`

## Source Contract

The screener endpoints are registered as user-visible routes and covered by the source-contract manifest.

Allowed source ids:

- `ft_screener_backend`
- `ft_derived_metrics_mart`
- `ft_model_engine`
- `sec_companyfacts`
- `sec_edgar`
- `fdic_bankfind_financials`
- `federal_reserve_fr_y9c`

Fallback is not permitted.

## Non-goals

- No request-path live fetch.
- No Yahoo-backed price context.
- No new screener-specific persistence table.
- No frontend surface in this change.