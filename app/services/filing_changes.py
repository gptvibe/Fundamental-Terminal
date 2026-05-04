from __future__ import annotations

from difflib import SequenceMatcher
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
_HIGH_SIGNAL_CHANGE_LIMIT = 8
_TEXT_CHANGE_SIMILARITY_THRESHOLD = 0.88
_HIGH_IMPORTANCE_TAGS = {
    "liquidity",
    "covenant",
    "impairment",
    "material weakness",
    "ineffective",
    "non-reliance",
    "auditor_change",
    "revenue recognition",
    "contingencies",
    "convertible",
}
_MDNA_SIGNAL_TERMS = (
    "liquidity",
    "working capital",
    "demand",
    "margin",
    "pricing",
    "inventory",
    "backlog",
    "restructuring",
    "impairment",
    "covenant",
    "tariff",
)
_FOOTNOTE_RISK_TERMS = (
    "liquidity",
    "covenant",
    "convertible",
    "impairment",
    "litigation",
    "contingenc",
    "deferred revenue",
    "valuation allowance",
    "stock compensation",
    "share based compensation",
    "revenue recognition",
)
_COMMENT_LETTER_HIGH_SIGNAL_TERMS = (
    "revenue",
    "recognition",
    "non-gaap",
    "non gaap",
    "internal control",
    "material weakness",
    "segment",
    "tax",
)


def build_changes_since_last_filing(
    financials: list[FinancialStatement],
    restatements: list[FinancialRestatement],
    *,
    parsed_filings: list[FinancialStatement] | None = None,
    comment_letters: list[Any] | None = None,
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
            "high_signal_changes": [],
            "comment_letter_history": _empty_comment_letter_history(),
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
    parser_current, parser_previous = _select_parser_pair(parsed_filings or [], current, previous)
    high_signal_changes, parser_flags = _build_high_signal_changes(
        parser_current=parser_current,
        parser_previous=parser_previous,
        comment_letters=comment_letters or [],
        current_filing=current,
        previous_filing=previous,
    )
    comment_letter_history = _build_comment_letter_history(comment_letters or [], current, previous)

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
    confidence_flags.update(parser_flags)

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
            "high_signal_change_count": len(high_signal_changes),
            "comment_letter_count": int(comment_letter_history.get("letters_since_previous_filing") or 0),
        },
        "metric_deltas": metric_deltas,
        "new_risk_indicators": new_risk_indicators,
        "segment_shifts": segment_shifts,
        "share_count_changes": share_count_changes,
        "capital_structure_changes": capital_structure_changes,
        "amended_prior_values": amended_prior_values,
        "high_signal_changes": high_signal_changes,
        "comment_letter_history": comment_letter_history,
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
        "high_signal_change_count": 0,
        "comment_letter_count": 0,
    }


