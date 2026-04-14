from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import app.services.cache_queries as cache_queries
import app.services.company_charts_dashboard as charts_service


def _revenue_point(year: int, value: float) -> charts_service.CompanyChartsSeriesPointPayload:
    return charts_service.CompanyChartsSeriesPointPayload(
        period_label=f"FY{year}",
        fiscal_year=year,
        period_end=date(year, 12, 31),
        value=value,
        series_kind="actual",
    )


def _forecast_revenue_point(year: int, value: float) -> charts_service.CompanyChartsSeriesPointPayload:
    return charts_service.CompanyChartsSeriesPointPayload(
        period_label=f"FY{year}E",
        fiscal_year=year,
        period_end=None,
        value=value,
        series_kind="forecast",
    )


def _series_point(
    year: int,
    value: float | None,
    *,
    kind: str = "actual",
) -> charts_service.CompanyChartsSeriesPointPayload:
    return charts_service.CompanyChartsSeriesPointPayload(
        period_label=f"FY{year}" if kind == "actual" else f"FY{year}E",
        fiscal_year=year,
        period_end=date(year, 12, 31) if kind == "actual" else None,
        value=value,
        series_kind=kind,
    )


def _statement(year: int, data: dict[str, float | None]) -> SimpleNamespace:
    return SimpleNamespace(
        period_end=date(year, 12, 31),
        filing_type="10-K",
        last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc),
        data=data,
    )


def _series_by_key(series: list[charts_service.CompanyChartsSeriesPayload], key: str) -> charts_service.CompanyChartsSeriesPayload:
    return next(item for item in series if item.key == key)


def _earnings_point(*, quality_score: float | None, drift: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc),
        quality_score=quality_score,
        earnings_momentum_drift=drift,
    )


def _earnings_model_row(
    year: int,
    *,
    quality_score: float | None,
    drift: float = 0.0,
    last_updated: datetime | None,
    last_checked: datetime | None = None,
) -> SimpleNamespace:
    observed_at = last_updated or last_checked or datetime(2026, 4, 12, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=year,
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        filing_type="10-K",
        quality_score=quality_score,
        earnings_momentum_drift=drift,
        last_updated=last_updated,
        last_checked=last_checked or observed_at,
    )


def _factor_by_key(response: charts_service.CompanyChartsDashboardResponse, key: str) -> charts_service.CompanyChartsFactorValuePayload:
    return next(item for item in response.factors.supporting if item.key == key)


def test_build_company_charts_dashboard_response_separates_actual_and_forecast(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        cik="0000123456",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))
    statements = [
        SimpleNamespace(period_end=date(2022, 12, 31), filing_type="10-K", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc), data={"revenue": 1000, "operating_income": 120, "net_income": 90, "operating_cash_flow": 160, "free_cash_flow": 110, "capex": 50, "eps": 1.2, "weighted_average_diluted_shares": 75}),
        SimpleNamespace(period_end=date(2023, 12, 31), filing_type="10-K", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc), data={"revenue": 1200, "operating_income": 156, "net_income": 118, "operating_cash_flow": 190, "free_cash_flow": 132, "capex": 58, "eps": 1.5, "weighted_average_diluted_shares": 79}),
        SimpleNamespace(period_end=date(2024, 12, 31), filing_type="10-K", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc), data={"revenue": 1500, "operating_income": 210, "net_income": 162, "operating_cash_flow": 245, "free_cash_flow": 180, "capex": 65, "eps": 1.95, "weighted_average_diluted_shares": 83}),
        SimpleNamespace(period_end=date(2025, 12, 31), filing_type="10-K", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc), data={"revenue": 1800, "operating_income": 270, "net_income": 207, "operating_cash_flow": 300, "free_cash_flow": 222, "capex": 78, "eps": 2.4, "weighted_average_diluted_shares": 86}),
    ]
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        charts_service,
        "get_company_earnings_model_points",
        lambda *_args, **_kwargs: [SimpleNamespace(last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc), quality_score=0.74, earnings_momentum_drift=0.11)],
    )

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.cards.revenue.series[0].points[0].series_kind == "actual"
    assert response.cards.revenue.series[1].points[0].series_kind == "forecast"
    assert {series.label for series in response.cards.revenue.series[1:]} == {"Base Forecast", "Bull Forecast", "Bear Forecast"}
    assert response.cards.revenue_growth.series[1].points[0].series_kind == "forecast"
    assert response.cards.eps.series[1].points[0].series_kind == "forecast"
    assert response.legend.items[0].label == "Reported"
    assert response.legend.items[1].label == "Forecast"
    assert response.factors.supporting[-1].key == "forecast_stability"
    assert response.factors.supporting[-1].label == "Forecast Stability"
    assert response.forecast_diagnostics.history_depth_years == 4
    assert response.forecast_methodology.heuristic is False
    assert response.cards.forecast_calculations is not None


