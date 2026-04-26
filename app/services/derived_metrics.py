from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
from typing import Any

from app.models import FinancialStatement, PriceHistory
from app.services.formula_registry import formula_ids_for_derived_metrics
from app.services.share_count_selection import shares_for_market_cap, shares_for_per_share_metric

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
FORMULA_VERSION = "sec_metrics_v3"
TTM_MIN_QUARTER_DAYS = 70
TTM_MAX_QUARTER_DAYS = 110
TTM_MIN_CONSECUTIVE_GAP_DAYS = 70
TTM_MAX_CONSECUTIVE_GAP_DAYS = 110


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

    ttm_rows = _build_ttm_rows(quarterly_rows, annual_rows)
    output.extend(_build_cadence_points(ttm_rows, "ttm", prices, filing_type="TTM"))

    series = sorted(output, key=lambda item: (item["period_end"], item["cadence"]))
    if cadence is not None:
        series = [item for item in series if item["cadence"] == cadence]
    if max_points is not None and max_points > 0 and len(series) > max_points:
        series = series[-max_points:]
    return series


def _normalize_financial_rows(financials: list[FinancialStatement]) -> list[dict[str, Any]]:
    deduped: dict[tuple[date, str], dict[str, Any]] = {}
    duplicate_counts: dict[tuple[date, str], int] = {}
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
            "statement_id": statement.id,
            "period_start": statement.period_start,
            "period_end": statement.period_end,
            "filing_type": statement.filing_type,
            "statement_type": statement.statement_type,
            "source": statement.source,
            "data": data,
            "restatement_ambiguous": False,
        }
        dedupe_key = (statement.period_end, statement.filing_type)
        duplicate_counts[dedupe_key] = duplicate_counts.get(dedupe_key, 0) + 1
        if dedupe_key in deduped:
            row["restatement_ambiguous"] = True
        deduped[dedupe_key] = row

    for dedupe_key, row in deduped.items():
        if duplicate_counts.get(dedupe_key, 0) > 1:
            row["restatement_ambiguous"] = True

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


