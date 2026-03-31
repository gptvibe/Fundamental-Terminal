# Multi-Period Financial And Segment Upgrade Spec

## Status

Implemented on the dedicated financials workspace.

The financials page now uses a shared period-selection model so charts and tables react to the same cadence, visible range, focused period, and comparison period. The upgrade reuses existing statement, metrics, and capital-structure history where possible and adds one backend segment-history path where the existing pairwise payload was too narrow.

## Delivered Scope

The upgrade standardizes three ideas across the financials page:

- one shared selection model for cadence, range, focus, and comparison
- explicit requested-versus-effective cadence so annual-only surfaces can explain fallbacks instead of silently changing behavior
- consistent handling of sparse or non-comparable SEC disclosures, especially for segment history

Implemented frontend pieces:

- `frontend/hooks/use-period-selection.ts` drives URL-backed shared state for cadence, range, compare mode, focused period, comparison period, and derived visibility limits
- `frontend/lib/financial-chart-state.ts` passes a normalized chart-state contract into filing-based charts and annual-only panels
- `frontend/lib/annual-financial-scope.ts` centralizes annual fallback, annual-range resolution, annual comparison mapping, and warning generation for annual-only surfaces
- `frontend/app/company/[ticker]/financials/page.tsx` builds one `sharedChartState` object and passes it through to charts and tables that need synchronized behavior

Implemented annual-only or annual-preferred surfaces now using the shared model:

- `frontend/components/company/financial-comparison-panel.tsx`
- `frontend/components/company/ratio-history-table.tsx`
- `frontend/components/company/financial-quality-summary.tsx`
- `frontend/components/charts/growth-waterfall-chart.tsx`

Implemented filing-history surfaces now respecting effective cadence and shared visible ranges:

- `frontend/components/charts/balance-sheet-chart.tsx`
- `frontend/components/charts/liquidity-capital-chart.tsx`
- `frontend/components/charts/share-dilution-tracker-chart.tsx`
- `frontend/components/charts/margin-trend-chart.tsx`
- `frontend/components/charts/operating-cost-structure-chart.tsx`
- `frontend/components/charts/cash-flow-waterfall-chart.tsx`

Implemented segment upgrade:

- `frontend/components/charts/business-segment-breakdown.tsx` now follows shared period state, removes internal period caps, and warns when the requested cadence or comparison cannot be supported by comparable disclosures

## What Reuses Existing History

Most of the upgrade does not require new public financial-history endpoints.

Existing routes reused directly:

| Route | Current use in the upgrade |
|-------|----------------------------|
| `GET /api/companies/{ticker}/financials` | Primary source for annual and quarterly filing history on the financials page |
| `GET /api/companies/{ticker}/metrics-timeseries` | Derived metrics charts, including TTM where appropriate |
| `GET /api/companies/{ticker}/metrics` | Periodized derived metrics when the UI needs normalized per-period values |
| `GET /api/companies/{ticker}/capital-structure` | Historical capital-structure, debt, payout, and dilution snapshots |

Existing service behavior reused directly:

- `app/services/cache_queries.py:get_company_financials`
- `app/services/cache_queries.py:get_company_regulated_bank_financials`
- `app/services/cache_queries.py:select_point_in_time_financials`
- `app/services/cache_queries.py:get_company_derived_metric_points`
- `app/services/cache_queries.py:get_company_capital_structure_snapshots`
- `app/services/regulated_financials.py:select_preferred_financials`

The key design choice is that the page reuses the full statement array it already had instead of letting individual components re-derive their own truncated or pairwise state.

## What Required New Backend Work

The main new backend work for this upgrade is segment history.

Why new work was needed:

- the pre-existing `segment_analysis` payload is intentionally latest-versus-previous and is not a general historical segment API
- raw `segment_breakdown` attached to recent statements is useful but not complete enough for a consistent multi-period segment view
- segment disclosures often need additional provenance and comparability signaling beyond what pairwise UI logic can infer locally

Backend pieces added or expanded for that work:

- `GET /api/companies/{ticker}/segment-history`
- `app/services/segment_history.py`
- route wiring in `app/api/routers/financials.py` and `app/main.py`
- backend coverage in `tests/test_segment_history.py`

This route is intentionally annual-first. The frontend does not pretend that all issuers provide quarter-by-quarter comparable segment disclosures.

## Shared State Model

The page-level contract separates user intent from what the underlying data can actually support.

Important fields in `SharedFinancialChartState`:

- `requestedCadence`: what the user asked for
- `effectiveCadence`: what the current filing-backed surface can actually render
- `visiblePeriodCount`: how many filings are in the shared visible range
- `selectedFinancial` and `comparisonFinancial`: focused statements after shared resolution
- `selectedPeriodLabel` and `comparisonPeriodLabel`: display labels derived from the resolved statements
- `cadenceNote`: explicit explanation when the rendered cadence differs from the requested cadence

This matters because annual-only panels now explain their fallback instead of silently replacing a quarterly request with annual data.

## Annual-Only Surface Rules

Several surfaces are annual by construction because their calculations or table shape depend on fiscal-year comparability.

The shared annual resolver in `frontend/lib/annual-financial-scope.ts` applies these rules:

- map the selected filing to its fiscal year when the user is browsing quarterly statements
- map the comparison filing to a distinct annual filing when possible
- keep the annual visible range aligned with the page-level range instead of using local caps
- show warnings when a quarterly comparison collapses onto the same annual filing or when only one comparable annual filing exists

Current annual-only consumers:

- financial comparison panel
- ratio history table
- financial quality summary trend mode
- growth waterfall chart

## Segment History And Comparability Rules

Segment disclosures are the least uniform part of the upgrade, so the UI must treat missing or inconsistent history as a first-class state rather than as an error to hide.

Known sparse or non-comparable SEC cases:

- many issuers disclose full business segments annually but not quarterly
- some issuers disclose geography only, or revenue without segment operating income
- segment names, axes, or grouping logic can change between filings
- segments can be added, removed, or merged between periods
- foreign issuer forms and non-standard quarter boundaries can reduce comparability

Frontend handling rules:

- annual-only server-backed segment history is labeled as annual-only when the user requests quarterly cadence
- sparse visible histories show explicit warnings instead of manufacturing trends from one filing
- unavailable comparison periods stay unavailable; the frontend does not silently substitute another segment period
- warnings are rendered through `SnapshotSurfaceStatus` so the user can see the comparability limitation directly in the panel

Backend comparability signals that can affect UI interpretation include:

- no prior comparable disclosure
- segment axis changed
- partial operating-income disclosure
- new or removed segments

The product requirement here is explicit: no hidden assumptions around segment comparability.

## Annual, Quarterly, And TTM Boundaries

The upgrade keeps cadence boundaries strict.

- raw statement surfaces use annual or quarterly filings from `GET /api/companies/{ticker}/financials`
- TTM remains a derived-metrics concept and should come from `metrics-timeseries` or `metrics`, not from client-side reconstruction of raw statements
- balance-sheet and capital-structure panels do not use TTM because they are point-in-time values rather than flows
- segment history is not treated as TTM-capable in this upgrade

## Bank-Mode Constraint

Bank mode remains intact.

The financials page still relies on the existing bank-selection path:

- canonical SEC financials and regulated-bank financials are loaded
- `select_preferred_financials` decides which history set is primary for the company
- the shared range, cadence, and comparison model sits on top of that chosen history instead of bypassing it

The upgrade does not collapse bank-mode behavior into the standard SEC workflow.

## Test Coverage Added For The Upgrade

The verification strategy covers state, panel behavior, and page-level synchronization.

- `frontend/hooks/use-period-selection.test.ts` covers shared period-selection state, cadence fallback, comparison resolution, and URL updates
- `frontend/components/company/financial-comparison-panel.test.ts` covers same-fiscal-year comparison collapse without silent fallback
- `frontend/components/company/ratio-history-table.test.ts` covers annual ratio calculations and quarterly-to-annual mapping behavior
- `frontend/components/charts/business-segment-breakdown.test.ts` covers sparse-history and comparison-unavailable warnings
- `frontend/app/company/[ticker]/financials/page.test.ts` covers range and selected/comparison synchronization across major charts and tables

## Remaining Follow-On Work

This upgrade standardizes the financials page, not every financial consumer in the repo.

Potential future follow-ons:

- repo-wide replacement of latest-versus-previous assumptions in model and alert panels
- richer multi-period bank-only summary surfaces
- longer-horizon annual history reuse from `financial-history` where that view adds value beyond the main financials workspace
- any new multi-period UI must tolerate `financials[]` being a regulated-bank history instead

### Existing Bank-Specific UI Assumptions

The dedicated financials page switches into bank mode when:

- `company.regulated_entity` is present
- at least one returned statement has `regulated_bank`

In bank mode today:

- the page replaces the standard header summaries with latest bank ratios
- `BankRegulatoryOverview` renders a latest-only bank snapshot
- `DerivedMetricsPanel` switches to bank metric options and still uses historical series
- `BankFinancialStatementsTable` shows full regulated-bank history
- segment and standard SEC statement panels are not rendered

### Bank-Specific Constraints

Do not break these assumptions:

- regulated-bank periods may come from FDIC call reports, FR Y-9C, or a mixed reporting basis
- bank histories are structurally different from canonical SEC statements
- bank mode should not be forced through the segment workflow
- SEC-companyfacts-derived long-horizon annual history should not silently replace regulated-bank history in the main bank branch

## Correct Integration Point On The Dedicated Financials Page

### Primary Integration Point

The correct primary integration point is:

- `frontend/app/company/[ticker]/financials/page.tsx`
- backed by `frontend/hooks/use-company-workspace.ts`

Reasoning:

- the page already owns bank-mode branching
- the hook already owns the main `financials` history payload
- the hook already inherits `as_of` from the current URL through `frontend/lib/api.ts`
- centralizing period-selection state at the page level avoids each child component inventing its own history logic

### Secondary Reusable Module

If the dedicated financials page needs a separate long-run annual history block, the existing reusable candidate is:

- `frontend/components/company/financial-history-section.tsx`

That module should be treated as:

- optional long-horizon annual history
- separate from the normalized statement-history workspace
- something to reuse or adapt, not duplicate

### What Not To Do First

Do not start by:

- adding a brand-new public financial-history endpoint
- making every child component fetch its own history payload
- forcing the segment UI to depend only on `segment_analysis` instead of raw statement-level segment data

## Recommended File Change Order

This is the recommended implementation order once product behavior changes are approved.

1. `frontend/hooks/use-company-workspace.ts`
   - Keep this as the page-level history source.
   - Add any shared financials-page state or supplemental history fetch here only if multiple child components need it.

2. `frontend/app/company/[ticker]/financials/page.tsx`
   - Introduce the page-level period or cadence controls here.
   - Thread selected period mode into child components instead of letting each component diverge.
   - Preserve the current bank-mode branch.

3. `frontend/components/charts/business-segment-breakdown.tsx`
   - This is the main segment bottleneck.
   - Upgrade it from latest-vs-previous behavior to a true multi-period segment explorer using `financials[].segment_breakdown`.

4. `frontend/components/company/financial-quality-summary.tsx`
   - Upgrade from single-snapshot annual summary to a period-aware or trend-aware quality module.

5. `frontend/components/company/financial-statements-table.tsx`
   - Keep exports and full raw history table.
   - Rework the top trend strip so it aligns with the new page-level cadence logic.

6. `frontend/components/charts/cash-flow-waterfall-chart.tsx`
   - Decide whether this remains intentionally latest-period or becomes period-selectable from the shared page controls.

7. `frontend/components/company/bank-regulatory-overview.tsx`
   - Only if a bank trend upgrade is explicitly desired.
   - Otherwise leave as a latest-period bank snapshot and keep the bank history table as the multi-period surface.

8. `frontend/components/company/capital-structure-intelligence-panel.tsx`
   - Optional follow-on if the product wants a deeper multi-period capital-structure view than latest plus five rows.

9. `frontend/components/company/financial-history-section.tsx`
   - Optional follow-on if the dedicated financials page should expose the existing companyfacts-based annual history module.

10. `app/services/segment_analysis.py`
    - Only after the frontend has consumed the raw statement-level segment history and a real backend gap remains.
    - The likely enhancement would be richer historical segment summaries, not a replacement for `financials[].segment_breakdown`.

11. `app/services/sec_edgar.py`
    - Only if the current recent-statement segment backfill window is too shallow for the approved UX.
    - Avoid touching this until the frontend proves the current history depth is insufficient.

12. `app/main.py`
    - Backend response changes should be last, not first.
    - The existing routes already cover the main annual, quarterly, TTM, and point-in-time needs.

13. `app/services/cache_queries.py`
    - Touch only if the approved UX requires a new retrieval shape that existing queries cannot provide cleanly.

## Recommended First Implementation Scope

If the team approves the upgrade, the first pass should remain UI-first and route-reuse-first.

Recommended first scope:

- keep `GET /api/companies/{ticker}/financials` as the raw statement source
- keep `GET /api/companies/{ticker}/metrics-timeseries` and `GET /api/companies/{ticker}/metrics` as the TTM and cadence-aware derived sources
- keep bank mode exactly as it is
- lift period-selection state to the dedicated financials page
- convert the segment and quality modules from pairwise logic to history-aware logic
- optionally add the existing companyfacts history section as a separate long-horizon annual panel rather than replacing the normalized financials workflow

## Summary

The repo already has the backend needed for a strong first multi-period upgrade:

- raw normalized annual and quarterly statement history
- point-in-time filtering via `as_of`
- quarterly, annual, and TTM derived metric histories
- persisted capital-structure history
- regulated-bank history with bank-aware metrics

The main upgrade gap is not missing financial history APIs. The main gap is that several financials-page components still collapse already-loaded history into latest-only or latest-vs-previous views.