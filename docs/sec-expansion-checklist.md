# SEC Expansion Execution Checklist

## How To Use This Checklist

- Treat each phase as a vertical slice.
- Do not mark a dataset complete until backend ingestion, API wiring, frontend visualization, and tests are all done.
- Keep backend and frontend types in sync before merging.
- Prefer small pull requests grouped by one page or one dataset family.

## Sprint 9: Valuation Workbench Depth (Shipped 2026-03-22)

### Valuation foundations

- [x] Extend canonical SEC normalization/serialization with:
  - [x] `cash_and_cash_equivalents`
  - [x] `short_term_investments`
  - [x] `cash_and_short_term_investments`
  - [x] `current_debt`
  - [x] `stockholders_equity`
  - [x] `accounts_payable`
  - [x] `depreciation_and_amortization`
- [x] Add parser and serializer tests for expanded valuation fields.

### External no-key risk-free input

- [x] Add Treasury-direct 10-year risk-free fetch path (no API key).
- [x] Cache latest successful Treasury snapshot for 24 hours.
- [x] Add retry/backoff and cached fallback behavior on temporary failures.
- [x] Expose source/tenor/observation date/rate in model assumption provenance.

### Trust-aware model outputs

- [x] Add explicit model statuses (`ok | partial | proxy | insufficient_data`) and explanation strings.
- [x] Mark models partial when >=2 canonical required inputs are missing across recent fiscal years.
- [x] Mark models proxy when substitutions/approximations are used.
- [x] Upgrade DCF output to enterprise value, net debt, equity value, fair value per share, and confidence summary.

### New models and ratios

- [x] Add `reverse_dcf` model output (with implied growth and heatmap payload).
- [x] Add `roic` model output (ROIC, incremental ROIC, reinvestment, spread vs capital-cost proxy).
- [x] Add `capital_allocation` model output (dividends, buybacks, debt changes, SBC, shareholder yield).
- [x] Expand ratio outputs with investor-grade metrics (`interest_coverage`, `cash_conversion`, `capex_intensity`, `sbc_to_revenue`, `net_debt_to_fcf`, `payout_ratio`).
- [x] Add backend tests for normal/partial/insufficient scenarios for new models.

### Decision workflows

- [x] Extend peers payload/UI with fair-value gap, ROIC, implied growth, shareholder yield, and valuation-band percentile.
- [x] Extend watchlist payload/UI with triage metrics for undervaluation, quality, capital return, and balance-sheet risk.
- [x] Add frontend sort/filter tests for watchlist decision triage behavior.

## Sprint 10: Market Context 2.0 + Residual Income Valuation (Shipped 2026-03-23)

### Macro data pipeline (official sources)

- [x] Add official-source providers for Treasury HQM, BLS Public API v1, and BEA proxy series via FRED.
- [x] Persist macro snapshots and observations in PostgreSQL using DB-first/cache-first read paths.
- [x] Add grouped macro response sections: `rates_credit`, `inflation_labor`, `growth_activity`.
- [x] Keep API/service naming as `market-context` while using "Macro" as the user-facing label.

### Valuation model updates

- [x] Add `residual_income` model v1.0.0 with status handling (`ok | partial | proxy | insufficient_data`).
- [x] Mark `residual_income` as primary for financial firms where DCF is unsupported.
- [x] Upgrade DCF to v2.2.0 with sector risk premium adjustments in discount rate assumptions.

### API and frontend integration

- [x] Extend `CompanyMarketContextResponse` with v2 macro fields and grouped series payloads.
- [x] Wire `/api/market-context` and `/api/companies/{ticker}/market-context` to v2 DB-first services.
- [x] Add grouped Macro sections to home dashboard.
- [x] Add `MacroStrip` to company overview pages.

### Test coverage

- [x] Add provider tests for HQM/BLS/BEA fetch and fallback behavior.
- [x] Add model tests for `residual_income` and DCF sector risk premium behavior.
- [x] Keep regression tests green for valuation and market-context paths.

## Sprint 1: Existing SEC Data Visibility Gaps

### Backend API contracts

- [x] Add `GET /api/companies/{ticker}/filing-insights` to `app/main.py`.
- [x] Add a response model for filing insights in `app/main.py` if not already declared.
- [x] Use `get_company_filing_insights` from `app/services/cache_queries.py` in the new route.
- [x] Return latest filing parser snapshots ordered by `period_end` descending.

