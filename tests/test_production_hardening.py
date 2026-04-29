from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
import app.services.rate_limit as rate_limit_module
from app.main import app
from app.services.rate_limit import PublicRouteRateLimiter, RateLimitDecision


def _override_settings(**updates):
    original_values = {name: getattr(main_module.settings, name) for name in updates}
    for name, value in updates.items():
        object.__setattr__(main_module.settings, name, value)
    return original_values


def _restore_settings(original_values):
    for name, value in original_values.items():
        object.__setattr__(main_module.settings, name, value)


def test_healthcheck_surfaces_hardening_summary(monkeypatch) -> None:
    async def _database_health_payload():
        return {"status": "ok", "pool": {"label": "primary"}}, True

    async def _redis_health_payload():
        return {"status": "degraded", "summary": "redis fallback"}, True

    async def _worker_health_payload():
        return {"status": "degraded", "detail": "No live refresh worker heartbeat detected."}, False

    async def _sec_upstream_health_payload():
        return {"status": "ok", "latency_ms": 12.5, "healthy": True}, True

    monkeypatch.setattr(main_module, "_database_health_payload", _database_health_payload)
    monkeypatch.setattr(main_module, "_redis_health_payload", _redis_health_payload)
    monkeypatch.setattr(main_module, "_worker_health_payload", _worker_health_payload)
    monkeypatch.setattr(main_module, "_sec_upstream_health_payload", _sec_upstream_health_payload)
    original_settings = _override_settings(
        auth_mode="forwarded-user",
        auth_required_path_prefixes=("/api/internal", "/api/admin"),
        api_rate_limit_enabled=True,
        api_rate_limit_requests=180,
        api_rate_limit_window_seconds=60,
        api_rate_limit_trust_proxy=True,
        security_headers_enabled=True,
    )

    try:
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["overall_status"] == "degraded"
        assert payload["degraded_components"] == ["worker"]
        assert payload["components"]["api"]["auth_mode"] == "forwarded-user"
        assert payload["components"]["api"]["auth_required_path_prefixes"] == ["/api/internal", "/api/admin"]
        assert payload["components"]["api"]["rate_limit"] == {
            "enabled": True,
            "requests": 180,
            "window_seconds": 60,
            "trust_proxy": True,
        }
        assert response.headers["X-Frame-Options"] == "DENY"
    finally:
        _restore_settings(original_settings)


def test_auth_middleware_blocks_internal_routes_and_keeps_security_headers(monkeypatch) -> None:
    original_settings = _override_settings(
        auth_mode="bearer",
        auth_bearer_token="super-secret-token",
        auth_required_path_prefixes=("/api/internal",),
        auth_exempt_paths=("/health", "/readyz"),
        security_headers_enabled=True,
    )

    try:
        client = TestClient(app)
        response = client.get("/api/internal/cache-metrics")

        assert response.status_code == 401
        assert response.json()["reason"] == "missing_bearer_token"
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    finally:
        _restore_settings(original_settings)


def test_rate_limit_middleware_returns_retry_metadata(monkeypatch) -> None:
    async def _deny(*_args, **_kwargs):
        return RateLimitDecision(
            allowed=False,
            limit=3,
            remaining=0,
            reset_at_epoch=1_700_000_000,
            retry_after_seconds=17,
        )

    original_settings = _override_settings(
        auth_mode="off",
        security_headers_enabled=True,
    )
    monkeypatch.setattr(main_module, "_is_rate_limited_public_route", lambda _path: True)
    monkeypatch.setattr(main_module.public_route_rate_limiter, "evaluate", _deny)

    try:
        client = TestClient(app)
        response = client.get("/api/companies/search?query=AAPL")

        assert response.status_code == 429
        assert response.json()["detail"] == "Rate limit exceeded"
        assert response.headers["Retry-After"] == "17"
        assert response.headers["X-RateLimit-Limit"] == "3"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Reset"] == "1700000000"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    finally:
        _restore_settings(original_settings)


def test_rate_limit_ignores_spoofed_x_forwarded_for_by_default(monkeypatch) -> None:
    seen_counts: dict[str, int] = {}

    async def _evaluate(identifier: str) -> RateLimitDecision:
        count = seen_counts.get(identifier, 0) + 1
        seen_counts[identifier] = count
        allowed = count <= 1
        return RateLimitDecision(
            allowed=allowed,
            limit=1,
            remaining=0 if not allowed else 1 - count,
            reset_at_epoch=1_700_000_000,
            retry_after_seconds=17,
        )

    original_settings = _override_settings(
        auth_mode="off",
        security_headers_enabled=True,
        api_rate_limit_trust_proxy=False,
    )
    monkeypatch.setattr(main_module, "_is_rate_limited_public_route", lambda _path: True)
    monkeypatch.setattr(main_module.public_route_rate_limiter, "evaluate", _evaluate)

    try:
        client = TestClient(app)
        first = client.get("/api/nonexistent", headers={"X-Forwarded-For": "203.0.113.10"})
        second = client.get("/api/nonexistent", headers={"X-Forwarded-For": "198.51.100.20"})

        assert first.status_code != 429
        assert second.status_code == 429
        assert len(seen_counts) == 1
    finally:
        _restore_settings(original_settings)


