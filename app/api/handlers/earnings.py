from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_earnings = route_handler("company_earnings")
company_earnings_summary = route_handler("company_earnings_summary")
company_earnings_workspace = route_handler("company_earnings_workspace")


__all__ = ["company_earnings", "company_earnings_summary", "company_earnings_workspace"]