from __future__ import annotations

from app.api.handlers._dispatch import route_handler


source_registry = route_handler("source_registry")


__all__ = ["source_registry"]