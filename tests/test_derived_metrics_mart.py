from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services.derived_metrics_mart import METRIC_REGISTRY, build_derived_metric_points


def _statement(
    statement_id: int,
    period_start: date,
    period_end: date,
    filing_type: str,
    data: dict[str, float | int | list[dict[str, float | str | None]] | None],
):
    return SimpleNamespace(
        id=statement_id,
        period_start=period_start,
        period_end=period_end,
        filing_type=filing_type,
        statement_type="canonical_xbrl",
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
