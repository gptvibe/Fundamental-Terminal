from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

import app.services.derived_metrics as derived_metrics_module
from app.services.derived_metrics import build_metrics_timeseries



def _statement(
    period_start: date,
    period_end: date,
    filing_type: str,
    revenue: float,
    shares: float,
    *,
    segment_breakdown: list[dict[str, float]] | None = None,
):
    data = {
        "revenue": revenue,
        "gross_profit": revenue * 0.4,
        "operating_income": revenue * 0.2,
        "net_income": revenue * 0.15,
        "operating_cash_flow": revenue * 0.18,
        "free_cash_flow": revenue * 0.12,
        "total_assets": revenue * 2.0,
        "current_assets": revenue * 0.7,
        "current_liabilities": revenue * 0.4,
        "current_debt": revenue * 0.05,
        "long_term_debt": revenue * 0.3,
        "stockholders_equity": revenue * 0.9,
        "shares_outstanding": shares,
        "weighted_average_diluted_shares": shares,
        "stock_based_compensation": revenue * 0.03,
        "share_buybacks": -(revenue * 0.02),
        "dividends": -(revenue * 0.01),
        "accounts_receivable": revenue * 0.2,
        "inventory": revenue * 0.08,
        "accounts_payable": revenue * 0.12,
        "segment_breakdown": segment_breakdown or [],
    }
    return SimpleNamespace(
        id=int(period_end.strftime("%Y%m%d")),
        period_start=period_start,
        period_end=period_end,
        filing_type=filing_type,
        statement_type="canonical_xbrl",
        source="https://data.sec.gov/example",
        last_updated=datetime.now(timezone.utc),
        data=data,
    )



def _price(trade_date: date, close: float):
    return SimpleNamespace(
        trade_date=trade_date,
        close=close,
        source="yahoo_finance",
    )



def test_build_metrics_timeseries_includes_quarterly_annual_and_ttm_rows():
    statements = [
        _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100),
        _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 110, 101),
        _statement(date(2025, 7, 1), date(2025, 9, 30), "10-Q", 120, 102),
        _statement(
            date(2025, 10, 1),
            date(2025, 12, 31),
            "10-Q",
            130,
            103,
            segment_breakdown=[
                {"segment_name": "Products", "revenue": 80.0},
                {"segment_name": "Services", "revenue": 50.0},
            ],
        ),
        _statement(
            date(2025, 1, 1),
            date(2025, 12, 31),
            "10-K",
            460,
            103,
            segment_breakdown=[
                {"segment_name": "Products", "revenue": 280.0},
                {"segment_name": "Services", "revenue": 180.0},
            ],
        ),
    ]
    prices = [_price(date(2025, 12, 31), 50.0)]

    series = build_metrics_timeseries(statements, prices)
    cadences = {point["cadence"] for point in series}

    assert cadences == {"quarterly", "annual", "ttm"}

    latest_quarterly = [point for point in series if point["cadence"] == "quarterly"][-1]
    assert latest_quarterly["metrics"]["revenue_growth"] is not None
    assert latest_quarterly["metrics"]["share_dilution"] is not None

    latest_ttm = [point for point in series if point["cadence"] == "ttm"][-1]
    assert latest_ttm["metrics"]["gross_margin"] is not None
    assert latest_ttm["metrics"]["operating_margin"] is not None
    assert latest_ttm["metrics"]["fcf_margin"] is not None
    assert latest_ttm["metrics"]["roic_proxy"] is not None
    assert latest_ttm["metrics"]["leverage_ratio"] is not None
    assert latest_ttm["metrics"]["current_ratio"] is not None
    assert latest_ttm["metrics"]["sbc_burden"] is not None
    assert latest_ttm["metrics"]["buyback_yield"] is not None
    assert latest_ttm["metrics"]["dividend_yield"] is not None
    assert latest_ttm["metrics"]["working_capital_days"] is not None
    assert latest_ttm["metrics"]["accrual_ratio"] is not None
    assert latest_ttm["metrics"]["cash_conversion"] is not None
    assert latest_ttm["metrics"]["segment_concentration"] is not None
    assert latest_ttm["quality"]["coverage_ratio"] > 0.8
    assert latest_ttm["provenance"]["price_source"] == "yahoo_finance"
    assert latest_ttm["provenance"]["formula_version"] == "sec_metrics_v3"
    assert latest_quarterly["provenance"]["metric_semantics"]["buyback_yield"] == "annualized"
    assert latest_quarterly["provenance"]["metric_semantics"]["dividend_yield"] == "annualized"
    assert latest_quarterly["provenance"]["metric_semantics"]["working_capital_days"] == "annualized"
    assert latest_ttm["provenance"]["metric_semantics"]["buyback_yield"] == "ttm"
    assert latest_ttm["provenance"]["metric_semantics"]["working_capital_days"] == "ttm"


