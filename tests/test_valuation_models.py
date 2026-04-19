from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import app.model_engine.models.capital_allocation as capital_allocation_model
import app.model_engine.models.dcf as dcf_model
import app.model_engine.models.reverse_dcf as reverse_dcf_model
import app.model_engine.models.roic as roic_model
from app.model_engine.registry import MODEL_REGISTRY
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


def _dataset(points: list[FinancialPoint], *, price: float | None = 85.0, sector: str = "Technology") -> CompanyDataset:
    ordered = tuple(sorted(points, key=lambda item: item.period_end, reverse=True))
    snapshot = (
        MarketSnapshot(
            latest_price=price,
            price_date=date(2026, 3, 21),
            price_source="yahoo_finance",
        )
        if price is not None
        else None
    )
    return CompanyDataset(
        company_id=1,
        ticker="ACME",
        name="Acme Corp",
        sector=sector,
        market_sector=sector,
        market_industry="Software",
        market_snapshot=snapshot,
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


def _reverse_dcf_value_from_growth(*, growth: float, starting_fcf: float, discount_rate: float, terminal_growth: float) -> float:
    projected_fcf = starting_fcf
    present_value = 0.0
    for year in range(1, reverse_dcf_model.PROJECTION_YEARS + 1):
        taper_factor = year / reverse_dcf_model.PROJECTION_YEARS
        year_growth = growth + (terminal_growth - growth) * taper_factor
        projected_fcf *= 1 + year_growth
        present_value += projected_fcf / ((1 + discount_rate) ** year)

    terminal_cash_flow = projected_fcf * (1 + terminal_growth)
    terminal_value = terminal_cash_flow / (discount_rate - terminal_growth)
    return present_value + (terminal_value / ((1 + discount_rate) ** reverse_dcf_model.PROJECTION_YEARS))


def _solve_growth_for_target_value(*, target_value: float, starting_fcf: float, discount_rate: float, terminal_growth: float) -> float:
    low = reverse_dcf_model.MIN_SOLVE_GROWTH
    high = reverse_dcf_model.MAX_SOLVE_GROWTH
    for _ in range(reverse_dcf_model.SOLVE_ITERATIONS):
        mid = (low + high) / 2
        mid_value = _reverse_dcf_value_from_growth(
            growth=mid,
            starting_fcf=starting_fcf,
            discount_rate=discount_rate,
            terminal_growth=terminal_growth,
        )
        if abs(mid_value - target_value) <= max(target_value * 1e-6, 1e-6):
            return mid
        if mid_value > target_value:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def test_dcf_normal_partial_and_insufficient(monkeypatch):
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    ok_result = dcf_model.compute(_dataset(_base_points()))
    assert ok_result["model_status"] == "supported"
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
    normal_result = reverse_dcf_model.compute(_dataset(normal_points, price=85))
    assert normal_result["model_status"] in {"supported", "partial"}

    partial_points = _base_points()
    partial_points[1].data["free_cash_flow"] = None
    partial_points[2].data["free_cash_flow"] = None
    partial_result = reverse_dcf_model.compute(_dataset(partial_points, price=80))
    assert partial_result["model_status"] in {"supported", "partial", "proxy"}

    insufficient_points = _base_points()
    insufficient_points[0].data["revenue"] = None
    insufficient_points[0].data["shares_outstanding"] = None
    insufficient_points[0].data["weighted_average_diluted_shares"] = None
    insufficient_result = reverse_dcf_model.compute(_dataset(insufficient_points, price=None))
    assert insufficient_result["model_status"] == "insufficient_data"


def test_capital_allocation_uses_price_backed_market_cap_not_eps_proxy():
    points = [
        _point(
            2025,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "weighted_average_diluted_shares": 100,
                "eps": 100,
            },
        ),
        _point(
            2024,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "weighted_average_diluted_shares": 100,
                "eps": 100,
            },
        ),
        _point(
            2023,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "weighted_average_diluted_shares": 100,
                "eps": 100,
            },
        ),
    ]

    result = capital_allocation_model.compute(_dataset(points, price=10.0))

    assert result["net_shareholder_distribution"] == pytest.approx(33.0)
    assert result["shareholder_yield"] == pytest.approx(0.033, rel=1e-6)
    assert result["shareholder_yield_basis"]["method"] == "latest_market_cap"
    assert result["shareholder_yield_basis"]["market_cap_denominator"] == pytest.approx(1000.0)


