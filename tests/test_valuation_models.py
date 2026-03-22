from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import app.model_engine.models.capital_allocation as capital_allocation_model
import app.model_engine.models.dcf as dcf_model
import app.model_engine.models.reverse_dcf as reverse_dcf_model
import app.model_engine.models.roic as roic_model
from app.model_engine.types import CompanyDataset, FinancialPoint


def _mock_risk_free(*_args, **_kwargs):
    return SimpleNamespace(
        source_name="U.S. Treasury Daily Par Yield Curve",
        tenor="10y",
        observation_date=date(2026, 3, 20),
        rate_used=0.042,
        fetched_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )


def _point(year: int, data: dict[str, float | int | None]) -> FinancialPoint:
    return FinancialPoint(
        statement_id=year,
        filing_type="10-K",
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        source="sec",
        last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
        data=data,
    )


def _dataset(points: list[FinancialPoint]) -> CompanyDataset:
    ordered = tuple(sorted(points, key=lambda item: item.period_end, reverse=True))
    return CompanyDataset(
        company_id=1,
        ticker="ACME",
        name="Acme Corp",
        sector="Technology",
        financials=ordered,
    )


def _base_points() -> list[FinancialPoint]:
    return [
        _point(
            2025,
            {
                "revenue": 1250,
                "operating_income": 260,
                "net_income": 190,
                "income_tax_expense": 42,
                "free_cash_flow": 210,
                "operating_cash_flow": 280,
                "capex": 70,
                "cash_and_short_term_investments": 340,
                "cash_and_cash_equivalents": 280,
                "short_term_investments": 60,
                "current_debt": 90,
                "long_term_debt": 410,
                "shares_outstanding": 120,
                "weighted_average_diluted_shares": 118,
                "stockholders_equity": 980,
                "dividends": 45,
                "share_buybacks": 65,
                "debt_changes": -20,
                "stock_based_compensation": 30,
                "eps": 6.0,
            },
        ),
        _point(
            2024,
            {
                "revenue": 1160,
                "operating_income": 235,
                "net_income": 170,
                "income_tax_expense": 39,
                "free_cash_flow": 190,
                "operating_cash_flow": 258,
                "capex": 68,
                "cash_and_short_term_investments": 320,
                "cash_and_cash_equivalents": 265,
                "short_term_investments": 55,
                "current_debt": 95,
                "long_term_debt": 420,
                "shares_outstanding": 121,
                "weighted_average_diluted_shares": 119,
                "stockholders_equity": 930,
                "dividends": 40,
                "share_buybacks": 58,
                "debt_changes": -15,
                "stock_based_compensation": 28,
                "eps": 5.6,
            },
        ),
        _point(
            2023,
            {
                "revenue": 1085,
                "operating_income": 220,
                "net_income": 160,
                "income_tax_expense": 35,
                "free_cash_flow": 175,
                "operating_cash_flow": 245,
                "capex": 66,
                "cash_and_short_term_investments": 300,
                "cash_and_cash_equivalents": 246,
                "short_term_investments": 54,
                "current_debt": 105,
                "long_term_debt": 430,
                "shares_outstanding": 122,
                "weighted_average_diluted_shares": 120,
                "stockholders_equity": 900,
                "dividends": 36,
                "share_buybacks": 52,
                "debt_changes": -10,
                "stock_based_compensation": 26,
                "eps": 5.2,
            },
        ),
    ]


def test_dcf_normal_partial_and_insufficient(monkeypatch):
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    ok_result = dcf_model.compute(_dataset(_base_points()))
    assert ok_result["model_status"] == "ok"
    assert ok_result["fair_value_per_share"] is not None

    partial_points = _base_points()
    partial_points[0].data["weighted_average_diluted_shares"] = None
    partial_points[1].data["weighted_average_diluted_shares"] = None
    partial_points[2].data["weighted_average_diluted_shares"] = None
    partial_points[1].data["shares_outstanding"] = None
    partial_result = dcf_model.compute(_dataset(partial_points))
    assert partial_result["model_status"] == "partial"

    insufficient_points = _base_points()
    for point in insufficient_points:
        point.data["free_cash_flow"] = None
        point.data["operating_cash_flow"] = None
        point.data["capex"] = None
    insufficient_result = dcf_model.compute(_dataset(insufficient_points))
    assert insufficient_result["model_status"] == "insufficient_data"


def test_reverse_dcf_status_variants(monkeypatch):
    monkeypatch.setattr(reverse_dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    normal_points = _base_points()
    normal_points[0].data["latest_price"] = 85
    normal_result = reverse_dcf_model.compute(_dataset(normal_points))
    assert normal_result["model_status"] in {"ok", "partial"}

    partial_points = _base_points()
    partial_points[0].data["latest_price"] = 80
    partial_points[1].data["free_cash_flow"] = None
    partial_points[2].data["free_cash_flow"] = None
    partial_result = reverse_dcf_model.compute(_dataset(partial_points))
    assert partial_result["model_status"] in {"ok", "partial", "proxy"}

    insufficient_points = _base_points()
    insufficient_points[0].data["revenue"] = None
    insufficient_points[0].data["shares_outstanding"] = None
    insufficient_points[0].data["weighted_average_diluted_shares"] = None
    insufficient_points[0].data["latest_price"] = None
    insufficient_result = reverse_dcf_model.compute(_dataset(insufficient_points))
    assert insufficient_result["model_status"] == "insufficient_data"


def test_roic_status_variants(monkeypatch):
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)

    normal_result = roic_model.compute(_dataset(_base_points()))
    assert normal_result["model_status"] in {"ok", "partial"}

    partial_points = _base_points()
    partial_points[0].data["stockholders_equity"] = None
    partial_result = roic_model.compute(_dataset(partial_points))
    assert partial_result["model_status"] in {"partial", "proxy"}

    insufficient_points = [
        _point(
            2025,
            {
                "revenue": 10,
            },
        )
    ]
    insufficient_result = roic_model.compute(_dataset(insufficient_points))
    assert insufficient_result["model_status"] == "insufficient_data"


def test_capital_allocation_status_variants():
    normal_result = capital_allocation_model.compute(_dataset(_base_points()))
    assert normal_result["model_status"] in {"ok", "partial", "proxy"}

    partial_points = _base_points()
    partial_points[0].data["dividends"] = None
    partial_points[1].data["share_buybacks"] = None
    partial_result = capital_allocation_model.compute(_dataset(partial_points))
    assert partial_result["model_status"] in {"partial", "proxy"}

    insufficient_points = [
        _point(
            2025,
            {
                "revenue": 100,
            },
        )
    ]
    insufficient_result = capital_allocation_model.compute(_dataset(insufficient_points))
    assert insufficient_result["model_status"] == "insufficient_data"
