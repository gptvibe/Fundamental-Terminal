from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_market_context = route_handler("company_market_context")
global_market_context = route_handler("global_market_context")
company_sector_context = route_handler("company_sector_context")
company_brief = route_handler("company_brief")
company_overview = route_handler("company_overview")
company_peers = route_handler("company_peers")


__all__ = ["company_brief", "company_market_context", "company_overview", "company_peers", "company_sector_context", "global_market_context"]
