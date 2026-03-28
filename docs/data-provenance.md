# Data Provenance

## Source Policy
Fundamental Terminal is SEC-first and public-data-first.

Allowed upstream sources:
- SEC EDGAR submissions and XBRL company facts
- U.S. Treasury and FiscalData
- U.S. Census Bureau economic indicators
- BLS
- BEA
- Treasury HQM
- FRED as optional macro support
- Yahoo Finance only for price, volume, and market profile context

Strict official mode:
- `STRICT_OFFICIAL_MODE=true` disables Yahoo-backed price and market-profile requests entirely.
- Company market sector and industry should be derived from SEC SIC code and description mapping.
- Price-dependent UI or model surfaces must either hide themselves or explain that no official equity-price source is configured.

Default mode fallback disclosure:
- Yahoo Finance remains allowed only as a labeled commercial fallback for price, volume, and market-profile context.
- Any UI surface that shows price-backed or market-profile-backed data must display a visible `commercial_fallback` badge and disclosure text whenever that fallback is present.
- Payloads that include fallback-backed price inputs must continue to expose explicit price provenance fields alongside `provenance[]` and `source_mix`.

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
- `census_eits_m3`
- `census_eits_retail_sales`
- `bls_public_data`
- `bea_nipa`
- `bea_gdp_by_industry`
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
- Canonical financial statements now persist the exact companyfacts fact lineage selected for each derived metric, including accession number, taxonomy, tag, filing date, source URL, and period bounds.
- Supported 10-K and 10-Q statement rows also persist a reconciliation payload against filing-parser-derived values so disagreements, missing parser coverage, and confidence penalties remain auditable after refresh.
- Segment and geography analysis on the financials route is derived at read time from the cached canonical statement history and remains official-source only.
- Governance, filing events, earnings release signals, ownership, and capital-markets datasets are derived from official SEC filings.
- Price-based overlays are supplemental and should never replace official filing-derived fundamentals.

## Point-in-Time Semantics
- Research routes may be queried with `as_of` to suppress data that would not have been visible at that timestamp.
- Canonical SEC statements use filing acceptance time when available; otherwise they fall back to the statement period end as the visibility cutoff.
- Financial restatement summaries use the amended filing acceptance time when available, then the filing date, so date-only `as_of` reviews include all SEC corrections known by the end of that day.
- Price-backed inputs use the market observation date.
- Risk-free-rate and macro assumptions use the latest published observation on or before the requested cutoff.
- Census M3 and retail observations use the published survey month as the public market visibility date.
- BLS JOLTS, PPI, and ECI observations use the published reference period as `as_of`, while fetch time remains separate in `last_refreshed_at`.
- BEA PCE and GDP-by-industry observations use the underlying BEA period label as `as_of` and keep API fetch time in `last_refreshed_at`.
- Fetch timestamps are stored separately from source observation timestamps so ingestion timing remains auditable without becoming the public market-visibility clock.
- Date-only `as_of` values are interpreted as end-of-day UTC.

## Amendment Lineage
- Restatement records are persisted from official SEC companyfacts normalization and archived filing links; no non-official amendment source is introduced.
- A restatement row can capture two related but distinct concepts: normalized statement value changes and companyfacts observation changes that did not move the final normalized value.
- Confidence impact flags on restatement responses summarize whether an amended filing, a core metric revision, or a materially large change was detected.

## Latest-vs-Prior Filing Comparison
- The changes-since-last-filing service derives its comparison from cached canonical SEC statements for the latest filing and the prior comparable filing of the same filing type.
- New risk indicators in that payload are computed from official filing metrics rather than supplemental market data.
- Amended prior values in that payload are sourced from persisted financial restatement records, so amendment context stays auditable and point-in-time compatible.

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

For financial statement reconciliation specifically:
- The route-level provenance for `/api/companies/{ticker}/financials` includes both `sec_companyfacts` and `sec_edgar` whenever the persisted reconciliation layer is present.
- Each financial statement can include a `reconciliation` object with its own `as_of`, `last_refreshed_at`, `provenance_sources`, `confidence_score`, `confidence_penalty`, `confidence_flags`, and `missing_field_flags`.
- Each reconciliation comparison row exposes the exact companyfacts taxonomy/tag pair and the companyfacts and parser periods that produced the compared values.

For segment and geography analysis specifically:
- `/api/companies/{ticker}/financials` can include a `segment_analysis` object with `business` and `geographic` lenses.
- Each lens carries its own `as_of`, `last_refreshed_at`, `provenance_sources`, `confidence_score`, and `confidence_flags` so the UI can disclose whether the mix summary came from current-only or comparable multi-period history.
- Each lens also carries structured `top_mix_movers`, `top_margin_contributors`, `concentration`, and `unusual_disclosures` payloads so the frontend can explain what changed rather than relying on charts alone.

## Diagnostics Surface
The `diagnostics` block still summarizes:
- `coverage_ratio`
- `fallback_ratio`
- `stale_flags`
- `parser_confidence`
- `missing_field_flags`
- `reconciliation_penalty`
- `reconciliation_disagreement_count`

This metadata is for reliability and UX transparency. It does not change the persisted source-of-truth model.

## Operational Guidance
- When adding a new dataset, document its provenance before exposing it in product routes.
- Prefer explicit source fields or source URLs where they already exist in backend models, then map them through the registry.
- If a dataset blends official and supplemental sources, keep the official source dominant and label the supplemental input clearly in `provenance[]` and `source_mix`.
- `commercial_fallback` and `manual_override` entries must always carry a disclosure note and should set a confidence flag when they influence the payload.
- In strict official mode, payloads should set a `strict_official_mode` confidence flag and should not expose `yahoo_finance` in `provenance[]` or `source_mix`.
