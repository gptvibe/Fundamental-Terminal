from __future__ import annotations

from fastapi.routing import APIRoute

from app.main import app


def test_public_route_inventory_remains_stable() -> None:
    expected_routes = {
        ("GET", "/health"),
        ("GET", "/api/internal/cache-metrics"),
        ("GET", "/api/jobs/{job_id}/events"),
        ("GET", "/api/companies/search"),
        ("GET", "/api/companies/resolve"),
        ("GET", "/api/screener/filters"),
        ("POST", "/api/screener/search"),
        ("GET", "/api/companies/compare"),
        ("GET", "/api/companies/{ticker}/financials"),
        ("GET", "/api/companies/{ticker}/segment-history"),
        ("GET", "/api/companies/{ticker}/capital-structure"),
        ("GET", "/api/companies/{ticker}/oil-scenario"),
        ("GET", "/api/companies/{ticker}/oil-scenario-overlay"),
        ("GET", "/api/companies/{ticker}/filing-insights"),
        ("GET", "/api/companies/{ticker}/changes-since-last-filing"),
        ("GET", "/api/companies/{ticker}/metrics-timeseries"),
        ("GET", "/api/companies/{ticker}/metrics"),
        ("GET", "/api/companies/{ticker}/metrics/summary"),
        ("GET", "/api/companies/{ticker}/insider-trades"),
        ("GET", "/api/companies/{ticker}/institutional-holdings"),
        ("GET", "/api/companies/{ticker}/institutional-holdings/summary"),
        ("GET", "/api/companies/{ticker}/form-144-filings"),
        ("GET", "/api/companies/{ticker}/earnings"),
        ("GET", "/api/companies/{ticker}/earnings/summary"),
        ("GET", "/api/companies/{ticker}/earnings/workspace"),
        ("GET", "/api/insiders/{ticker}"),
        ("GET", "/api/ownership/{ticker}"),
        ("POST", "/api/companies/{ticker}/refresh"),
        ("GET", "/api/companies/{ticker}/models"),
        ("GET", "/api/model-evaluations/latest"),
        ("GET", "/api/companies/{ticker}/market-context"),
        ("GET", "/api/companies/{ticker}/sector-context"),
        ("GET", "/api/market-context"),
        ("GET", "/api/source-registry"),
        ("GET", "/api/companies/{ticker}/peers"),
        ("GET", "/api/companies/{ticker}/filings"),
        ("GET", "/api/companies/{ticker}/beneficial-ownership"),
        ("GET", "/api/companies/{ticker}/beneficial-ownership/summary"),
        ("GET", "/api/companies/{ticker}/governance"),
        ("GET", "/api/companies/{ticker}/governance/summary"),
        ("GET", "/api/companies/{ticker}/executive-compensation"),
        ("GET", "/api/companies/{ticker}/capital-raises"),
        ("GET", "/api/companies/{ticker}/capital-markets"),
        ("GET", "/api/companies/{ticker}/capital-markets/summary"),
        ("GET", "/api/companies/{ticker}/events"),
        ("GET", "/api/companies/{ticker}/filing-events"),
        ("GET", "/api/companies/{ticker}/filing-events/summary"),
        ("GET", "/api/companies/{ticker}/comment-letters"),
        ("GET", "/api/companies/{ticker}/activity-feed"),
        ("GET", "/api/companies/{ticker}/alerts"),
        ("GET", "/api/companies/{ticker}/activity-overview"),
        ("POST", "/api/watchlist/summary"),
        ("GET", "/api/watchlist/calendar"),
        ("GET", "/api/filings/{ticker}"),
        ("GET", "/api/search_filings"),
        ("GET", "/api/companies/{ticker}/financial-history"),
        ("GET", "/api/companies/{ticker}/financial-restatements"),
        ("GET", "/api/companies/{ticker}/filings/view"),
    }

    actual_routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not (route.path == "/health" or route.path.startswith("/api/")):
            continue
        for method in route.methods:
            if method in {"GET", "POST"}:
                actual_routes.append((method, route.path))

    assert len(actual_routes) == len(set(actual_routes))
    assert set(actual_routes) == expected_routes
