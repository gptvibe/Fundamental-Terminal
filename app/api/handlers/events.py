from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_capital_raises = route_handler("company_capital_raises")
company_capital_markets = route_handler("company_capital_markets")
company_capital_markets_summary = route_handler("company_capital_markets_summary")
company_events = route_handler("company_events")
company_filing_events = route_handler("company_filing_events")
company_filing_events_summary = route_handler("company_filing_events_summary")
company_comment_letters = route_handler("company_comment_letters")
company_activity_feed = route_handler("company_activity_feed")
company_alerts = route_handler("company_alerts")
company_activity_overview = route_handler("company_activity_overview")


__all__ = [
    "company_activity_feed",
    "company_activity_overview",
    "company_alerts",
    "company_capital_markets",
    "company_capital_markets_summary",
    "company_comment_letters",
    "company_capital_raises",
    "company_events",
    "company_filing_events",
    "company_filing_events_summary",
]