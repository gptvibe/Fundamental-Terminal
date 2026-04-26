from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from app.config import settings

AuthMode = Literal["off", "bearer", "forwarded-user"]


@dataclass(frozen=True, slots=True)
class AuthContext:
    authenticated: bool
    principal: str | None
    mode: str
    reason: str


def is_auth_required_for_path(path: str) -> bool:
    normalized_path = path.strip() or "/"
    if any(normalized_path == exempt or normalized_path.startswith(f"{exempt.rstrip('/')}/") for exempt in settings.auth_exempt_paths):
        return False
    return any(
        normalized_path == prefix or normalized_path.startswith(f"{prefix.rstrip('/')}/")
        for prefix in settings.auth_required_path_prefixes
    )


def authenticate_request(request: Request) -> AuthContext:
    mode = _normalized_auth_mode(settings.auth_mode)
    if mode == "off":
        return AuthContext(authenticated=True, principal=None, mode=mode, reason="auth_disabled")

    if mode == "bearer":
        configured_token = settings.auth_bearer_token
        if not configured_token:
            return AuthContext(authenticated=False, principal=None, mode=mode, reason="missing_configured_token")
        auth_header = request.headers.get("authorization", "")
        scheme, _, supplied_token = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not supplied_token:
            return AuthContext(authenticated=False, principal=None, mode=mode, reason="missing_bearer_token")
        if not hmac.compare_digest(supplied_token.strip(), configured_token):
            return AuthContext(authenticated=False, principal=None, mode=mode, reason="invalid_bearer_token")
        return AuthContext(authenticated=True, principal="bearer", mode=mode, reason="ok")

    header_name = settings.auth_forwarded_user_header
    principal = request.headers.get(header_name, "").strip()
    if not principal:
        return AuthContext(authenticated=False, principal=None, mode=mode, reason=f"missing_{header_name.lower()}")
    return AuthContext(authenticated=True, principal=principal, mode=mode, reason="ok")


def _normalized_auth_mode(raw_mode: str) -> AuthMode:
    normalized = (raw_mode or "").strip().lower()
    if normalized in {"", "off", "disabled", "none"}:
        return "off"
    if normalized in {"bearer", "token"}:
        return "bearer"
    if normalized in {"forwarded-user", "forwarded", "proxy"}:
        return "forwarded-user"
    return "off"
