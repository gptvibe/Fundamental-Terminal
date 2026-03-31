from __future__ import annotations

from app.api.handlers._dispatch import route_handler


search_companies = route_handler("search_companies")
resolve_company_identifier = route_handler("resolve_company_identifier")


__all__ = ["resolve_company_identifier", "search_companies"]