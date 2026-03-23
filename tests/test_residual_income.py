"""Tests for residual_income valuation model."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import app.model_engine.models.residual_income as ri_model
from app.model_engine.types import CompanyDataset, FinancialPoint, MarketSnapshot


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


def _dataset(
    points: list[FinancialPoint],
    *,
    price: float | None = 50.0,
    sector: str = "Financials",
    market_sector: str = "Financials",
) -> CompanyDataset:
    ordered = tuple(sorted(points, key=lambda item: item.period_end, reverse=True))
    snapshot = (
        MarketSnapshot(latest_price=price, price_date=date(2026, 3, 21), price_source="test")
        if price is not None
        else None
    )
    return CompanyDataset(
        company_id=1,
        ticker="BANK",
        name="Test Bank",
        sector=sector,
        market_sector=market_sector,
        market_industry="Banking",
        market_snapshot=snapshot,
        financials=ordered,
    )


# ---------------------------------------------------------------------------
# Happy-path: financial firm with all required fields
# ---------------------------------------------------------------------------

def test_residual_income_ok_status(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    pts = [
        _point(2025, {"total_assets": 1_000_000, "total_liabilities": 800_000, "net_income": 20_000, "shares_outstanding": 1_000}),
        _point(2024, {"total_assets": 950_000, "total_liabilities": 780_000, "net_income": 18_000, "shares_outstanding": 1_000}),
        _point(2023, {"total_assets": 900_000, "total_liabilities": 760_000, "net_income": 16_000, "shares_outstanding": 1_000}),
    ]
    result = ri_model.compute(_dataset(pts))
    assert result["status"] in ("ok", "partial", "proxy")
    assert result["intrinsic_value"]["intrinsic_value_per_share"] is not None
    assert result["intrinsic_value"]["intrinsic_value_per_share"] > 0
    assert result["inputs"]["book_equity"] == pytest.approx(200_000.0)
    assert result["inputs"]["roe"] == pytest.approx(0.10, abs=0.001)


def test_residual_income_includes_cost_of_equity(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    # CoE = 0.042 + 0.05 + 0.005 = 0.097
    pts = [_point(2025, {"total_assets": 500_000, "total_liabilities": 400_000, "net_income": 10_000, "shares_outstanding": 500})]
    result = ri_model.compute(_dataset(pts))
    coe = result["assumption_provenance"]["cost_of_equity"]
    assert coe is not None
    assert abs(coe - 0.097) < 0.001


def test_residual_income_primary_for_financial_firms(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    pts = [_point(2025, {"total_assets": 500_000, "total_liabilities": 400_000, "net_income": 8_000, "shares_outstanding": 500})]
    result = ri_model.compute(_dataset(pts, sector="Financials", market_sector="Financials"))
    assert result.get("primary_for_sector") is True


def test_residual_income_not_primary_for_tech(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    def _tech_dataset(pts):
        ordered = tuple(sorted(pts, key=lambda item: item.period_end, reverse=True))
        snapshot = MarketSnapshot(latest_price=50.0, price_date=date(2026, 3, 21), price_source="test")
        return CompanyDataset(
            company_id=2, ticker="TECH", name="Tech Corp",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software",  # not a financial keyword
            market_snapshot=snapshot,
            financials=ordered,
        )
    pts = [_point(2025, {"total_assets": 500_000, "total_liabilities": 200_000, "net_income": 50_000, "shares_outstanding": 1_000})]
    result = ri_model.compute(_tech_dataset(pts))
    assert result.get("primary_for_sector") is False


# ---------------------------------------------------------------------------
# Insufficient data paths
# ---------------------------------------------------------------------------

def test_residual_income_insufficient_data_no_net_income(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    pts = [_point(2025, {"total_assets": 500_000, "total_liabilities": 400_000, "shares_outstanding": 1_000})]
    result = ri_model.compute(_dataset(pts))
    assert result["status"] == "insufficient_data"


def test_residual_income_insufficient_data_no_book_equity(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    pts = [_point(2025, {"net_income": 10_000, "shares_outstanding": 1_000})]
    result = ri_model.compute(_dataset(pts))
    assert result["status"] == "insufficient_data"


def test_residual_income_no_history(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    result = ri_model.compute(_dataset([]))
    assert result["status"] == "insufficient_data"


# ---------------------------------------------------------------------------
# Projections structure
# ---------------------------------------------------------------------------

def test_residual_income_projections_count(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    pts = [_point(2025, {"total_assets": 500_000, "total_liabilities": 400_000, "net_income": 10_000, "shares_outstanding": 500})]
    result = ri_model.compute(_dataset(pts))
    if result["status"] != "insufficient_data":
        assert len(result["projections"]) == ri_model.PROJECTION_YEARS


def test_residual_income_upside_vs_price(monkeypatch):
    monkeypatch.setattr(ri_model, "get_latest_risk_free_rate", _mock_risk_free)
    # Book equity per share = 200, price much lower → large upside expected
    pts = [_point(2025, {"total_assets": 2_000_000, "total_liabilities": 1_800_000, "net_income": 20_000, "shares_outstanding": 1_000})]
    result = ri_model.compute(_dataset(pts, price=100.0))
    if result["status"] != "insufficient_data":
        assert result["intrinsic_value"]["upside_vs_price"] is not None


# ---------------------------------------------------------------------------
# DCF sector risk premium upgrade
# ---------------------------------------------------------------------------

def test_dcf_sector_premium_technology(monkeypatch):
    from types import SimpleNamespace
    import app.model_engine.models.dcf as dcf_model

    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    def _make_tech_dataset() -> CompanyDataset:
        pts = [
            _point(2024, {"free_cash_flow": 100_000, "cash_and_short_term_investments": 50_000, "current_debt": 10_000, "long_term_debt": 20_000, "shares_outstanding": 1_000, "weighted_average_diluted_shares": 1_000}),
            _point(2023, {"free_cash_flow": 90_000, "cash_and_short_term_investments": 50_000, "current_debt": 10_000, "long_term_debt": 20_000, "shares_outstanding": 1_000, "weighted_average_diluted_shares": 1_000}),
        ]
        ordered = tuple(sorted(pts, key=lambda item: item.period_end, reverse=True))
        return CompanyDataset(
            company_id=1, ticker="TECH", name="Tech Corp",
            sector="Information Technology", market_sector="Technology",
            market_industry="Software",
            market_snapshot=MarketSnapshot(latest_price=200.0, price_date=date(2026, 3, 21), price_source="test"),
            financials=ordered,
        )

    result = dcf_model.compute(_make_tech_dataset())
    if result["status"] not in ("unsupported", "insufficient_data"):
        sector_premium = result["assumptions"]["sector_risk_premium"]
        assert sector_premium is not None
        assert sector_premium > 0  # Tech should have positive additional premium