def test_build_metrics_timeseries_annualizes_quarterly_flow_metrics_to_match_stable_ttm():
    statements = [
        _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100),
        _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 100, 100),
        _statement(date(2025, 7, 1), date(2025, 9, 30), "10-Q", 100, 100),
        _statement(date(2025, 10, 1), date(2025, 12, 31), "10-Q", 100, 100),
    ]
    prices = [_price(date(2025, 12, 31), 50.0)]

    series = build_metrics_timeseries(statements, prices)
    latest_quarterly = [point for point in series if point["cadence"] == "quarterly"][-1]
    latest_ttm = [point for point in series if point["cadence"] == "ttm"][-1]

    expected_buyback_yield = (100.0 * 0.02 * 4.0) / (50.0 * 100.0)
    expected_dividend_yield = (100.0 * 0.01 * 4.0) / (50.0 * 100.0)
    expected_working_capital_days = ((100.0 * 0.2) + (100.0 * 0.08) - (100.0 * 0.12)) / (100.0 * 4.0) * 365.0

    assert latest_quarterly["metrics"]["buyback_yield"] == pytest.approx(expected_buyback_yield, rel=1e-9)
    assert latest_ttm["metrics"]["buyback_yield"] == pytest.approx(expected_buyback_yield, rel=1e-9)
    assert latest_quarterly["metrics"]["dividend_yield"] == pytest.approx(expected_dividend_yield, rel=1e-9)
    assert latest_ttm["metrics"]["dividend_yield"] == pytest.approx(expected_dividend_yield, rel=1e-9)
    assert latest_quarterly["metrics"]["working_capital_days"] == pytest.approx(expected_working_capital_days, rel=1e-9)
    assert latest_ttm["metrics"]["working_capital_days"] == pytest.approx(expected_working_capital_days, rel=1e-9)
    assert latest_quarterly["provenance"]["metric_semantics"]["buyback_yield"] == "annualized"
    assert latest_ttm["provenance"]["metric_semantics"]["buyback_yield"] == "ttm"


