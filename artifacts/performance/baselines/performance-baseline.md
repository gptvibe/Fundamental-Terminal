# Performance Baseline

Generated: 2026-05-21T02:00:36.957Z

## Run Command

```bash
npm --prefix frontend run audit:performance -- --ticker AAPL --search-query "AAPL" --topbar-query "MSFT" --resolve-query "NET"
```

Prerequisites:
- Start the backend with `PERFORMANCE_AUDIT_ENABLED=true`.
- Start the frontend with `NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=true`.
- Keep the services on the default local ports or pass `--frontend-url` / `--backend-url`.
- Use `--search-query` to exercise exact autocomplete + submit reuse, `--topbar-query` for company-page top-bar search, and `--resolve-query` to force a resolve fallback probe.

Search-flow counters are only collected when the frontend performance audit flag is enabled, and duplicate same-query requests are counted when the same `/companies/search` input repeats within 1.5s.

## Search Flow Audit

| Flow | Phase | Autocomplete | Submit Search | Resolve Fallback | Aborted Autocomplete | Duplicate Same Query | Search→Resolve Pairs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Homepage search | cold | 1 | 0 | 0 | 0 | 0 | 0 |
| Homepage search | warm | 1 | 0 | 0 | 0 | 0 | 0 |
| Homepage resolve fallback | cold | 1 | 0 | 0 | 0 | 0 | 0 |
| Homepage resolve fallback | warm | 1 | 0 | 0 | 0 | 0 | 0 |
| Top-bar search | cold | 1 | 0 | 0 | 1 | 0 | 0 |
| Top-bar search | warm | 1 | 0 | 0 | 1 | 0 | 0 |
| Top-bar resolve fallback | cold | 1 | 0 | 0 | 1 | 0 | 0 |
| Top-bar resolve fallback | warm | 1 | 0 | 0 | 1 | 0 | 0 |
| /company/[ticker] | cold | 0 | 0 | 0 | 0 | 0 | 0 |
| /company/[ticker] | warm | 0 | 0 | 0 | 0 | 0 | 0 |
| Models | cold | 0 | 0 | 0 | 0 | 0 | 0 |
| Models | warm | 0 | 0 | 0 | 0 | 0 | 0 |
| Financials | cold | 0 | 0 | 0 | 0 | 0 | 0 |
| Financials | warm | 0 | 0 | 0 | 0 | 0 | 0 |
| Watchlist | cold | 0 | 0 | 0 | 0 | 0 | 0 |
| Watchlist | warm | 0 | 0 | 0 | 0 | 0 | 0 |

### Search Flow Totals

- Autocomplete requests: 8
- Submit-triggered search requests: 0
- Resolve fallback requests: 0
- Aborted autocomplete requests: 4
- Duplicate same-query requests (1500ms window): 0
- Search-to-resolve back-to-back pairs: 0

### Duplicate Same-Query Search Requests

| Flow | Phase | Query | Gap (ms) | First Source | Second Source | First Cache | Second Cache |
| --- | --- | --- | ---: | --- | --- | --- | --- |
No duplicate same-query search requests were captured in the audited flows.

### Search Then Resolve Pairs

| Flow | Phase | Query | Gap (ms) | Search Source | Search Cache | Resolve Source |
| --- | --- | --- | ---: | --- | --- | --- |
No search-to-resolve back-to-back pairs were captured in the audited flows.

## Request Budgets

| Flow | Phase | Max Requests | Max Network | Actual Requests | Actual Network | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| /company/[ticker] | cold | 24 | 10 | 97 | 4 | FAIL |
| /company/[ticker] | warm | 24 | 8 | 110 | 1 | FAIL |

## Top 10 Slowest Routes

