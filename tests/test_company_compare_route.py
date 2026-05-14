from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.db import get_db_session
from app.main import RefreshState, app


def _snapshot(ticker: str, company_id: int = 1):
    company = SimpleNamespace(
        id=company_id,
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
    monkeypatch.setattr(
        main_module,
        "get_company_snapshots_by_ticker",
        lambda _session, tickers: {ticker: _snapshot(ticker) for ticker in tickers},
    )
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


def test_company_compare_route_uses_preload_for_max_allowed_tickers(monkeypatch):
    tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
    snapshots = {ticker: _snapshot(ticker, company_id=index + 1) for index, ticker in enumerate(tickers)}
    now = datetime.now(timezone.utc)
    preload_calls: list[list[str]] = []

    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda _session, requested: {ticker: snapshots[ticker] for ticker in requested})

    def _preload(_session, snapshots_by_ticker, **_kwargs):
        preload_calls.append(list(snapshots_by_ticker))
        return {
            "financials_by_company_id": {
                snapshot.company.id: [_financial(date(2025, 12, 31))]
                for snapshot in snapshots.values()
            },
            "price_cache_status_by_company_id": {
                snapshot.company.id: (now, "fresh")
                for snapshot in snapshots.values()
            },
            "price_history_by_company_id": {
                snapshot.company.id: []
                for snapshot in snapshots.values()
            },
            "metric_rows_by_company_id": {
                snapshot.company.id: [_metric("gross_margin", 0.45)]
                for snapshot in snapshots.values()
            },
            "last_metrics_check_by_company_id": {
                snapshot.company.id: now
                for snapshot in snapshots.values()
            },
            "model_runs_by_company_id": {
                snapshot.company.id: {
                    "dcf": {
                        "model_name": "dcf",
                        "model_version": "test",
                        "created_at": now,
                        "input_periods": {},
                        "result": {"fair_value_per_share": 123.0},
                    }
                }
                for snapshot in snapshots.values()
            },
        }

    monkeypatch.setattr(main_module, "_load_company_compare_preload", _preload)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    for name in [
        "_visible_financials_for_company",
        "_visible_price_cache_status",
        "_visible_price_history",
        "get_company_derived_metric_points",
        "get_company_derived_metrics_last_checked",
        "get_company_models",
    ]:
        monkeypatch.setattr(
            main_module,
            name,
            lambda *_args, _name=name, **_kwargs: (_ for _ in ()).throw(AssertionError(f"{_name} should use preload")),
        )

    with _client() as client:
        response = client.get(f"/api/companies/compare?tickers={','.join(tickers)}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == tickers
    assert [company["financials"]["company"]["ticker"] for company in payload["companies"]] == tickers
    assert preload_calls == [tickers]


def test_company_compare_route_keeps_unknown_tickers_as_missing(monkeypatch):
    known_snapshot = _snapshot("AAPL")
    now = datetime.now(timezone.utc)

    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda _session, _tickers: {"AAPL": known_snapshot})
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda _session, ticker: known_snapshot if ticker == "AAPL" else None)
    monkeypatch.setattr(main_module, "_visible_financials_for_company", lambda *_args, **_kwargs: [_financial(date(2025, 12, 31))])
    monkeypatch.setattr(main_module, "_visible_price_cache_status", lambda *_args, **_kwargs: (now, "fresh"))
    monkeypatch.setattr(main_module, "_visible_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(main_module, "get_company_derived_metric_points", lambda *_args, **_kwargs: [_metric("gross_margin", 0.45)])
    monkeypatch.setattr(main_module, "get_company_derived_metrics_last_checked", lambda *_args, **_kwargs: now)
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_trigger_refresh", lambda ticker, **_kwargs: RefreshState(triggered=True, reason="missing", ticker=ticker, job_id="job-missing"))

    with _client() as client:
        response = client.get("/api/companies/compare?tickers=AAPL,UNKNOWN")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["AAPL", "UNKNOWN"]
    assert payload["companies"][0]["financials"]["company"]["ticker"] == "AAPL"
    assert payload["companies"][1]["financials"]["company"] is None
    assert payload["companies"][1]["financials"]["refresh"]["reason"] == "missing"


def test_company_compare_preload_failure_falls_back_to_per_company_helpers(monkeypatch):
    snapshot = _snapshot("AAPL")
    now = datetime.now(timezone.utc)
    fallback_calls = {
        "financials": 0,
        "prices": 0,
        "metrics": 0,
        "models": 0,
    }

    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda _session, _tickers: {"AAPL": snapshot})
    monkeypatch.setattr(main_module, "_load_company_compare_preload", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("preload unavailable")))

    def _financials(*_args, **_kwargs):
        fallback_calls["financials"] += 1
        return [_financial(date(2025, 12, 31))]

    def _price_status(*_args, **_kwargs):
        fallback_calls["prices"] += 1
        return now, "fresh"

    def _metrics(*_args, **_kwargs):
        fallback_calls["metrics"] += 1
        return [_metric("gross_margin", 0.45)]

    def _models(*_args, **_kwargs):
        fallback_calls["models"] += 1
        return []

    monkeypatch.setattr(main_module, "_visible_financials_for_company", _financials)
    monkeypatch.setattr(main_module, "_visible_price_cache_status", _price_status)
    monkeypatch.setattr(main_module, "_visible_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(main_module, "get_company_derived_metric_points", _metrics)
    monkeypatch.setattr(main_module, "get_company_derived_metrics_last_checked", lambda *_args, **_kwargs: now)
    monkeypatch.setattr(main_module, "get_company_models", _models)

    with _client() as client:
        response = client.get("/api/companies/compare?tickers=AAPL")

    assert response.status_code == 200
    assert response.json()["companies"][0]["financials"]["company"]["ticker"] == "AAPL"
    assert fallback_calls == {
        "financials": 1,
        "prices": 1,
        "metrics": 1,
        "models": 1,
    }


def test_company_compare_preload_uses_batch_as_of_price_history(monkeypatch):
    snapshot = _snapshot("AAPL")
    parsed_as_of = datetime(2025, 6, 30, tzinfo=timezone.utc)
    calls: list[tuple[list[int], datetime]] = []

    monkeypatch.setattr(main_module, "_visible_financials_by_company_ids", lambda *_args, **_kwargs: {snapshot.company.id: [_financial(date(2025, 12, 31))]})
    monkeypatch.setattr(main_module, "get_company_price_cache_status_by_company_ids", lambda *_args, **_kwargs: {snapshot.company.id: (parsed_as_of, "fresh")})
    monkeypatch.setattr(
        main_module,
        "get_company_price_history_by_company_ids",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("as_of compare should not load unbounded price history")),
    )

    def _price_history_as_of(_session, company_ids, as_of):
        calls.append((list(company_ids), as_of))
        return {snapshot.company.id: []}

    monkeypatch.setattr(main_module, "get_company_price_history_by_company_ids_as_of", _price_history_as_of)

    preload = main_module._load_company_compare_preload(
        SimpleNamespace(execute=lambda *_args, **_kwargs: None),
        {"AAPL": snapshot},
        parsed_as_of=parsed_as_of,
        requested_models=[],
    )

    assert preload is not None
    assert preload["price_history_by_company_id"] == {snapshot.company.id: []}
    assert calls == [([snapshot.company.id], parsed_as_of)]