def test_build_metrics_timeseries_includes_bank_specific_metrics():
    statements = [
        SimpleNamespace(
            id=1,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 3, 31),
            filing_type="CALL",
            statement_type="canonical_bank_regulatory",
            source="https://api.fdic.gov/banks/financials",
            last_updated=datetime.now(timezone.utc),
            data={
                "net_income": 10.0,
                "total_assets": 1000.0,
                "stockholders_equity": 100.0,
                "net_interest_income": 30.0,
                "provision_for_credit_losses": 3.0,
                "deposits_total": 700.0,
                "core_deposits": 500.0,
                "uninsured_deposits": 100.0,
                "net_interest_margin": 0.031,
                "nonperforming_assets_ratio": 0.01,
                "common_equity_tier1_ratio": 0.11,
                "tier1_risk_weighted_ratio": 0.12,
                "total_risk_based_capital_ratio": 0.14,
                "tangible_common_equity": 82.0,
                "weighted_average_diluted_shares": 10.0,
            },
        ),
        SimpleNamespace(
            id=2,
            period_start=date(2025, 4, 1),
            period_end=date(2025, 6, 30),
            filing_type="CALL",
            statement_type="canonical_bank_regulatory",
            source="https://api.fdic.gov/banks/financials",
            last_updated=datetime.now(timezone.utc),
            data={
                "net_income": 11.0,
                "total_assets": 1010.0,
                "stockholders_equity": 101.0,
                "net_interest_income": 31.0,
                "provision_for_credit_losses": 3.0,
                "deposits_total": 710.0,
                "core_deposits": 505.0,
                "uninsured_deposits": 102.0,
                "net_interest_margin": 0.032,
                "nonperforming_assets_ratio": 0.011,
                "common_equity_tier1_ratio": 0.112,
                "tier1_risk_weighted_ratio": 0.121,
                "total_risk_based_capital_ratio": 0.141,
                "tangible_common_equity": 83.0,
                "weighted_average_diluted_shares": 10.0,
            },
        ),
        SimpleNamespace(
            id=3,
            period_start=date(2025, 7, 1),
            period_end=date(2025, 9, 30),
            filing_type="CALL",
            statement_type="canonical_bank_regulatory",
            source="https://api.fdic.gov/banks/financials",
            last_updated=datetime.now(timezone.utc),
            data={
                "net_income": 12.0,
                "total_assets": 1020.0,
                "stockholders_equity": 102.0,
                "net_interest_income": 32.0,
                "provision_for_credit_losses": 4.0,
                "deposits_total": 720.0,
                "core_deposits": 510.0,
                "uninsured_deposits": 105.0,
                "net_interest_margin": 0.033,
                "nonperforming_assets_ratio": 0.012,
                "common_equity_tier1_ratio": 0.113,
                "tier1_risk_weighted_ratio": 0.122,
                "total_risk_based_capital_ratio": 0.142,
                "tangible_common_equity": 84.0,
                "weighted_average_diluted_shares": 10.0,
            },
        ),
        SimpleNamespace(
            id=4,
            period_start=date(2025, 10, 1),
            period_end=date(2025, 12, 31),
            filing_type="CALL",
            statement_type="canonical_bank_regulatory",
            source="https://api.fdic.gov/banks/financials",
            last_updated=datetime.now(timezone.utc),
            data={
                "net_income": 13.0,
                "total_assets": 1030.0,
                "stockholders_equity": 103.0,
                "net_interest_income": 33.0,
                "provision_for_credit_losses": 4.0,
                "deposits_total": 730.0,
                "core_deposits": 515.0,
                "uninsured_deposits": 108.0,
                "net_interest_margin": 0.034,
                "nonperforming_assets_ratio": 0.013,
                "common_equity_tier1_ratio": 0.114,
                "tier1_risk_weighted_ratio": 0.123,
                "total_risk_based_capital_ratio": 0.143,
                "tangible_common_equity": 85.0,
                "weighted_average_diluted_shares": 10.0,
            },
        ),
    ]

    series = build_metrics_timeseries(statements, [])
    latest_ttm = [point for point in series if point["cadence"] == "ttm"][-1]

    assert latest_ttm["metrics"]["net_interest_margin"] == 0.034
    assert latest_ttm["metrics"]["provision_burden"] is not None
    assert latest_ttm["metrics"]["cet1_ratio"] == 0.114
    assert latest_ttm["metrics"]["core_deposit_ratio"] is not None
    assert latest_ttm["metrics"]["tangible_book_value_per_share"] == 8.5
    assert latest_ttm["metrics"]["roatce"] is not None


def _legacy_price_on_or_before(prices: list[dict[str, Any]], period_end: date) -> dict[str, Any] | None:
    if not prices:
        return None
    date_index = [entry["trade_date"] for entry in prices]
    insertion = bisect_right(date_index, period_end)
    if insertion <= 0:
        return None
    return prices[insertion - 1]


