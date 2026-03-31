from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import market_context as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.company_overview import CompanyPeersResponse


def build_router() -> APIRouter:
    router = APIRouter(tags=["company-overview"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/peers",
        handlers.company_peers,
        methods=["GET"],
        response_model=CompanyPeersResponse,
    )
    return router
