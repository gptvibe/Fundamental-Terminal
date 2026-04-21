from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    ANNUAL_FORMS,
    average,
    book_equity,
    growth_rate,
    json_number,
    latest_statement,
    previous_comparable_statement,
    safe_divide,
    statement_value,
    status_from_data_quality,
    status_explanation,
)

MODEL_NAME = "ratios"
MODEL_VERSION = "1.2.0"

STOCK_FLOW_RATIO_KEYS = {
    "return_on_assets",
    "return_on_equity",
    "asset_turnover",
    "net_debt_to_fcf",
}


def compute(dataset: CompanyDataset) -> dict[str, object]:
    current = latest_statement(dataset)
    if current is None:
        return {"status": "insufficient_data", "model_status": "insufficient_data", "explanation": status_explanation("insufficient_data"), "reason": "No financial statements available"}

    previous = previous_comparable_statement(dataset, current)
    cadence = _statement_cadence(current)
    annualization_factor = 4.0 if cadence == "quarterly" else 1.0
    current_equity = book_equity(current)
    previous_equity = book_equity(previous) if previous else None
    average_assets = average(statement_value(current, "total_assets"), statement_value(previous, "total_assets") if previous else None)
    average_equity = average(current_equity, previous_equity)
    net_debt = (
        float(statement_value(current, "current_debt") or 0)
        + float(statement_value(current, "long_term_debt") or 0)
        - float(statement_value(current, "cash_and_short_term_investments") or 0)
    ) if any(
        statement_value(current, key) is not None
        for key in ("current_debt", "long_term_debt", "cash_and_short_term_investments")
    ) else None
    revenue = statement_value(current, "revenue")
    free_cash_flow = statement_value(current, "free_cash_flow")
    annualized_free_cash_flow = _annualize_flow(free_cash_flow, annualization_factor)

    ratios = {
        "gross_margin": safe_divide(statement_value(current, "gross_profit"), revenue),
        "operating_margin": safe_divide(statement_value(current, "operating_income"), revenue),
        "net_margin": safe_divide(statement_value(current, "net_income"), revenue),
        "operating_cash_flow_margin": safe_divide(statement_value(current, "operating_cash_flow"), revenue),
        "free_cash_flow_margin": safe_divide(free_cash_flow, revenue),
        "return_on_assets": _annualize_ratio(safe_divide(statement_value(current, "net_income"), average_assets), annualization_factor),
        "return_on_equity": _annualize_ratio(safe_divide(statement_value(current, "net_income"), average_equity), annualization_factor),
        "asset_turnover": _annualize_ratio(safe_divide(revenue, average_assets), annualization_factor),
        "liabilities_to_assets": safe_divide(statement_value(current, "total_liabilities"), statement_value(current, "total_assets")),
        "equity_ratio": safe_divide(current_equity, statement_value(current, "total_assets")),
        "revenue_growth": growth_rate(revenue, statement_value(previous, "revenue") if previous else None),
        "net_income_growth": growth_rate(statement_value(current, "net_income"), statement_value(previous, "net_income") if previous else None),
        "free_cash_flow_growth": growth_rate(free_cash_flow, statement_value(previous, "free_cash_flow") if previous else None),
        "interest_coverage": safe_divide(statement_value(current, "operating_income"), abs(float(statement_value(current, "interest_expense"))) if statement_value(current, "interest_expense") not in (None, 0) else None),
        "cash_conversion": safe_divide(statement_value(current, "operating_cash_flow"), statement_value(current, "net_income")),
        "capex_intensity": safe_divide(abs(float(statement_value(current, "capex"))) if statement_value(current, "capex") is not None else None, revenue),
        "sbc_to_revenue": safe_divide(statement_value(current, "stock_based_compensation"), revenue),
        "net_debt_to_fcf": safe_divide(net_debt, annualized_free_cash_flow),
        "payout_ratio": safe_divide(abs(float(statement_value(current, "dividends"))) if statement_value(current, "dividends") is not None else None, statement_value(current, "net_income")),
    }
    metric_semantics = {
        key: ("annualized" if cadence == "quarterly" and key in STOCK_FLOW_RATIO_KEYS else "period_based")
        for key in ratios
    }

    missing_fields = sorted(key for key, value in ratios.items() if value is None)
    status = status_from_data_quality(
        missing_fields=missing_fields,
        proxy_used=False,
        can_compute_directional=any(value is not None for value in ratios.values()),
    )

    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "cadence": cadence,
        "annualization_factor": int(annualization_factor),
        "previous_period_end": previous.period_end.isoformat() if previous else None,
        "values": {key: json_number(value) for key, value in ratios.items()},
        "metric_semantics": metric_semantics,
        "missing_required_fields_last_3y": missing_fields,
    }


def _statement_cadence(point) -> str:
    return "annual" if point.filing_type in ANNUAL_FORMS else "quarterly"


def _annualize_ratio(value: float | None, annualization_factor: float) -> float | None:
    if value is None:
        return None
    return value * annualization_factor


def _annualize_flow(value: float | int | None, annualization_factor: float) -> float | None:
    if value is None:
        return None
    return float(value) * annualization_factor
