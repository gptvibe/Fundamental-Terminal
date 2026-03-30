from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.source_contracts import add_user_visible_route
from app.api.schemas.search import CompanyResolutionResponse, CompanySearchResponse


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["search"])
    add_user_visible_route(
        router,
        "/api/companies/search",
        main_module.search_companies,
        methods=["GET"],
        response_model=CompanySearchResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/resolve",
        main_module.resolve_company_identifier,
        methods=["GET"],
        response_model=CompanyResolutionResponse,
    )
    return router
