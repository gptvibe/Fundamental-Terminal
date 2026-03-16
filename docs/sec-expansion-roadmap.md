# SEC Expansion Roadmap

## Goal

Expand the app from a solid SEC-first financial terminal into a broader investor research product that covers fundamentals, insider activity, institutional ownership, beneficial ownership, governance, filing events, and dilution risk.

Every dataset in this roadmap must ship as a complete vertical slice:

- ingestion and normalization
- database persistence
- API response contract
- frontend visualization
- refresh and cache wiring
- parsing and UI tests

Backend-only ingestion is not considered done.

Execution checklist:

- See `docs/sec-expansion-checklist.md` for the task-by-task build checklist.

## Current Baseline

The app already ingests and uses these SEC sources:

- `company_tickers.json` for ticker and CIK resolution
- `submissions/CIK##########.json` for filing history and filing discovery
- `api/xbrl/companyfacts/CIK##########.json` for normalized financial statements
- filing archive `index.json`, `FilingSummary.xml`, report HTML, Form 4 XML, and 13F information tables
- `efts.sec.gov/LATEST/search-index` for filing search and curated 13F manager resolution

Core backend entry points:

- `app/services/sec_edgar.py`
- `app/services/institutional_holdings.py`
- `app/services/filing_parser.py`
- `app/services/cache_queries.py`
- `app/main.py`

Core frontend entry points:

- `frontend/hooks/use-company-workspace.ts`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `frontend/app/company/[ticker]/page.tsx`
- `frontend/app/company/[ticker]/filings/page.tsx`
- `frontend/app/company/[ticker]/insiders/page.tsx`
- `frontend/app/company/[ticker]/ownership/page.tsx`

## Delivery Rules

1. Add one dataset family at a time.
2. Keep response models typed in both backend and frontend.
3. Prefer normalized tables for filing families with one-to-many records.
4. Prefer existing `financial_statements.data` JSON only for statement-shaped metrics that fit the current canonical model.
5. Gate every new parser behind sample fixtures and deterministic tests.
6. Ship at least one chart and one detail view for each major dataset.
7. Reuse the existing refresh queue and SSE console so users can see SEC fetch progress.

## Phase 1: Close Existing Visibility Gaps

### Outcome

Expose data already fetched on the backend but not fully visible in the UI.

### Scope

- expose stored Form 4 filing metadata
- expose stored 13F filing metadata
- add the missing filing insights API route
- ensure the filings page, insiders page, and ownership page render those fields

### Backend changes

Update serializers in `app/main.py`:

- `_serialize_insider_trade`
  - add `filing_date`
  - add `filing_type`
  - add `accession_number`
  - add `source`
- `_serialize_institutional_holding`
  - add `accession_number`
  - add `filing_date`
  - add `source`

Add or restore a dedicated filing insights route in `app/main.py`:

- `GET /api/companies/{ticker}/filing-insights`
- source data from `get_company_filing_insights` in `app/services/cache_queries.py`
- return latest filing parser snapshots stored with `statement_type == filing_parser`

### Frontend changes

Use the already-declared fields in `frontend/lib/types.ts` and ensure they are backed by the API:

- `InsiderTradePayload`
- `InstitutionalHoldingPayload`
- `CompanyFilingInsightsResponse`

Pages and components to verify:

- `frontend/components/tables/insider-transactions-table.tsx`
- `frontend/components/tables/hedge-fund-activity-table.tsx`
- `frontend/components/filings/filing-parser-insights.tsx`
- `frontend/app/company/[ticker]/filings/page.tsx`

### UI to ship

- insider transactions table with SEC filing date, accession, and source link
- 13F activity table with SEC filing date, accession, and source link
- filing parser snapshot panel backed by a real API route

### Tests

- API response contract tests for insider trades and institutional holdings
- route test for `filing-insights`
- component render tests for the filing metadata cells

