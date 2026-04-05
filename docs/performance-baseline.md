# Performance Baseline

Generated: 2026-04-05T10:52:54.829Z

## Run Command

```bash
npm --prefix frontend run audit:performance -- --ticker AAPL
```

Prerequisites:
- Start the backend with `PERFORMANCE_AUDIT_ENABLED=true`.
- Start the frontend with `NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=true`.
- Keep the services on the default local ports or pass `--frontend-url` / `--backend-url`.

## Top 10 Slowest Routes

| Route | Kind | Warm p50 (ms) | Warm p95 (ms) | Avg SQL Count | Avg SQL (ms) | Avg Serialize (ms) | Avg Payload (KB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| /api/companies/{ticker}/governance/summary | read | 8264.55 | 95112.67 | 4 | 52.42 | 0.1 | 7.36 |
| /api/companies/{ticker}/changes-since-last-filing | read | 530.62 | 94277.77 | 2.88 | 279.34 | 0.09 | 8.79 |
| /api/companies/{ticker}/activity-overview | read | 963.22 | 1232.34 | 12 | 370.64 | 0.28 | 65.22 |
| /api/watchlist/summary | refresh | 700.21 | 727.22 | 29 | 139.15 | 0.04 | 1.63 |
| /api/companies/{ticker}/insider-trades | read | 177.09 | 524.13 | 3 | 136.38 | 0.53 | 108.89 |
| /api/companies/{ticker}/earnings/summary | read | 18.83 | 340.4 | 3 | 60.75 | 0.03 | 1.42 |
| /api/companies/{ticker}/financials | read | 249.78 | 333.16 | 0 | 0 | 7.97 | 1010.85 |
| /api/companies/{ticker}/institutional-holdings | read | 172.11 | 308.46 | 4 | 89.07 | 0.08 | 9.25 |
| /api/companies/{ticker}/capital-markets/summary | read | 12.71 | 297.89 | 2 | 48.84 | 0.03 | 1.15 |
| /api/companies/search | read | 0.91 | 158.47 | 0 | 0 | 0.02 | 0.81 |

## Top 10 Most Over-Fetched Page Flows

| Flow | Phase | Requests | Network | Cache Hits | Backend SQL Queries | Serialize (ms) | Payload (KB) | Page Elapsed (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| /company/[ticker] | warm | 52 | 21 | 31 | 90 | 35.78 | 3916.53 | 9738.7 |
| /company/[ticker] | cold | 46 | 15 | 31 | 100 | 43.56 | 1658.41 | 18798.1 |
| Models | warm | 19 | 9 | 10 | 38 | 12.16 | 1467.65 | 264.1 |
| Models | cold | 18 | 8 | 10 | 47 | 12.1 | 1483.57 | 1569.6 |
| Financials | cold | 9 | 4 | 5 | 41 | 11.39 | 1141.79 | 507.7 |
| Financials | warm | 9 | 4 | 5 | 36 | 9.98 | 1141.79 | 851.9 |
| Homepage search | cold | 5 | 3 | 2 | 33 | 0.17 | 21.2 | 1145.1 |
| Homepage search | warm | 5 | 3 | 2 | 31 | 0.26 | 21.22 | 1192.8 |
| Watchlist | warm | 2 | 2 | 0 | 68 | 0.74 | 63.49 | 5118.9 |
| Watchlist | cold | 2 | 2 | 0 | 66 | 0.43 | 43.31 | 2554.1 |

## Duplicate Request Sources

| Flow | Phase | Source | Route | Count |
| --- | --- | --- | --- | ---: |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/changes-since-last-filing | 6 |
| /company/[ticker] | warm | company-overview:research-brief | /companies/AAPL/changes-since-last-filing | 6 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/metrics/summary?period_type=ttm | 3 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/financial-restatements | 3 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/activity-overview | 3 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/earnings/summary | 3 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/capital-structure?max_periods=6 | 3 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/capital-markets/summary | 3 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/governance/summary | 3 |
| /company/[ticker] | cold | company-overview:research-brief | /companies/AAPL/beneficial-ownership/summary | 3 |

## Cold vs Warm Timings

| Flow | Cold (ms) | Warm (ms) | Cold Requests | Warm Requests | Warm Cache Hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Homepage search | 1145.1 | 1192.8 | 5 | 5 | 2 |
| /company/[ticker] | 18798.1 | 9738.7 | 46 | 52 | 31 |
| Models | 1569.6 | 264.1 | 18 | 19 | 10 |
| Financials | 507.7 | 851.9 | 9 | 9 | 5 |
| Watchlist | 2554.1 | 5118.9 | 2 | 2 | 0 |

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

