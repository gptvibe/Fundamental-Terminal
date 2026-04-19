from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.db import get_db_session
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


def _bank_snapshot():
    snapshot = _snapshot(ticker="WFC", cik="0000072971")
    snapshot.company.name = "Wells Fargo Bank, National Association"
    snapshot.company.sector = "Financials"
    snapshot.company.market_sector = "Financials"
    snapshot.company.market_industry = "Banks"
    return snapshot


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture(autouse=True)
def _stub_regulated_bank_query(monkeypatch):
    monkeypatch.setattr(main_module, "get_company_regulated_bank_financials", lambda *_args, **_kwargs: [])



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
                    "formula_version": "sec_metrics_v2",
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

    with _client() as client:
        response = client.get("/api/companies/AAPL/metrics-timeseries?cadence=ttm&max_points=10")

    assert response.status_code == 200
    payload = response.json()
    assert observed["cadence"] == "ttm"
    assert observed["max_points"] == 10
    assert payload["company"]["ticker"] == "AAPL"
    assert payload["series"][0]["cadence"] == "ttm"
    assert payload["series"][0]["metrics"]["revenue_growth"] == 0.12
    assert payload["series"][0]["provenance"]["formula_version"] == "sec_metrics_v2"
    assert "price_source" in payload["series"][0]["provenance"]
    assert payload["series"][0]["provenance"]["price_source"] == "yahoo_finance"
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

    with _client() as client:
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


def test_metrics_timeseries_endpoint_hides_price_fields_in_strict_mode(monkeypatch):
    snapshot = _snapshot()
    snapshot.company.sector = "prepackaged software"
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(strict_official_mode=True))
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "get_company_price_history",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("price history should be hidden in strict mode")),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_price_cache_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("price cache should be hidden in strict mode")),
    )
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "build_metrics_timeseries",
        lambda *_args, **_kwargs: [
            {
                "cadence": "ttm",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "filing_type": "TTM",
                "metrics": {
                    "revenue_growth": 0.12,
                    "gross_margin": 0.42,
                    "buyback_yield": 0.03,
                },
                "provenance": {
                    "statement_type": "canonical_xbrl",
                    "statement_source": "https://data.sec.gov/example",
                    "price_source": "yahoo_finance",
                    "formula_version": "sec_metrics_v2",
                },
                "quality": {
                    "available_metrics": 3,
                    "missing_metrics": [],
                    "coverage_ratio": 0.2,
                    "flags": [],
                },
            }
        ],
    )

    with _client() as client:
        response = client.get("/api/companies/AAPL/metrics-timeseries?cadence=ttm&max_points=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["strict_official_mode"] is True
    assert payload["company"]["market_sector"] == "Technology"
    assert payload["last_price_check"] is None
    assert payload["series"][0]["provenance"]["price_source"] is None
    assert {entry["source_id"] for entry in payload["provenance"]} == {"ft_derived_metrics_engine", "sec_edgar"}
    assert payload["source_mix"]["fallback_source_ids"] == []
    assert "strict_official_mode" in payload["confidence_flags"]


def test_metrics_timeseries_endpoint_prefers_regulated_bank_statements(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _bank_snapshot())
    monkeypatch.setattr(
        main_module,
        "get_company_financials",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                statement_type="canonical_xbrl",
                filing_type="10-K",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
                source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000072971.json",
                last_updated=datetime.now(timezone.utc),
                data={"revenue": 1.0},
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_regulated_bank_financials",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                statement_type="canonical_bank_regulatory",
                filing_type="CALL",
                period_start=date(2025, 10, 1),
                period_end=date(2025, 12, 31),
                source="https://api.fdic.gov/banks/financials",
                last_updated=datetime.now(timezone.utc),
                data={"net_interest_margin": 0.038},
            )
        ],
    )
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="WFC", job_id=None),
    )
    observed: dict[str, object] = {}

    def _build_metrics_timeseries(statements, *_args, **_kwargs):
        observed["statement_types"] = [statement.statement_type for statement in statements]
        return [
            {
                "cadence": "ttm",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "filing_type": "TTM",
                "metrics": {
                    "net_interest_margin": 0.038,
                },
                "provenance": {
                    "statement_type": "canonical_bank_regulatory",
                    "statement_source": "https://api.fdic.gov/banks/financials",
                    "price_source": None,
                    "formula_version": "sec_metrics_v2",
                },
                "quality": {
                    "available_metrics": 1,
                    "missing_metrics": [],
                    "coverage_ratio": 1.0,
                    "flags": [],
                },
            }
        ]

    monkeypatch.setattr(main_module, "build_metrics_timeseries", _build_metrics_timeseries)

    with _client() as client:
        response = client.get("/api/companies/WFC/metrics-timeseries?cadence=ttm&max_points=10")

    assert response.status_code == 200
    payload = response.json()
    assert observed["statement_types"] == ["canonical_bank_regulatory"]
    assert payload["company"]["regulated_entity"]["issuer_type"] == "bank"
    assert payload["series"][0]["metrics"]["net_interest_margin"] == 0.038
    assert {entry["source_id"] for entry in payload["provenance"]} == {"fdic_bankfind_financials", "ft_derived_metrics_engine"}
