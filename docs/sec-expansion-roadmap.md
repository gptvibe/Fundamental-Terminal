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

---

## Shipped As Of 2026-03-22

The following phases are fully complete. Their build details have been removed from this document. See `docs/sec-expansion-checklist.md` for the task-level record.

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Close existing visibility gaps (Form 4 metadata, 13F metadata, filing insights route) | ✓ Shipped |
| 2 | Expand XBRL fundamentals and segment visuals (canonical metrics, segment operating income, geographic assets, segment mix chart) | ✓ Shipped |
| 3 | Deepen insider and 13F analysis (signal quality, role breakdown, conviction heatmap, new/exited positions) | ✓ Shipped |
| 4 | Beneficial ownership tracking — SC 13D/G, ownership-changes page, activist signals | ✓ Shipped |
| 5 | Proxy and governance — DEF 14A, vote outcomes, board history, executive pay table and trend chart (`governance/page.tsx`) | ✓ Shipped |
| 6 | 8-K event intelligence — classification, filing-events table, events page, category chart | ✓ Shipped |
| 7 | Dilution and capital-raise monitoring — S-1/S-3/424B/NT filings, capital-markets page | ✓ Shipped |
| 8 | Unified activity feed and alerts — activity-feed and alerts routes, sec-feed page, Form 144 in feed | ✓ Shipped |
| 9 | Valuation workbench depth — trust-aware DCF, Treasury risk-free input, reverse DCF, ROIC, capital allocation, peers/watchlist decision metrics | ✓ Shipped |
| 10 | Market Context 2.0 + Residual Income Valuation — official-source macro providers (HQM, BLS, BEA), DB-first enriched macro snapshot, residual income model v1.0.0, DCF v2.2.0 sector risk premiums, MacroStrip component | ✓ Shipped |

### Core backend entry points

- `app/services/sec_edgar.py`
- `app/services/institutional_holdings.py`
- `app/services/filing_parser.py`
- `app/services/beneficial_ownership.py`
- `app/services/proxy_parser.py`
- `app/services/eight_k_events.py`
- `app/services/capital_markets.py`
- `app/services/cache_queries.py`
- `app/main.py`

### Shipped routes

```
GET  /api/companies/{ticker}/financials
GET  /api/companies/{ticker}/filing-insights
GET  /api/companies/{ticker}/insider-trades
GET  /api/companies/{ticker}/form-144-filings
GET  /api/companies/{ticker}/institutional-holdings
GET  /api/companies/{ticker}/beneficial-ownership
GET  /api/companies/{ticker}/beneficial-ownership/summary
GET  /api/companies/{ticker}/governance
GET  /api/companies/{ticker}/governance/summary
GET  /api/companies/{ticker}/executive-compensation
GET  /api/companies/{ticker}/filing-events
GET  /api/companies/{ticker}/filing-events/summary
GET  /api/companies/{ticker}/capital-markets
GET  /api/companies/{ticker}/capital-markets/summary
GET  /api/companies/{ticker}/activity-feed
GET  /api/companies/{ticker}/alerts
GET  /api/companies/{ticker}/activity-overview
```

### Shipped frontend pages

- `/company/[ticker]` — overview with unified activity feed, priority alerts, and financial visuals
- `/company/[ticker]/financials` — financial statements, charts, and segment breakdown
- `/company/[ticker]/peers` — decision comparison workspace with fair-value gap, ROIC, implied growth, shareholder yield, and valuation-band percentile
- `/company/[ticker]/filings` — filing timeline, filing-event classification, and parser insights
- `/company/[ticker]/insiders` — Form 4 analytics, signal quality, role breakdown, and Form 144 planned sales
- `/company/[ticker]/ownership` — institutional holdings analytics, conviction heatmap, and turnover
- `/company/[ticker]/ownership-changes` — beneficial ownership (SC 13D/G) timeline, owner table, and activist signals
- `/company/[ticker]/governance` — DEF 14A filings, vote outcomes, board history, executive pay table, and pay trend chart
- `/company/[ticker]/capital-markets` — registration statements, prospectuses, and late-filer notices
- `/company/[ticker]/events` — 8-K events classified by item code with category chart
- `/company/[ticker]/sec-feed` — unified SEC activity timeline and prioritized alerts
- `/company/[ticker]/models` — valuation workbench with trust-aware DCF, reverse DCF heatmap, ROIC trend, capital-allocation stack, and assumption provenance
- `/company/[ticker]/stakes` — redirects to `/company/[ticker]/ownership-changes`

### Shipped personal workflow

- Browser-local watchlist and private notes are available without auth.
- Local data can be exported/imported as `LocalUserData` JSON and cleared entirely from the saved-companies workflow.
- Import is merge-by-default with an explicit replace option.

### Cache-first request paths

- Persisted company research routes are cache-first and do not block on live SEC fetches.
- If data is stale or missing, routes return cached/empty payloads and queue refresh in the background.
- Explicit live SEC utility routes remain available for direct utility workflows (filing search, filing embed view, financial-history/companyfacts).

---

## Remaining Work

Core SEC dataset expansion and valuation-workbench depth are now shipped through Phase 9.

Future roadmap work should prioritize model calibration quality, interaction telemetry-guided UX iteration, and performance hardening over adding new ingestion families.

### SEC-Heavy Earnings Models (Next Sequence)

This sequence starts with SEC-first earnings modeling and keeps external dependencies optional.

Current sprint note (PR1 in progress):

- Add cache-first derived metrics timeseries route from canonical SEC financial cache + cached price history with typed provenance/quality fields and a financials-page panel visualization.

Earnings sprint update (2026-03-26):

- Shipped cache-first `/api/companies/{ticker}/earnings/workspace` with persisted SEC-heavy earnings model points, explainability payloads (SEC tags + periods + proxy usage), directional backtests (cached price windows), peer-relative percentiles, and threshold alerts.
- Wired earnings model recomputation into the existing refresh queue/SSE flow and preserved non-blocking cache-first response behavior.

1. Ship SEC-heavy earnings model panel on `/company/[ticker]/earnings` (quality score trend, EPS drift, segment contribution delta) using cached 10-Q/10-K statement data.
2. Improve parser precision for Item 2.02 exhibits so release-level revenue/EPS coverage rises and fallback usage declines.
3. Add model diagnostics chips (coverage ratio, fallback ratio, stale period warning) so users know confidence level at a glance.
4. Add backtests for model signal stability per ticker (directional consistency of quality score and EPS drift around earnings windows).
5. Add peer-relative SEC model context on the earnings page (issuer percentile vs sector for quality and EPS drift).
6. Add explainability panel that logs exact formula inputs from SEC fields for each model point.
7. Add alerts for threshold moves (quality score regime shift, EPS drift sign flip, segment share change beyond threshold).
8. Only after SEC-heavy quality is stable, layer optional non-SEC augmentations (consensus surprise and transcript sentiment) behind explicit source labels.

---

## Delivery Rules (Ongoing)

1. Add one dataset family at a time.
2. Keep response models typed in both backend and frontend.
3. Prefer normalized tables for filing families with one-to-many records.
4. Gate every new parser behind sample fixtures and deterministic tests.
5. Ship at least one chart and one detail view for each major dataset.
6. Reuse the existing refresh queue and SSE console so users can see SEC fetch progress.

## Definition Of Done For Each Dataset

- parsed and normalized backend data
- database persistence or explicit cache-only strategy
- typed backend response model
- typed frontend response contract
- at least one chart or timeline view
- at least one table or detail view
- loading, empty, and error states
- representative parser tests
- API response tests
