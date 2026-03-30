# Multi-Period Financial And Segment Upgrade Spec

## Status

Audit-only document. No product behavior changes are included here.

## Goal

Upgrade the dedicated financials surface from a mix of snapshot panels and partial trend panels into a consistent multi-period workspace without adding new product behavior yet and without introducing new public endpoints unless reuse clearly fails.

The working assumption for implementation is:

- reuse existing history-capable backend endpoints first
- keep bank-mode and regulated-entity behavior intact
- distinguish true SEC disclosure sparsity from frontend presentation limits

## Current Reusable History Endpoints

These are the existing backend routes that already expose reusable historical or periodized financial data.

| Route | Current support | Why it matters for the upgrade | Recommendation |
|-------|-----------------|--------------------------------|----------------|
| `GET /api/companies/{ticker}/financials` | Full normalized statement history in descending period order, plus `price_history`, `segment_analysis`, provenance, diagnostics, and `as_of` point-in-time filtering | This is the main reusable statement-history endpoint for the dedicated financials page | Primary source of truth for raw annual and quarterly statement history |
| `GET /api/companies/{ticker}/capital-structure` | Persisted `latest` plus `history[]`, supports `max_periods` and `as_of` | Already covers multi-period debt, payout, and dilution history | Reuse as-is for capital-structure panels |
| `GET /api/companies/{ticker}/metrics-timeseries` | Multi-period derived series with `cadence=quarterly|annual|ttm`, `max_points`, `as_of` | Already solves quarterly, annual, and TTM time-series needs for derived metrics | Reuse as-is for TTM-aware charts and selectors |
| `GET /api/companies/{ticker}/metrics` | Periodized derived metrics with `period_type=quarterly|annual|ttm`, `max_periods`, `as_of` | Better source than raw statements when the UI needs TTM or normalized derived values per period | Reuse before considering any new TTM route |
| `GET /api/companies/{ticker}/metrics/summary` | Summary for latest selected `period_type`, supports `as_of` | Useful for snapshot cards but not a full history source | Keep as summary-only; not enough for the core multi-period upgrade by itself |
| `GET /api/companies/{ticker}/financial-history` | Raw SEC companyfacts payload keyed by ticker or CIK | Already exists for long-run annual history, but the current frontend parser narrows it to 10 annual fiscal years and four metrics | Reuse only for a separate long-horizon annual history module |
| `GET /api/companies/{ticker}/financial-restatements` | Historical restatement list with `as_of` filtering | Useful for multi-period audit context and confidence signaling | Optional supporting history surface |
| `GET /api/companies/{ticker}/changes-since-last-filing` | Latest-vs-previous comparable filing pair, supports `as_of` | Helpful comparison endpoint, but intentionally pairwise rather than full-history | Do not use as the main multi-period source |
| `GET /api/companies/{ticker}/filing-insights` | Recent filing-parser-derived statement rows, limited set | Supplemental recent filing context | Not the main source for a multi-period financial workspace |

### Route Registration Note

Financial routes are registered in `app/api/routers/financials.py`, including `capital-structure`, `metrics-timeseries`, `metrics`, `metrics/summary`, `financial-history`, and `financial-restatements`.

This matters because the repo already has a clean financials router surface. The upgrade does not need a new public route in its first pass.

## Current Reusable Service Layer

These existing service functions already support historical retrieval or history-aware filtering.

