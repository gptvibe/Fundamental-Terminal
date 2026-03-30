from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.source_contracts import add_user_visible_route
from app.api.schemas.ownership import (
    CompanyBeneficialOwnershipResponse,
    CompanyBeneficialOwnershipSummaryResponse,
    CompanyForm144Response,
    CompanyInsiderTradesResponse,
    CompanyInstitutionalHoldingsResponse,
    CompanyInstitutionalHoldingsSummaryResponse,
    InsiderAnalyticsResponse,
    OwnershipAnalyticsResponse,
)


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["ownership"])
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/insider-trades",
        main_module.company_insider_trades,
        methods=["GET"],
        response_model=CompanyInsiderTradesResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/institutional-holdings",
        main_module.company_institutional_holdings,
        methods=["GET"],
        response_model=CompanyInstitutionalHoldingsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/institutional-holdings/summary",
        main_module.company_institutional_holdings_summary,
        methods=["GET"],
        response_model=CompanyInstitutionalHoldingsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/form-144-filings",
        main_module.company_form144_filings,
        methods=["GET"],
        response_model=CompanyForm144Response,
    )
    add_user_visible_route(
        router,
        "/api/insiders/{ticker}",
        main_module.insider_analytics,
        methods=["GET"],
        response_model=InsiderAnalyticsResponse,
    )
    add_user_visible_route(
        router,
        "/api/ownership/{ticker}",
        main_module.ownership_analytics,
        methods=["GET"],
        response_model=OwnershipAnalyticsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/beneficial-ownership",
        main_module.company_beneficial_ownership,
        methods=["GET"],
        response_model=CompanyBeneficialOwnershipResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/beneficial-ownership/summary",
        main_module.company_beneficial_ownership_summary,
        methods=["GET"],
        response_model=CompanyBeneficialOwnershipSummaryResponse,
    )
    return router