Acceptance criteria:

- Route returns HTTP 200 for a company with cached filing parser data.
- Route returns an empty `insights` list for a company without filing parser data.

### Backend serializer fixes

- [x] Update `_serialize_insider_trade` in `app/main.py` to return:
  - [x] `filing_date`
  - [x] `filing_type`
  - [x] `accession_number`
  - [x] `source`
- [x] Update `_serialize_institutional_holding` in `app/main.py` to return:
  - [x] `accession_number`
  - [x] `filing_date`
  - [x] `source`

Acceptance criteria:

- Insider trade API payload matches the fields declared in `frontend/lib/types.ts`.
- Institutional holdings API payload matches the fields declared in `frontend/lib/types.ts`.

### Frontend data plumbing

- [x] Verify `getCompanyFilingInsights` in `frontend/lib/api.ts` points to a real backend route.
- [x] Verify `CompanyFilingInsightsResponse` in `frontend/lib/types.ts` matches backend payload.
- [x] Verify `InsiderTradePayload` and `InstitutionalHoldingPayload` remain aligned with backend output.

Acceptance criteria:

- No frontend runtime errors caused by missing response fields.
- TypeScript types match actual API payloads.

### Frontend UI verification

- [x] Verify filing metadata renders in `frontend/components/tables/insider-transactions-table.tsx`.
- [x] Verify filing metadata renders in `frontend/components/tables/hedge-fund-activity-table.tsx`.
- [x] Verify `frontend/components/filings/filing-parser-insights.tsx` loads real data.
- [x] Verify `frontend/app/company/[ticker]/filings/page.tsx` handles loading, empty, and error states for filing insights.

Acceptance criteria:

- Insider table shows filing date, accession, and SEC source link.
- 13F table shows filing date, accession, and SEC source link.
- Filing parser snapshot panel renders cached results when present.

### Tests

- [x] Add API route test for `GET /api/companies/{ticker}/filing-insights`.
- [x] Add serializer tests for insider and institutional payloads.
- [x] Add frontend render tests for filing metadata cells if a frontend test harness exists.

Definition of done:

- All three pages show currently fetched SEC metadata.
- No placeholder fields remain disconnected from backend output.

## Sprint 2: Expanded XBRL Fundamentals And Segment Visuals

### Canonical metric expansion

- [x] Add companyfacts mappings in `app/services/sec_edgar.py` for:
  - [x] `sga`
  - [x] `research_and_development`
  - [x] `interest_expense`
  - [x] `income_tax_expense`
  - [x] `inventory`
  - [x] `accounts_receivable`
  - [x] `goodwill_and_intangibles`
  - [x] `long_term_debt`
  - [x] `lease_liabilities`
  - [x] `stock_based_compensation`
  - [x] `weighted_average_diluted_shares`

Acceptance criteria:

- New metrics are normalized for representative 10-K and 10-Q filings.
- Existing metrics continue to serialize unchanged.

### Segment expansion (2026-03-20)

- [x] Extend segment extraction in `app/services/sec_edgar.py` to capture per-segment `operating_income` and `assets` from both the XBRL companyfacts path (via `SEGMENT_SUPPLEMENTAL_TAGS`) and the HTML filing parser path.
- [x] Add `operating_income` and `assets` fields to `FinancialSegmentPayload` in `app/main.py`.
- [x] Add `operating_income` and `assets` fields to `FinancialSegmentPayload` in `frontend/lib/types.ts`.
- [x] Add segment operating margin bar chart to `frontend/components/charts/business-segment-breakdown.tsx` (renders when data present).
- [x] Show operating income, operating margin, and assets in segment tooltip.

### Response model updates

- [x] Extend financial payload model in `app/main.py`.
- [x] Extend `FinancialPayload` in `frontend/lib/types.ts`.
- [x] Confirm `useCompanyWorkspace` continues to function with additional fields in `frontend/hooks/use-company-workspace.ts`.

Acceptance criteria:

- Backend and frontend types compile cleanly.
- Existing pages do not regress.

### Frontend components

