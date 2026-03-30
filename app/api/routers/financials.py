from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.source_contracts import add_user_visible_route
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
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/financials",
        main_module.company_financials,
        methods=["GET"],
        response_model=CompanyFinancialsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/capital-structure",
        main_module.company_capital_structure,
        methods=["GET"],
        response_model=CompanyCapitalStructureResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/filing-insights",
        main_module.company_filing_insights,
        methods=["GET"],
        response_model=CompanyFilingInsightsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/changes-since-last-filing",
        main_module.company_changes_since_last_filing,
        methods=["GET"],
        response_model=CompanyChangesSinceLastFilingResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/metrics-timeseries",
        main_module.company_metrics_timeseries,
        methods=["GET"],
        response_model=CompanyMetricsTimeseriesResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/metrics",
        main_module.company_derived_metrics,
        methods=["GET"],
        response_model=CompanyDerivedMetricsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/metrics/summary",
        main_module.company_derived_metrics_summary,
        methods=["GET"],
        response_model=CompanyDerivedMetricsSummaryResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/financial-history",
        main_module.company_financial_history,
        methods=["GET"],
        response_model=CompanyFactsResponse,
    )
    add_user_visible_route(
        router,
        "/api/companies/{ticker}/financial-restatements",
        main_module.company_financial_restatements,
        methods=["GET"],
        response_model=CompanyFinancialRestatementsResponse,
    )
    return router
