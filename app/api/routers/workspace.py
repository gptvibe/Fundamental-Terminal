from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.workspace import (
    CompanyEarningsResponse,
    CompanyEarningsSummaryResponse,
    CompanyEarningsWorkspaceResponse,
    WatchlistSummaryResponse,
)


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["workspace"])
    router.add_api_route(
        "/api/companies/{ticker}/earnings",
        main_module.company_earnings,
        methods=["GET"],
        response_model=CompanyEarningsResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/earnings/summary",
        main_module.company_earnings_summary,
        methods=["GET"],
        response_model=CompanyEarningsSummaryResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/earnings/workspace",
        main_module.company_earnings_workspace,
        methods=["GET"],
        response_model=CompanyEarningsWorkspaceResponse,
    )
    router.add_api_route(
        "/api/watchlist/summary",
        main_module.watchlist_summary,
        methods=["POST"],
        response_model=WatchlistSummaryResponse,
    )
    return router