def test_get_company_earnings_model_points_filters_rows_by_materialization_time() -> None:
    latest_only = _earnings_model_row(
        2026,
        quality_score=0.9,
        drift=0.12,
        last_updated=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    visible_historical = _earnings_model_row(
        2025,
        quality_score=0.5,
        drift=0.03,
        last_updated=datetime(2026, 1, 15, tzinfo=timezone.utc),
        last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc),
    )
    older_visible = _earnings_model_row(
        2024,
        quality_score=0.4,
        drift=-0.02,
        last_updated=datetime(2025, 2, 15, tzinfo=timezone.utc),
    )
    rows = [latest_only, visible_historical, older_visible]

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self._items

    class _FakeSession:
        def execute(self, _statement):
            return _FakeResult(rows)

    historical = cache_queries.get_company_earnings_model_points(
        _FakeSession(),
        1,
        as_of=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    latest = cache_queries.get_company_earnings_model_points(_FakeSession(), 1)

    assert [item.period_end for item in historical] == [date(2024, 12, 31), date(2025, 12, 31)]
    assert [item.period_end for item in latest] == [date(2024, 12, 31), date(2025, 12, 31), date(2026, 12, 31)]


def test_build_company_charts_dashboard_response_filters_earnings_model_inputs_for_as_of(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        cik="0000123456",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))
    statements = [
        SimpleNamespace(period_end=date(2022, 12, 31), filing_type="10-K", last_checked=datetime(2023, 2, 12, tzinfo=timezone.utc), data={"revenue": 1000, "operating_income": 120, "net_income": 90, "operating_cash_flow": 160, "free_cash_flow": 110, "capex": 50, "eps": 1.2, "weighted_average_diluted_shares": 75}),
        SimpleNamespace(period_end=date(2023, 12, 31), filing_type="10-K", last_checked=datetime(2024, 2, 12, tzinfo=timezone.utc), data={"revenue": 1200, "operating_income": 156, "net_income": 118, "operating_cash_flow": 190, "free_cash_flow": 132, "capex": 58, "eps": 1.5, "weighted_average_diluted_shares": 79}),
        SimpleNamespace(period_end=date(2024, 12, 31), filing_type="10-K", last_checked=datetime(2025, 2, 12, tzinfo=timezone.utc), data={"revenue": 1500, "operating_income": 210, "net_income": 162, "operating_cash_flow": 245, "free_cash_flow": 180, "capex": 65, "eps": 1.95, "weighted_average_diluted_shares": 83}),
        SimpleNamespace(period_end=date(2025, 12, 31), filing_type="10-K", last_checked=datetime(2026, 2, 12, tzinfo=timezone.utc), data={"revenue": 1800, "operating_income": 270, "net_income": 207, "operating_cash_flow": 300, "free_cash_flow": 222, "capex": 78, "eps": 2.4, "weighted_average_diluted_shares": 86}),
    ]
    historical_point = _earnings_model_row(
        2024,
        quality_score=0.35,
        drift=-0.04,
        last_updated=datetime(2025, 2, 15, tzinfo=timezone.utc),
        last_checked=datetime(2025, 2, 15, tzinfo=timezone.utc),
    )
    latest_point = _earnings_model_row(
        2025,
        quality_score=0.9,
        drift=0.11,
        last_updated=datetime(2026, 4, 12, tzinfo=timezone.utc),
        last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc),
    )
    observed_as_of: list[datetime | None] = []
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    def _get_points(_session, _company_id, *, limit=8, as_of=None):
        observed_as_of.append(as_of)
        rows = [historical_point, latest_point]
        if as_of is None:
            return rows[-limit:]
        return [row for row in rows if row.last_updated is not None and row.last_updated <= as_of][-limit:]

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", _get_points)

    latest_response = charts_service.build_company_charts_dashboard_response(
        fake_session,
        1,
        generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    historical_response = charts_service.build_company_charts_dashboard_response(
        fake_session,
        1,
        as_of=datetime(2025, 12, 31, tzinfo=timezone.utc),
        generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )

    assert latest_response is not None
    assert historical_response is not None
    assert observed_as_of == [None, datetime(2025, 12, 31, tzinfo=timezone.utc)]
    assert _factor_by_key(latest_response, "momentum").score > _factor_by_key(historical_response, "momentum").score
    assert latest_response.forecast_diagnostics.final_score > historical_response.forecast_diagnostics.final_score
    assert latest_response.diagnostics.parser_confidence == pytest.approx(0.9, abs=1e-6)
    assert historical_response.diagnostics.parser_confidence == pytest.approx(0.35, abs=1e-6)
    assert latest_response.last_refreshed_at == datetime(2026, 4, 12, tzinfo=timezone.utc)
    assert historical_response.last_refreshed_at == datetime(2025, 2, 15, tzinfo=timezone.utc)
    assert historical_response.cards.revenue.series[0].points[0].series_kind == "actual"
    assert historical_response.cards.revenue.series[1].points[0].series_kind == "forecast"
    assert historical_response.legend.items[0].label == "Reported"
    assert historical_response.legend.items[1].label == "Forecast"


def test_build_company_charts_dashboard_response_uses_driver_model_with_guidance_and_segments(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        cik="0000123456",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))
    statements = [
        SimpleNamespace(
            period_end=date(2023, 12, 31),
            filing_type="10-K",
            last_checked=datetime(2024, 2, 12, tzinfo=timezone.utc),
            data={
                "revenue": 1000,
                "operating_income": 150,
                "net_income": 120,
                "operating_cash_flow": 170,
                "free_cash_flow": 120,
                "capex": 50,
                "depreciation_and_amortization": 30,
                "weighted_average_diluted_shares": 100,
                "current_assets": 420,
                "current_liabilities": 180,
                "total_assets": 1200,
                "stock_based_compensation": 18,
                "share_buybacks": 12,
                "segment_breakdown": [
                    {"segment_id": "cloud", "segment_name": "Cloud", "kind": "business", "revenue": 600, "share_of_revenue": 0.6, "operating_income": 120},
                    {"segment_id": "services", "segment_name": "Services", "kind": "business", "revenue": 400, "share_of_revenue": 0.4, "operating_income": 30},
                ],
            },
        ),
        SimpleNamespace(
            period_end=date(2024, 12, 31),
            filing_type="10-K",
            last_checked=datetime(2025, 2, 12, tzinfo=timezone.utc),
            data={
                "revenue": 1180,
                "operating_income": 183,
                "net_income": 144,
                "operating_cash_flow": 205,
                "free_cash_flow": 145,
                "capex": 60,
                "depreciation_and_amortization": 34,
                "weighted_average_diluted_shares": 101,
                "current_assets": 460,
                "current_liabilities": 195,
                "total_assets": 1325,
                "stock_based_compensation": 20,
                "share_buybacks": 14,
                "segment_breakdown": [
                    {"segment_id": "cloud", "segment_name": "Cloud", "kind": "business", "revenue": 730, "share_of_revenue": 0.619, "operating_income": 152},
                    {"segment_id": "services", "segment_name": "Services", "kind": "business", "revenue": 450, "share_of_revenue": 0.381, "operating_income": 31},
                ],
            },
        ),
        SimpleNamespace(
            period_end=date(2025, 12, 31),
            filing_type="10-K",
            last_checked=datetime(2026, 2, 12, tzinfo=timezone.utc),
            data={
                "revenue": 1380,
                "operating_income": 221,
                "net_income": 174,
                "operating_cash_flow": 245,
                "free_cash_flow": 174,
                "capex": 71,
                "depreciation_and_amortization": 40,
                "weighted_average_diluted_shares": 102,
                "current_assets": 515,
                "current_liabilities": 210,
                "total_assets": 1460,
                "stock_based_compensation": 23,
                "share_buybacks": 15,
                "segment_breakdown": [
                    {"segment_id": "cloud", "segment_name": "Cloud", "kind": "business", "revenue": 900, "share_of_revenue": 0.652, "operating_income": 192},
                    {"segment_id": "services", "segment_name": "Services", "kind": "business", "revenue": 480, "share_of_revenue": 0.348, "operating_income": 29},
                ],
            },
        ),
    ]
    release = SimpleNamespace(
        id=1,
        filing_acceptance_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        filing_date=date(2026, 1, 20),
        reported_period_end=date(2025, 12, 31),
        revenue_guidance_low=1500.0,
        revenue_guidance_high=1540.0,
        last_checked=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.forecast_methodology.heuristic is False
    assert response.forecast_methodology.label == "Driver-based three-statement-lite forecast"
    assert {series.label for series in response.cards.revenue.series[1:]} == {"Base Forecast", "Bull Forecast", "Bear Forecast"}
    assert response.cards.forecast_calculations is not None
    assert any(item.label == "Management Guidance" for item in response.cards.forecast_assumptions.items)
    assert any(item.label == "Growth Sensitivity" for item in response.cards.forecast_calculations.items)


def test_build_company_charts_dashboard_response_falls_back_when_driver_inputs_are_too_thin(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        cik="0000123456",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))
    statements = [
        SimpleNamespace(period_end=date(2024, 12, 31), filing_type="10-K", last_checked=datetime(2025, 2, 12, tzinfo=timezone.utc), data={"revenue": 1000, "operating_income": 150, "net_income": 120}),
        SimpleNamespace(period_end=date(2025, 12, 31), filing_type="10-K", last_checked=datetime(2026, 2, 12, tzinfo=timezone.utc), data={"revenue": 1100, "operating_income": 165, "net_income": 130}),
    ]
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.6, drift=0.02)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.forecast_methodology.heuristic is True
    assert response.cards.forecast_calculations is None
    assert response.cards.revenue.series[1].label == "Forecast"


