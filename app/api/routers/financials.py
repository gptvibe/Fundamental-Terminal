from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.financials import (
    CompanyCapitalStructureResponse,
    CompanyChangesSinceLastFilingResponse,
    CompanyDerivedMetricsResponse,
    CompanyDerivedMetricsSummaryResponse,
    CompanyFactsResponse,
    CompanyFilingInsightsResponse,
    CompanyFinancialsResponse,
    CompanyFinancialRestatementsResponse,
    CompanyMetricsTimeseriesResponse,
)


def build_router(main_module: Any) -> APIRouter:
    router = APIRouter(tags=["financials"])
    router.add_api_route(
        "/api/companies/{ticker}/financials",
        main_module.company_financials,
        methods=["GET"],
        response_model=CompanyFinancialsResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/capital-structure",
        main_module.company_capital_structure,
        methods=["GET"],
        response_model=CompanyCapitalStructureResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/filing-insights",
        main_module.company_filing_insights,
        methods=["GET"],
        response_model=CompanyFilingInsightsResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/changes-since-last-filing",
        main_module.company_changes_since_last_filing,
        methods=["GET"],
        response_model=CompanyChangesSinceLastFilingResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/metrics-timeseries",
        main_module.company_metrics_timeseries,
        methods=["GET"],
        response_model=CompanyMetricsTimeseriesResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/metrics",
        main_module.company_derived_metrics,
        methods=["GET"],
        response_model=CompanyDerivedMetricsResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/metrics/summary",
        main_module.company_derived_metrics_summary,
        methods=["GET"],
        response_model=CompanyDerivedMetricsSummaryResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/financial-history",
        main_module.company_financial_history,
        methods=["GET"],
        response_model=CompanyFactsResponse,
    )
    router.add_api_route(
        "/api/companies/{ticker}/financial-restatements",
        main_module.company_financial_restatements,
        methods=["GET"],
        response_model=CompanyFinancialRestatementsResponse,
    )
    return router
