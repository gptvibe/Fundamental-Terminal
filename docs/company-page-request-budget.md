# Company Page Request Budget

Updated: 2026-04-06

## Budget

The `/company/[ticker]` overview page should stay within the following client request budget during the initial page load:

- Cold load: at most 10 backend API requests
- Warm load: at most 8 backend API requests

For the repo's audit tooling, the same flow is also budgeted in `frontend/scripts/run-performance-audit.mjs` as:

- Cold load: `maxRequests = 24`, `maxNetworkRequests = 10`
- Warm load: `maxRequests = 24`, `maxNetworkRequests = 8`

The higher `maxRequests` value in the audit script accounts for cache-hit bookkeeping inside the client audit collector, while the API-request budget above stays focused on backend pressure.

## Live Observation

Using the compose-built stack and a Playwright request capture against `http://127.0.0.1:3000/company/AAPL`, the overview page issued 9 backend API requests on the initial load:

- `/companies/AAPL/brief`
- `/companies/AAPL/financials`
- `/companies/AAPL/institutional-holdings`
- `/companies/AAPL/insider-trades`
- `/companies/AAPL/changes-since-last-filing`
- `/companies/AAPL/metrics/summary?period_type=ttm`
- `/companies/AAPL/financial-restatements`
- `/companies/AAPL/segment-history?kind=business&years=4`
- `/companies/search?query=AAPL&refresh=false`

That observation is within the cold-load budget.