def test_forecast_revenue_handles_steady_compounder():
    actual = [
        _revenue_point(2022, 100.0),
        _revenue_point(2023, 110.0),
        _revenue_point(2024, 121.0),
        _revenue_point(2025, 133.1),
    ]

    forecast, curve = charts_service._forecast_revenue(actual)

    assert curve == pytest.approx([0.10, 0.0685, 0.051175], abs=1e-6)
    assert [point.value for point in forecast] == pytest.approx([146.41, 156.44, 164.44], abs=1e-2)


def test_forecast_revenue_dampens_one_year_spike_for_cyclical_history():
    actual = [
        _revenue_point(2022, 100.0),
        _revenue_point(2023, 200.0),
        _revenue_point(2024, 210.0),
        _revenue_point(2025, 220.5),
    ]

    forecast, curve = charts_service._forecast_revenue(actual)

    assert curve == pytest.approx([0.17, 0.107, 0.07235], abs=1e-6)
    assert curve[0] < 0.20
    assert [point.value for point in forecast] == pytest.approx([257.99, 285.59, 306.25], abs=1e-2)


def test_forecast_revenue_handles_flat_history_with_terminal_reversion():
    actual = [
        _revenue_point(2022, 100.0),
        _revenue_point(2023, 100.0),
        _revenue_point(2024, 100.0),
        _revenue_point(2025, 100.0),
    ]

    forecast, curve = charts_service._forecast_revenue(actual)

    assert curve == pytest.approx([0.0, 0.0135, 0.020925], abs=1e-6)
    assert [point.value for point in forecast] == pytest.approx([100.0, 101.35, 103.47], abs=1e-2)