- [x] Add a margin trend chart component under `frontend/components/charts/` (shipped as `margin-trend-chart.tsx`).
- [x] Add a capital allocation chart component under `frontend/components/charts/` (covered by `cash-flow-waterfall-chart.tsx` and `share-dilution-tracker-chart.tsx`).
- [x] Add a balance-sheet risk chart component under `frontend/components/charts/` (covered by `balance-sheet-chart.tsx` and `liquidity-capital-chart.tsx`).
- [x] Add a segment mix chart component under `frontend/components/charts/`.
- [x] Add a financial quality summary component under `frontend/components/company/`.

### Frontend page integration

- [x] Extend `frontend/app/company/[ticker]/page.tsx` with new financial summary visuals.
- [x] Decide whether to add a dedicated financials page or keep visual expansion on the overview page (dedicated page shipped at `frontend/app/company/[ticker]/financials/page.tsx`).

Acceptance criteria:

- Users can see margin, capital allocation, leverage, and segment visuals.
- New charts work on desktop and mobile layouts.

### Tests

- [x] Add parser tests for newly mapped XBRL tags.
- [x] Add serializer tests for expanded financial payloads.
- [x] Add chart transform tests for representative financial data.

Definition of done:

- Expanded fundamentals are both stored and visualized.

## Sprint 3: Deeper Insider And 13F Analysis

### Form 4 parser improvements

- [ ] Extend Form 4 parsing in `app/services/sec_edgar.py` to capture:
  - [x] security title
  - [x] derivative vs non-derivative flag
  - [x] direct vs indirect ownership
  - [x] exercise price if present
  - [x] expiration date if present
  - [x] optional normalized footnote tags

### 13F parser improvements

- [ ] Extend 13F parsing in `app/services/institutional_holdings.py` to capture where available:
  - [x] put-call flags
  - [x] discretion
  - [x] voting authority
  - [x] more than two quarters of history
- [x] Design a safe expansion strategy for broader manager coverage.

Acceptance criteria:

- Data model supports deeper analysis without breaking current pages.
- Historical snapshots can support quarter-over-quarter visualizations.

### Frontend components

- [x] Add insider signal quality component under `frontend/components/insiders/`.
- [x] Add insider role activity chart under `frontend/components/charts/`.
- [x] Add top holder trend component under `frontend/components/institutional/`.
- [x] Add conviction heatmap under `frontend/components/institutional/`.
- [x] Add new vs exited positions summary under `frontend/components/institutional/`.

### Frontend page integration

- [x] Extend `frontend/app/company/[ticker]/insiders/page.tsx` with signal-quality visuals.
- [x] Extend `frontend/app/company/[ticker]/ownership/page.tsx` with conviction and turnover visuals.

Acceptance criteria:

- Insiders page distinguishes open-market signal from low-signal activity.
- Ownership page highlights conviction, concentration, and flow changes.

### Tests

- [x] Add parser tests for derivative and ownership attributes.
- [x] Add analytics tests for updated insider and 13F summaries.

Definition of done:

- Insider and institutional sections are analytical, not just tabular.

## Sprint 4: Beneficial Ownership (13D and 13G)

### Backend scaffolding

- [x] Create `app/services/beneficial_ownership.py`.
- [x] Add migration for `beneficial_ownership_reports`.
- [x] Add migration for `beneficial_ownership_parties` if needed.
- [x] Add ORM models under `app/models/`.
- [x] Add query helpers in `app/services/cache_queries.py`.

### SEC ingestion

- [x] Detect `SC 13D`, `SC 13D/A`, `SC 13G`, and `SC 13G/A` from submissions.
- [x] Parse filer name, ownership percentage, share count, filing date, and source URL.
- [x] Normalize amendment history.

### API contracts

- [x] Add `GET /api/companies/{ticker}/beneficial-ownership`.
- [x] Add `GET /api/companies/{ticker}/beneficial-ownership/summary`.
- [x] Add corresponding frontend types in `frontend/lib/types.ts`.
- [x] Add API calls in `frontend/lib/api.ts`.

### Frontend visualization

- [x] Add `frontend/app/company/[ticker]/ownership-changes/page.tsx`.
- [x] Add beneficial owner timeline component.
- [x] Add beneficial owner table component.
- [x] Add activist signal panel.

Acceptance criteria:

- Users can see major beneficial owners and stake changes over time.
- Activist-style stake changes are visually highlighted.

### Tests

- [x] Add parser tests for representative 13D and 13G filings.
- [x] Add route tests for ownership-change APIs.