## Phase 2: Expand XBRL Fundamentals And Segment Visuals

### Outcome

Broaden the canonical financial model and visualize a deeper investor dashboard.

### New data to normalize

Add mappings in `app/services/sec_edgar.py` for:

- `sga`
- `research_and_development`
- `interest_expense`
- `income_tax_expense`
- `inventory`
- `accounts_receivable`
- `goodwill_and_intangibles`
- `long_term_debt`
- `lease_liabilities`
- `stock_based_compensation`
- `weighted_average_diluted_shares`

Extend segment extraction where available:

- segment operating income
- geographic revenue
- geographic assets

### Persistence approach

Keep these as additions to canonical financial statement payloads unless a metric requires row-level history outside the statement period grain.

Update:

- `app/main.py` financial payload models
- `frontend/lib/types.ts` financial payload types

### Frontend pages and components

Primary pages:

- `frontend/app/company/[ticker]/page.tsx`
- `frontend/app/company/[ticker]/financials` if later added

New or expanded components:

- `frontend/components/charts/financial-margin-trend-chart.tsx`
- `frontend/components/charts/capital-allocation-chart.tsx`
- `frontend/components/charts/balance-sheet-risk-chart.tsx`
- `frontend/components/charts/segment-mix-chart.tsx`
- `frontend/components/company/financial-quality-summary.tsx`

### UI to ship

- margin trend chart
- debt and liquidity chart
- capex, buybacks, dividends, acquisitions chart
- segment mix visualization over time
- financial quality summary cards for dilution, leverage, and cash conversion

### Tests

- parser tests for added tags
- serializer tests for new financial payload fields
- chart smoke tests with representative data

## Phase 3: Deepen Insider And 13F Analysis

### Outcome

Turn insiders and ownership from mostly tabular views into analytical workflows.

### Form 4 improvements

Extend parsing in `app/services/sec_edgar.py` to include where available:

- security title
- derivative versus non-derivative flag
- direct versus indirect ownership nature
- exercise price and expiration date for derivative transactions
- selected footnote text or normalized footnote tags

### 13F improvements

Extend parsing in `app/services/institutional_holdings.py` to include where available:

- option type or put-call flags
- investment discretion
- voting authority
- more than two reporting quarters
- broader manager coverage beyond the curated set

### Suggested schema additions

Add normalized columns or related tables if needed instead of overloading generic text fields.

Candidates:

- `insider_trade_footnotes`
- `institutional_holding_attributes`

### Frontend pages and components

Insiders:

- `frontend/app/company/[ticker]/insiders/page.tsx`
- `frontend/components/insiders/insider-signal-breakdown.tsx`
- `frontend/components/charts/insider-role-activity-chart.tsx`

Ownership:

- `frontend/app/company/[ticker]/ownership/page.tsx`
- `frontend/components/institutional/top-holder-trend.tsx`
- `frontend/components/institutional/conviction-heatmap.tsx`
- `frontend/components/institutional/new-vs-exited-positions.tsx`

### UI to ship

- insider signal quality panel separating open-market trades from admin noise
- role breakdown chart for CEO, CFO, director, and other insiders
- top holder trend chart by quarter
- conviction heatmap by fund and quarter
- new and exited positions summary cards

### Tests

- parser tests for derivative and ownership attributes
- analytics tests for new summary logic
- component tests for filters and chart transforms

## Phase 4: Add Beneficial Ownership Tracking (13D and 13G)

### Outcome

Show activist or large-owner stake changes that matter to investors.

### SEC scope

- `SC 13D`
- `SC 13D/A`
- `SC 13G`
- `SC 13G/A`

### Backend design

Add a dedicated service:

- `app/services/beneficial_ownership.py`

Add tables:

- `beneficial_ownership_reports`
  - company_id
  - filer_name
  - filer_cik if available
  - accession_number
  - filing_type
  - filing_date
  - event_date if parsed
  - percent_owned
  - shares_owned
  - ownership_purpose
  - source
