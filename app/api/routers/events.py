from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import events as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.events import (
    CompanyActivityFeedResponse,
    CompanyActivityOverviewResponse,
    CompanyAlertsResponse,
    CompanyCommentLettersResponse,
    CompanyCapitalMarketsSummaryResponse,
    CompanyCapitalRaisesResponse,
    CompanyEventsResponse,
    CompanyFilingEventsSummaryResponse,
)


def build_router() -> APIRouter:
    router = APIRouter(tags=["events"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/capital-raises",
        handlers.company_capital_raises,
        methods=["GET"],
        response_model=CompanyCapitalRaisesResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/capital-markets",
        handlers.company_capital_markets,
        methods=["GET"],
        response_model=CompanyCapitalRaisesResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/capital-markets/summary",
        handlers.company_capital_markets_summary,
        methods=["GET"],
        response_model=CompanyCapitalMarketsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/events",
        handlers.company_events,
        methods=["GET"],
        response_model=CompanyEventsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filing-events",
        handlers.company_filing_events,
        methods=["GET"],
        response_model=CompanyEventsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filing-events/summary",
        handlers.company_filing_events_summary,
        methods=["GET"],
        response_model=CompanyFilingEventsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/comment-letters",
        handlers.company_comment_letters,
        methods=["GET"],
        response_model=CompanyCommentLettersResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/activity-feed",
        handlers.company_activity_feed,
        methods=["GET"],
        response_model=CompanyActivityFeedResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/alerts",
        handlers.company_alerts,
        methods=["GET"],
        response_model=CompanyAlertsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/activity-overview",
        handlers.company_activity_overview,
        methods=["GET"],
        response_model=CompanyActivityOverviewResponse,
    )
    return router
