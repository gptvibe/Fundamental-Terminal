from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.services.cache_queries as cache_queries
import app.services.company_charts_dashboard as charts_service
import app.services.company_charts_driver_model as driver_model


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


def _guidance_release(anchor: float) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        filing_acceptance_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        filing_date=date(2026, 1, 20),
        reported_period_end=date(2025, 12, 31),
        revenue_guidance_low=anchor,
        revenue_guidance_high=anchor,
        last_checked=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )


def _driver_forecast_statement(
    year: int,
    revenue: float,
    *,
    receivables_days: float,
    inventory_days: float,
    payable_days: float,
    deferred_revenue_days: float = 0.0,
    accrued_liability_days: float = 0.0,
    net_ppe: float | None = None,
    ppe_disposals: float | None = None,
    cash_balance: float | None = None,
    current_debt: float | None = None,
    long_term_debt: float | None = None,
    total_debt: float | None = None,
    interest_expense: float | None = None,
    interest_income: float | None = None,
    extra_data: dict[str, float | None] | None = None,
) -> SimpleNamespace:
    cost_of_revenue = revenue * 0.55
    depreciation = revenue * 0.03
    operating_income = revenue * 0.14
    pretax_income = revenue * 0.131
    income_tax_expense = pretax_income * 0.21
    net_income = pretax_income - income_tax_expense
    cash_operating_cost = revenue - operating_income - depreciation
    data = {
        "revenue": revenue,
        "gross_profit": revenue - cost_of_revenue,
        "operating_income": operating_income,
        "pretax_income": pretax_income,
        "income_tax_expense": income_tax_expense,
        "net_income": net_income,
        "operating_cash_flow": revenue * 0.13,
        "free_cash_flow": revenue * 0.09,
        "capex": revenue * 0.04,
        "depreciation_and_amortization": depreciation,
        "weighted_average_diluted_shares": 100.0,
        "accounts_receivable": driver_model._days_to_balance(revenue, receivables_days),
        "inventory": driver_model._days_to_balance(cost_of_revenue, inventory_days),
        "accounts_payable": driver_model._days_to_balance(cost_of_revenue, payable_days),
        "deferred_revenue": driver_model._days_to_balance(revenue, deferred_revenue_days),
        "accrued_operating_liabilities": driver_model._days_to_balance(cash_operating_cost, accrued_liability_days),
        "net_ppe": net_ppe,
        "ppe_disposals": ppe_disposals,
        "current_assets": revenue * 0.40,
        "current_liabilities": revenue * 0.20,
        "total_assets": revenue * 1.20,
        "cash_and_cash_equivalents": revenue * 0.18 if cash_balance is None else cash_balance,
        "current_debt": revenue * 0.02 if current_debt is None else current_debt,
        "long_term_debt": revenue * 0.18 if long_term_debt is None else long_term_debt,
        "total_debt": total_debt,
        "interest_expense": revenue * 0.01 if interest_expense is None else interest_expense,
        "interest_income": revenue * 0.002 if interest_income is None else interest_income,
        "other_income_expense": -(revenue * 0.001),
        "stock_based_compensation": revenue * 0.01,
        "share_buybacks": revenue * 0.003,
    }
    if extra_data:
        data.update(extra_data)
    return _statement(year, data)


def _standard_driver_regression_statements() -> list[SimpleNamespace]:
    return [
        _driver_forecast_statement(2023, 900.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, deferred_revenue_days=3.0, accrued_liability_days=3.0),
        _driver_forecast_statement(2024, 1000.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, deferred_revenue_days=3.0, accrued_liability_days=3.0),
        _driver_forecast_statement(2025, 1100.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, deferred_revenue_days=3.0, accrued_liability_days=3.0),
    ]


def _ppe_disclosure_driver_statements() -> list[SimpleNamespace]:
    return [
        _driver_forecast_statement(2023, 900.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, net_ppe=310.0, ppe_disposals=4.0),
        _driver_forecast_statement(2024, 1000.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, net_ppe=340.0, ppe_disposals=5.0),
        _driver_forecast_statement(2025, 1100.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, net_ppe=369.0, ppe_disposals=6.0),
    ]


def _ppe_sparse_driver_statements() -> list[SimpleNamespace]:
    return [
        _driver_forecast_statement(2023, 900.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, net_ppe=310.0),
        _driver_forecast_statement(2024, 1000.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, net_ppe=340.0),
        _driver_forecast_statement(2025, 1100.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, net_ppe=None),
    ]


def _loss_recovery_tax_driver_statements() -> list[SimpleNamespace]:
    return [
        _driver_forecast_statement(
            2023,
            900.0,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            extra_data={
                "pretax_income": 118.0,
                "income_tax_expense": 24.0,
                "net_income": 94.0,
                "cash_taxes_paid": 24.0,
            },
        ),
        _driver_forecast_statement(
            2024,
            850.0,
            receivables_days=58.0,
            inventory_days=34.0,
            payable_days=29.0,
            extra_data={
                "operating_income": -42.0,
                "pretax_income": -80.0,
                "income_tax_expense": -16.0,
                "net_income": -64.0,
                "operating_cash_flow": -36.0,
                "free_cash_flow": -70.0,
                "cash_taxes_paid": 0.0,
            },
        ),
        _driver_forecast_statement(
            2025,
            980.0,
            receivables_days=56.0,
            inventory_days=33.0,
            payable_days=28.0,
            extra_data={
                "pretax_income": 60.0,
                "income_tax_expense": 0.0,
                "net_income": 60.0,
                "cash_taxes_paid": 0.0,
            },
        ),
    ]


def _sparse_tax_driver_statements() -> list[SimpleNamespace]:
    return [
        _driver_forecast_statement(
            2023,
            900.0,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            extra_data={
                "income_tax_expense": None,
                "cash_taxes_paid": None,
                "current_tax_expense": None,
                "deferred_tax_expense": None,
                "deferred_tax_asset": None,
                "net_income": 118.0,
            },
        ),
        _driver_forecast_statement(
            2024,
            1000.0,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            extra_data={
                "income_tax_expense": None,
                "cash_taxes_paid": None,
                "current_tax_expense": None,
                "deferred_tax_expense": None,
                "deferred_tax_asset": None,
                "net_income": 131.0,
            },
        ),
        _driver_forecast_statement(
            2025,
            1100.0,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            extra_data={
                "income_tax_expense": None,
                "cash_taxes_paid": None,
                "current_tax_expense": None,
                "deferred_tax_expense": None,
                "deferred_tax_asset": None,
                "net_income": 144.1,
            },
        ),
    ]


def _balanced_balance_sheet_driver_statements() -> list[SimpleNamespace]:
    statements: list[SimpleNamespace] = []
    for year, revenue, net_ppe in ((2023, 900.0, 280.0), (2024, 1000.0, 310.0), (2025, 1100.0, 340.0)):
        statement = _driver_forecast_statement(
            year,
            revenue,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            net_ppe=net_ppe,
            cash_balance=revenue * 0.12,
            current_debt=20.0,
            long_term_debt=80.0,
            total_debt=100.0,
            extra_data={
                "stock_based_compensation": 0.0,
                "share_buybacks": 0.0,
                "dividends_paid": 0.0,
            },
        )
        data = statement.data
        current_assets = data["cash_and_cash_equivalents"] + data["accounts_receivable"] + data["inventory"]
        total_assets = current_assets + data["net_ppe"]
        total_liabilities = data["accounts_payable"] + data["current_debt"] + data["long_term_debt"]
        total_equity = total_assets - total_liabilities
        data.update(
            {
                "current_assets": current_assets,
                "current_liabilities": data["accounts_payable"] + data["current_debt"],
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "total_equity": total_equity,
                "retained_earnings": total_equity,
                "cash_taxes_paid": data["income_tax_expense"],
            }
        )
        statements.append(statement)
    return statements


def _plugged_balance_sheet_driver_statements() -> list[SimpleNamespace]:
    statements = _balanced_balance_sheet_driver_statements()
    for statement in statements:
        statement.data["total_assets"] = float(statement.data["total_assets"]) + 40.0
        statement.data.pop("total_liabilities", None)
        statement.data.pop("total_equity", None)
        statement.data["retained_earnings"] = float(statement.data["retained_earnings"])
    return statements


def _no_debt_draw_driver_statements() -> list[SimpleNamespace]:
    statements: list[SimpleNamespace] = []
    for year, revenue in ((2023, 900.0), (2024, 1000.0), (2025, 1100.0)):
        statements.append(
            _statement(
                year,
                {
                    "revenue": revenue,
                    "gross_profit": revenue * 0.42,
                    "operating_income": revenue * 0.06,
                    "pretax_income": revenue * 0.055,
                    "income_tax_expense": revenue * 0.011,
                    "net_income": revenue * 0.044,
                    "operating_cash_flow": revenue * 0.05,
                    "free_cash_flow": -(revenue * 0.08),
                    "capex": revenue * 0.13,
                    "depreciation_and_amortization": revenue * 0.02,
                    "weighted_average_diluted_shares": 100.0,
                    "accounts_receivable": revenue * 0.12,
                    "inventory": revenue * 0.08,
                    "accounts_payable": revenue * 0.06,
                    "cash_and_cash_equivalents": revenue * 0.005,
                    "current_debt": None,
                    "long_term_debt": None,
                    "total_debt": None,
                    "interest_expense": 0.0,
                    "interest_income": 0.0,
                    "stock_based_compensation": revenue * 0.005,
                },
            )
        )
    return statements


def _multi_tranche_driver_statements() -> list[SimpleNamespace]:
    return [
        _driver_forecast_statement(
            2023,
            900.0,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            cash_balance=24.0,
            current_debt=18.0,
            long_term_debt=162.0,
            total_debt=180.0,
            extra_data={
                "revolver_debt": 24.0,
                "term_loan_debt": 68.0,
                "notes_bonds_debt": 73.0,
                "lease_liabilities": 15.0,
                "revolver_interest_rate": 0.060,
                "term_loan_interest_rate": 0.055,
                "notes_interest_rate": 0.0475,
                "lease_interest_rate": 0.040,
                "term_loan_mandatory_amortization": 8.0,
                "notes_maturity_repayment": 0.0,
                "lease_principal_payment": 4.0,
                "current_maturities_debt": 12.0,
            },
        ),
        _driver_forecast_statement(
            2024,
            1000.0,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            cash_balance=20.0,
            current_debt=18.0,
            long_term_debt=167.0,
            total_debt=185.0,
            extra_data={
                "revolver_debt": 26.0,
                "term_loan_debt": 69.0,
                "notes_bonds_debt": 75.0,
                "lease_liabilities": 15.0,
                "revolver_interest_rate": 0.060,
                "term_loan_interest_rate": 0.055,
                "notes_interest_rate": 0.0475,
                "lease_interest_rate": 0.040,
                "term_loan_mandatory_amortization": 8.0,
                "notes_maturity_repayment": 0.0,
                "lease_principal_payment": 4.0,
                "current_maturities_debt": 12.0,
            },
        ),
        _driver_forecast_statement(
            2025,
            1100.0,
            receivables_days=55.0,
            inventory_days=32.0,
            payable_days=28.0,
            cash_balance=120.0,
            current_debt=18.0,
            long_term_debt=172.0,
            total_debt=190.0,
            extra_data={
                "revolver_debt": 30.0,
                "term_loan_debt": 70.0,
                "notes_bonds_debt": 75.0,
                "lease_liabilities": 15.0,
                "revolver_interest_rate": 0.060,
                "term_loan_interest_rate": 0.055,
                "notes_interest_rate": 0.0475,
                "lease_interest_rate": 0.040,
                "term_loan_mandatory_amortization": 8.0,
                "notes_maturity_repayment": 12.0,
                "lease_principal_payment": 4.0,
                "current_maturities_debt": 12.0,
            },
        ),
    ]


def _explicit_dilution_driver_statements() -> list[SimpleNamespace]:
    return [
        _statement(
            2023,
            {
                "revenue": 900.0,
                "gross_profit": 405.0,
                "operating_income": 135.0,
                "pretax_income": 108.0,
                "income_tax_expense": 21.6,
                "net_income": 86.4,
                "operating_cash_flow": 126.0,
                "free_cash_flow": 81.0,
                "capex": 45.0,
                "depreciation_and_amortization": 27.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 108.0,
                "inventory": 45.0,
                "accounts_payable": 63.0,
                "current_assets": 360.0,
                "current_liabilities": 180.0,
                "total_assets": 990.0,
                "cash_and_cash_equivalents": 90.0,
                "total_debt": 135.0,
                "interest_expense": 7.2,
                "interest_income": 0.9,
                "other_income_expense": 0.0,
                "stock_based_compensation": 13.5,
                "share_buybacks": 18.0,
                "rsu_shares": 2.0,
                "acquisition_shares_issued": 1.0,
                "shares_repurchased": 1.5,
                "share_price": 20.0,
                "option_warrant_dilution_shares": 2.0,
                "convertible_dilution_shares": 1.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1000.0,
                "gross_profit": 450.0,
                "operating_income": 150.0,
                "pretax_income": 120.0,
                "income_tax_expense": 24.0,
                "net_income": 96.0,
                "operating_cash_flow": 140.0,
                "free_cash_flow": 90.0,
                "capex": 50.0,
                "depreciation_and_amortization": 30.0,
                "weighted_average_shares_basic": 99.0,
                "weighted_average_diluted_shares": 102.0,
                "accounts_receivable": 120.0,
                "inventory": 50.0,
                "accounts_payable": 70.0,
                "current_assets": 400.0,
                "current_liabilities": 200.0,
                "total_assets": 1100.0,
                "cash_and_cash_equivalents": 100.0,
                "total_debt": 150.0,
                "interest_expense": 8.0,
                "interest_income": 1.0,
                "other_income_expense": 0.0,
                "stock_based_compensation": 15.0,
                "share_buybacks": 20.0,
                "rsu_shares": 2.2,
                "acquisition_shares_issued": 1.2,
                "shares_repurchased": 1.4,
                "share_price": 22.0,
                "option_warrant_dilution_shares": 2.1,
                "convertible_dilution_shares": 1.1,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1100.0,
                "gross_profit": 495.0,
                "operating_income": 165.0,
                "pretax_income": 132.0,
                "income_tax_expense": 26.4,
                "net_income": 105.6,
                "operating_cash_flow": 154.0,
                "free_cash_flow": 99.0,
                "capex": 55.0,
                "depreciation_and_amortization": 33.0,
                "weighted_average_shares_basic": 100.0,
                "weighted_average_diluted_shares": 104.0,
                "accounts_receivable": 132.0,
                "inventory": 55.0,
                "accounts_payable": 77.0,
                "current_assets": 440.0,
                "current_liabilities": 220.0,
                "total_assets": 1210.0,
                "cash_and_cash_equivalents": 110.0,
                "total_debt": 165.0,
                "interest_expense": 8.8,
                "interest_income": 1.1,
                "other_income_expense": 0.0,
                "stock_based_compensation": 16.5,
                "share_buybacks": 22.0,
                "rsu_shares": 2.4,
                "acquisition_shares_issued": 1.1,
                "shares_repurchased": 1.3,
                "share_price": 24.0,
                "option_warrant_dilution_shares": 2.2,
                "convertible_dilution_shares": 1.2,
            },
        ),
    ]


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


