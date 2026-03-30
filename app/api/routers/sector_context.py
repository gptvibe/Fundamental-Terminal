from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.source_contracts import add_user_visible_route
from app.api.schemas.sector_context import CompanySectorContextResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["sector-context"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/sector-context",
        main_module.company_sector_context,
        methods=["GET"],
        response_model=CompanySectorContextResponse,
    )
    return router