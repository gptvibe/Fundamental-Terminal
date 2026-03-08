from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Sequence

from app.models import InsiderTrade

SIGNAL_BUY_CODES = {"P"}
SIGNAL_SELL_CODES = {"S"}


@dataclass(slots=True)
class InsiderActivityMetrics:
    total_buy_value: float
    total_sell_value: float
    net_value: float
    unique_insiders_buying: int
    unique_insiders_selling: int


@dataclass(slots=True)
class InsiderActivitySummary:
    sentiment: str
    summary_lines: list[str]
    metrics: InsiderActivityMetrics


def build_insider_activity_summary(
    trades: Sequence[InsiderTrade],
    *,
    as_of: date | None = None,
) -> InsiderActivitySummary:
    as_of_date = as_of or datetime.now(timezone.utc).date()
    twelve_month_cutoff = _subtract_months(as_of_date, 12)
    eighteen_month_cutoff = _subtract_months(as_of_date, 18)

    dated_trades = [trade for trade in trades if trade.transaction_date is not None]
    recent_trades = [trade for trade in dated_trades if trade.transaction_date >= twelve_month_cutoff]

    recent_buys = [trade for trade in recent_trades if _normalize_action(trade.action) == "buy"]
    recent_sells = [trade for trade in recent_trades if _normalize_action(trade.action) == "sell"]
    signal_buys = [trade for trade in recent_buys if _is_signal_buy(trade)]
    signal_sells = [trade for trade in recent_sells if _is_signal_sell(trade)]
    non_signal_buys = [trade for trade in recent_buys if trade not in signal_buys]

    raw_buy_value = round(sum(_transaction_value(trade) for trade in recent_buys), 2)
    signal_buy_value = round(sum(_transaction_value(trade) for trade in signal_buys), 2)
    signal_sell_value = round(sum(_transaction_value(trade) for trade in signal_sells), 2)
    signal_net_value = round(signal_buy_value - signal_sell_value, 2)
    unique_signal_buyers = len({_normalize_name(trade.insider_name) for trade in signal_buys})
    unique_signal_sellers = len({_normalize_name(trade.insider_name) for trade in signal_sells})

    ceo_signal_buys = [trade for trade in signal_buys if _is_ceo(trade.role)]
    ceo_signal_sells = [trade for trade in signal_sells if _is_ceo(trade.role)]
    cfo_signal_buys = [trade for trade in signal_buys if _is_cfo(trade.role)]
    cfo_signal_sells = [trade for trade in signal_sells if _is_cfo(trade.role)]
    director_signal_buys = [trade for trade in signal_buys if _is_director(trade.role)]
    director_signal_sells = [trade for trade in signal_sells if _is_director(trade.role)]

    ceo_buy_value = round(sum(_transaction_value(trade) for trade in ceo_signal_buys), 2)
    ceo_sell_value = round(sum(_transaction_value(trade) for trade in ceo_signal_sells), 2)
    cfo_buy_value = round(sum(_transaction_value(trade) for trade in cfo_signal_buys), 2)
    cfo_sell_value = round(sum(_transaction_value(trade) for trade in cfo_signal_sells), 2)
    director_net_shares = round(
        sum(_share_count(trade) for trade in director_signal_buys) - sum(_share_count(trade) for trade in director_signal_sells),
        2,
    )

    latest_signal_buy_date = max((trade.transaction_date for trade in signal_buys), default=None)
    cluster_buying, cluster_buying_count = _detect_cluster_buying(signal_buys)
    long_buying_drought = latest_signal_buy_date is None or latest_signal_buy_date < eighteen_month_cutoff
    no_buy_for_twelve_months = latest_signal_buy_date is None or latest_signal_buy_date < twelve_month_cutoff
    heavy_selling = signal_sell_value > (signal_buy_value * 3) if signal_buy_value > 0 else signal_sell_value > 0
    routine_selling = _detect_routine_selling(signal_sells)
    balanced_flow = abs(signal_buy_value - signal_sell_value) <= max(100_000.0, max(signal_buy_value, signal_sell_value, 1.0) * 0.15)

    bullish = signal_net_value > 0 or ceo_buy_value > 0 or cluster_buying
    bearish = (signal_sell_value > signal_buy_value and no_buy_for_twelve_months) or (
        heavy_selling and ceo_buy_value == 0 and not cluster_buying and signal_buy_value < (signal_sell_value * 0.25)
    )

    if bullish:
        sentiment = "bullish"
    elif bearish:
        sentiment = "bearish"
    elif balanced_flow or routine_selling or (signal_buy_value == 0 and signal_sell_value == 0):
        sentiment = "neutral"
    else:
        sentiment = "neutral" if signal_net_value >= 0 else "bearish"

    largest_signal_trade = max([*signal_buys, *signal_sells], key=_transaction_value, default=None)
    largest_signal_trade_value = _transaction_value(largest_signal_trade) if largest_signal_trade is not None else 0.0

    summary_lines: list[str] = []

    if ceo_buy_value > 0:
        summary_lines.append(f"CEO bought {_format_money(ceo_buy_value)} in open-market shares over the last 12 months.")
    elif ceo_sell_value > 0:
        summary_lines.append(f"CEO sold {_format_money(ceo_sell_value)} in open-market shares over the last 12 months.")
    elif cfo_buy_value > 0:
        summary_lines.append(f"CFO bought {_format_money(cfo_buy_value)} in open-market shares over the last 12 months.")
    elif cfo_sell_value > 0:
        summary_lines.append(f"CFO sold {_format_money(cfo_sell_value)} in open-market shares over the last 12 months.")

    if director_net_shares > 0:
        summary_lines.append(f"Directors net bought {_format_shares(director_net_shares)} open-market shares over the last 12 months.")
    elif director_net_shares < 0:
        summary_lines.append(f"Directors net sold {_format_shares(abs(director_net_shares))} open-market shares over the last 12 months.")

    if cluster_buying:
        summary_lines.append(f"Cluster buying detected with {cluster_buying_count} insiders buying within a 30-day window.")

    if signal_net_value > 0:
        summary_lines.append(f"Net open-market insider buying totals {_format_money(signal_net_value)} over the last year.")
    elif signal_net_value < 0:
        summary_lines.append(f"Net open-market insider selling totals {_format_money(abs(signal_net_value))} over the last year.")
    else:
        summary_lines.append("Open-market insider buying and selling were broadly balanced over the last year.")

    if long_buying_drought:
        summary_lines.append("No open-market insider buy has been recorded in the last 18 months.")
    elif latest_signal_buy_date is not None and no_buy_for_twelve_months:
        summary_lines.append(f"The last open-market insider buy was on {latest_signal_buy_date:%b %d, %Y}.")

    if routine_selling:
        summary_lines.append("Most open-market sales appear to be routine sub-$100k 10b5-1 plan transactions.")
    elif heavy_selling:
        summary_lines.append("Open-market selling outweighed buying by more than 3x.")

    if raw_buy_value > signal_buy_value * 3 and non_signal_buys:
        summary_lines.append("Most recorded buy-side filings were grants or option exercises rather than open-market purchases.")

    if len(summary_lines) < 3 and largest_signal_trade is not None and largest_signal_trade_value > 0:
        trade_role = (largest_signal_trade.role or "insider").strip()
        summary_lines.append(
            f"Largest open-market trade was a {trade_role} {_normalize_action(largest_signal_trade.action)} worth {_format_money(largest_signal_trade_value)}."
        )

    if len(summary_lines) < 3:
        summary_lines.append(
            f"{unique_signal_buyers} insiders bought and {unique_signal_sellers} insiders sold shares in the open market over the last 12 months."
        )

    if len(summary_lines) < 3 and latest_signal_buy_date is not None:
        summary_lines.append(f"Last open-market insider buy date: {latest_signal_buy_date:%b %d, %Y}.")

    if not summary_lines:
        summary_lines = [
            "No cached insider transactions were recorded for the last 12 months.",
            "No open-market insider buying or selling patterns could be established from the current cache.",
            "Refresh the ticker to pull newer Form 4 filings if available.",
        ]

    summary_lines = _dedupe_lines(summary_lines)[:4]

    return InsiderActivitySummary(
        sentiment=sentiment,
        summary_lines=summary_lines,
        metrics=InsiderActivityMetrics(
            total_buy_value=signal_buy_value,
            total_sell_value=signal_sell_value,
            net_value=signal_net_value,
            unique_insiders_buying=unique_signal_buyers,
            unique_insiders_selling=unique_signal_sellers,
        ),
    )


