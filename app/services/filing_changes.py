from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from typing import Any

from app.models import FinancialRestatement, FinancialStatement


CANONICAL_STATEMENT_TYPE = "canonical_xbrl"
COMPARABLE_FILING_TYPES = {"10-K", "10-Q", "20-F", "40-F", "6-K"}

_METRIC_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("revenue", "Revenue", "usd"),
    ("gross_profit", "Gross Profit", "usd"),
    ("operating_income", "Operating Income", "usd"),
    ("net_income", "Net Income", "usd"),
    ("operating_cash_flow", "Operating Cash Flow", "usd"),
    ("free_cash_flow", "Free Cash Flow", "usd"),
    ("eps", "EPS", "usd_per_share"),
)

_SHARE_COUNT_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("shares_outstanding", "Shares Outstanding", "shares"),
    ("weighted_average_diluted_shares", "Weighted Diluted Shares", "shares"),
)

_CAPITAL_STRUCTURE_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("cash_and_short_term_investments", "Cash and Short-Term Investments", "usd"),
    ("current_debt", "Current Debt", "usd"),
    ("long_term_debt", "Long-Term Debt", "usd"),
    ("lease_liabilities", "Lease Liabilities", "usd"),
    ("stockholders_equity", "Stockholders' Equity", "usd"),
    ("net_debt", "Net Debt", "usd"),
    ("debt_to_equity", "Debt to Equity", "ratio"),
)

_AMENDED_VALUE_LIMIT = 12


def build_changes_since_last_filing(
    financials: list[FinancialStatement],
    restatements: list[FinancialRestatement],
) -> dict[str, Any]:
    comparable = [
        statement
        for statement in financials
        if statement.statement_type == CANONICAL_STATEMENT_TYPE
        and statement.filing_type in COMPARABLE_FILING_TYPES
        and isinstance(statement.data, dict)
    ]
    ordered = sorted(comparable, key=_statement_sort_key, reverse=True)
    current = ordered[0] if ordered else None
    if current is None:
        return {
            "current_filing": None,
            "previous_filing": None,
            "summary": _empty_summary(),
            "metric_deltas": [],
            "new_risk_indicators": [],
            "segment_shifts": [],
            "share_count_changes": [],
            "capital_structure_changes": [],
            "amended_prior_values": [],
            "confidence_flags": ["current_filing_missing"],
        }

    comparable_chain = [statement for statement in ordered if statement.filing_type == current.filing_type]
    previous = comparable_chain[1] if len(comparable_chain) > 1 else None
    previous_reference = comparable_chain[2] if len(comparable_chain) > 2 else None

    metric_deltas = _build_metric_delta_group(current, previous, _METRIC_DEFINITIONS)
    share_count_changes = _build_metric_delta_group(current, previous, _SHARE_COUNT_DEFINITIONS)
    capital_structure_changes = _build_metric_delta_group(current, previous, _CAPITAL_STRUCTURE_DEFINITIONS)
    segment_shifts = _build_segment_shifts(current, previous)

    current_risk_indicators = _build_risk_indicators(current, previous)
    previous_risk_keys = {
        indicator["indicator_key"]
        for indicator in _build_risk_indicators(previous, previous_reference)
    }
    new_risk_indicators = [
        indicator
        for indicator in current_risk_indicators
        if indicator["indicator_key"] not in previous_risk_keys
    ]

    amended_prior_values = _build_amended_prior_values(previous, restatements)

    confidence_flags: set[str] = set()
    if previous is None:
        confidence_flags.add("previous_comparable_filing_missing")
    if not metric_deltas:
        confidence_flags.add("metric_delta_data_limited")
    if not segment_shifts:
        confidence_flags.add("segment_shift_data_unavailable")
    if amended_prior_values:
        confidence_flags.add("prior_values_amended")
    if any(indicator["severity"] == "high" for indicator in new_risk_indicators):
        confidence_flags.add("high_risk_indicator_added")
    if any(change["direction"] in {"added", "removed"} for change in segment_shifts):
        confidence_flags.add("segment_mix_reclassified")
    if current.filing_acceptance_at is None:
        confidence_flags.add("statement_acceptance_time_missing")

    return {
        "current_filing": _serialize_statement_reference(current),
        "previous_filing": _serialize_statement_reference(previous),
        "summary": {
            "filing_type": current.filing_type,
            "current_period_start": current.period_start,
            "current_period_end": current.period_end,
            "previous_period_start": previous.period_start if previous is not None else None,
            "previous_period_end": previous.period_end if previous is not None else None,
            "metric_delta_count": len(metric_deltas),
            "new_risk_indicator_count": len(new_risk_indicators),
            "segment_shift_count": len(segment_shifts),
            "share_count_change_count": len(share_count_changes),
            "capital_structure_change_count": len(capital_structure_changes),
            "amended_prior_value_count": len(amended_prior_values),
        },
        "metric_deltas": metric_deltas,
        "new_risk_indicators": new_risk_indicators,
        "segment_shifts": segment_shifts,
        "share_count_changes": share_count_changes,
        "capital_structure_changes": capital_structure_changes,
        "amended_prior_values": amended_prior_values,
        "confidence_flags": sorted(confidence_flags),
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "filing_type": None,
        "current_period_start": None,
        "current_period_end": None,
        "previous_period_start": None,
        "previous_period_end": None,
        "metric_delta_count": 0,
        "new_risk_indicator_count": 0,
        "segment_shift_count": 0,
        "share_count_change_count": 0,
        "capital_structure_change_count": 0,
        "amended_prior_value_count": 0,
    }


