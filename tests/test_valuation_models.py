from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import app.model_engine.models.altman_z as altman_z_model
import app.model_engine.models.capital_allocation as capital_allocation_model
import app.model_engine.models.dcf as dcf_model
import app.model_engine.models.piotroski as piotroski_model
import app.model_engine.models.ratios as ratios_model
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


def _quarterly_point(year: int, quarter_end: date, data: dict[str, float | int | None]) -> FinancialPoint:
    quarter_start_month = quarter_end.month - 2
    return FinancialPoint(
        statement_id=int(quarter_end.strftime("%Y%m%d")),
        filing_type="10-Q",
        period_start=date(year, quarter_start_month, 1),
        period_end=quarter_end,
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


def test_altman_z_classic_public_variant_uses_market_cap_for_x4():
    points = [
        _point(
            2025,
            {
                "total_assets": 1000,
                "total_liabilities": 400,
                "current_assets": 500,
                "current_liabilities": 200,
                "retained_earnings": 100,
                "operating_income": 150,
                "revenue": 1000,
                "shares_outstanding": 50,
                "weighted_average_diluted_shares": 40,
            },
        )
    ]

    result = altman_z_model.compute(_dataset(points, price=10.0))

    assert result["model_status"] == "supported"
    assert result["variant"] == "classic_public_company_1968"
    assert result["factors"]["market_value_equity_to_liabilities"] == pytest.approx(1.25, rel=1e-9)
    assert result["factors"]["market_value_equity_to_liabilities"] != pytest.approx(1.5, rel=1e-9)
    assert result["z_score_approximate"] == pytest.approx(2.745, rel=1e-9)


def test_altman_z_quarterly_only_inputs_are_not_treated_as_supported_annual_score():
    points = [
        _quarterly_point(
            2025,
            date(2025, 9, 30),
            {
                "total_assets": 1000,
                "total_liabilities": 400,
                "current_assets": 500,
                "current_liabilities": 200,
                "retained_earnings": 100,
                "operating_income": 150,
                "revenue": 1000,
                "shares_outstanding": 50,
            },
        )
    ]

    result = altman_z_model.compute(_dataset(points, price=10.0))

    assert result["model_status"] == "partial"
    assert result["filing_type"] == "10-Q"
    assert result["z_score_approximate"] is None
    assert "annual" in result["reason"].lower()


def test_altman_z_missing_factors_do_not_rescale_score_upward():
    points = [
        _point(
            2025,
            {
                "total_assets": 1000,
                "total_liabilities": 400,
                "current_assets": 500,
                "current_liabilities": 200,
                "retained_earnings": 100,
                "operating_income": 150,
                "revenue": None,
                "shares_outstanding": 50,
            },
        )
    ]

    result = altman_z_model.compute(_dataset(points, price=10.0))

    assert result["model_status"] == "partial"
    assert result["z_score_approximate"] is None
    assert "sales_to_assets" in result["missing_factors"]


def test_piotroski_lower_leverage_uses_long_term_debt_not_total_liabilities():
    points = [
        _point(
            2025,
            {
                "net_income": 120,
                "total_assets": 1000,
                "current_assets": 420,
                "current_liabilities": 220,
                "operating_cash_flow": 150,
                "shares_outstanding": 100,
                "long_term_debt": 180,
                "total_liabilities": 720,
                "gross_profit": 500,
                "revenue": 900,
            },
        ),
        _point(
            2024,
            {
                "net_income": 100,
                "total_assets": 950,
                "current_assets": 380,
                "current_liabilities": 240,
                "operating_cash_flow": 120,
                "shares_outstanding": 100,
                "long_term_debt": 240,
                "total_liabilities": 650,
                "gross_profit": 460,
                "revenue": 840,
            },
        ),
        _point(
            2023,
            {
                "net_income": 90,
                "total_assets": 900,
                "current_assets": 360,
                "current_liabilities": 235,
                "operating_cash_flow": 110,
                "shares_outstanding": 101,
                "long_term_debt": 260,
                "total_liabilities": 620,
                "gross_profit": 430,
                "revenue": 800,
            },
        ),
    ]

    result = piotroski_model.compute(_dataset(points))

    assert result["model_status"] == "supported"
    assert result["criteria"]["lower_leverage"] is True
    assert result["criterion_basis"]["lower_leverage"] == "long_term_debt_to_total_assets"


def test_piotroski_lower_leverage_is_unavailable_without_long_term_debt():
    points = [
        _point(
            2025,
            {
                "net_income": 120,
                "total_assets": 1000,
                "current_assets": 420,
                "current_liabilities": 220,
                "operating_cash_flow": 150,
                "shares_outstanding": 100,
                "long_term_debt": None,
                "total_liabilities": 720,
                "gross_profit": 500,
                "revenue": 900,
            },
        ),
        _point(
            2024,
            {
                "net_income": 100,
                "total_assets": 950,
                "current_assets": 380,
                "current_liabilities": 240,
                "operating_cash_flow": 120,
                "shares_outstanding": 100,
                "long_term_debt": None,
                "total_liabilities": 650,
                "gross_profit": 460,
                "revenue": 840,
            },
        ),
        _point(
            2023,
            {
                "net_income": 90,
                "total_assets": 900,
                "current_assets": 360,
                "current_liabilities": 235,
                "operating_cash_flow": 110,
                "shares_outstanding": 101,
                "long_term_debt": None,
                "total_liabilities": 620,
                "gross_profit": 430,
                "revenue": 800,
            },
        ),
    ]

    result = piotroski_model.compute(_dataset(points))

    assert result["model_status"] == "partial"
    assert result["criteria"]["lower_leverage"] is None
    assert "lower_leverage" in result["unavailable_criteria"]


def test_dcf_prefers_point_in_time_shares_outstanding_for_per_share_value(monkeypatch):
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    points = _base_points()
    points[0].data["shares_outstanding"] = 200
    points[0].data["weighted_average_diluted_shares"] = 100

    result = dcf_model.compute(_dataset(points))

    assert result["fair_value_per_share"] == pytest.approx(result["equity_value"] / 200, rel=1e-9)
    assert result["fair_value_per_share"] != pytest.approx(result["equity_value"] / 100, rel=1e-9)


def test_dcf_cash_fallback_marks_capital_structure_proxy_without_company_risk_premium(monkeypatch):
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    points = _base_points()
    for point in points:
        point.data["cash_and_short_term_investments"] = None

    dataset = _dataset(points)
    result = dcf_model.compute(dataset)
    expected_discount_rate = (
        _mock_risk_free().rate_used
        + dcf_model.EQUITY_RISK_PREMIUM
        + dcf_model._sector_risk_premium(dataset)
    )

    assert result["assumptions"]["discount_rate"] == pytest.approx(expected_discount_rate, rel=1e-9)
    assert result["assumption_provenance"]["discount_rate_inputs"]["company_risk_premium"] == pytest.approx(0.0, abs=1e-12)
    assert result["input_quality"]["starting_cash_flow_proxied"] is False
    assert result["input_quality"]["capital_structure_proxied"] is True


def test_dcf_starting_cash_flow_proxy_flag_only_tracks_fcf_proxying(monkeypatch):
    monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

    points = _base_points()
    points[0].data["free_cash_flow"] = None
    points[0].data["operating_cash_flow"] = 190
    points[0].data["capex"] = 70

    dataset = _dataset(points)
    result = dcf_model.compute(dataset)
    expected_discount_rate = (
        _mock_risk_free().rate_used
        + dcf_model.EQUITY_RISK_PREMIUM
        + dcf_model._sector_risk_premium(dataset)
        + dcf_model.BASE_COMPANY_RISK_PREMIUM
    )

    assert result["assumptions"]["discount_rate"] == pytest.approx(expected_discount_rate, rel=1e-9)
    assert result["assumption_provenance"]["discount_rate_inputs"]["company_risk_premium"] == pytest.approx(
        dcf_model.BASE_COMPANY_RISK_PREMIUM,
        rel=1e-9,
    )
    assert result["input_quality"]["starting_cash_flow_proxied"] is True
    assert result["input_quality"]["capital_structure_proxied"] is False


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


def test_capital_allocation_uses_latest_market_cap_for_shareholder_yield():
    points = [
        _point(
            2025,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "shares_outstanding": 200,
                "weighted_average_diluted_shares": 100,
                "eps": 1000,
            },
        ),
        _point(
            2024,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
                "eps": 1,
            },
        ),
        _point(
            2023,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
                "eps": 1,
            },
        ),
    ]

    result = capital_allocation_model.compute(_dataset(points, price=10.0))

    assert result["net_shareholder_distribution"] == pytest.approx(33.0)
    assert result["annualized_shareholder_distribution"] == pytest.approx(11.0)
    assert result["shareholder_yield"] == pytest.approx(11.0 / 2000.0, rel=1e-6)
    assert result["cumulative_shareholder_distribution_ratio"] == pytest.approx(33.0 / 2000.0, rel=1e-6)
    assert result["shareholder_yield_basis"]["method"] == "latest_market_cap"
    assert result["shareholder_yield_basis"]["market_cap_denominator"] == pytest.approx(2000.0)
    assert result["shareholder_yield_basis"]["metric_definition"] == "annualized_net_shareholder_distribution_divided_by_market_cap"
    assert result["shareholder_yield_basis"]["numerator_horizon_years"] == 3
    assert result["shareholder_yield_basis"]["market_cap_observations_used"] == 1


