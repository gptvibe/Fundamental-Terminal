from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from app.models import InstitutionalHolding


@dataclass(slots=True)
class TopHolder:
    fund: str
    shares: float


@dataclass(slots=True)
class OwnershipAnalytics:
    top_holders: list[TopHolder]
    institutional_ownership: float
    ownership_concentration: float
    quarterly_inflow: float
    quarterly_outflow: float
    new_positions: int
    sold_positions: int
    reporting_date: date | None


def build_ownership_analytics(
    holdings: Sequence[InstitutionalHolding],
    *,
    top_n: int = 10,
) -> OwnershipAnalytics:
    if not holdings:
        return OwnershipAnalytics(
            top_holders=[],
            institutional_ownership=0.0,
            ownership_concentration=0.0,
            quarterly_inflow=0.0,
            quarterly_outflow=0.0,
            new_positions=0,
            sold_positions=0,
            reporting_date=None,
        )

    reporting_dates = sorted({holding.reporting_date for holding in holdings if holding.reporting_date is not None}, reverse=True)
    latest_date = reporting_dates[0] if reporting_dates else None
    previous_date = reporting_dates[1] if len(reporting_dates) > 1 else None

    latest_rows = [holding for holding in holdings if holding.reporting_date == latest_date]
    previous_rows = [holding for holding in holdings if previous_date is not None and holding.reporting_date == previous_date]

    latest_by_fund: dict[int, InstitutionalHolding] = {}
    for row in latest_rows:
        latest_by_fund[row.fund_id] = row

    previous_by_fund: dict[int, InstitutionalHolding] = {}
    for row in previous_rows:
        previous_by_fund[row.fund_id] = row

    ranked_rows = sorted(latest_rows, key=lambda row: _shares(row), reverse=True)
    top_holders = [
        TopHolder(
            fund=(row.fund.fund_name if row.fund is not None else f"Fund {row.fund_id}"),
            shares=_shares(row),
        )
        for row in ranked_rows[:top_n]
        if _shares(row) > 0
    ]

    total_shares_latest = sum(_shares(row) for row in latest_rows)
    top5_shares = sum(holder.shares for holder in top_holders[:5])
    concentration = _ratio(top5_shares, total_shares_latest)

    inflow = 0.0
    outflow = 0.0
    for row in latest_rows:
        change = row.change_in_shares
        if change is None:
            prev = previous_by_fund.get(row.fund_id)
            if prev is not None:
                change = _shares(row) - _shares(prev)
        if change is None:
            continue
        if change > 0:
            inflow += float(change)
        elif change < 0:
            outflow += abs(float(change))

    new_positions = 0
    for row in latest_rows:
        latest_shares = _shares(row)
        prev_shares = _shares(previous_by_fund[row.fund_id]) if row.fund_id in previous_by_fund else 0.0
        if latest_shares > 0 and prev_shares <= 0:
            new_positions += 1

    sold_positions = 0
    for fund_id, prev_row in previous_by_fund.items():
        prev_shares = _shares(prev_row)
        latest_row = latest_by_fund.get(fund_id)
        latest_shares = _shares(latest_row) if latest_row is not None else 0.0
        if prev_shares > 0 and latest_shares <= 0:
            sold_positions += 1

    return OwnershipAnalytics(
        top_holders=top_holders,
        institutional_ownership=concentration,
        ownership_concentration=concentration,
        quarterly_inflow=round(inflow, 2),
        quarterly_outflow=round(outflow, 2),
        new_positions=new_positions,
        sold_positions=sold_positions,
        reporting_date=latest_date,
    )


def _shares(row: InstitutionalHolding | None) -> float:
    if row is None or row.shares_held is None:
        return 0.0
    return max(float(row.shares_held), 0.0)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