def _card_series_by_key(
    card: charts_service.CompanyChartsCardPayload,
    key: str,
) -> charts_service.CompanyChartsSeriesPayload:
    return next(item for item in card.series if item.key == key)


def _first_series_value(card: charts_service.CompanyChartsCardPayload, key: str) -> float:
    value = _card_series_by_key(card, key).points[0].value
    assert isinstance(value, (int, float))
    return float(value)


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
    assert response.forecast_methodology.label == "Driver-based integrated forecast"
    assert {series.label for series in response.cards.revenue.series[1:]} == {"Base Forecast", "Bull Forecast", "Bear Forecast"}
    assert response.cards.forecast_calculations is not None
    assert any(item.label == "Management Guidance" for item in response.cards.forecast_assumptions.items)
    assert any(item.label == "Operating Working Capital" for item in response.cards.forecast_assumptions.items)
    assert any(item.label == "Below-The-Line Bridge" for item in response.cards.forecast_assumptions.items)
    assert any(item.label == "Fixed-Capital Reinvestment" for item in response.cards.forecast_assumptions.items)
    assert any(item.label == "Growth Sensitivity" for item in response.cards.forecast_calculations.items)
    assert any(item.label == "Pretax Income Formula" for item in response.cards.forecast_calculations.items)
    assert any(item.label == "Operating Cash Flow Formula" for item in response.cards.forecast_calculations.items)
    calculation_items = {item.key: item for item in response.cards.forecast_calculations.items}
    assert calculation_items["formula_reinvestment"].label == "Capex Formula"
    assert calculation_items["formula_reinvestment"].value == driver_model.FORECAST_FORMULA_CAPEX
    assert "flows through OCF, not capex" in str(calculation_items["formula_reinvestment"].detail)
    assert calculation_items["formula_ocf"].value == driver_model.FORECAST_FORMULA_OCF
    assert "delta operating WC" in str(calculation_items["formula_ocf"].detail)
    assert response.cards.revenue_outlook_bridge is not None
    assert response.cards.margin_path is not None
    assert response.cards.fcf_outlook is not None
    assert response.cards.revenue.title == "Revenue"
    assert response.cards.cash_flow_metric.title == "Cash Flow Metrics"
    expected_stability_label = f"Forecast stability: {charts_service._stability_label(response.forecast_diagnostics.final_score)}"
    assert response.forecast_methodology.stability_label == expected_stability_label
    assert response.forecast_methodology.confidence_label == response.forecast_methodology.stability_label


def test_build_company_charts_dashboard_response_populates_new_card_math_from_driver_bundle(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    bundle = driver_model.build_driver_forecast_bundle(statements, [release])
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    assert bundle is not None

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.cards.revenue_outlook_bridge is not None
    assert response.cards.margin_path is not None
    assert response.cards.fcf_outlook is not None

    revenue_bridge = response.cards.revenue_outlook_bridge
    start_value = _first_series_value(revenue_bridge, "revenue_bridge_start")
    end_value = _first_series_value(revenue_bridge, "revenue_bridge_end")
    component_total = sum(
        float(point.value or 0.0)
        for series in revenue_bridge.series
        if series.key not in {"revenue_bridge_start", "revenue_bridge_end"}
        for point in series.points
    )
    assert end_value == pytest.approx(start_value + component_total, abs=0.25)

    margin_path = response.cards.margin_path
    gross_margin_actual = _first_series_value(margin_path, "gross_margin_actual")
    gross_margin_forecast = _first_series_value(margin_path, "gross_margin_forecast")
    operating_margin_forecast = _first_series_value(margin_path, "operating_margin_forecast")
    net_margin_forecast = _first_series_value(margin_path, "net_margin_forecast")
    assert gross_margin_actual == pytest.approx(0.45, abs=1e-6)
    assert gross_margin_forecast == pytest.approx(bundle.projected_gross_margin or 0.0, abs=1e-6)
    assert operating_margin_forecast == pytest.approx(bundle.scenarios["base"].operating_income.values[0] / bundle.scenarios["base"].revenue.values[0], abs=1e-4)
    assert net_margin_forecast == pytest.approx(bundle.scenarios["base"].net_income.values[0] / bundle.scenarios["base"].revenue.values[0], abs=1e-4)

    fcf_outlook = response.cards.fcf_outlook
    forecast_net_income = _first_series_value(fcf_outlook, "fcf_net_income_forecast")
    forecast_depreciation = _first_series_value(fcf_outlook, "fcf_depreciation_forecast")
    forecast_sbc = _first_series_value(fcf_outlook, "fcf_sbc_forecast")
    forecast_delta_wc = _first_series_value(fcf_outlook, "fcf_delta_wc_forecast")
    forecast_ocf = _first_series_value(fcf_outlook, "fcf_ocf_forecast")
    forecast_capex = _first_series_value(fcf_outlook, "fcf_capex_forecast")
    forecast_fcf = _first_series_value(fcf_outlook, "fcf_fcf_forecast")
    assert forecast_ocf == pytest.approx(forecast_net_income + forecast_depreciation + forecast_sbc - forecast_delta_wc, abs=0.25)
    assert forecast_fcf == pytest.approx(forecast_ocf - forecast_capex, abs=0.25)


def test_build_fcf_outlook_card_falls_back_to_base_cash_series_when_driver_bridge_is_missing():
    forecast_year = 2026
    profit_series = [
        charts_service._series(
            "net_income_forecast",
            "Net Income Base",
            "usd",
            "line",
            "forecast",
            "dashed",
            [
                charts_service.CompanyChartsSeriesPointPayload(
                    period_label=f"FY{forecast_year}E",
                    fiscal_year=forecast_year,
                    period_end=None,
                    value=125.0,
                    series_kind="forecast",
                )
            ],
        )
    ]
    cash_series = [
        charts_service._series(
            "operating_cash_flow_forecast",
            "Operating CF Base",
            "usd",
            "line",
            "forecast",
            "dashed",
            [
                charts_service.CompanyChartsSeriesPointPayload(
                    period_label=f"FY{forecast_year}E",
                    fiscal_year=forecast_year,
                    period_end=None,
                    value=180.0,
                    series_kind="forecast",
                )
            ],
        ),
        charts_service._series(
            "capex_forecast",
            "Capex Base",
            "usd",
            "line",
            "forecast",
            "dashed",
            [
                charts_service.CompanyChartsSeriesPointPayload(
                    period_label=f"FY{forecast_year}E",
                    fiscal_year=forecast_year,
                    period_end=None,
                    value=55.0,
                    series_kind="forecast",
                )
            ],
        ),
        charts_service._series(
            "free_cash_flow_forecast",
            "Free CF Base",
            "usd",
            "line",
            "forecast",
            "dashed",
            [
                charts_service.CompanyChartsSeriesPointPayload(
                    period_label=f"FY{forecast_year}E",
                    fiscal_year=forecast_year,
                    period_end=None,
                    value=125.0,
                    series_kind="forecast",
                )
            ],
        ),
    ]
    driver_bundle = SimpleNamespace(scenarios={"base": SimpleNamespace(bridge=[])} )

    card = charts_service._build_fcf_outlook_card([], profit_series, cash_series, driver_bundle)

    assert card is not None
    assert {series.key for series in card.series} == {
        "fcf_net_income_forecast",
        "fcf_ocf_forecast",
        "fcf_capex_forecast",
        "fcf_fcf_forecast",
    }
    assert any("detailed bridge payload was unavailable" in highlight for highlight in card.highlights)


def _projection_section(
    studio: charts_service.CompanyChartsProjectionStudioPayload,
    key: str,
) -> charts_service.CompanyChartsScheduleSectionPayload:
    return next(section for section in studio.schedule_sections if section.key == key)



def _projection_row(
    studio: charts_service.CompanyChartsProjectionStudioPayload,
    section_key: str,
    row_key: str,
) -> charts_service.CompanyChartsProjectedRowPayload:
    section = _projection_section(studio, section_key)
    return next(row for row in section.rows if row.key == row_key)



def test_build_company_charts_dashboard_response_populates_projection_studio_from_driver_traces(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.projection_studio is not None
    assert [section.title for section in response.projection_studio.schedule_sections] == [
        "Income Statement",
        "Balance Sheet",
        "Cash Flow Statement",
    ]
    assert response.projection_studio.drivers_used
    assert len(response.projection_studio.scenarios_comparison) == 5
    assert len(response.projection_studio.sensitivity_matrix) == 25
    base_cell = next(cell for cell in response.projection_studio.sensitivity_matrix if cell.is_base)
    assert base_cell.eps == pytest.approx(response.cards.eps.series[1].points[0].value or 0.0, abs=1e-6)



def test_build_company_charts_dashboard_response_sets_projection_studio_none_when_driver_detail_is_unavailable(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "build_driver_forecast_bundle", lambda *_args, **_kwargs: None)

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.projection_studio is None



def test_projection_studio_schedule_rows_map_to_actual_and_forecast_values(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)
    bundle = driver_model.build_driver_forecast_bundle(statements, [release])

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.projection_studio is not None
    assert bundle is not None

    revenue_row = _projection_row(response.projection_studio, "income_statement", "revenue")
    ar_row = _projection_row(response.projection_studio, "balance_sheet", "accounts_receivable")
    capex_row = _projection_row(response.projection_studio, "cash_flow_statement", "capex")
    first_year = bundle.scenarios["base"].revenue.years[0]

    assert revenue_row.reported_values[2025] == pytest.approx(1100.0, abs=1e-6)
    assert revenue_row.projected_values[first_year] == pytest.approx(charts_service._round(bundle.scenarios["base"].revenue.values[0], 2) or 0.0, abs=1e-6)
    assert ar_row.projected_values[first_year] == pytest.approx(charts_service._round(bundle.line_traces["accounts_receivable"][first_year].result_value, 2) or 0.0, abs=1e-6)
    assert capex_row.projected_values[first_year] == pytest.approx(charts_service._round(bundle.scenarios["base"].capex.values[0], 2) or 0.0, abs=1e-6)



def test_projection_studio_formula_trace_payloads_match_source_traces(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)
    bundle = driver_model.build_driver_forecast_bundle(statements, [release])

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.projection_studio is not None
    assert bundle is not None

    first_year = bundle.scenarios["base"].revenue.years[0]
    source_trace = bundle.line_traces["revenue"][first_year]
    payload_trace = _projection_row(response.projection_studio, "income_statement", "revenue").formula_traces[first_year]

    assert payload_trace.formula_template == source_trace.formula_template
    assert payload_trace.formula_computation == source_trace.formula_computation
    assert payload_trace.confidence == source_trace.confidence
    assert payload_trace.inputs[0].source_detail == source_trace.inputs[0].source_detail
    assert payload_trace.result_value == pytest.approx(source_trace.result_value or 0.0, abs=1e-6)



def test_company_charts_dashboard_response_round_trips_new_cards_through_snapshot_payload(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    round_trip = charts_service.CompanyChartsDashboardResponse.model_validate(response.model_dump(mode="json"))

    assert round_trip.cards.revenue_outlook_bridge is not None
    assert round_trip.cards.margin_path is not None
    assert round_trip.cards.fcf_outlook is not None
    assert round_trip.projection_studio is not None
    assert _first_series_value(round_trip.cards.revenue_outlook_bridge, "revenue_bridge_end") == pytest.approx(
        _first_series_value(response.cards.revenue_outlook_bridge, "revenue_bridge_end"),
        abs=1e-6,
    )
    assert _first_series_value(round_trip.cards.margin_path, "gross_margin_forecast") == pytest.approx(
        _first_series_value(response.cards.margin_path, "gross_margin_forecast"),
        abs=1e-6,
    )
    assert _first_series_value(round_trip.cards.fcf_outlook, "fcf_fcf_forecast") == pytest.approx(
        _first_series_value(response.cards.fcf_outlook, "fcf_fcf_forecast"),
        abs=1e-6,
    )
    assert len(round_trip.projection_studio.sensitivity_matrix) == 25
    assert _projection_row(round_trip.projection_studio, "income_statement", "revenue").projected_values == _projection_row(
        response.projection_studio,
        "income_statement",
        "revenue",
    ).projected_values


def test_build_company_charts_dashboard_response_populates_event_overlay_and_quarter_change(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = SimpleNamespace(
        id=41,
        filing_acceptance_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        filing_date=date(2026, 1, 20),
        reported_period_end=date(2025, 12, 31),
        revenue_guidance_low=1220.0,
        revenue_guidance_high=1260.0,
        eps_guidance_low=1.1,
        eps_guidance_high=1.2,
        share_repurchase_amount=22000000.0,
        source_url="https://www.sec.gov/ixviewer/earnings",
        last_checked=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )
    restatement = SimpleNamespace(
        id=90,
        filing_acceptance_at=datetime(2026, 2, 8, tzinfo=timezone.utc),
        filing_date=date(2026, 2, 8),
        period_end=date(2024, 12, 31),
        changed_metric_keys=["revenue", "net_income"],
        source="https://www.sec.gov/ixviewer/restatement",
        last_checked=datetime(2026, 2, 8, tzinfo=timezone.utc),
    )
    capital_event = SimpleNamespace(
        id=77,
        filing_date=date(2026, 3, 1),
        report_date=None,
        event_type="acquisition",
        summary="Completed acquisition of a strategic platform business.",
        source_url="https://www.sec.gov/ixviewer/m-and-a",
        last_checked=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [restatement])
    monkeypatch.setattr(charts_service, "get_company_capital_markets_events", lambda *_args, **_kwargs: [capital_event])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    event_types = {event.event_type for event in response.event_overlay.events}
    assert {"earnings", "guidance", "buyback", "restatement", "major_m_and_a"}.issubset(event_types)
    assert response.quarter_change.empty_state is None
    assert response.quarter_change.items
    assert response.quarter_change.latest_period_label == "FY2025"
    assert response.chart_spec is not None
    assert response.chart_spec.outlook.event_overlay.events


def test_build_company_charts_dashboard_response_event_overlay_sparse_fallback(monkeypatch):
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
        _statement(2024, {"revenue": 1000.0, "net_income": 130.0, "eps": 1.2, "free_cash_flow": 105.0, "share_buybacks": 8.5, "acquisitions": 0.0}),
        _statement(2025, {"revenue": 1110.0, "net_income": 142.0, "eps": 1.33, "free_cash_flow": 117.0, "share_buybacks": 12.0, "acquisitions": 18.0}),
    ]
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.6, drift=0.02)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_capital_markets_events", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    event_types = {event.event_type for event in response.event_overlay.events}
    assert "buyback" in event_types
    assert "major_m_and_a" in event_types
    assert response.event_overlay.sparse_data_note is not None
    assert response.quarter_change.empty_state is None


def test_build_metric_diff_payload_prefers_restatement_source() -> None:
    latest = _statement(2025, {"revenue": 1200.0})
    prior = _statement(2024, {"revenue": 1000.0})
    restatement = SimpleNamespace(
        filing_acceptance_at=datetime(2026, 2, 8, tzinfo=timezone.utc),
        filing_date=date(2026, 2, 8),
        filing_type="10-K/A",
        period_end=date(2024, 12, 31),
        changed_metric_keys=["revenue", "net_income"],
    )
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))

    payload = charts_service._build_metric_diff_payload(
        metric_key="revenue",
        metric_label="Revenue",
        current_value=1200.0,
        previous_value=1000.0,
        latest_statement=latest,
        prior_statement=prior,
        restatements=[restatement],
        snapshot=snapshot,
    )

    assert payload.absolute_change == pytest.approx(200.0)
    assert payload.percentage_change == pytest.approx(0.2)
    assert payload.source is not None
    assert payload.source.source_label == "SEC restatement filing"
    assert payload.source.filing_type == "10-K/A"
    assert "revenue" in payload.changed_input_fields


