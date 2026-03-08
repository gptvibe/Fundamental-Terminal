from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    average,
    book_equity,
    growth_rate,
    json_number,
    latest_statement,
    previous_comparable_statement,
    safe_divide,
    statement_value,
)

MODEL_NAME = "ratios"
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

    ratios = {
        "gross_margin": safe_divide(statement_value(current, "gross_profit"), statement_value(current, "revenue")),
        "operating_margin": safe_divide(statement_value(current, "operating_income"), statement_value(current, "revenue")),
        "net_margin": safe_divide(statement_value(current, "net_income"), statement_value(current, "revenue")),
        "operating_cash_flow_margin": safe_divide(statement_value(current, "operating_cash_flow"), statement_value(current, "revenue")),
        "free_cash_flow_margin": safe_divide(statement_value(current, "free_cash_flow"), statement_value(current, "revenue")),
        "return_on_assets": safe_divide(statement_value(current, "net_income"), average_assets),
        "return_on_equity": safe_divide(statement_value(current, "net_income"), average_equity),
        "asset_turnover": safe_divide(statement_value(current, "revenue"), average_assets),
        "liabilities_to_assets": safe_divide(statement_value(current, "total_liabilities"), statement_value(current, "total_assets")),
        "equity_ratio": safe_divide(current_equity, statement_value(current, "total_assets")),
        "revenue_growth": growth_rate(statement_value(current, "revenue"), statement_value(previous, "revenue") if previous else None),
        "net_income_growth": growth_rate(statement_value(current, "net_income"), statement_value(previous, "net_income") if previous else None),
        "free_cash_flow_growth": growth_rate(statement_value(current, "free_cash_flow"), statement_value(previous, "free_cash_flow") if previous else None),
    }

    return {
        "status": "ok",
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "previous_period_end": previous.period_end.isoformat() if previous else None,
        "values": {key: json_number(value) for key, value in ratios.items()},
    }
