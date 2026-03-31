from __future__ import annotations

from app.api.handlers._dispatch import route_handler


official_screener_filters = route_handler("official_screener_filters")
official_screener_search = route_handler("official_screener_search")


__all__ = ["official_screener_filters", "official_screener_search"]