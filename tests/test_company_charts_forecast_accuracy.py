from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import app.main as main_module
from app.models.company_charts_dashboard_snapshot import CompanyChartsDashboardSnapshot
from app.services import company_charts_dashboard as charts_service


def _annual_statement(
    fiscal_year: int,
    *,
    revenue: float,
    operating_income: float,
    eps: float,
    free_cash_flow: float,
    acceptance: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        period_end=date(fiscal_year, 12, 31),
        filing_type="10-K",
        filing_acceptance_at=acceptance,
        last_checked=acceptance,
        data={
            "revenue": revenue,
            "operating_income": operating_income,
            "net_income": eps * 100,
            "eps": eps,
            "free_cash_flow": free_cash_flow,
            "weighted_average_diluted_shares": 100.0,
        },
    )


def test_forecast_accuracy_enforces_point_in_time_statement_visibility(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        cik="0000123456",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )

    # Descending order mirrors cache query ordering.
    statements = [
        _annual_statement(2025, revenue=133.0, operating_income=22.0, eps=2.2, free_cash_flow=18.0, acceptance=datetime(2026, 2, 10, tzinfo=timezone.utc)),
        _annual_statement(2024, revenue=120.0, operating_income=20.0, eps=2.0, free_cash_flow=16.0, acceptance=datetime(2025, 2, 10, tzinfo=timezone.utc)),
        _annual_statement(2023, revenue=999.0, operating_income=60.0, eps=6.0, free_cash_flow=55.0, acceptance=datetime(2026, 1, 25, tzinfo=timezone.utc)),
        _annual_statement(2023, revenue=100.0, operating_income=15.0, eps=1.5, free_cash_flow=12.0, acceptance=datetime(2024, 2, 10, tzinfo=timezone.utc)),
        _annual_statement(2022, revenue=90.0, operating_income=12.0, eps=1.2, free_cash_flow=10.0, acceptance=datetime(2023, 2, 10, tzinfo=timezone.utc)),
    ]

    class _Session:
        def get(self, _model, _company_id):
            return company

    observed_visible_snapshots: list[tuple[int, list[float]]] = []

    def _fake_forecast_state(annuals, *_args, **_kwargs):
        observed_visible_snapshots.append((annuals[-1].period_end.year, [float(statement.data["revenue"]) for statement in annuals]))
        return {"anchor_year": annuals[-1].period_end.year}

    def _fake_forecast_metric_value_for_year(forecast_state, metric, fiscal_year):
        if fiscal_year != forecast_state["anchor_year"] + 1:
            return None
        return {
            "revenue": 130.0,
            "operating_income": 21.0,
            "eps": 2.1,
            "free_cash_flow": 17.0,
        }[metric]

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 1, tzinfo=timezone.utc)))
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "_build_forecast_state", _fake_forecast_state)
    monkeypatch.setattr(charts_service, "_forecast_metric_value_for_year", _fake_forecast_metric_value_for_year)

    response = charts_service.build_company_charts_forecast_accuracy_response(_Session(), 1)

    assert response is not None
    # For the 2024 anchor snapshot (cutoff before the 2026 restatement), 2023 must remain 100.0.
    anchor_2024_windows = [window for anchor_year, window in observed_visible_snapshots if anchor_year == 2024]
    assert anchor_2024_windows
    assert anchor_2024_windows[0][-2] == 100.0


def test_forecast_accuracy_returns_insufficient_history_when_history_is_thin(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        cik="0000123456",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )

    statements = [
        _annual_statement(2024, revenue=120.0, operating_income=20.0, eps=2.0, free_cash_flow=16.0, acceptance=datetime(2025, 2, 10, tzinfo=timezone.utc)),
        _annual_statement(2023, revenue=100.0, operating_income=15.0, eps=1.5, free_cash_flow=12.0, acceptance=datetime(2024, 2, 10, tzinfo=timezone.utc)),
    ]

    class _Session:
        def get(self, _model, _company_id):
            return company

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 1, tzinfo=timezone.utc)))
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_forecast_accuracy_response(_Session(), 1)

    assert response is not None
    assert response.status == "insufficient_history"
    assert response.aggregate.sample_count == 0
    assert response.insufficient_history_reason is not None


