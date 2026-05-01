from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import _shared as shared_handlers
import app.api.handlers.jobs as job_handlers
import app.legacy_api as legacy_module
from app.config import settings
from app.main import create_app


def _override_settings(**updates):
    original_values = {name: getattr(settings, name) for name in updates}
    for name, value in updates.items():
        object.__setattr__(settings, name, value)
    return original_values


def _restore_settings(original_values):
    for name, value in original_values.items():
        object.__setattr__(settings, name, value)


def _patch_legacy_targets(monkeypatch, name: str, value) -> None:
    monkeypatch.setattr(main_module, name, value)
    monkeypatch.setattr(legacy_module, name, value)
    if hasattr(shared_handlers, name):
        monkeypatch.setattr(shared_handlers, name, value)
    if hasattr(job_handlers, name):
        monkeypatch.setattr(job_handlers, name, value)


def test_protected_endpoint_rejects_unauthenticated_requests() -> None:
    original_settings = _override_settings(
        auth_mode="bearer",
        auth_bearer_token="super-secret-token",
        auth_required_path_prefixes=("/api/internal",),
        auth_exempt_paths=("/health", "/readyz"),
        security_headers_enabled=True,
    )

    try:
        client = TestClient(create_app())
        response = client.get("/api/internal/cache-metrics")

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Authentication required",
            "reason": "missing_bearer_token",
            "mode": "bearer",
        }
        assert response.headers["WWW-Authenticate"] == "Bearer"
    finally:
        _restore_settings(original_settings)


def test_protected_endpoint_allows_authenticated_requests(monkeypatch) -> None:
    async def _snapshot_metrics() -> dict[str, object]:
        return {
            "backend": "local",
            "backend_mode": "local_memory_fallback",
            "shared": False,
            "namespace": "ft:hot-cache",
            "backend_details": {
                "configured_backend": "redis",
                "cache_scope": "process-local",
                "redis_configured": True,
                "fallback_active": False,
                "startup_reason": None,
                "fallback_events_total": 0,
                "last_fallback_reason": None,
                "last_fallback_error": None,
                "last_fallback_at": None,
                "cross_instance_reuse": "disabled",
                "status": "ok",
                "summary": "Local cache active.",
                "operational_impact": "",
                "recommended_checks": [],
            },
            "config": {
                "ttl_seconds": 20,
                "stale_ttl_seconds": 120,
                "singleflight_lock_seconds": 30,
                "singleflight_wait_seconds": 15.0,
                "singleflight_poll_seconds": 0.05,
            },
            "overall": {},
            "routes": {},
        }

    original_settings = _override_settings(
        auth_mode="bearer",
        auth_bearer_token="super-secret-token",
        auth_required_path_prefixes=("/api/internal",),
        auth_exempt_paths=("/health", "/readyz"),
        security_headers_enabled=True,
    )
    monkeypatch.setattr(shared_handlers.shared_hot_response_cache, "snapshot_metrics", _snapshot_metrics)

    try:
        client = TestClient(create_app())
        response = client.get(
            "/api/internal/cache-metrics",
            headers={"Authorization": "Bearer super-secret-token"},
        )

        assert response.status_code == 200
        assert response.json()["hot_cache_backend"] == "local"
    finally:
        _restore_settings(original_settings)


def test_health_endpoint_remains_accessible_when_auth_is_enabled(monkeypatch) -> None:
    async def _database_health_payload():
        return {"status": "ok", "pool": {"label": "primary"}}, True

    async def _redis_health_payload():
        return {"status": "ok"}, True

    async def _worker_health_payload():
        return {"status": "ok"}, True

    async def _sec_upstream_health_payload():
        return {"status": "ok", "healthy": True}, True

    _patch_legacy_targets(monkeypatch, "_database_health_payload", _database_health_payload)
    _patch_legacy_targets(monkeypatch, "_redis_health_payload", _redis_health_payload)
    _patch_legacy_targets(monkeypatch, "_worker_health_payload", _worker_health_payload)
    _patch_legacy_targets(monkeypatch, "_sec_upstream_health_payload", _sec_upstream_health_payload)
    original_settings = _override_settings(
        auth_mode="bearer",
        auth_bearer_token="super-secret-token",
        auth_required_path_prefixes=("/api/internal",),
        auth_exempt_paths=("/health", "/readyz"),
        security_headers_enabled=True,
    )

    try:
        client = TestClient(create_app())
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["overall_status"] == "ok"
    finally:
        _restore_settings(original_settings)
