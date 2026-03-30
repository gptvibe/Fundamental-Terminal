from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from starlette.responses import HTMLResponse

from app.api.source_contracts import add_user_visible_route
from app.api.schemas.filings import CompanyFilingsResponse, FilingSearchResultPayload, FilingTimelineItemPayload


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["filings"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filings",
        main_module.company_filings,
        methods=["GET"],
        response_model=CompanyFilingsResponse,
    )
    add_user_visible_route(
        router,
        "/api/filings/{ticker}",
        main_module.filings_timeline,
        methods=["GET"],
        response_model=list[FilingTimelineItemPayload],
    )
    add_user_visible_route(
        router,
        "/api/search_filings",
        main_module.search_filings,
        methods=["GET"],
        response_model=list[FilingSearchResultPayload],
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filings/view",
        main_module.company_filing_view,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    return router
