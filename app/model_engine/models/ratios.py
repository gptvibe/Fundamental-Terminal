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
    status_explanation,
)

MODEL_NAME = "ratios"
MODEL_VERSION = "1.1.0"


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
        "interest_coverage": safe_divide(statement_value(current, "operating_income"), abs(float(statement_value(current, "interest_expense"))) if statement_value(current, "interest_expense") not in (None, 0) else None),
        "cash_conversion": safe_divide(statement_value(current, "operating_cash_flow"), statement_value(current, "net_income")),
        "capex_intensity": safe_divide(statement_value(current, "capex"), statement_value(current, "revenue")),
        "sbc_to_revenue": safe_divide(statement_value(current, "stock_based_compensation"), statement_value(current, "revenue")),
        "net_debt_to_fcf": safe_divide(
            (
                float(statement_value(current, "current_debt") or 0)
                + float(statement_value(current, "long_term_debt") or 0)
                - float(statement_value(current, "cash_and_short_term_investments") or 0)
            )
            if any(
                statement_value(current, key) is not None
                for key in ("current_debt", "long_term_debt", "cash_and_short_term_investments")
            )
            else None,
            statement_value(current, "free_cash_flow"),
        ),
        "payout_ratio": safe_divide(abs(float(statement_value(current, "dividends"))) if statement_value(current, "dividends") is not None else None, statement_value(current, "net_income")),
    }

    missing_count = sum(1 for value in ratios.values() if value is None)
    status = "ok" if missing_count == 0 else "partial"

    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "previous_period_end": previous.period_end.isoformat() if previous else None,
        "values": {key: json_number(value) for key, value in ratios.items()},
    }
