from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import RefreshState, app
from app.services import peer_comparison as peer_module


def _snapshot(company_id: int, ticker: str) -> SimpleNamespace:
    company = SimpleNamespace(
        id=company_id,
        ticker=ticker,
        cik=f"{company_id:010d}",
        name=f"{ticker} Corp.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc))


def _statement(statement_id: int, acceptance_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id=statement_id,
        filing_type="10-K",
        statement_type="canonical_xbrl",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        source="https://data.sec.gov/api/xbrl/companyfacts/example.json",
        last_updated=acceptance_at,
        filing_acceptance_at=acceptance_at,
        fetch_timestamp=acceptance_at,
        last_checked=acceptance_at,
        data={
            "revenue": float(statement_id),
            "net_income": 10.0,
            "operating_income": 8.0,
            "free_cash_flow": 7.0,
            "eps": 2.0,
            "shares_outstanding": 5.0,
            "total_liabilities": 3.0,
            "segment_breakdown": [],
        },
    )


def _price(trade_date: date, close: float) -> SimpleNamespace:
    observed_at = datetime.combine(trade_date, datetime.max.time(), tzinfo=timezone.utc)
    return SimpleNamespace(
        id=int(trade_date.strftime("%d")),
        company_id=1,
        trade_date=trade_date,
        close=close,
        volume=1_000,
        source="yahoo_finance",
        last_updated=observed_at,
        fetch_timestamp=observed_at,
    )


def test_models_endpoint_filters_future_inputs_for_as_of(monkeypatch):
    snapshot = _snapshot(1, "AAPL")
    past_statement = _statement(1, datetime(2025, 1, 15, tzinfo=timezone.utc))
    future_statement = _statement(2, datetime(2025, 3, 15, tzinfo=timezone.utc))
    past_price = _price(date(2025, 1, 31), 100.0)
    future_price = _price(date(2025, 3, 1), 150.0)
    observed: dict[str, object] = {}

    class _FakeModelEngine:
        def __init__(self, _session):
            pass

        def compute_models(self, *_args, **_kwargs):
            raise AssertionError("cached model path should not run for as_of requests")

        def evaluate_models(self, dataset, **_kwargs):
            observed["statement_ids"] = [point.statement_id for point in dataset.financials]
            observed["price_date"] = dataset.market_snapshot.price_date if dataset.market_snapshot is not None else None
            observed["as_of_date"] = dataset.as_of_date
            return [
                {
                    "model_name": "dcf",
                    "model_version": "v2",
                    "created_at": datetime(2026, 3, 22, tzinfo=timezone.utc),
                    "input_periods": {"period_end": "2024-12-31"},
                    "result": {
                        "model_status": "ok",
                        "base_period_end": "2024-12-31",
                        "price_snapshot": {
                            "price_date": "2025-01-31",
                            "price_source": "yahoo_finance",
                        },
                    },
                }
            ]

    monkeypatch.setattr(main_module, "ModelEngine", _FakeModelEngine)
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_refresh_for_snapshot", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None))
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [future_statement, past_statement])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [past_price, future_price])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/models?as_of=2025-02-01")

    assert response.status_code == 200
    assert observed["statement_ids"] == [1]
    assert observed["price_date"] == date(2025, 1, 31)
    assert observed["as_of_date"] == date(2025, 2, 1)
    assert response.json()["as_of"] == "2025-02-01"