| File | Service | Current behavior |
|------|---------|------------------|
| `app/services/cache_queries.py` | `get_company_financials` | Returns full canonical SEC statement history ordered by `period_end desc` |
| `app/services/cache_queries.py` | `get_company_regulated_bank_financials` | Returns full regulated-bank statement history ordered by `period_end desc` |
| `app/services/cache_queries.py` | `select_point_in_time_financials` | Applies `as_of` visibility rules and deduplicates visible statement versions |
| `app/services/cache_queries.py` | `get_company_derived_metric_points` | Returns multi-period derived metric rows for selected `period_type` |
| `app/services/cache_queries.py` | `get_company_capital_structure_snapshots` | Returns historical capital-structure snapshots |
| `app/services/sec_edgar.py` | Canonical statement normalization pipeline | Refreshes and normalizes multi-form SEC statement history across `10-K`, `10-Q`, `20-F`, `40-F`, and `6-K` |
| `app/services/sec_edgar.py` | Segment extraction and backfill | Populates `segment_breakdown` from companyfacts and filing HTML for a limited recent statement set |
| `app/services/segment_analysis.py` | `build_segment_analysis` | Builds a latest-vs-previous segment lens from the cached history |
| `app/services/regulated_financials.py` | `select_preferred_financials` | Swaps SEC statement history for regulated-bank history when a regulated entity has bank data |

## Existing Financial History Behavior By Surface

### Dedicated Financials Page

`frontend/app/company/[ticker]/financials/page.tsx` is a composition layer around `useCompanyWorkspace(ticker)`.

That hook already provides:

- `financials`: full statement history returned by `GET /api/companies/{ticker}/financials`
- `annualStatements`: annual subset computed client-side
- `latestFinancial`: first statement in the descending history array
- `priceHistory`: full cached price series returned by the same endpoint

Important implication:

- the page already has the main raw history it needs for annual and quarterly statement views
- the page does not currently fetch `financial-history`, `metrics`, or `metrics-timeseries` through the workspace hook
- the page relies on child components to decide whether to show full history, latest-only, or latest-vs-previous behavior

### Existing Secondary History Module

`frontend/components/company/financial-history-section.tsx` already consumes `GET /api/companies/{ticker}/financial-history` through `getCompanyFinancialHistory`.

Current limitations of that path are frontend-side, not endpoint-side:

- it only parses four metrics: revenue, net income, EPS, and operating cash flow
- it only keeps annual forms (`10-K`, `20-F`, `40-F`) with `fp=FY`
- it hard-caps the display to the last 10 fiscal years
- it is not wired into the dedicated financials page today

This is a reusable annual-history module, but it is not a replacement for the normalized financials workspace endpoint.

## Snapshot-Only Or Latest-Vs-Previous Frontend Components

The dedicated financials page already mixes true history components with components that flatten that history back down.

### Components That Already Support Multi-Period Behavior

| File | Current behavior |
|------|------------------|
| `frontend/components/charts/margin-trend-chart.tsx` | Annual/quarterly toggle over historical statements |
| `frontend/components/charts/operating-cost-structure-chart.tsx` | Annual/quarterly toggle over historical statements |
| `frontend/components/charts/share-dilution-tracker-chart.tsx` | Historical shares-outstanding trend over annual history with fallback |
| `frontend/components/charts/balance-sheet-chart.tsx` | Full statement-history chart |
| `frontend/components/charts/liquidity-capital-chart.tsx` | Multi-period liquidity and retained-earnings history |
| `frontend/components/charts/derived-metrics-panel.tsx` | Quarterly, annual, and TTM series from `metrics-timeseries` |
| `frontend/components/company/capital-structure-intelligence-panel.tsx` | Multi-period `history[]` already exists, though the UI emphasizes the latest snapshot |

### Components Still Flattening History

| File | Current behavior | Limiting factor |
|------|------------------|-----------------|
| `frontend/app/company/[ticker]/financials/page.tsx` | Header summaries and top-level bank summaries use a selected-or-latest single snapshot only | UI-level snapshot choice |
| `frontend/components/charts/business-segment-breakdown.tsx` | Uses `latestStatement` and `previousStatement` only; charts show latest mix and one-period growth comparison | Both UI and summary-payload shape |
| `frontend/components/company/financial-quality-summary.tsx` | Computes annual quality metrics from latest annual and prior annual only | UI-level latest-vs-previous summary |
| `frontend/components/charts/cash-flow-waterfall-chart.tsx` | Lets the user pick annual vs quarterly, but still shows only the latest statement in that cadence | UI-level snapshot choice |
| `frontend/components/company/financial-comparison-panel.tsx` | Compares exactly two annual periods at a time | UI-level pairwise comparison |
| `frontend/components/company/financial-statements-table.tsx` | Sparkline strip shows history, but the main table and exports collapse to selected period plus optional comparison period | Table and export collapse to pairwise view |
| `frontend/components/company/bank-financial-statements-table.tsx` | Regulated-bank table and exports collapse to selected period plus optional comparison period | Table and export collapse to pairwise view |
| `frontend/components/company/capital-structure-intelligence-panel.tsx` | Latest snapshot dominates, and the trend table is truncated to five rows | UI-level emphasis and truncation |
| `frontend/components/company/bank-regulatory-overview.tsx` | Latest regulated-bank snapshot only | UI-level snapshot choice |