def test_capital_allocation_missing_price_returns_none_for_shareholder_yield():
    result = capital_allocation_model.compute(_dataset(_base_points(), price=None))

    assert result["model_status"] == "proxy"
    assert result["shareholder_yield"] is None
    assert result["shareholder_yield_basis"]["method"] is None
    assert result["shareholder_yield_basis"]["market_cap_denominator"] is None
    assert result["net_shareholder_distribution"] == pytest.approx(212.0)


def test_capital_allocation_has_no_eps_based_fallback_for_shareholder_yield():
    points = [
        _point(
            2025,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
                "eps": 5000,
            },
        ),
        _point(
            2024,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
                "eps": 1,
            },
        ),
        _point(
            2023,
            {
                "dividends": 10,
                "share_buybacks": 2,
                "stock_based_compensation": 1,
                "debt_changes": 0,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 100,
                "eps": 1,
            },
        ),
    ]

    result = capital_allocation_model.compute(_dataset(points, price=10.0))

    assert result["shareholder_yield"] == pytest.approx(11.0 / 1000.0, rel=1e-6)
    assert result["shareholder_yield"] != pytest.approx(11.0 / (100.0 * 5000.0 * 12.0), rel=1e-6)
    assert result["shareholder_yield_basis"]["method"] == "latest_market_cap"
    assert result["shareholder_yield_basis"]["market_cap_denominator"] == pytest.approx(1000.0)


