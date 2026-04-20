from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect
from sqlalchemy.dialects.postgresql import insert

from app.models import DerivedMetricPoint

from app.services.derived_metrics import build_metrics_timeseries
from app.services.derived_metrics_mart import (
    DERIVED_METRIC_UPSERT_BATCH_SIZE,
    METRIC_REGISTRY,
    _chunked_payloads,
    build_derived_metric_points,
)


def _statement(
    statement_id: int,
    period_start: date,
    period_end: date,
    filing_type: str,
    data: dict[str, float | int | list[dict[str, float | str | None]] | None],
    *,
    statement_type: str = "canonical_xbrl",
):
    return SimpleNamespace(
        id=statement_id,
        period_start=period_start,
        period_end=period_end,
        filing_type=filing_type,
        statement_type=statement_type,
        source="https://data.sec.gov/example",
        last_updated=datetime.now(timezone.utc),
        data=data,
    )


def _price(trade_date: date, close: float):
    return SimpleNamespace(trade_date=trade_date, close=close, source="yahoo_finance")


def _build_quarter(revenue: float, shares: float, *, with_segments: bool = True) -> dict[str, float | int | list[dict[str, float | str | None]]]:
    payload: dict[str, float | int | list[dict[str, float | str | None]]] = {
        "revenue": revenue,
        "gross_profit": revenue * 0.42,
        "operating_income": revenue * 0.22,
        "net_income": revenue * 0.16,
        "free_cash_flow": revenue * 0.11,
        "operating_cash_flow": revenue * 0.18,
        "eps": 2.0,
        "total_assets": revenue * 2.1,
        "stockholders_equity": revenue * 1.0,
        "current_assets": revenue * 0.8,
        "current_liabilities": revenue * 0.45,
        "current_debt": revenue * 0.06,
        "long_term_debt": revenue * 0.28,
        "interest_expense": revenue * 0.01,
        "stock_based_compensation": revenue * 0.03,
        "dividends": -(revenue * 0.01),
        "share_buybacks": -(revenue * 0.02),
        "accounts_receivable": revenue * 0.2,
        "inventory": revenue * 0.1,
        "accounts_payable": revenue * 0.12,
        "weighted_average_diluted_shares": shares,
    }
    if with_segments:
        payload["segment_breakdown"] = [
            {"segment_name": "Products", "kind": "business", "revenue": revenue * 0.7},
            {"segment_name": "Services", "kind": "business", "revenue": revenue * 0.3},
            {"segment_name": "US", "kind": "geographic", "revenue": revenue * 0.55},
            {"segment_name": "Intl", "kind": "geographic", "revenue": revenue * 0.45},
        ]
    return payload


def test_registry_contains_required_metrics():
    keys = {metric.key for metric in METRIC_REGISTRY}
    expected = {
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "free_cash_flow",
        "revenue_growth",
        "eps_growth",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "fcf_margin",
        "roic_proxy",
        "roe",
        "roa",
        "debt_to_equity",
        "debt_to_assets",
        "interest_coverage_proxy",
        "current_ratio",
        "cash_ratio",
        "dilution_trend",
        "shares_cagr",
        "sbc_to_revenue",
        "dividend_yield_proxy",
        "buyback_yield_proxy",
        "shareholder_yield",
        "dso_days",
        "dio_days",
        "dpo_days",
        "cash_conversion_cycle_days",
        "accrual_ratio",
        "cash_conversion_ratio",
        "segment_concentration",
        "geography_concentration",
        "filing_lag_days",
        "stale_period_flag",
        "restatement_flag",
    }
    assert expected.issubset(keys)