def _serialize_statement_reference(statement: FinancialStatement | None) -> dict[str, Any] | None:
    if statement is None:
        return None
    return {
        "accession_number": _extract_accession_number(statement.source),
        "filing_type": statement.filing_type,
        "statement_type": statement.statement_type,
        "period_start": statement.period_start,
        "period_end": statement.period_end,
        "source": statement.source,
        "last_updated": statement.last_updated,
        "last_checked": statement.last_checked,
        "filing_acceptance_at": getattr(statement, "filing_acceptance_at", None),
        "fetch_timestamp": getattr(statement, "fetch_timestamp", None),
    }


def _build_metric_delta_group(
    current: FinancialStatement,
    previous: FinancialStatement | None,
    definitions: tuple[tuple[str, str, str], ...],
) -> list[dict[str, Any]]:
    if previous is None:
        return []

    current_data = dict(current.data or {})
    previous_data = dict(previous.data or {})
    rows: list[dict[str, Any]] = []
    for metric_key, label, unit in definitions:
        current_value = _metric_value(metric_key, current_data)
        previous_value = _metric_value(metric_key, previous_data)
        if current_value is None and previous_value is None:
            continue
        if current_value == previous_value:
            continue
        rows.append(
            {
                "metric_key": metric_key,
                "label": label,
                "unit": unit,
                "previous_value": previous_value,
                "current_value": current_value,
                "delta": _numeric_delta(previous_value, current_value),
                "relative_change": _relative_change(previous_value, current_value),
                "direction": _change_direction(previous_value, current_value),
            }
        )

    rows.sort(
        key=lambda item: (_sort_magnitude(item.get("delta")), str(item.get("label") or "")),
        reverse=True,
    )
    return rows


def _build_segment_shifts(current: FinancialStatement, previous: FinancialStatement | None) -> list[dict[str, Any]]:
    if previous is None:
        return []

    current_segments = _segment_map(dict(current.data or {}).get("segment_breakdown"))
    previous_segments = _segment_map(dict(previous.data or {}).get("segment_breakdown"))
    if not current_segments and not previous_segments:
        return []

    rows: list[dict[str, Any]] = []
    for segment_id in sorted({*current_segments.keys(), *previous_segments.keys()}):
        current_segment = current_segments.get(segment_id)
        previous_segment = previous_segments.get(segment_id)
        current_revenue = current_segment.get("revenue") if current_segment else None
        previous_revenue = previous_segment.get("revenue") if previous_segment else None
        current_share = current_segment.get("share_of_revenue") if current_segment else None
        previous_share = previous_segment.get("share_of_revenue") if previous_segment else None
        if current_segment == previous_segment:
            continue
        rows.append(
            {
                "segment_id": segment_id,
                "segment_name": str((current_segment or previous_segment or {}).get("segment_name") or segment_id),
                "kind": _segment_kind((current_segment or previous_segment or {}).get("kind")),
                "current_revenue": current_revenue,
                "previous_revenue": previous_revenue,
                "revenue_delta": _numeric_delta(previous_revenue, current_revenue),
                "current_share_of_revenue": current_share,
                "previous_share_of_revenue": previous_share,
                "share_delta": _numeric_delta(previous_share, current_share),
                "direction": _change_direction(previous_share, current_share),
            }
        )

    rows.sort(
        key=lambda item: (
            _sort_magnitude(item.get("share_delta")),
            _sort_magnitude(item.get("revenue_delta")),
            str(item.get("segment_name") or ""),
        ),
        reverse=True,
    )
    return rows


def _build_risk_indicators(current: FinancialStatement | None, previous: FinancialStatement | None) -> list[dict[str, Any]]:
    if current is None:
        return []

    current_data = dict(current.data or {})
    previous_data = dict(previous.data or {}) if previous is not None else {}

    current_ratio = _safe_div(_to_float(current_data.get("current_assets")), _to_float(current_data.get("current_liabilities")))
    debt_to_equity = _safe_div(_total_debt(current_data), _to_float(current_data.get("stockholders_equity")))
    free_cash_flow = _to_float(current_data.get("free_cash_flow"))
    share_change = _relative_change(_shares_proxy(previous_data), _shares_proxy(current_data))
    operating_margin = _safe_div(_to_float(current_data.get("operating_income")), _to_float(current_data.get("revenue")))
    previous_operating_margin = _safe_div(_to_float(previous_data.get("operating_income")), _to_float(previous_data.get("revenue")))
    operating_margin_delta = _numeric_delta(previous_operating_margin, operating_margin)

    rows: list[dict[str, Any]] = []
    if current_ratio is not None and current_ratio < 1.25:
        rows.append(
            _risk_indicator(
                "liquidity_pressure",
                "Liquidity Pressure",
                "high" if current_ratio < 1.0 else "medium",
                "Current assets no longer cover short-term obligations with a comfortable buffer.",
                current_ratio,
                _safe_div(_to_float(previous_data.get("current_assets")), _to_float(previous_data.get("current_liabilities"))),
            )
        )
    if debt_to_equity is not None and debt_to_equity > 1.0:
        rows.append(
            _risk_indicator(
                "leverage_pressure",
                "Leverage Pressure",
                "high" if debt_to_equity > 1.5 else "medium",
                "Debt load is elevated relative to equity in the latest comparable filing.",
                debt_to_equity,
                _safe_div(_total_debt(previous_data), _to_float(previous_data.get("stockholders_equity"))),
            )
        )
    if free_cash_flow is not None and free_cash_flow < 0:
        previous_fcf = _to_float(previous_data.get("free_cash_flow"))
        rows.append(
            _risk_indicator(
                "negative_free_cash_flow",
                "Negative Free Cash Flow",
                "high" if previous_fcf is not None and previous_fcf >= 0 else "medium",
                "Cash generation turned negative or remained negative in the latest filing.",
                free_cash_flow,
                previous_fcf,
            )
        )
    if share_change is not None and share_change > 0.02:
        rows.append(
            _risk_indicator(
                "dilution_pressure",
                "Dilution Pressure",
                "high" if share_change > 0.05 else "medium",
                "Reported share count increased versus the prior comparable filing.",
                share_change,
                None,
            )
        )
    if operating_margin_delta is not None and operating_margin_delta < -0.03:
        rows.append(
            _risk_indicator(
                "margin_compression",
                "Operating Margin Compression",
                "high" if operating_margin_delta < -0.08 else "medium",
                "Operating profitability deteriorated materially relative to the prior comparable filing.",
                operating_margin,
                previous_operating_margin,
            )
        )
    rows.sort(key=lambda item: (0 if item["severity"] == "high" else 1, str(item["label"])))
    return rows