def test_ratios_quarterly_stock_flow_metrics_are_annualized_and_disclosed():
    points = [
        _quarterly_point(
            2025,
            date(2025, 9, 30),
            {
                "revenue": 100,
                "gross_profit": 55,
                "operating_income": 20,
                "net_income": 10,
                "operating_cash_flow": 18,
                "free_cash_flow": 12,
                "capex": -6,
                "interest_expense": -5,
                "stock_based_compensation": 2,
                "dividends": -3,
                "total_assets": 200,
                "total_liabilities": 80,
                "stockholders_equity": 120,
                "current_debt": 15,
                "long_term_debt": 40,
                "cash_and_short_term_investments": 20,
            },
        ),
        _quarterly_point(
            2025,
            date(2025, 6, 30),
            {
                "revenue": 90,
                "gross_profit": 48,
                "operating_income": 18,
                "net_income": 9,
                "operating_cash_flow": 16,
                "free_cash_flow": 10,
                "capex": -5,
                "interest_expense": -4,
                "stock_based_compensation": 2,
                "dividends": -2,
                "total_assets": 180,
                "total_liabilities": 70,
                "stockholders_equity": 110,
                "current_debt": 12,
                "long_term_debt": 42,
                "cash_and_short_term_investments": 18,
            },
        ),
    ]

    result = ratios_model.compute(_dataset(points))
    values = result["values"]
    semantics = result["metric_semantics"]

    assert result["model_status"] == "supported"
    assert result["cadence"] == "quarterly"
    assert result["annualization_factor"] == 4
    assert semantics["return_on_assets"] == "annualized"
    assert semantics["return_on_equity"] == "annualized"
    assert semantics["asset_turnover"] == "annualized"
    assert semantics["net_margin"] == "period_based"
    assert values["return_on_assets"] == pytest.approx((10 / 190) * 4, rel=1e-9)
    assert values["return_on_equity"] == pytest.approx((10 / 115) * 4, rel=1e-9)
    assert values["asset_turnover"] == pytest.approx((100 / 190) * 4, rel=1e-9)
    assert values["return_on_assets"] != pytest.approx(10 / 190, rel=1e-9)
    assert values["return_on_equity"] != pytest.approx(10 / 115, rel=1e-9)
    assert values["asset_turnover"] != pytest.approx(100 / 190, rel=1e-9)