def test_forecast_revenue_handles_declining_history_with_mean_reversion():
    actual = [
        _revenue_point(2022, 100.0),
        _revenue_point(2023, 90.0),
        _revenue_point(2024, 81.0),
        _revenue_point(2025, 72.9),
    ]

    forecast, curve = charts_service._forecast_revenue(actual)

    assert curve == pytest.approx([-0.10, -0.0415, -0.009325], abs=1e-6)
    assert [point.value for point in forecast] == pytest.approx([65.61, 62.89, 62.30], abs=1e-2)


def test_forecast_revenue_uses_terminal_growth_when_history_is_insufficient():
    actual = [_revenue_point(2025, 100.0)]

    forecast, curve = charts_service._forecast_revenue(actual)

    assert curve == pytest.approx([0.03, 0.03, 0.03], abs=1e-6)
    assert [point.value for point in forecast] == pytest.approx([103.0, 106.09, 109.27], abs=1e-2)


def test_forecast_revenue_ignores_missing_revenue_values_without_creating_false_zeros():
    actual = [
        _revenue_point(2022, 100.0),
        _series_point(2023, None),
        _revenue_point(2024, 121.0),
    ]

    forecast, curve = charts_service._forecast_revenue(actual)
    growth = charts_service._growth_series(actual, "actual")

    assert curve == pytest.approx([0.03, 0.03, 0.03], abs=1e-6)
    assert [point.value for point in forecast] == pytest.approx([124.63, 128.37, 132.22], abs=1e-2)
    assert growth == []
    assert all(point.value is not None and point.value > 0 for point in forecast)


def test_forecast_revenue_applies_guardrails_to_extreme_histories():
    high_actual = [
        _revenue_point(2022, 100.0),
        _revenue_point(2023, 500.0),
        _revenue_point(2024, 2500.0),
        _revenue_point(2025, 12500.0),
    ]
    low_actual = [
        _revenue_point(2022, 1000.0),
        _revenue_point(2023, 100.0),
        _revenue_point(2024, 10.0),
        _revenue_point(2025, 1.0),
    ]

    high_forecast, high_curve = charts_service._forecast_revenue(high_actual)
    low_forecast, low_curve = charts_service._forecast_revenue(low_actual)

    assert high_curve == pytest.approx([0.30, 0.1785, 0.111675], abs=1e-6)
    assert low_curve == pytest.approx([-0.18, -0.0855, -0.033525], abs=1e-6)
    assert high_forecast[0].value == pytest.approx(16250.0, abs=1e-2)
    assert low_forecast[0].value == pytest.approx(0.82, abs=1e-2)


