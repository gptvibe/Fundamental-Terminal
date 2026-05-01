from __future__ import annotations

from fastapi import FastAPI, Request

from app.observability import observability_enabled
from app.performance_audit import (
    begin_request,
    complete_request,
    end_request,
    is_enabled,
    should_skip_path,
)


def register_performance_audit_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def performance_audit_middleware(request: Request, call_next):
        if not (is_enabled() or observability_enabled()) or should_skip_path(request.url.path):
            return await call_next(request)

        metrics, token = begin_request(request)
        response = None
        try:
            response = await call_next(request)
            body = getattr(response, "body", None)
            if metrics.response_bytes is None and isinstance(body, (bytes, bytearray)):
                metrics.response_bytes = len(body)
            complete_request(request, metrics, status_code=response.status_code)
            return response
        except Exception as exc:
            complete_request(
                request,
                metrics,
                status_code=getattr(response, "status_code", 500),
                error_type=type(exc).__name__,
            )
            raise
        finally:
            end_request(token)


__all__ = ["register_performance_audit_middleware"]