def test_metrics_endpoint_filters_future_inputs_for_as_of(monkeypatch):
    snapshot = _snapshot(1, "AAPL")
    past_statement = _statement(1, datetime(2025, 1, 15, tzinfo=timezone.utc))
    future_statement = _statement(2, datetime(2025, 3, 15, tzinfo=timezone.utc))
    past_price = _price(date(2025, 1, 31), 100.0)
    future_price = _price(date(2025, 3, 1), 150.0)
    observed: dict[str, object] = {}

    def _build_points(financials, prices):
        observed["statement_ids"] = [statement.id for statement in financials]
        observed["price_dates"] = [point.trade_date for point in prices]
        return [
            {
                "period_type": "ttm",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 12, 31),
                "filing_type": "TTM",
                "metric_key": "revenue_growth",
                "metric_value": 0.1,
                "is_proxy": False,
                "provenance": {
                    "formula_version": "sec_metrics_mart_v1",
                    "statement_source": "sec_companyfacts",
                    "price_source": "yahoo_finance",
                },
                "quality_flags": [],
            }
        ]

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [future_statement, past_statement])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [past_price, future_price])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "_refresh_for_financial_page", lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None))
    monkeypatch.setattr(main_module, "build_derived_metric_points", _build_points)
    monkeypatch.setattr(main_module, "get_company_derived_metric_points", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mart path should not run for as_of requests")))

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/metrics?period_type=ttm&as_of=2025-02-01")

    assert response.status_code == 200
    assert observed["statement_ids"] == [1]
    assert observed["price_dates"] == [date(2025, 1, 31)]
    payload = response.json()
    assert payload["as_of"] == "2025-02-01"
    assert {entry["source_id"] for entry in payload["provenance"]} == {"ft_derived_metrics_engine", "sec_companyfacts", "yahoo_finance"}


def test_peer_comparison_filters_future_inputs_for_as_of(monkeypatch):
    focus_snapshot = _snapshot(1, "AAPL")
    peer_snapshot = _snapshot(2, "MSFT")
    focus_past_statement = _statement(1, datetime(2025, 1, 15, tzinfo=timezone.utc))
    focus_future_statement = _statement(2, datetime(2025, 3, 15, tzinfo=timezone.utc))
    peer_past_statement = _statement(3, datetime(2025, 1, 20, tzinfo=timezone.utc))
    peer_future_statement = _statement(4, datetime(2025, 3, 20, tzinfo=timezone.utc))
    focus_past_price = SimpleNamespace(**{**_price(date(2025, 1, 31), 100.0).__dict__, "company_id": 1})
    focus_future_price = SimpleNamespace(**{**_price(date(2025, 3, 1), 150.0).__dict__, "company_id": 1})
    peer_past_price = SimpleNamespace(**{**_price(date(2025, 1, 31), 200.0).__dict__, "company_id": 2})
    peer_future_price = SimpleNamespace(**{**_price(date(2025, 3, 1), 250.0).__dict__, "company_id": 2})
    observed: list[tuple[str, list[int], date | None, date | None]] = []

    class _FakePeerModelEngine:
        def __init__(self, _session):
            pass

        def compute_models(self, *_args, **_kwargs):
            raise AssertionError("cached peer model path should not run for as_of requests")

        def evaluate_models(self, dataset, **_kwargs):
            observed.append(
                (
                    dataset.ticker,
                    [point.statement_id for point in dataset.financials],
                    dataset.market_snapshot.price_date if dataset.market_snapshot is not None else None,
                    dataset.as_of_date,
                )
            )
            return [
                {
                    "model_name": "dcf",
                    "model_version": "v2",
                    "created_at": datetime(2026, 3, 22, tzinfo=timezone.utc),
                    "input_periods": {"period_end": "2024-12-31"},
                    "result": {"model_status": "ok", "fair_value_per_share": 110.0},
                },
                {
                    "model_name": "reverse_dcf",
                    "model_version": "v2",
                    "created_at": datetime(2026, 3, 22, tzinfo=timezone.utc),
                    "input_periods": {"period_end": "2024-12-31"},
                    "result": {"model_status": "ok", "implied_growth": 0.05},
                },
            ]

    monkeypatch.setattr(peer_module, "ModelEngine", _FakePeerModelEngine)
    monkeypatch.setattr(peer_module, "get_company_snapshot", lambda *_args, **_kwargs: focus_snapshot)
    monkeypatch.setattr(peer_module, "_load_peer_snapshots", lambda *_args, **_kwargs: [peer_snapshot])
    monkeypatch.setattr(
        peer_module,
        "_load_financials_for_companies",
        lambda *_args, **_kwargs: {
            1: [focus_future_statement, focus_past_statement],
            2: [peer_future_statement, peer_past_statement],
        },
    )
    monkeypatch.setattr(
        peer_module,
        "_load_price_history_for_companies",
        lambda *_args, **_kwargs: {
            1: [focus_past_price, focus_future_price],
            2: [peer_past_price, peer_future_price],
        },
    )

    payload = peer_module.build_peer_comparison(None, "AAPL", as_of=datetime(2025, 2, 1, tzinfo=timezone.utc))

    assert payload is not None
    assert observed == [
        ("AAPL", [1], date(2025, 1, 31), date(2025, 2, 1)),
        ("MSFT", [3], date(2025, 1, 31), date(2025, 2, 1)),
    ]
    assert all(row["price_date"] == date(2025, 1, 31) for row in payload["peers"])