Definition of done:

- Beneficial ownership is visible as a standalone investor workflow.

## Sprint 5: Proxy And Governance (DEF 14A)

### Backend scaffolding

- [x] Create `app/services/proxy_parser.py` (live-derived via `parse_proxy_filing_signals`).
- [x] Add migrations for persistent `proxy_statements`, `executive_compensation`, `proxy_vote_results` tables.
- [x] Add ORM models under `app/models/` for proxy persistence.

### SEC ingestion

- [x] Detect and ingest `DEF 14A` filings.
- [x] Parse meeting date and source URL.
- [x] Parse high-level vote outcomes when available.
- [x] Parse named executive compensation table into structured rows (via `_extract_exec_comp_rows` in `proxy_parser.py`).

### API contracts

- [x] Add `GET /api/companies/{ticker}/governance`.
- [x] Add `GET /api/companies/{ticker}/governance/summary`.
- [x] Add `GET /api/companies/{ticker}/executive-compensation`.
- [x] Add matching frontend API and types.

### Frontend visualization

- [x] Add `frontend/app/company/[ticker]/governance/page.tsx`.
- [x] Add board & meeting history table.
- [x] Add vote outcomes panel with visual for/against bars.
- [x] Add executive pay table.
- [x] Add pay trend chart.

Acceptance criteria:

- Governance data is visible from a dedicated page. ✓
- Vote outcomes and board history are understandable without reading the filing. ✓

### Tests

- [x] Add parser tests against multiple proxy formats (see `tests/test_proxy_parser.py`).
- [x] Add API route tests for governance endpoints (see `tests/test_sec_expansion_routes.py`).

Definition of done:

- Governance is a first-class research surface. ✓ (proxy persistence deferred)

## Cache-First Workflow Polish (2026-03-22)

### Backend request-path policy

- [x] Remove live SEC fallback from persisted company-data routes for governance, beneficial ownership, filing events, capital markets, activity feed, alerts, and watchlist summary.
- [x] Add `GET /api/companies/{ticker}/activity-overview` with shared cached feed entries + alerts + summary + refresh metadata.
- [x] Keep existing public routes (`activity-feed`, `alerts`) and serve them from the same shared cached activity bundle.

### Watchlist summary performance

- [x] Rework `POST /api/watchlist/summary` into a bulk cached aggregation path.
- [x] Use aggregate count queries for financial and price coverage instead of loading full histories.
- [x] Keep per-ticker failure tolerance with fallback payloads.

### Frontend workflow and cost

- [x] Consolidate overview and SEC feed activity calls to one `activity-overview` request.
- [x] Remove extra overview-page Altman API fetch.
- [x] Dynamically load heavy models-page components to reduce first-load JS.
- [x] Keep saved companies and notes browser-only with no auth/backend persistence.
- [x] Harden local JSON import/export UX: merge-by-default import, replace option, and clear-all confirmation.

## Sprint 6: 8-K Event Intelligence

### Backend scaffolding

- [x] Create `app/services/eight_k_parser.py`.
- [x] Add migration for `filing_events`.
- [x] Add ORM model for filing events.

### SEC ingestion

- [x] Classify 8-K item codes for at least:
  - [x] 1.01
  - [x] 2.02
  - [x] 2.06
  - [x] 5.02
  - [x] 8.01
- [x] Create normalized event summaries.

### API contracts

- [x] Add `GET /api/companies/{ticker}/filing-events`.
- [x] Add `GET /api/companies/{ticker}/filing-events/summary`.
- [x] Add matching frontend API and types.

### Frontend visualization

- [x] Extend `frontend/app/company/[ticker]/filings/page.tsx` with an event timeline.
- [x] Add a reusable SEC activity feed component (delivered as `frontend/app/company/[ticker]/events/page.tsx` with `FilingEventCategoryChart`).
- [x] Add category filters (filter strip added to filings page, 2026-03-20).
- [x] Add a latest material events panel on `frontend/app/company/[ticker]/page.tsx` (covered by "Live Activity & Alerts" panel using the activity feed).

Acceptance criteria:

- Users can filter 8-K events by category.
- Overview page surfaces recent material filing events.

### Tests

- [x] Add event-classification tests for 8-K samples (see `tests/test_eight_k_events.py`).
- [x] Add API route tests for event endpoints.