def _empty_comment_letter_history() -> dict[str, Any]:
    return {
        "total_letters": 0,
        "letters_since_previous_filing": 0,
        "latest_filing_date": None,
        "recent_letters": [],
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


def _select_parser_pair(
    parsed_filings: list[FinancialStatement],
    current: FinancialStatement,
    previous: FinancialStatement | None,
) -> tuple[FinancialStatement | None, FinancialStatement | None]:
    comparable = [
        statement
        for statement in parsed_filings
        if getattr(statement, "statement_type", None) == "filing_parser"
        and statement.filing_type == current.filing_type
        and isinstance(statement.data, dict)
    ]
    ordered = sorted(comparable, key=_statement_sort_key, reverse=True)
    current_match = next((item for item in ordered if item.period_end == current.period_end), ordered[0] if ordered else None)
    previous_match = None
    if previous is not None:
        previous_match = next((item for item in ordered if item.period_end == previous.period_end and item is not current_match), None)
    if previous_match is None and current_match is not None:
        previous_match = next((item for item in ordered if item is not current_match), None)
    return current_match, previous_match


def _build_high_signal_changes(
    *,
    parser_current: FinancialStatement | None,
    parser_previous: FinancialStatement | None,
    comment_letters: list[Any],
    current_filing: FinancialStatement,
    previous_filing: FinancialStatement | None,
) -> tuple[list[dict[str, Any]], set[str]]:
    rows: list[dict[str, Any]] = []
    flags: set[str] = set()

    if parser_current is None:
        flags.add("filing_parser_current_missing")
    if previous_filing is not None and parser_previous is None:
        flags.add("filing_parser_previous_missing")

    if parser_current is not None and parser_previous is not None:
        mdna_change = _build_mdna_change(parser_current, parser_previous)
        if mdna_change is not None:
            rows.append(mdna_change)
        rows.extend(_build_footnote_changes(parser_current, parser_previous))
        non_gaap_change = _build_non_gaap_change(parser_current, parser_previous)
        if non_gaap_change is not None:
            rows.append(non_gaap_change)
        controls_change = _build_controls_change(parser_current, parser_previous)
        if controls_change is not None:
            rows.append(controls_change)

    comment_change = _build_comment_letter_change(comment_letters, current_filing, previous_filing)
    if comment_change is not None:
        rows.append(comment_change)

    rows.sort(
        key=lambda item: (
            1 if item.get("importance") == "high" else 0,
            _date_sort_value(item.get("current_period_end") or item.get("previous_period_end")),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return rows[:_HIGH_SIGNAL_CHANGE_LIMIT], flags


def _build_mdna_change(current: FinancialStatement, previous: FinancialStatement) -> dict[str, Any] | None:
    current_section = _section_payload(current.data, "mdna")
    previous_section = _section_payload(previous.data, "mdna")
    if current_section is None or previous_section is None:
        return None
    current_text = str(current_section.get("text") or "")
    previous_text = str(previous_section.get("text") or "")
    if not _text_changed_materially(current_text, previous_text):
        return None
    current_terms = set(_matched_terms_from_text(current_text, _MDNA_SIGNAL_TERMS))
    previous_terms = set(_matched_terms_from_text(previous_text, _MDNA_SIGNAL_TERMS))
    added_terms = sorted(current_terms - previous_terms)
    tags = added_terms or sorted(current_terms)[:3]
    importance = "high" if any(term in _HIGH_IMPORTANCE_TAGS for term in tags) else "medium"
    summary = "MD&A tone shifted materially versus the prior comparable filing"
    if tags:
        summary = f"MD&A added emphasis on {', '.join(tags[:3])} versus the prior comparable filing."
    return _high_signal_change(
        change_key=f"mda-{current.period_end.isoformat()}",
        category="mda",
        importance=importance,
        title="MD&A discussion changed materially",
        summary=summary,
        why_it_matters="Management discussion is usually where operational pressure, liquidity strain, and demand changes show up before they are obvious in headline metrics.",
        signal_tags=tags,
        current=current,
        previous=previous,
        current_payload=current_section,
        previous_payload=previous_section,
        current_label="Latest MD&A excerpt",
        previous_label="Prior MD&A excerpt",
    )


def _build_footnote_changes(current: FinancialStatement, previous: FinancialStatement) -> list[dict[str, Any]]:
    current_notes = _footnote_map(current.data)
    previous_notes = _footnote_map(previous.data)
    rows: list[dict[str, Any]] = []
    for key in sorted(set(current_notes) | set(previous_notes)):
        current_note = current_notes.get(key)
        previous_note = previous_notes.get(key)
        current_text = str((current_note or {}).get("text") or "")
        previous_text = str((previous_note or {}).get("text") or "")
        if not current_text and not previous_text:
            continue
        if previous_note is not None and current_note is not None and not _text_changed_materially(current_text, previous_text):
            continue
        tags = sorted(set(_matched_terms_from_text(current_text, _FOOTNOTE_RISK_TERMS)) - set(_matched_terms_from_text(previous_text, _FOOTNOTE_RISK_TERMS)))
        label = str((current_note or previous_note or {}).get("label") or key.replace("_", " ").title())
        importance = "high" if key in {"debt", "revenue_recognition", "contingencies", "goodwill_intangibles"} or any(term in _HIGH_IMPORTANCE_TAGS for term in tags) else "medium"
        summary = f"{label} disclosure changed materially versus the prior comparable filing."
        if tags:
            summary = f"{label} disclosure added {', '.join(tags[:3])} language versus the prior comparable filing."
        rows.append(
            _high_signal_change(
                change_key=f"footnote-{key}-{current.period_end.isoformat()}",
                category="footnote",
                importance=importance,
                title=f"{label} footnote changed",
                summary=summary,
                why_it_matters=_footnote_why_it_matters(key),
                signal_tags=tags or [key],
                current=current,
                previous=previous,
                current_payload=current_note,
                previous_payload=previous_note,
                current_label=f"Latest {label} note",
                previous_label=f"Prior {label} note",
            )
        )
    return rows[:4]


def _build_non_gaap_change(current: FinancialStatement, previous: FinancialStatement) -> dict[str, Any] | None:
    current_payload = _dict_payload(current.data, "non_gaap")
    previous_payload = _dict_payload(previous.data, "non_gaap")
    current_mentions = int(current_payload.get("mention_count") or 0)
    previous_mentions = int(previous_payload.get("mention_count") or 0)
    current_recon = int(current_payload.get("reconciliation_mentions") or 0)
    previous_recon = int(previous_payload.get("reconciliation_mentions") or 0)
    if current_mentions == 0 and previous_mentions == 0:
        return None
    if current_mentions == previous_mentions and current_recon == previous_recon and set(current_payload.get("terms", [])) == set(previous_payload.get("terms", [])):
        return None
    importance = "high" if current_mentions >= 3 and current_recon == 0 else "medium"
    tags = [str(term) for term in current_payload.get("terms", []) if term][:3]
    summary = (
        f"Non-GAAP references moved from {previous_mentions} to {current_mentions}, and reconciliation language moved from {previous_recon} to {current_recon}."
    )
    return {
        "change_key": f"non-gaap-{current.period_end.isoformat()}",
        "category": "non_gaap",
        "importance": importance,
        "title": "Non-GAAP reliance changed",
        "summary": summary,
        "why_it_matters": "Heavier reliance on adjusted metrics, especially with weaker reconciliation language, can make period-to-period comparability worse.",
        "signal_tags": tags,
        "current_period_end": current.period_end,
        "previous_period_end": previous.period_end,
        "evidence": [
            item
            for item in [
                _evidence_payload("Latest non-GAAP excerpt", current_payload, current.filing_type, current.period_end),
                _evidence_payload("Prior non-GAAP excerpt", previous_payload, previous.filing_type, previous.period_end),
            ]
            if item is not None
        ],
    }


def _build_controls_change(current: FinancialStatement, previous: FinancialStatement) -> dict[str, Any] | None:
    current_payload = _dict_payload(current.data, "controls")
    previous_payload = _dict_payload(previous.data, "controls")
    current_control_terms = set(str(term) for term in current_payload.get("control_terms", []) if term)
    previous_control_terms = set(str(term) for term in previous_payload.get("control_terms", []) if term)
    current_auditors = set(str(term) for term in current_payload.get("auditor_names", []) if term)
    previous_auditors = set(str(term) for term in previous_payload.get("auditor_names", []) if term)
    auditor_changed = bool(current_auditors and previous_auditors and current_auditors != previous_auditors)
    new_material_weakness = bool(current_payload.get("material_weakness")) and not bool(previous_payload.get("material_weakness"))
    new_ineffective = bool(current_payload.get("ineffective_controls")) and not bool(previous_payload.get("ineffective_controls"))
    new_non_reliance = bool(current_payload.get("non_reliance")) and not bool(previous_payload.get("non_reliance"))
    added_terms = sorted(current_control_terms - previous_control_terms)
    if not any((auditor_changed, new_material_weakness, new_ineffective, new_non_reliance, added_terms)):
        return None
    tags = added_terms[:3]
    if auditor_changed:
        tags.append("auditor_change")
    importance = "high" if any((auditor_changed, new_material_weakness, new_ineffective, new_non_reliance)) else "medium"
    summary_parts: list[str] = []
    if auditor_changed:
        summary_parts.append("auditor references changed")
    if new_material_weakness:
        summary_parts.append("material weakness language appeared")
    if new_ineffective:
        summary_parts.append("ineffective controls language appeared")
    if new_non_reliance:
        summary_parts.append("non-reliance language appeared")
    if not summary_parts and tags:
        summary_parts.append(f"control language added {', '.join(tags[:3])}")
    return {
        "change_key": f"controls-{current.period_end.isoformat()}",
        "category": "controls",
        "importance": importance,
        "title": "Auditor or controls disclosure changed",
        "summary": "; ".join(summary_parts).capitalize() + ".",
        "why_it_matters": "Changes in auditor or controls language can change confidence in reported numbers even before a restatement happens.",
        "signal_tags": tags,
        "current_period_end": current.period_end,
        "previous_period_end": previous.period_end,
        "evidence": [
            item
            for item in [
                _evidence_payload("Latest controls excerpt", current_payload, current.filing_type, current.period_end),
                _evidence_payload("Prior controls excerpt", previous_payload, previous.filing_type, previous.period_end),
            ]
            if item is not None
        ],
    }


def _build_comment_letter_history(
    comment_letters: list[Any],
    current_filing: FinancialStatement,
    previous_filing: FinancialStatement | None,
) -> dict[str, Any]:
    if not comment_letters:
        return _empty_comment_letter_history()
    previous_cutoff = _effective_letter_date(previous_filing)
    current_cutoff = _effective_letter_date(current_filing)
    ordered = sorted(comment_letters, key=lambda item: (_date_sort_value(getattr(item, "filing_date", None)), str(getattr(item, "accession_number", ""))), reverse=True)
    recent_letters = []
    letters_since_previous = 0
    for item in ordered:
        filing_date = getattr(item, "filing_date", None)
        if filing_date is not None and filing_date >= previous_cutoff.date():
            letters_since_previous += 1
        recent_letters.append(
            {
                "accession_number": getattr(item, "accession_number", None),
                "filing_date": filing_date,
                "description": str(getattr(item, "description", "SEC correspondence") or "SEC correspondence"),
                "sec_url": str(getattr(item, "sec_url", "") or ""),
                "is_new_since_current_filing": bool(filing_date is not None and filing_date >= current_cutoff.date()),
                "acceptance_datetime": getattr(item, "acceptance_datetime", None),
                "document_url": str(getattr(item, "document_url", "") or "") or None,
                "document_format": str(getattr(item, "document_format", "") or "") or None,
                "correspondent_role": str(getattr(item, "correspondent_role", "") or "") or None,
                "document_kind": str(getattr(item, "document_kind", "") or "") or None,
                "thread_key": str(getattr(item, "thread_key", "") or "") or None,
                "review_sequence": str(getattr(item, "review_sequence", "") or "") or None,
                "topics": [str(topic) for topic in (getattr(item, "topics", None) or []) if str(topic).strip()],
                "has_document_text": bool(getattr(item, "document_text", None)),
                "document_text_excerpt": _comment_letter_excerpt(getattr(item, "document_text", None)),
            }
        )
    return {
        "total_letters": len(ordered),
        "letters_since_previous_filing": letters_since_previous,
        "latest_filing_date": getattr(ordered[0], "filing_date", None),
        "recent_letters": recent_letters[:5],
    }


def _comment_letter_excerpt(value: object, limit: int = 320) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped}..." if clipped else f"{text[:limit].strip()}..."


def _build_comment_letter_change(
    comment_letters: list[Any],
    current_filing: FinancialStatement,
    previous_filing: FinancialStatement | None,
) -> dict[str, Any] | None:
    history = _build_comment_letter_history(comment_letters, current_filing, previous_filing)
    if int(history.get("letters_since_previous_filing") or 0) <= 0:
        return None
    recent_letters = history.get("recent_letters") or []
    latest = recent_letters[0] if recent_letters else None
    description = str((latest or {}).get("description") or "Recent SEC correspondence is available.")
    importance = "high" if any(term in description.lower() for term in _COMMENT_LETTER_HIGH_SIGNAL_TERMS) else "medium"
    return {
        "change_key": f"comment-letter-{(latest or {}).get('accession_number') or current_filing.period_end.isoformat()}",
        "category": "comment_letter",
        "importance": importance,
        "title": "SEC comment-letter history updated",
        "summary": f"{history['letters_since_previous_filing']} correspondence filing(s) appeared since the prior comparable filing.",
        "why_it_matters": "SEC correspondence can highlight disclosure areas the regulator questioned, even when the reported numbers did not visibly change.",
        "signal_tags": ["comment_letter"],
        "current_period_end": current_filing.period_end,
        "previous_period_end": previous_filing.period_end if previous_filing is not None else None,
        "evidence": [
            {
                "label": "Latest SEC correspondence",
                "excerpt": description,
                "source": str((latest or {}).get("sec_url") or ""),
                "filing_type": "CORRESP",
                "period_end": (latest or {}).get("filing_date"),
            }
        ] if latest and (latest or {}).get("sec_url") else [],
    }


def _high_signal_change(
    *,
    change_key: str,
    category: str,
    importance: str,
    title: str,
    summary: str,
    why_it_matters: str,
    signal_tags: list[str],
    current: FinancialStatement,
    previous: FinancialStatement,
    current_payload: dict[str, Any] | None,
    previous_payload: dict[str, Any] | None,
    current_label: str,
    previous_label: str,
) -> dict[str, Any]:
    return {
        "change_key": change_key,
        "category": category,
        "importance": importance,
        "title": title,
        "summary": summary,
        "why_it_matters": why_it_matters,
        "signal_tags": signal_tags[:4],
        "current_period_end": current.period_end,
        "previous_period_end": previous.period_end,
        "evidence": [
            item
            for item in [
                _evidence_payload(current_label, current_payload, current.filing_type, current.period_end),
                _evidence_payload(previous_label, previous_payload, previous.filing_type, previous.period_end),
            ]
            if item is not None
        ],
    }


def _evidence_payload(label: str, payload: dict[str, Any] | None, filing_type: str, period_end: date) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    excerpt = str(payload.get("excerpt") or "").strip()
    source = str(payload.get("source") or "").strip()
    if not excerpt or not source:
        return None
    return {
        "label": label,
        "excerpt": excerpt,
        "source": source,
        "filing_type": filing_type,
        "period_end": period_end,
    }


def _section_payload(data: dict[str, Any], key: str) -> dict[str, Any] | None:
    payload = data.get(key)
    return payload if isinstance(payload, dict) else None


def _dict_payload(data: dict[str, Any], key: str) -> dict[str, Any]:
    payload = data.get(key)
    return payload if isinstance(payload, dict) else {}


def _footnote_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = data.get("footnotes")
    rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
    return {str(item.get("key") or item.get("label") or "unknown"): item for item in rows}


def _text_changed_materially(current_text: str, previous_text: str) -> bool:
    current_normalized = _normalize_text_blob(current_text)
    previous_normalized = _normalize_text_blob(previous_text)
    if not current_normalized or not previous_normalized:
        return bool(current_normalized or previous_normalized)
    similarity = SequenceMatcher(None, current_normalized, previous_normalized).ratio()
    if similarity < _TEXT_CHANGE_SIMILARITY_THRESHOLD:
        return True
    return abs(len(current_normalized) - len(previous_normalized)) > 600


def _normalize_text_blob(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _matched_terms_from_text(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = _normalize_text_blob(text)
    return sorted({term for term in terms if term in normalized})


def _footnote_why_it_matters(key: str) -> str:
    reasons = {
        "revenue_recognition": "Revenue-recognition note changes can alter how durable or repeatable the top line really is.",
        "debt": "Debt-note changes can signal refinancing pressure, convert dilution, or covenant risk before it is obvious in leverage ratios.",
        "stock_compensation": "Stock-compensation note changes can reshape the real cost of labor and future dilution.",
        "income_taxes": "Tax-footnote changes can materially affect earnings quality and cash taxes.",
        "goodwill_intangibles": "Goodwill and intangible-note changes often flag acquisition integration issues or impairment risk.",
        "contingencies": "Contingency-note changes can surface litigation or contractual exposures that are not obvious in headline numbers.",
        "segments": "Segment-note changes can reveal where the business mix is strengthening, weakening, or being reclassified.",
        "fair_value": "Fair-value note changes can shift how much of reported value depends on assumptions rather than observable markets.",
        "inventory": "Inventory-note changes can be an early warning for demand weakness, obsolescence, or margin pressure.",
    }
    return reasons.get(key, "Footnote changes can alter the economics behind the headline statements.")


def _effective_letter_date(statement: FinancialStatement | None) -> datetime:
    if statement is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return _statement_effective_at(statement)