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



def test_metrics_timeseries_endpoint_returns_typed_payload(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    observed: dict[str, object] = {"cadence": None, "max_points": None}

    def _build_metrics_timeseries(*_args, **kwargs):
        observed["cadence"] = kwargs.get("cadence")
        observed["max_points"] = kwargs.get("max_points")
        return [
            {
                "cadence": "ttm",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "filing_type": "TTM",
                "metrics": {
                    "revenue_growth": 0.12,
                    "gross_margin": 0.42,
                },
                "provenance": {
                    "statement_type": "canonical_xbrl",
                    "statement_source": "https://data.sec.gov/example",
                    "price_source": "yahoo_finance",
                    "formula_version": "sec_metrics_v1",
                },
                "quality": {
                    "available_metrics": 2,
                    "missing_metrics": ["operating_margin"],
                    "coverage_ratio": 0.1333,
                    "flags": ["low_metric_coverage"],
                },
            }
        ]

    monkeypatch.setattr(main_module, "build_metrics_timeseries", _build_metrics_timeseries)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/metrics-timeseries?cadence=ttm&max_points=10")

    assert response.status_code == 200
    payload = response.json()
    assert observed["cadence"] == "ttm"
    assert observed["max_points"] == 10
    assert payload["company"]["ticker"] == "AAPL"
    assert payload["series"][0]["cadence"] == "ttm"
    assert payload["series"][0]["metrics"]["revenue_growth"] == 0.12
    assert payload["series"][0]["provenance"]["formula_version"] == "sec_metrics_v1"
    assert payload["last_financials_check"] is not None
    assert payload["last_price_check"] is not None
    assert payload["staleness_reason"] == "fresh"
    assert payload["as_of"] == "2025-12-31"
    assert payload["last_refreshed_at"] is not None
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "ft_derived_metrics_engine",
        "sec_edgar",
        "yahoo_finance",
    }
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "commercial_fallback_present" in payload["confidence_flags"]



def test_metrics_timeseries_endpoint_triggers_refresh_when_company_missing(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="AAPL", job_id="job-1"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/metrics-timeseries")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] is None
    assert payload["series"] == []
    assert payload["last_financials_check"] is None
    assert payload["last_price_check"] is None
    assert payload["staleness_reason"] == "company_missing"
    assert payload["refresh"]["triggered"] is True
    assert payload["refresh"]["reason"] == "missing"
    assert payload["provenance"] == []
    assert payload["source_mix"]["source_ids"] == []
    assert payload["confidence_flags"] == ["company_missing"]