def _build_ttm_rows(
    quarterly_rows: list[dict[str, Any]],
    annual_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    quarterly_candidates = _augment_quarterly_rows_with_derived_q4(quarterly_rows, annual_rows)
    quarterly_candidates = sorted(quarterly_candidates, key=lambda row: row["period_end"])
    if len(quarterly_candidates) < 4:
        return []

    output: list[dict[str, Any]] = []
    for index in range(3, len(quarterly_candidates)):
        trailing_rows = quarterly_candidates[index - 3 : index + 1]
        latest = trailing_rows[-1]
        validation_flags = _validate_ttm_window(trailing_rows)
        is_valid_window = len(validation_flags) == 0
        ttm_flags = list(validation_flags)

        if any(bool(row.get("q4_derived_from_annual")) for row in trailing_rows):
            ttm_flags.append("ttm_q4_derived_from_annual")

        aggregated_data: dict[str, Any] = {}
        if is_valid_window:
            for metric in FLOW_FIELDS:
                values = [_to_float(row["data"].get(metric)) for row in trailing_rows]
                non_null = [value for value in values if value is not None]
                aggregated_data[metric] = sum(non_null) if non_null else None
        else:
            # If periods are not comparable, TTM flows are explicitly unavailable.
            for metric in FLOW_FIELDS:
                aggregated_data[metric] = None

        latest_data = latest["data"]
        for key, value in latest_data.items():
            if key in FLOW_FIELDS:
                continue
            aggregated_data[key] = value

        ttm_construction = "four_reported_quarters"
        if "ttm_q4_derived_from_annual" in ttm_flags:
            ttm_construction = "annual_minus_q1_q3_derived_q4"

        output.append(
            {
                "period_start": trailing_rows[0]["period_start"],
                "period_end": latest["period_end"],
                "filing_type": "TTM",
                "statement_type": latest["statement_type"],
                "source": latest["source"],
                "data": aggregated_data,
                "ttm_validation_flags": sorted(set(ttm_flags)),
                "ttm_validation_status": "valid" if is_valid_window else "invalid",
                "ttm_construction": ttm_construction,
                "ttm_component_period_ends": [row["period_end"] for row in trailing_rows],
                "ttm_component_filing_types": [str(row["filing_type"]) for row in trailing_rows],
                "ttm_component_statement_ids": [row.get("statement_id") for row in trailing_rows if row.get("statement_id") is not None],
            }
        )

    return output


def _augment_quarterly_rows_with_derived_q4(
    quarterly_rows: list[dict[str, Any]],
    annual_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not quarterly_rows or not annual_rows:
        return list(quarterly_rows)

    augmented = list(quarterly_rows)
    existing_period_ends = {row["period_end"] for row in quarterly_rows}

    for annual in annual_rows:
        annual_start = annual["period_start"]
        annual_end = annual["period_end"]
        annual_days = (annual_end - annual_start).days + 1
        if annual_days < 330:
            continue
        if annual_end in existing_period_ends:
            continue

        in_year_quarters = [
            row
            for row in quarterly_rows
            if row["statement_type"] == annual["statement_type"]
            and annual_start <= row["period_start"] <= row["period_end"] <= annual_end
        ]
        in_year_quarters = sorted(in_year_quarters, key=lambda row: row["period_end"])
        if len(in_year_quarters) < 3:
            continue
        first_three = in_year_quarters[:3]
        if any(_quarter_length_days(row) > TTM_MAX_QUARTER_DAYS or _quarter_length_days(row) < TTM_MIN_QUARTER_DAYS for row in first_three):
            continue
        if _validate_consecutive_quarters(first_three):
            continue

        q3 = first_three[-1]
        expected_q4_end = q3["period_end"] + timedelta(days=92)
        if abs((annual_end - expected_q4_end).days) > 25:
            continue

        derived_q4_data = dict(annual["data"])
        for metric in FLOW_FIELDS:
            annual_value = _to_float(annual["data"].get(metric))
            q_values = [_to_float(row["data"].get(metric)) for row in first_three]
            if annual_value is None or any(value is None for value in q_values):
                derived_q4_data[metric] = None
                continue
            derived_q4_data[metric] = annual_value - sum(value for value in q_values if value is not None)

        derived_row = {
            "statement_id": annual.get("statement_id"),
            "period_start": q3["period_end"] + timedelta(days=1),
            "period_end": annual_end,
            "filing_type": "DERIVED_Q4",
            "statement_type": annual["statement_type"],
            "source": annual["source"],
            "data": derived_q4_data,
            "restatement_ambiguous": bool(annual.get("restatement_ambiguous")),
            "q4_derived_from_annual": True,
        }
        augmented.append(derived_row)
        existing_period_ends.add(annual_end)

    return augmented


def _validate_ttm_window(rows: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    if len(rows) != 4:
        return ["ttm_window_incomplete"]

    period_ends = [row["period_end"] for row in rows]
    if len(set(period_ends)) != 4:
        flags.append("ttm_duplicate_quarter")

    for row in rows:
        quarter_days = _quarter_length_days(row)
        if quarter_days < TTM_MIN_QUARTER_DAYS or quarter_days > TTM_MAX_QUARTER_DAYS:
            flags.append("ttm_non_quarterly_form")
            break

    flags.extend(_validate_consecutive_quarters(rows))

    quarter_lengths = [_quarter_length_days(row) for row in rows]
    if max(quarter_lengths) - min(quarter_lengths) > 20:
        flags.append("ttm_mixed_fiscal_calendars")

    if any(bool(row.get("restatement_ambiguous")) for row in rows):
        flags.append("ttm_restatement_ambiguity")

    return sorted(set(flags))


def _validate_consecutive_quarters(rows: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    if len(rows) < 2:
        return flags

    ordered = sorted(rows, key=lambda row: row["period_end"])
    gaps = [
        (ordered[index]["period_end"] - ordered[index - 1]["period_end"]).days
        for index in range(1, len(ordered))
    ]
    if any(gap > TTM_MAX_CONSECUTIVE_GAP_DAYS for gap in gaps):
        flags.append("ttm_missing_quarter")
    if any(gap < TTM_MIN_CONSECUTIVE_GAP_DAYS for gap in gaps):
        flags.append("ttm_duplicate_quarter")
    if max(gaps) - min(gaps) > 20:
        flags.append("ttm_mixed_fiscal_calendars")
    return flags


def _quarter_length_days(row: dict[str, Any]) -> int:
    return (row["period_end"] - row["period_start"]).days + 1


def _build_cadence_points(
    rows: list[dict[str, Any]],
    cadence: str,
    prices: list[dict[str, Any]],
    *,
    filing_type: str | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    price_date_index = [entry["trade_date"] for entry in prices]

    for row in rows:
        matched_price = _price_on_or_before(prices, row["period_end"], price_date_index)
        metrics = _compute_metrics(
            row["data"],
            previous["data"] if previous else None,
            matched_price,
            cadence=cadence,
            statement_type=row["statement_type"],
        )
        quality_flags = list(metrics["flags"])
        if cadence == "ttm":
            quality_flags.extend(row.get("ttm_validation_flags", []))
            quality_flags = sorted(set(quality_flags))

        provenance = {
            "statement_type": row["statement_type"],
            "statement_source": row["source"],
            "price_source": matched_price["source"] if matched_price else None,
            "formula_version": FORMULA_VERSION,
            "formula_ids": formula_ids_for_derived_metrics(METRIC_KEYS),
            "metric_semantics": _metric_semantics(cadence, row["statement_type"]),
            "market_cap_share_source": metrics["market_cap_share_source"],
            "market_cap_share_source_is_proxy": metrics["market_cap_share_source_is_proxy"],
            "per_share_metric_share_source": metrics["per_share_metric_share_source"],
            "per_share_metric_share_source_is_proxy": metrics["per_share_metric_share_source_is_proxy"],
        }
        if cadence == "ttm":
            provenance.update(
                {
                    "ttm_validation_status": row.get("ttm_validation_status", "valid"),
                    "ttm_construction": row.get("ttm_construction", "four_reported_quarters"),
                    "ttm_formula": "sum(Q1..Q4 comparable fiscal quarters) or annual - (Q1+Q2+Q3) for derived Q4",
                    "ttm_component_period_ends": [
                        component.isoformat() if isinstance(component, date) else component
                        for component in row.get("ttm_component_period_ends", [])
                    ],
                    "ttm_component_filing_types": row.get("ttm_component_filing_types", []),
                    "ttm_component_statement_ids": row.get("ttm_component_statement_ids", []),
                }
            )

        output.append(
            {
                "cadence": cadence,
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "filing_type": filing_type or row["filing_type"],
                "metrics": metrics["values"],
                "provenance": provenance,
                "quality": {
                    "available_metrics": metrics["available_metrics"],
                    "missing_metrics": metrics["missing_metrics"],
                    "coverage_ratio": metrics["coverage_ratio"],
                    "flags": quality_flags,
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
    market_cap_shares = shares_for_market_cap(current)
    per_share_shares = shares_for_per_share_metric(current)
    previous_shares_proxy = None
    previous_revenue = None
    previous_tangible_common_equity = None
    if previous is not None:
        previous_revenue = _to_float(previous.get("revenue"))
        previous_shares_proxy = shares_for_per_share_metric(previous).value
        previous_tangible_common_equity = _to_float(previous.get("tangible_common_equity"))

    invested_capital = _sum_non_null(stockholders_equity, long_term_debt, current_debt)
    if invested_capital is not None and cash_proxy is not None:
        invested_capital = invested_capital - cash_proxy

    market_cap = None
    if price_point is not None and market_cap_shares.value is not None:
        market_cap = price_point["close"] * market_cap_shares.value

    net_debt = _sum_non_null(current_debt, long_term_debt)
    if net_debt is not None and cash_proxy is not None:
        net_debt = net_debt - cash_proxy

    quarterly_annualization_scale = 4.0 if cadence == "quarterly" else 1.0
    working_capital_days_scale = 365.0 / quarterly_annualization_scale

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
        "sbc_burden": _safe_div(stock_based_compensation, revenue),
        "buyback_yield": _safe_div(_abs_if_negative(share_buybacks), market_cap, scale=quarterly_annualization_scale),
        "dividend_yield": _safe_div(_abs_if_negative(dividends), market_cap, scale=quarterly_annualization_scale),
        "working_capital_days": _safe_div(
            _sum_non_null(accounts_receivable, inventory, _negate(accounts_payable)),
            revenue,
            scale=working_capital_days_scale,
        ),
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
        "share_dilution": _pct_change(per_share_shares.value, previous_shares_proxy),
        "tangible_book_value_per_share": _safe_div(tangible_common_equity, per_share_shares.value),
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
        "market_cap_share_source": market_cap_shares.source,
        "market_cap_share_source_is_proxy": market_cap_shares.is_proxy,
        "per_share_metric_share_source": per_share_shares.source,
        "per_share_metric_share_source_is_proxy": per_share_shares.is_proxy,
    }


def _metric_semantics(cadence: str, statement_type: str) -> dict[str, str]:
    metric_keys = BANK_METRIC_KEYS if statement_type == "canonical_bank_regulatory" else GENERAL_METRIC_KEYS
    if cadence == "ttm":
        default_semantic = "ttm"
    else:
        default_semantic = "period_based"

    semantics = {key: default_semantic for key in metric_keys}
    if cadence == "quarterly":
        for key in ("buyback_yield", "dividend_yield", "working_capital_days", "roatce"):
            if key in semantics:
                semantics[key] = "annualized"
    return semantics


def _price_on_or_before(
    prices: list[dict[str, Any]],
    period_end: date,
    price_date_index: list[date],
) -> dict[str, Any] | None:
    if not prices:
        return None
    insertion = bisect_right(price_date_index, period_end)
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
