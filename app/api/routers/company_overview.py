from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.company_overview import CompanyPeersResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["company-overview"])
    router.add_api_route(
        "/api/companies/{ticker}/peers",
        main_module.company_peers,
        methods=["GET"],
        response_model=CompanyPeersResponse,
    )
    return router
