from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_compare = route_handler("company_compare")
company_charts = route_handler("company_charts")
company_charts_what_if = route_handler("company_charts_what_if")
company_charts_forecast_accuracy = route_handler("company_charts_forecast_accuracy")
company_equity_claim_risk = route_handler("company_equity_claim_risk")
company_financials = route_handler("company_financials")
company_segment_history = route_handler("company_segment_history")
company_capital_structure = route_handler("company_capital_structure")
company_filing_insights = route_handler("company_filing_insights")
company_changes_since_last_filing = route_handler("company_changes_since_last_filing")
company_metrics_timeseries = route_handler("company_metrics_timeseries")
company_derived_metrics = route_handler("company_derived_metrics")
company_derived_metrics_summary = route_handler("company_derived_metrics_summary")
company_financial_restatements = route_handler("company_financial_restatements")
company_financial_history = route_handler("company_financial_history")


__all__ = [
    "company_capital_structure",
    "company_charts",
    "company_charts_forecast_accuracy",
    "company_charts_what_if",
    "company_changes_since_last_filing",
    "company_compare",
    "company_derived_metrics",
    "company_derived_metrics_summary",
    "company_equity_claim_risk",
    "company_filing_insights",
    "company_financial_history",
    "company_financial_restatements",
    "company_financials",
    "company_metrics_timeseries",
    "company_segment_history",
]
