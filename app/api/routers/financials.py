from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas.financials import (
    CompanyDerivedMetricsResponse,
    CompanyDerivedMetricsSummaryResponse,
    CompanyFactsResponse,
    CompanyFilingInsightsResponse,
    CompanyFinancialsResponse,
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
        "/api/companies/{ticker}/filing-insights",
        main_module.company_filing_insights,
        methods=["GET"],
        response_model=CompanyFilingInsightsResponse,
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
    return router
