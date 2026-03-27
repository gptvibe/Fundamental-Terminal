from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.market_context import CompanyMarketContextResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["market-context"])
    router.add_api_route(
        "/api/companies/{ticker}/market-context",
        main_module.company_market_context,
        methods=["GET"],
        response_model=CompanyMarketContextResponse,
    )
    router.add_api_route(
        "/api/market-context",
        main_module.global_market_context,
        methods=["GET"],
        response_model=CompanyMarketContextResponse,
    )
    return router
