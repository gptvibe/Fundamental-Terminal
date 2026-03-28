from __future__ import annotations

from bisect import bisect_right
from datetime import date
from typing import Any

from app.models import FinancialStatement, PriceHistory

ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
QUARTERLY_FORMS = {"10-Q", "6-K", "CALL", "FR Y-9C"}
GENERAL_METRIC_KEYS = [
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "fcf_margin",
    "roic_proxy",
    "leverage_ratio",
    "current_ratio",
    "share_dilution",
    "sbc_burden",
    "buyback_yield",
    "dividend_yield",
    "working_capital_days",
    "accrual_ratio",
    "cash_conversion",
    "segment_concentration",
]
BANK_METRIC_KEYS = [
    "net_interest_margin",
    "provision_burden",
    "asset_quality_ratio",
    "cet1_ratio",
    "tier1_capital_ratio",
    "total_capital_ratio",
    "core_deposit_ratio",
    "uninsured_deposit_ratio",
    "tangible_book_value_per_share",
    "roatce",
]
FLOW_FIELDS = {
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "free_cash_flow",
    "stock_based_compensation",
    "share_buybacks",
    "dividends",
    "net_interest_income",
    "noninterest_income",
    "noninterest_expense",
    "pretax_income",
    "provision_for_credit_losses",
}
METRIC_KEYS = [*GENERAL_METRIC_KEYS, *BANK_METRIC_KEYS]


def build_metrics_timeseries(
    financials: list[FinancialStatement],
    price_history: list[PriceHistory],
    *,
    cadence: str | None = None,
    max_points: int | None = None,
) -> list[dict[str, Any]]:
    rows = _normalize_financial_rows(financials)
    prices = _normalize_price_rows(price_history)

    annual_rows = [row for row in rows if row["filing_type"] in ANNUAL_FORMS]
    quarterly_rows = [row for row in rows if row["filing_type"] in QUARTERLY_FORMS]

    output: list[dict[str, Any]] = []
    output.extend(_build_cadence_points(annual_rows, "annual", prices))
    output.extend(_build_cadence_points(quarterly_rows, "quarterly", prices))

    ttm_rows = _build_ttm_rows(quarterly_rows)
    output.extend(_build_cadence_points(ttm_rows, "ttm", prices, filing_type="TTM"))

    series = sorted(output, key=lambda item: (item["period_end"], item["cadence"]))
    if cadence is not None:
        series = [item for item in series if item["cadence"] == cadence]
    if max_points is not None and max_points > 0 and len(series) > max_points:
        series = series[-max_points:]
    return series


def _normalize_financial_rows(financials: list[FinancialStatement]) -> list[dict[str, Any]]:
    deduped: dict[tuple[date, str], dict[str, Any]] = {}
    sorted_rows = sorted(
        financials,
        key=lambda statement: (
            statement.period_end,
            statement.filing_type,
            statement.last_updated,
            statement.id,
        ),
    )

    for statement in sorted_rows:
        data = dict(statement.data or {})
        row = {
            "period_start": statement.period_start,
            "period_end": statement.period_end,
            "filing_type": statement.filing_type,
            "statement_type": statement.statement_type,
            "source": statement.source,
            "data": data,
        }
        deduped[(statement.period_end, statement.filing_type)] = row

    return sorted(deduped.values(), key=lambda row: row["period_end"])


def _normalize_price_rows(price_history: list[PriceHistory]) -> list[dict[str, Any]]:
    return [
        {
            "trade_date": point.trade_date,
            "close": float(point.close),
            "source": point.source,
        }
        for point in sorted(price_history, key=lambda point: point.trade_date)
    ]