def test_ratios_capex_intensity_uses_abs_capex_for_negative_outflow():
    points = [
        _point(
            2025,
            {
                "revenue": 100,
                "gross_profit": 55,
                "operating_income": 20,
                "net_income": 10,
                "operating_cash_flow": 18,
                "free_cash_flow": 12,
                "capex": -25,
                "interest_expense": -5,
                "stock_based_compensation": 2,
                "dividends": -3,
                "total_assets": 200,
                "total_liabilities": 80,
                "stockholders_equity": 120,
                "current_debt": 15,
                "long_term_debt": 40,
                "cash_and_short_term_investments": 20,
            },
        ),
        _point(
            2024,
            {
                "revenue": 90,
                "gross_profit": 50,
                "operating_income": 18,
                "net_income": 9,
                "operating_cash_flow": 16,
                "free_cash_flow": 11,
                "capex": -20,
                "interest_expense": -4,
                "stock_based_compensation": 2,
                "dividends": -2,
                "total_assets": 190,
                "total_liabilities": 78,
                "stockholders_equity": 112,
                "current_debt": 14,
                "long_term_debt": 42,
                "cash_and_short_term_investments": 18,
            },
        ),
    ]

    result = ratios_model.compute(_dataset(points))

    assert result["model_status"] == "supported"
    assert result["values"]["capex_intensity"] == pytest.approx(0.25, rel=1e-9)
    assert result["values"]["capex_intensity"] > 0


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

    assert result["roic"] == pytest.approx(0.1975, abs=1e-9)
    assert result["incremental_roic"] == pytest.approx(0.29625, abs=1e-9)


def test_roic_uses_pretax_income_for_tax_rate_when_available(monkeypatch):
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)
    points = [
        _point(
            2025,
            {
                "operating_income": 200,
                "pretax_income": 100,
                "income_tax_expense": 20,
                "stockholders_equity": 300,
                "current_debt": 100,
                "long_term_debt": 100,
                "cash_and_short_term_investments": 0,
                "capex": 20,
                "operating_cash_flow": 100,
            },
        ),
        _point(
            2024,
            {
                "operating_income": 180,
                "pretax_income": 90,
                "income_tax_expense": 18,
                "stockholders_equity": 290,
                "current_debt": 100,
                "long_term_debt": 90,
                "cash_and_short_term_investments": 0,
                "capex": 18,
                "operating_cash_flow": 95,
            },
        ),
    ]

    result = roic_model.compute(_dataset(points))

    assert result["roic"] == pytest.approx((200.0 * (1.0 - 0.20)) / 500.0, abs=1e-9)
    assert result["roic"] != pytest.approx((200.0 * (1.0 - 0.10)) / 500.0, abs=1e-9)


