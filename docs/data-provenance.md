# Data Provenance

## Source Policy
Fundamental Terminal is SEC-first and public-data-first.

Allowed upstream sources:
- SEC EDGAR submissions and XBRL company facts
- U.S. Treasury and FiscalData
- BLS
- BEA
- Treasury HQM
- FRED as optional macro support
- Yahoo Finance only for price, volume, and market profile context

Not allowed for core fundamentals:
- Paid or auth-gated vendor APIs
- Unofficial scraped fundamentals feeds
- Third-party fundamentals providers that obscure original SEC provenance

## Central Registry
New data surfaces should resolve to a canonical source id from the shared registry before they ship.

Supported source tiers:
- `official_regulator`
- `official_statistical`
- `official_treasury_or_fed`
- `derived_from_official`
- `commercial_fallback`
- `manual_override`

Current canonical source ids include:
- `sec_edgar`
- `sec_companyfacts`
- `us_treasury_daily_par_yield_curve`
- `us_treasury_fiscaldata`
- `fred`
- `bls_public_data`
- `bea_nipa`
- `treasury_hqm_corporate_yield_curve`
- `yahoo_finance`
- `ft_derived_metrics_engine`
- `ft_derived_metrics_mart`
- `ft_model_engine`
- `ft_peer_comparison`
- `ft_activity_overview`
- `manual_override`

## Product Semantics
- Canonical financials are normalized from SEC XBRL facts and filing metadata.
- Governance, filing events, earnings release signals, ownership, and capital-markets datasets are derived from official SEC filings.
- Price-based overlays are supplemental and should never replace official filing-derived fundamentals.

## Provenance Contract
Hot company payloads now expose:
- `provenance[]`
- `as_of`
- `last_refreshed_at`
- `source_mix`
- `confidence_flags`
- `diagnostics`

Each `provenance[]` entry carries:
- canonical `source_id`
- `source_tier`
- display label
- canonical URL
- default freshness TTL
- disclosure note
- role (`primary`, `supplemental`, `derived`, or `fallback`)
- per-source `as_of`
- per-source `last_refreshed_at`

`source_mix` is the summary layer used by the frontend to disclose whether the payload is official-only or includes a labeled fallback.

## Diagnostics Surface
The `diagnostics` block still summarizes:
- `coverage_ratio`
- `fallback_ratio`
- `stale_flags`
- `parser_confidence`
- `missing_field_flags`

This metadata is for reliability and UX transparency. It does not change the persisted source-of-truth model.

## Operational Guidance
- When adding a new dataset, document its provenance before exposing it in product routes.
- Prefer explicit source fields or source URLs where they already exist in backend models, then map them through the registry.
- If a dataset blends official and supplemental sources, keep the official source dominant and label the supplemental input clearly in `provenance[]` and `source_mix`.
- `commercial_fallback` and `manual_override` entries must always carry a disclosure note and should set a confidence flag when they influence the payload.
