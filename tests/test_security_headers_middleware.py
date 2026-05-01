from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as shared_handlers
import app.api.handlers.jobs as job_handlers
import app.legacy_api as legacy_module
from app.config import settings
from app.main import create_app
from app.middleware.security_headers import SecurityHeadersMiddleware


def _patch_legacy_targets(monkeypatch, name: str, value) -> None:
    monkeypatch.setattr(main_module, name, value)
    monkeypatch.setattr(legacy_module, name, value)
    if hasattr(shared_handlers, name):
        monkeypatch.setattr(shared_handlers, name, value)
    if hasattr(job_handlers, name):
        monkeypatch.setattr(job_handlers, name, value)


def _override_settings(**updates):
    original_values = {name: getattr(settings, name) for name in updates}
    for name, value in updates.items():
        object.__setattr__(settings, name, value)
    return original_values


def _restore_settings(original_values):
    for name, value in original_values.items():
        object.__setattr__(settings, name, value)


def _healthy_session_scope():
    class _HealthySession:
        async def execute(self, _statement):
            return None

    class _HealthyScope:
        async def __aenter__(self):
            return _HealthySession()

        async def __aexit__(self, *_args):
            return False

    return _HealthyScope()


def test_create_app_registers_security_headers_middleware() -> None:
    app = create_app()

    assert any(entry.cls is SecurityHeadersMiddleware for entry in app.user_middleware)


def test_readyz_includes_expected_security_headers(monkeypatch) -> None:
    original_settings = _override_settings(security_headers_enabled=True)
    _patch_legacy_targets(monkeypatch, "_session_scope", _healthy_session_scope)

    try:
        client = TestClient(create_app())
        response = client.get("/readyz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Permissions-Policy"] == "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    finally:
        _restore_settings(original_settings)


def test_hsts_is_added_for_https_requests(monkeypatch) -> None:
    original_settings = _override_settings(security_headers_enabled=True)
    _patch_legacy_targets(monkeypatch, "_session_scope", _healthy_session_scope)

    try:
        client = TestClient(create_app(), base_url="https://testserver")
        response = client.get("/readyz")

        assert response.status_code == 200
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    finally:
        _restore_settings(original_settings)


def test_hsts_is_not_added_for_http_self_hosted_requests(monkeypatch) -> None:
    original_settings = _override_settings(security_headers_enabled=True)
    _patch_legacy_targets(monkeypatch, "_session_scope", _healthy_session_scope)

    try:
        client = TestClient(create_app())
        response = client.get("/readyz")

        assert response.status_code == 200
        assert "Strict-Transport-Security" not in response.headers
    finally:
        _restore_settings(original_settings)
