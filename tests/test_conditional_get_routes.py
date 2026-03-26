from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import RefreshState, app


def _snapshot(ticker: str = "AAPL", cik: str = "0000320193"):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik=cik,
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


def _assert_304_on_second_request(client: TestClient, url: str) -> None:
    first = client.get(url)
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag

    second = client.get(url, headers={"If-None-Match": etag})
    assert second.status_code == 304


def test_search_route_supports_conditional_get(monkeypatch):
    monkeypatch.setattr(main_module, "search_company_snapshots", lambda *_args, **_kwargs: [_snapshot()])
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/search?query=AAPL&refresh=false")


def test_financials_route_supports_conditional_get(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/AAPL/financials")


def test_models_route_supports_conditional_get(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/AAPL/models")


def test_peers_route_supports_conditional_get(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "build_peer_comparison",
        lambda *_args, **_kwargs: {
            "company": snapshot,
            "peer_basis": "Technology peers",
            "available_companies": [],
            "selected_tickers": [],
            "peers": [],
            "notes": {},
        },
    )

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/AAPL/peers")
