from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

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
