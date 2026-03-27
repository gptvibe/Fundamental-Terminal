from __future__ import annotations

from datetime import date, datetime, timezone
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


def _financial_statement(source: str = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"):
    return SimpleNamespace(
        filing_type="10-K",
        statement_type="canonical_xbrl",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source=source,
        last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc),
        data={
            "revenue": 391_000_000_000,
            "net_income": 97_000_000_000,
            "operating_income": 123_000_000_000,
            "free_cash_flow": 110_000_000_000,
            "segment_breakdown": [],
        },
    )


def _price_point():
    return SimpleNamespace(
        trade_date=date(2026, 3, 21),
        close=190.5,
        volume=10_000_000,
        source="https://finance.yahoo.com/quote/AAPL",
    )


def _assert_provenance_envelope(payload: dict, expected_sources: set[str], *, require_as_of: bool = True) -> None:
    assert payload["provenance"]
    assert {entry["source_id"] for entry in payload["provenance"]} == expected_sources
    if require_as_of:
        assert payload["as_of"] is not None
    assert payload["last_refreshed_at"] is not None
    assert payload["source_mix"]["source_ids"]
    assert isinstance(payload["confidence_flags"], list)


def test_financials_route_includes_registry_backed_provenance(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [_price_point()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/financials")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(payload, {"sec_companyfacts", "yahoo_finance"})
    assert payload["as_of"] == "2025-12-31"
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "commercial_fallback_present" in payload["confidence_flags"]


def test_models_route_includes_registry_backed_provenance(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_models",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                model_name="dcf",
                model_version="v2",
                created_at=datetime(2026, 3, 22, tzinfo=timezone.utc),
                input_periods={"period_end": "2025-12-31"},
                result={
                    "model_status": "ok",
                    "base_period_end": "2025-12-31",
                    "price_snapshot": {
                        "price_date": "2026-03-21",
                        "price_source": "yahoo_finance",
                    },
                    "assumption_provenance": {
                        "risk_free_rate": {
                            "source_name": "U.S. Treasury Daily Par Yield Curve",
                            "observation_date": "2026-03-20",
                        }
                    },
                },
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/models")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(
        payload,
        {"ft_model_engine", "sec_companyfacts", "us_treasury_daily_par_yield_curve", "yahoo_finance"},
    )
    assert payload["as_of"] == "2025-12-31"
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "commercial_fallback_present" in payload["confidence_flags"]


def test_peers_route_includes_registry_backed_provenance(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "build_peer_comparison",
        lambda *_args, **_kwargs: {
            "company": SimpleNamespace(company=snapshot.company, cache_state="fresh", last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc)),
            "peer_basis": "Technology peers",
            "available_companies": [],
            "selected_tickers": ["MSFT"],
            "peers": [
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Consumer Electronics",
                    "is_focus": True,
                    "cache_state": "fresh",
                    "last_checked": "2026-03-22T00:00:00Z",
                    "period_end": "2025-12-31",
                    "price_date": "2026-03-21",
                    "latest_price": 190.5,
                    "pe": 28.0,
                    "ev_to_ebit": 20.0,
                    "price_to_free_cash_flow": 30.0,
                    "roe": 0.24,
                    "revenue_growth": 0.08,
                    "piotroski_score": 8,
                    "altman_z_score": 4.2,
                    "dcf_model_status": "partial",
                    "reverse_dcf_model_status": "ok",
                    "revenue_history": [],
                }
            ],
            "notes": {"ev_to_ebit": "proxy"},
            "source_hints": {
                "financial_statement_sources": ["sec_companyfacts"],
                "price_sources": ["yahoo_finance"],
                "risk_free_sources": ["U.S. Treasury Daily Par Yield Curve"],
            },
        },
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/peers")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(
        payload,
        {"ft_peer_comparison", "sec_companyfacts", "us_treasury_daily_par_yield_curve", "yahoo_finance"},
    )
    assert payload["as_of"] == "2025-12-31"
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "partial_peer_models" in payload["confidence_flags"]


def test_activity_overview_route_includes_registry_backed_provenance(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "_load_company_activity_data",
        lambda *_args, **_kwargs: {
            "filings": [],
            "filing_events": [],
            "governance_filings": [],
            "beneficial_filings": [],
            "insider_trades": [],
            "form144_filings": [],
            "institutional_holdings": [],
            "capital_filings": [],
        },
    )
    monkeypatch.setattr(
        main_module,
        "get_cached_market_context_status",
        lambda: {
            "state": "partial",
            "label": "Macro partial",
            "observation_date": "2026-03-21",
            "source": "U.S. Treasury Daily Par Yield Curve",
            "treasury_status": "ok",
        },
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/activity-overview")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(
        payload,
        {"ft_activity_overview", "sec_edgar", "us_treasury_daily_par_yield_curve"},
        require_as_of=False,
    )
    assert payload["as_of"] is None
    assert payload["source_mix"]["official_only"] is True
    assert "activity_feed_empty" in payload["confidence_flags"]
    assert "market_context_partial" in payload["confidence_flags"]
