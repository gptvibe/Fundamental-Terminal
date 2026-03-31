from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import screener as handlers
from app.api.schemas.screener import OfficialScreenerMetadataResponse, OfficialScreenerSearchResponse
from app.api.source_contracts import add_user_visible_route


def build_router() -> APIRouter:
    router = APIRouter(tags=["screener"])
    add_user_visible_route(
        router,
        "/api/screener/filters",
        handlers.official_screener_filters,
        methods=["GET"],
        response_model=OfficialScreenerMetadataResponse,
    )
    add_user_visible_route(
        router,
        "/api/screener/search",
        handlers.official_screener_search,
        methods=["POST"],
        response_model=OfficialScreenerSearchResponse,
    )
    return router


__all__ = ["build_router"]