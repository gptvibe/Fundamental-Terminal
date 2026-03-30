from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.source_contracts import add_user_visible_route
from app.api.schemas.workspace import (
    CompanyEarningsResponse,
    CompanyEarningsSummaryResponse,
    CompanyEarningsWorkspaceResponse,
    WatchlistSummaryResponse,
)


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["workspace"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/earnings",
        main_module.company_earnings,
        methods=["GET"],
        response_model=CompanyEarningsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/earnings/summary",
        main_module.company_earnings_summary,
        methods=["GET"],
        response_model=CompanyEarningsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/earnings/workspace",
        main_module.company_earnings_workspace,
        methods=["GET"],
        response_model=CompanyEarningsWorkspaceResponse,
    )
    add_user_visible_route(
        router,
        "/api/watchlist/summary",
        main_module.watchlist_summary,
        methods=["POST"],
        response_model=WatchlistSummaryResponse,
    )
    return router