def _detect_cluster_buying(trades: Sequence[InsiderTrade]) -> tuple[bool, int]:
    if len(trades) < 3:
        return False, 0

    sorted_trades = sorted((trade for trade in trades if trade.transaction_date is not None), key=lambda trade: trade.transaction_date)
    largest_cluster = 0
    for index, trade in enumerate(sorted_trades):
        window_end = trade.transaction_date.toordinal() + 30
        window_names = {_normalize_name(trade.insider_name)}
        for candidate in sorted_trades[index + 1 :]:
            if candidate.transaction_date is None:
                continue
            if candidate.transaction_date.toordinal() > window_end:
                break
            window_names.add(_normalize_name(candidate.insider_name))
        largest_cluster = max(largest_cluster, len(window_names))
        if largest_cluster >= 3:
            return True, largest_cluster

    return False, largest_cluster


def _detect_routine_selling(trades: Sequence[InsiderTrade]) -> bool:
    if not trades:
        return False

    routine_count = 0
    for trade in trades:
        if _transaction_value(trade) < 100_000 and trade.is_10b5_1:
            routine_count += 1

    return routine_count / len(trades) >= 0.6


def _normalize_action(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"buy", "sell"}:
        return normalized
    return "other"


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def _is_ceo(role: str | None) -> bool:
    normalized = _normalize_role(role)
    return "CEO" in normalized or "CHIEF EXECUTIVE" in normalized


