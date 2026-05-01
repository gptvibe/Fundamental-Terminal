from __future__ import annotations

from fastapi import FastAPI, Request, status
from starlette.responses import JSONResponse

from app.services.auth import authenticate_request, is_auth_required_for_path


def register_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path

        if is_auth_required_for_path(path):
            auth_context = authenticate_request(request)
            request.state.auth_context = auth_context
            if not auth_context.authenticated:
                response = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "detail": "Authentication required",
                        "reason": auth_context.reason,
                        "mode": auth_context.mode,
                    },
                )
                response.headers["WWW-Authenticate"] = "Bearer"
                return response

        return await call_next(request)


__all__ = ["register_auth_middleware"]