def _legacy_build_cadence_points(
    rows: list[dict[str, Any]],
    cadence: str,
    prices: list[dict[str, Any]],
    *,
    filing_type: str | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None

    for row in rows:
        matched_price = _legacy_price_on_or_before(prices, row["period_end"])
        metrics = derived_metrics_module._compute_metrics(
            row["data"],
            previous["data"] if previous else None,
            matched_price,
            cadence=cadence,
            statement_type=row["statement_type"],
        )
        quality_flags = list(metrics["flags"])
        if cadence == "ttm":
            quality_flags.extend(row.get("ttm_validation_flags", []))
            quality_flags = sorted(set(quality_flags))

        provenance = {
            "statement_type": row["statement_type"],
            "statement_source": row["source"],
            "price_source": matched_price["source"] if matched_price else None,
            "formula_version": derived_metrics_module.FORMULA_VERSION,
            "formula_ids": derived_metrics_module.formula_ids_for_derived_metrics(derived_metrics_module.METRIC_KEYS),
            "metric_semantics": derived_metrics_module._metric_semantics(cadence, row["statement_type"]),
            "market_cap_share_source": metrics["market_cap_share_source"],
            "market_cap_share_source_is_proxy": metrics["market_cap_share_source_is_proxy"],
            "per_share_metric_share_source": metrics["per_share_metric_share_source"],
            "per_share_metric_share_source_is_proxy": metrics["per_share_metric_share_source_is_proxy"],
        }
        if cadence == "ttm":
            provenance.update(
                {
                    "ttm_validation_status": row.get("ttm_validation_status", "valid"),
                    "ttm_construction": row.get("ttm_construction", "four_reported_quarters"),
                    "ttm_formula": "sum(Q1..Q4 comparable fiscal quarters) or annual - (Q1+Q2+Q3) for derived Q4",
                    "ttm_component_period_ends": [
                        component.isoformat() if isinstance(component, date) else component
                        for component in row.get("ttm_component_period_ends", [])
                    ],
                    "ttm_component_filing_types": row.get("ttm_component_filing_types", []),
                    "ttm_component_statement_ids": row.get("ttm_component_statement_ids", []),
                }
            )

        output.append(
            {
                "cadence": cadence,
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "filing_type": filing_type or row["filing_type"],
                "metrics": metrics["values"],
                "provenance": provenance,
                "quality": {
                    "available_metrics": metrics["available_metrics"],
                    "missing_metrics": metrics["missing_metrics"],
                    "coverage_ratio": metrics["coverage_ratio"],
                    "flags": quality_flags,
                },
            }
        )
        previous = row

    return output


def _legacy_build_metrics_timeseries(
    financials: list[Any],
    price_history: list[Any],
    *,
    cadence: str | None = None,
    max_points: int | None = None,
) -> list[dict[str, Any]]:
    rows = derived_metrics_module._normalize_financial_rows(financials)
    prices = derived_metrics_module._normalize_price_rows(price_history)

    annual_rows = [row for row in rows if row["filing_type"] in derived_metrics_module.ANNUAL_FORMS]
    quarterly_rows = [row for row in rows if row["filing_type"] in derived_metrics_module.QUARTERLY_FORMS]

    output: list[dict[str, Any]] = []
    output.extend(_legacy_build_cadence_points(annual_rows, "annual", prices))
    output.extend(_legacy_build_cadence_points(quarterly_rows, "quarterly", prices))

    ttm_rows = derived_metrics_module._build_ttm_rows(quarterly_rows, annual_rows)
    output.extend(_legacy_build_cadence_points(ttm_rows, "ttm", prices, filing_type="TTM"))

    series = sorted(output, key=lambda item: (item["period_end"], item["cadence"]))
    if cadence is not None:
        series = [item for item in series if item["cadence"] == cadence]
    if max_points is not None and max_points > 0 and len(series) > max_points:
        series = series[-max_points:]
    return series


def test_build_metrics_timeseries_matches_legacy_price_index_behavior() -> None:
    statements = [
        _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100),
        _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 110, 101),
        _statement(date(2025, 7, 1), date(2025, 9, 30), "10-Q", 120, 102),
        _statement(date(2025, 10, 1), date(2025, 12, 31), "10-Q", 130, 103),
        _statement(date(2025, 1, 1), date(2025, 12, 31), "10-K", 460, 103),
    ]
    prices = [
        _price(date(2025, 1, 15), 43.0),
        _price(date(2025, 3, 31), 45.0),
        _price(date(2025, 6, 15), 46.0),
        _price(date(2025, 9, 30), 48.0),
        _price(date(2025, 12, 31), 50.0),
    ]

    optimized = build_metrics_timeseries(statements, prices)
    legacy = _legacy_build_metrics_timeseries(statements, prices)

    assert optimized == legacy


