from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.insider_analytics import build_insider_analytics
from app.services.ownership_analytics import build_ownership_analytics


def _trade(
    *,
    insider_name: str,
    transaction_date: date | None,
    filing_date: date | None,
    value: float | None = None,
    shares: float | None = None,
    price: float | None = None,
    transaction_code: str | None = None,
    action: str | None = None,
):
    return SimpleNamespace(
        insider_name=insider_name,
        transaction_date=transaction_date,
        filing_date=filing_date,
        value=value,
        shares=shares,
        price=price,
        transaction_code=transaction_code,
        action=action,
    )


def _holding(*, fund_id: int, fund_name: str, reporting_date: date, shares_held: float, change_in_shares: float | None):
    return SimpleNamespace(
        fund_id=fund_id,
        fund=SimpleNamespace(fund_name=fund_name),
        reporting_date=reporting_date,
        shares_held=shares_held,
        change_in_shares=change_in_shares,
    )


def test_build_insider_analytics_calculates_ratio_largest_trade_and_trend():
    trades = [
        _trade(
            insider_name="Alice",
            transaction_date=date(2026, 3, 10),
            filing_date=None,
            value=100,
            transaction_code="P",
        ),
        _trade(
            insider_name="Bob",
            transaction_date=date(2026, 3, 1),
            filing_date=None,
            shares=10,
            price=50,
            transaction_code="S",
        ),
        _trade(
            insider_name="Carol",
            transaction_date=date(2026, 2, 20),
            filing_date=None,
            value=200,
            action="sell",
        ),
        _trade(
            insider_name="Dave",
            transaction_date=None,
            filing_date=date(2026, 1, 20),
            value=100,
            transaction_code="S",
        ),
    ]

    analytics = build_insider_analytics(trades, as_of=date(2026, 3, 15))

    assert analytics.buy_value_30d == 100
    assert analytics.sell_value_30d == 700
    assert analytics.buy_sell_ratio == 0.14
    assert analytics.largest_trade is not None
    assert analytics.largest_trade.insider == "Bob"
    assert analytics.largest_trade.type == "SELL"
    assert analytics.largest_trade.value == 500
    assert analytics.insider_activity_trend == "increasing_selling"


def test_build_ownership_analytics_tracks_flows_concentration_and_position_changes():
    latest = date(2025, 12, 31)
    previous = date(2025, 9, 30)
    holdings = [
        _holding(fund_id=1, fund_name="Fund A", reporting_date=latest, shares_held=100, change_in_shares=10),
        _holding(fund_id=2, fund_name="Fund B", reporting_date=latest, shares_held=50, change_in_shares=-20),
        _holding(fund_id=3, fund_name="Fund C", reporting_date=latest, shares_held=25, change_in_shares=None),
        _holding(fund_id=1, fund_name="Fund A", reporting_date=previous, shares_held=90, change_in_shares=None),
        _holding(fund_id=2, fund_name="Fund B", reporting_date=previous, shares_held=70, change_in_shares=None),
        _holding(fund_id=4, fund_name="Fund D", reporting_date=previous, shares_held=40, change_in_shares=None),
    ]

    analytics = build_ownership_analytics(holdings)

    assert analytics.reporting_date == latest
    assert analytics.quarterly_inflow == 10
    assert analytics.quarterly_outflow == 20
    assert analytics.new_positions == 1
    assert analytics.sold_positions == 1
    assert analytics.ownership_concentration == 1.0
    assert analytics.institutional_ownership == 1.0
    assert [holder.fund for holder in analytics.top_holders[:3]] == ["Fund A", "Fund B", "Fund C"]
