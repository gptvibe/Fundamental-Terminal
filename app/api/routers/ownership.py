from __future__ import annotations

from typing import Any

from fastapi import APIRouter

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
    router.add_api_route(
        "/api/companies/{ticker}/insider-trades",
        main_module.company_insider_trades,
        methods=["GET"],
        response_model=CompanyInsiderTradesResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/institutional-holdings",
        main_module.company_institutional_holdings,
        methods=["GET"],
        response_model=CompanyInstitutionalHoldingsResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/institutional-holdings/summary",
        main_module.company_institutional_holdings_summary,
        methods=["GET"],
        response_model=CompanyInstitutionalHoldingsSummaryResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/form-144-filings",
        main_module.company_form144_filings,
        methods=["GET"],
        response_model=CompanyForm144Response,
    )
    router.add_api_route(
        "/api/insiders/{ticker}",
        main_module.insider_analytics,
        methods=["GET"],
        response_model=InsiderAnalyticsResponse,
    )
    router.add_api_route(
        "/api/ownership/{ticker}",
        main_module.ownership_analytics,
        methods=["GET"],
        response_model=OwnershipAnalyticsResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/beneficial-ownership",
        main_module.company_beneficial_ownership,
        methods=["GET"],
        response_model=CompanyBeneficialOwnershipResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/beneficial-ownership/summary",
        main_module.company_beneficial_ownership_summary,
        methods=["GET"],
        response_model=CompanyBeneficialOwnershipSummaryResponse,
    )
    return router
