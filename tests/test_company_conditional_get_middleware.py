from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.middleware.conditional_get as conditional_get


def _build_test_app(call_log: list[str]) -> FastAPI:
    app = FastAPI()
    conditional_get.register_company_conditional_get_middleware(app)

    @app.get("/api/companies/AAPL/financials")
    async def financials():
        call_log.append("called")
        return JSONResponse({"company": {"ticker": "AAPL"}})

    return app


def test_company_conditional_get_middleware_returns_304_on_matching_if_none_match(monkeypatch) -> None:
    call_log: list[str] = []

    async def _cache_metadata(*_args, **_kwargs):
        return 'W/"company-aapl"', "Sun, 13 Apr 2026 00:00:00 GMT", False

    async def _no_hot_cache(*_args, **_kwargs):
        return None

    monkeypatch.setattr(conditional_get, "_resolve_company_route_cache_metadata", _cache_metadata)
    monkeypatch.setattr(conditional_get, "_resolve_company_route_hot_cache_metadata", _no_hot_cache)

    client = TestClient(_build_test_app(call_log))
    response = client.get(
        "/api/companies/AAPL/financials",
        headers={"If-None-Match": 'W/"company-aapl"'},
    )

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["cache-control"] == "public, max-age=20, stale-while-revalidate=300"
    assert response.headers["etag"] == 'W/"company-aapl"'
    assert call_log == []


def test_company_conditional_get_middleware_returns_body_on_non_matching_if_none_match(monkeypatch) -> None:
    call_log: list[str] = []

    async def _cache_metadata(*_args, **_kwargs):
        return 'W/"company-aapl"', "Sun, 13 Apr 2026 00:00:00 GMT", False

    async def _no_hot_cache(*_args, **_kwargs):
        return None

    monkeypatch.setattr(conditional_get, "_resolve_company_route_cache_metadata", _cache_metadata)
    monkeypatch.setattr(conditional_get, "_resolve_company_route_hot_cache_metadata", _no_hot_cache)

    client = TestClient(_build_test_app(call_log))
    response = client.get(
        "/api/companies/AAPL/financials",
        headers={"If-None-Match": 'W/"something-else"'},
    )

    assert response.status_code == 200
    assert response.json() == {"company": {"ticker": "AAPL"}}
    assert response.headers["cache-control"] == "public, max-age=20, stale-while-revalidate=300"
    assert response.headers["etag"] == 'W/"company-aapl"'
    assert call_log == ["called"]
