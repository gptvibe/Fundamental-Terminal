from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.screener import OfficialScreenerMetadataResponse, OfficialScreenerSearchResponse
from app.api.source_contracts import add_user_visible_route


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["screener"])
    add_user_visible_route(
        router,
        "/api/screener/filters",
        main_module.official_screener_filters,
        methods=["GET"],
        response_model=OfficialScreenerMetadataResponse,
    )
    add_user_visible_route(
        router,
        "/api/screener/search",
        main_module.official_screener_search,
        methods=["POST"],
        response_model=OfficialScreenerSearchResponse,
    )
    return router


__all__ = ["build_router"]