def test_forecast_accuracy_schema_version_fits_snapshot_column() -> None:
    schema_version_length = CompanyChartsDashboardSnapshot.__table__.c.schema_version.type.length
    assert schema_version_length is not None
    assert len(charts_service.CHARTS_DASHBOARD_SCHEMA_VERSION) <= schema_version_length
    assert len(charts_service.CHARTS_FORECAST_ACCURACY_SCHEMA_VERSION) <= schema_version_length


def test_forecast_accuracy_aggregate_metrics_are_mathematically_consistent(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        cik="0000123456",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )

    statements = [
        _annual_statement(2025, revenue=133.0, operating_income=22.0, eps=2.2, free_cash_flow=18.0, acceptance=datetime(2026, 2, 10, tzinfo=timezone.utc)),
        _annual_statement(2024, revenue=120.0, operating_income=20.0, eps=2.0, free_cash_flow=16.0, acceptance=datetime(2025, 2, 10, tzinfo=timezone.utc)),
        _annual_statement(2023, revenue=100.0, operating_income=15.0, eps=1.5, free_cash_flow=12.0, acceptance=datetime(2024, 2, 10, tzinfo=timezone.utc)),
    ]

    class _Session:
        def get(self, _model, _company_id):
            return company

    fixed_samples = [
        charts_service.CompanyChartsForecastAccuracySamplePayload(
            metric_key="revenue",
            metric_label="Revenue",
            unit="usd",
            anchor_fiscal_year=2023,
            target_fiscal_year=2024,
            cutoff_as_of="2024-02-10T00:00:00+00:00",
            predicted_value=110.0,
            actual_value=120.0,
            absolute_error=10.0,
            absolute_percentage_error=0.083333,
            directionally_correct=True,
        ),
        charts_service.CompanyChartsForecastAccuracySamplePayload(
            metric_key="revenue",
            metric_label="Revenue",
            unit="usd",
            anchor_fiscal_year=2024,
            target_fiscal_year=2025,
            cutoff_as_of="2025-02-10T00:00:00+00:00",
            predicted_value=126.0,
            actual_value=133.0,
            absolute_error=7.0,
            absolute_percentage_error=0.052632,
            directionally_correct=True,
        ),
        charts_service.CompanyChartsForecastAccuracySamplePayload(
            metric_key="eps",
            metric_label="Diluted EPS",
            unit="usd_per_share",
            anchor_fiscal_year=2023,
            target_fiscal_year=2024,
            cutoff_as_of="2024-02-10T00:00:00+00:00",
            predicted_value=1.6,
            actual_value=2.0,
            absolute_error=0.4,
            absolute_percentage_error=0.2,
            directionally_correct=True,
        ),
        charts_service.CompanyChartsForecastAccuracySamplePayload(
            metric_key="eps",
            metric_label="Diluted EPS",
            unit="usd_per_share",
            anchor_fiscal_year=2024,
            target_fiscal_year=2025,
            cutoff_as_of="2025-02-10T00:00:00+00:00",
            predicted_value=1.8,
            actual_value=2.2,
            absolute_error=0.4,
            absolute_percentage_error=0.181818,
            directionally_correct=False,
        ),
    ]

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 1, tzinfo=timezone.utc)))
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "_build_forecast_accuracy_samples", lambda *_args, **_kwargs: fixed_samples)

    response = charts_service.build_company_charts_forecast_accuracy_response(_Session(), 1)

    assert response is not None
    assert response.status == "ok"
    revenue_metric = next(metric for metric in response.metrics if metric.key == "revenue")
    eps_metric = next(metric for metric in response.metrics if metric.key == "eps")
    assert revenue_metric.sample_count == 2
    assert revenue_metric.mean_absolute_error == 8.5
    assert revenue_metric.directional_accuracy == 1.0
    assert eps_metric.sample_count == 2
    assert eps_metric.directional_accuracy == 0.5
    assert response.aggregate.sample_count == 4
    assert response.aggregate.directional_sample_count == 4
    assert response.aggregate.directional_accuracy == 0.75


