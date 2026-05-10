"""Lightweight always-on route timing middleware.

Records per-request timing into the in-process ring buffer for every
API request, regardless of feature flags.  The handler is intentionally
minimal: one perf_counter pair, one store write, no external calls.

Registered via :func:`register_route_timing_middleware`.
"""
from __future__ import annotations

from time import perf_counter

from fastapi import FastAPI, Request

import app.services.route_timing as _store

_SKIP_PREFIXES = (
    "/health",
    "/readyz",
    "/api/admin/performance",
    "/api/internal/performance-audit",
    "/api/internal/observability",
    "/api/internal/cache-metrics",
)


def register_route_timing_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _route_timing_middleware(request: Request, call_next):
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
            return await call_next(request)

        started_at = perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (perf_counter() - started_at) * 1000.0

            # Route path is resolved during call_next; scope is mutated in-place.
            route = request.scope.get("route")
            route_path = getattr(route, "path", None) or path

            status_code = getattr(response, "status_code", 0) if response is not None else 0

            # Detect cache hit from response header when present.
            cache_hit: bool | None = None
            if response is not None:
                raw_header = (
                    response.headers.get("X-Cache-Status")
                    or response.headers.get("x-cache-status")
                )
                if raw_header:
                    cache_hit = raw_header.lower().strip() in {"hit", "true", "1", "yes"}

            # Pull upstream call count from the observability context if live.
            upstream_count = 0
            try:
                from app.observability import current_request_observation

                obs = current_request_observation()
                if obs is not None:
                    upstream_count = obs.upstream_request_count
            except Exception:
                pass

            _store.record(
                route=route_path,
                method=request.method.upper(),
                status_code=status_code,
                duration_ms=duration_ms,
                cache_hit=cache_hit,
                upstream_count=upstream_count,
            )


__all__ = ["register_route_timing_middleware"]