def test_build_derived_metric_points_outputs_provenance_and_quality_flags():
    statements = [
        _statement(1, date(2025, 1, 1), date(2025, 3, 31), "10-Q", _build_quarter(100.0, 100.0)),
        _statement(2, date(2025, 4, 1), date(2025, 6, 30), "10-Q", _build_quarter(110.0, 101.0)),
        _statement(3, date(2025, 7, 1), date(2025, 9, 30), "10-Q", _build_quarter(120.0, 102.0)),
        _statement(4, date(2025, 10, 1), date(2025, 12, 31), "10-Q", _build_quarter(130.0, 103.0)),
        _statement(5, date(2025, 1, 1), date(2025, 12, 31), "10-K", _build_quarter(460.0, 103.0)),
    ]
    prices = [_price(date(2025, 12, 31), 50.0)]

    points = build_derived_metric_points(statements, prices)

    assert points
    point = next(item for item in points if item["period_type"] == "ttm" and item["metric_key"] == "gross_margin")
    assert point["metric_value"] is not None
    assert point["provenance"]["formula_version"] == "sec_metrics_mart_v1"
    assert "quality_flags" in point


def test_build_derived_metric_points_annualizes_quarterly_yields_and_working_capital_days():
    statements = [
        _statement(1, date(2025, 1, 1), date(2025, 3, 31), "10-Q", _build_quarter(100.0, 100.0)),
        _statement(2, date(2025, 4, 1), date(2025, 6, 30), "10-Q", _build_quarter(100.0, 100.0)),
        _statement(3, date(2025, 7, 1), date(2025, 9, 30), "10-Q", _build_quarter(100.0, 100.0)),
        _statement(4, date(2025, 10, 1), date(2025, 12, 31), "10-Q", _build_quarter(100.0, 100.0)),
    ]
    prices = [_price(date(2025, 12, 31), 50.0)]

    main_series = build_metrics_timeseries(statements, prices)
    main_quarterly = [point for point in main_series if point["cadence"] == "quarterly"][-1]
    main_ttm = [point for point in main_series if point["cadence"] == "ttm"][-1]

    mart_points = build_derived_metric_points(statements, prices)

    def mart_value(period_type: str, metric_key: str) -> float:
        return next(
            item["metric_value"]
            for item in mart_points
            if item["period_type"] == period_type
            and item["metric_key"] == metric_key
            and item["period_end"] == date(2025, 12, 31)
        )

    expected_buyback_yield = main_quarterly["metrics"]["buyback_yield"]
    expected_dividend_yield = main_quarterly["metrics"]["dividend_yield"]
    expected_dso_days = (100.0 * 0.2) / (100.0 * 4.0) * 365.0
    expected_dio_days = (100.0 * 0.1) / ((100.0 - (100.0 * 0.42)) * 4.0) * 365.0
    expected_dpo_days = (100.0 * 0.12) / ((100.0 - (100.0 * 0.42)) * 4.0) * 365.0
    expected_ccc_days = expected_dso_days + expected_dio_days - expected_dpo_days

    assert mart_value("quarterly", "buyback_yield_proxy") == pytest.approx(expected_buyback_yield, rel=1e-9)
    assert mart_value("ttm", "buyback_yield_proxy") == pytest.approx(expected_buyback_yield, rel=1e-9)
    assert mart_value("quarterly", "dividend_yield_proxy") == pytest.approx(expected_dividend_yield, rel=1e-9)
    assert mart_value("ttm", "dividend_yield_proxy") == pytest.approx(expected_dividend_yield, rel=1e-9)
    assert mart_value("quarterly", "shareholder_yield") == pytest.approx(expected_buyback_yield + expected_dividend_yield, rel=1e-9)
    assert mart_value("ttm", "shareholder_yield") == pytest.approx(expected_buyback_yield + expected_dividend_yield, rel=1e-9)
    assert mart_value("quarterly", "dso_days") == pytest.approx(expected_dso_days, rel=1e-9)
    assert mart_value("ttm", "dso_days") == pytest.approx(expected_dso_days, rel=1e-9)
    assert mart_value("quarterly", "dio_days") == pytest.approx(expected_dio_days, rel=1e-9)
    assert mart_value("ttm", "dio_days") == pytest.approx(expected_dio_days, rel=1e-9)
    assert mart_value("quarterly", "dpo_days") == pytest.approx(expected_dpo_days, rel=1e-9)
    assert mart_value("ttm", "dpo_days") == pytest.approx(expected_dpo_days, rel=1e-9)
    assert mart_value("quarterly", "cash_conversion_cycle_days") == pytest.approx(expected_ccc_days, rel=1e-9)
    assert mart_value("ttm", "cash_conversion_cycle_days") == pytest.approx(expected_ccc_days, rel=1e-9)
    assert main_ttm["metrics"]["buyback_yield"] == pytest.approx(expected_buyback_yield, rel=1e-9)
    assert main_ttm["metrics"]["dividend_yield"] == pytest.approx(expected_dividend_yield, rel=1e-9)


