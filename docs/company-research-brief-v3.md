# Company Research Brief v3

## Intent

Turn `/company/[ticker]` into the default narrative Research Brief without breaking the existing specialist workspaces.

The brief is not a generic market dashboard. It is the first read for an SEC-first investor workflow:

- start with the cached company snapshot
- move through filing and business changes in order
- judge business quality and capital risk
- compare price with persisted valuation work
- end with an explicit monitor list and drill-down routes

The page stays thin. It only composes persisted frontend endpoints and existing workspace components.

## Default Brief Structure

The default route now answers six investor questions in a fixed order.

### 1. Snapshot
Question: What matters before I read further?

Content:
- price versus operating momentum
- reported segment mix
- compact business context metrics

Primary data:
- company financial workspace payload
- cached price history
- cached annual fundamentals trend data
- reported segment disclosures

### 2. What Changed
Question: What is new since the last filing or review?

Content:
- filing delta scoreboard
- latest-vs-prior filing comparison card
- top alerts and latest dated activity timeline

Primary data:
- `activity-overview`
- `changes-since-last-filing`
- `earnings/summary`

### 3. Business Quality
Question: Is the business getting stronger, weaker, or just noisier?

Content:
- financial quality summary
- margin trend chart
- cash flow waterfall

Primary data:
- cached company financials from the default workspace hook

### 4. Capital & Risk
Question: Is the equity claim being protected, diluted, or put at risk?

Content:
- persisted capital structure intelligence panel when available
- share dilution history
- governance, financing, ownership, insider, and institutional control signals

Primary data:
- `capital-structure`
- `capital-markets/summary`
- `governance/summary`
- `beneficial-ownership/summary`
- cached insider trades summary
- cached institutional holdings history

### 5. Valuation
Question: How does the current price compare with peers and cached model ranges?

Content:
- investment summary panel from cached model outputs
- compact peer snapshot table

Primary data:
- `models`
- `peers`
- cached price history

### 6. Monitor
Question: What should I keep watching after I leave this page?

Content:
- priority alerts
- dated timeline
- explicit next-step monitor checklist

Primary data:
- `activity-overview`
- company refresh state
- cached insider and institutional context

## Route And Navigation Rules

The route contract stays stable.

- `/company/[ticker]` remains the default company route.
- Existing specialist routes stay intact.
- The company subnav now labels the default route as `Brief` instead of `Overview`.
- The brief adds a sticky in-page section nav for the six sections.
- Each section ends with direct links into the most relevant specialist routes.

## Trust, Provenance, And Freshness

The brief keeps the existing source policy explicit.

- Core fundamentals, analytics, and filing-derived summaries remain official/public-source-first.
- Commercial fallback data is only used for price and market-profile context.
- Fallback usage is labeled directly in the header through the existing commercial fallback notice.
- Each section shows compact freshness and provenance cues instead of repeating a full diagnostics panel.
- The utility rail keeps refresh state and background job context visible without converting the route into a live-fetch workflow.

## State Model

The default route now has deterministic route and section states.

### Route-level
- `loading.tsx` renders a brief-specific skeleton with nav chips and section cards.
- `error.tsx` renders a brief-specific retry state.

### Section-level
- Each section renders an explicit loading state when the persisted slice is still resolving.
- Each section renders a deterministic empty state when the slice is cached but incomplete.
- Partial workspace failures do not blank the whole page. The brief shows a compact partial-data warning and keeps the rest of the route usable.

## Endpoint Composition

The page uses two data paths.

### Shared company workspace hook
Used for:
- company identity
- cached financial statements
- annual statements
- price history
- trend data
- insider summary
- institutional holdings
- refresh status
- chart console entries

### Page-local persisted summaries
Loaded in parallel for:
- `activity-overview`
- `changes-since-last-filing`
- `earnings/summary`
- `capital-structure`
- `capital-markets/summary`
- `governance/summary`
- `beneficial-ownership/summary`
- `models`
- `peers`

This keeps the page thin while preferring persisted read endpoints over route-time recomputation.

## Testing And Fixture Notes

The brief is covered by deterministic fixtures in two places.

### Vitest
`frontend/app/company/[ticker]/page.activity-feed.test.ts`

Coverage:
- six-section brief render
- labeled commercial fallback notice
- Form 144 planned-sale labeling in the monitor feed
- deterministic empty states when persisted slices are missing

### Playwright
`frontend/e2e/company-workspace.smoke.spec.ts`

Coverage:
- browser smoke for the default company brief
- deterministic mocked responses for all brief-only persisted endpoints
- content-rich fixture data for snapshot, change monitoring, valuation, and fallback labeling

These fixtures are screenshot-friendly because the page does not depend on live request-path fetches or time-varying vendor data.

## Non-Goals

The brief intentionally does not:

- replace the specialist workspaces
- collapse everything into a generic terminal homepage
- move analytics into the route layer
- hide fallback-source usage behind generic labels
- block initial render on long-running refresh jobs