- `beneficial_ownership_parties`
  - report_id
  - party_name
  - role or group designation

Add query helpers in `app/services/cache_queries.py`.

### API contracts

Add endpoints in `app/main.py`:

- `GET /api/companies/{ticker}/beneficial-ownership`
- `GET /api/beneficial-ownership/{ticker}/summary`

### Frontend pages and components

Add a new page:

- `frontend/app/company/[ticker]/ownership-changes/page.tsx`

Add components:

- `frontend/components/ownership/beneficial-owner-timeline.tsx`
- `frontend/components/ownership/beneficial-owner-table.tsx`
- `frontend/components/ownership/activist-signal-panel.tsx`

### UI to ship

- time-series timeline of ownership filings
- latest reported beneficial owners table
- activist signal cards for stake build, amendment, and purpose changes

### Tests

- parser tests from representative 13D and 13G filings
- route tests for ownership pages

## Phase 5: Add Proxy And Governance Data (DEF 14A)

### Outcome

Bring compensation and governance into the research workflow.

### SEC scope

- `DEF 14A`

### Backend design

Add service:

- `app/services/proxy_parser.py`

Add tables:

- `proxy_statements`
  - company_id
  - accession_number
  - filing_date
  - meeting_date
  - source
- `executive_compensation`
  - proxy_statement_id
  - executive_name
  - title
  - salary
  - bonus
  - stock_awards
  - option_awards
  - non_equity_incentive`
  - total_compensation
- `proxy_vote_results`
  - proxy_statement_id
  - proposal_name
  - votes_for
  - votes_against
  - abstentions

### API contracts

Add endpoints:

- `GET /api/companies/{ticker}/governance`
- `GET /api/companies/{ticker}/executive-compensation`

### Frontend pages and components

Add a new page:

- `frontend/app/company/[ticker]/governance/page.tsx`

Add components:

- `frontend/components/governance/executive-pay-table.tsx`
- `frontend/components/governance/pay-trend-chart.tsx`
- `frontend/components/governance/vote-outcomes-panel.tsx`
- `frontend/components/governance/board-summary.tsx`

### UI to ship

- executive compensation table
- pay trend chart
- vote result summary cards
- governance red-flag section on the company overview rail

### Tests

- parser tests against multiple proxy statement formats
- response contract tests for governance endpoints

## Phase 6: Add 8-K Event Intelligence

### Outcome

Turn raw 8-K filings into a classified event feed.

### SEC scope

Focus initial extraction on these item families:

- `1.01` material definitive agreement
- `2.02` results of operations and financial condition
- `2.06` material impairments
- `5.02` director and officer changes
- `8.01` other events

### Backend design

Add service:

- `app/services/eight_k_parser.py`

Add tables:

- `filing_events`
  - company_id
  - accession_number
  - filing_type
  - filing_date
  - item_code
  - event_category
  - title
  - summary
  - source

### API contracts

Add endpoints:

- `GET /api/companies/{ticker}/filing-events`
- `GET /api/companies/{ticker}/filing-events/summary`

### Frontend pages and components

Extend:

- `frontend/app/company/[ticker]/filings/page.tsx`
- `frontend/app/company/[ticker]/page.tsx`

Add components:

- `frontend/components/filings/event-timeline.tsx`
- `frontend/components/filings/event-category-filter.tsx`
- `frontend/components/company/sec-activity-feed.tsx`

### UI to ship

- categorized SEC event timeline
- latest material events feed on overview page
- filters by event category

### Tests

- item classification tests
- filing event route tests

## Phase 7: Add Dilution And Capital-Raise Monitoring

### Outcome

Give investors a dedicated view of financing and dilution risk.

### SEC scope

- `S-1`
- `S-3`
- `F-3`
- `424B*`
- `NT 10-K`
- `NT 10-Q`

### Backend design

Add service:

- `app/services/capital_markets_parser.py`

Add tables:

- `capital_markets_events`
  - company_id
  - accession_number
  - filing_type
  - filing_date
  - event_type
  - amount_raised if parsed
  - shelf_size if parsed
  - security_type
  - summary
  - source

### API contracts

Add endpoints:

- `GET /api/companies/{ticker}/capital-markets`
- `GET /api/companies/{ticker}/capital-markets/summary`

### Frontend pages and components

Add a new page:

- `frontend/app/company/[ticker]/capital-markets/page.tsx`

Add components:

- `frontend/components/capital-markets/dilution-risk-panel.tsx`
- `frontend/components/capital-markets/offering-timeline.tsx`
- `frontend/components/capital-markets/late-filer-alerts.tsx`

### UI to ship

- dilution risk summary cards
- offering timeline
- late filer alerts

### Tests

- parser tests for registration and prospectus classifications
- API contract tests for summary endpoints

## Phase 8: Add Unified Search, Feed, And Alerts

### Outcome

Unify the new SEC datasets into one investor-facing workflow.

### Backend design

Create a normalized event feed assembler in a new service:

- `app/services/sec_activity_feed.py`

Input sources:

- recent filing timeline
- filing events
- insider trades
- 13F changes
- beneficial ownership reports
- governance snapshots
- capital markets events

Add alert rule service:

- `app/services/alert_rules.py`

### API contracts

Add endpoints:

- `GET /api/companies/{ticker}/activity-feed`
- `GET /api/companies/{ticker}/alerts`

### Frontend pages and components

Extend overview:

- `frontend/app/company/[ticker]/page.tsx`

Add components:

- `frontend/components/company/activity-feed.tsx`
- `frontend/components/alerts/sec-alerts-panel.tsx`

### UI to ship

- unified company SEC activity feed
- alert panels for insider drought, activist stakes, dilution, turnover, and filing delays

### Tests

- feed composition tests
- alert rule tests
- component tests for feed ordering and alert severity rendering

## Suggested Sprint Plan

### Sprint 1

- complete Phase 1
- fix existing serializer and route gaps
- ship missing frontend visibility

### Sprint 2

- complete Phase 2
- expand canonical fundamentals and segment visuals

### Sprint 3

- complete Phase 3
- deepen insider and 13F analysis

### Sprint 4

- complete Phase 4
- ship beneficial ownership tracking page

### Sprint 5

- complete Phase 5
- ship governance page and proxy parsing

### Sprint 6

- complete Phase 6 and Phase 7
- ship event intelligence and capital-markets risk views

### Sprint 7

- complete Phase 8
- unify activity feed and alerts

## Prioritization By Investor Value

Highest near-term value:

1. Phase 1 visibility fixes
2. Phase 2 expanded fundamentals and segment visuals
3. Phase 3 deeper insider and 13F analysis

Highest medium-term value:

1. Phase 4 beneficial ownership
2. Phase 6 8-K event intelligence
3. Phase 7 dilution monitoring

Highest strategic value:

1. Phase 5 proxy and governance
2. Phase 8 unified feed and alerts

## Definition Of Done For Each Dataset

A dataset family is complete only when all of the following exist:

- parsed and normalized backend data
- database persistence or explicit cache-only strategy
- typed backend response model
- typed frontend response contract
- at least one chart or timeline view
- at least one table or detail view
- loading, empty, and error states
- representative parser tests
- API response tests

## Immediate Next Build Tasks

If work starts now, implement these first:

1. Add `GET /api/companies/{ticker}/filing-insights` in `app/main.py`.
2. Expose missing Form 4 metadata in `_serialize_insider_trade`.
3. Expose missing 13F metadata in `_serialize_institutional_holding`.
4. Verify `frontend/lib/api.ts` and `frontend/lib/types.ts` match real backend payloads.
5. Confirm the filings, insiders, and ownership pages render the newly exposed fields.
