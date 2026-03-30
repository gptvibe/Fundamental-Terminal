from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.source_contracts import add_user_visible_route
from app.api.schemas.company_overview import CompanyPeersResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["company-overview"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/peers",
        main_module.company_peers,
        methods=["GET"],
        response_model=CompanyPeersResponse,
    )
    return router