def _is_cfo(role: str | None) -> bool:
    normalized = _normalize_role(role)
    return "CFO" in normalized or "CHIEF FINANCIAL" in normalized


def _is_director(role: str | None) -> bool:
    normalized = _normalize_role(role)
    return "DIRECTOR" in normalized


def _normalize_role(role: str | None) -> str:
    return (role or "").upper()


def _is_signal_buy(trade: InsiderTrade) -> bool:
    code = (trade.transaction_code or "").upper()
    if code:
        return code in SIGNAL_BUY_CODES
    return _normalize_action(trade.action) == "buy"


def _is_signal_sell(trade: InsiderTrade) -> bool:
    code = (trade.transaction_code or "").upper()
    if code:
        return code in SIGNAL_SELL_CODES
    return _normalize_action(trade.action) == "sell"


def _transaction_value(trade: InsiderTrade | None) -> float:
    if trade is None:
        return 0.0
    if trade.value is not None:
        return abs(float(trade.value))
    if trade.shares is not None and trade.price is not None:
        return abs(float(trade.shares) * float(trade.price))
    return 0.0


def _share_count(trade: InsiderTrade | None) -> float:
    if trade is None or trade.shares is None:
        return 0.0
    return float(trade.shares)


def _subtract_months(value: date, months: int) -> date:
    year = value.year
    month = value.month - months
    while month <= 0:
        year -= 1
        month += 12
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _format_money(value: float) -> str:
    absolute_value = abs(value)
    if absolute_value >= 1_000_000_000:
        return f"${absolute_value / 1_000_000_000:.2f}B"
    if absolute_value >= 1_000_000:
        return f"${absolute_value / 1_000_000:.2f}M"
    if absolute_value >= 1_000:
        return f"${absolute_value / 1_000:.0f}K"
    return f"${absolute_value:,.0f}"


def _format_shares(value: float) -> str:
    absolute_value = abs(value)
    if absolute_value >= 1_000_000:
        return f"{absolute_value / 1_000_000:.2f}M"
    if absolute_value >= 1_000:
        return f"{absolute_value / 1_000:.1f}K"
    return f"{absolute_value:,.0f}"


def _dedupe_lines(lines: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        normalized = line.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped
