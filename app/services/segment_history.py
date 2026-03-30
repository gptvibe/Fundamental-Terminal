from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.services.segment_analysis import (
    _segment_margin,
    _segment_revenue,
    _segment_share,
    _segments_for_kind,
    _statement_total_revenue,
    _to_float,
)
from app.services.snapshot_history import build_snapshot_history_windows, statement_fiscal_year

SegmentKind = Literal["business", "geographic"]


@dataclass(slots=True, frozen=True)
class SegmentHistorySegmentRecord:
    segment_id: str
    segment_name: str
    axis_label: str | None
    kind: Literal["business", "geographic", "other"]
    revenue: float | None
    share_of_revenue: float | None
    operating_income: float | None


@dataclass(slots=True, frozen=True)
class SegmentHistoryStatementRecord:
    filing_type: str
    period_end: Any
    source: str | None
    last_checked: Any
    revenue: float | None
    operating_income: float | None
    segment_breakdown: tuple[SegmentHistorySegmentRecord, ...]


@dataclass(slots=True, frozen=True)
class SegmentHistoryPeriodResult:
    period_end: Any
    fiscal_year: int | None
    kind: SegmentKind
    segments: list[dict[str, Any]]
    comparability_flags: dict[str, bool]


@dataclass(slots=True, frozen=True)
class SegmentHistoryBuildResult:
    periods: list[SegmentHistoryPeriodResult]
    provenance_statements: list[SegmentHistoryStatementRecord]


def build_segment_history(
    financials: Sequence[Any],
    *,
    kind: SegmentKind = "business",
    years: int = 5,
) -> SegmentHistoryBuildResult:
    normalized = [_normalize_statement(statement) for statement in financials]
    windows = build_snapshot_history_windows(
        normalized,
        years=years,
        include_statement=lambda statement: bool(_segments_for_kind(statement, kind)),
        prefer_annual=True,
        normalized_period_key=statement_fiscal_year,
    )

    periods: list[SegmentHistoryPeriodResult] = []
    provenance_statements: list[SegmentHistoryStatementRecord] = []
    seen_statement_keys: set[tuple[Any, str]] = set()

    for window in windows:
        statement = window.statement
        previous_statement = window.previous_statement
        current_segments = sorted(
            _segments_for_kind(statement, kind),
            key=lambda segment: (_segment_revenue(segment) or 0.0, segment.segment_name),
            reverse=True,
        )
        previous_segments = _segments_for_kind(previous_statement, kind)
        total_revenue = _statement_total_revenue(statement, current_segments)
        current_axis = next((segment.axis_label for segment in current_segments if segment.axis_label), None)
        previous_axis = next((segment.axis_label for segment in previous_segments if segment.axis_label), None)
        current_segment_ids = {segment.segment_id for segment in current_segments}
        previous_segment_ids = {segment.segment_id for segment in previous_segments}
        operating_income_count = sum(1 for segment in current_segments if _to_float(segment.operating_income) is not None)

        periods.append(
            SegmentHistoryPeriodResult(
                period_end=statement.period_end,
                fiscal_year=statement_fiscal_year(statement),
                kind=kind,
                segments=[
                    {
                        "name": segment.segment_name,
                        "revenue": _segment_revenue(segment),
                        "operating_income": _to_float(segment.operating_income),
                        "operating_margin": _segment_margin(segment),
                        "share_of_revenue": _segment_share(segment, total_revenue),
                    }
                    for segment in current_segments
                ],
                comparability_flags={
                    "no_prior_comparable_disclosure": previous_statement is None,
                    "segment_axis_changed": bool(
                        previous_statement is not None
                        and current_axis
                        and previous_axis
                        and current_axis != previous_axis
                    ),
                    "partial_operating_income_disclosure": bool(
                        current_segments and operating_income_count < len(current_segments)
                    ),
                    "new_or_removed_segments": bool(
                        previous_statement is not None and current_segment_ids != previous_segment_ids
                    ),
                },
            )
        )

        for candidate in (statement, previous_statement):
            if candidate is None:
                continue
            statement_key = (candidate.period_end, candidate.filing_type)
            if statement_key in seen_statement_keys:
                continue
            seen_statement_keys.add(statement_key)
            provenance_statements.append(candidate)

    return SegmentHistoryBuildResult(periods=periods, provenance_statements=provenance_statements)


def _normalize_statement(statement: Any) -> SegmentHistoryStatementRecord:
    data = statement.data if isinstance(getattr(statement, "data", None), dict) else {}
    segment_items = getattr(statement, "segment_breakdown", None)
    if not isinstance(segment_items, Sequence) or isinstance(segment_items, (str, bytes, bytearray)):
        segment_items = data.get("segment_breakdown", [])

    return SegmentHistoryStatementRecord(
        filing_type=str(getattr(statement, "filing_type", "")),
        period_end=getattr(statement, "period_end", None),
        source=getattr(statement, "source", None),
        last_checked=getattr(statement, "last_checked", None),
        revenue=_to_float(getattr(statement, "revenue", data.get("revenue"))),
        operating_income=_to_float(getattr(statement, "operating_income", data.get("operating_income"))),
        segment_breakdown=tuple(
            segment
            for segment in (_normalize_segment(item) for item in segment_items)
            if segment is not None
        ),
    )


def _normalize_segment(payload: Any) -> SegmentHistorySegmentRecord | None:
    if isinstance(payload, dict):
        segment_id = payload.get("segment_id") or payload.get("segment_name")
        segment_name = payload.get("segment_name") or payload.get("segment_id")
        axis_label = payload.get("axis_label")
        kind = payload.get("kind")
        revenue = payload.get("revenue")
        share_of_revenue = payload.get("share_of_revenue")
        operating_income = payload.get("operating_income")
    else:
        segment_id = getattr(payload, "segment_id", None) or getattr(payload, "segment_name", None)
        segment_name = getattr(payload, "segment_name", None) or getattr(payload, "segment_id", None)
        axis_label = getattr(payload, "axis_label", None)
        kind = getattr(payload, "kind", None)
        revenue = getattr(payload, "revenue", None)
        share_of_revenue = getattr(payload, "share_of_revenue", None)
        operating_income = getattr(payload, "operating_income", None)

    if not segment_id or not segment_name:
        return None

    normalized_kind = kind if kind in {"business", "geographic", "other"} else "other"
    return SegmentHistorySegmentRecord(
        segment_id=str(segment_id),
        segment_name=str(segment_name),
        axis_label=str(axis_label) if axis_label else None,
        kind=normalized_kind,
        revenue=_to_float(revenue),
        share_of_revenue=_to_float(share_of_revenue),
        operating_income=_to_float(operating_income),
    )