### Snapshot-bound Surfaces To Upgrade

This expands the high-level component list above into a concrete implementation backlog. It includes sub-surfaces inside otherwise history-capable panels when those sub-surfaces still collapse to a latest-only, latest-plus-previous, or single-selected-period view.

| Surface | File path | Current behavior | Desired behavior | Existing frontend data enough? | Backend/history work required? | Priority |
|---------|-----------|------------------|------------------|-------------------------------|--------------------------------|----------|
| Financials header summary cards | `frontend/app/company/[ticker]/financials/page.tsx` | `CompanyResearchHeader` summaries show only the active snapshot. In standard mode that means selected-or-latest revenue, operating income, and free cash flow. In bank mode that means selected-or-latest NIM, CET1, deposits, and TCE. There is no multi-period delta, trend, or visible-range context in the cards themselves. | Convert the header cards into period-aware summary cards that can show trend, delta versus the comparison period, or a compact visible-range summary without falling back to a pure snapshot. | Yes. `financials[]`, annual subsets, and comparison selection are already on the page. | No for a first pass. | medium |
| Segment charts and lens summary | `frontend/components/charts/business-segment-breakdown.tsx` | The treemap and revenue-share chart are built from `latestStatement`; the growth bars compare only against `previousStatement`; the margin chart is still a single-period view; `LensSummary` depends on pairwise `segmentAnalysis` output. The surface stays bound to one disclosure snapshot plus one prior comparison. | Replace the pairwise view with a multi-period segment explorer: period selector, compare-any-two-periods, segment/geography trend views, and movers calculated across more than one pair. Keep single-period disclosure fallbacks only when history is genuinely sparse. | Partial. Raw `financials[].segment_breakdown` is enough for a first pass on disclosed periods, but not for every desired historical summary. | Yes for deeper backfill coverage and any non-pairwise replacement for `segmentAnalysis`. | high |
| Cash flow waterfall | `frontend/components/charts/cash-flow-waterfall-chart.tsx` | The chart renders `buildWaterfallData(focusStatement)` for one selected statement only. Comparison mode adds delta pills against one other statement, but the chart itself is still a single-snapshot bridge. | Add a true multi-period workflow: period stepping from the shared selector, compare mode that can render side-by-side bridges or a period-to-period bridge trend, and clear visible-range navigation. | Yes. The page already passes the visible filing set plus selected and comparison statements. | No for a first pass. | high |
| Financial quality summary cards | `frontend/components/company/financial-quality-summary.tsx` | The panel computes one annual summary for the selected annual filing and one resolved prior annual filing. Growth metrics are always pairwise, and the card grid never shows more than one period at a time. | Rework the panel into a multi-period quality surface: visible annual trend cards, rolling deltas, and an at-a-glance history of quality metrics rather than one selected-period snapshot. | Yes. Full annual history is already available in `financials[]`. | No for a first pass. | high |
| Annual financial comparison table | `frontend/components/company/financial-comparison-panel.tsx` | The table compares exactly two annual filings at a time, defaulting to latest and prior annual. It is pairwise by construction even when longer annual history is loaded. | Expand to a true multi-period annual comparison matrix or trend-oriented comparison surface that can show more than two annual periods at once. | Yes. The component already receives the full annual history. | No for a first pass. | medium |
| Financial statements table and export scope | `frontend/components/company/financial-statements-table.tsx` | The sparkline strip summarizes latest values with history, but the main table collapses to selected period plus optional comparison period. Export actions also only emit those focused statements instead of the whole visible range. | Restore a true multi-period statement table across the visible range, with comparison as an overlay rather than a replacement for history, and let exports include the full visible period set. | Yes. The visible filing history is already passed in. | No for a first pass. | high |
| Derived metrics summary cards | `frontend/components/charts/derived-metrics-panel.tsx` | The chart plots a full time series, but the summary card grid underneath is bound to `latest` only. The cards do not follow focus, hover, selected point, or comparison mode. | Make the cards period-aware so they reflect the focused or compared point on the chart, with optional visible-range deltas instead of hard-coded latest-only readouts. | Yes. `series[]` already contains the needed period values. | No for a first pass. | low |
| Capital structure snapshot cards, bucket tables, and truncated trend table | `frontend/components/company/capital-structure-intelligence-panel.tsx` | The top summary pills, metric cards, debt ladder, lease table, and debt/dilution bridge are all tied to one `activeSnapshot`. The only visible history is a table truncated to `history.slice(0, 5)`. | Promote the panel into a multi-period capital-structure workspace: full visible history table, compare mode across snapshots, and per-section history views for maturities, leases, payouts, and dilution. | Yes for the periods already returned by `history[]`. | No for a first pass, unless product later wants more history than the current `maxPeriods` window. | medium |
| Regulated bank snapshot cards | `frontend/components/company/bank-regulatory-overview.tsx` | The bank overview renders one regulated-bank snapshot only, even when multiple regulated-bank filings are already available on the page. | Add period-aware bank ratio and funding views that respect the shared selector and comparison mode, while keeping bank-mode semantics intact. | Yes. Regulated-bank statement history is already returned through `financials[]`. | No for a first pass. | medium |
| Regulated bank statements table and export scope | `frontend/components/company/bank-financial-statements-table.tsx` | The bank table now shows selected period plus optional comparison period only. Like the general statements table, exports are limited to the focused statements rather than the full visible bank history. | Restore a multi-column bank history table across visible filings and reserve comparison mode for highlighting, not replacing, the full history view. | Yes. The visible bank filing set is already passed in. | No for a first pass. | high |
| Workspace latest selector | `frontend/hooks/use-company-workspace.ts` | The hook exposes `latestFinancial = financials[0]` as a first-class primitive, which encourages downstream surfaces to stay snapshot-oriented even after a visible-range selector exists. | Keep `latestFinancial` as a fallback only, and push consumers toward explicit focus/comparison state derived from page-level period selection. | Yes. No additional data is needed. | No. | medium |
| Period selection fallback and pairwise comparison selector | `frontend/hooks/use-period-selection.ts` | `findFinancialByKey` falls back to the first visible period, and `resolveComparisonFinancial` only supports off, previous, or one custom comparison. The hook does not expose richer period sets for components that need more than one or two periods. | Extend the selection model so components can opt into explicit focus, visible-range access, and richer compare semantics without implicit latest-period collapse. | Yes. The visible filing array is already computed here. | No. | medium |

