from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import market_context as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.market_context import CompanyMarketContextResponse


def build_router() -> APIRouter:
    router = APIRouter(tags=["market-context"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/market-context",
        handlers.company_market_context,
        methods=["GET"],
        response_model=CompanyMarketContextResponse,
    )
    add_user_visible_route(
        router,
        "/api/market-context",
        handlers.global_market_context,
        methods=["GET"],
        response_model=CompanyMarketContextResponse,
    )
    return router
