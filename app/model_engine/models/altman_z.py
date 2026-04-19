from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import json_number, latest_annual_statement, latest_statement, safe_divide, statement_value, status_explanation

MODEL_NAME = "altman_z"
MODEL_VERSION = "2.0.0"
ALTMAN_VARIANT = "classic_public_company_1968"
ALTMAN_VARIANT_LABEL = "Altman Z-score (1968 public-company variant)"

FACTOR_WEIGHTS = {
    "working_capital_to_assets": 1.2,
    "retained_earnings_to_assets": 1.4,
    "ebit_to_assets": 3.3,
    "market_value_equity_to_liabilities": 0.6,
    "sales_to_assets": 1.0,
}


def compute(dataset: CompanyDataset) -> dict[str, object]:
    current = latest_annual_statement(dataset)
    if current is None:
        latest = latest_statement(dataset)
        if latest is None:
            return {
                "status": "insufficient_data",
                "model_status": "insufficient_data",
                "explanation": status_explanation("insufficient_data"),
                "reason": "No financial statements available",
                "variant": ALTMAN_VARIANT,
                "variant_label": ALTMAN_VARIANT_LABEL,
                "z_score_approximate": None,
                "factors": {},
                "basis": "Classic public-company Altman Z requires annual financial statements and market value of equity.",
                "missing_factors": list(FACTOR_WEIGHTS.keys()),
                "missing_fields": ["annual_financial_statement"],
            }

        return {
            "status": "partial",
            "model_status": "partial",
            "explanation": status_explanation("partial"),
            "reason": "Classic public-company Altman Z requires an annual financial statement; latest available filing is not annual.",
            "period_end": latest.period_end.isoformat(),
            "filing_type": latest.filing_type,
            "variant": ALTMAN_VARIANT,
            "variant_label": ALTMAN_VARIANT_LABEL,
            "z_score_approximate": None,
            "factors": {},
            "basis": "Classic public-company Altman Z requires annual financial statements and market value of equity.",
            "missing_factors": list(FACTOR_WEIGHTS.keys()),
            "missing_fields": ["annual_financial_statement"],
        }

    total_assets = statement_value(current, "total_assets")
    total_liabilities = statement_value(current, "total_liabilities")
    current_assets = statement_value(current, "current_assets")
    current_liabilities = statement_value(current, "current_liabilities")
    retained_earnings = statement_value(current, "retained_earnings")
    revenue = statement_value(current, "revenue")
    operating_income = statement_value(current, "operating_income")
    working_capital = None
    if current_assets is not None and current_liabilities is not None:
        working_capital = float(current_assets) - float(current_liabilities)
    latest_price = dataset.market_snapshot.latest_price if dataset.market_snapshot is not None else None
    share_count = statement_value(current, "shares_outstanding")
    if share_count is None:
        share_count = statement_value(current, "weighted_average_diluted_shares")
    market_value_equity = None
    if latest_price is not None and share_count not in (None, 0):
        market_value_equity = float(latest_price) * float(share_count)

    factors = {
        "working_capital_to_assets": safe_divide(working_capital, total_assets),
        "retained_earnings_to_assets": safe_divide(retained_earnings, total_assets),
        "ebit_to_assets": safe_divide(operating_income, total_assets),
        "market_value_equity_to_liabilities": safe_divide(market_value_equity, total_liabilities),
        "sales_to_assets": safe_divide(revenue, total_assets),
    }

    missing_factors = [key for key, value in factors.items() if value is None]
    missing_fields: list[str] = []
    if total_assets is None:
        missing_fields.append("total_assets")
    if total_liabilities is None:
        missing_fields.append("total_liabilities")
    if current_assets is None:
        missing_fields.append("current_assets")
    if current_liabilities is None:
        missing_fields.append("current_liabilities")
    if retained_earnings is None:
        missing_fields.append("retained_earnings")
    if operating_income is None:
        missing_fields.append("operating_income")
    if revenue is None:
        missing_fields.append("revenue")
    if latest_price is None:
        missing_fields.append("latest_price")
    if statement_value(current, "shares_outstanding") is None and statement_value(current, "weighted_average_diluted_shares") is None:
        missing_fields.extend(["shares_outstanding", "weighted_average_diluted_shares"])

    approximate_score = None
    if not missing_factors:
        approximate_score = sum(FACTOR_WEIGHTS[key] * float(value) for key, value in factors.items() if value is not None)

    available_factor_count = len(factors) - len(missing_factors)
    status = "supported" if approximate_score is not None else "partial" if available_factor_count > 0 else "insufficient_data"
    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "variant": ALTMAN_VARIANT,
        "variant_label": ALTMAN_VARIANT_LABEL,
        "z_score_approximate": json_number(approximate_score),
        "factors": {key: json_number(value) for key, value in factors.items()},
        "basis": "Classic public-company Altman Z with annual inputs only; X4 uses market value of equity divided by total liabilities.",
        "market_value_equity": json_number(market_value_equity),
        "missing_factors": missing_factors,
        "missing_fields": sorted(set(missing_fields)),
    }
