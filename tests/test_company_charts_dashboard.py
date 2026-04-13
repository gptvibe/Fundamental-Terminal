from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import app.services.company_charts_dashboard as charts_service


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