def test_build_metrics_timeseries_matches_legacy_behavior_with_filters() -> None:
    statements = [
        _statement(date(2024, 1, 1), date(2024, 3, 31), "10-Q", 80, 95),
        _statement(date(2024, 4, 1), date(2024, 6, 30), "10-Q", 90, 96),
        _statement(date(2024, 7, 1), date(2024, 9, 30), "10-Q", 95, 97),
        _statement(date(2024, 10, 1), date(2024, 12, 31), "10-Q", 98, 98),
        _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100),
        _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 110, 101),
    ]
    prices = [
        _price(date(2024, 3, 31), 40.0),
        _price(date(2024, 6, 30), 41.0),
        _price(date(2024, 9, 30), 42.0),
        _price(date(2024, 12, 31), 43.0),
        _price(date(2025, 3, 31), 44.0),
        _price(date(2025, 6, 30), 45.0),
    ]

    optimized = build_metrics_timeseries(statements, prices, cadence="quarterly", max_points=3)
    legacy = _legacy_build_metrics_timeseries(statements, prices, cadence="quarterly", max_points=3)

    assert optimized == legacy


def test_market_cap_uses_point_in_time_shares_and_emits_provenance() -> None:
    statement = _statement(date(2025, 1, 1), date(2025, 12, 31), "10-K", 100, 100)
    statement.data["weighted_average_diluted_shares"] = 120
    prices = [_price(date(2025, 12, 31), 10.0)]

    series = build_metrics_timeseries([statement], prices)
    point = [item for item in series if item["cadence"] == "annual"][0]

    expected_buyback_yield = 2.0 / 1000.0
    assert point["metrics"]["buyback_yield"] == pytest.approx(expected_buyback_yield, rel=1e-9)
    assert point["provenance"]["market_cap_share_source"] == "shares_outstanding"
    assert point["provenance"]["market_cap_share_source_is_proxy"] is False


def test_market_cap_diluted_fallback_is_marked_proxy_in_provenance() -> None:
    statement = _statement(date(2025, 1, 1), date(2025, 12, 31), "10-K", 100, 100)
    statement.data["shares_outstanding"] = None
    statement.data["weighted_average_diluted_shares"] = 120
    prices = [_price(date(2025, 12, 31), 10.0)]

    series = build_metrics_timeseries([statement], prices)
    point = [item for item in series if item["cadence"] == "annual"][0]

    expected_buyback_yield = 2.0 / 1200.0
    assert point["metrics"]["buyback_yield"] == pytest.approx(expected_buyback_yield, rel=1e-9)
    assert point["provenance"]["market_cap_share_source"] == "weighted_average_diluted_shares"
    assert point["provenance"]["market_cap_share_source_is_proxy"] is True


def test_per_share_metric_prefers_weighted_average_basic_when_diluted_missing() -> None:
    statement = _statement(date(2025, 1, 1), date(2025, 12, 31), "10-K", 100, 100)
    statement.data["weighted_average_diluted_shares"] = None
    statement.data["weighted_average_basic_shares"] = 120
    statement.data["tangible_common_equity"] = 240

    series = build_metrics_timeseries([statement], [])
    point = [item for item in series if item["cadence"] == "annual"][0]

    assert point["metrics"]["tangible_book_value_per_share"] == pytest.approx(2.0, rel=1e-9)
    assert point["provenance"]["per_share_metric_share_source"] == "weighted_average_basic_shares"
    assert point["provenance"]["per_share_metric_share_source_is_proxy"] is False