def test_build_metric_diff_payload_uses_latest_filing_source_for_new_filing() -> None:
    latest = _statement(2025, {"eps": 2.4})
    prior = _statement(2024, {"eps": 2.0})
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))

    payload = charts_service._build_metric_diff_payload(
        metric_key="eps",
        metric_label="EPS",
        current_value=2.4,
        previous_value=2.0,
        latest_statement=latest,
        prior_statement=prior,
        restatements=[],
        snapshot=snapshot,
    )

    assert payload.source is not None
    assert payload.source.source_id == "sec_companyfacts"
    assert payload.source.source_label == "Official filing snapshot"
    assert payload.source.filing_type == "10-K"
    assert payload.previous_value_missing is False


def test_build_metric_diff_payload_marks_stale_cache() -> None:
    latest = _statement(2025, {"free_cash_flow": 180.0})
    prior = _statement(2024, {"free_cash_flow": 150.0})
    snapshot = SimpleNamespace(cache_state="stale", last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc))

    payload = charts_service._build_metric_diff_payload(
        metric_key="free_cash_flow",
        metric_label="Free cash flow",
        current_value=180.0,
        previous_value=150.0,
        latest_statement=latest,
        prior_statement=prior,
        restatements=[],
        snapshot=snapshot,
    )

    assert payload.stale_cache is True
    assert payload.source is not None
    assert payload.source.detail is not None
    assert "stale" in payload.source.detail.lower()


def test_build_metric_diff_payload_handles_missing_previous_value() -> None:
    latest = _statement(2025, {"revenue": 980.0})
    prior = _statement(2024, {"revenue": None})
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))

    payload = charts_service._build_metric_diff_payload(
        metric_key="revenue",
        metric_label="Revenue",
        current_value=980.0,
        previous_value=None,
        latest_statement=latest,
        prior_statement=prior,
        restatements=[],
        snapshot=snapshot,
    )

    assert payload.previous_value_missing is True
    assert payload.previous_value is None
    assert payload.absolute_change is None
    assert payload.percentage_change is None


