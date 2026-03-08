from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import book_equity, json_number, latest_annual_statement, latest_statement, safe_divide, statement_value

MODEL_NAME = "altman_z"
MODEL_VERSION = "1.1.0"


def compute(dataset: CompanyDataset) -> dict[str, object]:
    current = latest_annual_statement(dataset) or latest_statement(dataset)
    if current is None:
        return {"status": "insufficient_data", "reason": "No financial statements available"}

    total_assets = statement_value(current, "total_assets")
    total_liabilities = statement_value(current, "total_liabilities")
    current_assets = statement_value(current, "current_assets")
    current_liabilities = statement_value(current, "current_liabilities")
    retained_earnings = statement_value(current, "retained_earnings")
    revenue = statement_value(current, "revenue")
    operating_income = statement_value(current, "operating_income")
    equity_proxy = book_equity(current)
    working_capital = None
    if current_assets is not None and current_liabilities is not None:
        working_capital = float(current_assets) - float(current_liabilities)

    factors = {
        "ebit_to_assets": safe_divide(operating_income, total_assets),
        "book_equity_to_liabilities": safe_divide(equity_proxy, total_liabilities),
        "sales_to_assets": safe_divide(revenue, total_assets),
        "working_capital_to_assets": safe_divide(working_capital, total_assets),
        "retained_earnings_to_assets": safe_divide(retained_earnings, total_assets),
    }

    approximate_score = None
    core_factors_available = None not in (
        factors["ebit_to_assets"],
        factors["book_equity_to_liabilities"],
        factors["sales_to_assets"],
    )
    if core_factors_available:
        approximate_score = (
            3.3 * float(factors["ebit_to_assets"])
            + 0.6 * float(factors["book_equity_to_liabilities"])
            + 1.0 * float(factors["sales_to_assets"])
            + (1.2 * float(factors["working_capital_to_assets"]) if factors["working_capital_to_assets"] is not None else 0.0)
            + (1.4 * float(factors["retained_earnings_to_assets"]) if factors["retained_earnings_to_assets"] is not None else 0.0)
        )

    return {
        "status": "ok" if approximate_score is not None and all(value is not None for value in factors.values()) else "approximate" if approximate_score is not None else "insufficient_data",
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "z_score_approximate": json_number(approximate_score),
        "factors": {key: json_number(value) for key, value in factors.items()},
        "basis": "Book equity proxy using available normalized fields only",
        "missing_factors": [key for key, value in factors.items() if value is None],
    }
