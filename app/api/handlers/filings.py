from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_filings = route_handler("company_filings")
filings_timeline = route_handler("filings_timeline")
search_filings = route_handler("search_filings")
company_filing_view = route_handler("company_filing_view")


__all__ = ["company_filing_view", "company_filings", "filings_timeline", "search_filings"]