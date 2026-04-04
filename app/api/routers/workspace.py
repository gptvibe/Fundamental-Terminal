from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import earnings as earnings_handlers
from app.api.handlers import workspace as workspace_handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.workspace import (
    CompanyEarningsResponse,
    CompanyEarningsSummaryResponse,
    CompanyEarningsWorkspaceResponse,
    WatchlistCalendarResponse,
    WatchlistSummaryResponse,
)


def build_router() -> APIRouter:
    router = APIRouter(tags=["workspace"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/earnings",
        earnings_handlers.company_earnings,
        methods=["GET"],
        response_model=CompanyEarningsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/earnings/summary",
        earnings_handlers.company_earnings_summary,
        methods=["GET"],
        response_model=CompanyEarningsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/earnings/workspace",
        earnings_handlers.company_earnings_workspace,
        methods=["GET"],
        response_model=CompanyEarningsWorkspaceResponse,
    )
    add_user_visible_route(
        router,
        "/api/watchlist/summary",
        workspace_handlers.watchlist_summary,
        methods=["POST"],
        response_model=WatchlistSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/watchlist/calendar",
        workspace_handlers.watchlist_calendar,
        methods=["GET"],
        response_model=WatchlistCalendarResponse,
    )
    return router
