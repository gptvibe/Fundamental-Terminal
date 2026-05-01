from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
import app.middleware.rate_limit as rate_limit_middleware
from app.main import create_app
from app.services.rate_limit import RateLimitDecision


def _override_settings(**updates):
    original_values = {name: getattr(settings, name) for name in updates}
    for name, value in updates.items():
        object.__setattr__(settings, name, value)
    return original_values


def _restore_settings(original_values):
    for name, value in original_values.items():
        object.__setattr__(settings, name, value)


def test_rate_limit_middleware_returns_existing_retry_headers(monkeypatch) -> None:
    async def _deny(*_args, **_kwargs):
        return RateLimitDecision(
            allowed=False,
            limit=3,
            remaining=0,
            reset_at_epoch=1_700_000_000,
            retry_after_seconds=17,
        )

    original_settings = _override_settings(auth_mode="off", security_headers_enabled=True)
    monkeypatch.setattr(rate_limit_middleware, "is_rate_limited_public_route", lambda _path: True)
    monkeypatch.setattr(rate_limit_middleware.public_route_rate_limiter, "evaluate", _deny)

    try:
        client = TestClient(create_app())
        response = client.get("/api/companies/search?query=AAPL")

        assert response.status_code == 429
        assert response.json() == {
            "detail": "Rate limit exceeded",
            "limit": 3,
            "retry_after_seconds": 17,
        }
        assert response.headers["Retry-After"] == "17"
        assert response.headers["X-RateLimit-Limit"] == "3"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Reset"] == "1700000000"
    finally:
        _restore_settings(original_settings)


def test_rate_limit_middleware_preserves_downstream_response_and_adds_headers(monkeypatch) -> None:
    async def _allow(*_args, **_kwargs):
        return RateLimitDecision(
            allowed=True,
            limit=5,
            remaining=4,
            reset_at_epoch=1_700_000_123,
            retry_after_seconds=0,
        )

    original_settings = _override_settings(auth_mode="off", security_headers_enabled=True)
    monkeypatch.setattr(rate_limit_middleware, "is_rate_limited_public_route", lambda _path: True)
    monkeypatch.setattr(rate_limit_middleware.public_route_rate_limiter, "evaluate", _allow)

    try:
        client = TestClient(create_app())
        response = client.get("/api/nonexistent")

        assert response.status_code == 404
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "4"
        assert response.headers["X-RateLimit-Reset"] == "1700000123"
    finally:
        _restore_settings(original_settings)


def test_rate_limit_middleware_uses_direct_ip_when_proxy_trust_disabled(monkeypatch) -> None:
    seen_counts: dict[str, int] = {}

    async def _evaluate(identifier: str) -> RateLimitDecision:
        count = seen_counts.get(identifier, 0) + 1
        seen_counts[identifier] = count
        return RateLimitDecision(
            allowed=count <= 1,
            limit=1,
            remaining=0 if count > 1 else 0,
            reset_at_epoch=1_700_000_000,
            retry_after_seconds=17,
        )

    original_settings = _override_settings(
        auth_mode="off",
        security_headers_enabled=True,
        api_rate_limit_trust_proxy=False,
    )
    monkeypatch.setattr(rate_limit_middleware, "is_rate_limited_public_route", lambda _path: True)
    monkeypatch.setattr(rate_limit_middleware.public_route_rate_limiter, "evaluate", _evaluate)

    try:
        client = TestClient(create_app())
        first = client.get("/api/nonexistent", headers={"X-Forwarded-For": "203.0.113.10"})
        second = client.get("/api/nonexistent", headers={"X-Forwarded-For": "198.51.100.20"})

        assert first.status_code != 429
        assert second.status_code == 429
        assert len(seen_counts) == 1
    finally:
        _restore_settings(original_settings)


def test_rate_limit_middleware_can_trust_proxy_when_enabled(monkeypatch) -> None:
    seen_counts: dict[str, int] = {}

    async def _evaluate(identifier: str) -> RateLimitDecision:
        count = seen_counts.get(identifier, 0) + 1
        seen_counts[identifier] = count
        return RateLimitDecision(
            allowed=True,
            limit=1,
            remaining=1 - min(count, 1),
            reset_at_epoch=1_700_000_000,
            retry_after_seconds=17,
        )

    original_settings = _override_settings(
        auth_mode="off",
        security_headers_enabled=True,
        api_rate_limit_trust_proxy=True,
    )
    monkeypatch.setattr(rate_limit_middleware, "is_rate_limited_public_route", lambda _path: True)
    monkeypatch.setattr(rate_limit_middleware.public_route_rate_limiter, "evaluate", _evaluate)

    try:
        client = TestClient(create_app())
        first = client.get("/api/nonexistent", headers={"X-Forwarded-For": "203.0.113.10"})
        second = client.get("/api/nonexistent", headers={"X-Forwarded-For": "198.51.100.20"})

        assert first.status_code != 429
        assert second.status_code != 429
        assert set(seen_counts) == {"203.0.113.10", "198.51.100.20"}
    finally:
        _restore_settings(original_settings)