def test_rate_limit_can_trust_x_forwarded_for_when_opted_in(monkeypatch) -> None:
    seen_counts: dict[str, int] = {}

    async def _evaluate(identifier: str) -> RateLimitDecision:
        count = seen_counts.get(identifier, 0) + 1
        seen_counts[identifier] = count
        allowed = count <= 1
        return RateLimitDecision(
            allowed=allowed,
            limit=1,
            remaining=0 if not allowed else 1 - count,
            reset_at_epoch=1_700_000_000,
            retry_after_seconds=17,
        )

    original_settings = _override_settings(
        auth_mode="off",
        security_headers_enabled=True,
        api_rate_limit_trust_proxy=True,
    )
    monkeypatch.setattr(main_module, "_is_rate_limited_public_route", lambda _path: True)
    monkeypatch.setattr(main_module.public_route_rate_limiter, "evaluate", _evaluate)

    try:
        client = TestClient(app)
        first = client.get("/api/nonexistent", headers={"X-Forwarded-For": "203.0.113.10"})
        second = client.get("/api/nonexistent", headers={"X-Forwarded-For": "198.51.100.20"})

        assert first.status_code != 429
        assert second.status_code != 429
        assert set(seen_counts) == {"203.0.113.10", "198.51.100.20"}
    finally:
        _restore_settings(original_settings)


def test_local_rate_limit_fallback_is_safe_across_threads() -> None:
    limiter = PublicRouteRateLimiter()
    limiter._redis = None

    def _evaluate_once():
        return asyncio.run(limiter.evaluate("198.51.100.10"))

    with ThreadPoolExecutor(max_workers=6) as executor:
        decisions = list(executor.map(lambda _index: _evaluate_once(), range(12)))

    assert len(decisions) == 12
    assert all(isinstance(decision, RateLimitDecision) for decision in decisions)


def test_local_rate_limit_evicts_stale_windows_but_preserves_recent_ones() -> None:
    limiter = PublicRouteRateLimiter()
    limiter._redis = None
    limiter._window_seconds = 60
    limiter._local_counts = {
        "test:public-api:stale:0": (4, 10),
        "test:public-api:recent:120": (2, 150),
        "test:public-api:current:180": (1, 240),
    }

    decision = asyncio.run(
        limiter._evaluate_local(
            redis_key="test:public-api:new:180",
            now=200,
            window_end=240,
        )
    )

    assert decision.allowed is True
    assert decision.remaining == limiter._limit - 1
    assert "test:public-api:stale:0" not in limiter._local_counts
    assert limiter._local_counts["test:public-api:recent:120"] == (2, 150)
    assert limiter._local_counts["test:public-api:current:180"] == (1, 240)
    assert limiter._local_counts["test:public-api:new:180"] == (1, 240)


def test_rate_limit_redis_keys_use_dedicated_namespace(monkeypatch) -> None:
    observed: dict[str, str] = {}

    async def _capture_local(*, redis_key: str, now: int, window_end: int) -> RateLimitDecision:
        observed["redis_key"] = redis_key
        return RateLimitDecision(
            allowed=True,
            limit=10,
            remaining=9,
            reset_at_epoch=window_end,
            retry_after_seconds=0,
        )

    monkeypatch.setattr(
        rate_limit_module,
        "settings",
        SimpleNamespace(
            api_rate_limit_enabled=True,
            api_rate_limit_requests=10,
            api_rate_limit_window_seconds=60,
            rate_limit_namespace="ft:test-rate-limit",
            redis_url="",
        ),
    )
    monkeypatch.setattr(rate_limit_module.time, "time", lambda: 125)

    limiter = rate_limit_module.PublicRouteRateLimiter()
    limiter._redis = None
    monkeypatch.setattr(limiter, "_evaluate_local", _capture_local)

    decision = asyncio.run(limiter.evaluate("198.51.100.10", scope="public-api"))

    assert decision.allowed is True
    assert observed["redis_key"] == "ft:test-rate-limit:public-api:198.51.100.10:120"
