from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_governance = route_handler("company_governance")
company_governance_summary = route_handler("company_governance_summary")
company_executive_compensation = route_handler("company_executive_compensation")


__all__ = ["company_executive_compensation", "company_governance", "company_governance_summary"]