Definition of done:

- 8-K filings are translated into an event workflow users can browse quickly.

## Sprint 7: Dilution And Capital Markets Risk

### Backend scaffolding

- [x] Create `app/services/capital_markets.py`.
- [x] Add migration for `capital_markets_events` (see `20260319_0012_add_capital_markets_events_cache.py`).
- [x] Add ORM model for capital markets events.

### SEC ingestion

- [x] Detect and classify:
  - [x] `S-1`, `S-3`, `F-3`
  - [x] `424B*`
  - [x] `NT 10-K`, `NT 10-Q`
- [x] Parse event type, security type, filing date, source, and summary.
- [x] Capture shelf size or raise amount when extractable.

### API contracts

- [x] Add `GET /api/companies/{ticker}/capital-markets`.
- [x] Add `GET /api/companies/{ticker}/capital-markets/summary`.
- [x] Add matching frontend API and types.

### Frontend visualization

- [x] Add `frontend/app/company/[ticker]/capital-markets/page.tsx`.
- [x] Add dilution risk / offering summary panel.
- [x] Add late-filer alerts within the capital-markets page.

Acceptance criteria:

- Users can identify dilution and financing risk from a dedicated UI. ✓
- Late-filer warnings are visible without opening raw filings. ✓

### Tests

- [x] Add route tests for capital-markets endpoints (see `tests/test_sec_expansion_routes.py`).

Definition of done:

- Dilution and financing activity is visualized and searchable. ✓

## Sprint 8: Unified Activity Feed And Alerts

### Backend feed assembly

- [x] Compose a unified feed from filing timeline, filing events, insider trades, Form 144 planned sales, 13F changes, beneficial ownership changes, governance updates, and capital markets events (assembled in `_load_company_activity_data` / `_build_activity_feed_entries` in `app/main.py`).

### Backend alerts

- [x] Implement alert rules for:
  - [x] insider buying drought
  - [x] new activist stake (SC 13D ≥ 5%)
  - [x] sudden large institutional exits (≥ 20% position reduction)
  - [x] recent financing or dilution filing
  - [x] late filing notices
- [x] Alerts sorted by severity then newest-first (fixed 2026-03-21).
- [x] Activity loader is partial-data tolerant — routes degrade gracefully when one cache source is unavailable (fixed 2026-03-21).

### API contracts

- [x] Add `GET /api/companies/{ticker}/activity-feed`.
- [x] Add `GET /api/companies/{ticker}/alerts`.
- [x] Add matching frontend API and types.

### Frontend visualization

- [x] Extend `frontend/app/company/[ticker]/page.tsx` with a unified activity feed and alerts panel.
- [x] Ship `frontend/app/company/[ticker]/sec-feed/page.tsx` as a dedicated unified SEC timeline and alerts view.
- [x] Severity styling (high/medium/low) and source badges.

Acceptance criteria:

- Overview page provides one place to review important SEC activity. ✓
- Alerts summarize decision-relevant changes without requiring raw filing review. ✓
- Newest alerts appear first within each severity tier. ✓ (fixed 2026-03-21)

### Tests

- [x] Alert and feed route tests (see `tests/test_sec_expansion_routes.py` — 47/47 green as of 2026-03-21).

Definition of done:

- SEC data across filing families is unified into a coherent investor workflow. ✓

## Cross-Cutting Tasks

### Data quality and fixtures

- [x] Create a reusable SEC fixture directory for representative filings (see `tests/fixtures/`).
- [x] Add fixtures for 8-K, Form 4, 13F, 13D/G, DEF 14A, S-3, Form 144, and NT filings (see `tests/fixtures/README.md`).
- [x] Add parser test coverage before broadening production ingestion (fixture-backed tests in `tests/test_proxy_parser.py`).

### Refresh and cache wiring

- [ ] Reuse existing refresh queue and SSE reporting where possible.
- [ ] Add progress stage names for new dataset families.
- [ ] Add cache TTL decisions for new SEC document classes.

### Documentation

- [ ] Keep `docs/sec-expansion-roadmap.md` updated when scope changes.
- [ ] Update `README.md` when major new pages or APIs ship.

### Release discipline

- [ ] Ship each sprint with both backend and frontend complete.
- [ ] Avoid merging hidden backend-only datasets.
