from __future__ import annotations


def register_routers(*args, **kwargs):
	from app.api.routers import register_routers as _register_routers

	return _register_routers(*args, **kwargs)

__all__ = ["register_routers"]