def test_build_company_charts_dashboard_response_applies_what_if_overrides_and_surfaces_trace_metadata(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    baseline_response = charts_service.build_company_charts_dashboard_response(
        fake_session,
        1,
        generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    scenario_response = charts_service.build_company_charts_dashboard_response(
        fake_session,
        1,
        generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc),
        what_if_request=charts_service.CompanyChartsWhatIfRequest(
            overrides={
                "price_growth": 0.08,
                "dso": 70.0,
            }
        ),
    )

    assert baseline_response is not None
    assert baseline_response.projection_studio is not None
    assert scenario_response is not None
    assert scenario_response.projection_studio is not None
    assert scenario_response.what_if is not None

    forecast_year = scenario_response.what_if.impact_summary.forecast_year
    assert forecast_year is not None
    baseline_revenue = _projection_row(baseline_response.projection_studio, "income_statement", "revenue").projected_values[forecast_year]
    scenario_revenue = _projection_row(scenario_response.projection_studio, "income_statement", "revenue").projected_values[forecast_year]
    assert scenario_revenue != baseline_revenue

    applied_keys = {item.key for item in scenario_response.what_if.overrides_applied}
    assert applied_keys == {"price_growth", "dso"}
    control_keys = {item.key for item in scenario_response.what_if.driver_control_metadata}
    assert {"price_growth", "dso", "variable_cost_ratio", "sales_to_capital"}.issubset(control_keys)
    price_control = next(item for item in scenario_response.what_if.driver_control_metadata if item.key == "price_growth")
    assert price_control.current_value == pytest.approx(0.08, abs=1e-6)

    revenue_trace = _projection_row(scenario_response.projection_studio, "income_statement", "revenue").formula_traces[forecast_year]
    assert revenue_trace.scenario_state == "user_override"
    assert any(input_item.is_override and input_item.key == "price_growth" for input_item in revenue_trace.inputs)

    receivables_trace = _projection_row(scenario_response.projection_studio, "balance_sheet", "accounts_receivable").formula_traces[forecast_year]
    assert receivables_trace.scenario_state == "user_override"
    assert any(input_item.is_override and input_item.key == "accounts_receivable_days" for input_item in receivables_trace.inputs)


def test_build_company_charts_dashboard_response_clips_out_of_range_what_if_overrides(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(
        fake_session,
        1,
        generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc),
        what_if_request=charts_service.CompanyChartsWhatIfRequest(
            overrides={
                "price_growth": 0.5,
                "dso": 500.0,
            }
        ),
    )

    assert response is not None
    assert response.what_if is not None
    clipped_keys = {item.key for item in response.what_if.overrides_clipped}
    assert clipped_keys == {"price_growth", "dso"}

    clipped_price = next(item for item in response.what_if.overrides_clipped if item.key == "price_growth")
    clipped_dso = next(item for item in response.what_if.overrides_clipped if item.key == "dso")
    assert clipped_price.applied_value == pytest.approx(driver_model.PRICE_GROWTH_CAP, abs=1e-6)
    assert clipped_dso.applied_value == pytest.approx(driver_model.DSO_CAP, abs=1e-6)


def test_company_charts_what_if_request_rejects_unknown_or_non_numeric_overrides() -> None:
    with pytest.raises(ValidationError, match="Unsupported override keys: mystery_driver"):
        charts_service.CompanyChartsWhatIfRequest.model_validate({"overrides": {"mystery_driver": 0.1}})

    with pytest.raises(ValidationError):
        charts_service.CompanyChartsWhatIfRequest.model_validate({"overrides": {"dso": "not-a-number"}})


def _assert_base_bridge_formulas(bundle: driver_model.DriverForecastBundle, statements: list[SimpleNamespace]) -> tuple[driver_model.DriverForecastScenario, driver_model._ForecastBridgePoint]:
    base_scenario = bundle.scenarios["base"]
    bridge = base_scenario.bridge[0]
    history = driver_model._normalize_statements(statements)
    cost_schedule = driver_model._derive_cost_schedule(history)
    reinvestment_schedule = driver_model._derive_reinvestment_schedule(history, cost_schedule)
    below_line_schedule = driver_model._derive_below_line_schedule(history)
    next_revenue = base_scenario.revenue.values[0]
    previous_revenue = history[-1]["revenue"] or 0.0
    variable_cost_ratio = driver_model._clip(
        cost_schedule.variable_cost_ratio,
        driver_model.VARIABLE_COST_RATIO_FLOOR,
        driver_model.VARIABLE_COST_RATIO_CAP,
    )
    variable_cost = next_revenue * variable_cost_ratio
    target_semi_ratio = driver_model._clip(
        cost_schedule.semi_variable_cost_ratio,
        driver_model.SEMI_VARIABLE_COST_RATIO_FLOOR,
        driver_model.SEMI_VARIABLE_COST_RATIO_CAP,
    )
    semi_cost = previous_revenue * cost_schedule.semi_variable_cost_ratio
    semi_cost = max(0.0, semi_cost * (1.0 + (base_scenario.revenue_growth.values[0] * 0.55)))
    semi_cost = (semi_cost * 0.55) + ((next_revenue * target_semi_ratio) * 0.45)
    fixed_cost_growth = driver_model._clip(
        cost_schedule.fixed_cost_growth,
        driver_model.FIXED_COST_GROWTH_FLOOR,
        driver_model.FIXED_COST_GROWTH_CAP,
    )
    fixed_cost = max(0.0, cost_schedule.fixed_cost_base * (1.0 + fixed_cost_growth))
    growth_reinvestment = max(next_revenue - previous_revenue, 0.0) / reinvestment_schedule.sales_to_capital
    expected_depreciation = min(
        reinvestment_schedule.ppe_schedule.opening_net_ppe * reinvestment_schedule.depreciation_ratio,
        reinvestment_schedule.ppe_schedule.opening_net_ppe + (next_revenue * reinvestment_schedule.capex_intensity) - reinvestment_schedule.ppe_schedule.annual_disposals,
    )
    maintenance_capex = max(next_revenue * reinvestment_schedule.capex_intensity, bridge.depreciation)

    assert bridge.ebit == pytest.approx(next_revenue - variable_cost - semi_cost - fixed_cost, abs=1e-6)
    assert bridge.ebit == pytest.approx(base_scenario.operating_income.values[0], abs=1e-6)
    assert bridge.depreciation == pytest.approx(expected_depreciation, abs=1e-6)
    assert bridge.pretax_income == pytest.approx(
        bridge.ebit - bridge.interest_expense + bridge.interest_income + bridge.other_income_expense,
        abs=1e-6,
    )
    expected_tax_point = driver_model._project_tax_schedule(
        bridge.pretax_income,
        below_line_schedule.tax_schedule,
        opening_nol=bridge.beginning_nol,
        opening_deferred_tax_asset=bridge.beginning_deferred_tax_asset,
    )
    assert bridge.taxes == pytest.approx(expected_tax_point.book_tax_expense, abs=1e-6)
    assert bridge.cash_tax == pytest.approx(expected_tax_point.cash_tax, abs=1e-6)
    assert bridge.deferred_tax_expense == pytest.approx(expected_tax_point.deferred_tax_expense, abs=1e-6)
    assert bridge.ending_nol == pytest.approx(bridge.beginning_nol + bridge.nol_created - bridge.nol_used, abs=1e-6)
    assert bridge.net_income == pytest.approx(bridge.pretax_income - bridge.taxes, abs=1e-6)
    assert bridge.operating_cash_flow == pytest.approx(
        bridge.net_income + bridge.depreciation + bridge.stock_based_compensation + bridge.deferred_tax_expense - bridge.delta_working_capital,
        abs=1e-6,
    )
    assert bridge.capex == pytest.approx(
        max(maintenance_capex, bridge.depreciation + growth_reinvestment),
        abs=1e-6,
    )
    assert bridge.ending_net_ppe == pytest.approx(
        bridge.beginning_net_ppe + bridge.capex - bridge.depreciation - bridge.ppe_disposals,
        abs=1e-6,
    )
    assert bridge.free_cash_flow == pytest.approx(bridge.operating_cash_flow - bridge.capex, abs=1e-6)
    assert bridge.beginning_debt == pytest.approx(sum(tranche.opening_balance for tranche in bridge.debt_tranches), abs=1e-6)
    assert bridge.ending_debt == pytest.approx(sum(tranche.ending_balance for tranche in bridge.debt_tranches), abs=1e-6)
    assert bridge.interest_expense == pytest.approx(
        sum(tranche.average_balance * tranche.interest_rate for tranche in bridge.debt_tranches),
        abs=1e-6,
    )
    assert bridge.ending_retained_earnings == pytest.approx(
        bridge.beginning_retained_earnings + bridge.net_income - bridge.dividends - bridge.buyback_cash,
        abs=1e-6,
    )
    assert bridge.balance_sheet_delta == pytest.approx(
        bridge.total_assets - bridge.total_liabilities_and_equity,
        abs=1e-6,
    )
    assert base_scenario.net_income.values[0] == pytest.approx(bridge.net_income, abs=1e-6)
    assert base_scenario.operating_cash_flow.values[0] == pytest.approx(bridge.operating_cash_flow, abs=1e-6)
    assert base_scenario.capex.values[0] == pytest.approx(bridge.capex, abs=1e-6)
    assert base_scenario.free_cash_flow.values[0] == pytest.approx(bridge.free_cash_flow, abs=1e-6)
    return base_scenario, bridge


def _trace_input_value(trace: driver_model.FormulaTrace, key: str) -> float:
    value = next(item.value for item in trace.inputs if item.key == key)
    assert value is not None
    return float(value)


def _assert_trace_math(trace: driver_model.FormulaTrace) -> None:
    if trace.line_item == "revenue":
        expected = _trace_input_value(trace, "previous_revenue") * (1.0 + _trace_input_value(trace, "applied_growth"))
    elif trace.line_item == "cost_of_revenue":
        expected = max(
            _trace_input_value(trace, "revenue") * _trace_input_value(trace, "cost_of_revenue_ratio"),
            _trace_input_value(trace, "variable_cost"),
        )
    elif trace.line_item == "gross_profit":
        expected = _trace_input_value(trace, "revenue") - _trace_input_value(trace, "cost_of_revenue")
    elif trace.line_item == "operating_income":
        expected = (
            _trace_input_value(trace, "revenue")
            - _trace_input_value(trace, "variable_cost")
            - _trace_input_value(trace, "semi_variable_cost")
            - _trace_input_value(trace, "fixed_cost")
        )
    elif trace.line_item == "pretax_income":
        expected = (
            _trace_input_value(trace, "ebit")
            - _trace_input_value(trace, "interest_expense")
            + _trace_input_value(trace, "interest_income")
            + _trace_input_value(trace, "other_income_expense")
        )
    elif trace.line_item == "income_tax":
        expected = _trace_input_value(trace, "cash_tax") + _trace_input_value(trace, "deferred_tax_expense")
    elif trace.line_item == "net_income":
        expected = _trace_input_value(trace, "pretax_income") - _trace_input_value(trace, "taxes")
    elif trace.line_item == "accounts_receivable":
        expected = driver_model._days_to_balance(
            _trace_input_value(trace, "revenue"),
            _trace_input_value(trace, "accounts_receivable_days"),
        )
    elif trace.line_item == "inventory":
        expected = driver_model._days_to_balance(
            _trace_input_value(trace, "cost_of_revenue"),
            _trace_input_value(trace, "inventory_days"),
        )
    elif trace.line_item == "accounts_payable":
        expected = driver_model._days_to_balance(
            _trace_input_value(trace, "cost_of_revenue"),
            _trace_input_value(trace, "accounts_payable_days"),
        )
    elif trace.line_item == "deferred_revenue":
        expected = driver_model._days_to_balance(
            _trace_input_value(trace, "revenue"),
            _trace_input_value(trace, "deferred_revenue_days"),
        )
    elif trace.line_item == "accrued_operating_liabilities":
        expected = driver_model._days_to_balance(
            _trace_input_value(trace, "cash_operating_cost"),
            _trace_input_value(trace, "accrued_operating_liabilities_days"),
        )
    elif trace.line_item == "depreciation_amortization":
        expected = _trace_input_value(trace, "opening_net_ppe") / _trace_input_value(trace, "useful_life_years")
    elif trace.line_item == "net_ppe":
        expected = (
            _trace_input_value(trace, "opening_net_ppe")
            + _trace_input_value(trace, "capex")
            - _trace_input_value(trace, "depreciation_amortization")
            - _trace_input_value(trace, "ppe_disposals")
        )
    elif trace.line_item == "sbc_expense":
        expected = _trace_input_value(trace, "revenue") * _trace_input_value(trace, "sbc_ratio")
    elif trace.line_item == "capex":
        expected = max(
            _trace_input_value(trace, "maintenance_capex"),
            _trace_input_value(trace, "depreciation_amortization") + _trace_input_value(trace, "growth_reinvestment"),
        )
    elif trace.line_item == "operating_cash_flow":
        expected = (
            _trace_input_value(trace, "net_income")
            + _trace_input_value(trace, "depreciation")
            + _trace_input_value(trace, "stock_based_compensation")
            + _trace_input_value(trace, "deferred_tax_expense")
            - _trace_input_value(trace, "delta_operating_working_capital")
        )
    elif trace.line_item == "free_cash_flow":
        expected = _trace_input_value(trace, "operating_cash_flow") - _trace_input_value(trace, "capex")
    elif trace.line_item == "diluted_shares":
        expected = sum(item.value or 0.0 for item in trace.inputs)
    elif trace.line_item == "eps":
        expected = _trace_input_value(trace, "net_income") / _trace_input_value(trace, "diluted_shares")
    else:
        raise AssertionError(f"Unhandled trace line item: {trace.line_item}")

    assert trace.result_value == pytest.approx(expected, abs=1e-6)


def test_top_down_revenue_projection_uses_driver_stack_and_guidance_overlay():
    history = driver_model._normalize_statements(_standard_driver_regression_statements())
    drivers = driver_model._RevenueDrivers(
        mode="top_down_proxy_decomposition+guidance",
        segment_basis=None,
        pricing_growth_proxy=0.04,
        residual_market_growth=0.08,
        share_shift_proxy=0.03,
        volume_growth_proxy=0.0,
        guidance_anchor=1300.0,
        backlog_floor_growth=None,
        capacity_growth_cap=None,
        utilization_ratio=None,
        segment_profiles=[],
    )

    projection = driver_model._top_down_revenue_projection(
        history,
        drivers,
        driver_model._scenario_tweaks()["base"],
        latest_year=2025,
        horizon_years=1,
    )

    expected_demand_growth = 0.08 + ((driver_model.TERMINAL_MARKET_GROWTH - 0.08) * 0.30)
    expected_share_change = 0.03 + ((0.0 - 0.03) * 0.40)
    expected_price_growth = 0.04 + ((driver_model.TERMINAL_PRICE_GROWTH - 0.04) * 0.35)
    expected_raw_growth = expected_demand_growth + expected_share_change + expected_price_growth + (expected_demand_growth * expected_price_growth)
    expected_guided_growth = (1300.0 / 1100.0) - 1.0
    expected_growth = (expected_raw_growth * 0.35) + (expected_guided_growth * 0.65)
    year, revenue, growth = projection[0]

    assert year == 2026
    assert revenue == pytest.approx(1100.0 * (1.0 + expected_growth), abs=1e-6)
    assert growth == pytest.approx(expected_growth, abs=1e-6)


def test_driver_forecast_bundle_normalizes_partial_segment_coverage_before_bottom_up_rollup():
    statements = [
        _driver_forecast_statement(2023, 1000.0, receivables_days=52.0, inventory_days=34.0, payable_days=28.0),
        _driver_forecast_statement(2024, 1100.0, receivables_days=52.0, inventory_days=34.0, payable_days=28.0),
        _driver_forecast_statement(2025, 1210.0, receivables_days=52.0, inventory_days=34.0, payable_days=28.0),
    ]
    segment_payloads = [
        [
            {"segment_id": "client", "segment_name": "Client", "kind": "business", "revenue": 420.0, "operating_income": 84.0},
            {"segment_id": "data_center", "segment_name": "Data Center", "kind": "business", "revenue": 280.0, "operating_income": 56.0},
            {"segment_id": "americas", "segment_name": "Americas", "kind": "geography", "revenue": 1000.0, "operating_income": 140.0},
        ],
        [
            {"segment_id": "client", "segment_name": "Client", "kind": "business", "revenue": 462.0, "operating_income": 92.4},
            {"segment_id": "data_center", "segment_name": "Data Center", "kind": "business", "revenue": 308.0, "operating_income": 61.6},
            {"segment_id": "americas", "segment_name": "Americas", "kind": "geography", "revenue": 1100.0, "operating_income": 154.0},
        ],
        [
            {"segment_id": "client", "segment_name": "Client", "kind": "business", "revenue": 508.2, "operating_income": 101.64},
            {"segment_id": "data_center", "segment_name": "Data Center", "kind": "business", "revenue": 338.8, "operating_income": 67.76},
            {"segment_id": "americas", "segment_name": "Americas", "kind": "geography", "revenue": 1210.0, "operating_income": 169.4},
        ],
    ]
    for statement, segment_breakdown in zip(statements, segment_payloads):
        statement.data["segment_breakdown"] = segment_breakdown

    history = driver_model._normalize_statements(statements)
    segment_profiles, segment_basis = driver_model._segment_profiles(history, residual_market_growth=0.08, pricing_growth_proxy=0.02)
    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert segment_basis == "business"
    assert sum(profile["latest_revenue"] for profile in segment_profiles) == pytest.approx(1210.0, abs=1e-6)
    assert bundle is not None
    assert bundle.scenarios["base"].revenue.values[0] > 1210.0
    assert bundle.scenarios["base"].revenue_growth.values[0] > 0.0
    assert bundle.scenarios["base"].revenue_growth.values[0] != pytest.approx(driver_model.REVENUE_GROWTH_FLOOR, abs=1e-6)


def test_apply_revenue_overlays_respects_backlog_floor_then_capacity_cap():
    no_capacity = driver_model._RevenueDrivers(
        mode="top_down_proxy_decomposition+backlog",
        segment_basis=None,
        pricing_growth_proxy=0.0,
        residual_market_growth=0.0,
        share_shift_proxy=0.0,
        volume_growth_proxy=0.0,
        guidance_anchor=None,
        backlog_floor_growth=0.24,
        capacity_growth_cap=None,
        utilization_ratio=None,
        segment_profiles=[],
    )
    with_capacity = driver_model._RevenueDrivers(
        mode="top_down_proxy_decomposition+backlog+capacity",
        segment_basis=None,
        pricing_growth_proxy=0.0,
        residual_market_growth=0.0,
        share_shift_proxy=0.0,
        volume_growth_proxy=0.0,
        guidance_anchor=None,
        backlog_floor_growth=0.24,
        capacity_growth_cap=0.12,
        utilization_ratio=0.98,
        segment_profiles=[],
    )

    assert driver_model._apply_revenue_overlays(1000.0, 0.10, no_capacity, 0) == pytest.approx(1240.0, abs=1e-6)
    assert driver_model._apply_revenue_overlays(1000.0, 0.10, with_capacity, 0) == pytest.approx(1120.0, abs=1e-6)


@pytest.mark.parametrize(
    ("case_name", "statements", "guidance_anchor"),
    [
        (
            "positive_growth_year",
            [
                _driver_forecast_statement(2023, 900.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, deferred_revenue_days=3.0, accrued_liability_days=3.0),
                _driver_forecast_statement(2024, 1000.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, deferred_revenue_days=3.0, accrued_liability_days=3.0),
                _driver_forecast_statement(2025, 1100.0, receivables_days=55.0, inventory_days=32.0, payable_days=28.0, deferred_revenue_days=3.0, accrued_liability_days=3.0),
            ],
            1200.0,
        ),
        (
            "flat_year",
            [
                _driver_forecast_statement(2023, 1000.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2024, 1000.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2025, 1000.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
            ],
            980.0,
        ),
        (
            "negative_growth_year",
            [
                _driver_forecast_statement(2023, 1200.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2024, 1100.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2025, 1000.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
            ],
            850.0,
        ),
        (
            "high_working_capital_build",
            [
                _driver_forecast_statement(2023, 900.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2024, 1000.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2025, 1100.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
            ],
            1200.0,
        ),
        (
            "working_capital_release",
            [
                _driver_forecast_statement(2023, 1200.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2024, 1100.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
                _driver_forecast_statement(2025, 1000.0, receivables_days=73.0, inventory_days=60.0, payable_days=30.0, deferred_revenue_days=4.0, accrued_liability_days=4.0),
            ],
            850.0,
        ),
    ],
    ids=["positive_growth_year", "flat_year", "negative_growth_year", "high_working_capital_build", "working_capital_release"],
)
def test_driver_forecast_bundle_regression_bridge_regimes(
    case_name: str,
    statements: list[SimpleNamespace],
    guidance_anchor: float,
):
    bundle = driver_model.build_driver_forecast_bundle(statements, [_guidance_release(guidance_anchor)])

    assert bundle is not None
    base_scenario, bridge = _assert_base_bridge_formulas(bundle, statements)

    if case_name == "positive_growth_year":
        assert base_scenario.revenue_growth.values[0] > 0
        assert base_scenario.revenue.values[0] > (statements[-1].data["revenue"] or 0.0)
    elif case_name == "flat_year":
        assert abs(base_scenario.revenue_growth.values[0]) <= 0.01
        assert bridge.capex == pytest.approx(max(base_scenario.revenue.values[0] * 0.04, bridge.depreciation), rel=0.15)
    elif case_name == "negative_growth_year":
        assert base_scenario.revenue_growth.values[0] < 0
        assert base_scenario.revenue.values[0] < (statements[-1].data["revenue"] or 0.0)
    elif case_name == "high_working_capital_build":
        assert bridge.delta_working_capital > 40.0
        assert bridge.operating_cash_flow < (bridge.net_income + bridge.depreciation + bridge.stock_based_compensation)
    elif case_name == "working_capital_release":
        assert bridge.delta_working_capital < 0.0
        assert bridge.operating_cash_flow > (bridge.net_income + bridge.depreciation + bridge.stock_based_compensation)


@pytest.mark.parametrize(
    ("next_revenue", "next_cost_of_revenue", "next_cash_operating_cost", "expected_sign"),
    [
        (1100.0, 660.0, 770.0, 1),
        (1000.0, 600.0, 700.0, 0),
        (850.0, 510.0, 595.0, -1),
    ],
)
def test_project_operating_working_capital_point_handles_growth_regimes(
    next_revenue: float,
    next_cost_of_revenue: float,
    next_cash_operating_cost: float,
    expected_sign: int,
):
    base_revenue = 1000.0
    base_cost_of_revenue = 600.0
    base_cash_operating_cost = 700.0
    schedule = driver_model._OperatingWorkingCapitalSchedule(
        dso=45.0,
        dio=30.0,
        dpo=35.0,
        deferred_revenue_days=10.0,
        accrued_operating_liability_days=15.0,
        cost_of_revenue_ratio=0.60,
        starting_accounts_receivable=driver_model._days_to_balance(base_revenue, 45.0),
        starting_inventory=driver_model._days_to_balance(base_cost_of_revenue, 30.0),
        starting_accounts_payable=driver_model._days_to_balance(base_cost_of_revenue, 35.0),
        starting_deferred_revenue=driver_model._days_to_balance(base_revenue, 10.0),
        starting_accrued_operating_liabilities=driver_model._days_to_balance(base_cash_operating_cost, 15.0),
        basis_detail="test",
    )
    previous_total = driver_model._operating_working_capital_total(
        schedule.starting_accounts_receivable,
        schedule.starting_inventory,
        schedule.starting_accounts_payable,
        schedule.starting_deferred_revenue,
        schedule.starting_accrued_operating_liabilities,
    )

    point = driver_model._project_operating_working_capital_point(
        revenue=next_revenue,
        cost_of_revenue=next_cost_of_revenue,
        cash_operating_cost=next_cash_operating_cost,
        schedule=schedule,
        days_shift=0.0,
    )
    delta = point["total"] - previous_total

    if expected_sign > 0:
        assert delta > 0
    elif expected_sign < 0:
        assert delta < 0
    else:
        assert delta == pytest.approx(0.0, abs=1e-6)


def test_driver_forecast_bundle_base_case_reconciles_below_the_line_bridge():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 170.0,
                "pretax_income": 152.0,
                "income_tax_expense": 32.0,
                "net_income": 120.0,
                "operating_cash_flow": 150.0,
                "free_cash_flow": 96.0,
                "capex": 54.0,
                "depreciation_and_amortization": 32.0,
                "weighted_average_diluted_shares": 100.0,
                "current_assets": 410.0,
                "current_liabilities": 180.0,
                "total_assets": 1180.0,
                "cash_and_cash_equivalents": 180.0,
                "current_debt": 35.0,
                "long_term_debt": 265.0,
                "interest_expense": 20.0,
                "interest_income": 4.0,
                "other_income_expense": -2.0,
                "stock_based_compensation": 12.0,
                "share_buybacks": 5.0,
                "debt_repayment": 10.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1120.0,
                "operating_income": 190.0,
                "pretax_income": 170.0,
                "income_tax_expense": 36.0,
                "net_income": 134.0,
                "operating_cash_flow": 173.0,
                "free_cash_flow": 113.0,
                "capex": 60.0,
                "depreciation_and_amortization": 35.0,
                "weighted_average_diluted_shares": 99.0,
                "current_assets": 450.0,
                "current_liabilities": 195.0,
                "total_assets": 1260.0,
                "cash_and_cash_equivalents": 190.0,
                "current_debt": 30.0,
                "long_term_debt": 250.0,
                "interest_expense": 18.0,
                "interest_income": 5.0,
                "other_income_expense": -2.0,
                "stock_based_compensation": 13.0,
                "share_buybacks": 6.0,
                "debt_repayment": 20.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1260.0,
                "operating_income": 220.0,
                "pretax_income": 201.0,
                "income_tax_expense": 42.0,
                "net_income": 159.0,
                "operating_cash_flow": 202.0,
                "free_cash_flow": 134.0,
                "capex": 68.0,
                "depreciation_and_amortization": 40.0,
                "weighted_average_diluted_shares": 98.0,
                "current_assets": 498.0,
                "current_liabilities": 215.0,
                "total_assets": 1360.0,
                "cash_and_cash_equivalents": 205.0,
                "current_debt": 25.0,
                "long_term_debt": 230.0,
                "interest_expense": 16.0,
                "interest_income": 6.0,
                "other_income_expense": -3.0,
                "stock_based_compensation": 14.0,
                "share_buybacks": 8.0,
                "debt_repayment": 25.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    base_scenario = bundle.scenarios["base"]
    bridge = base_scenario.bridge[0]

    assert bridge.pretax_income == pytest.approx(
        bridge.ebit - bridge.interest_expense + bridge.interest_income + bridge.other_income_expense,
        abs=1e-6,
    )
    assert bridge.net_income == pytest.approx(bridge.pretax_income - bridge.taxes, abs=1e-6)
    assert bridge.operating_cash_flow == pytest.approx(
        bridge.net_income + bridge.depreciation + bridge.stock_based_compensation - bridge.delta_working_capital,
        abs=1e-6,
    )
    assert bridge.free_cash_flow == pytest.approx(bridge.operating_cash_flow - bridge.capex, abs=1e-6)
    assert base_scenario.net_income.values[0] == pytest.approx(bridge.net_income, abs=1e-6)
    assert base_scenario.operating_cash_flow.values[0] == pytest.approx(bridge.operating_cash_flow, abs=1e-6)
    assert base_scenario.free_cash_flow.values[0] == pytest.approx(bridge.free_cash_flow, abs=1e-6)


def test_driver_forecast_bundle_releases_operating_working_capital_in_downcycle():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1200.0,
                "gross_profit": 540.0,
                "operating_income": 180.0,
                "pretax_income": 166.0,
                "income_tax_expense": 35.0,
                "net_income": 131.0,
                "operating_cash_flow": 185.0,
                "free_cash_flow": 135.0,
                "capex": 50.0,
                "depreciation_and_amortization": 34.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 180.0,
                "inventory": 62.0,
                "accounts_payable": 68.0,
                "deferred_revenue": 30.0,
                "accrued_operating_liabilities": 22.0,
                "current_assets": 500.0,
                "current_liabilities": 220.0,
                "total_assets": 1380.0,
                "cash_and_cash_equivalents": 210.0,
                "current_debt": 30.0,
                "long_term_debt": 260.0,
                "interest_expense": 18.0,
                "interest_income": 5.0,
                "other_income_expense": -1.0,
                "stock_based_compensation": 12.0,
                "share_buybacks": 6.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "gross_profit": 495.0,
                "operating_income": 160.0,
                "pretax_income": 147.0,
                "income_tax_expense": 31.0,
                "net_income": 116.0,
                "operating_cash_flow": 172.0,
                "free_cash_flow": 127.0,
                "capex": 45.0,
                "depreciation_and_amortization": 32.0,
                "weighted_average_diluted_shares": 99.0,
                "accounts_receivable": 165.0,
                "inventory": 56.0,
                "accounts_payable": 62.0,
                "deferred_revenue": 28.0,
                "accrued_operating_liabilities": 20.0,
                "current_assets": 470.0,
                "current_liabilities": 210.0,
                "total_assets": 1310.0,
                "cash_and_cash_equivalents": 205.0,
                "current_debt": 26.0,
                "long_term_debt": 245.0,
                "interest_expense": 17.0,
                "interest_income": 5.0,
                "other_income_expense": -1.0,
                "stock_based_compensation": 11.0,
                "share_buybacks": 6.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1000.0,
                "gross_profit": 450.0,
                "operating_income": 140.0,
                "pretax_income": 129.0,
                "income_tax_expense": 27.0,
                "net_income": 102.0,
                "operating_cash_flow": 160.0,
                "free_cash_flow": 120.0,
                "capex": 40.0,
                "depreciation_and_amortization": 30.0,
                "weighted_average_diluted_shares": 98.0,
                "accounts_receivable": 150.0,
                "inventory": 50.0,
                "accounts_payable": 57.0,
                "deferred_revenue": 26.0,
                "accrued_operating_liabilities": 18.0,
                "current_assets": 440.0,
                "current_liabilities": 205.0,
                "total_assets": 1240.0,
                "cash_and_cash_equivalents": 198.0,
                "current_debt": 24.0,
                "long_term_debt": 232.0,
                "interest_expense": 16.0,
                "interest_income": 5.0,
                "other_income_expense": -1.0,
                "stock_based_compensation": 10.0,
                "share_buybacks": 5.0,
            },
        ),
    ]
    release = SimpleNamespace(
        id=1,
        filing_acceptance_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        filing_date=date(2026, 1, 20),
        reported_period_end=date(2025, 12, 31),
        revenue_guidance_low=920.0,
        revenue_guidance_high=940.0,
        last_checked=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )

    bundle = driver_model.build_driver_forecast_bundle(statements, [release])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    assert bundle.scenarios["base"].revenue_growth.values[0] < 0
    assert bridge.delta_working_capital < 0
    assert bridge.ending_operating_working_capital < bridge.beginning_operating_working_capital
    assert bridge.operating_cash_flow > (bridge.net_income + bridge.depreciation + bridge.stock_based_compensation)


def test_driver_forecast_bundle_uses_treasury_stock_method_for_option_dilution():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "options_outstanding": 8.0,
                "option_exercise_price": 10.0,
                "share_price": 20.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 101.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "options_outstanding": 8.0,
                "option_exercise_price": 10.0,
                "share_price": 20.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 102.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "options_outstanding": 8.0,
                "option_exercise_price": 10.0,
                "share_price": 20.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.basic_shares == pytest.approx(98.0, abs=1e-6)
    assert share_bridge.option_warrant_dilution_shares == pytest.approx(4.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(102.0, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert dilution_assumption["value"] == "98 basic + 4 TSM + 0 RSU / SBC + 0 converts"
    assert "Treasury stock method" in dilution_assumption["detail"]


def test_driver_forecast_bundle_uses_treasury_stock_method_for_warrant_dilution():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "warrants_outstanding": 10.0,
                "warrant_exercise_price": 15.0,
                "share_price": 30.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 101.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "warrants_outstanding": 10.0,
                "warrant_exercise_price": 15.0,
                "share_price": 30.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 103.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "warrants_outstanding": 10.0,
                "warrant_exercise_price": 15.0,
                "share_price": 30.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.option_warrant_dilution_shares == pytest.approx(5.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(103.0, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert dilution_assumption["value"] == "98 basic + 5 TSM + 0 RSU / SBC + 0 converts"
    assert "Treasury stock method using disclosed share price" in dilution_assumption["detail"]


def test_driver_forecast_bundle_adds_direct_rsu_issuance_into_diluted_shares_and_eps():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 96.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "rsu_shares": 2.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 97.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "rsu_shares": 2.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 98.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "rsu_shares": 2.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.rsu_shares == pytest.approx(2.0, abs=1e-6)
    assert share_bridge.buyback_retirement_shares == pytest.approx(0.0, abs=1e-6)
    assert share_bridge.basic_shares == pytest.approx(100.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(100.0, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )


def test_driver_forecast_bundle_infers_rsu_issuance_from_residual_share_bridge():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 96.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "shares_issued": 2.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 97.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "shares_issued": 2.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 98.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "shares_issued": 2.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.rsu_shares == pytest.approx(2.0, abs=1e-6)
    assert share_bridge.basic_shares == pytest.approx(100.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(100.0, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert dilution_assumption["detail"] == (
        "Starting basis: Basic weighted-average shares. Options and warrants: No option or warrant disclosure. "
        "RSU / SBC issuance: Residual issued-share bridge after acquisition issuance. "
        "Buybacks: No explicit repurchased-share disclosure. Acquisition issuance: No acquisition share issuance disclosure. "
        "Convertibles: No convertible share disclosure."
    )


def test_driver_forecast_bundle_uses_if_converted_shares_when_convertible_is_dilutive():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 98.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "dilutive_convertible_shares": 3.0,
                "convertible_is_dilutive": 1.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 99.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "dilutive_convertible_shares": 3.0,
                "convertible_is_dilutive": 1.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "dilutive_convertible_shares": 3.0,
                "convertible_is_dilutive": 1.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.basic_shares == pytest.approx(98.0, abs=1e-6)
    assert share_bridge.convertible_dilution_shares == pytest.approx(3.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(101.0, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert dilution_assumption["value"] == "98 basic + 0 TSM + 0 RSU / SBC + 3 converts"
    assert "Direct dilutive convertible shares" in dilution_assumption["detail"]


def test_driver_forecast_bundle_uses_conversion_price_to_gate_if_converted_dilution():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 99.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "convertible_dilution_shares": 4.0,
                "convertible_conversion_price": 15.0,
                "share_price": 30.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "convertible_dilution_shares": 4.0,
                "convertible_conversion_price": 15.0,
                "share_price": 30.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 102.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "convertible_dilution_shares": 4.0,
                "convertible_conversion_price": 15.0,
                "share_price": 30.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.convertible_dilution_shares == pytest.approx(98.0 * driver_model.CONVERT_DILUTION_CAP, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(98.0 + (98.0 * driver_model.CONVERT_DILUTION_CAP), abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert dilution_assumption["value"] == "98 basic + 0 TSM + 0 RSU / SBC + 4 converts"
    assert "If-converted shares using disclosed share price" in dilution_assumption["detail"]


def test_driver_forecast_bundle_lets_buybacks_offset_rsu_dilution():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 99.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "rsu_shares": 2.0,
                "shares_repurchased": 4.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "rsu_shares": 2.0,
                "shares_repurchased": 4.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 101.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "rsu_shares": 2.0,
                "shares_repurchased": 4.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.rsu_shares == pytest.approx(2.0, abs=1e-6)
    assert share_bridge.buyback_retirement_shares == pytest.approx(4.0, abs=1e-6)
    assert share_bridge.basic_shares == pytest.approx(96.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(96.0, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert dilution_assumption["detail"] == (
        "Starting basis: Basic weighted-average shares. Options and warrants: No option or warrant disclosure. "
        "RSU / SBC issuance: Direct RSU or stock-award shares. Buybacks: Direct repurchased-share disclosure. "
        "Acquisition issuance: No acquisition share issuance disclosure. Convertibles: No convertible share disclosure."
    )


def test_driver_forecast_bundle_translates_buyback_cash_into_retirement_shares():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 96.0,
                "weighted_average_diluted_shares": 96.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "share_buybacks": 40.0,
                "share_price": 20.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 97.0,
                "weighted_average_diluted_shares": 97.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "share_buybacks": 40.0,
                "share_price": 20.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 98.0,
                "weighted_average_diluted_shares": 98.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "share_buybacks": 40.0,
                "share_price": 20.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is False
    assert share_bridge.buyback_retirement_shares == pytest.approx(2.0, abs=1e-6)
    assert share_bridge.basic_shares == pytest.approx(96.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(96.0, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert "Repurchase cash translated into shares using disclosed share price" in dilution_assumption["detail"]


def test_driver_forecast_bundle_uses_proxy_fallback_when_disclosure_is_incomplete():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
                "stock_based_compensation": 8.0,
                "share_buybacks": 2.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_diluted_shares": 103.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
                "stock_based_compensation": 9.0,
                "share_buybacks": 2.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_diluted_shares": 106.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
                "stock_based_compensation": 10.0,
                "share_buybacks": 2.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is True
    assert share_bridge.proxy_net_change_shares > 0
    assert share_bridge.diluted_shares == pytest.approx(share_bridge.basic_shares, abs=1e-6)
    assert bundle.scenarios["base"].eps.values[0] == pytest.approx(
        bundle.scenarios["base"].net_income.values[0] / share_bridge.diluted_shares,
        abs=1e-6,
    )
    assert dilution_assumption["value"] == "Proxy fallback from historical share drift"
    assert dilution_assumption["detail"] == (
        "Fallback basis: Historical diluted-share growth with revenue-scaled SBC, buyback, acquisition, and convert proxies."
    )


def test_driver_forecast_bundle_proxy_fallback_adds_no_latent_dilution_without_historical_spread():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 100.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 101.0,
                "weighted_average_diluted_shares": 101.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 102.0,
                "weighted_average_diluted_shares": 102.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]

    assert share_bridge.uses_proxy_fallback is True
    assert share_bridge.latent_dilution_shares == pytest.approx(0.0, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(share_bridge.basic_shares, abs=1e-6)


def test_driver_forecast_bundle_proxy_fallback_uses_stable_historical_spread_for_modest_uplift():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 100.0,
                "weighted_average_diluted_shares": 102.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 101.0,
                "weighted_average_diluted_shares": 103.02,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 102.0,
                "weighted_average_diluted_shares": 104.04,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is True
    assert share_bridge.latent_dilution_shares == pytest.approx(share_bridge.basic_shares * 0.02, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(share_bridge.basic_shares * 1.02, abs=1e-6)
    assert "Latent dilution overlay uses the historical median diluted-vs-basic spread" in dilution_assumption["detail"]


def test_driver_forecast_bundle_proxy_fallback_clips_sparse_noisy_historical_spread():
    statements = [
        _statement(
            2023,
            {
                "revenue": 1000.0,
                "operating_income": 150.0,
                "pretax_income": 138.0,
                "income_tax_expense": 28.0,
                "net_income": 110.0,
                "operating_cash_flow": 155.0,
                "free_cash_flow": 115.0,
                "capex": 40.0,
                "depreciation_and_amortization": 22.0,
                "weighted_average_shares_basic": 100.0,
                "weighted_average_diluted_shares": 100.0,
                "accounts_receivable": 120.0,
                "inventory": 25.0,
                "accounts_payable": 60.0,
                "cash_and_cash_equivalents": 100.0,
                "current_debt": 20.0,
                "long_term_debt": 80.0,
            },
        ),
        _statement(
            2024,
            {
                "revenue": 1100.0,
                "operating_income": 165.0,
                "pretax_income": 151.0,
                "income_tax_expense": 31.0,
                "net_income": 120.0,
                "operating_cash_flow": 168.0,
                "free_cash_flow": 125.0,
                "capex": 43.0,
                "depreciation_and_amortization": 24.0,
                "weighted_average_shares_basic": 100.0,
                "weighted_average_diluted_shares": 112.0,
                "accounts_receivable": 128.0,
                "inventory": 26.0,
                "accounts_payable": 63.0,
                "cash_and_cash_equivalents": 108.0,
                "current_debt": 18.0,
                "long_term_debt": 76.0,
            },
        ),
        _statement(
            2025,
            {
                "revenue": 1210.0,
                "operating_income": 182.0,
                "pretax_income": 166.0,
                "income_tax_expense": 34.0,
                "net_income": 132.0,
                "operating_cash_flow": 182.0,
                "free_cash_flow": 136.0,
                "capex": 46.0,
                "depreciation_and_amortization": 26.0,
                "weighted_average_shares_basic": 100.0,
                "weighted_average_diluted_shares": 101.0,
                "accounts_receivable": 136.0,
                "inventory": 27.0,
                "accounts_payable": 66.0,
                "cash_and_cash_equivalents": 116.0,
                "current_debt": 16.0,
                "long_term_debt": 72.0,
            },
        ),
    ]

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    share_bridge = bundle.scenarios["base"].share_bridge[0]
    dilution_assumption = next(row for row in bundle.assumption_rows if row["key"] == "dilution")

    assert share_bridge.uses_proxy_fallback is True
    assert share_bridge.latent_dilution_shares == pytest.approx(share_bridge.basic_shares * 0.02, abs=1e-6)
    assert share_bridge.diluted_shares == pytest.approx(share_bridge.basic_shares * 1.02, abs=1e-6)
    assert "weighted by 2 supporting periods" in dilution_assumption["detail"]


def test_driver_forecast_calculation_rows_match_backend_formula_contract():
    statements = _standard_driver_regression_statements()
    bundle = driver_model.build_driver_forecast_bundle(statements, [_guidance_release(1200.0)])

    assert bundle is not None
    base_scenario, bridge = _assert_base_bridge_formulas(bundle, statements)
    calculation_rows = {row["key"]: row for row in bundle.calculation_rows}

    assert calculation_rows["formula_revenue"]["value"] == (
        "Prior revenue x (1 + residual-demand effect + share/mix proxy effect + price proxy effect + price-volume cross term), "
        "then apply the year-one guidance blend"
    )
    assert calculation_rows["formula_margin"]["value"] == driver_model.FORECAST_FORMULA_MARGIN
    assert calculation_rows["formula_pretax"]["value"] == driver_model.FORECAST_FORMULA_PRETAX
    assert calculation_rows["formula_tax"]["value"] == driver_model.FORECAST_FORMULA_TAX
    assert calculation_rows["formula_reinvestment"]["value"] == driver_model.FORECAST_FORMULA_CAPEX
    assert calculation_rows["formula_ppe"]["value"] == driver_model.FORECAST_FORMULA_NET_PPE
    assert calculation_rows["formula_ocf"]["value"] == driver_model.FORECAST_FORMULA_OCF
    assert calculation_rows["formula_fcf"]["value"] == driver_model.FORECAST_FORMULA_FCF
    assert calculation_rows["formula_retained_earnings"]["value"] == driver_model.FORECAST_FORMULA_RETAINED_EARNINGS
    assert calculation_rows["formula_balance_sheet"]["value"] == driver_model.FORECAST_FORMULA_BALANCE_SHEET
    assert calculation_rows["formula_eps"]["value"] == (
        "Net income / diluted shares, with basic shares rolled by proxy net dilution and diluted shares topped up by a latent dilution overlay"
    )
    assert calculation_rows["formula_revenue"]["value"] != "Prior revenue x (1 + price + market growth + share)"
    assert calculation_rows["formula_eps"]["value"] != "Net income / diluted shares"
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_pretax"]["detail"]
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_tax"]["detail"]
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_reinvestment"]["detail"]
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_ppe"]["detail"]
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_ocf"]["detail"]
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_fcf"]["detail"]
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_retained_earnings"]["detail"]
    assert f"Base FY{bridge.year}E" in calculation_rows["formula_balance_sheet"]["detail"]
    assert "PP&E-schedule D&A" in calculation_rows["formula_reinvestment"]["detail"]
    assert "opening net PP&E" in calculation_rows["formula_ppe"]["detail"]
    assert "ending net PP&E" in calculation_rows["formula_ppe"]["detail"]
    assert "Guidance blend active: 35% model 8.8% + 65% guided 9.1% toward $1200.00 = 9.0%." in calculation_rows["formula_revenue"]["detail"]
    assert "residual-implied demand growth 8.6%" in calculation_rows["formula_revenue"]["detail"]
    assert "share/mix proxy 0.0%" in calculation_rows["formula_revenue"]["detail"]
    assert calculation_rows["formula_eps"]["detail"] == (
        "FY2026E proxy fallback: starting basic 100 + proxy net change 0 = ending basic 100; "
        "latent dilution overlay 0 from 0.0% reaches 100 diluted shares. "
        "Proxy basis: Historical diluted-share growth with revenue-scaled SBC, buyback, acquisition, and convert proxies. "
        f"EPS = {driver_model._money(base_scenario.net_income.values[0])} / 100 = {driver_model._money(base_scenario.eps.values[0])}."
    )


def test_driver_forecast_bundle_uses_disclosed_ppe_history_for_depreciation_schedule():
    statements = _ppe_disclosure_driver_statements()
    history = driver_model._normalize_statements(statements)
    cost_schedule = driver_model._derive_cost_schedule(history)
    reinvestment_schedule = driver_model._derive_reinvestment_schedule(history, cost_schedule)
    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    ppe_assumption = next(row for row in bundle.assumption_rows if row["key"] == "ppe_schedule")
    ppe_formula = next(row for row in bundle.calculation_rows if row["key"] == "formula_ppe")

    assert reinvestment_schedule.ppe_schedule.opening_net_ppe == pytest.approx(369.0, abs=1e-6)
    assert reinvestment_schedule.ppe_schedule.annual_disposals == pytest.approx(5.0, abs=1e-6)
    assert reinvestment_schedule.depreciation_ratio == pytest.approx(33.0 / 369.0, abs=1e-6)
    assert bridge.depreciation == pytest.approx(369.0 * reinvestment_schedule.depreciation_ratio, abs=1e-6)
    assert bridge.ending_net_ppe == pytest.approx(bridge.beginning_net_ppe + bridge.capex - bridge.depreciation - bridge.ppe_disposals, abs=1e-6)
    assert "opening net PP&E" in ppe_formula["detail"]
    assert "Useful life" in ppe_formula["detail"]
    assert "Opening basis: Disclosed or reconstructed latest net PP&E." in ppe_assumption["detail"]


def test_driver_forecast_bundle_reconstructs_sparse_latest_ppe_with_labeled_fallback():
    statements = _ppe_sparse_driver_statements()
    history = driver_model._normalize_statements(statements)
    cost_schedule = driver_model._derive_cost_schedule(history)
    reinvestment_schedule = driver_model._derive_reinvestment_schedule(history, cost_schedule)
    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    depreciation_trace = bundle.line_traces["depreciation_amortization"][bundle.scenarios["base"].revenue.years[0]]

    assert reinvestment_schedule.ppe_schedule.opening_net_ppe == pytest.approx(351.0, abs=1e-6)
    assert reinvestment_schedule.ppe_schedule.opening_basis == "Disclosed or reconstructed latest net PP&E"
    assert reinvestment_schedule.ppe_schedule.annual_disposals == pytest.approx(0.0, abs=1e-6)
    assert "Disclosed or reconstructed latest net PP&E" in depreciation_trace.inputs[0].source_detail
    assert bridge.ending_net_ppe == pytest.approx(bridge.beginning_net_ppe + bridge.capex - bridge.depreciation - bridge.ppe_disposals, abs=1e-6)
    assert bundle.scenarios["base"].free_cash_flow.values[0] == pytest.approx(bridge.operating_cash_flow - bridge.capex, abs=1e-6)


def test_driver_forecast_bundle_uses_explicit_tax_schedule_for_profitable_company_with_no_nol():
    statements = _standard_driver_regression_statements()
    history = driver_model._normalize_statements(statements)
    below_line_schedule = driver_model._derive_below_line_schedule(history)
    bundle = driver_model.build_driver_forecast_bundle(statements, [_guidance_release(1200.0)])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    tax_assumption = next(row for row in bundle.assumption_rows if row["key"] == "tax_schedule")

    assert below_line_schedule.tax_schedule is not None
    assert below_line_schedule.tax_schedule.uses_explicit_nol_schedule is True
    assert bridge.beginning_nol == pytest.approx(0.0, abs=1e-6)
    assert bridge.nol_used == pytest.approx(0.0, abs=1e-6)
    assert bridge.cash_tax == pytest.approx(bridge.taxes, abs=1e-6)
    assert bridge.deferred_tax_expense == pytest.approx(0.0, abs=1e-6)
    assert "Explicit NOL + deferred-tax schedule" in tax_assumption["detail"]


def test_driver_forecast_bundle_builds_nol_and_uses_it_before_cash_taxes_normalize():
    statements = _loss_recovery_tax_driver_statements()
    history = driver_model._normalize_statements(statements)
    below_line_schedule = driver_model._derive_below_line_schedule(history)
    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    tax_formula = next(row for row in bundle.calculation_rows if row["key"] == "formula_tax")
    expected_tax_point = driver_model._project_tax_schedule(
        bridge.pretax_income,
        below_line_schedule.tax_schedule,
        opening_nol=bridge.beginning_nol,
        opening_deferred_tax_asset=bridge.beginning_deferred_tax_asset,
    )

    assert below_line_schedule.tax_schedule is not None
    assert below_line_schedule.tax_schedule.uses_explicit_nol_schedule is True
    assert bridge.beginning_nol > 0
    assert bridge.nol_used > 0
    assert bridge.ending_nol == pytest.approx(bridge.beginning_nol + bridge.nol_created - bridge.nol_used, abs=1e-6)
    assert bridge.cash_tax == pytest.approx(expected_tax_point.cash_tax, abs=1e-6)
    assert bridge.taxes == pytest.approx(expected_tax_point.book_tax_expense, abs=1e-6)
    assert bridge.cash_tax < bridge.taxes
    assert "opening NOL" in tax_formula["detail"]
    assert "Cash tax" in tax_formula["detail"]


def test_driver_forecast_bundle_uses_fallback_tax_method_when_disclosure_is_sparse():
    statements = _sparse_tax_driver_statements()
    history = driver_model._normalize_statements(statements)
    below_line_schedule = driver_model._derive_below_line_schedule(history)
    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    tax_assumption = next(row for row in bundle.assumption_rows if row["key"] == "tax_schedule")

    assert below_line_schedule.tax_schedule is not None
    assert below_line_schedule.tax_schedule.uses_explicit_nol_schedule is False
    assert bridge.beginning_nol == pytest.approx(0.0, abs=1e-6)
    assert bridge.nol_used == pytest.approx(0.0, abs=1e-6)
    assert bridge.cash_tax == pytest.approx(bridge.taxes, abs=1e-6)
    assert bridge.deferred_tax_expense == pytest.approx(0.0, abs=1e-6)
    assert "Fallback simple effective-tax-rate method" in tax_assumption["detail"]


def test_driver_forecast_bundle_balances_clean_balance_sheet_when_disclosure_is_sufficient():
    statements = _balanced_balance_sheet_driver_statements()
    history = driver_model._normalize_statements(statements)
    cost_schedule = driver_model._derive_cost_schedule(history)
    reinvestment_schedule = driver_model._derive_reinvestment_schedule(history, cost_schedule)
    below_line_schedule = driver_model._derive_below_line_schedule(history)
    balance_sheet_schedule = driver_model._derive_balance_sheet_schedule(history, reinvestment_schedule, below_line_schedule)
    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    balance_formula = next(row for row in bundle.calculation_rows if row["key"] == "formula_balance_sheet")

    assert balance_sheet_schedule.plug_bucket_mode == "none"
    assert bridge.balance_sheet_plug == pytest.approx(0.0, abs=1e-6)
    assert bridge.balance_sheet_delta_before_plug == pytest.approx(bridge.balance_sheet_delta, abs=1e-6)
    assert bridge.balance_sheet_delta == pytest.approx(0.0, abs=1e-3)
    assert bridge.total_assets == pytest.approx(bridge.total_liabilities_and_equity, abs=1e-3)
    assert "Raw delta before plug" in balance_formula["detail"]


def test_driver_forecast_bundle_uses_explicit_balance_sheet_plug_when_disclosure_is_partial():
    statements = _plugged_balance_sheet_driver_statements()
    history = driver_model._normalize_statements(statements)
    cost_schedule = driver_model._derive_cost_schedule(history)
    reinvestment_schedule = driver_model._derive_reinvestment_schedule(history, cost_schedule)
    below_line_schedule = driver_model._derive_below_line_schedule(history)
    balance_sheet_schedule = driver_model._derive_balance_sheet_schedule(history, reinvestment_schedule, below_line_schedule)
    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    balance_assumption = next(row for row in bundle.assumption_rows if row["key"] == "balance_sheet_framework")
    balance_formula = next(row for row in bundle.calculation_rows if row["key"] == "formula_balance_sheet")

    assert balance_sheet_schedule.plug_bucket_mode == "dynamic"
    assert bridge.balance_sheet_plug > 0
    assert bridge.balance_sheet_plug_bucket in {"Other Liabilities Plug", "Other Long-Term Assets Plug"}
    assert abs(bridge.balance_sheet_delta_before_plug) > 1e-6
    assert bridge.balance_sheet_delta == pytest.approx(0.0, abs=1e-6)
    assert "plug bucket" in balance_assumption["detail"].lower()
    assert bridge.balance_sheet_plug_bucket in balance_formula["detail"]


def test_driver_forecast_bundle_draws_synthetic_revolver_when_no_opening_debt_supports_minimum_cash():
    bundle = driver_model.build_driver_forecast_bundle(_no_debt_draw_driver_statements(), [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    debt_formula = next(row for row in bundle.calculation_rows if row["key"] == "formula_debt_schedule")
    debt_assumption = next(row for row in bundle.assumption_rows if row["key"] == "debt_schedule")

    assert bridge.beginning_debt == pytest.approx(0.0, abs=1e-6)
    assert bridge.debt_draw > 0
    assert bridge.ending_debt == pytest.approx(bridge.debt_draw, abs=1e-6)
    assert any(tranche.key == "revolver" and tranche.optional_draw > 0 for tranche in bridge.debt_tranches)
    assert "synthetic revolver" in debt_assumption["detail"].lower()
    assert "draws" in debt_formula["detail"]


def test_driver_forecast_bundle_keeps_simple_debt_in_clearly_labeled_fallback_schedule():
    bundle = driver_model.build_driver_forecast_bundle(_standard_driver_regression_statements(), [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    debt_assumption = next(row for row in bundle.assumption_rows if row["key"] == "debt_schedule")
    debt_formula = next(row for row in bundle.calculation_rows if row["key"] == "formula_debt_schedule")

    assert [tranche.key for tranche in bridge.debt_tranches] == ["revolver", "debt_fallback"]
    assert bridge.debt_tranches[0].opening_balance == pytest.approx(0.0, abs=1e-6)
    assert bridge.debt_tranches[1].opening_balance == pytest.approx(bridge.beginning_debt, abs=1e-6)
    assert "fallback single-tranche debt schedule" in debt_assumption["detail"].lower()
    assert "Debt Fallback" in debt_formula["detail"]


def test_driver_forecast_bundle_rolls_multi_tranche_debt_and_interest_by_average_balance():
    bundle = driver_model.build_driver_forecast_bundle(_multi_tranche_driver_statements(), [])

    assert bundle is not None
    bridge = bundle.scenarios["base"].bridge[0]
    debt_formula = next(row for row in bundle.calculation_rows if row["key"] == "formula_debt_schedule")

    tranche_map = {tranche.key: tranche for tranche in bridge.debt_tranches}

    assert {"revolver", "term_loan", "notes_bonds", "leases"} <= set(tranche_map)
    assert bridge.beginning_debt == pytest.approx(190.0, abs=1e-6)
    assert tranche_map["term_loan"].mandatory_amortization == pytest.approx(8.0, abs=1e-6)
    assert tranche_map["notes_bonds"].maturity_repayment == pytest.approx(12.0, abs=1e-6)
    assert tranche_map["leases"].mandatory_amortization == pytest.approx(4.0, abs=1e-6)
    assert tranche_map["revolver"].optional_sweep_repayment > 0
    assert all(
        tranche.ending_balance
        == pytest.approx(
            tranche.opening_balance
            - tranche.mandatory_amortization
            - tranche.maturity_repayment
            - tranche.optional_sweep_repayment
            + tranche.optional_draw,
            abs=1e-6,
        )
        for tranche in bridge.debt_tranches
    )
    assert bridge.interest_expense == pytest.approx(
        sum(
            ((tranche.opening_balance + tranche.ending_balance) / 2.0) * tranche.interest_rate
            for tranche in bridge.debt_tranches
        ),
        abs=1e-6,
    )
    assert "Interest by tranche" in debt_formula["detail"]
    assert "Term Loan" in debt_formula["detail"]


def test_driver_forecast_bundle_exposes_ib_modeling_suitability_rows():
    bundle = driver_model.build_driver_forecast_bundle(_standard_driver_regression_statements(), [_guidance_release(1200.0)])

    assert bundle is not None
    suitability_rows = {row["key"]: row for row in bundle.suitability_rows}
    routing_row = next(row for row in bundle.assumption_rows if row["key"] == "entity_routing")
    model_scope = next(row for row in bundle.assumption_rows if row["key"] == "model_scope")

    assert bundle.engine_mode == driver_model.ENGINE_MODE_DRIVER
    assert bundle.entity_routing == driver_model.ENTITY_ROUTING_NONFIN_IB_MODEL
    assert routing_row["value"] == driver_model.ENTITY_ROUTING_NONFIN_IB_MODEL
    assert suitability_rows["revenue_growth"]["classification"] == driver_model.MODEL_SUITABILITY_IB_USEFUL_BUT_HEURISTIC
    assert suitability_rows["margin_logic"]["classification"] == driver_model.MODEL_SUITABILITY_IB_USEFUL_BUT_HEURISTIC
    assert suitability_rows["depreciation_amortization"]["classification"] == driver_model.MODEL_SUITABILITY_IB_CORE_NONFIN
    assert suitability_rows["operating_working_capital"]["classification"] == driver_model.MODEL_SUITABILITY_IB_CORE_NONFIN
    assert suitability_rows["capex_reinvestment"]["classification"] == driver_model.MODEL_SUITABILITY_IB_USEFUL_BUT_HEURISTIC
    assert suitability_rows["debt_cash_interest"]["classification"] == driver_model.MODEL_SUITABILITY_IB_USEFUL_BUT_HEURISTIC
    assert suitability_rows["taxes"]["classification"] == driver_model.MODEL_SUITABILITY_IB_USEFUL_BUT_HEURISTIC
    assert suitability_rows["share_count_dilution"]["classification"] == driver_model.MODEL_SUITABILITY_IB_USEFUL_BUT_HEURISTIC
    assert suitability_rows["balance_sheet_linkage"]["classification"] == driver_model.MODEL_SUITABILITY_IB_USEFUL_BUT_HEURISTIC
    assert suitability_rows["regulated_financial_routing"]["classification"] == driver_model.MODEL_SUITABILITY_BANK_ENTITY_SEPARATE_MODEL
    assert model_scope["value"] == "Industrial scope: OWC, financing, taxes, and balance-sheet diagnostics are upgraded; plug buckets may still be required"
    assert "visible balancing check with explicit plugs" in model_scope["detail"]


def test_driver_forecast_bundle_flags_regulated_financial_markers_for_separate_bank_model():
    statements = []
    for statement in _standard_driver_regression_statements():
        statements.append(
            _statement(
                statement.period_end.year,
                {
                    **statement.data,
                    "regulated_bank_source_id": "fdic_bankfind_financials",
                    "regulated_bank_reporting_basis": "fdic_call_report",
                    "net_interest_income": statement.data["revenue"] * 0.55,
                    "provision_for_credit_losses": statement.data["revenue"] * 0.02,
                    "deposits_total": statement.data["revenue"] * 0.85,
                    "common_equity_tier1_ratio": 0.12,
                },
            )
        )

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    routing_row = next(row for row in bundle.assumption_rows if row["key"] == "entity_routing")
    model_scope = next(row for row in bundle.assumption_rows if row["key"] == "model_scope")
    regulated_row = next(row for row in bundle.suitability_rows if row["key"] == "regulated_financial_routing")

    assert bundle.engine_mode == driver_model.ENGINE_MODE_REGULATED_FINANCIAL_SEPARATE
    assert bundle.entity_routing == driver_model.ENTITY_ROUTING_REGULATED_FINANCIAL_SEPARATE
    assert routing_row["value"] == driver_model.ENTITY_ROUTING_REGULATED_FINANCIAL_SEPARATE
    assert model_scope["value"] == "Regulated-financial separate path required before industrial forecasting"
    assert "industrial DSO/DIO/DPO, sales-to-capital, and industrial capex heuristics are bypassed" in model_scope["detail"]
    assert regulated_row["classification"] == driver_model.MODEL_SUITABILITY_BANK_ENTITY_SEPARATE_MODEL
    assert regulated_row["bank_appropriateness"] == "Required because the routing gate classified the issuer for the regulated-financial separate path."


def test_driver_forecast_bundle_uses_conservative_fallback_for_unsure_financial_sector_issuer():
    company = SimpleNamespace(
        name="Example Capital Markets",
        sector="Financials",
        market_sector="Financials",
        market_industry="Capital Markets",
    )

    bundle = driver_model.build_driver_forecast_bundle(
        _standard_driver_regression_statements(),
        [],
        company=company,
    )

    assert bundle is not None
    routing_row = next(row for row in bundle.assumption_rows if row["key"] == "entity_routing")
    model_scope = next(row for row in bundle.assumption_rows if row["key"] == "model_scope")

    assert bundle.engine_mode == driver_model.ENGINE_MODE_CONSERVATIVE_FALLBACK
    assert bundle.entity_routing == driver_model.ENTITY_ROUTING_UNSURE_REQUIRE_CONSERVATIVE_FALLBACK
    assert routing_row["value"] == driver_model.ENTITY_ROUTING_UNSURE_REQUIRE_CONSERVATIVE_FALLBACK
    assert model_scope["value"] == "Conservative fallback active until routing is confirmed"
    assert bundle.scenarios == {}


def test_build_company_charts_dashboard_response_withholds_industrial_forecast_for_regulated_financials(monkeypatch):
    company = SimpleNamespace(
        id=1,
        ticker="BANK",
        cik="0000123000",
        name="Example Bank Corp",
        sector="Financials",
        market_sector="Financials",
        market_industry="Banks",
    )
    snapshot = SimpleNamespace(cache_state="fresh", last_checked=datetime(2026, 4, 12, tzinfo=timezone.utc))
    statements = _standard_driver_regression_statements()
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.6, drift=0.02)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.forecast_methodology.heuristic is False
    assert response.forecast_methodology.label == "Regulated-financial separate path required"
    assert response.cards.revenue.series == [series for series in response.cards.revenue.series if series.series_kind == "actual"]
    assert response.cards.revenue_outlook_bridge is None
    assert response.cards.forecast_assumptions is not None
    assert response.cards.forecast_assumptions.items[0].value == driver_model.ENTITY_ROUTING_REGULATED_FINANCIAL_SEPARATE


def test_driver_forecast_docs_match_backend_formula_wording():
    docs_text = Path("docs/company-charts-driver-forecast.md").read_text(encoding="utf-8")

    assert f"`Growth reinvestment = {driver_model.FORECAST_FORMULA_FIXED_CAPITAL_REINVESTMENT}`" in docs_text
    assert f"`OCF = {driver_model.FORECAST_FORMULA_OCF}`" in docs_text
    assert "`Capex = max(maintenance capex, D&A + growth reinvestment)`" in docs_text
    assert "`FCF = OCF - Capex`" in docs_text
    assert "Delta operating working capital flows through OCF, not capex." in docs_text


def test_build_company_charts_dashboard_response_preserves_exact_driver_formula_copy(monkeypatch):
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
    statements = _standard_driver_regression_statements()
    release = _guidance_release(1200.0)
    expected_bundle = driver_model.build_driver_forecast_bundle(statements, [release])
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    assert expected_bundle is not None

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [release])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.cards.forecast_calculations is not None

    actual_formula_rows = [
        {"key": item.key, "label": item.label, "value": item.value, "detail": item.detail}
        for item in response.cards.forecast_calculations.items
        if item.key.startswith("formula_")
    ]

    expected_formula_rows = [row for row in expected_bundle.calculation_rows if str(row.get("key", "")).startswith("formula_")]

    assert actual_formula_rows == expected_formula_rows
    formula_items = {item.key: item for item in response.cards.forecast_calculations.items}
    assert formula_items["formula_revenue"].value == (
        "Prior revenue x (1 + residual-demand effect + share/mix proxy effect + price proxy effect + price-volume cross term), "
        "then apply the year-one guidance blend"
    )
    assert formula_items["formula_revenue"].detail == (
        "FY2026E effects: residual demand 6.9%, share/mix 0.0%, price proxy 1.7%, cross term 0.1%, raw growth 8.8%. "
        "Driver seed decomposes realized growth into price proxy 1.9%, residual-implied demand growth 8.6%, and share/mix proxy 0.0%. "
        "Guidance blend active: 35% model 8.8% + 65% guided 9.1% toward $1200.00 = 9.0%. "
        "Final FY2026E growth 9.0% drives revenue to $1198.85."
    )
    assert formula_items["formula_eps"].value == (
        "Net income / diluted shares, with basic shares rolled by proxy net dilution and diluted shares topped up by a latent dilution overlay"
    )
    assert formula_items["formula_eps"].detail == next(
        row["detail"] for row in expected_bundle.calculation_rows if row["key"] == "formula_eps"
    )


def test_build_company_charts_dashboard_response_preserves_explicit_driver_formula_copy(monkeypatch):
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
    statements = _explicit_dilution_driver_statements()
    expected_bundle = driver_model.build_driver_forecast_bundle(statements, [])
    fake_session = SimpleNamespace(get=lambda _model, _company_id: company)

    assert expected_bundle is not None

    monkeypatch.setattr(charts_service, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(charts_service, "get_company_financials", lambda *_args, **_kwargs: statements)
    monkeypatch.setattr(charts_service, "get_company_earnings_model_points", lambda *_args, **_kwargs: [_earnings_point(quality_score=0.8, drift=0.06)])
    monkeypatch.setattr(charts_service, "get_company_earnings_releases", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(charts_service, "get_company_financial_restatements", lambda *_args, **_kwargs: [])

    response = charts_service.build_company_charts_dashboard_response(fake_session, 1, generated_at=datetime(2026, 4, 13, tzinfo=timezone.utc))

    assert response is not None
    assert response.cards.forecast_calculations is not None

    actual_formula_rows = [
        {"key": item.key, "label": item.label, "value": item.value, "detail": item.detail}
        for item in response.cards.forecast_calculations.items
        if item.key.startswith("formula_")
    ]
    expected_formula_rows = [row for row in expected_bundle.calculation_rows if str(row.get("key", "")).startswith("formula_")]

    assert actual_formula_rows == expected_formula_rows
    formula_items = {item.key: item for item in response.cards.forecast_calculations.items}
    assert formula_items["formula_revenue"].value != "Prior revenue x (1 + price + market growth + share)"
    assert formula_items["formula_eps"].value != "Net income / diluted shares"
    assert formula_items["formula_eps"].value == (
        "Net income / diluted shares, with basic shares = prior basic + RSU or SBC issuance + acquisition issuance - buybacks "
        "and diluted shares = basic + options or warrants + convertibles"
    )
    assert formula_items["formula_eps"].detail == next(
        row["detail"] for row in expected_bundle.calculation_rows if row["key"] == "formula_eps"
    )


def test_driver_formula_copy_calls_out_backlog_floor_and_capacity_cap():
    statements = _standard_driver_regression_statements()
    latest_data = dict(statements[-1].data)
    latest_data["order_backlog"] = 2200.0
    latest_data["capacity_utilization"] = 98.0
    statements[-1] = SimpleNamespace(
        period_end=statements[-1].period_end,
        filing_type=statements[-1].filing_type,
        last_checked=statements[-1].last_checked,
        data=latest_data,
    )

    bundle = driver_model.build_driver_forecast_bundle(statements, [])

    assert bundle is not None
    formula_revenue = next(row for row in bundle.calculation_rows if row["key"] == "formula_revenue")
    assert formula_revenue["value"] == (
        "Prior revenue x (1 + residual-demand effect + share/mix proxy effect + price proxy effect + price-volume cross term), "
        "then apply the year-one backlog floor and capacity cap"
    )
    assert formula_revenue["detail"] == (
        "FY2026E effects: residual demand 6.9%, share/mix 0.0%, price proxy 1.7%, cross term 0.1%, raw growth 8.8%. "
        "Driver seed decomposes realized growth into price proxy 1.9%, residual-implied demand growth 8.6%, and share/mix proxy 0.0%. "
        "Backlog floor active: max(8.8%, 20.0%) = 20.0%. "
        "Capacity cap active at 98.0% utilization: min(20.0%, 3.7%) = 3.7%. "
        "Final FY2026E growth 3.7% drives revenue to $1141.07."
    )


def test_driver_formula_copy_calls_out_explicit_dilution_bridge():
    bundle = driver_model.build_driver_forecast_bundle(_explicit_dilution_driver_statements(), [])

    assert bundle is not None
    formula_eps = next(row for row in bundle.calculation_rows if row["key"] == "formula_eps")
    base_scenario = bundle.scenarios["base"]
    assert formula_eps["value"] == (
        "Net income / diluted shares, with basic shares = prior basic + RSU or SBC issuance + acquisition issuance - buybacks "
        "and diluted shares = basic + options or warrants + convertibles"
    )
    assert formula_eps["detail"] == (
        "FY2026E explicit bridge: starting basic 100 + RSU or SBC 2 + acquisitions 1 - buybacks 1 + options or warrants 2 + "
        "convertibles 1 = 105 diluted shares. Starting basis: Basic weighted-average shares. "
        "Options and warrants: Direct dilutive option or warrant shares. RSU or SBC issuance: Direct RSU or stock-award shares. "
        "Buybacks: Direct repurchased-share disclosure. Acquisition issuance: Direct acquisition share issuance. "
        f"Convertibles: Direct dilutive convertible shares. EPS = {driver_model._money(base_scenario.net_income.values[0])} / 105 = {driver_model._money(base_scenario.eps.values[0])}."
    )


def test_driver_forecast_bundle_populates_formula_traces_for_core_base_lines():
    bundle = driver_model.build_driver_forecast_bundle(_standard_driver_regression_statements(), [_guidance_release(1200.0)])

    assert bundle is not None
    expected_lines = {
        "revenue",
        "cost_of_revenue",
        "gross_profit",
        "operating_income",
        "pretax_income",
        "income_tax",
        "net_income",
        "net_ppe",
        "accounts_receivable",
        "inventory",
        "accounts_payable",
        "deferred_revenue",
        "accrued_operating_liabilities",
        "depreciation_amortization",
        "sbc_expense",
        "capex",
        "operating_cash_flow",
        "free_cash_flow",
        "diluted_shares",
        "eps",
    }
    forecast_years = set(bundle.scenarios["base"].revenue.years)

    assert set(bundle.line_traces) == expected_lines
    for line_item in expected_lines:
        assert set(bundle.line_traces[line_item]) == forecast_years


def test_driver_formula_traces_use_readable_computation_strings():
    bundle = driver_model.build_driver_forecast_bundle(_standard_driver_regression_statements(), [_guidance_release(1200.0)])

    assert bundle is not None
    first_year = bundle.scenarios["base"].revenue.years[0]
    revenue_trace = bundle.line_traces["revenue"][first_year]
    accounts_receivable_trace = bundle.line_traces["accounts_receivable"][first_year]
    ocf_trace = bundle.line_traces["operating_cash_flow"][first_year]

    assert revenue_trace.formula_computation.startswith("$1100.00 x (1 + ")
    assert "%" in revenue_trace.formula_computation
    assert "days" in accounts_receivable_trace.formula_computation
    assert "$" in ocf_trace.formula_computation
    assert " = " in ocf_trace.formula_computation
    assert all(input_item.formatted_value for input_item in revenue_trace.inputs)


def test_driver_formula_traces_confidence_tracks_sec_default_and_fallback_inputs():
    high_bundle = driver_model.build_driver_forecast_bundle(_explicit_dilution_driver_statements(), [])
    medium_statements = [_statement(year, {**statement.data, "accounts_receivable": None}) for year, statement in zip((2023, 2024, 2025), _explicit_dilution_driver_statements(), strict=True)]
    medium_bundle = driver_model.build_driver_forecast_bundle(medium_statements, [])
    low_statements = []
    for year, statement in zip((2023, 2024, 2025), _explicit_dilution_driver_statements(), strict=True):
        data = {key: value for key, value in statement.data.items() if key != "gross_profit"}
        low_statements.append(_statement(year, data))
    low_bundle = driver_model.build_driver_forecast_bundle(low_statements, [])

    assert high_bundle is not None
    assert medium_bundle is not None
    assert low_bundle is not None

    first_year = high_bundle.scenarios["base"].revenue.years[0]
    assert high_bundle.line_traces["diluted_shares"][first_year].confidence == "high"
    assert medium_bundle.line_traces["accounts_receivable"][first_year].confidence == "medium"
    assert medium_bundle.line_traces["accounts_receivable"][first_year].inputs[1].source_kind == "default"
    assert low_bundle.line_traces["cost_of_revenue"][first_year].confidence == "low"
    assert low_bundle.line_traces["inventory"][first_year].confidence == "low"


def test_driver_formula_traces_reproduce_trace_results_within_tolerance():
    bundle = driver_model.build_driver_forecast_bundle(_standard_driver_regression_statements(), [_guidance_release(1200.0)])

    assert bundle is not None
    for line_traces in bundle.line_traces.values():
        for trace in line_traces.values():
            _assert_trace_math(trace)


def test_driver_formula_traces_are_additive_and_do_not_change_existing_forecast_outputs():
    statements = _standard_driver_regression_statements()
    bundle = driver_model.build_driver_forecast_bundle(statements, [_guidance_release(1200.0)])

    assert bundle is not None
    base_scenario, bridge = _assert_base_bridge_formulas(bundle, statements)
    calculation_rows = {row["key"]: row for row in bundle.calculation_rows}
    first_year = base_scenario.revenue.years[0]

    assert calculation_rows["formula_ocf"]["value"] == driver_model.FORECAST_FORMULA_OCF
    assert calculation_rows["formula_fcf"]["value"] == driver_model.FORECAST_FORMULA_FCF
    assert bundle.line_traces["revenue"][first_year].result_value == pytest.approx(base_scenario.revenue.values[0], abs=1e-6)
    assert bundle.line_traces["capex"][first_year].result_value == pytest.approx(base_scenario.capex.values[0], abs=1e-6)
    assert bundle.line_traces["operating_cash_flow"][first_year].result_value == pytest.approx(bridge.operating_cash_flow, abs=1e-6)
    assert bundle.line_traces["free_cash_flow"][first_year].result_value == pytest.approx(base_scenario.free_cash_flow.values[0], abs=1e-6)


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
    assert response.cards.revenue_outlook_bridge is None
    assert response.cards.margin_path is not None
    assert response.cards.fcf_outlook is not None


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
    assert diagnostics.backtest_metric_weights["revenue"] == pytest.approx(0.5, abs=1e-9)
    assert set(diagnostics.backtest_metric_errors) == {"revenue", "operating_income", "eps", "free_cash_flow"}
    assert diagnostics.final_score <= charts_service.FORECAST_STABILITY_MAX_SCORE


def test_forecast_stability_profile_penalties_reduce_score_monotonically(monkeypatch):
    company = SimpleNamespace(id=1, name="Acme", sector="Technology", market_sector="Technology")
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
    calm_revenue_actual = [_revenue_point(year, value) for year, value in [(2021, 100.0), (2022, 108.0), (2023, 116.64), (2024, 125.97), (2025, 136.05)]]
    noisy_revenue_actual = [_revenue_point(year, value) for year, value in [(2021, 100.0), (2022, 180.0), (2023, 90.0), (2024, 220.0), (2025, 140.0)]]

    fixed_backtest = {
        "sample_size": 3,
        "weighted_error": 0.1,
        "error_band": "moderate",
        "horizon_errors": {1: 0.09, 2: 0.1, 3: 0.12},
        "metric_weights": dict(charts_service.FORECAST_STABILITY_BACKTEST_METRIC_WEIGHTS),
        "metric_errors": {"revenue": 0.08, "operating_income": 0.1, "eps": 0.12, "free_cash_flow": 0.14},
        "metric_horizon_errors": {
            "revenue": {1: 0.08, 2: 0.08, 3: 0.08},
            "operating_income": {1: 0.1, 2: 0.1, 3: 0.1},
            "eps": {1: 0.12, 2: 0.12, 3: 0.12},
            "free_cash_flow": {1: 0.14, 2: 0.14, 3: 0.14},
        },
        "metric_sample_sizes": {"revenue": 3, "operating_income": 3, "eps": 3, "free_cash_flow": 3},
    }

    monkeypatch.setattr(charts_service, "_walk_forward_forecast_backtest", lambda *_args, **_kwargs: fixed_backtest)

    calm = charts_service._forecast_stability_profile(
        object(),
        company,
        calm_statements,
        calm_revenue_actual,
        [_earnings_point(quality_score=0.8)],
        [],
        [],
        None,
    )
    noisy = charts_service._forecast_stability_profile(
        object(),
        company,
        noisy_statements,
        noisy_revenue_actual,
        [_earnings_point(quality_score=0.8)],
        [],
        [],
        None,
    )

    assert noisy.final_score < calm.final_score
    assert sum(component.impact for component in noisy.components) < sum(component.impact for component in calm.components)


def test_walk_forward_backtest_blends_metric_level_weights(monkeypatch):
    company = SimpleNamespace(name="Acme", sector="Technology", market_sector="Technology")
    statements = [
        _statement(2022, {"revenue": 100.0, "operating_income": 20.0, "free_cash_flow": 10.0, "eps": 1.0}),
        _statement(2023, {"revenue": 110.0, "operating_income": 22.0, "free_cash_flow": 11.0, "eps": 1.1}),
        _statement(2024, {"revenue": 121.0, "operating_income": 24.2, "free_cash_flow": 12.1, "eps": 1.21}),
        _statement(2025, {"revenue": 133.1, "operating_income": 26.62, "free_cash_flow": 13.31, "eps": 1.331}),
    ]

    def _fake_forecast_state(history, *_args, **_kwargs):
        next_year = history[-1].period_end.year + 1
        actual_statement = next(item for item in statements if item.period_end.year == next_year)
        revenue = charts_service._statement_value(actual_statement, "revenue")
        ebit = charts_service._statement_value(actual_statement, "operating_income")
        free_cash_flow = charts_service._statement_value(actual_statement, "free_cash_flow")
        eps = charts_service._statement_value(actual_statement, "eps")
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
                        points=[charts_service.CompanyChartsSeriesPointPayload(period_label=f"FY{next_year}E", fiscal_year=next_year, period_end=None, value=revenue * 1.10, series_kind="forecast")],
                    )
                ],
            ),
            "profit_series": [
                charts_service.CompanyChartsSeriesPayload(
                    key="operating_income_forecast",
                    label="EBIT Forecast",
                    unit="usd",
                    chart_type="line",
                    series_kind="forecast",
                    stroke_style="dashed",
                    points=[charts_service.CompanyChartsSeriesPointPayload(period_label=f"FY{next_year}E", fiscal_year=next_year, period_end=None, value=ebit * 1.20, series_kind="forecast")],
                )
            ],
            "cash_series": [
                charts_service.CompanyChartsSeriesPayload(
                    key="free_cash_flow_forecast",
                    label="FCF Forecast",
                    unit="usd",
                    chart_type="line",
                    series_kind="forecast",
                    stroke_style="dashed",
                    points=[charts_service.CompanyChartsSeriesPointPayload(period_label=f"FY{next_year}E", fiscal_year=next_year, period_end=None, value=free_cash_flow * 1.30, series_kind="forecast")],
                )
            ],
            "eps_card": charts_service.CompanyChartsCardPayload(
                key="eps",
                title="EPS",
                series=[
                    charts_service.CompanyChartsSeriesPayload(
                        key="eps_forecast",
                        label="EPS Forecast",
                        unit="usd_per_share",
                        chart_type="bar",
                        series_kind="forecast",
                        stroke_style="muted",
                        points=[charts_service.CompanyChartsSeriesPointPayload(period_label=f"FY{next_year}E", fiscal_year=next_year, period_end=None, value=eps * 1.40, series_kind="forecast")],
                    )
                ],
            ),
        }

    monkeypatch.setattr(charts_service, "_build_forecast_state", _fake_forecast_state)

    backtest = charts_service._walk_forward_forecast_backtest(object(), company, statements, [])

    assert backtest["sample_size"] == 2
    assert backtest["metric_errors"]["revenue"] == pytest.approx(0.1, abs=1e-9)
    assert backtest["metric_errors"]["operating_income"] == pytest.approx(0.2, abs=1e-9)
    assert backtest["metric_errors"]["free_cash_flow"] == pytest.approx(0.3, abs=1e-9)
    assert backtest["metric_errors"]["eps"] == pytest.approx(0.4, abs=1e-9)
    assert backtest["horizon_errors"][1] == pytest.approx(0.195, abs=1e-9)
    assert backtest["weighted_error"] == pytest.approx(0.195, abs=1e-9)
    assert backtest["metric_sample_sizes"] == {"revenue": 2, "operating_income": 2, "eps": 2, "free_cash_flow": 2}


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

    def _fake_bundle(_history, releases, **_kwargs):
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
