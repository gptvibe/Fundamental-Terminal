from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import search as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.search import CompanyResolutionResponse, CompanySearchResponse


def build_router() -> APIRouter:
    router = APIRouter(tags=["search"])
    add_user_visible_route(
        router,
        "/api/companies/search",
        handlers.search_companies,
        methods=["GET"],
        response_model=CompanySearchResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/resolve",
        handlers.resolve_company_identifier,
        methods=["GET"],
        response_model=CompanyResolutionResponse,
    )
    return router
