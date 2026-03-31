from __future__ import annotations

from app.api.handlers._dispatch import route_handler


watchlist_summary = route_handler("watchlist_summary")


__all__ = ["watchlist_summary"]