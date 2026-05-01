from __future__ import annotations

from fastapi import FastAPI, Request, status
from starlette.responses import JSONResponse

from app.config import settings
from app.services.rate_limit import public_route_rate_limiter


def is_rate_limited_public_route(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path.startswith("/api/internal/"):
        return False
    exempt_paths = getattr(settings, "api_rate_limit_exempt_paths", []) or []
    for exempt in exempt_paths:
        normalized = exempt.rstrip("/") or "/"
        if path == normalized or path.startswith(f"{normalized}/"):
            return False
    return True


def client_identifier(request: Request) -> str:
    if bool(getattr(settings, "api_rate_limit_trust_proxy", False)):
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            first = forwarded_for.split(",", 1)[0].strip()
            if first:
                return first
    client_host = getattr(request.client, "host", None)
    return str(client_host or "unknown")


def register_rate_limit_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        path = request.url.path
        if not is_rate_limited_public_route(path):
            return await call_next(request)

        decision = await public_route_rate_limiter.evaluate(client_identifier(request))
        if not decision.allowed:
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded",
                    "limit": decision.limit,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
            )
            response.headers["Retry-After"] = str(decision.retry_after_seconds)
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = "0"
            response.headers["X-RateLimit-Reset"] = str(decision.reset_at_epoch)
            return response

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Reset"] = str(decision.reset_at_epoch)
        return response


__all__ = ["client_identifier", "is_rate_limited_public_route", "register_rate_limit_middleware"]