def test_margin_projection_normalizes_unusually_high_recent_operating_margin():
    statements = [
        _statement(2022, {"revenue": 100.0, "operating_income": 20.0}),
        _statement(2023, {"revenue": 100.0, "operating_income": 20.0}),
        _statement(2024, {"revenue": 100.0, "operating_income": 20.0}),
        _statement(2025, {"revenue": 100.0, "operating_income": 35.0}),
    ]
    revenue_actual = [_revenue_point(2022, 100.0), _revenue_point(2023, 100.0), _revenue_point(2024, 100.0), _revenue_point(2025, 100.0)]
    revenue_forecast = [_forecast_revenue_point(2026, 100.0), _forecast_revenue_point(2027, 100.0), _forecast_revenue_point(2028, 100.0)]

    series = charts_service._margin_projected_series(statements, revenue_actual, revenue_forecast, [("operating_income", "EBIT")])
    forecast_series = _series_by_key(series, "operating_income_forecast")

    assert [point.value for point in forecast_series.points] == pytest.approx([31.22, 27.97, 25.81], abs=1e-2)
    assert forecast_series.points[0].value < 35.0
    assert forecast_series.points[2].value < forecast_series.points[0].value


def test_margin_projection_keeps_stable_mature_company_margins_consistent():
    statements = [
        _statement(2022, {"revenue": 100.0, "ebitda_proxy": None, "operating_income": 25.0, "depreciation_and_amortization": 5.0, "capex": 6.0}),
        _statement(2023, {"revenue": 110.0, "ebitda_proxy": None, "operating_income": 27.5, "depreciation_and_amortization": 5.5, "capex": 6.6}),
        _statement(2024, {"revenue": 121.0, "ebitda_proxy": None, "operating_income": 30.25, "depreciation_and_amortization": 6.05, "capex": 7.26}),
        _statement(2025, {"revenue": 133.1, "ebitda_proxy": None, "operating_income": 33.275, "depreciation_and_amortization": 6.655, "capex": 7.986}),
    ]
    revenue_actual = [_revenue_point(2022, 100.0), _revenue_point(2023, 110.0), _revenue_point(2024, 121.0), _revenue_point(2025, 133.1)]
    revenue_forecast = [_forecast_revenue_point(2026, 146.41), _forecast_revenue_point(2027, 156.44), _forecast_revenue_point(2028, 164.44)]

    series = charts_service._margin_projected_series(statements, revenue_actual, revenue_forecast, [("ebitda_proxy", "EBITDA"), ("capex", "Capex")])
    ebitda_forecast = _series_by_key(series, "ebitda_proxy_forecast")
    capex_forecast = _series_by_key(series, "capex_forecast")

    ebitda_margins = [point.value / revenue for point, revenue in zip(ebitda_forecast.points, [146.41, 156.44, 164.44])]
    capex_margins = [point.value / revenue for point, revenue in zip(capex_forecast.points, [146.41, 156.44, 164.44])]

    assert ebitda_margins == pytest.approx([0.30, 0.30, 0.30], abs=1e-4)
    assert capex_margins == pytest.approx([0.06, 0.06, 0.06], abs=1e-4)


def test_margin_projection_uses_ocf_minus_capex_when_fcf_history_is_missing():
    statements = [
        _statement(2022, {"revenue": 100.0, "operating_cash_flow": 15.0, "capex": 5.0, "free_cash_flow": None}),
        _statement(2023, {"revenue": 110.0, "operating_cash_flow": 16.5, "capex": 5.5, "free_cash_flow": None}),
        _statement(2024, {"revenue": 121.0, "operating_cash_flow": 18.15, "capex": 6.05, "free_cash_flow": None}),
        _statement(2025, {"revenue": 133.1, "operating_cash_flow": 19.965, "capex": 6.655, "free_cash_flow": None}),
    ]
    revenue_actual = [_revenue_point(2022, 100.0), _revenue_point(2023, 110.0), _revenue_point(2024, 121.0), _revenue_point(2025, 133.1)]
    revenue_forecast = [_forecast_revenue_point(2026, 140.0), _forecast_revenue_point(2027, 150.0), _forecast_revenue_point(2028, 160.0)]

    series = charts_service._margin_projected_series(statements, revenue_actual, revenue_forecast, [("free_cash_flow", "Free CF")])
    actual_series = _series_by_key(series, "free_cash_flow_actual")
    forecast_series = _series_by_key(series, "free_cash_flow_forecast")

    assert [point.value for point in actual_series.points] == pytest.approx([10.0, 11.0, 12.1, 13.31], abs=1e-2)
    assert [point.value for point in forecast_series.points] == pytest.approx([14.0, 15.0, 16.0], abs=1e-2)