def test_reverse_dcf_uses_enterprise_value_target_when_capital_structure_available(monkeypatch):
    monkeypatch.setattr(reverse_dcf_model, "get_latest_risk_free_rate", _mock_risk_free)
    points = [
        _point(
            2025,
            {
                "revenue": 1000,
                "operating_income": 180,
                "free_cash_flow": 100,
                "cash_and_short_term_investments": 100,
                "current_debt": 100,
                "long_term_debt": 300,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
            },
        ),
        _point(
            2024,
            {
                "revenue": 960,
                "operating_income": 168,
                "free_cash_flow": 96,
                "cash_and_short_term_investments": 90,
                "current_debt": 90,
                "long_term_debt": 280,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
            },
        ),
        _point(
            2023,
            {
                "revenue": 925,
                "operating_income": 160,
                "free_cash_flow": 92,
                "cash_and_short_term_investments": 85,
                "current_debt": 85,
                "long_term_debt": 270,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
            },
        ),
    ]

    result = reverse_dcf_model.compute(_dataset(points, price=10.0))
    discount_rate = _mock_risk_free().rate_used + 0.055
    terminal_growth = min(0.03, max(0.005, _mock_risk_free().rate_used * 0.6))
    expected_growth = _solve_growth_for_target_value(
        target_value=1300.0,
        starting_fcf=100.0,
        discount_rate=discount_rate,
        terminal_growth=terminal_growth,
    )

    assert result["market_cap_proxy"] == pytest.approx(1000.0)
    assert result["enterprise_value_proxy"] == pytest.approx(1300.0)
    assert result["net_debt"] == pytest.approx(300.0)
    assert result["implied_growth"] == pytest.approx(expected_growth, abs=1e-6)
    assert result["assumption_provenance"]["target_value"]["basis"] == "enterprise_value"


def test_reverse_dcf_fcf_proxy_uses_operating_cash_flow_less_capex(monkeypatch):
    monkeypatch.setattr(reverse_dcf_model, "get_latest_risk_free_rate", _mock_risk_free)
    points = _base_points()
    points[0].data["free_cash_flow"] = None
    points[0].data["operating_cash_flow"] = 180
    points[0].data["capex"] = 80
    points[0].data["revenue"] = 1000

    result = reverse_dcf_model.compute(_dataset(points, price=85.0))

    assert result["model_status"] == "proxy"
    assert result["implied_margin"] == pytest.approx(0.10, abs=1e-9)
    assert result["assumption_provenance"]["free_cash_flow_margin"]["source"] == "operating_cash_flow_less_capex"


def test_roic_incremental_roic_uses_delta_nopat_over_delta_invested_capital(monkeypatch):
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)
    points = [
        _point(
            2025,
            {
                "operating_income": 300,
                "income_tax_expense": 60,
                "stockholders_equity": 960,
                "current_debt": 80,
                "long_term_debt": 260,
                "cash_and_short_term_investments": 100,
                "capex": 120,
                "operating_cash_flow": 300,
            },
        ),
        _point(
            2024,
            {
                "operating_income": 250,
                "income_tax_expense": 50,
                "stockholders_equity": 900,
                "current_debt": 60,
                "long_term_debt": 240,
                "cash_and_short_term_investments": 200,
                "capex": 110,
                "operating_cash_flow": 275,
            },
        ),
        _point(
            2023,
            {
                "operating_income": 210,
                "income_tax_expense": 42,
                "stockholders_equity": 860,
                "current_debt": 55,
                "long_term_debt": 220,
                "cash_and_short_term_investments": 175,
                "capex": 100,
                "operating_cash_flow": 250,
            },
        ),
    ]

    result = roic_model.compute(_dataset(points))

    assert result["roic"] == pytest.approx(0.20, abs=1e-9)
    assert result["incremental_roic"] == pytest.approx(0.20, abs=1e-9)


def test_dcf_and_reverse_dcf_mark_financial_sector_unsupported(monkeypatch):
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)
    monkeypatch.setattr(reverse_dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    points = _base_points()
    bank_dataset = _dataset(points, sector="Banks")

    dcf_result = dcf_model.compute(bank_dataset)
    reverse_result = reverse_dcf_model.compute(bank_dataset)

    assert dcf_result["model_status"] == "unsupported"
    assert reverse_result["model_status"] == "unsupported"


def test_roic_status_variants(monkeypatch):
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)

    normal_result = roic_model.compute(_dataset(_base_points()))
    assert normal_result["model_status"] in {"supported", "partial"}
    assert normal_result["roic"] == pytest.approx(0.1912280702, abs=1e-6)
    assert normal_result["incremental_roic"] == pytest.approx(1.4666666667, abs=1e-6)

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
    assert normal_result["model_status"] in {"supported", "partial", "proxy"}
    assert normal_result["net_shareholder_distribution"] == pytest.approx(212.0)
    assert normal_result["shareholder_yield"] == pytest.approx(212.0 / (85.0 * 118.0), rel=1e-6)

    partial_points = _base_points()
    partial_points[0].data["dividends"] = None
    partial_points[1].data["share_buybacks"] = None
    partial_result = capital_allocation_model.compute(_dataset(partial_points))
    assert partial_result["model_status"] in {"partial", "proxy"}

    no_price_result = capital_allocation_model.compute(_dataset(_base_points(), price=None))
    assert no_price_result["model_status"] == "proxy"
    assert no_price_result["shareholder_yield"] is None
    assert no_price_result["net_shareholder_distribution"] == pytest.approx(212.0)

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


def test_registry_wrapper_adds_standardized_model_metadata(monkeypatch):
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    result = MODEL_REGISTRY["dcf"].compute(_dataset(_base_points()))

    assert result["model_status"] == "supported"
    assert result["confidence_score"] is not None
    assert result["confidence_reasons"]
    assert "free_cash_flow" in result["fields_used"]
    assert result["proxy_usage"]["used"] is False
    assert result["stale_inputs"] == []
    assert result["sector_suitability"]["status"] == "supported"
    assert result["misleading_reasons"]