def test_ttm_clean_four_quarters_emits_validated_ttm() -> None:
    statements = [
        _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100),
        _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 110, 100),
        _statement(date(2025, 7, 1), date(2025, 9, 30), "10-Q", 120, 100),
        _statement(date(2025, 10, 1), date(2025, 12, 31), "10-Q", 130, 100),
    ]

    series = build_metrics_timeseries(statements, [])
    ttm = [point for point in series if point["cadence"] == "ttm"][-1]

    assert ttm["provenance"]["ttm_validation_status"] == "valid"
    assert ttm["provenance"]["ttm_construction"] == "four_reported_quarters"
    assert "ttm_missing_quarter" not in ttm["quality"]["flags"]
    assert ttm["metrics"]["gross_margin"] is not None


def test_ttm_missing_quarter_marks_unavailable_with_quality_flags() -> None:
    statements = [
        _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100),
        _statement(date(2025, 7, 1), date(2025, 9, 30), "10-Q", 120, 100),
        _statement(date(2025, 10, 1), date(2025, 12, 31), "10-Q", 130, 100),
        _statement(date(2026, 1, 1), date(2026, 3, 31), "10-Q", 140, 100),
    ]

    series = build_metrics_timeseries(statements, [])
    ttm = [point for point in series if point["cadence"] == "ttm"][-1]

    assert ttm["provenance"]["ttm_validation_status"] == "invalid"
    assert "ttm_missing_quarter" in ttm["quality"]["flags"]
    assert ttm["metrics"]["revenue_growth"] is None


def test_ttm_duplicate_restatement_quarter_is_flagged_ambiguous() -> None:
    q1 = _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100)
    q2_original = _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 110, 100)
    q2_restated = _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 111, 100)
    q3 = _statement(date(2025, 7, 1), date(2025, 9, 30), "10-Q", 120, 100)
    q4 = _statement(date(2025, 10, 1), date(2025, 12, 31), "10-Q", 130, 100)
    q2_restated.last_updated = q2_original.last_updated.replace(microsecond=q2_original.last_updated.microsecond + 1)
    q2_restated.id = q2_original.id + 1

    series = build_metrics_timeseries([q1, q2_original, q2_restated, q3, q4], [])
    ttm = [point for point in series if point["cadence"] == "ttm"][-1]

    assert ttm["provenance"]["ttm_validation_status"] == "invalid"
    assert "ttm_restatement_ambiguity" in ttm["quality"]["flags"]


def test_ttm_derives_q4_from_annual_minus_q1_q3_when_quality_is_sufficient() -> None:
    q1 = _statement(date(2025, 1, 1), date(2025, 3, 31), "10-Q", 100, 100)
    q2 = _statement(date(2025, 4, 1), date(2025, 6, 30), "10-Q", 110, 100)
    q3 = _statement(date(2025, 7, 1), date(2025, 9, 30), "10-Q", 120, 100)
    annual = _statement(date(2025, 1, 1), date(2025, 12, 31), "10-K", 500, 100)

    series = build_metrics_timeseries([q1, q2, q3, annual], [])
    ttm = [point for point in series if point["cadence"] == "ttm"][-1]

    assert ttm["provenance"]["ttm_validation_status"] == "valid"
    assert ttm["provenance"]["ttm_construction"] == "annual_minus_q1_q3_derived_q4"
    assert "ttm_q4_derived_from_annual" in ttm["quality"]["flags"]
    assert ttm["provenance"]["ttm_formula"]


def test_ttm_semiannual_foreign_data_not_treated_as_valid_quarters() -> None:
    statements = [
        _statement(date(2025, 1, 1), date(2025, 6, 30), "6-K", 220, 100),
        _statement(date(2025, 7, 1), date(2025, 12, 31), "6-K", 280, 100),
        _statement(date(2026, 1, 1), date(2026, 6, 30), "6-K", 230, 100),
        _statement(date(2026, 7, 1), date(2026, 12, 31), "6-K", 290, 100),
    ]

    series = build_metrics_timeseries(statements, [])
    ttm = [point for point in series if point["cadence"] == "ttm"][-1]

    assert ttm["provenance"]["ttm_validation_status"] == "invalid"
    assert "ttm_non_quarterly_form" in ttm["quality"]["flags"]
    assert ttm["metrics"]["fcf_margin"] is None