def test_build_derived_metric_points_handles_missing_and_partial_segment_data():
    statements = [
        _statement(
            1,
            date(2025, 1, 1),
            date(2025, 3, 31),
            "10-Q",
            {
                "revenue": 100.0,
                "gross_profit": 40.0,
                "operating_income": 20.0,
                "net_income": 12.0,
                "free_cash_flow": 8.0,
                "weighted_average_diluted_shares": 100.0,
                "segment_breakdown": [
                    {"segment_name": "Products", "kind": "business", "revenue": 70.0},
                    {"segment_name": "Services", "kind": "business", "revenue": None},
                ],
            },
        ),
        _statement(2, date(2025, 4, 1), date(2025, 6, 30), "10-Q", _build_quarter(110.0, 101.0, with_segments=False)),
    ]
    prices = []

    points = build_derived_metric_points(statements, prices)
    segment_rows = [item for item in points if item["metric_key"] in {"segment_concentration", "geography_concentration"}]
    assert segment_rows

    geo = next(item for item in segment_rows if item["metric_key"] == "geography_concentration")
    assert geo["metric_value"] is None
    assert "segment_data_unavailable" in geo["quality_flags"]


def test_build_derived_metric_points_includes_bank_metrics():
    statements = [
        _statement(
            1,
            date(2025, 1, 1),
            date(2025, 3, 31),
            "CALL",
            {
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
            statement_type="canonical_bank_regulatory",
        ),
        _statement(
            2,
            date(2025, 4, 1),
            date(2025, 6, 30),
            "CALL",
            {
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
            statement_type="canonical_bank_regulatory",
        ),
        _statement(
            3,
            date(2025, 7, 1),
            date(2025, 9, 30),
            "CALL",
            {
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
            statement_type="canonical_bank_regulatory",
        ),
        _statement(
            4,
            date(2025, 10, 1),
            date(2025, 12, 31),
            "CALL",
            {
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
            statement_type="canonical_bank_regulatory",
        ),
    ]

    points = build_derived_metric_points(statements, [])

    metric_keys = {point["metric_key"] for point in points}
    assert {"net_interest_margin", "provision_burden", "cet1_ratio", "roatce"}.issubset(metric_keys)


def test_derived_metric_upsert_batches_stay_under_postgres_parameter_limit():
    payloads = [
        {
            "company_id": index,
            "period_start": date(2025, 1, 1),
            "period_end": date(2025, 3, 31),
            "period_type": "quarterly",
            "filing_type": "10-Q",
            "metric_key": f"metric_{index}",
            "metric_value": float(index),
            "metric_date": date(2025, 3, 31),
            "is_proxy": False,
            "provenance": {"formula_version": "sec_metrics_mart_v1"},
            "source_statement_ids": [index],
            "quality_flags": [],
            "last_updated": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "last_checked": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        for index in range(DERIVED_METRIC_UPSERT_BATCH_SIZE + 5)
    ]

    batches = _chunked_payloads(payloads, DERIVED_METRIC_UPSERT_BATCH_SIZE)

    assert [len(batch) for batch in batches] == [DERIVED_METRIC_UPSERT_BATCH_SIZE, 5]

    compiled = insert(DerivedMetricPoint).values(batches[0]).compile(dialect=postgresql_dialect())
    assert len(compiled.params) == DERIVED_METRIC_UPSERT_BATCH_SIZE * 14
    assert len(compiled.params) <= 65535
