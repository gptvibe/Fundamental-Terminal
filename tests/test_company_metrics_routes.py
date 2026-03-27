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


def _metric_row(period_type: str, period_end: date, metric_key: str, value: float):
    return SimpleNamespace(
        period_type=period_type,
        period_start=date(period_end.year, 1, 1),
        period_end=period_end,
        filing_type="TTM" if period_type == "ttm" else "10-K",
        metric_key=metric_key,
        metric_value=value,
        is_proxy=False,
        provenance={
            "formula_version": "sec_metrics_mart_v1",
            "unit": "ratio",
            "statement_source": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            "price_source": "yahoo_finance",
        },
        quality_flags=[],
    )


def test_metrics_endpoint_returns_typed_payload(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_derived_metric_points",
        lambda *_args, **_kwargs: [
            _metric_row("ttm", date(2025, 12, 31), "revenue_growth", 0.12),
            _metric_row("ttm", date(2025, 12, 31), "gross_margin", 0.43),
        ],
    )
    monkeypatch.setattr(main_module, "get_company_derived_metrics_last_checked", lambda *_args, **_kwargs: datetime.now(timezone.utc))

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/metrics?period_type=ttm&max_periods=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["ticker"] == "AAPL"
    assert payload["period_type"] == "ttm"
    assert payload["periods"]
    assert payload["periods"][0]["period_type"] == "ttm"
    assert payload["periods"][0]["metrics"][0]["metric_key"] in {"gross_margin", "revenue_growth"}
    assert "available_metric_keys" in payload
    assert payload["as_of"] == "2025-12-31"
    assert payload["last_refreshed_at"] is not None
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "ft_derived_metrics_mart",
        "sec_companyfacts",
        "yahoo_finance",
    }
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "commercial_fallback_present" in payload["confidence_flags"]


def test_metrics_summary_endpoint_returns_latest_period(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_derived_metric_points",
        lambda *_args, **_kwargs: [
            _metric_row("ttm", date(2025, 9, 30), "revenue_growth", 0.1),
            _metric_row("ttm", date(2025, 12, 31), "revenue_growth", 0.12),
        ],
    )
    monkeypatch.setattr(main_module, "get_company_derived_metrics_last_checked", lambda *_args, **_kwargs: datetime.now(timezone.utc))

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/metrics/summary?period_type=ttm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["ticker"] == "AAPL"
    assert payload["latest_period_end"] == "2025-12-31"
    assert payload["metrics"]
    assert payload["as_of"] == "2025-12-31"
    assert payload["last_refreshed_at"] is not None
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "ft_derived_metrics_mart",
        "sec_companyfacts",
        "yahoo_finance",
    }
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "commercial_fallback_present" in payload["confidence_flags"]


def test_metrics_endpoint_triggers_refresh_when_company_missing(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="AAPL", job_id="job-1"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] is None
    assert payload["periods"] == []
    assert payload["refresh"]["triggered"] is True
    assert payload["provenance"] == []
    assert payload["source_mix"]["source_ids"] == []
    assert payload["confidence_flags"] == ["company_missing"]
