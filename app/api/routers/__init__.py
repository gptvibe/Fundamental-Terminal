from __future__ import annotations

from fastapi import FastAPI

from app.api.source_contracts import ensure_user_visible_routes_have_source_contracts
from app.api.routers.company_overview import build_router as build_company_overview_router
from app.api.routers.events import build_router as build_events_router
from app.api.routers.filings import build_router as build_filings_router
from app.api.routers.financials import build_router as build_financials_router
from app.api.routers.governance import build_router as build_governance_router
from app.api.routers.jobs import build_router as build_jobs_router
from app.api.routers.market_context import build_router as build_market_context_router
from app.api.routers.models import build_router as build_models_router
from app.api.routers.ownership import build_router as build_ownership_router
from app.api.routers.screener import build_router as build_screener_router
from app.api.routers.search import build_router as build_search_router
from app.api.routers.sector_context import build_router as build_sector_context_router
from app.api.routers.workspace import build_router as build_workspace_router


ROUTER_BUILDERS = (
    build_jobs_router,
    build_search_router,
    build_screener_router,
    build_company_overview_router,
    build_financials_router,
    build_filings_router,
    build_ownership_router,
    build_governance_router,
    build_events_router,
    build_models_router,
    build_market_context_router,
    build_sector_context_router,
    build_workspace_router,
)


def register_routers(app: FastAPI) -> None:
    for builder in ROUTER_BUILDERS:
        app.include_router(builder())
    ensure_user_visible_routes_have_source_contracts(app)


__all__ = ["register_routers"]
