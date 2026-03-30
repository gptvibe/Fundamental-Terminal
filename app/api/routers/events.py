from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.source_contracts import add_user_visible_route
from app.api.schemas.events import (
    CompanyActivityFeedResponse,
    CompanyActivityOverviewResponse,
    CompanyAlertsResponse,
    CompanyCapitalMarketsSummaryResponse,
    CompanyCapitalRaisesResponse,
    CompanyEventsResponse,
    CompanyFilingEventsSummaryResponse,
)


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["events"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/capital-raises",
        main_module.company_capital_raises,
        methods=["GET"],
        response_model=CompanyCapitalRaisesResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/capital-markets",
        main_module.company_capital_markets,
        methods=["GET"],
        response_model=CompanyCapitalRaisesResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/capital-markets/summary",
        main_module.company_capital_markets_summary,
        methods=["GET"],
        response_model=CompanyCapitalMarketsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/events",
        main_module.company_events,
        methods=["GET"],
        response_model=CompanyEventsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filing-events",
        main_module.company_filing_events,
        methods=["GET"],
        response_model=CompanyEventsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filing-events/summary",
        main_module.company_filing_events_summary,
        methods=["GET"],
        response_model=CompanyFilingEventsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/activity-feed",
        main_module.company_activity_feed,
        methods=["GET"],
        response_model=CompanyActivityFeedResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/alerts",
        main_module.company_alerts,
        methods=["GET"],
        response_model=CompanyAlertsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/activity-overview",
        main_module.company_activity_overview,
        methods=["GET"],
        response_model=CompanyActivityOverviewResponse,
    )
    return router
