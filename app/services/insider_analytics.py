from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from app.models import InsiderTrade


@dataclass(slots=True)
class LargestTrade:
    insider: str
    type: str
    value: float
    date: date | None


@dataclass(slots=True)
class InsiderAnalytics:
    buy_value_30d: float
    sell_value_30d: float
    buy_sell_ratio: float
    largest_trade: LargestTrade | None
    insider_activity_trend: str


def build_insider_analytics(
    trades: Sequence[InsiderTrade],
    *,
    as_of: date | None = None,
) -> InsiderAnalytics:
    today = as_of or datetime.now(timezone.utc).date()
    cutoff_30 = today - timedelta(days=30)
    cutoff_60 = today - timedelta(days=60)

    recent_trades = [trade for trade in trades if (_trade_date(trade) or date.min) >= cutoff_30]
    previous_trades = [
        trade
        for trade in trades
        if (trade_date := _trade_date(trade)) is not None and cutoff_60 <= trade_date < cutoff_30
    ]

    buy_value_30d = round(sum(_trade_value(trade) for trade in recent_trades if _trade_side(trade) == "BUY"), 2)
    sell_value_30d = round(sum(_trade_value(trade) for trade in recent_trades if _trade_side(trade) == "SELL"), 2)

    if sell_value_30d > 0:
        ratio = round(buy_value_30d / sell_value_30d, 2)
    elif buy_value_30d > 0:
        ratio = round(buy_value_30d, 2)
    else:
        ratio = 0.0

    largest = _largest_trade(recent_trades)
    trend = _activity_trend(recent_trades, previous_trades)

    return InsiderAnalytics(
        buy_value_30d=buy_value_30d,
        sell_value_30d=sell_value_30d,
        buy_sell_ratio=ratio,
        largest_trade=largest,
        insider_activity_trend=trend,
    )


def _largest_trade(trades: Sequence[InsiderTrade]) -> LargestTrade | None:
    signal_trades = [trade for trade in trades if _trade_side(trade) in {"BUY", "SELL"}]
    if not signal_trades:
        return None

    trade = max(signal_trades, key=_trade_value)
    return LargestTrade(
        insider=trade.insider_name,
        type=_trade_side(trade),
        value=round(_trade_value(trade), 2),
        date=_trade_date(trade),
    )


def _activity_trend(recent_trades: Sequence[InsiderTrade], previous_trades: Sequence[InsiderTrade]) -> str:
    recent_buy = sum(_trade_value(trade) for trade in recent_trades if _trade_side(trade) == "BUY")
    recent_sell = sum(_trade_value(trade) for trade in recent_trades if _trade_side(trade) == "SELL")
    previous_buy = sum(_trade_value(trade) for trade in previous_trades if _trade_side(trade) == "BUY")
    previous_sell = sum(_trade_value(trade) for trade in previous_trades if _trade_side(trade) == "SELL")

    recent_net = recent_buy - recent_sell
    previous_net = previous_buy - previous_sell

    if abs(recent_net) < 1 and abs(previous_net) < 1:
        return "stable"
    if recent_net > previous_net and recent_net > 0:
        return "increasing_buying"
    if recent_net < previous_net and recent_net < 0:
        return "increasing_selling"
    return "mixed"


def _trade_date(trade: InsiderTrade) -> date | None:
    return trade.transaction_date or trade.filing_date


def _trade_value(trade: InsiderTrade) -> float:
    if trade.value is not None:
        return abs(float(trade.value))
    if trade.shares is not None and trade.price is not None:
        return abs(float(trade.shares) * float(trade.price))
    return 0.0


def _trade_side(trade: InsiderTrade) -> str:
    code = (trade.transaction_code or "").upper().strip()
    if code == "P":
        return "BUY"
    if code == "S":
        return "SELL"

    normalized = (trade.action or "").strip().lower()
    if normalized == "buy":
        return "BUY"
    if normalized == "sell":
        return "SELL"
    return "OTHER"
