from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol

from app.source_registry import infer_source_id

ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
SEGMENT_KINDS: tuple[Literal["business", "geographic"], ...] = ("business", "geographic")


class FinancialSegmentRecord(Protocol):
    segment_id: str
    segment_name: str
    axis_label: str | None
    kind: Literal["business", "geographic", "other"]
    revenue: Any
    share_of_revenue: Any
    operating_income: Any


class FinancialStatementRecord(Protocol):
    filing_type: str
    period_end: Any
    source: str | None
    last_checked: Any
    revenue: Any
    operating_income: Any
    segment_breakdown: Sequence[FinancialSegmentRecord]


def build_segment_analysis(financials: Sequence[FinancialStatementRecord]) -> dict[str, Any] | None:
    output = {kind: _build_segment_lens(financials, kind) for kind in SEGMENT_KINDS}
    if not any(output.values()):
        return None
    return output


def _build_segment_lens(
    financials: Sequence[FinancialStatementRecord],
    kind: Literal["business", "geographic"],
) -> dict[str, Any] | None:
    statements = _statements_for_kind(financials, kind)
    if not statements:
        return None

    latest = statements[0]
    previous = statements[1] if len(statements) > 1 else None
    latest_segments = _segments_for_kind(latest, kind)
    if len(latest_segments) < 2:
        return None

    previous_segments = _segments_for_kind(previous, kind) if previous is not None else []
    latest_total_revenue = _statement_total_revenue(latest, latest_segments)
    previous_total_revenue = _statement_total_revenue(previous, previous_segments) if previous is not None else None
    latest_total_operating_income = _statement_total_operating_income(latest, latest_segments)

    latest_map = {segment.segment_id: segment for segment in latest_segments}
    previous_map = {segment.segment_id: segment for segment in previous_segments}
    rows: list[dict[str, Any]] = []
    new_segments: list[str] = []
    removed_segments: list[str] = []

    for segment_id in sorted({*latest_map.keys(), *previous_map.keys()}):
        current = latest_map.get(segment_id)
        previous_segment = previous_map.get(segment_id)
        if current is None and previous_segment is None:
            continue

        status: Literal["existing", "new", "removed"] = "existing"
        if current is None:
            status = "removed"
            removed_segments.append(previous_segment.segment_name if previous_segment is not None else segment_id)
        elif previous_segment is None:
            status = "new"
            new_segments.append(current.segment_name)

        current_revenue = _segment_revenue(current)
        previous_revenue = _segment_revenue(previous_segment)
        current_share = _segment_share(current, latest_total_revenue, default_zero=current is None and previous_segment is not None)
        previous_share = _segment_share(previous_segment, previous_total_revenue, default_zero=previous_segment is None and current is not None)
        current_margin = _segment_margin(current)
        previous_margin = _segment_margin(previous_segment)
        row = {
            "segment_id": current.segment_id if current is not None else previous_segment.segment_id,
            "segment_name": current.segment_name if current is not None else previous_segment.segment_name,
            "kind": current.kind if current is not None else previous_segment.kind,
            "status": status,
            "current_revenue": current_revenue,
            "previous_revenue": previous_revenue,
            "revenue_delta": _delta(previous_revenue, current_revenue),
            "current_share_of_revenue": current_share,
            "previous_share_of_revenue": previous_share,
            "share_delta": _delta(previous_share, current_share),
            "operating_income": _to_float(current.operating_income) if current is not None else None,
            "operating_margin": current_margin,
            "previous_operating_margin": previous_margin,
            "operating_margin_delta": _delta(previous_margin, current_margin),
            "share_of_operating_income": _safe_div(
                _to_float(current.operating_income) if current is not None else None,
                latest_total_operating_income,
            ),
        }
        rows.append(row)

    rows.sort(
        key=lambda item: (
            abs(_to_float(item.get("share_delta")) or 0.0),
            abs(_to_float(item.get("revenue_delta")) or 0.0),
            str(item.get("segment_name") or ""),
        ),
        reverse=True,
    )

    concentration = _build_concentration(latest_segments, latest_total_revenue)
    disclosures = _build_disclosures(
        kind=kind,
        latest=latest,
        previous=previous,
        latest_segments=latest_segments,
        rows=rows,
        new_segments=new_segments,
        removed_segments=removed_segments,
        concentration=concentration,
    )
    confidence_flags = sorted({str(item["code"]) for item in disclosures})
    if previous is None:
        confidence_flags.append(f"no_prior_{kind}_comparison")
    if latest_total_revenue in (None, 0):
        confidence_flags.append(f"{kind}_share_of_revenue_unavailable")

    confidence_score = _confidence_score(
        kind=kind,
        latest_segments=latest_segments,
        previous=previous,
        disclosures=disclosures,
    )
    top_mix_movers = rows[:3]
    top_margin_contributors = [
        row
        for row in sorted(
            rows,
            key=lambda item: (
                abs(_to_float(item.get("share_of_operating_income")) or 0.0),
                abs(_to_float(item.get("operating_income")) or 0.0),
            ),
            reverse=True,
        )
        if row.get("operating_income") is not None
    ][:3]

    return {
        "kind": kind,
        "axis_label": next((segment.axis_label for segment in latest_segments if segment.axis_label), None),
        "as_of": latest.period_end,
        "last_refreshed_at": latest.last_checked,
        "provenance_sources": _provenance_sources(latest, previous),
        "confidence_score": confidence_score,
        "confidence_flags": sorted(set(confidence_flags)),
        "summary": _build_summary(kind, top_mix_movers, concentration, previous is not None),
        "top_mix_movers": top_mix_movers,
        "top_margin_contributors": top_margin_contributors,
        "concentration": concentration,
        "unusual_disclosures": disclosures,
    }


