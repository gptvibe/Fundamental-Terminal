from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import market_context as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.sector_context import CompanySectorContextResponse


def build_router() -> APIRouter:
    router = APIRouter(tags=["sector-context"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/sector-context",
        handlers.company_sector_context,
        methods=["GET"],
        response_model=CompanySectorContextResponse,
    )
    return router