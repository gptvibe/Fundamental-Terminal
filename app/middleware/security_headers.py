from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import settings


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def security_headers_for_request(request: Request) -> dict[str, str]:
    headers = dict(_SECURITY_HEADERS)
    if request.url.path.startswith("/api/") or request.url.path in {"/health", "/readyz"}:
        headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    if request.headers.get("x-forwarded-proto", request.url.scheme).lower() == "https":
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if not bool(getattr(settings, "security_headers_enabled", True)):
            return response
        for key, value in security_headers_for_request(request).items():
            response.headers.setdefault(key, value)
        return response


__all__ = ["SecurityHeadersMiddleware", "security_headers_for_request"]