def test_margin_projection_handles_negative_net_income_margins():
    statements = [
        _statement(2022, {"revenue": 100.0, "net_income": -5.0}),
        _statement(2023, {"revenue": 100.0, "net_income": -6.0}),
        _statement(2024, {"revenue": 100.0, "net_income": -7.0}),
        _statement(2025, {"revenue": 100.0, "net_income": -15.0}),
    ]
    revenue_actual = [_revenue_point(2022, 100.0), _revenue_point(2023, 100.0), _revenue_point(2024, 100.0), _revenue_point(2025, 100.0)]
    revenue_forecast = [_forecast_revenue_point(2026, 100.0), _forecast_revenue_point(2027, 100.0), _forecast_revenue_point(2028, 100.0)]

    series = charts_service._margin_projected_series(statements, revenue_actual, revenue_forecast, [("net_income", "Net Income")])
    forecast_series = _series_by_key(series, "net_income_forecast")

    assert [point.value for point in forecast_series.points] == pytest.approx([-12.08, -10.14, -9.17], abs=1e-2)
    assert all(point.value < 0 for point in forecast_series.points)
    assert forecast_series.points[0].value < forecast_series.points[1].value < forecast_series.points[2].value


def test_forecast_diluted_shares_stays_flat_with_stable_share_count():
    forecast = charts_service._forecast_diluted_shares([100.0, 100.0, 100.0, 100.0], 3)

    assert forecast == pytest.approx([100.0, 100.0, 100.0], abs=1e-6)


def test_forecast_diluted_shares_extends_buyback_trend_with_reversion():
    forecast = charts_service._forecast_diluted_shares([100.0, 98.0, 96.04, 94.1192], 3)

    assert forecast == pytest.approx([92.236816, 91.31444784, 90.8578756008], abs=1e-6)
    assert forecast[0] < 94.1192
    assert forecast[2] < forecast[1] < forecast[0]


def test_forecast_diluted_shares_extends_dilution_trend_with_reversion():
    forecast = charts_service._forecast_diluted_shares([100.0, 103.0, 106.09, 109.2727], 3)

    assert forecast == pytest.approx([112.550881, 114.239144215, 115.0959377966125], abs=1e-6)
    assert forecast[0] > 109.2727
    assert forecast[2] > forecast[1] > forecast[0]


def test_eps_series_falls_back_to_net_income_over_shares_when_reported_eps_missing():
    statements = [
        _statement(2024, {"revenue": 100.0, "net_income": 10.0, "weighted_average_diluted_shares": 100.0, "eps": None}),
        _statement(2025, {"revenue": 110.0, "net_income": 11.0, "weighted_average_diluted_shares": 100.0, "eps": None}),
    ]
    net_income_forecast = [
        _forecast_revenue_point(2026, 12.0),
        _forecast_revenue_point(2027, 13.0),
        _forecast_revenue_point(2028, 14.0),
    ]

    actual, forecast = charts_service._eps_series(statements, net_income_forecast)

    assert [point.value for point in actual] == pytest.approx([0.1, 0.11], abs=1e-3)
    assert [point.value for point in forecast] == pytest.approx([0.12, 0.13, 0.14], abs=1e-3)


def test_eps_series_suppresses_forecast_when_share_history_is_missing():
    statements = [
        _statement(2024, {"revenue": 100.0, "net_income": 10.0, "weighted_average_diluted_shares": None, "eps": 0.1}),
        _statement(2025, {"revenue": 110.0, "net_income": 11.0, "weighted_average_diluted_shares": None, "eps": 0.11}),
    ]
    net_income_forecast = [
        _forecast_revenue_point(2026, 12.0),
        _forecast_revenue_point(2027, 13.0),
        _forecast_revenue_point(2028, 14.0),
    ]

    actual, forecast = charts_service._eps_series(statements, net_income_forecast)

    assert [point.value for point in actual] == pytest.approx([0.1, 0.11], abs=1e-3)
    assert forecast == []


def test_eps_series_omits_missing_net_income_forecast_points():
    statements = [
        _statement(2024, {"revenue": 100.0, "net_income": 10.0, "weighted_average_diluted_shares": 100.0, "eps": 0.1}),
        _statement(2025, {"revenue": 110.0, "net_income": 11.0, "weighted_average_diluted_shares": 100.0, "eps": 0.11}),
    ]
    net_income_forecast = [
        _series_point(2026, 12.0, kind="forecast"),
        _series_point(2027, None, kind="forecast"),
        _series_point(2028, 14.0, kind="forecast"),
    ]

    actual, forecast = charts_service._eps_series(statements, net_income_forecast)

    assert [point.value for point in actual] == pytest.approx([0.1, 0.11], abs=1e-3)
    assert [point.fiscal_year for point in forecast] == [2026, 2028]
    assert [point.value for point in forecast] == pytest.approx([0.12, 0.14], abs=1e-3)