def _statements_for_kind(
    financials: Sequence[FinancialStatementRecord],
    kind: Literal["business", "geographic"],
) -> list[FinancialStatementRecord]:
    annual = [statement for statement in financials if statement.filing_type in ANNUAL_FORMS and _segments_for_kind(statement, kind)]
    if annual:
        return annual
    return [statement for statement in financials if _segments_for_kind(statement, kind)]


def _segments_for_kind(
    statement: FinancialStatementRecord | None,
    kind: Literal["business", "geographic"],
) -> list[FinancialSegmentRecord]:
    if statement is None:
        return []
    return [
        segment
        for segment in statement.segment_breakdown
        if segment.kind == kind and _segment_revenue(segment) not in (None, 0)
    ]


def _statement_total_revenue(statement: FinancialStatementRecord | None, segments: Sequence[FinancialSegmentRecord]) -> float | None:
    if statement is None:
        return None
    if (statement.revenue or 0) > 0:
        return float(statement.revenue)
    values = [_segment_revenue(segment) for segment in segments]
    numeric = [value for value in values if value not in (None, 0)]
    if not numeric:
        return None
    return sum(numeric)


def _statement_total_operating_income(statement: FinancialStatementRecord | None, segments: Sequence[FinancialSegmentRecord]) -> float | None:
    if statement is not None and _to_float(statement.operating_income) not in (None, 0):
        return _to_float(statement.operating_income)
    numeric = [_to_float(segment.operating_income) for segment in segments if _to_float(segment.operating_income) not in (None, 0)]
    if not numeric:
        return None
    return sum(numeric)


def _build_concentration(
    segments: Sequence[FinancialSegmentRecord],
    total_revenue: float | None,
) -> dict[str, Any]:
    ranked = []
    for segment in segments:
        share = _segment_share(segment, total_revenue)
        if share is None or share <= 0:
            continue
        ranked.append((segment, share))

    ranked.sort(key=lambda item: item[1], reverse=True)
    top_segment = ranked[0] if ranked else None
    top_two_share = sum(item[1] for item in ranked[:2]) if ranked else None
    hhi = sum(item[1] ** 2 for item in ranked) if ranked else None
    return {
        "segment_count": len(ranked),
        "top_segment_id": top_segment[0].segment_id if top_segment is not None else None,
        "top_segment_name": top_segment[0].segment_name if top_segment is not None else None,
        "top_segment_share": _rounded(top_segment[1]) if top_segment is not None else None,
        "top_two_share": _rounded(top_two_share),
        "hhi": _rounded(hhi),
    }


