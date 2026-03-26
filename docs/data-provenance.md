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

## Product Semantics
- Canonical financials are normalized from SEC XBRL facts and filing metadata.
- Governance, filing events, earnings release signals, ownership, and capital-markets datasets are derived from official SEC filings.
- Price-based overlays are supplemental and should never replace official filing-derived fundamentals.

## Diagnostics Surface
Hot company payloads now expose a `diagnostics` block that summarizes:
- `coverage_ratio`
- `fallback_ratio`
- `stale_flags`
- `parser_confidence`
- `missing_field_flags`

This metadata is for reliability and UX transparency. It does not change the persisted source-of-truth model.

## Operational Guidance
- When adding a new dataset, document its provenance before exposing it in product routes.
- Prefer explicit source fields or source URLs where they already exist in backend models.
- If a dataset blends official and supplemental sources, keep the official source dominant and label the supplemental input clearly.