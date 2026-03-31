from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers import governance as handlers
from app.api.source_contracts import add_user_visible_route
from app.api.schemas.governance import (
    CompanyExecutiveCompensationResponse,
    CompanyGovernanceResponse,
    CompanyGovernanceSummaryResponse,
)


def build_router() -> APIRouter:
    router = APIRouter(tags=["governance"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/governance",
        handlers.company_governance,
        methods=["GET"],
        response_model=CompanyGovernanceResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/governance/summary",
        handlers.company_governance_summary,
        methods=["GET"],
        response_model=CompanyGovernanceSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/executive-compensation",
        handlers.company_executive_compensation,
        methods=["GET"],
        response_model=CompanyExecutiveCompensationResponse,
    )
    return router