def test_company_compare_item_uses_preloaded_batch_data(monkeypatch):
    snapshot = _snapshot("AAPL")
    financial = _financial(date(2025, 12, 31))
    metrics = [_metric("gross_margin", 0.45), _metric("operating_margin", 0.2)]
    model_runs = {
        "dcf": {
            "model_name": "dcf",
            "model_version": "test",
            "created_at": datetime.now(timezone.utc),
            "input_periods": {},
            "result": {"fair_value_per_share": 123.0},
        },
        "piotroski": {
            "model_name": "piotroski",
            "model_version": "test",
            "created_at": datetime.now(timezone.utc),
            "input_periods": {},
            "result": {"score": 7.0, "score_max": 9.0, "available_criteria": 9.0},
        },
        "altman_z": {
            "model_name": "altman_z",
            "model_version": "test",
            "created_at": datetime.now(timezone.utc),
            "input_periods": {},
            "result": {"z_score_approximate": 3.8},
        },
    }

    for name in [
        "get_company_financials",
        "get_company_price_cache_status",
        "get_company_price_history",
        "get_company_derived_metric_points",
        "get_company_derived_metrics_last_checked",
        "get_company_models",
    ]:
        monkeypatch.setattr(
            main_module,
            name,
            lambda *_args, _name=name, **_kwargs: (_ for _ in ()).throw(AssertionError(f"{_name} should be preloaded")),
        )

    token = main_module._company_compare_preload_ctx.set(
        {
            "financials_by_company_id": {snapshot.company.id: [financial]},
            "price_cache_status_by_company_id": {snapshot.company.id: (datetime.now(timezone.utc), "fresh")},
            "price_history_by_company_id": {snapshot.company.id: []},
            "metric_rows_by_company_id": {snapshot.company.id: metrics},
            "last_metrics_check_by_company_id": {snapshot.company.id: datetime.now(timezone.utc)},
            "model_runs_by_company_id": {snapshot.company.id: model_runs},
        }
    )
    try:
        item = main_module._build_company_compare_item(
            object(),
            "AAPL",
            requested_as_of=None,
            parsed_as_of=None,
            snapshot=snapshot,
        )
    finally:
        main_module._company_compare_preload_ctx.reset(token)

    assert item.financials.company.ticker == "AAPL"
    assert item.metrics_summary.metrics[0].metric_key == "gross_margin"
    assert item.models.models[0].model_name == "dcf"
