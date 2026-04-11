from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.db import get_db_session
from app.main import RefreshState, app


def _snapshot(ticker: str):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik="0000320193",
        name=f"{ticker} Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )
    return SimpleNamespace(company=company, cache_state="stale", last_checked=datetime.now(timezone.utc))


def _financial(period_end: date):
    return SimpleNamespace(
        filing_type="10-K",
        statement_type="annual",
        period_start=date(period_end.year - 1, 1, 1),
        period_end=period_end,
        source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        last_updated=datetime.now(timezone.utc),
        last_checked=datetime.now(timezone.utc),
        data={
            "revenue": 100.0,
            "operating_income": 20.0,
            "net_income": 15.0,
            "free_cash_flow": 18.0,
            "segment_breakdown": [],
        },
        reconciliation=None,
    )


def _metric(metric_key: str, metric_value: float):
    return SimpleNamespace(
        period_type="ttm",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        filing_type="TTM",
        metric_key=metric_key,
        metric_value=metric_value,
        is_proxy=False,
        provenance={
            "formula_version": "sec_metrics_mart_v1",
            "unit": "ratio",
            "statement_source": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            "price_source": "yahoo_finance",
        },
        quality_flags=[],
    )


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_company_compare_route_returns_batch_payload(monkeypatch):
    monkeypatch.setattr(main_module, "get_company_snapshot", lambda _session, ticker: _snapshot(ticker))
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda _session, ticker: _snapshot(ticker))
    monkeypatch.setattr(main_module, "_visible_financials_for_company", lambda *_args, **_kwargs: [_financial(date(2025, 12, 31))])
    monkeypatch.setattr(main_module, "_visible_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "_visible_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_derived_metric_points",
        lambda *_args, **_kwargs: [
            _metric("gross_margin", 0.45),
            _metric("operating_margin", 0.2),
        ],
    )
    monkeypatch.setattr(main_module, "get_company_derived_metrics_last_checked", lambda *_args, **_kwargs: datetime.now(timezone.utc))
    monkeypatch.setattr(
        main_module,
        "get_company_models",
        lambda *_args, **_kwargs: [
            {
                "model_name": "dcf",
                "model_version": "test",
                "created_at": datetime.now(timezone.utc),
                "input_periods": {},
                "result": {"fair_value_per_share": 123.0},
            },
            {
                "model_name": "piotroski",
                "model_version": "test",
                "created_at": datetime.now(timezone.utc),
                "input_periods": {},
                "result": {"score": 7.0, "score_max": 9.0, "available_criteria": 9.0},
            },
            {
                "model_name": "altman_z",
                "model_version": "test",
                "created_at": datetime.now(timezone.utc),
                "input_periods": {},
                "result": {"z_score_approximate": 3.8},
            },
        ],
    )

    with _client() as client:
        response = client.get("/api/companies/compare?tickers=AAPL,MSFT")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["AAPL", "MSFT"]
    assert len(payload["companies"]) == 2
    assert payload["companies"][0]["financials"]["company"]["ticker"] == "AAPL"
    assert payload["companies"][0]["metrics_summary"]["metrics"][0]["metric_key"] == "gross_margin"
    assert payload["companies"][0]["models"]["models"][0]["model_name"] == "dcf"