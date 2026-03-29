from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    average,
    book_equity,
    json_number,
    latest_annual_statement,
    previous_comparable_statement,
    safe_divide,
    status_explanation,
    statement_value,
)

MODEL_NAME = "piotroski"
MODEL_VERSION = "1.3.0"


def compute(dataset: CompanyDataset) -> dict[str, object]:
    current = latest_annual_statement(dataset)
    if current is None:
        return {"status": "insufficient_data", "model_status": "insufficient_data", "explanation": status_explanation("insufficient_data"), "reason": "Annual financial statements unavailable"}

    previous = previous_comparable_statement(dataset, current)
    prior = previous_comparable_statement(dataset, previous) if previous else None
    current_net_income = statement_value(current, "net_income")
    previous_net_income = statement_value(previous, "net_income") if previous else None
    current_assets = statement_value(current, "total_assets")
    previous_assets = statement_value(previous, "total_assets") if previous else None
    current_assets_current = statement_value(current, "current_assets")
    previous_assets_current = statement_value(previous, "current_assets") if previous else None
    current_liabilities_current = statement_value(current, "current_liabilities")
    previous_liabilities_current = statement_value(previous, "current_liabilities") if previous else None
    prior_assets = statement_value(prior, "total_assets") if prior else None
    current_operating_cash_flow = statement_value(current, "operating_cash_flow")
    current_shares = statement_value(current, "shares_outstanding")
    previous_shares = statement_value(previous, "shares_outstanding") if previous else None
    current_roa = safe_divide(
        current_net_income,
        average(current_assets, previous_assets),
    )
    previous_roa = safe_divide(
        previous_net_income,
        average(previous_assets, prior_assets) if prior_assets is not None else previous_assets,
    ) if previous else None
    current_leverage = safe_divide(statement_value(current, "total_liabilities"), current_assets)
    previous_leverage = safe_divide(statement_value(previous, "total_liabilities") if previous else None, previous_assets)
    current_ratio = safe_divide(current_assets_current, current_liabilities_current)
    previous_ratio = safe_divide(previous_assets_current, previous_liabilities_current)
    current_margin = safe_divide(statement_value(current, "gross_profit"), statement_value(current, "revenue"))
    previous_margin = safe_divide(statement_value(previous, "gross_profit") if previous else None, statement_value(previous, "revenue") if previous else None)
    current_turnover = safe_divide(statement_value(current, "revenue"), average(current_assets, previous_assets))
    previous_turnover = safe_divide(
        statement_value(previous, "revenue") if previous else None,
        average(previous_assets, prior_assets) if prior_assets is not None else previous_assets,
    )

    criteria = {
        "positive_roa": _positive(current_roa),
        "positive_operating_cash_flow": _positive(current_operating_cash_flow),
        "improving_roa": _greater_than(current_roa, previous_roa),
        "operating_cash_flow_exceeds_net_income": _greater_than(current_operating_cash_flow, current_net_income),
        "lower_leverage": _less_than(current_leverage, previous_leverage),
        "better_liquidity": _greater_than(current_ratio, previous_ratio),
        "no_share_dilution": _less_than_or_equal(current_shares, previous_shares),
        "higher_gross_margin": _greater_than(current_margin, previous_margin),
        "better_asset_turnover": _greater_than(current_turnover, previous_turnover),
    }

    available = [value for value in criteria.values() if value is not None]
    score = sum(1 for value in available if value)
    available_criteria = len(available)
    normalized_score = float(score) if available_criteria == 9 else None

    status = "supported" if available_criteria == 9 else "partial"
    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "period_end": current.period_end.isoformat(),
        "score": score,
        "score_max": 9,
        "available_criteria": available_criteria,
        "normalized_score_9": json_number(normalized_score),
        "criteria": criteria,
        "unavailable_criteria": [key for key, value in criteria.items() if value is None],
        "equity_proxy": json_number(book_equity(current)),
    }


def _positive(value: float | int | None) -> bool | None:
    if value is None:
        return None
    return float(value) > 0


def _greater_than(left: float | int | None, right: float | int | None) -> bool | None:
    if left is None or right is None:
        return None
    return float(left) > float(right)


def _less_than(left: float | int | None, right: float | int | None) -> bool | None:
    if left is None or right is None:
        return None
    return float(left) < float(right)


def _less_than_or_equal(left: float | int | None, right: float | int | None) -> bool | None:
    if left is None or right is None:
        return None
    return float(left) <= float(right)
