from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.governance import (
    CompanyExecutiveCompensationResponse,
    CompanyGovernanceResponse,
    CompanyGovernanceSummaryResponse,
)


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["governance"])
    router.add_api_route(
        "/api/companies/{ticker}/governance",
        main_module.company_governance,
        methods=["GET"],
        response_model=CompanyGovernanceResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/governance/summary",
        main_module.company_governance_summary,
        methods=["GET"],
        response_model=CompanyGovernanceSummaryResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/executive-compensation",
        main_module.company_executive_compensation,
        methods=["GET"],
        response_model=CompanyExecutiveCompensationResponse,
    )
    return router