def _risk_indicator(
    indicator_key: str,
    label: str,
    severity: str,
    description: str,
    current_value: float | None,
    previous_value: float | None,
) -> dict[str, Any]:
    return {
        "indicator_key": indicator_key,
        "label": label,
        "severity": severity if severity in {"medium", "high"} else "medium",
        "description": description,
        "current_value": current_value,
        "previous_value": previous_value,
    }


def _build_amended_prior_values(
    previous: FinancialStatement | None,
    restatements: list[FinancialRestatement],
) -> list[dict[str, Any]]:
    if previous is None:
        return []

    matching_records = [
        record
        for record in restatements
        if record.filing_type == previous.filing_type
        and record.period_start == previous.period_start
        and record.period_end == previous.period_end
    ]
    if not matching_records:
        return []

    deduped: dict[str, dict[str, Any]] = {}
    for record in sorted(matching_records, key=_restatement_sort_key, reverse=True):
        for item in record.normalized_data_changes or []:
            if not isinstance(item, dict):
                continue
            metric_key = str(item.get("metric_key") or "")
            if not metric_key or metric_key in deduped:
                continue
            deduped[metric_key] = {
                "metric_key": metric_key,
                "label": _metric_label(metric_key),
                "previous_value": item.get("previous_value"),
                "amended_value": item.get("current_value"),
                "delta": item.get("delta"),
                "relative_change": item.get("relative_change"),
                "direction": _change_direction(item.get("previous_value"), item.get("current_value")),
                "accession_number": record.accession_number,
                "form": record.form,
                "detection_kind": record.detection_kind,
                "amended_at": record.filing_acceptance_at or _date_to_datetime(record.filing_date) or record.last_updated,
                "source": record.source,
                "confidence_severity": str((record.confidence_impact or {}).get("severity") or "low"),
                "confidence_flags": list((record.confidence_impact or {}).get("flags") or []),
            }
        for item in record.companyfacts_changes or []:
            if not isinstance(item, dict) or not item.get("value_changed"):
                continue
            metric_key = str(item.get("metric_key") or "")
            if not metric_key or metric_key in deduped:
                continue
            previous_fact = item.get("previous_fact") if isinstance(item.get("previous_fact"), dict) else {}
            current_fact = item.get("current_fact") if isinstance(item.get("current_fact"), dict) else {}
            previous_value = previous_fact.get("value")
            amended_value = current_fact.get("value")
            deduped[metric_key] = {
                "metric_key": metric_key,
                "label": _metric_label(metric_key),
                "previous_value": previous_value,
                "amended_value": amended_value,
                "delta": _numeric_delta(previous_value, amended_value),
                "relative_change": _relative_change(previous_value, amended_value),
                "direction": _change_direction(previous_value, amended_value),
                "accession_number": record.accession_number,
                "form": record.form,
                "detection_kind": record.detection_kind,
                "amended_at": record.filing_acceptance_at or _date_to_datetime(record.filing_date) or record.last_updated,
                "source": record.source,
                "confidence_severity": str((record.confidence_impact or {}).get("severity") or "low"),
                "confidence_flags": list((record.confidence_impact or {}).get("flags") or []),
            }

    rows = list(deduped.values())
    rows.sort(
        key=lambda item: (_date_sort_value(item.get("amended_at")), _sort_magnitude(item.get("delta"))),
        reverse=True,
    )
    return rows[:_AMENDED_VALUE_LIMIT]


def _statement_sort_key(statement: FinancialStatement) -> tuple[datetime, date, datetime, int]:
    return (
        _statement_effective_at(statement),
        statement.period_end,
        statement.last_updated,
        int(getattr(statement, "id", 0) or 0),
    )


def _statement_effective_at(statement: FinancialStatement) -> datetime:
    acceptance_at = getattr(statement, "filing_acceptance_at", None)
    if isinstance(acceptance_at, datetime):
        return _normalize_datetime(acceptance_at)
    return datetime.combine(statement.period_end, time.max, tzinfo=timezone.utc)


def _restatement_sort_key(record: FinancialRestatement) -> tuple[datetime, date, datetime, int]:
    amended_at = record.filing_acceptance_at or _date_to_datetime(record.filing_date) or record.last_updated
    return (
        _normalize_datetime(amended_at),
        record.period_end,
        record.last_updated,
        int(getattr(record, "id", 0) or 0),
    )