def test_eps_series_handles_partial_missing_diluted_share_history_without_zero_fallbacks():
    statements = [
        _statement(2024, {"revenue": 100.0, "net_income": 10.0, "weighted_average_diluted_shares": 100.0, "eps": None}),
        _statement(2025, {"revenue": 110.0, "net_income": 11.0, "weighted_average_diluted_shares": None, "eps": None}),
    ]
    net_income_forecast = [
        _series_point(2026, 12.0, kind="forecast"),
        _series_point(2027, 13.0, kind="forecast"),
    ]

    actual, forecast = charts_service._eps_series(statements, net_income_forecast)

    assert [point.value for point in actual] == pytest.approx([0.1], abs=1e-3)
    assert [point.value for point in forecast] == pytest.approx([0.12, 0.13], abs=1e-3)
    assert all(point.value is not None and point.value > 0 for point in forecast)


def test_margin_projection_skips_forecast_points_when_revenue_forecast_values_are_missing():
    statements = [
        _statement(2023, {"revenue": 100.0, "operating_income": 20.0}),
        _statement(2024, {"revenue": 110.0, "operating_income": 22.0}),
        _statement(2025, {"revenue": 121.0, "operating_income": 24.2}),
    ]
    revenue_actual = [_revenue_point(2023, 100.0), _revenue_point(2024, 110.0), _revenue_point(2025, 121.0)]
    revenue_forecast = [
        _series_point(2026, 130.0, kind="forecast"),
        _series_point(2027, None, kind="forecast"),
        _series_point(2028, 150.0, kind="forecast"),
    ]

    series = charts_service._margin_projected_series(statements, revenue_actual, revenue_forecast, [("operating_income", "EBIT")])
    forecast_series = _series_by_key(series, "operating_income_forecast")

    assert [point.fiscal_year for point in forecast_series.points] == [2026, 2028]
    assert all(point.value is not None and point.value > 0 for point in forecast_series.points)


def test_growth_helpers_guard_zero_and_invalid_denominators():
    assert charts_service._growth_rate(120.0, 0.0) is None
    assert charts_service._growth_rate(120.0, -10.0) is None
    assert charts_service._growth_rate(-5.0, 100.0) is None
    assert charts_service._safe_divide(10.0, 0.0) is None
    assert charts_service._safe_divide(10.0, -1.0) is None
    assert charts_service._cagr([100.0, 0.0, 120.0]) is None


def test_forecast_stability_label_boundaries():
    assert charts_service._stability_label(None) == "Guarded stability"
    assert charts_service._stability_label(85) == "Higher stability"
    assert charts_service._stability_label(65) == "Moderate stability"
    assert charts_service._stability_label(45) == "Guarded stability"
    assert charts_service._stability_label(30) == "Low stability"


def test_forecast_stability_calibrates_empirical_error_bands_by_sector_template():
    company = SimpleNamespace(name="Acme", sector="Technology", market_sector="Technology")
    template = charts_service._forecast_stability_sector_template(company)

    assert charts_service._error_band(0.08, template) == "tight"
    assert charts_service._error_band(0.14, template) == "moderate"
    assert charts_service._error_band(0.24, template) == "wide"
    assert charts_service._error_band(0.40, template) == "very_wide"
    assert charts_service._empirical_stability_score(0.08, 4, template) > charts_service._empirical_stability_score(0.24, 4, template)


