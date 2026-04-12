from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.api.handlers._shared as shared_module
import app.main as main_module
from app.db import get_db_session
from app.main import app
from app.services.hot_cache import shared_hot_response_cache


class _NotFoundEdgarClient:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def resolve_company(self, query: str):
        self._calls.append(query)
        raise ValueError("not_found")

    def close(self) -> None:
        return None


class _ResolvedEdgarClient:
    def resolve_company(self, query: str):
        return SimpleNamespace(ticker=query, name="Netflix, Inc.", cik="0001065280")

    def close(self) -> None:
        return None


class _AsyncSessionOverride:
    def __init__(self, sync_session: object) -> None:
        self._sync_session = sync_session

    async def run_sync(self, callback):
        return callback(self._sync_session)


def test_resolve_endpoint_reuses_shared_hot_cache_for_repeated_queries(monkeypatch) -> None:
    calls: list[str] = []
    app.dependency_overrides[get_db_session] = lambda: SimpleNamespace()
    shared_hot_response_cache.clear_sync()
    monkeypatch.setattr(shared_module, "EdgarClient", lambda: _NotFoundEdgarClient(calls))
    monkeypatch.setattr(main_module, "EdgarClient", lambda: _NotFoundEdgarClient(calls))

    try:
        with TestClient(app) as client:
            first = client.get("/api/companies/resolve", params={"query": "UNKNOWN-TICKER"})
            second = client.get("/api/companies/resolve", params={"query": "UNKNOWN-TICKER"})
    finally:
        app.dependency_overrides.clear()
        shared_hot_response_cache.clear_sync()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {
        "query": "UNKNOWN-TICKER",
        "resolved": False,
        "ticker": None,
        "name": None,
        "error": "not_found",
    }
    assert second.json() == first.json()
    assert calls == ["UNKNOWN-TICKER"]


def test_resolve_endpoint_uses_bound_sync_session_for_canonical_ticker_lookup(monkeypatch) -> None:
    sync_session = object()
    async_session = _AsyncSessionOverride(sync_session)

    def resolve_canonical_ticker(session, identity) -> str:
        assert session is sync_session
        assert identity.cik == "0001065280"
        return "NFLX"

    app.dependency_overrides[get_db_session] = lambda: async_session
    shared_hot_response_cache.clear_sync()
    monkeypatch.setattr(shared_module, "EdgarClient", _ResolvedEdgarClient)
    monkeypatch.setattr(main_module, "EdgarClient", _ResolvedEdgarClient)
    monkeypatch.setattr(shared_module, "_resolve_canonical_ticker", resolve_canonical_ticker)
    monkeypatch.setattr(main_module, "_resolve_canonical_ticker", resolve_canonical_ticker)

    try:
        with TestClient(app) as client:
            response = client.get("/api/companies/resolve", params={"query": "NFLX"})
    finally:
        app.dependency_overrides.clear()
        shared_hot_response_cache.clear_sync()

    assert response.status_code == 200
    assert response.json() == {
        "query": "NFLX",
        "resolved": True,
        "ticker": "NFLX",
        "name": "Netflix, Inc.",
        "error": None,
    }
