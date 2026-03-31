from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import HTMLResponse

from app.api.handlers import filings as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.filings import CompanyFilingsResponse, FilingSearchResultPayload, FilingTimelineItemPayload


def build_router() -> APIRouter:
    router = APIRouter(tags=["filings"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filings",
        handlers.company_filings,
        methods=["GET"],
        response_model=CompanyFilingsResponse,
    )
    add_user_visible_route(
        router,
        "/api/filings/{ticker}",
        handlers.filings_timeline,
        methods=["GET"],
        response_model=list[FilingTimelineItemPayload],
    )
    add_user_visible_route(
        router,
        "/api/search_filings",
        handlers.search_filings,
        methods=["GET"],
        response_model=list[FilingSearchResultPayload],
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filings/view",
        handlers.company_filing_view,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    return router
