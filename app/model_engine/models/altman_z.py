from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import book_equity, json_number, latest_annual_statement, latest_statement, safe_divide, statement_value, status_explanation

MODEL_NAME = "altman_z"
MODEL_VERSION = "1.2.0"

FACTOR_WEIGHTS = {
    "ebit_to_assets": 3.3,
    "book_equity_to_liabilities": 0.6,
    "sales_to_assets": 1.0,
    "working_capital_to_assets": 1.2,
    "retained_earnings_to_assets": 1.4,
}


def compute(dataset: CompanyDataset) -> dict[str, object]:
    current = latest_annual_statement(dataset) or latest_statement(dataset)
    if current is None:
        return {"status": "insufficient_data", "model_status": "insufficient_data", "explanation": status_explanation("insufficient_data"), "reason": "No financial statements available"}

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
    available_factors = {key: value for key, value in factors.items() if value is not None}
    if available_factors:
        present_weight = sum(FACTOR_WEIGHTS[key] for key in available_factors)
        weighted_sum = sum(FACTOR_WEIGHTS[key] * float(value) for key, value in available_factors.items())
        if present_weight:
            # Rescale to the full Altman-Z weight to avoid biasing missing factors to zero.
            total_weight = sum(FACTOR_WEIGHTS.values())
            approximate_score = weighted_sum * (total_weight / present_weight)

    status = "supported" if approximate_score is not None and len(available_factors) == len(factors) else "partial" if approximate_score is not None else "insufficient_data"
    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "z_score_approximate": json_number(approximate_score),
        "factors": {key: json_number(value) for key, value in factors.items()},
        "basis": "Book equity proxy using available normalized fields only",
        "missing_factors": [key for key, value in factors.items() if value is None],
    }