def _build_disclosures(
    *,
    kind: Literal["business", "geographic"],
    latest: FinancialStatementRecord,
    previous: FinancialStatementRecord | None,
    latest_segments: Sequence[FinancialSegmentRecord],
    rows: Sequence[dict[str, Any]],
    new_segments: Sequence[str],
    removed_segments: Sequence[str],
    concentration: dict[str, Any],
) -> list[dict[str, Any]]:
    disclosures: list[dict[str, Any]] = []
    if previous is None:
        disclosures.append(
            _disclosure(
                f"no_prior_{kind}_comparison",
                "No prior comparable disclosure",
                f"The latest {kind} mix has no prior comparable filing in cache, so share shifts are based on the latest disclosure only.",
                "info",
            )
        )

    current_axis = next((segment.axis_label for segment in latest_segments if segment.axis_label), None)
    previous_axis = next((segment.axis_label for segment in _segments_for_kind(previous, kind) if segment.axis_label), None)
    if previous is not None and current_axis and previous_axis and current_axis != previous_axis:
        disclosures.append(
            _disclosure(
                f"{kind}_axis_changed",
                "Disclosure axis changed",
                f"The issuer changed the {kind} reporting axis from {previous_axis} to {current_axis}, which can distort period-over-period mix comparisons.",
                "medium",
            )
        )

    if new_segments:
        disclosures.append(
            _disclosure(
                f"new_{kind}_segments",
                "New segments disclosed",
                f"Newly disclosed {kind} lines in the latest filing: {_format_name_list(new_segments)}.",
                "medium",
            )
        )
    if removed_segments:
        disclosures.append(
            _disclosure(
                f"removed_{kind}_segments",
                "Prior segments removed",
                f"Previously disclosed {kind} lines no longer appear: {_format_name_list(removed_segments)}.",
                "medium",
            )
        )

    margin_count = sum(1 for segment in latest_segments if _to_float(segment.operating_income) is not None)
    if kind == "business":
        if margin_count == 0:
            disclosures.append(
                _disclosure(
                    "business_margin_not_disclosed",
                    "Business segment margins missing",
                    "The latest business segment disclosure provides revenue mix but no segment operating income, limiting margin-contribution analysis.",
                    "medium",
                )
            )
        elif margin_count < len(latest_segments):
            disclosures.append(
                _disclosure(
                    "business_margin_partial",
                    "Business margin disclosure is partial",
                    "Only part of the latest business segment set includes operating income, so margin contribution is incomplete.",
                    "info",
                )
            )
    elif margin_count == 0:
        disclosures.append(
            _disclosure(
                "geographic_revenue_only",
                "Geographic disclosure is revenue-only",
                "The latest geographic disclosure reports revenue by region or country without segment margin detail.",
                "info",
            )
        )

    top_segment_share = _to_float(concentration.get("top_segment_share"))
    top_two_share = _to_float(concentration.get("top_two_share"))
    if top_segment_share is not None and top_segment_share >= 0.5:
        disclosures.append(
            _disclosure(
                f"{kind}_dominant_segment",
                "Mix is concentrated in one line",
                f"{concentration.get('top_segment_name') or 'The leading line'} accounts for {_format_percent(top_segment_share)} of the latest {kind} revenue mix.",
                "high" if top_segment_share >= 0.65 else "medium",
            )
        )
    elif top_two_share is not None and top_two_share >= 0.75:
        disclosures.append(
            _disclosure(
                f"{kind}_top_two_concentrated",
                "Top two lines dominate mix",
                f"The top two {kind} lines account for {_format_percent(top_two_share)} of the latest revenue mix.",
                "medium",
            )
        )

    if len(rows) <= 2:
        disclosures.append(
            _disclosure(
                f"limited_{kind}_breadth",
                "Limited disclosure breadth",
                f"Only {len(rows)} {kind} lines were disclosed in the latest comparable view.",
                "info",
            )
        )

    return disclosures