| Route | Kind | Warm p50 (ms) | Warm p95 (ms) | Avg SQL Count | Avg SQL (ms) | Avg Serialize (ms) | Avg Payload (KB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| /api/watchlist/summary | refresh | 155.77 | 252.11 | 0 | 0 | 0 | 0 |
| /api/companies/{ticker}/insider-trades | read | 25.64 | 104.89 | 0 | 0 | 0 | 0 |
| /api/companies/{ticker}/changes-since-last-filing | read | 31.1 | 49.64 | 0 | 0 | 0 | 0 |
| /api/watchlist/calendar | read | 32.43 | 47.59 | 0 | 0 | 0 | 0 |
| /api/companies/{ticker}/governance/summary | read | 42.23 | 46.49 | 0 | 0 | 0 | 0 |
| /api/source-registry | read | 13.68 | 30.88 | 0 | 0 | 0 | 0 |
| /api/companies/{ticker}/beneficial-ownership/summary | read | 24.46 | 29.27 | 0 | 0 | 0 | 0 |
| /api/companies/{ticker}/earnings/summary | read | 20.66 | 27.97 | 0 | 0 | 0 | 0 |
| /api/companies/{ticker}/institutional-holdings | read | 18.78 | 26.3 | 0 | 0 | 0 | 0 |
| /api/companies/{ticker}/activity-overview | read | 24.67 | 26.21 | 0 | 0 | 0 | 0 |

## Top 10 Most Over-Fetched Page Flows

| Flow | Phase | Requests | Network | Cache Hits | Backend SQL Queries | Serialize (ms) | Payload (KB) | Page Elapsed (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Homepage resolve fallback | cold | 241 | 8 | 233 | 0 | 0 | 0 | 6463 |
| Homepage resolve fallback | warm | 233 | 2 | 231 | 0 | 0 | 0 | 6684 |
| /company/[ticker] | warm | 110 | 1 | 109 | 0 | 0 | 0 | 5293 |
| Homepage search | cold | 101 | 8 | 93 | 0 | 0 | 0 | 6431 |
| /company/[ticker] | cold | 97 | 4 | 93 | 0 | 0 | 0 | 5210 |
| Homepage search | warm | 84 | 3 | 81 | 0 | 0 | 0 | 6683 |
| Financials | warm | 63 | 0 | 63 | 0 | 0 | 0 | 5176 |
| Financials | cold | 59 | 4 | 55 | 0 | 0 | 0 | 5127 |
| Top-bar resolve fallback | cold | 58 | 2 | 56 | 0 | 0 | 0 | 3399.3 |
| Top-bar search | warm | 56 | 1 | 55 | 0 | 0 | 0 | 3418.5 |

## Duplicate Request Sources

| Flow | Phase | Source | Route | Count |
| --- | --- | --- | --- | ---: |
| Homepage resolve fallback | cold | company-workspace:initial-load | /companies/NET/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 233 |
| Homepage resolve fallback | warm | company-workspace:initial-load | /companies/NET/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 225 |
| /company/[ticker] | warm | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 107 |
| /company/[ticker] | cold | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 94 |
| Homepage search | cold | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 93 |
| Homepage search | warm | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 77 |
| Financials | warm | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_earnings_summary=true | 61 |
| Financials | cold | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_earnings_summary=true | 57 |
| Top-bar resolve fallback | cold | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 56 |
| Top-bar search | warm | company-workspace:initial-load | /companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=3200&price_max_points=480&include_overview_brief=true | 55 |

## Cold vs Warm Timings

| Flow | Cold (ms) | Warm (ms) | Cold Requests | Warm Requests | Warm Cache Hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Homepage search | 6431 | 6683 | 101 | 84 | 81 |
| Homepage resolve fallback | 6463 | 6684 | 241 | 233 | 231 |
| Top-bar search | 2981.3 | 3418.5 | 55 | 56 | 55 |
| Top-bar resolve fallback | 3399.3 | 3597.5 | 58 | 55 | 54 |
| /company/[ticker] | 5210 | 5293 | 97 | 110 | 109 |
| Models | 92.1 | 4 | 1 | 2 | 2 |
| Financials | 5127 | 5176 | 59 | 63 | 63 |
| Watchlist | 265.4 | 212.7 | 2 | 2 | 1 |

## Recommendations By Expected Impact

### High Impact
- Collapse the company overview research-brief fan-out into one server-composed workspace payload. The overview flow currently pays for multiple summary endpoints in parallel even after the base financial payload lands.
- Reuse tab-shared company payloads across overview, models, and financials. The models and financials pages repeat financial and capital-structure reads that the overview path already fetched.
- Trim the heaviest route payloads before touching the public contract. Large default arrays are driving both response bytes and server-side serialization cost on the slowest read routes.

### Medium Impact
- Stop watchlist dual-fetch and polling from competing with the rest of the page. Summary and calendar are always requested together and the three-second poll loop can keep the page chatty.
- Treat stale-cache returns separately from background revalidation in the UI. A page can feel slow even when network fan-out is lower because the client still fans out many logical reads and background revalidators.
- Memoize or batch homepage search follow-ups. The audit makes it visible when autocomplete search and resolve-style lookup happen back-to-back for the same input.

### Lower Impact
- Increase the visibility of route-level payload and serialization metrics in local developer workflows so regressions show up before they reach UI review.
- Keep the internal audit collector enabled only for local measurement runs. It is structured and low-risk, but it still adds measurable overhead when active.