def test_company_charts_forecast_accuracy_route_returns_response_shape(monkeypatch):
    snapshot = SimpleNamespace(
        company=SimpleNamespace(
            id=1,
            ticker="ACME",
            cik="0000123456",
            name="Acme Corp",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software",
        ),
        cache_state="fresh",
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    payload = charts_service.CompanyChartsForecastAccuracyResponse(
        company=main_module._serialize_company(snapshot),
        status="ok",
        insufficient_history_reason=None,
        max_backtests=6,
        metrics=[],
        aggregate=charts_service.CompanyChartsForecastAccuracyAggregatePayload(
            snapshot_count=2,
            sample_count=4,
            directional_sample_count=4,
            mean_absolute_percentage_error=0.12,
            directional_accuracy=0.75,
        ),
        samples=[],
        refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        main_module,
        "_load_company_charts_forecast_accuracy_snapshot_record",
        lambda *_args, **_kwargs: (
            SimpleNamespace(last_checked=datetime(2026, 4, 11, tzinfo=timezone.utc), last_updated=datetime(2026, 4, 11, tzinfo=timezone.utc)),
            payload,
        ),
    )
    monkeypatch.setattr(
        main_module,
        "_refresh_for_company_charts_forecast_accuracy",
        lambda *_args, **_kwargs: main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
    )
    monkeypatch.setattr(main_module.shared_hot_response_cache, "get_sync", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module.shared_hot_response_cache, "store_sync", lambda *_args, **_kwargs: None)

    response = main_module.company_charts_forecast_accuracy("ACME", as_of=None, session=object())

    assert response.status == "ok"
    assert response.aggregate.snapshot_count == 2
    assert response.company is not None
    assert response.company.ticker == "ACME"


def test_company_charts_forecast_accuracy_route_triggers_stale_refresh_but_serves_cached_snapshot(monkeypatch):
    snapshot = SimpleNamespace(
        company=SimpleNamespace(
            id=1,
            ticker="ACME",
            cik="0000123456",
            name="Acme Corp",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software",
        ),
        cache_state="fresh",
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    payload = charts_service.CompanyChartsForecastAccuracyResponse(
        company=main_module._serialize_company(snapshot),
        status="ok",
        insufficient_history_reason=None,
        max_backtests=6,
        metrics=[],
        aggregate=charts_service.CompanyChartsForecastAccuracyAggregatePayload(snapshot_count=1, sample_count=2, directional_sample_count=2),
        samples=[],
        refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        main_module,
        "_load_company_charts_forecast_accuracy_snapshot_record",
        lambda *_args, **_kwargs: (
            SimpleNamespace(last_checked=datetime(2026, 4, 11, tzinfo=timezone.utc), last_updated=datetime(2026, 4, 11, tzinfo=timezone.utc)),
            payload,
        ),
    )
    monkeypatch.setattr(
        main_module,
        "_refresh_for_company_charts_forecast_accuracy",
        lambda *_args, **_kwargs: main_module.RefreshState(triggered=True, reason="stale", ticker="ACME", job_id="job-forecast-accuracy-stale"),
    )
    monkeypatch.setattr(main_module.shared_hot_response_cache, "get_sync", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module.shared_hot_response_cache, "store_sync", lambda *_args, **_kwargs: None)

    response = main_module.company_charts_forecast_accuracy("ACME", as_of=None, session=object())

    assert response.status == "ok"
    assert response.refresh.triggered is True
    assert response.refresh.reason == "stale"
    assert response.refresh.job_id == "job-forecast-accuracy-stale"


def test_company_charts_forecast_accuracy_route_recomputes_inline_when_snapshot_missing(monkeypatch):
    snapshot = SimpleNamespace(
        company=SimpleNamespace(
            id=1,
            ticker="ACME",
            cik="0000123456",
            name="Acme Corp",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software",
        ),
        cache_state="fresh",
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    generated_payload = charts_service.CompanyChartsForecastAccuracyResponse(
        company=main_module._serialize_company(snapshot),
        status="ok",
        insufficient_history_reason=None,
        max_backtests=6,
        metrics=[],
        aggregate=charts_service.CompanyChartsForecastAccuracyAggregatePayload(snapshot_count=2, sample_count=4, directional_sample_count=4),
        samples=[],
        refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )

    class _Session:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

        def execute(self, *_args, **_kwargs):
            return None

    session = _Session()

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_load_company_charts_forecast_accuracy_snapshot_record", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(main_module, "recompute_and_persist_company_charts_forecast_accuracy", lambda *_args, **_kwargs: generated_payload)
    monkeypatch.setattr(main_module, "_refresh_for_company_charts_forecast_accuracy", lambda *_args, **_kwargs: main_module.RefreshState(triggered=True, reason="missing", ticker="ACME", job_id="job-missing"))
    monkeypatch.setattr(main_module.shared_hot_response_cache, "get_sync", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module.shared_hot_response_cache, "store_sync", lambda *_args, **_kwargs: None)

    response = main_module.company_charts_forecast_accuracy("ACME", as_of=None, session=session)

    assert response.status == "ok"
    assert response.refresh.triggered is False
    assert response.refresh.reason == "fresh"
    assert session.commits == 1


def test_company_charts_forecast_accuracy_route_uses_hot_cache_when_fresh(monkeypatch):
    snapshot = SimpleNamespace(
        company=SimpleNamespace(
            id=1,
            ticker="ACME",
            cik="0000123456",
            name="Acme Corp",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software",
        ),
        cache_state="fresh",
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    payload = charts_service.CompanyChartsForecastAccuracyResponse(
        company=main_module._serialize_company(snapshot),
        status="ok",
        insufficient_history_reason=None,
        max_backtests=6,
        metrics=[],
        aggregate=charts_service.CompanyChartsForecastAccuracyAggregatePayload(snapshot_count=2, sample_count=4, directional_sample_count=4),
        samples=[],
        refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )
    encoded_payload = json.dumps(payload.model_dump(mode="json"))
    hot_lookup = SimpleNamespace(is_fresh=True, content=encoded_payload, etag='"etag"', last_modified=None)

    monkeypatch.setattr(main_module.shared_hot_response_cache, "get_sync", lambda *_args, **_kwargs: hot_lookup)

    response = main_module.company_charts_forecast_accuracy("ACME", as_of=None, session=object())

    assert response.status == "ok"
    assert response.aggregate.sample_count == 4


def test_forecast_accuracy_refresh_detects_sources_newer_than_snapshot(monkeypatch):
    snapshot = SimpleNamespace(
        company=SimpleNamespace(id=1, ticker="ACME"),
        cache_state="fresh",
    )
    stored_snapshot = SimpleNamespace(
        last_checked=datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc),
        last_updated=datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc),
    )

    class _Session:
        def execute(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(main_module, "_snapshot_last_checked_is_fresh", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        main_module,
        "get_dataset_last_checked",
        lambda _session, _company_id, dataset: datetime(2026, 4, 11, 0, 0, tzinfo=timezone.utc)
        if dataset == "financials"
        else datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda ticker, reason: main_module.RefreshState(triggered=True, reason=reason, ticker=ticker, job_id="job-stale"),
    )

    refresh = main_module._refresh_for_company_charts_forecast_accuracy(
        _Session(),
        snapshot,
        stored_snapshot=stored_snapshot,
        as_of=None,
    )

    assert refresh.triggered is True
    assert refresh.reason == "stale"
    assert refresh.job_id == "job-stale"