def test_forecast_stability_penalties_are_monotonic():
    calm_statements = [
        _statement(2021, {"revenue": 100.0, "operating_income": 20.0, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
        _statement(2022, {"revenue": 108.0, "operating_income": 21.6, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
        _statement(2023, {"revenue": 116.64, "operating_income": 23.33, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
        _statement(2024, {"revenue": 125.97, "operating_income": 25.19, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
        _statement(2025, {"revenue": 136.05, "operating_income": 27.21, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
    ]
    noisy_statements = [
        _statement(2021, {"revenue": 100.0, "operating_income": 20.0, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
        _statement(2022, {"revenue": 180.0, "operating_income": 18.0, "weighted_average_diluted_shares": 108.0, "acquisitions": 5.0}),
        _statement(2023, {"revenue": 90.0, "operating_income": 6.0, "weighted_average_diluted_shares": 121.0, "acquisitions": 20.0}),
        _statement(2024, {"revenue": 220.0, "operating_income": 40.0, "weighted_average_diluted_shares": 138.0, "acquisitions": 60.0}),
        _statement(2025, {"revenue": 140.0, "operating_income": 12.0, "weighted_average_diluted_shares": 160.0, "acquisitions": 50.0}),
    ]
    calm_growths = charts_service._historical_growth_rates([100.0, 108.0, 116.64, 125.97, 136.05])
    noisy_growths = charts_service._historical_growth_rates([100.0, 180.0, 90.0, 220.0, 140.0])

    assert charts_service._structural_break_penalty(noisy_growths, noisy_statements) >= charts_service._structural_break_penalty(calm_growths, calm_statements)
    assert charts_service._major_mna_penalty(noisy_statements) > charts_service._major_mna_penalty(calm_statements)
    assert charts_service._share_instability_penalty(noisy_statements) > charts_service._share_instability_penalty(calm_statements)
    assert charts_service._restatement_penalty(
        [
            SimpleNamespace(changed_metric_keys=["revenue", "net_income"], confidence_impact={"score_delta": -2.0}),
            SimpleNamespace(changed_metric_keys=["eps"], confidence_impact={"score_delta": -1.0}),
        ]
    ) > charts_service._restatement_penalty([])


def test_forecast_stability_profile_uses_conservative_backtest_and_penalties():
    company = SimpleNamespace(id=1, name="Acme", sector="Technology", market_sector="Technology")
    statements = [
        _statement(2021, {"revenue": 100.0, "operating_income": 20.0, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
        _statement(2022, {"revenue": 108.0, "operating_income": 21.6, "weighted_average_diluted_shares": 100.0, "acquisitions": 0.0}),
        _statement(2023, {"revenue": 116.64, "operating_income": 23.33, "weighted_average_diluted_shares": 101.0, "acquisitions": 0.0}),
        _statement(2024, {"revenue": 125.97, "operating_income": 25.19, "weighted_average_diluted_shares": 101.0, "acquisitions": 0.0}),
        _statement(2025, {"revenue": 136.05, "operating_income": 27.21, "weighted_average_diluted_shares": 102.0, "acquisitions": 0.0}),
    ]
    revenue_actual = [_revenue_point(year, value) for year, value in [(2021, 100.0), (2022, 108.0), (2023, 116.64), (2024, 125.97), (2025, 136.05)]]

    diagnostics = charts_service._forecast_stability_profile(
        object(),
        company,
        statements,
        revenue_actual,
        [_earnings_point(quality_score=66.67)],
        [],
        [],
        None,
    )

    assert diagnostics.score_key == "forecast_stability"
    assert diagnostics.score_name == "Forecast Stability"
    assert diagnostics.quality_score == pytest.approx(66.67, abs=1e-6)
    assert diagnostics.components[-2].display_value == "66.67%"
    assert diagnostics.sample_size >= 2
    assert diagnostics.historical_backtest_error_band in {"tight", "moderate", "wide", "very_wide"}
    assert diagnostics.final_score <= charts_service.FORECAST_STABILITY_MAX_SCORE


def test_walk_forward_backtest_filters_future_release_inputs(monkeypatch):
    company = SimpleNamespace(name="Acme", sector="Technology", market_sector="Technology")
    statements = [
        _statement(2022, {"revenue": 100.0}),
        _statement(2023, {"revenue": 110.0}),
        _statement(2024, {"revenue": 121.0}),
        _statement(2025, {"revenue": 133.1}),
    ]
    visible_release = SimpleNamespace(filing_date=date(2024, 1, 20), filing_acceptance_at=datetime(2024, 1, 20, tzinfo=timezone.utc), revenue_guidance_high=121.0)
    future_release = SimpleNamespace(filing_date=date(2025, 2, 20), filing_acceptance_at=datetime(2025, 2, 20, tzinfo=timezone.utc), revenue_guidance_high=999.0)

    def _fake_bundle(_history, releases):
        anchor = max((getattr(release, "revenue_guidance_high", 0.0) or 0.0) for release in releases) if releases else 0.0
        return SimpleNamespace(guidance_anchor=anchor)

    def _fake_forecast_state(history, *_args, driver_bundle=None, **_kwargs):
        latest_year = history[-1].period_end.year
        latest_revenue = charts_service._statement_value(history[-1], "revenue")
        next_value = latest_revenue * (1.10 if (getattr(driver_bundle, "guidance_anchor", 0.0) or 0.0) < 500 else 5.0)
        return {
            "revenue_card": charts_service.CompanyChartsCardPayload(
                key="revenue",
                title="Revenue",
                series=[
                    charts_service.CompanyChartsSeriesPayload(
                        key="revenue_forecast",
                        label="Forecast",
                        unit="usd",
                        chart_type="line",
                        series_kind="forecast",
                        stroke_style="dashed",
                        points=[
                            charts_service.CompanyChartsSeriesPointPayload(
                                period_label=f"FY{latest_year + 1}E",
                                fiscal_year=latest_year + 1,
                                period_end=None,
                                value=round(next_value, 2),
                                series_kind="forecast",
                            )
                        ],
                    )
                ],
            )
        }

    monkeypatch.setattr(charts_service, "build_driver_forecast_bundle", _fake_bundle)
    monkeypatch.setattr(charts_service, "_build_forecast_state", _fake_forecast_state)

    backtest = charts_service._walk_forward_revenue_backtest(object(), company, statements, [visible_release, future_release])

    assert backtest["sample_size"] == 2
    assert backtest["horizon_errors"][1] == pytest.approx(0.0, abs=1e-9)
    assert backtest["weighted_error"] == pytest.approx(0.0, abs=1e-9)