def _build_ttm_rows(quarterly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(quarterly_rows) < 4:
        return []

    output: list[dict[str, Any]] = []
    for index in range(3, len(quarterly_rows)):
        trailing_rows = quarterly_rows[index - 3 : index + 1]
        latest = trailing_rows[-1]
        aggregated_data: dict[str, Any] = {}

        for metric in FLOW_FIELDS:
            values = [_to_float(row["data"].get(metric)) for row in trailing_rows]
            non_null = [value for value in values if value is not None]
            aggregated_data[metric] = sum(non_null) if non_null else None

        latest_data = latest["data"]
        for key, value in latest_data.items():
            if key in FLOW_FIELDS:
                continue
            aggregated_data[key] = value

        output.append(
            {
                "period_start": trailing_rows[0]["period_start"],
                "period_end": latest["period_end"],
                "filing_type": "TTM",
                "statement_type": latest["statement_type"],
                "source": latest["source"],
                "data": aggregated_data,
            }
        )

    return output


def _build_cadence_points(
    rows: list[dict[str, Any]],
    cadence: str,
    prices: list[dict[str, Any]],
    *,
    filing_type: str | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None

    for row in rows:
        matched_price = _price_on_or_before(prices, row["period_end"])
        metrics = _compute_metrics(
            row["data"],
            previous["data"] if previous else None,
            matched_price,
            cadence=cadence,
            statement_type=row["statement_type"],
        )
        output.append(
            {
                "cadence": cadence,
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "filing_type": filing_type or row["filing_type"],
                "metrics": metrics["values"],
                "provenance": {
                    "statement_type": row["statement_type"],
                    "statement_source": row["source"],
                    "price_source": matched_price["source"] if matched_price else None,
                    "formula_version": "sec_metrics_v1",
                },
                "quality": {
                    "available_metrics": metrics["available_metrics"],
                    "missing_metrics": metrics["missing_metrics"],
                    "coverage_ratio": metrics["coverage_ratio"],
                    "flags": metrics["flags"],
                },
            }
        )
        previous = row

    return output


def _compute_metrics(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    price_point: dict[str, Any] | None,
    *,
    cadence: str,
    statement_type: str,
) -> dict[str, Any]:
    revenue = _to_float(current.get("revenue"))
    gross_profit = _to_float(current.get("gross_profit"))
    operating_income = _to_float(current.get("operating_income"))
    free_cash_flow = _to_float(current.get("free_cash_flow"))
    net_income = _to_float(current.get("net_income"))

    total_assets = _to_float(current.get("total_assets"))
    current_assets = _to_float(current.get("current_assets"))
    current_liabilities = _to_float(current.get("current_liabilities"))
    current_debt = _to_float(current.get("current_debt"))
    long_term_debt = _to_float(current.get("long_term_debt"))
    stockholders_equity = _to_float(current.get("stockholders_equity"))
    operating_cash_flow = _to_float(current.get("operating_cash_flow"))
    stock_based_compensation = _to_float(current.get("stock_based_compensation"))
    share_buybacks = _to_float(current.get("share_buybacks"))
    dividends = _to_float(current.get("dividends"))
    accounts_receivable = _to_float(current.get("accounts_receivable"))
    inventory = _to_float(current.get("inventory"))
    accounts_payable = _to_float(current.get("accounts_payable"))

    cash_proxy = _first_non_null(
        _to_float(current.get("cash_and_short_term_investments")),
        _to_float(current.get("cash_and_cash_equivalents")),
    )
    tangible_common_equity = _to_float(current.get("tangible_common_equity"))
    shares_proxy = _first_non_null(
        _to_float(current.get("weighted_average_diluted_shares")),
        _to_float(current.get("shares_outstanding")),
    )
    previous_shares_proxy = None
    previous_revenue = None
    previous_tangible_common_equity = None
    if previous is not None:
        previous_revenue = _to_float(previous.get("revenue"))
        previous_shares_proxy = _first_non_null(
            _to_float(previous.get("weighted_average_diluted_shares")),
            _to_float(previous.get("shares_outstanding")),
        )
        previous_tangible_common_equity = _to_float(previous.get("tangible_common_equity"))

    invested_capital = _sum_non_null(stockholders_equity, long_term_debt, current_debt)
    if invested_capital is not None and cash_proxy is not None:
        invested_capital = invested_capital - cash_proxy

    market_cap = None
    if price_point is not None and shares_proxy is not None:
        market_cap = price_point["close"] * shares_proxy

    net_debt = _sum_non_null(current_debt, long_term_debt)
    if net_debt is not None and cash_proxy is not None:
        net_debt = net_debt - cash_proxy

    segment_concentration = _segment_revenue_concentration(current.get("segment_breakdown"))
    average_tangible_common_equity = None
    if tangible_common_equity is not None:
        average_tangible_common_equity = tangible_common_equity if previous_tangible_common_equity is None else (tangible_common_equity + previous_tangible_common_equity) / 2.0

    values: dict[str, float | None] = {
        "revenue_growth": _pct_change(revenue, previous_revenue),
        "gross_margin": _safe_div(gross_profit, revenue),
        "operating_margin": _safe_div(operating_income, revenue),
        "fcf_margin": _safe_div(free_cash_flow, revenue),
        "roic_proxy": _safe_div(operating_income, invested_capital),
        "leverage_ratio": _safe_div(net_debt, stockholders_equity),
        "current_ratio": _safe_div(current_assets, current_liabilities),
        "share_dilution": _pct_change(shares_proxy, previous_shares_proxy),
        "sbc_burden": _safe_div(stock_based_compensation, revenue),
        "buyback_yield": _safe_div(_abs_if_negative(share_buybacks), market_cap),
        "dividend_yield": _safe_div(_abs_if_negative(dividends), market_cap),
        "working_capital_days": _safe_div(_sum_non_null(accounts_receivable, inventory, _negate(accounts_payable)), revenue, scale=365.0),
        "accrual_ratio": _safe_div(_difference(net_income, operating_cash_flow), total_assets),
        "cash_conversion": _safe_div(free_cash_flow, net_income),
        "segment_concentration": segment_concentration,
        "net_interest_margin": _to_float(current.get("net_interest_margin")),
        "provision_burden": _safe_div(_to_float(current.get("provision_for_credit_losses")), _to_float(current.get("net_interest_income"))),
        "asset_quality_ratio": _to_float(current.get("nonperforming_assets_ratio")),
        "cet1_ratio": _to_float(current.get("common_equity_tier1_ratio")),
        "tier1_capital_ratio": _to_float(current.get("tier1_risk_weighted_ratio")),
        "total_capital_ratio": _to_float(current.get("total_risk_based_capital_ratio")),
        "core_deposit_ratio": _safe_div(_to_float(current.get("core_deposits")), _to_float(current.get("deposits_total"))),
        "uninsured_deposit_ratio": _safe_div(_to_float(current.get("uninsured_deposits")), _to_float(current.get("deposits_total"))),
        "tangible_book_value_per_share": _safe_div(tangible_common_equity, shares_proxy),
        "roatce": _safe_div(net_income, average_tangible_common_equity, scale=4.0 if cadence == "quarterly" else 1.0),
    }

    metric_keys = BANK_METRIC_KEYS if statement_type == "canonical_bank_regulatory" else GENERAL_METRIC_KEYS
    missing_metrics = [key for key in metric_keys if values.get(key) is None]
    available_metrics = len(metric_keys) - len(missing_metrics)
    coverage_ratio = available_metrics / len(metric_keys) if metric_keys else 0.0
    flags: list[str] = []
    if coverage_ratio < 0.65:
        flags.append("low_metric_coverage")
    if segment_concentration is None:
        flags.append("segment_data_unavailable")
    if market_cap is None:
        flags.append("missing_price_context")
    if values["net_interest_margin"] is None and any(current.get(key) is not None for key in ("net_interest_income", "deposits_total", "common_equity_tier1_ratio")):
        flags.append("bank_metric_inputs_partial")

    return {
        "values": values,
        "available_metrics": available_metrics,
        "missing_metrics": missing_metrics,
        "coverage_ratio": round(coverage_ratio, 4),
        "flags": flags,
    }


def _price_on_or_before(prices: list[dict[str, Any]], period_end: date) -> dict[str, Any] | None:
    if not prices:
        return None
    date_index = [entry["trade_date"] for entry in prices]
    insertion = bisect_right(date_index, period_end)
    if insertion <= 0:
        return None
    return prices[insertion - 1]


def _segment_revenue_concentration(payload: Any) -> float | None:
    if not isinstance(payload, list):
        return None
    revenues = [
        _to_float(item.get("revenue"))
        for item in payload
        if isinstance(item, dict)
    ]
    valid = [value for value in revenues if value is not None and value > 0]
    total = sum(valid)
    if total <= 0:
        return None
    top_two = sorted(valid, reverse=True)[:2]
    return sum(top_two) / total


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _safe_div(numerator: float | None, denominator: float | None, *, scale: float = 1.0) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator) * scale


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous) - 1.0


def _sum_non_null(*values: float | None) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered)


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _negate(value: float | None) -> float | None:
    if value is None:
        return None
    return -value


def _abs_if_negative(value: float | None) -> float | None:
    if value is None:
        return None
    if value < 0:
        return abs(value)
    return value


def _first_non_null(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None
