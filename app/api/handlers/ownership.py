from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_insider_trades = route_handler("company_insider_trades")
company_institutional_holdings = route_handler("company_institutional_holdings")
company_institutional_holdings_summary = route_handler("company_institutional_holdings_summary")
company_form144_filings = route_handler("company_form144_filings")
insider_analytics = route_handler("insider_analytics")
ownership_analytics = route_handler("ownership_analytics")
company_beneficial_ownership = route_handler("company_beneficial_ownership")
company_beneficial_ownership_summary = route_handler("company_beneficial_ownership_summary")


__all__ = [
    "company_beneficial_ownership",
    "company_beneficial_ownership_summary",
    "company_form144_filings",
    "company_insider_trades",
    "company_institutional_holdings",
    "company_institutional_holdings_summary",
    "insider_analytics",
    "ownership_analytics",
]