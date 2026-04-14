from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

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
    monkeypatch.setattr(
        charts_service,
        "get_company_earnings_model_points",
        lambda *_args, **_kwargs: [SimpleNamespace(last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc), quality_score=0.74, earnings_momentum_drift=0.11)],
    )

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.cards.revenue.series[0].points[0].series_kind == "actual"
    assert response.cards.revenue.series[1].points[0].series_kind == "forecast"
    assert response.cards.revenue_growth.series[1].points[0].series_kind == "forecast"
    assert response.cards.eps.series[1].points[0].series_kind == "forecast"
    assert response.legend.items[0].label == "Reported"
    assert response.legend.items[1].label == "Forecast"
    assert response.factors.supporting[-1].key == "forecast_confidence"
    assert response.factors.supporting[-1].label == "Forecast Reliability"
    assert response.forecast_diagnostics.history_depth_years == 4
    assert response.forecast_methodology.heuristic is True


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


def test_forecast_reliability_flags_thin_history():
    statements = [
        _statement(2024, {"revenue": 100.0}),
        _statement(2025, {"revenue": 110.0}),
    ]
    revenue_actual = [_revenue_point(2024, 100.0), _revenue_point(2025, 110.0)]

    diagnostics = charts_service._forecast_reliability_profile(statements, revenue_actual, [_earnings_point(quality_score=0.5)])

    assert diagnostics.history_depth_years == 2
    assert diagnostics.thin_history is True
    assert diagnostics.final_score == 59


def test_forecast_reliability_marks_volatile_revenue_history():
    statements = [
        _statement(2022, {"revenue": 100.0}),
        _statement(2023, {"revenue": 200.0}),
        _statement(2024, {"revenue": 80.0}),
        _statement(2025, {"revenue": 220.0}),
    ]
    revenue_actual = [_revenue_point(2022, 100.0), _revenue_point(2023, 200.0), _revenue_point(2024, 80.0), _revenue_point(2025, 220.0)]

    diagnostics = charts_service._forecast_reliability_profile(statements, revenue_actual, [_earnings_point(quality_score=0.5)])

    assert diagnostics.growth_volatility_band == "high"
    assert diagnostics.growth_volatility == pytest.approx(1.1167, abs=1e-4)
    assert diagnostics.final_score == 59


def test_forecast_reliability_rewards_high_quality_score():
    statements = [
        _statement(2022, {"revenue": 100.0}),
        _statement(2023, {"revenue": 108.0}),
        _statement(2024, {"revenue": 116.64}),
        _statement(2025, {"revenue": 125.97}),
        _statement(2026, {"revenue": 136.05}),
    ]
    revenue_actual = [_revenue_point(2022, 100.0), _revenue_point(2023, 108.0), _revenue_point(2024, 116.64), _revenue_point(2025, 125.97), _revenue_point(2026, 136.05)]

    high_quality = charts_service._forecast_reliability_profile(statements, revenue_actual, [_earnings_point(quality_score=0.9)])
    neutral_quality = charts_service._forecast_reliability_profile(statements, revenue_actual, [_earnings_point(quality_score=0.5)])

    assert high_quality.quality_score == pytest.approx(0.9, abs=1e-6)
    assert high_quality.final_score == 85
    assert high_quality.final_score > neutral_quality.final_score


def test_forecast_reliability_normalizes_percentage_scale_quality_score():
    statements = [
        _statement(2022, {"revenue": 100.0}),
        _statement(2023, {"revenue": 130.0}),
        _statement(2024, {"revenue": 169.0}),
        _statement(2025, {"revenue": 219.7}),
        _statement(2026, {"revenue": 285.61}),
        _statement(2027, {"revenue": 371.29}),
        _statement(2028, {"revenue": 482.68}),
        _statement(2029, {"revenue": 627.48}),
    ]
    revenue_actual = [_revenue_point(year, value) for year, value in [(2022, 100.0), (2023, 130.0), (2024, 169.0), (2025, 219.7), (2026, 285.61), (2027, 371.29), (2028, 482.68), (2029, 627.48)]]

    diagnostics = charts_service._forecast_reliability_profile(statements, revenue_actual, [_earnings_point(quality_score=66.67)])

    assert diagnostics.quality_score == pytest.approx(66.67, abs=1e-6)
    assert diagnostics.components[-1].display_value == "66.67%"
    assert diagnostics.components[-1].impact == 3
    assert diagnostics.final_score == 83


def test_forecast_reliability_penalizes_low_quality_score():
    statements = [
        _statement(2022, {"revenue": 100.0}),
        _statement(2023, {"revenue": 108.0}),
        _statement(2024, {"revenue": 116.64}),
        _statement(2025, {"revenue": 125.97}),
        _statement(2026, {"revenue": 136.05}),
    ]
    revenue_actual = [_revenue_point(2022, 100.0), _revenue_point(2023, 108.0), _revenue_point(2024, 116.64), _revenue_point(2025, 125.97), _revenue_point(2026, 136.05)]

    low_quality = charts_service._forecast_reliability_profile(statements, revenue_actual, [_earnings_point(quality_score=0.1)])
    neutral_quality = charts_service._forecast_reliability_profile(statements, revenue_actual, [_earnings_point(quality_score=0.5)])

    assert low_quality.quality_score == pytest.approx(0.1, abs=1e-6)
    assert low_quality.final_score == 69
    assert low_quality.final_score < neutral_quality.final_score


def test_forecast_reliability_clips_to_min_and_max_bounds():
    high_statements = [_statement(year, {"revenue": 100.0 + ((year - 2020) * 2.0)}) for year in range(2021, 2029)]
    high_revenue_actual = [_revenue_point(year, 100.0 + ((year - 2020) * 2.0)) for year in range(2021, 2029)]
    low_statements = [
        _statement(2024, {"revenue": 100.0}),
        _statement(2025, {"revenue": 400.0}),
    ]
    low_revenue_actual = [_revenue_point(2024, 100.0), _revenue_point(2025, 400.0)]

    high = charts_service._forecast_reliability_profile(high_statements, high_revenue_actual, [_earnings_point(quality_score=200.0)])
    low = charts_service._forecast_reliability_profile(low_statements, low_revenue_actual, [_earnings_point(quality_score=-500.0)])

    assert high.final_score == charts_service.FORECAST_RELIABILITY_MAX_SCORE
    assert low.final_score == charts_service.FORECAST_RELIABILITY_MIN_SCORE
