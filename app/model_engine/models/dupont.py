from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    average,
    book_equity,
    json_number,
    latest_statement,
    previous_comparable_statement,
    safe_divide,
    statement_value,
)

MODEL_NAME = "dupont"
MODEL_VERSION = "1.0.0"


def compute(dataset: CompanyDataset) -> dict[str, object]:
    current = latest_statement(dataset)
    if current is None:
        return {"status": "insufficient_data", "reason": "No financial statements available"}

    previous = previous_comparable_statement(dataset, current)
    current_equity = book_equity(current)
    previous_equity = book_equity(previous) if previous else None
    average_assets = average(statement_value(current, "total_assets"), statement_value(previous, "total_assets") if previous else None)
    average_equity = average(current_equity, previous_equity)

    net_profit_margin = safe_divide(statement_value(current, "net_income"), statement_value(current, "revenue"))
    asset_turnover = safe_divide(statement_value(current, "revenue"), average_assets)
    equity_multiplier = safe_divide(average_assets, average_equity)

    return {
        "status": "ok" if all(value is not None for value in (net_profit_margin, asset_turnover, equity_multiplier)) else "partial",
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "net_profit_margin": json_number(net_profit_margin),
        "asset_turnover": json_number(asset_turnover),
        "equity_multiplier": json_number(equity_multiplier),
        "return_on_equity": json_number(
            None if None in (net_profit_margin, asset_turnover, equity_multiplier) else net_profit_margin * asset_turnover * equity_multiplier
        ),
        "average_assets": json_number(average_assets),
        "average_equity": json_number(average_equity),
    }