### Adjacent Repo-Wide Pairwise Financial Consumers

These are outside the dedicated financials page, but they still rely on latest or latest-vs-previous financial logic and should be considered follow-on work if the product later wants a repo-wide multi-period standard.

| File | Current behavior |
|------|------------------|
| `frontend/components/models/financial-health-score.tsx` | Uses current and previous annuals, with fallback to `financials[0]` and `financials[1]` |
| `frontend/components/models/dcf-scenario-analysis.tsx` | Uses latest annual and previous annual to derive defaults |
| `frontend/components/models/investment-summary-panel.tsx` | Uses current and previous annuals to build the summary layer |
| `frontend/components/models/valuation-scenario-workbench.tsx` | Uses latest annual and previous annual to seed scenario defaults |
| `frontend/components/alerts/risk-red-flag-panel.tsx` | Uses latest annual-or-latest filing values for fallback risk signals |

These components are not the recommended first-pass targets for the dedicated financials page upgrade, but they are part of the broader repo audit.

### Existing Pairwise Summary Service That Mirrors The UI Limitation

`app/services/segment_analysis.py` intentionally builds a latest-vs-previous comparable segment lens.

That means:

- the raw `financials[].segment_breakdown` array is more historical than the summary payload
- the backend summary is not wrong, but it is intentionally narrower than a multi-period segment workspace
- the first upgrade pass should consume raw per-statement segment history before considering a new endpoint

