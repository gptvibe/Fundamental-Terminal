"""Deterministic golden tests for core financial model calculations.

Each test uses toy companies with simple round numbers so expected outputs can be
verified by hand.  Tolerances are documented inline where floating-point arithmetic
produces non-representable results.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

import app.model_engine.models.dcf as dcf_model
import app.model_engine.models.roic as roic_model
from app.model_engine.types import CompanyDataset, FinancialPoint, MarketSnapshot
from app.services.derived_metrics import (
    _abs_if_negative,
    _pct_change,
    _safe_div,
    _sum_non_null,
    build_metrics_timeseries,
)
from app.services.share_count_selection import (
    shares_for_equity_value_per_share,
    shares_for_market_cap,
    shares_for_per_share_metric,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _mock_risk_free(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(
        source_name="U.S. Treasury Daily Par Yield Curve",
        tenor="10y",
        observation_date=date(2026, 3, 20),
        rate_used=0.042,
        fetched_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )


def _annual_point(year: int, data: dict[str, Any]) -> FinancialPoint:
    return FinancialPoint(
        statement_id=year,
        filing_type="10-K",
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        source="https://data.sec.gov/fixture",
        last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data=data,
    )


def _quarterly_stmt(
    period_start: date,
    period_end: date,
    data: dict[str, Any],
    *,
    statement_type: str = "canonical_xbrl",
    source: str = "https://data.sec.gov/fixture",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=int(period_end.strftime("%Y%m%d")),
        period_start=period_start,
        period_end=period_end,
        filing_type="10-Q",
        statement_type=statement_type,
        source=source,
        last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data=data,
    )


def _annual_stmt(
    year: int,
    data: dict[str, Any],
    *,
    statement_type: str = "canonical_xbrl",
    source: str = "https://data.sec.gov/fixture",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=year,
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        filing_type="10-K",
        statement_type=statement_type,
        source=source,
        last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data=data,
    )


def _price_point(trade_date: date, close: float) -> SimpleNamespace:
    return SimpleNamespace(
        trade_date=trade_date,
        close=close,
        source="yahoo_finance",
    )


def _dataset(
    points: list[FinancialPoint],
    *,
    price: float | None = None,
    sector: str = "Information Technology",
) -> CompanyDataset:
    ordered = tuple(sorted(points, key=lambda p: p.period_end, reverse=True))
    snapshot = (
        MarketSnapshot(
            latest_price=price,
            price_date=date(2026, 1, 1),
            price_source="yahoo_finance",
        )
        if price is not None
        else None
    )
    return CompanyDataset(
        company_id=99,
        ticker="TOYX",
        name="Toy Corp",
        sector=sector,
        market_sector=sector,
        market_industry="Software",
        market_snapshot=snapshot,
        financials=ordered,
    )


# ---------------------------------------------------------------------------
# 1. Primitive formula helpers
# ---------------------------------------------------------------------------

class TestPctChange:
    def test_positive_growth(self) -> None:
        # (120 / 100) - 1 = 0.20
        assert _pct_change(120.0, 100.0) == pytest.approx(0.20, rel=1e-9)

    def test_negative_growth(self) -> None:
        # (80 / 100) - 1 = -0.20
        assert _pct_change(80.0, 100.0) == pytest.approx(-0.20, rel=1e-9)

    def test_zero_base_returns_none(self) -> None:
        assert _pct_change(100.0, 0.0) is None

    def test_none_inputs_return_none(self) -> None:
        assert _pct_change(None, 100.0) is None
        assert _pct_change(100.0, None) is None
        assert _pct_change(None, None) is None

    def test_flat_growth(self) -> None:
        assert _pct_change(100.0, 100.0) == pytest.approx(0.0, abs=1e-12)


class TestSafeDiv:
    def test_basic_ratio(self) -> None:
        # 600 / 1000 = 0.60
        assert _safe_div(600.0, 1000.0) == pytest.approx(0.60, rel=1e-9)

    def test_zero_denominator_returns_none(self) -> None:
        assert _safe_div(100.0, 0.0) is None

    def test_none_numerator_returns_none(self) -> None:
        assert _safe_div(None, 1000.0) is None

    def test_none_denominator_returns_none(self) -> None:
        assert _safe_div(100.0, None) is None

    def test_scale_applied(self) -> None:
        # 50 / 1000 * 4 = 0.20
        assert _safe_div(50.0, 1000.0, scale=4.0) == pytest.approx(0.20, rel=1e-9)


class TestSumNonNull:
    def test_all_present(self) -> None:
        assert _sum_non_null(100.0, 200.0, 300.0) == pytest.approx(600.0, rel=1e-9)

    def test_partial_present(self) -> None:
        assert _sum_non_null(100.0, None, 300.0) == pytest.approx(400.0, rel=1e-9)

    def test_all_none_returns_none(self) -> None:
        assert _sum_non_null(None, None) is None


class TestAbsIfNegative:
    def test_negative_becomes_positive(self) -> None:
        assert _abs_if_negative(-50.0) == pytest.approx(50.0, rel=1e-9)

    def test_positive_unchanged(self) -> None:
        # Positive values (e.g. buybacks already stored as positive) pass through.
        assert _abs_if_negative(50.0) == pytest.approx(50.0, rel=1e-9)

    def test_none_returns_none(self) -> None:
        assert _abs_if_negative(None) is None


# ---------------------------------------------------------------------------
# 2. Derived metrics via build_metrics_timeseries (annual cadence)
# ---------------------------------------------------------------------------

def _minimal_annual_data(revenue: float, gross_profit: float, fcf: float) -> dict[str, Any]:
    """Return a minimal but self-consistent financial data dict."""
    operating_income = gross_profit * 0.5
    net_income = gross_profit * 0.4
    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "free_cash_flow": fcf,
        "operating_cash_flow": fcf * 1.2,
        "total_assets": revenue * 2.0,
        "current_assets": revenue * 0.7,
        "current_liabilities": revenue * 0.4,
        "current_debt": revenue * 0.05,
        "long_term_debt": revenue * 0.30,
        "stockholders_equity": revenue * 0.9,
        "cash_and_short_term_investments": revenue * 0.25,
        "shares_outstanding": 1000.0,
        "weighted_average_diluted_shares": 980.0,
        "stock_based_compensation": revenue * 0.03,
        "share_buybacks": -(revenue * 0.02),
        "dividends": -(revenue * 0.01),
        "accounts_receivable": revenue * 0.20,
        "inventory": revenue * 0.08,
        "accounts_payable": revenue * 0.12,
    }


class TestDerivedMetricsFormulas:
    """Test formula arithmetic via the public build_metrics_timeseries API."""

    def test_revenue_growth_is_pct_change_of_successive_annual_revenues(self) -> None:
        # Toy company: rev 1000 → 1200 (20% growth)
        stmts = [
            _annual_stmt(2024, _minimal_annual_data(1000.0, 400.0, 120.0)),
            _annual_stmt(2025, _minimal_annual_data(1200.0, 480.0, 144.0)),
        ]
        prices = [_price_point(date(2025, 12, 31), 50.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual_2025 = next(p for p in series if p["cadence"] == "annual" and p["period_end"].year == 2025)
        expected_growth = (1200.0 / 1000.0) - 1.0  # = 0.20
        assert annual_2025["metrics"]["revenue_growth"] == pytest.approx(expected_growth, rel=1e-9)

    def test_revenue_growth_is_none_for_first_period_with_no_prior_data(self) -> None:
        stmts = [_annual_stmt(2025, _minimal_annual_data(1000.0, 400.0, 120.0))]
        prices = [_price_point(date(2025, 12, 31), 50.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual_2025 = next(p for p in series if p["cadence"] == "annual")
        assert annual_2025["metrics"]["revenue_growth"] is None

    def test_gross_margin_equals_gross_profit_over_revenue(self) -> None:
        # gross_profit = 600, revenue = 1000 → gross_margin = 0.60
        stmts = [_annual_stmt(2025, _minimal_annual_data(1000.0, 600.0, 120.0))]
        prices = [_price_point(date(2025, 12, 31), 50.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual = series[0]
        expected = 600.0 / 1000.0  # = 0.60
        assert annual["metrics"]["gross_margin"] == pytest.approx(expected, rel=1e-9)

    def test_fcf_margin_equals_free_cash_flow_over_revenue(self) -> None:
        # fcf = 150, revenue = 1000 → fcf_margin = 0.15
        stmts = [_annual_stmt(2025, _minimal_annual_data(1000.0, 400.0, 150.0))]
        prices = [_price_point(date(2025, 12, 31), 50.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual = series[0]
        expected = 150.0 / 1000.0  # = 0.15
        assert annual["metrics"]["fcf_margin"] == pytest.approx(expected, rel=1e-9)

    def test_operating_margin_equals_operating_income_over_revenue(self) -> None:
        # operating_income = 0.50 * gross_profit, gross_profit = 400, revenue = 1000
        # operating_margin = 200/1000 = 0.20
        data = _minimal_annual_data(1000.0, 400.0, 120.0)
        expected_oi = data["operating_income"]  # 200.0
        stmts = [_annual_stmt(2025, data)]
        prices = [_price_point(date(2025, 12, 31), 50.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual = series[0]
        expected = expected_oi / 1000.0  # 0.20
        assert annual["metrics"]["operating_margin"] == pytest.approx(expected, rel=1e-9)

    def test_metrics_none_when_revenue_is_missing(self) -> None:
        data = _minimal_annual_data(1000.0, 400.0, 120.0)
        data["revenue"] = None
        stmts = [_annual_stmt(2025, data)]
        prices = [_price_point(date(2025, 12, 31), 50.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual = series[0]
        assert annual["metrics"]["gross_margin"] is None
        assert annual["metrics"]["fcf_margin"] is None
        assert annual["metrics"]["operating_margin"] is None

    def test_market_cap_uses_price_times_shares_outstanding(self) -> None:
        # price = 10, shares_outstanding = 500, buybacks = -10 (negative → outflow)
        # buyback_yield = abs(-10) / (10 * 500) = 10/5000 = 0.002
        data = _minimal_annual_data(1000.0, 400.0, 120.0)
        data["shares_outstanding"] = 500.0
        data["weighted_average_diluted_shares"] = 480.0
        data["share_buybacks"] = -10.0
        stmts = [_annual_stmt(2025, data)]
        prices = [_price_point(date(2025, 12, 31), 10.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual = series[0]
        # market_cap = 10.0 * 500.0 = 5000.0 (uses shares_outstanding for market cap)
        expected_buyback_yield = 10.0 / (10.0 * 500.0)  # = 0.002
        assert annual["metrics"]["buyback_yield"] == pytest.approx(expected_buyback_yield, rel=1e-9)
        assert annual["provenance"]["market_cap_share_source"] == "shares_outstanding"
        assert annual["provenance"]["market_cap_share_source_is_proxy"] is False

    def test_per_share_metric_uses_weighted_average_diluted_shares(self) -> None:
        data = _minimal_annual_data(1000.0, 400.0, 120.0)
        data["shares_outstanding"] = 500.0
        data["weighted_average_diluted_shares"] = 480.0
        stmts = [_annual_stmt(2025, data), _annual_stmt(2024, _minimal_annual_data(900.0, 360.0, 108.0))]
        prices = [_price_point(date(2025, 12, 31), 10.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual_2025 = next(p for p in series if p["cadence"] == "annual" and p["period_end"].year == 2025)
        assert annual_2025["provenance"]["per_share_metric_share_source"] == "weighted_average_diluted_shares"
        assert annual_2025["provenance"]["per_share_metric_share_source_is_proxy"] is False

    def test_market_cap_falls_back_to_diluted_proxy_when_shares_outstanding_missing(self) -> None:
        data = _minimal_annual_data(1000.0, 400.0, 120.0)
        data["shares_outstanding"] = None
        data["weighted_average_diluted_shares"] = 480.0
        stmts = [_annual_stmt(2025, data)]
        prices = [_price_point(date(2025, 12, 31), 10.0)]
        series = build_metrics_timeseries(stmts, prices)

        annual = series[0]
        assert annual["provenance"]["market_cap_share_source"] == "weighted_average_diluted_shares"
        assert annual["provenance"]["market_cap_share_source_is_proxy"] is True


# ---------------------------------------------------------------------------
# 3. Share-count selection golden tests
# ---------------------------------------------------------------------------

class TestShareCountSelectionGoldens:
    """Deterministic tests for share-count priority ordering."""

    # --- shares_for_market_cap ---

    def test_market_cap_zero_shares_outstanding_treated_as_missing(self) -> None:
        # _to_float returns None for 0, so 0 shares_outstanding should fall back.
        sel = shares_for_market_cap({"shares_outstanding": 0, "weighted_average_diluted_shares": 500.0})
        assert sel.value == pytest.approx(500.0)
        assert sel.is_proxy is True

    def test_market_cap_integer_shares_outstanding_resolved(self) -> None:
        sel = shares_for_market_cap({"shares_outstanding": 1000})
        assert sel.value == pytest.approx(1000.0)
        assert sel.source == "shares_outstanding"
        assert sel.is_proxy is False

    # --- shares_for_equity_value_per_share ---

    def test_fair_value_prefers_shares_outstanding_over_diluted(self) -> None:
        sel = shares_for_equity_value_per_share(
            {"shares_outstanding": 800.0, "weighted_average_diluted_shares": 750.0}
        )
        assert sel.value == pytest.approx(800.0)
        assert sel.source == "shares_outstanding"
        assert sel.is_proxy is False

    def test_fair_value_uses_diluted_proxy_when_no_point_in_time(self) -> None:
        sel = shares_for_equity_value_per_share(
            {"shares_outstanding": None, "weighted_average_diluted_shares": 750.0}
        )
        assert sel.value == pytest.approx(750.0)
        assert sel.source == "weighted_average_diluted_shares"
        assert sel.is_proxy is True

    def test_fair_value_returns_none_when_all_missing(self) -> None:
        sel = shares_for_equity_value_per_share({})
        assert sel.value is None
        assert sel.source is None
        assert sel.is_proxy is True

    # --- shares_for_per_share_metric ---

    def test_per_share_priority_diluted_gt_basic_gt_pit(self) -> None:
        all_present = shares_for_per_share_metric(
            {
                "weighted_average_diluted_shares": 300.0,
                "weighted_average_basic_shares": 280.0,
                "shares_outstanding": 260.0,
            }
        )
        assert all_present.value == pytest.approx(300.0)
        assert all_present.source == "weighted_average_diluted_shares"
        assert all_present.is_proxy is False

        no_diluted = shares_for_per_share_metric(
            {
                "weighted_average_diluted_shares": None,
                "weighted_average_basic_shares": 280.0,
                "shares_outstanding": 260.0,
            }
        )
        assert no_diluted.value == pytest.approx(280.0)
        assert no_diluted.source == "weighted_average_basic_shares"
        assert no_diluted.is_proxy is False

        pit_only = shares_for_per_share_metric(
            {
                "weighted_average_diluted_shares": None,
                "weighted_average_basic_shares": None,
                "shares_outstanding": 260.0,
            }
        )
        assert pit_only.value == pytest.approx(260.0)
        assert pit_only.source == "shares_outstanding"
        assert pit_only.is_proxy is True


# ---------------------------------------------------------------------------
# 4. ROIC invested capital golden tests
# ---------------------------------------------------------------------------

class TestROICInvestedCapital:
    """Exact arithmetic checks for invested-capital and ROIC computation."""

    def test_roic_with_full_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify ROIC using equity + current_debt + long_term_debt - cash formula.

        Toy company numbers (easy to verify by hand):
          2024: equity=1000, current_debt=100, long_term_debt=400, cash=200
                IC = 1000+100+400-200 = 1300
                operating_income=200, pretax_income=200, tax=50
                tax_rate = 50/200 = 0.25  =>  nopat = 200*0.75 = 150
                roic_2024 = 150/1300

          2025: equity=1100, current_debt=110, long_term_debt=390, cash=220
                IC = 1100+110+390-220 = 1380
                operating_income=210, pretax_income=210, tax=52.5
                tax_rate = 0.25  =>  nopat = 210*0.75 = 157.5
                roic_2025 = 157.5/1380  (latest, reported in result)

          incremental_roic = (157.5-150)/(1380-1300) = 7.5/80 = 0.09375
        """
        monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)

        points = [
            _annual_point(
                2024,
                {
                    "operating_income": 200.0,
                    "pretax_income": 200.0,
                    "income_tax_expense": 50.0,
                    "stockholders_equity": 1000.0,
                    "current_debt": 100.0,
                    "long_term_debt": 400.0,
                    "cash_and_short_term_investments": 200.0,
                    "operating_cash_flow": 240.0,
                    "capex": -60.0,
                },
            ),
            _annual_point(
                2025,
                {
                    "operating_income": 210.0,
                    "pretax_income": 210.0,
                    "income_tax_expense": 52.5,
                    "stockholders_equity": 1100.0,
                    "current_debt": 110.0,
                    "long_term_debt": 390.0,
                    "cash_and_short_term_investments": 220.0,
                    "operating_cash_flow": 252.0,
                    "capex": -63.0,
                },
            ),
        ]
        result = roic_model.compute(_dataset(points))

        # Computed invested capital and ROIC (hand-verified)
        ic_2024 = 1000.0 + 100.0 + 400.0 - 200.0  # = 1300.0
        ic_2025 = 1100.0 + 110.0 + 390.0 - 220.0  # = 1380.0
        tax_rate = 0.25  # 52.5/210 = 0.25
        nopat_2024 = 200.0 * (1.0 - tax_rate)  # = 150.0
        nopat_2025 = 210.0 * (1.0 - tax_rate)  # = 157.5
        expected_roic = nopat_2025 / ic_2025  # = 157.5/1380
        expected_incremental_roic = (nopat_2025 - nopat_2024) / (ic_2025 - ic_2024)  # 7.5/80 = 0.09375
        capital_cost_proxy = 0.042 + 0.045  # risk_free + 4.5pp premium = 0.087

        assert result["model_status"] in ("supported", "partial", "proxy")
        assert result["roic"] == pytest.approx(expected_roic, rel=1e-6)
        assert result["incremental_roic"] == pytest.approx(expected_incremental_roic, rel=1e-6)
        assert result["capital_cost_proxy"] == pytest.approx(capital_cost_proxy, rel=1e-9)
        expected_spread = expected_roic - capital_cost_proxy
        assert result["spread_vs_capital_cost_proxy"] == pytest.approx(expected_spread, rel=1e-6)

    def test_roic_uses_total_debt_when_individual_debt_components_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When total_debt is supplied but current/long-term breakdown is absent,
        the model should still compute invested capital using total_debt directly."""
        monkeypatch.setattr(roic_model, "get_latest_risk_free_rate", _mock_risk_free)

        # Two years needed for the model; second year is the one we verify.
        points = [
            _annual_point(
                2024,
                {
                    "operating_income": 100.0,
                    "pretax_income": 100.0,
                    "stockholders_equity": 500.0,
                    "total_debt": 200.0,
                    "cash_and_short_term_investments": 50.0,
                    "operating_cash_flow": 120.0,
                    "capex": -30.0,
                },
            ),
            _annual_point(
                2025,
                {
                    "operating_income": 110.0,
                    "pretax_income": 110.0,
                    "stockholders_equity": 550.0,
                    "total_debt": 210.0,
                    "cash_and_short_term_investments": 60.0,
                    "operating_cash_flow": 132.0,
                    "capex": -33.0,
                },
            ),
        ]
        result = roic_model.compute(_dataset(points))

        # IC = equity + total_debt - cash = 550 + 210 - 60 = 700
        # nopat = 110 * 0.21 = 86.9 (default tax 21% — no pretax/tax data pair)
        # The model uses default 21% when pretax or tax_expense is missing/zero.
        expected_ic = 550.0 + 210.0 - 60.0  # = 700.0
        expected_nopat = 110.0 * (1.0 - 0.21)  # = 86.9
        expected_roic = expected_nopat / expected_ic

        assert result["roic"] == pytest.approx(expected_roic, rel=1e-6)
        # proxy_used=True (current/long_term absent) => status_from_data_quality returns "proxy"
        assert result["model_status"] in ("supported", "partial", "proxy")


# ---------------------------------------------------------------------------
# 5. DCF terminal value and equity bridge golden tests
# ---------------------------------------------------------------------------

class TestDCFGoldens:
    """Exact arithmetic golden tests for DCF projection, terminal value, and equity bridge."""

    # Constants matching the production module
    _EQUITY_RISK_PREMIUM = 0.05
    _IT_SECTOR_PREMIUM = 0.015  # dcf._SECTOR_RISK_PREMIUM["information technology"]
    _RISK_FREE = 0.042
    _PROJECTION_YEARS = 5

    def _expected_discount_rate(self) -> float:
        return self._RISK_FREE + self._EQUITY_RISK_PREMIUM + self._IT_SECTOR_PREMIUM  # 0.107

    def _expected_terminal_growth(self) -> float:
        return min(0.03, max(0.005, self._RISK_FREE * 0.6))  # min(0.03, 0.0252) = 0.0252

    def _compute_full_dcf(
        self,
        *,
        starting_fcf: float,
        assumed_growth: float,
        discount_rate: float,
        terminal_growth: float,
        years: int = 5,
    ) -> tuple[float, float, float]:
        """Return (pv_sum, terminal_pv, enterprise_value) mirroring production formula."""
        projected_fcf = starting_fcf
        pv_sum = 0.0
        for year in range(1, years + 1):
            taper = year / years
            g = assumed_growth + (terminal_growth - assumed_growth) * taper
            projected_fcf *= 1.0 + g
            pv_sum += projected_fcf / (1.0 + discount_rate) ** year

        terminal_cf = projected_fcf * (1.0 + terminal_growth)
        terminal_value = terminal_cf / (discount_rate - terminal_growth)
        terminal_pv = terminal_value / (1.0 + discount_rate) ** years
        return pv_sum, terminal_pv, pv_sum + terminal_pv

    def test_dcf_assumptions_are_deterministic_for_known_growth_and_sector(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With a two-point FCF history [100, 110] and IT sector, assumptions are fixed."""
        monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

        points = [
            _annual_point(
                2024,
                {
                    "free_cash_flow": 100.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                    "current_debt": 200.0,
                    "long_term_debt": 100.0,
                    "cash_and_short_term_investments": 150.0,
                },
            ),
            _annual_point(
                2025,
                {
                    "free_cash_flow": 110.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                    "current_debt": 200.0,
                    "long_term_debt": 100.0,
                    "cash_and_short_term_investments": 150.0,
                },
            ),
        ]
        result = dcf_model.compute(_dataset(points, sector="Information Technology"))

        # historical growth rate: (110-100)/100 = 0.10, assumed_growth = 0.10
        expected_assumed_growth = 0.10
        expected_discount_rate = self._expected_discount_rate()
        expected_terminal_growth = self._expected_terminal_growth()

        assert result["assumptions"]["starting_growth_rate"] == pytest.approx(expected_assumed_growth, rel=1e-9)
        assert result["assumptions"]["discount_rate"] == pytest.approx(expected_discount_rate, rel=1e-9)
        assert result["assumptions"]["terminal_growth_rate"] == pytest.approx(expected_terminal_growth, rel=1e-9)
        assert result["assumptions"]["projection_years"] == self._PROJECTION_YEARS
        assert result["assumptions"]["equity_risk_premium"] == pytest.approx(self._EQUITY_RISK_PREMIUM, rel=1e-9)
        assert result["assumptions"]["sector_risk_premium"] == pytest.approx(self._IT_SECTOR_PREMIUM, rel=1e-9)

    def test_dcf_enterprise_value_and_terminal_pv_match_formula(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify enterprise value components against the inline reproduction of the formula."""
        monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

        points = [
            _annual_point(
                2024,
                {
                    "free_cash_flow": 100.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                    "current_debt": 200.0,
                    "long_term_debt": 100.0,
                    "cash_and_short_term_investments": 150.0,
                },
            ),
            _annual_point(
                2025,
                {
                    "free_cash_flow": 110.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                    "current_debt": 200.0,
                    "long_term_debt": 100.0,
                    "cash_and_short_term_investments": 150.0,
                },
            ),
        ]
        result = dcf_model.compute(_dataset(points, sector="Information Technology"))

        dr = self._expected_discount_rate()
        tg = self._expected_terminal_growth()
        pv_sum, terminal_pv, ev = self._compute_full_dcf(
            starting_fcf=110.0, assumed_growth=0.10, discount_rate=dr, terminal_growth=tg
        )

        assert result["present_value_of_cash_flows"] == pytest.approx(pv_sum, rel=1e-6)
        assert result["terminal_value_present_value"] == pytest.approx(terminal_pv, rel=1e-6)
        assert result["enterprise_value"] == pytest.approx(ev, rel=1e-6)

    def test_dcf_equity_bridge_with_full_capital_structure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """EV - net_debt = equity_value; equity_value / shares = fair_value_per_share."""
        monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

        # current_debt=200, long_term_debt=100 → total_debt=300
        # cash=150 → net_debt=150  → equity_value = EV - 150
        points = [
            _annual_point(
                2024,
                {
                    "free_cash_flow": 100.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                    "current_debt": 200.0,
                    "long_term_debt": 100.0,
                    "cash_and_short_term_investments": 150.0,
                },
            ),
            _annual_point(
                2025,
                {
                    "free_cash_flow": 110.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                    "current_debt": 200.0,
                    "long_term_debt": 100.0,
                    "cash_and_short_term_investments": 150.0,
                },
            ),
        ]
        result = dcf_model.compute(_dataset(points, sector="Information Technology"))

        dr = self._expected_discount_rate()
        tg = self._expected_terminal_growth()
        _, _, ev = self._compute_full_dcf(
            starting_fcf=110.0, assumed_growth=0.10, discount_rate=dr, terminal_growth=tg
        )

        total_debt = 200.0 + 100.0  # = 300
        cash = 150.0
        net_debt = total_debt - cash  # = 150
        equity_value = ev - net_debt
        fair_value_per_share = equity_value / 1000.0  # shares_outstanding

        assert result["value_basis"] == "equity_value"
        assert result["total_debt"] == pytest.approx(total_debt, rel=1e-9)
        assert result["net_debt"] == pytest.approx(net_debt, rel=1e-9)
        assert result["equity_value"] == pytest.approx(equity_value, rel=1e-6)
        assert result["fair_value_per_share"] == pytest.approx(fair_value_per_share, rel=1e-6)
        assert result["capital_structure_proxied"] is False

    def test_dcf_equity_bridge_degrades_to_enterprise_value_proxy_when_debt_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without debt info, fair_value_per_share = enterprise_value / shares."""
        monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

        points = [
            _annual_point(
                2024,
                {
                    "free_cash_flow": 100.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                    # No debt or cash fields
                },
            ),
            _annual_point(
                2025,
                {
                    "free_cash_flow": 110.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                },
            ),
        ]
        result = dcf_model.compute(_dataset(points, sector="Information Technology"))

        dr = self._expected_discount_rate()
        tg = self._expected_terminal_growth()
        _, _, ev = self._compute_full_dcf(
            starting_fcf=110.0, assumed_growth=0.10, discount_rate=dr, terminal_growth=tg
        )
        expected_fvps = ev / 1000.0  # no net-debt deduction

        assert result["value_basis"] == "enterprise_value_proxy"
        assert result["fair_value_per_share"] == pytest.approx(expected_fvps, rel=1e-6)
        assert result["capital_structure_proxied"] is True

    def test_dcf_growth_clamped_to_max_growth_rate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When historical growth exceeds MAX_GROWTH_RATE (0.15), assumed_growth is clamped."""
        monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

        # 100 → 200 implies 100% growth; should be clamped to 0.15
        points = [
            _annual_point(
                2024,
                {
                    "free_cash_flow": 100.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                },
            ),
            _annual_point(
                2025,
                {
                    "free_cash_flow": 200.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                },
            ),
        ]
        result = dcf_model.compute(_dataset(points, sector="Information Technology"))

        assert result["assumptions"]["starting_growth_rate"] == pytest.approx(
            dcf_model.MAX_GROWTH_RATE, rel=1e-9
        )

    def test_dcf_growth_clamped_to_min_growth_rate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When FCF declines sharply, assumed_growth is clamped to MIN_GROWTH_RATE (-0.10)."""
        monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

        # 100 → 10 implies -90% growth; should be clamped to -0.10
        points = [
            _annual_point(
                2024,
                {
                    "free_cash_flow": 100.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                },
            ),
            _annual_point(
                2025,
                {
                    "free_cash_flow": 10.0,
                    "shares_outstanding": 1000.0,
                    "weighted_average_diluted_shares": 980.0,
                },
            ),
        ]
        result = dcf_model.compute(_dataset(points, sector="Information Technology"))

        assert result["assumptions"]["starting_growth_rate"] == pytest.approx(
            dcf_model.MIN_GROWTH_RATE, rel=1e-9
        )

    def test_dcf_share_count_for_fair_value_uses_shares_outstanding_over_diluted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fair-value share count should prefer shares_outstanding (not proxy)."""
        monkeypatch.setattr(dcf_model, "get_latest_risk_free_rate", _mock_risk_free)

        # shares_outstanding=1000 vs weighted_average_diluted_shares=500
        # per-share value with 1000 shares should be half that with 500 shares.
        points_1000 = [
            _annual_point(2024, {"free_cash_flow": 100.0, "shares_outstanding": 1000.0}),
            _annual_point(2025, {"free_cash_flow": 110.0, "shares_outstanding": 1000.0}),
        ]
        points_500 = [
            _annual_point(2024, {"free_cash_flow": 100.0, "shares_outstanding": 500.0}),
            _annual_point(2025, {"free_cash_flow": 110.0, "shares_outstanding": 500.0}),
        ]

        result_1000 = dcf_model.compute(_dataset(points_1000))
        result_500 = dcf_model.compute(_dataset(points_500))

        # Both should succeed with equity_value = enterprise_value (no debt/cash info)
        assert result_1000["fair_value_per_share"] is not None
        assert result_500["fair_value_per_share"] is not None
        fvps_1000 = result_1000["fair_value_per_share"]
        fvps_500 = result_500["fair_value_per_share"]
        assert fvps_500 == pytest.approx(fvps_1000 * 2.0, rel=1e-6)

        assert result_1000["assumption_provenance"]["valuation_framework"]["per_share_share_source"] == "shares_outstanding"
        assert result_1000["assumption_provenance"]["valuation_framework"]["per_share_share_source_is_proxy"] is False


# ---------------------------------------------------------------------------
# 6. TTM aggregation golden tests
# ---------------------------------------------------------------------------

def _quarterly_data(revenue: float, fcf: float | None, gross_profit: float) -> dict[str, Any]:
    """Minimal quarterly financial data."""
    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": gross_profit * 0.5,
        "net_income": gross_profit * 0.4,
        "free_cash_flow": fcf,
        "operating_cash_flow": (fcf * 1.2) if fcf is not None else None,
        "total_assets": revenue * 2.0,
        "current_assets": revenue * 0.7,
        "current_liabilities": revenue * 0.4,
        "current_debt": revenue * 0.05,
        "long_term_debt": revenue * 0.30,
        "stockholders_equity": revenue * 0.9,
        "cash_and_short_term_investments": revenue * 0.25,
        "shares_outstanding": 1000.0,
        "weighted_average_diluted_shares": 980.0,
        "stock_based_compensation": revenue * 0.03,
        "share_buybacks": -(revenue * 0.02),
        "dividends": -(revenue * 0.01),
        "accounts_receivable": revenue * 0.20,
        "inventory": revenue * 0.08,
        "accounts_payable": revenue * 0.12,
    }


class TestTTMAggregation:
    """TTM flow fields must equal the sum of the 4 trailing quarterly values."""

    _Q1 = (date(2025, 1, 1), date(2025, 3, 31))    # 90 days
    _Q2 = (date(2025, 4, 1), date(2025, 6, 30))    # 91 days
    _Q3 = (date(2025, 7, 1), date(2025, 9, 30))    # 92 days
    _Q4 = (date(2025, 10, 1), date(2025, 12, 31))  # 92 days

    def _four_quarters(
        self,
        revenues: tuple[float, float, float, float],
        fcfs: tuple[float | None, float | None, float | None, float | None],
        gross_profits: tuple[float, float, float, float],
    ) -> list[SimpleNamespace]:
        quarters = [self._Q1, self._Q2, self._Q3, self._Q4]
        return [
            _quarterly_stmt(s, e, _quarterly_data(rev, fcf, gp))
            for (s, e), rev, fcf, gp in zip(quarters, revenues, fcfs, gross_profits)
        ]

    def test_ttm_revenue_and_fcf_equal_sum_of_four_quarters(self) -> None:
        revenues = (100.0, 110.0, 120.0, 130.0)
        fcfs = (25.0, 27.0, 30.0, 32.0)
        gross_profits = (40.0, 44.0, 48.0, 52.0)
        stmts = self._four_quarters(revenues, fcfs, gross_profits)
        prices = [_price_point(date(2025, 12, 31), 10.0)]

        series = build_metrics_timeseries(stmts, prices)
        ttm_rows = [p for p in series if p["cadence"] == "ttm"]
        assert ttm_rows, "Expected at least one TTM row"

        latest_ttm = ttm_rows[-1]
        # TTM revenue = 100+110+120+130 = 460
        # TTM fcf = 25+27+30+32 = 114
        expected_ttm_revenue = sum(revenues)  # 460.0
        expected_ttm_fcf = sum(fcfs)  # 114.0
        expected_ttm_gross_profit = sum(gross_profits)  # 184.0
        expected_gross_margin = expected_ttm_gross_profit / expected_ttm_revenue  # 184/460

        assert latest_ttm["metrics"]["gross_margin"] == pytest.approx(expected_gross_margin, rel=1e-9)
        assert latest_ttm["metrics"]["fcf_margin"] == pytest.approx(
            expected_ttm_fcf / expected_ttm_revenue, rel=1e-9
        )

    def test_ttm_fcf_is_none_when_any_quarter_has_missing_fcf(self) -> None:
        """One quarter with fcf=None poisons the TTM fcf aggregate."""
        revenues = (100.0, 110.0, 120.0, 130.0)
        fcfs: tuple[float | None, float | None, float | None, float | None] = (25.0, None, 30.0, 32.0)
        gross_profits = (40.0, 44.0, 48.0, 52.0)
        stmts = self._four_quarters(revenues, fcfs, gross_profits)
        prices = [_price_point(date(2025, 12, 31), 10.0)]

        series = build_metrics_timeseries(stmts, prices)
        ttm_rows = [p for p in series if p["cadence"] == "ttm"]
        assert ttm_rows

        latest_ttm = ttm_rows[-1]
        # fcf is None → fcf_margin should be None
        assert latest_ttm["metrics"]["fcf_margin"] is None
        # gross_margin can still be computed (gross_profit and revenue are available)
        assert latest_ttm["metrics"]["gross_margin"] is not None
        # The missing-component flag should be set for free_cash_flow
        assert any(
            "ttm_metric_missing_component:free_cash_flow" in flag
            for flag in latest_ttm["quality"]["flags"]
        )

    def test_ttm_gross_margin_is_none_when_all_quarters_have_missing_gross_profit(self) -> None:
        revenues = (100.0, 110.0, 120.0, 130.0)
        fcfs = (25.0, 27.0, 30.0, 32.0)
        gross_profits = (40.0, 44.0, 48.0, 52.0)
        stmts = self._four_quarters(revenues, fcfs, gross_profits)
        # Blank out gross_profit on all quarters
        for stmt in stmts:
            stmt.data["gross_profit"] = None
        prices = [_price_point(date(2025, 12, 31), 10.0)]

        series = build_metrics_timeseries(stmts, prices)
        ttm_rows = [p for p in series if p["cadence"] == "ttm"]
        assert ttm_rows

        latest_ttm = ttm_rows[-1]
        assert latest_ttm["metrics"]["gross_margin"] is None

    def test_ttm_validation_flags_when_window_spans_different_sources(self) -> None:
        """Quarters from a different source origin break TTM compatibility."""
        stmts = [
            _quarterly_stmt(
                self._Q1[0], self._Q1[1],
                _quarterly_data(100.0, 25.0, 40.0),
                source="https://api.fdic.gov/fixture",
            ),
            _quarterly_stmt(
                self._Q2[0], self._Q2[1],
                _quarterly_data(110.0, 27.0, 44.0),
                source="https://data.sec.gov/fixture",
            ),
            _quarterly_stmt(
                self._Q3[0], self._Q3[1],
                _quarterly_data(120.0, 30.0, 48.0),
                source="https://data.sec.gov/fixture",
            ),
            _quarterly_stmt(
                self._Q4[0], self._Q4[1],
                _quarterly_data(130.0, 32.0, 52.0),
                source="https://data.sec.gov/fixture",
            ),
        ]
        prices = [_price_point(date(2025, 12, 31), 10.0)]
        series = build_metrics_timeseries(stmts, prices)

        # The mixed-source TTM row should either be absent or flagged as invalid.
        ttm_rows = [p for p in series if p["cadence"] == "ttm"]
        for row in ttm_rows:
            has_invalid_flag = row["provenance"]["ttm_validation_status"] != "valid"
            has_incompatible_flag = any(
                "incompatible" in f for f in row["quality"]["flags"]
            )
            if has_invalid_flag or has_incompatible_flag:
                break
        else:
            # If a TTM row exists and is marked valid with incompatible sources,
            # that is itself a regression to catch.
            if ttm_rows:
                for row in ttm_rows:
                    assert row["provenance"]["ttm_validation_status"] != "valid", (
                        "TTM window with incompatible sources should not be marked valid"
                    )
