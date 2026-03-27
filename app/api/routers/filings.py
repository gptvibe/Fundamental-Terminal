from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from starlette.responses import HTMLResponse

from app.api.schemas.filings import CompanyFilingsResponse, FilingSearchResultPayload, FilingTimelineItemPayload


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["filings"])
    router.add_api_route(
        "/api/companies/{ticker}/filings",
        main_module.company_filings,
        methods=["GET"],
        response_model=CompanyFilingsResponse,
    )
    router.add_api_route(
        "/api/filings/{ticker}",
        main_module.filings_timeline,
        methods=["GET"],
        response_model=list[FilingTimelineItemPayload],
    )
    router.add_api_route(
        "/api/search_filings",
        main_module.search_filings,
        methods=["GET"],
        response_model=list[FilingSearchResultPayload],
    )
    router.add_api_route(
        "/api/companies/{ticker}/filings/view",
        main_module.company_filing_view,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    return router