## Annual Vs Quarterly Vs TTM Considerations

### Raw Statements

`GET /api/companies/{ticker}/financials` already returns annual and quarterly statement history where filings exist.

Use cases:

- annual views: long-horizon quality, segment stability, capital retention, dilution trend
- quarterly views: recent operating turns, margin compression/recovery, working-capital behavior

Constraints:

- annual and quarterly rows should not be mixed in one comparison view without an explicit cadence choice
- `6-K` periods may exist for foreign issuers and are not always as comparable as `10-Q`

### TTM

TTM does not exist as a first-class raw statement row in the financials endpoint.

Current correct source:

- `GET /api/companies/{ticker}/metrics-timeseries?cadence=ttm`
- `GET /api/companies/{ticker}/metrics?period_type=ttm`

Implication:

- do not synthesize TTM client-side from raw statements if the existing derived-metrics endpoints already provide it

### Balance Sheet And Capital Structure

TTM is generally not the correct mode for balance-sheet and capital-structure fields because those are point-in-time balances rather than flow metrics.

Recommended handling:

- annual or quarterly for balance-sheet tables and charts
- TTM only for derived flow metrics where the backend already computes it

### Segment Data

Segment history is not naturally TTM-friendly in the same way as derived metrics.

Recommended handling:

- support annual and quarterly per-filing segment views where disclosures exist
- do not introduce TTM segment mix as a first-pass requirement

## SEC Sparse By Nature Vs UI-Limited

### Sparse By Nature

These are genuine disclosure limits rather than missing product work.

| Area | Why it is sparse |
|------|------------------|
| Segment disclosures | Many issuers only disclose segment detail annually, only disclose geography, or only disclose revenue without segment operating income |
| Segment comparability | Axis names and reported segment sets can change period to period |
| Geographic margins | Often not disclosed at all; geography is frequently revenue-only |
| TTM raw statements | TTM is derived, not reported as a standalone SEC statement row |
| Regulated-bank segment views | Bank regulatory statements do not map cleanly to the segment workflow |

`app/services/segment_analysis.py` already exposes some of this sparsity through confidence flags such as:

- no prior comparable disclosure
- new or removed segments
- changed segment axis
- business margin missing or partial
- geography revenue-only

`app/services/sec_edgar.py` also limits segment HTML backfill to a recent target set, preferring recent annual statements first.

### UI-Limited

These are current product choices, not hard data constraints.

| Area | Why it is UI-limited |
|------|----------------------|
| Financial header summaries | The page already has full history but surfaces only latest values |
| Financial quality summary | Uses only latest annual and previous annual, even though longer annual history is already loaded |
| Cash flow waterfall | Chooses the latest statement in a cadence instead of allowing period selection across the loaded history |
| Business segment breakdown | Renders latest mix and one comparison even though per-statement `segment_breakdown` history is present on recent statements |
| Companyfacts history module | Frontend parser narrows raw companyfacts to annual-only, four metrics, and 10 fiscal years |
| Capital structure panel | Fetches historical snapshots but foregrounds latest and truncates the visible trend |

## Bank-Mode Caveats

This branch must remain intact.

### How Bank Mode Is Chosen

`app/main.py` calls `_visible_financials_for_company`, which does this:

- load canonical SEC financials
- load regulated-bank financials
- pass both into `select_preferred_financials`

`select_preferred_financials` prefers regulated-bank statements whenever the company is classified as a regulated entity and regulatory financials exist.

Implication:

- `financials[]` on the financials page is not always SEC canonical history
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