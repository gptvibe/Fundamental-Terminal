from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, DerivedMetricPoint, FinancialStatement, PriceHistory
from app.services.regulated_financials import BANK_REGULATORY_STATEMENT_TYPE, select_preferred_financials
from app.services.refresh_state import build_payload_version_hash, mark_dataset_checked

ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
QUARTERLY_FORMS = {"10-Q", "6-K", "CALL", "FR Y-9C"}
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
    "eps",
    "net_interest_income",
    "noninterest_income",
    "noninterest_expense",
    "pretax_income",
    "provision_for_credit_losses",
}
FORMULA_VERSION = "sec_metrics_mart_v1"
DERIVED_METRICS_PAYLOAD_VERSION = "derived-metrics-v1"
POSTGRES_MAX_BIND_PARAMS = 65535
DERIVED_METRIC_UPSERT_COLUMN_COUNT = 14
DERIVED_METRIC_UPSERT_BATCH_SIZE = POSTGRES_MAX_BIND_PARAMS // DERIVED_METRIC_UPSERT_COLUMN_COUNT


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    unit: str
    compute: Callable[["MetricContext"], tuple[float | None, bool, list[str]]]


@dataclass(frozen=True, slots=True)
class MetricContext:
    period_type: str
    current: dict[str, Any]
    previous: dict[str, Any] | None
    first: dict[str, Any] | None
    price_point: dict[str, Any] | None
    as_of_date: date


def recompute_and_persist_company_derived_metrics(
    session: Session,
    company_id: int,
    *,
    checked_at: datetime | None = None,
    payload_version_hash: str | None = None,
) -> int:
    company = session.get(Company, company_id)
    if company is None:
        return 0

    all_financials = list(
        session.execute(
            select(FinancialStatement).where(
                FinancialStatement.company_id == company_id,
                FinancialStatement.statement_type.in_(("canonical_xbrl", BANK_REGULATORY_STATEMENT_TYPE)),
            )
        ).scalars()
    )
    sec_financials = [item for item in all_financials if item.statement_type == "canonical_xbrl"]
    regulated_financials = [item for item in all_financials if item.statement_type == BANK_REGULATORY_STATEMENT_TYPE]
    financials = select_preferred_financials(company, sec_financials, regulated_financials)
    prices = []
    if not settings.strict_official_mode:
        prices = list(session.execute(select(PriceHistory).where(PriceHistory.company_id == company_id)).scalars())
    points = build_derived_metric_points(financials, prices)
    effective_payload_version_hash = payload_version_hash or build_payload_version_hash(
        version=DERIVED_METRICS_PAYLOAD_VERSION,
        payload=points,
    )

    session.execute(delete(DerivedMetricPoint).where(DerivedMetricPoint.company_id == company_id))
    if not points:
        timestamp = checked_at or datetime.now(timezone.utc)
        mark_dataset_checked(
            session,
            company_id,
            "derived_metrics",
            checked_at=timestamp,
            success=True,
            payload_version_hash=effective_payload_version_hash,
            invalidate_hot_cache=True,
        )
        return 0

    timestamp = checked_at or datetime.now(timezone.utc)
    payloads = []
    for point in points:
        payload = {
            "company_id": company_id,
            "period_start": point["period_start"],
            "period_end": point["period_end"],
            "period_type": point["period_type"],
            "filing_type": point["filing_type"],
            "metric_key": point["metric_key"],
            "metric_value": point["metric_value"],
            "metric_date": point["metric_date"],
            "is_proxy": point["is_proxy"],
            "provenance": point["provenance"],
            "source_statement_ids": point["source_statement_ids"],
            "quality_flags": point["quality_flags"],
            "last_updated": timestamp,
            "last_checked": timestamp,
        }
        payloads.append(payload)

    for batch in _chunked_payloads(payloads, DERIVED_METRIC_UPSERT_BATCH_SIZE):
        statement = insert(DerivedMetricPoint).values(batch)
        statement = statement.on_conflict_do_update(
            constraint="uq_derived_metric_points_company_period_type_metric",
            set_={
                "period_start": statement.excluded.period_start,
                "filing_type": statement.excluded.filing_type,
                "metric_value": statement.excluded.metric_value,
                "metric_date": statement.excluded.metric_date,
                "is_proxy": statement.excluded.is_proxy,
                "provenance": statement.excluded.provenance,
                "source_statement_ids": statement.excluded.source_statement_ids,
                "quality_flags": statement.excluded.quality_flags,
                "last_updated": statement.excluded.last_updated,
                "last_checked": statement.excluded.last_checked,
            },
        )
        session.execute(statement)
    mark_dataset_checked(
        session,
        company_id,
        "derived_metrics",
        checked_at=timestamp,
        success=True,
        payload_version_hash=effective_payload_version_hash,
        invalidate_hot_cache=True,
    )
    return len(payloads)


def _chunked_payloads(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def build_derived_metric_points(financials: list[FinancialStatement], prices: list[PriceHistory]) -> list[dict[str, Any]]:
    rows = _normalize_financial_rows(financials)
    price_rows = _normalize_price_rows(prices)

    annual_rows = [row for row in rows if row["filing_type"] in ANNUAL_FORMS]
    quarterly_rows = [row for row in rows if row["filing_type"] in QUARTERLY_FORMS]
    ttm_rows = _build_ttm_rows(quarterly_rows)

    points: list[dict[str, Any]] = []
    points.extend(_build_points_for_cadence(annual_rows, "annual", price_rows))
    points.extend(_build_points_for_cadence(quarterly_rows, "quarterly", price_rows))
    points.extend(_build_points_for_cadence(ttm_rows, "ttm", price_rows))
    return points


def to_period_payload(rows: list[DerivedMetricPoint]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, date, date, str], list[DerivedMetricPoint]] = defaultdict(list)
    for row in rows:
        grouped[(row.period_type, row.period_start, row.period_end, row.filing_type)].append(row)

    payload: list[dict[str, Any]] = []
    for key in sorted(grouped.keys(), key=lambda item: (item[0], item[2])):
        period_type, period_start, period_end, filing_type = key
        metric_rows = sorted(grouped[key], key=lambda item: item.metric_key)
        payload.append(
            {
                "period_type": period_type,
                "period_start": period_start,
                "period_end": period_end,
                "filing_type": filing_type,
                "metrics": [
                    {
                        "metric_key": metric.metric_key,
                        "metric_value": metric.metric_value,
                        "is_proxy": metric.is_proxy,
                        "provenance": metric.provenance,
                        "quality_flags": metric.quality_flags,
                    }
                    for metric in metric_rows
                ],
            }
        )
    return payload


def to_period_payload_from_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, date, date, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["period_type"], row["period_start"], row["period_end"], row["filing_type"])].append(row)

    payload: list[dict[str, Any]] = []
    for key in sorted(grouped.keys(), key=lambda item: (item[0], item[2])):
        period_type, period_start, period_end, filing_type = key
        metric_rows = sorted(grouped[key], key=lambda item: str(item.get("metric_key") or ""))
        payload.append(
            {
                "period_type": period_type,
                "period_start": period_start,
                "period_end": period_end,
                "filing_type": filing_type,
                "metrics": [
                    {
                        "metric_key": metric.get("metric_key"),
                        "metric_value": metric.get("metric_value"),
                        "is_proxy": bool(metric.get("is_proxy")),
                        "provenance": metric.get("provenance") or {},
                        "quality_flags": list(metric.get("quality_flags") or []),
                    }
                    for metric in metric_rows
                ],
            }
        )
    return payload


def build_summary_payload(rows: list[DerivedMetricPoint], period_type: str) -> dict[str, Any]:
    if not rows:
        return {"period_type": period_type, "latest_period_end": None, "metrics": []}

    preferred = [item for item in rows if item.period_type == period_type]
    if not preferred:
        fallback_order = ["ttm", "annual", "quarterly"]
        for fallback in fallback_order:
            preferred = [item for item in rows if item.period_type == fallback]
            if preferred:
                period_type = fallback
                break

    latest_period_end = max(item.period_end for item in preferred)
    latest_rows = [item for item in preferred if item.period_end == latest_period_end]
    latest_rows.sort(key=lambda item: item.metric_key)
    return {
        "period_type": period_type,
        "latest_period_end": latest_period_end,
        "metrics": [
            {
                "metric_key": row.metric_key,
                "metric_value": row.metric_value,
                "is_proxy": row.is_proxy,
                "provenance": row.provenance,
                "quality_flags": row.quality_flags,
            }
            for row in latest_rows
        ],
    }


def build_summary_payload_from_points(rows: list[dict[str, Any]], period_type: str) -> dict[str, Any]:
    if not rows:
        return {"period_type": period_type, "latest_period_end": None, "metrics": []}

    preferred = [item for item in rows if item.get("period_type") == period_type]
    if not preferred:
        fallback_order = ["ttm", "annual", "quarterly"]
        for fallback in fallback_order:
            preferred = [item for item in rows if item.get("period_type") == fallback]
            if preferred:
                period_type = fallback
                break

    latest_period_end = max(item["period_end"] for item in preferred)
    latest_rows = [item for item in preferred if item.get("period_end") == latest_period_end]
    latest_rows.sort(key=lambda item: str(item.get("metric_key") or ""))
    return {
        "period_type": period_type,
        "latest_period_end": latest_period_end,
        "metrics": [
            {
                "metric_key": row.get("metric_key"),
                "metric_value": row.get("metric_value"),
                "is_proxy": bool(row.get("is_proxy")),
                "provenance": row.get("provenance") or {},
                "quality_flags": list(row.get("quality_flags") or []),
            }
            for row in latest_rows
        ],
    }


def _build_points_for_cadence(rows: list[dict[str, Any]], period_type: str, prices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    first = rows[0] if rows else None
    for index, row in enumerate(rows):
        previous = rows[index - 1] if index > 0 else None
        price_point = _price_on_or_before(prices, row["period_end"])
        context = MetricContext(
            period_type=period_type,
            current=row,
            previous=previous,
            first=first,
            price_point=price_point,
            as_of_date=date.today(),
        )
        for definition in METRIC_REGISTRY:
            value, is_proxy, flags = definition.compute(context)
            period_flags = list(row.get("quality_flags", []))
            output.append(
                {
                    "period_type": period_type,
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "filing_type": row["filing_type"],
                    "metric_key": definition.key,
                    "metric_value": value,
                    "metric_date": row["period_end"],
                    "is_proxy": is_proxy,
                    "provenance": {
                        "formula_version": FORMULA_VERSION,
                        "unit": definition.unit,
                        "statement_type": row["statement_type"],
                        "statement_source": row["source"],
                        "price_source": price_point["source"] if price_point else None,
                        "period_type": period_type,
                    },
                    "source_statement_ids": row["statement_ids"],
                    "quality_flags": sorted(set(period_flags + flags)),
                }
            )
    return output


def _normalize_financial_rows(financials: list[FinancialStatement]) -> list[dict[str, Any]]:
    grouped: dict[tuple[date, str], list[FinancialStatement]] = defaultdict(list)
    for statement in financials:
        grouped[(statement.period_end, statement.filing_type)].append(statement)

    normalized: list[dict[str, Any]] = []
    for (_period_end, _filing_type), statements in grouped.items():
        sorted_statements = sorted(statements, key=lambda item: (item.last_updated, item.id))
        latest = sorted_statements[-1]
        distinct_payloads = {str(item.data or {}) for item in sorted_statements}
        quality_flags: list[str] = []
        if len(distinct_payloads) > 1:
            quality_flags.append("restatement_detected")
        row = {
            "statement_ids": [item.id for item in sorted_statements],
            "period_start": latest.period_start,
            "period_end": latest.period_end,
            "filing_type": latest.filing_type,
            "statement_type": latest.statement_type,
            "source": latest.source,
            "last_updated": latest.last_updated,
            "quality_flags": quality_flags,
            "data": dict(latest.data or {}),
        }
        normalized.append(row)
    normalized.sort(key=lambda item: item["period_end"])
    return normalized


def _normalize_price_rows(prices: list[PriceHistory]) -> list[dict[str, Any]]:
    return [
        {
            "trade_date": point.trade_date,
            "close": float(point.close),
            "source": point.source,
        }
        for point in sorted(prices, key=lambda point: point.trade_date)
    ]


def _build_ttm_rows(quarterly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(quarterly_rows) < 4:
        return []

    output: list[dict[str, Any]] = []
    for index in range(3, len(quarterly_rows)):
        trailing_rows = quarterly_rows[index - 3 : index + 1]
        latest = trailing_rows[-1]
        aggregated: dict[str, Any] = {}

        for key in FLOW_FIELDS:
            values = [_to_float(item["data"].get(key)) for item in trailing_rows]
            non_null = [item for item in values if item is not None]
            aggregated[key] = sum(non_null) if non_null else None

        for key, value in latest["data"].items():
            if key in FLOW_FIELDS:
                continue
            aggregated[key] = value

        quality_flags = []
        for row in trailing_rows:
            quality_flags.extend(row.get("quality_flags", []))

        output.append(
            {
                "statement_ids": [statement_id for row in trailing_rows for statement_id in row["statement_ids"]],
                "period_start": trailing_rows[0]["period_start"],
                "period_end": latest["period_end"],
                "filing_type": "TTM",
                "statement_type": latest["statement_type"],
                "source": latest["source"],
                "last_updated": latest["last_updated"],
                "quality_flags": sorted(set(quality_flags)),
                "data": aggregated,
            }
        )

    return output


def _num(context: MetricContext, key: str) -> float | None:
    return _to_float((context.current.get("data") or {}).get(key))


def _prev_num(context: MetricContext, key: str) -> float | None:
    if context.previous is None:
        return None
    return _to_float((context.previous.get("data") or {}).get(key))


def _first_num(context: MetricContext, key: str) -> float | None:
    if context.first is None:
        return None
    return _to_float((context.first.get("data") or {}).get(key))


def _shares_proxy(data: dict[str, Any]) -> float | None:
    return _first_non_null(
        _to_float(data.get("weighted_average_diluted_shares")),
        _to_float(data.get("shares_outstanding")),
    )


def _price_on_or_before(prices: list[dict[str, Any]], period_end: date) -> dict[str, Any] | None:
    if not prices:
        return None
    dates = [point["trade_date"] for point in prices]
    insertion = bisect_right(dates, period_end)
    if insertion <= 0:
        return None
    return prices[insertion - 1]


def _segment_concentration(data: dict[str, Any], *, kind: str) -> tuple[float | None, bool, list[str]]:
    payload = data.get("segment_breakdown")
    if not isinstance(payload, list):
        return None, True, ["segment_data_unavailable"]

    selected: list[float] = []
    partial = False
    for item in payload:
        if not isinstance(item, dict):
            continue
        item_kind = str(item.get("kind") or "business")
        if item_kind != kind:
            continue
        value = _to_float(item.get("revenue"))
        if value is None:
            partial = True
            continue
        if value > 0:
            selected.append(value)

    if not selected:
        return None, True, ["segment_data_unavailable"]

    total = sum(selected)
    if total <= 0:
        return None, True, ["segment_data_unavailable"]
    top_two = sorted(selected, reverse=True)[:2]
    flags = ["segment_data_partial"] if partial else []
    return sum(top_two) / total, False, flags


def _compute_filing_lag_days(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    data = context.current.get("data") or {}
    raw_date = data.get("filing_date")
    period_end = context.current.get("period_end")
    if not isinstance(period_end, date):
        return None, True, ["period_end_unavailable"]

    if isinstance(raw_date, str):
        try:
            filing_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
            return float((filing_date - period_end).days), False, []
        except ValueError:
            pass

    last_updated = context.current.get("last_updated")
    if isinstance(last_updated, datetime):
        return float((last_updated.date() - period_end).days), True, ["filing_lag_proxy_from_last_updated"]
    return None, True, ["filing_date_unavailable"]


def _compute_stale_period_flag(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    period_end = context.current.get("period_end")
    if not isinstance(period_end, date):
        return None, True, ["period_end_unavailable"]

    age_days = (context.as_of_date - period_end).days
    threshold = 550 if context.period_type == "annual" else 190
    return (1.0 if age_days > threshold else 0.0), True, []


def _metric_from_key(key: str) -> Callable[[MetricContext], tuple[float | None, bool, list[str]]]:
    def _inner(context: MetricContext) -> tuple[float | None, bool, list[str]]:
        value = _num(context, key)
        return value, False, (["source_value_missing"] if value is None else [])

    return _inner


def _revenue_growth(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _pct_change(_num(context, "revenue"), _prev_num(context, "revenue"))
    return value, True, (["growth_requires_previous_period"] if value is None else [])


def _eps_growth(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _pct_change(_num(context, "eps"), _prev_num(context, "eps"))
    return value, True, (["growth_requires_previous_period"] if value is None else [])


def _gross_margin(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "gross_profit"), _num(context, "revenue")), False, []


def _operating_margin(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "operating_income"), _num(context, "revenue")), False, []


def _net_margin(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "net_income"), _num(context, "revenue")), False, []


def _fcf_margin(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "free_cash_flow"), _num(context, "revenue")), False, []


def _roic_proxy(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    data = context.current.get("data") or {}
    cash_proxy = _first_non_null(_to_float(data.get("cash_and_short_term_investments")), _to_float(data.get("cash_and_cash_equivalents")))
    invested_capital = _sum_non_null(_to_float(data.get("stockholders_equity")), _to_float(data.get("long_term_debt")), _to_float(data.get("current_debt")))
    if invested_capital is not None and cash_proxy is not None:
        invested_capital -= cash_proxy
    return _safe_div(_num(context, "operating_income"), invested_capital), True, []


def _roe(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "net_income"), _num(context, "stockholders_equity")), False, []


def _roa(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "net_income"), _num(context, "total_assets")), False, []


def _debt_to_equity(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    debt = _sum_non_null(_num(context, "current_debt"), _num(context, "long_term_debt"))
    return _safe_div(debt, _num(context, "stockholders_equity")), False, []


def _debt_to_assets(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    debt = _sum_non_null(_num(context, "current_debt"), _num(context, "long_term_debt"))
    return _safe_div(debt, _num(context, "total_assets")), False, []


def _interest_coverage_proxy(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    interest = _num(context, "interest_expense")
    if interest is not None and interest < 0:
        interest = abs(interest)
    return _safe_div(_num(context, "operating_income"), interest), True, []


def _current_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "current_assets"), _num(context, "current_liabilities")), False, []


def _cash_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    data = context.current.get("data") or {}
    cash_proxy = _first_non_null(_to_float(data.get("cash_and_short_term_investments")), _to_float(data.get("cash_and_cash_equivalents")))
    return _safe_div(cash_proxy, _num(context, "current_liabilities")), True, []


def _dilution_trend(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    current_shares = _shares_proxy(context.current.get("data") or {})
    previous_shares = _shares_proxy(context.previous.get("data") or {}) if context.previous else None
    value = _pct_change(current_shares, previous_shares)
    return value, True, (["shares_history_unavailable"] if value is None else [])


def _shares_cagr(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    current_shares = _shares_proxy(context.current.get("data") or {})
    first_shares = _shares_proxy(context.first.get("data") or {}) if context.first else None
    current_end = context.current.get("period_end")
    first_end = context.first.get("period_end") if context.first else None
    if current_shares is None or first_shares is None or first_shares <= 0:
        return None, True, ["shares_history_unavailable"]
    if not isinstance(current_end, date) or not isinstance(first_end, date):
        return None, True, ["period_date_unavailable"]
    years = max((current_end - first_end).days / 365.25, 0.25)
    return ((current_shares / first_shares) ** (1.0 / years)) - 1.0, True, []


def _sbc_to_revenue(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "stock_based_compensation"), _num(context, "revenue")), False, []


def _market_cap(context: MetricContext) -> float | None:
    price = context.price_point.get("close") if context.price_point else None
    shares = _shares_proxy(context.current.get("data") or {})
    if price is None or shares is None:
        return None
    return price * shares


def _quarterly_annualization_scale(context: MetricContext) -> float:
    return 4.0 if context.period_type == "quarterly" else 1.0


def _working_capital_days_scale(context: MetricContext) -> float:
    return 365.0 / _quarterly_annualization_scale(context)


def _dividend_yield_proxy(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    market_cap = _market_cap(context)
    dividends = _num(context, "dividends")
    if dividends is not None and dividends < 0:
        dividends = abs(dividends)
    value = _safe_div(dividends, market_cap, scale=_quarterly_annualization_scale(context))
    flags = ["missing_price_context"] if market_cap is None else []
    return value, True, flags


def _buyback_yield_proxy(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    market_cap = _market_cap(context)
    buybacks = _num(context, "share_buybacks")
    if buybacks is not None and buybacks < 0:
        buybacks = abs(buybacks)
    value = _safe_div(buybacks, market_cap, scale=_quarterly_annualization_scale(context))
    flags = ["missing_price_context"] if market_cap is None else []
    return value, True, flags


def _shareholder_yield(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    dividend, _, div_flags = _dividend_yield_proxy(context)
    buyback, _, buyback_flags = _buyback_yield_proxy(context)
    return _sum_non_null(dividend, buyback), True, sorted(set(div_flags + buyback_flags))


def _dso(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(
        _num(context, "accounts_receivable"),
        _num(context, "revenue"),
        scale=_working_capital_days_scale(context),
    ), True, []


def _cost_of_revenue(context: MetricContext) -> float | None:
    return _difference(_num(context, "revenue"), _num(context, "gross_profit"))


def _dio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(
        _num(context, "inventory"),
        _cost_of_revenue(context),
        scale=_working_capital_days_scale(context),
    ), True, []


def _dpo(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(
        _num(context, "accounts_payable"),
        _cost_of_revenue(context),
        scale=_working_capital_days_scale(context),
    ), True, []


def _ccc(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    dso_value, _, _ = _dso(context)
    dio_value, _, _ = _dio(context)
    dpo_value, _, _ = _dpo(context)
    if dso_value is None or dio_value is None or dpo_value is None:
        return None, True, ["working_capital_inputs_missing"]
    return dso_value + dio_value - dpo_value, True, []


def _accrual_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _safe_div(_difference(_num(context, "net_income"), _num(context, "operating_cash_flow")), _num(context, "total_assets"))
    return value, True, []


def _cash_conversion_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _safe_div(_num(context, "free_cash_flow"), _num(context, "net_income")), True, []


def _net_interest_margin_metric(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _num(context, "net_interest_margin")
    return value, False, (["source_value_missing"] if value is None else [])


def _provision_burden(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _safe_div(_num(context, "provision_for_credit_losses"), _num(context, "net_interest_income"))
    return value, True, (["bank_provision_inputs_missing"] if value is None else [])


def _asset_quality_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _num(context, "nonperforming_assets_ratio")
    return value, False, (["source_value_missing"] if value is None else [])


def _cet1_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _num(context, "common_equity_tier1_ratio")
    return value, False, (["source_value_missing"] if value is None else [])


def _tier1_capital_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _num(context, "tier1_risk_weighted_ratio")
    return value, False, (["source_value_missing"] if value is None else [])


def _total_capital_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _num(context, "total_risk_based_capital_ratio")
    return value, False, (["source_value_missing"] if value is None else [])


def _core_deposit_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _safe_div(_num(context, "core_deposits"), _num(context, "deposits_total"))
    return value, True, (["bank_deposit_inputs_missing"] if value is None else [])


def _uninsured_deposit_ratio(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _safe_div(_num(context, "uninsured_deposits"), _num(context, "deposits_total"))
    return value, True, (["bank_deposit_inputs_missing"] if value is None else [])


def _tangible_book_value_per_share(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    value = _safe_div(_num(context, "tangible_common_equity"), _shares_proxy(context.current.get("data") or {}))
    return value, True, (["tangible_book_inputs_missing"] if value is None else [])


def _roatce(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    current_tce = _num(context, "tangible_common_equity")
    previous_tce = _prev_num(context, "tangible_common_equity")
    if current_tce is None:
        return None, True, ["roatce_inputs_missing"]
    average_tce = current_tce if previous_tce is None else (current_tce + previous_tce) / 2.0
    net_income = _num(context, "net_income")
    if net_income is None or average_tce == 0:
        return None, True, ["roatce_inputs_missing"]
    annualization = _quarterly_annualization_scale(context)
    return (net_income * annualization) / average_tce, True, ([] if previous_tce is not None else ["roatce_average_equity_proxy"])


def _business_segment_concentration(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _segment_concentration(context.current.get("data") or {}, kind="business")


def _geography_segment_concentration(context: MetricContext) -> tuple[float | None, bool, list[str]]:
    return _segment_concentration(context.current.get("data") or {}, kind="geographic")


METRIC_REGISTRY: tuple[MetricDefinition, ...] = (
    MetricDefinition("revenue", "usd", _metric_from_key("revenue")),
    MetricDefinition("gross_profit", "usd", _metric_from_key("gross_profit")),
    MetricDefinition("operating_income", "usd", _metric_from_key("operating_income")),
    MetricDefinition("net_income", "usd", _metric_from_key("net_income")),
    MetricDefinition("free_cash_flow", "usd", _metric_from_key("free_cash_flow")),
    MetricDefinition("revenue_growth", "ratio", _revenue_growth),
    MetricDefinition("eps_growth", "ratio", _eps_growth),
    MetricDefinition("gross_margin", "ratio", _gross_margin),
    MetricDefinition("operating_margin", "ratio", _operating_margin),
    MetricDefinition("net_margin", "ratio", _net_margin),
    MetricDefinition("fcf_margin", "ratio", _fcf_margin),
    MetricDefinition("roic_proxy", "ratio", _roic_proxy),
    MetricDefinition("roe", "ratio", _roe),
    MetricDefinition("roa", "ratio", _roa),
    MetricDefinition("debt_to_equity", "ratio", _debt_to_equity),
    MetricDefinition("debt_to_assets", "ratio", _debt_to_assets),
    MetricDefinition("interest_coverage_proxy", "ratio", _interest_coverage_proxy),
    MetricDefinition("current_ratio", "ratio", _current_ratio),
    MetricDefinition("cash_ratio", "ratio", _cash_ratio),
    MetricDefinition("dilution_trend", "ratio", _dilution_trend),
    MetricDefinition("shares_cagr", "ratio", _shares_cagr),
    MetricDefinition("sbc_to_revenue", "ratio", _sbc_to_revenue),
    MetricDefinition("dividend_yield_proxy", "ratio", _dividend_yield_proxy),
    MetricDefinition("buyback_yield_proxy", "ratio", _buyback_yield_proxy),
    MetricDefinition("shareholder_yield", "ratio", _shareholder_yield),
    MetricDefinition("dso_days", "days", _dso),
    MetricDefinition("dio_days", "days", _dio),
    MetricDefinition("dpo_days", "days", _dpo),
    MetricDefinition("cash_conversion_cycle_days", "days", _ccc),
    MetricDefinition("accrual_ratio", "ratio", _accrual_ratio),
    MetricDefinition("cash_conversion_ratio", "ratio", _cash_conversion_ratio),
    MetricDefinition("segment_concentration", "ratio", _business_segment_concentration),
    MetricDefinition("geography_concentration", "ratio", _geography_segment_concentration),
    MetricDefinition("net_interest_margin", "ratio", _net_interest_margin_metric),
    MetricDefinition("provision_burden", "ratio", _provision_burden),
    MetricDefinition("asset_quality_ratio", "ratio", _asset_quality_ratio),
    MetricDefinition("cet1_ratio", "ratio", _cet1_ratio),
    MetricDefinition("tier1_capital_ratio", "ratio", _tier1_capital_ratio),
    MetricDefinition("total_capital_ratio", "ratio", _total_capital_ratio),
    MetricDefinition("core_deposit_ratio", "ratio", _core_deposit_ratio),
    MetricDefinition("uninsured_deposit_ratio", "ratio", _uninsured_deposit_ratio),
    MetricDefinition("tangible_book_value_per_share", "usd_per_share", _tangible_book_value_per_share),
    MetricDefinition("roatce", "ratio", _roatce),
    MetricDefinition("filing_lag_days", "days", _compute_filing_lag_days),
    MetricDefinition("stale_period_flag", "flag", _compute_stale_period_flag),
    MetricDefinition(
        "restatement_flag",
        "flag",
        lambda context: (1.0 if "restatement_detected" in context.current.get("quality_flags", []) else 0.0, True, []),
    ),
)


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
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


def _first_non_null(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None