def _segment_map(payload: Any) -> dict[str, dict[str, Any]]:
    rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
    if not rows:
        return {}

    total_revenue = sum(abs(_to_float(item.get("revenue")) or 0.0) for item in rows)
    output: dict[str, dict[str, Any]] = {}
    for item in rows:
        segment_id = str(item.get("segment_id") or item.get("segment_name") or "unknown")
        revenue = _to_float(item.get("revenue"))
        share = _to_float(item.get("share_of_revenue"))
        if share is None and revenue is not None and total_revenue > 0:
            share = abs(revenue) / total_revenue
        output[segment_id] = {
            "segment_name": str(item.get("segment_name") or segment_id),
            "kind": _segment_kind(item.get("kind")),
            "revenue": revenue,
            "share_of_revenue": share,
        }
    return output


def _segment_kind(value: Any) -> str:
    kind = str(value or "other")
    return kind if kind in {"business", "geographic", "other"} else "other"


def _metric_value(metric_key: str, data: dict[str, Any]) -> float | None:
    if metric_key == "cash_and_short_term_investments":
        return _cash_proxy(data)
    if metric_key == "net_debt":
        debt = _total_debt(data)
        cash = _cash_proxy(data)
        if debt is None and cash is None:
            return None
        return _sum_non_null(debt, -cash if cash is not None else None)
    if metric_key == "debt_to_equity":
        return _safe_div(_total_debt(data), _to_float(data.get("stockholders_equity")))
    return _to_float(data.get(metric_key))


def _cash_proxy(data: dict[str, Any]) -> float | None:
    return _first_non_null(
        _to_float(data.get("cash_and_short_term_investments")),
        _to_float(data.get("cash_and_cash_equivalents")),
    )


def _shares_proxy(data: dict[str, Any]) -> float | None:
    return _first_non_null(
        _to_float(data.get("weighted_average_diluted_shares")),
        _to_float(data.get("shares_outstanding")),
    )


def _total_debt(data: dict[str, Any]) -> float | None:
    return _sum_non_null(_to_float(data.get("current_debt")), _to_float(data.get("long_term_debt")))


def _extract_accession_number(source_url: str | None) -> str | None:
    if not source_url:
        return None
    match = re.search(r"(\d{10}-\d{2}-\d{6})", str(source_url))
    if match:
        return match.group(1)
    match = re.search(r"accn=([0-9-]{20})", str(source_url))
    if match:
        return match.group(1)
    return None


def _metric_label(metric_key: str) -> str:
    for key, label, _unit in (*_METRIC_DEFINITIONS, *_SHARE_COUNT_DEFINITIONS, *_CAPITAL_STRUCTURE_DEFINITIONS):
        if key == metric_key:
            return label
    return metric_key.replace("_", " ").title()


def _numeric_delta(previous_value: Any, current_value: Any) -> float | None:
    previous_number = _to_float(previous_value)
    current_number = _to_float(current_value)
    if previous_number is None or current_number is None:
        return None
    return current_number - previous_number


def _relative_change(previous_value: Any, current_value: Any) -> float | None:
    previous_number = _to_float(previous_value)
    current_number = _to_float(current_value)
    if previous_number is None or current_number is None or previous_number == 0:
        return None
    return (current_number / previous_number) - 1.0


def _change_direction(previous_value: Any, current_value: Any) -> str:
    previous_number = _to_float(previous_value)
    current_number = _to_float(current_value)
    if previous_value is None and current_value is not None:
        return "added"
    if previous_value is not None and current_value is None:
        return "removed"
    if previous_number is not None and current_number is not None:
        if current_number > previous_number:
            return "increase"
        if current_number < previous_number:
            return "decrease"
    return "changed"


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _sum_non_null(*values: float | None) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers)


def _first_non_null(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _sort_magnitude(value: Any) -> float:
    number = _to_float(value)
    return abs(number) if number is not None else -1.0


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_to_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _date_sort_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if isinstance(value, date):
        return datetime.combine(value, time.max, tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)