def test_roic_incremental_roic_changes_with_capital_deployed(monkeypatch):
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)
    low_capital_delta_points = [
        _point(
            2025,
            {
                "operating_income": 220,
                "income_tax_expense": 22,
                "stockholders_equity": 410,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 20,
                "operating_cash_flow": 100,
            },
        ),
        _point(
            2024,
            {
                "operating_income": 205,
                "income_tax_expense": 20.5,
                "stockholders_equity": 405,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 18,
                "operating_cash_flow": 95,
            },
        ),
        _point(
            2023,
            {
                "operating_income": 200,
                "income_tax_expense": 20,
                "stockholders_equity": 400,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 16,
                "operating_cash_flow": 90,
            },
        ),
    ]
    high_capital_delta_points = [
        _point(
            2025,
            {
                "operating_income": 220,
                "income_tax_expense": 22,
                "stockholders_equity": 600,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 20,
                "operating_cash_flow": 100,
            },
        ),
        _point(
            2024,
            {
                "operating_income": 205,
                "income_tax_expense": 20.5,
                "stockholders_equity": 500,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 18,
                "operating_cash_flow": 95,
            },
        ),
        _point(
            2023,
            {
                "operating_income": 200,
                "income_tax_expense": 20,
                "stockholders_equity": 400,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 16,
                "operating_cash_flow": 90,
            },
        ),
    ]

    low_capital_delta_result = roic_model.compute(_dataset(low_capital_delta_points))
    high_capital_delta_result = roic_model.compute(_dataset(high_capital_delta_points))

    assert low_capital_delta_result["incremental_roic"] == pytest.approx((173.8 - 158.0) / (510.0 - 500.0), abs=1e-9)
    assert high_capital_delta_result["incremental_roic"] == pytest.approx((173.8 - 158.0) / (700.0 - 500.0), abs=1e-9)
    assert high_capital_delta_result["incremental_roic"] != low_capital_delta_result["incremental_roic"]


def test_roic_zero_capital_delta_returns_none(monkeypatch):
    monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)
    points = [
        _point(
            2025,
            {
                "operating_income": 220,
                "income_tax_expense": 22,
                "stockholders_equity": 400,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 20,
                "operating_cash_flow": 100,
            },
        ),
        _point(
            2024,
            {
                "operating_income": 210,
                "income_tax_expense": 21,
                "stockholders_equity": 400,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 18,
                "operating_cash_flow": 95,
            },
        ),
        _point(
            2023,
            {
                "operating_income": 200,
                "income_tax_expense": 20,
                "stockholders_equity": 400,
                "current_debt": 50,
                "long_term_debt": 50,
                "cash_and_short_term_investments": 0,
                "capex": 16,
                "operating_cash_flow": 90,
            },
        ),
    ]

    result = roic_model.compute(_dataset(points))

    assert result["incremental_roic"] is None


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
    assert normal_result["roic"] == pytest.approx(0.1801754386, abs=1e-6)
    assert normal_result["incremental_roic"] == pytest.approx(6.32, abs=1e-6)

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
    expected_market_cap = 85.0 * 120.0
    assert normal_result["model_status"] in {"supported", "partial", "proxy"}
    assert normal_result["net_shareholder_distribution"] == pytest.approx(212.0)
    assert normal_result["annualized_shareholder_distribution"] == pytest.approx(212.0 / 3.0, rel=1e-6)
    assert normal_result["shareholder_yield"] == pytest.approx((212.0 / 3.0) / expected_market_cap, rel=1e-6)
    assert normal_result["cumulative_shareholder_distribution_ratio"] == pytest.approx(212.0 / expected_market_cap, rel=1e-6)

    partial_points = _base_points()
    partial_points[0].data["dividends"] = None
    partial_points[1].data["share_buybacks"] = None
    partial_result = capital_allocation_model.compute(_dataset(partial_points))
    assert partial_result["model_status"] in {"partial", "proxy"}

    no_price_result = capital_allocation_model.compute(_dataset(_base_points(), price=None))
    assert no_price_result["model_status"] == "proxy"
    assert no_price_result["shareholder_yield"] is None
    assert no_price_result["shareholder_yield_basis"]["market_cap_denominator"] is None
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