def _confidence_score(
    *,
    kind: Literal["business", "geographic"],
    latest_segments: Sequence[FinancialSegmentRecord],
    previous: FinancialStatementRecord | None,
    disclosures: Sequence[dict[str, Any]],
) -> float:
    score = 1.0
    if previous is None:
        score -= 0.2
    if len(latest_segments) < 3:
        score -= 0.1
    medium_count = sum(1 for disclosure in disclosures if disclosure.get("severity") == "medium")
    high_count = sum(1 for disclosure in disclosures if disclosure.get("severity") == "high")
    score -= medium_count * 0.08
    score -= high_count * 0.15
    if kind == "business" and not any(_to_float(segment.operating_income) is not None for segment in latest_segments):
        score -= 0.12
    return _rounded(max(0.35, min(1.0, score))) or 0.35


def _build_summary(
    kind: Literal["business", "geographic"],
    top_mix_movers: Sequence[dict[str, Any]],
    concentration: dict[str, Any],
    has_previous: bool,
) -> str | None:
    if not top_mix_movers:
        return None

    top_two_share = _to_float(concentration.get("top_two_share"))
    if has_previous:
        mover_text = ", ".join(
            f"{row['segment_name']} {_format_points(_to_float(row.get('share_delta')))}"
            for row in top_mix_movers[:2]
        )
        if top_two_share is not None:
            return f"Mix shifted most in {mover_text}; the top two {kind} lines now represent {_format_percent(top_two_share)} of revenue."
        return f"Mix shifted most in {mover_text}."

    lead_names = ", ".join(str(row.get("segment_name") or "Unknown") for row in top_mix_movers[:2])
    if top_two_share is not None:
        return f"Latest {kind} disclosure is led by {lead_names}; the top two lines represent {_format_percent(top_two_share)} of revenue."
    return f"Latest {kind} disclosure is led by {lead_names}."


def _provenance_sources(*statements: FinancialStatementRecord | None) -> list[str]:
    output: list[str] = []
    for statement in statements:
        if statement is None:
            continue
        source_id = infer_source_id(statement.source, default="sec_companyfacts")
        if source_id is not None and source_id not in output:
            output.append(source_id)
    if not output:
        output.append("sec_companyfacts")
    return output


def _segment_revenue(segment: FinancialSegmentRecord | None) -> float | None:
    if segment is None:
        return None
    return _to_float(segment.revenue)


def _segment_share(
    segment: FinancialSegmentRecord | None,
    total_revenue: float | None,
    *,
    default_zero: bool = False,
) -> float | None:
    if segment is None:
        return 0.0 if default_zero else None
    if _to_float(segment.share_of_revenue) is not None:
        return _to_float(segment.share_of_revenue)
    revenue = _segment_revenue(segment)
    share = _safe_div(revenue, total_revenue)
    if share is None and default_zero:
        return 0.0
    return share


def _segment_margin(segment: FinancialSegmentRecord | None) -> float | None:
    if segment is None:
        return None
    return _safe_div(_to_float(segment.operating_income), _segment_revenue(segment))


def _delta(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None:
        return None
    return _rounded(current - previous)


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return _rounded(numerator / denominator)


def _rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _disclosure(code: str, label: str, detail: str, severity: Literal["info", "medium", "high"]) -> dict[str, str]:
    return {
        "code": code,
        "label": label,
        "detail": detail,
        "severity": severity,
    }


def _format_name_list(names: Sequence[str]) -> str:
    trimmed = [str(name) for name in names if name][:3]
    if len(names) > len(trimmed):
        trimmed.append(f"+{len(names) - len(trimmed)} more")
    return ", ".join(trimmed) if trimmed else "n/a"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _format_points(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f} pts"
