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


def test_search_route_does_not_trigger_refresh_when_refresh_disabled_on_stale_hot_cache(monkeypatch):
    trigger_calls: list[str] = []

    monkeypatch.setattr(
        main_module,
        "_get_hot_cached_payload",
        lambda *_args, **_kwargs: (
            {
                "query": "O",
                "results": [
                    {
                        "ticker": "ON",
                        "cik": "0001097864",
                        "name": "ON SEMICONDUCTOR CORP",
                        "sector": "Semiconductors & Related Devices",
                        "market_sector": "Technology",
                        "market_industry": "Semiconductors",
                        "oil_exposure_type": "non_oil",
                        "oil_support_status": "unsupported",
                        "oil_support_reasons": ["non_energy_classification"],
                        "regulated_entity": None,
                        "strict_official_mode": False,
                        "last_checked": datetime.now(timezone.utc).isoformat(),
                        "last_checked_financials": datetime.now(timezone.utc).isoformat(),
                        "last_checked_prices": None,
                        "last_checked_insiders": None,
                        "last_checked_institutional": None,
                        "last_checked_filings": None,
                        "earnings_last_checked": None,
                        "cache_state": "stale",
                    }
                ],
                "refresh": {"triggered": False, "reason": "stale", "ticker": "O", "job_id": None},
            },
            False,
        ),
    )
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: trigger_calls.append("called") or RefreshState(triggered=True, reason="stale", ticker="O", job_id="job-1"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/search?query=O&refresh=false")

    assert response.status_code == 200
    assert response.json()["refresh"] == {"triggered": False, "reason": "stale", "ticker": "O", "job_id": None}
    assert trigger_calls == []


def test_financials_route_supports_conditional_get(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_regulated_bank_financials", lambda *_args, **_kwargs: [])
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
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/AAPL/models")


def test_model_evaluation_route_supports_conditional_get(monkeypatch):
    completed_at = datetime.now(timezone.utc)
    payload = {
        "id": 7,
        "suite_key": "historical_fixture_v1",
        "candidate_label": "fixture_baseline_v1",
        "baseline_label": "fixture_baseline_v1",
        "status": "completed",
        "completed_at": completed_at,
        "configuration": {"horizon_days": 420},
        "summary": {"provenance_mode": "synthetic_fixture", "latest_as_of": "2025-02-15"},
        "models": [
            {
                "model_name": "dcf",
                "sample_count": 8,
                "calibration": 0.75,
                "stability": 0.08,
                "mean_absolute_error": 0.11,
                "root_mean_square_error": 0.13,
                "mean_signed_error": 0.02,
                "status": "ok",
                "delta": {
                    "calibration": 0,
                    "stability": 0,
                    "mean_absolute_error": 0,
                    "root_mean_square_error": 0,
                    "mean_signed_error": 0,
                    "sample_count": 0,
                },
            }
        ],
        "deltas_present": False,
    }
    monkeypatch.setattr(main_module, "get_latest_model_evaluation_run", lambda *_args, **_kwargs: SimpleNamespace(created_at=completed_at, completed_at=completed_at))
    monkeypatch.setattr(main_module, "serialize_model_evaluation_run", lambda *_args, **_kwargs: payload)

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/model-evaluations/latest")


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
