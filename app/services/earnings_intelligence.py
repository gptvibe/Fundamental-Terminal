from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, EarningsModelPoint, EarningsRelease, FinancialStatement, PriceHistory
from app.services.refresh_state import build_payload_version_hash, mark_dataset_checked
from app.services.sec_sic import resolve_sec_sic_profile

QUARTERLY_FORMS = {"10-Q", "6-K"}
ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
MODEL_VERSION = "sec_earnings_intel_v1"
EARNINGS_MODEL_PAYLOAD_VERSION = "earnings-models-v1"
SEGMENT_ALERT_THRESHOLD = 0.08
QUALITY_MID_THRESHOLD = 45.0
QUALITY_HIGH_THRESHOLD = 65.0

_CANONICAL_TAG_HINTS: dict[str, list[str]] = {
    "revenue": [
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "us-gaap:Revenues",
        "ifrs-full:Revenue",
    ],
    "net_income": ["us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss", "ifrs-full:ProfitLoss"],
    "operating_cash_flow": [
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "ifrs-full:CashFlowsFromUsedInOperatingActivities",
    ],
    "free_cash_flow": ["derived:operating_cash_flow_minus_capex"],
    "total_assets": ["us-gaap:Assets", "ifrs-full:Assets"],
}

_TAG_HINTS: dict[str, list[str]] = {
    "eps": ["us-gaap:EarningsPerShareDiluted", "ifrs-full:BasicEarningsLossPerShare"],
    "segment_breakdown": [
        "us-gaap:StatementBusinessSegmentsAxis",
        "us-gaap:StatementGeographicalAxis",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    ],
}


def recompute_and_persist_company_earnings_model_points(
    session: Session,
    company_id: int,
    *,
    checked_at: datetime | None = None,
    payload_version_hash: str | None = None,
) -> int:
    financials = list(
        session.execute(
            select(FinancialStatement).where(
                FinancialStatement.company_id == company_id,
                FinancialStatement.statement_type == "canonical_xbrl",
            )
        ).scalars()
    )
    releases = list(
        session.execute(select(EarningsRelease).where(EarningsRelease.company_id == company_id)).scalars()
    )
    points = build_earnings_model_points(financials, releases)
    effective_payload_version_hash = payload_version_hash or build_payload_version_hash(
        version=EARNINGS_MODEL_PAYLOAD_VERSION,
        payload=points,
    )

    session.execute(delete(EarningsModelPoint).where(EarningsModelPoint.company_id == company_id))
    if not points:
        timestamp = checked_at or datetime.now(timezone.utc)
        mark_dataset_checked(
            session,
            company_id,
            "earnings_models",
            checked_at=timestamp,
            success=True,
            payload_version_hash=effective_payload_version_hash,
            invalidate_hot_cache=True,
        )
        return 0

    timestamp = checked_at or datetime.now(timezone.utc)
    payloads = []
    for point in points:
        payloads.append(
            {
                "company_id": company_id,
                "period_start": point["period_start"],
                "period_end": point["period_end"],
                "filing_type": point["filing_type"],
                "quality_score": point["quality_score"],
                "quality_score_delta": point["quality_score_delta"],
                "eps_drift": point["eps_drift"],
                "earnings_momentum_drift": point["earnings_momentum_drift"],
                "segment_contribution_delta": point["segment_contribution_delta"],
                "release_statement_coverage_ratio": point["release_statement_coverage_ratio"],
                "fallback_ratio": point["fallback_ratio"],
                "stale_period_warning": point["stale_period_warning"],
                "explainability": point["explainability"],
                "quality_flags": point["quality_flags"],
                "source_statement_ids": point["source_statement_ids"],
                "source_release_ids": point["source_release_ids"],
                "last_updated": timestamp,
                "last_checked": timestamp,
            }
        )

    statement = insert(EarningsModelPoint).values(payloads)
    statement = statement.on_conflict_do_update(
        constraint="uq_earnings_model_points_company_period",
        set_={
            "period_start": statement.excluded.period_start,
            "filing_type": statement.excluded.filing_type,
            "quality_score": statement.excluded.quality_score,
            "quality_score_delta": statement.excluded.quality_score_delta,
            "eps_drift": statement.excluded.eps_drift,
            "earnings_momentum_drift": statement.excluded.earnings_momentum_drift,
            "segment_contribution_delta": statement.excluded.segment_contribution_delta,
            "release_statement_coverage_ratio": statement.excluded.release_statement_coverage_ratio,
            "fallback_ratio": statement.excluded.fallback_ratio,
            "stale_period_warning": statement.excluded.stale_period_warning,
            "explainability": statement.excluded.explainability,
            "quality_flags": statement.excluded.quality_flags,
            "source_statement_ids": statement.excluded.source_statement_ids,
            "source_release_ids": statement.excluded.source_release_ids,
            "last_updated": statement.excluded.last_updated,
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    mark_dataset_checked(
        session,
        company_id,
        "earnings_models",
        checked_at=timestamp,
        success=True,
        payload_version_hash=effective_payload_version_hash,
        invalidate_hot_cache=True,
    )
    return len(payloads)


def build_earnings_model_points(
    financials: list[FinancialStatement],
    releases: list[EarningsRelease],
    *,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    normalized = _normalize_financial_rows(financials)
    quarterly_rows = [row for row in normalized if row["filing_type"] in QUARTERLY_FORMS]
    annual_rows = [row for row in normalized if row["filing_type"] in ANNUAL_FORMS]
    source_rows = quarterly_rows if len(quarterly_rows) >= 2 else annual_rows
    if len(source_rows) < 2:
        return []

    release_periods_by_cutoff = _build_release_coverage_index(releases)
    output: list[dict[str, Any]] = []
    previous_eps_drift: float | None = None
    period_count = 0

    today = as_of_date or date.today()
    for index, row in enumerate(source_rows):
        previous = source_rows[index - 1] if index > 0 else None
        period_count += 1

        inputs: list[dict[str, Any]] = []
        quality_flags: list[str] = []
        proxy_used = 0
        input_count = 0

        revenue = _num(row, "revenue")
        net_income = _num(row, "net_income")
        operating_cash_flow = _num(row, "operating_cash_flow")
        free_cash_flow = _num(row, "free_cash_flow")
        eps = _num(row, "eps")
        total_assets = _num(row, "total_assets")

        fcf_margin, fcf_margin_proxy = _safe_ratio_with_proxy(
            numerator=free_cash_flow,
            denominator=revenue,
            proxy_numerator=operating_cash_flow,
            proxy_label="operating_cash_flow_proxy",
        )
        if fcf_margin is not None:
            input_count += 1
            proxy_used += 1 if fcf_margin_proxy else 0
        else:
            quality_flags.append("fcf_margin_missing")

        cash_conversion, cash_conversion_proxy = _safe_ratio_with_proxy(
            numerator=operating_cash_flow,
            denominator=net_income,
            proxy_numerator=free_cash_flow,
            proxy_label="free_cash_flow_proxy",
        )
        if cash_conversion is not None:
            input_count += 1
            proxy_used += 1 if cash_conversion_proxy else 0
        else:
            quality_flags.append("cash_conversion_missing")

        accrual_ratio, accrual_proxy = _accrual_ratio(net_income, operating_cash_flow, total_assets, revenue)
        if accrual_ratio is not None:
            input_count += 1
            proxy_used += 1 if accrual_proxy else 0
        else:
            quality_flags.append("accrual_ratio_missing")

        quality_score = _compute_quality_score(fcf_margin, cash_conversion, accrual_ratio)
        prev_quality_score = output[index - 1]["quality_score"] if index > 0 else None
        quality_score_delta = (quality_score - prev_quality_score) if quality_score is not None and prev_quality_score is not None else None

        previous_eps = _num(previous, "eps") if previous else None
        eps_drift = (eps - previous_eps) if eps is not None and previous_eps is not None else None
        if eps_drift is None:
            quality_flags.append("eps_drift_missing")

        earnings_momentum_drift = (
            eps_drift - previous_eps_drift
            if eps_drift is not None and previous_eps_drift is not None
            else None
        )
        if eps_drift is not None:
            previous_eps_drift = eps_drift

        segment_delta, segment_rows = _segment_contribution_delta(row, previous)
        if segment_delta is None:
            quality_flags.append("segment_delta_missing")

        covered_release_ids, coverage_ratio = _release_statement_coverage_ratio(
            release_periods_by_cutoff,
            cutoff=row["period_end"],
            period_count=period_count,
        )

        stale_days = 130 if row["filing_type"] in QUARTERLY_FORMS else 410
        stale_period_warning = (today - row["period_end"]).days > stale_days
        if stale_period_warning:
            quality_flags.append("stale_period")

        fallback_ratio = (proxy_used / input_count) if input_count else None

        inputs.extend(
            [
                _explain_input("revenue", revenue, row["period_end"]),
                _explain_input("net_income", net_income, row["period_end"]),
                _explain_input("operating_cash_flow", operating_cash_flow, row["period_end"]),
                _explain_input("free_cash_flow", free_cash_flow, row["period_end"]),
                _explain_input("eps", eps, row["period_end"]),
                _explain_input("total_assets", total_assets, row["period_end"]),
            ]
        )

        output.append(
            {
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "filing_type": row["filing_type"],
                "quality_score": quality_score,
                "quality_score_delta": quality_score_delta,
                "eps_drift": eps_drift,
                "earnings_momentum_drift": earnings_momentum_drift,
                "segment_contribution_delta": segment_delta,
                "release_statement_coverage_ratio": coverage_ratio,
                "fallback_ratio": fallback_ratio,
                "stale_period_warning": stale_period_warning,
                "quality_flags": sorted(set(quality_flags)),
                "source_statement_ids": row["statement_ids"],
                "source_release_ids": covered_release_ids,
                "explainability": {
                    "formula_version": MODEL_VERSION,
                    "period_end": row["period_end"].isoformat(),
                    "filing_type": row["filing_type"],
                    "inputs": [item for item in inputs if item["value"] is not None],
                    "component_values": {
                        "fcf_margin": fcf_margin,
                        "cash_conversion": cash_conversion,
                        "accrual_ratio": accrual_ratio,
                    },
                    "proxy_usage": {
                        "fcf_margin_proxy": fcf_margin_proxy,
                        "cash_conversion_proxy": cash_conversion_proxy,
                        "accrual_ratio_proxy": accrual_proxy,
                    },
                    "segment_deltas": segment_rows,
                    "release_statement_coverage": {
                        "ratio": coverage_ratio,
                        "statement_period_count": period_count,
                        "covered_release_count": len(covered_release_ids),
                    },
                    "quality_formula": "mean(scale(fcf_margin,-0.08,0.20), scale(cash_conversion,0.5,1.5), inverse_scale(accrual_ratio,0,0.18)) * 100",
                    "eps_drift_formula": "current_diluted_eps - previous_diluted_eps",
                    "momentum_formula": "current_eps_drift - previous_eps_drift",
                },
            }
        )

    return output


def build_earnings_directional_backtest(
    points: list[EarningsModelPoint],
    releases: list[EarningsRelease],
    prices: list[PriceHistory],
    *,
    post_sessions: int = 3,
) -> dict[str, Any]:
    model_by_period = {point.period_end: point for point in points}
    ordered_points = sorted(points, key=lambda item: item.period_end)
    period_list = [item.period_end for item in ordered_points]
    price_rows = sorted(prices, key=lambda item: item.trade_date)

    windows: list[dict[str, Any]] = []
    quality_total = 0
    quality_consistent = 0
    eps_total = 0
    eps_consistent = 0

    for release in sorted(releases, key=lambda item: (item.filing_date or date.min, item.id)):
        if release.filing_date is None:
            continue

        model_point = None
        if release.reported_period_end in model_by_period:
            model_point = model_by_period[release.reported_period_end]
        elif release.reported_period_end is not None and period_list:
            index = bisect_right(period_list, release.reported_period_end)
            if index > 0:
                model_point = ordered_points[index - 1]
        elif period_list:
            model_point = ordered_points[-1]

        if model_point is None:
            continue

        pre_price = _price_on_or_before(price_rows, release.filing_date)
        post_price = _price_after_sessions(price_rows, release.filing_date, post_sessions)
        if pre_price is None or post_price is None or pre_price.close == 0:
            continue

        return_window = (post_price.close - pre_price.close) / pre_price.close

        quality_signal = _signal(model_point.quality_score_delta)
        eps_signal = _signal(model_point.eps_drift)
        quality_consistency = None
        eps_consistency = None

        if quality_signal != 0:
            quality_total += 1
            quality_consistency = _signal(return_window) == quality_signal
            if quality_consistency:
                quality_consistent += 1

        if eps_signal != 0:
            eps_total += 1
            eps_consistency = _signal(return_window) == eps_signal
            if eps_consistency:
                eps_consistent += 1

        windows.append(
            {
                "accession_number": release.accession_number,
                "filing_date": release.filing_date,
                "reported_period_end": release.reported_period_end,
                "pre_price": pre_price.close,
                "post_price": post_price.close,
                "price_return": return_window,
                "quality_score_delta": model_point.quality_score_delta,
                "eps_drift": model_point.eps_drift,
                "quality_directional_consistent": quality_consistency,
                "eps_directional_consistent": eps_consistency,
                "price_source": pre_price.source,
            }
        )

    return {
        "window_sessions": post_sessions,
        "quality_directional_consistency": _safe_ratio(quality_consistent, quality_total),
        "quality_total_windows": quality_total,
        "quality_consistent_windows": quality_consistent,
        "eps_directional_consistency": _safe_ratio(eps_consistent, eps_total),
        "eps_total_windows": eps_total,
        "eps_consistent_windows": eps_consistent,
        "windows": windows,
    }


def build_earnings_peer_percentiles(
    session: Session,
    company: Company,
    latest_point: EarningsModelPoint | None,
) -> dict[str, Any]:
    if latest_point is None:
        return {
            "peer_group_basis": "market_sector",
            "peer_group_size": 0,
            "quality_percentile": None,
            "eps_drift_percentile": None,
            "sector_group_size": 0,
            "sector_quality_percentile": None,
            "sector_eps_drift_percentile": None,
        }

    market_sector, market_industry = _company_market_classification(company)
    sector_values = _latest_peer_metric_values(session, company, basis="market_sector")
    industry_values = _latest_peer_metric_values(session, company, basis="market_industry")
    use_industry = bool(market_industry and len(industry_values["quality"]) >= 4)
    peer_basis = "market_industry" if use_industry else "market_sector"
    peer_values = industry_values if use_industry else sector_values

    return {
        "peer_group_basis": peer_basis,
        "peer_group_size": len(peer_values["quality"]),
        "quality_percentile": _percentile_rank(peer_values["quality"], latest_point.quality_score),
        "eps_drift_percentile": _percentile_rank(peer_values["eps_drift"], latest_point.eps_drift),
        "sector_group_size": len(sector_values["quality"]),
        "sector_quality_percentile": _percentile_rank(sector_values["quality"], latest_point.quality_score),
        "sector_eps_drift_percentile": _percentile_rank(sector_values["eps_drift"], latest_point.eps_drift),
    }


def build_sector_alert_profile(session: Session, company: Company) -> dict[str, float]:
    profile = {
        "quality_mid_threshold": QUALITY_MID_THRESHOLD,
        "quality_high_threshold": QUALITY_HIGH_THRESHOLD,
        "segment_change_threshold": SEGMENT_ALERT_THRESHOLD,
    }

    market_sector, _market_industry = _company_market_classification(company)
    if not market_sector:
        return profile

    if settings.strict_official_mode:
        latest_periods = (
            select(
                EarningsModelPoint.company_id.label("company_id"),
                func.max(EarningsModelPoint.period_end).label("period_end"),
            )
            .group_by(EarningsModelPoint.company_id)
            .subquery()
        )

        quality_statement = (
            select(Company, EarningsModelPoint.quality_score)
            .join(
                latest_periods,
                (latest_periods.c.company_id == EarningsModelPoint.company_id)
                & (latest_periods.c.period_end == EarningsModelPoint.period_end),
            )
            .join(Company, Company.id == EarningsModelPoint.company_id)
            .where(
                Company.id != company.id,
                EarningsModelPoint.quality_score.is_not(None),
            )
        )
        quality_values = [
            float(value)
            for peer_company, value in session.execute(quality_statement).all()
            if value is not None and _company_market_classification(peer_company)[0] == market_sector
        ]
        if len(quality_values) >= 8:
            profile["quality_mid_threshold"] = _percentile_value(quality_values, 0.40)
            profile["quality_high_threshold"] = max(
                profile["quality_mid_threshold"] + 5.0,
                _percentile_value(quality_values, 0.75),
            )

        segment_statement = (
            select(Company, func.abs(EarningsModelPoint.segment_contribution_delta))
            .join(Company, Company.id == EarningsModelPoint.company_id)
            .where(
                Company.id != company.id,
                EarningsModelPoint.segment_contribution_delta.is_not(None),
            )
        )
        segment_values = [
            float(value)
            for peer_company, value in session.execute(segment_statement).all()
            if value is not None and _company_market_classification(peer_company)[0] == market_sector
        ]
        if len(segment_values) >= 20:
            tuned = _percentile_value(segment_values, 0.80)
            profile["segment_change_threshold"] = max(0.04, min(0.20, tuned))
        return profile

    latest_periods = (
        select(
            EarningsModelPoint.company_id.label("company_id"),
            func.max(EarningsModelPoint.period_end).label("period_end"),
        )
        .group_by(EarningsModelPoint.company_id)
        .subquery()
    )

    quality_statement = (
        select(EarningsModelPoint.quality_score)
        .join(
            latest_periods,
            (latest_periods.c.company_id == EarningsModelPoint.company_id)
            & (latest_periods.c.period_end == EarningsModelPoint.period_end),
        )
        .join(Company, Company.id == EarningsModelPoint.company_id)
        .where(
            Company.id != company.id,
            Company.market_sector == market_sector,
            EarningsModelPoint.quality_score.is_not(None),
        )
    )
    quality_values = [float(value) for value in session.execute(quality_statement).scalars() if value is not None]
    if len(quality_values) >= 8:
        profile["quality_mid_threshold"] = _percentile_value(quality_values, 0.40)
        profile["quality_high_threshold"] = max(
            profile["quality_mid_threshold"] + 5.0,
            _percentile_value(quality_values, 0.75),
        )

    segment_statement = (
        select(func.abs(EarningsModelPoint.segment_contribution_delta))
        .join(Company, Company.id == EarningsModelPoint.company_id)
        .where(
            Company.id != company.id,
            Company.market_sector == market_sector,
            EarningsModelPoint.segment_contribution_delta.is_not(None),
        )
    )
    segment_values = [float(value) for value in session.execute(segment_statement).scalars() if value is not None]
    if len(segment_values) >= 20:
        tuned = _percentile_value(segment_values, 0.80)
        profile["segment_change_threshold"] = max(0.04, min(0.20, tuned))

    return profile


def build_earnings_alerts(
    points: list[EarningsModelPoint],
    *,
    profile: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    if len(points) < 2:
        return []

    active_profile = profile or {}
    quality_mid_threshold = float(active_profile.get("quality_mid_threshold", QUALITY_MID_THRESHOLD))
    quality_high_threshold = float(active_profile.get("quality_high_threshold", QUALITY_HIGH_THRESHOLD))
    segment_threshold = float(active_profile.get("segment_change_threshold", SEGMENT_ALERT_THRESHOLD))

    ordered = sorted(points, key=lambda item: item.period_end)
    alerts: list[dict[str, Any]] = []

    for index in range(1, len(ordered)):
        previous = ordered[index - 1]
        current = ordered[index]

        previous_regime = _quality_regime(
            previous.quality_score,
            mid_threshold=quality_mid_threshold,
            high_threshold=quality_high_threshold,
        )
        current_regime = _quality_regime(
            current.quality_score,
            mid_threshold=quality_mid_threshold,
            high_threshold=quality_high_threshold,
        )
        if previous_regime != current_regime:
            alerts.append(
                {
                    "id": f"quality-regime:{current.period_end.isoformat()}",
                    "type": "quality_regime_shift",
                    "level": "high",
                    "title": "Quality score regime shift",
                    "detail": (
                        f"Quality regime moved from {previous_regime} to "
                        f"{current_regime}."
                    ),
                    "period_end": current.period_end,
                }
            )

        if _signal(previous.eps_drift) != 0 and _signal(current.eps_drift) != 0 and _signal(previous.eps_drift) != _signal(current.eps_drift):
            alerts.append(
                {
                    "id": f"eps-sign-flip:{current.period_end.isoformat()}",
                    "type": "eps_drift_sign_flip",
                    "level": "medium",
                    "title": "EPS drift sign flip",
                    "detail": "EPS drift changed sign versus the previous reported period.",
                    "period_end": current.period_end,
                }
            )

        if current.segment_contribution_delta is not None and abs(current.segment_contribution_delta) >= segment_threshold:
            alerts.append(
                {
                    "id": f"segment-share:{current.period_end.isoformat()}",
                    "type": "segment_share_change",
                    "level": "medium",
                    "title": "Segment share change exceeded threshold",
                    "detail": (
                        f"Largest segment contribution change reached {current.segment_contribution_delta:.1%}, "
                        f"over the {segment_threshold:.1%} threshold."
                    ),
                    "period_end": current.period_end,
                }
            )

    return alerts[-12:]


def _normalize_financial_rows(financials: list[FinancialStatement]) -> list[dict[str, Any]]:
    grouped: dict[tuple[date, str], list[FinancialStatement]] = defaultdict(list)
    for statement in financials:
        grouped[(statement.period_end, statement.filing_type)].append(statement)

    rows: list[dict[str, Any]] = []
    for (_period_end, _filing_type), statements in grouped.items():
        sorted_rows = sorted(statements, key=lambda item: (item.last_updated, item.id))
        latest = sorted_rows[-1]
        rows.append(
            {
                "statement_ids": [row.id for row in sorted_rows],
                "period_start": latest.period_start,
                "period_end": latest.period_end,
                "filing_type": latest.filing_type,
                "data": dict(latest.data or {}),
            }
        )

    rows.sort(key=lambda item: item["period_end"])
    return rows


def _build_release_coverage_index(releases: list[EarningsRelease]) -> list[tuple[date, int]]:
    index: list[tuple[date, int]] = []
    seen_accessions: set[str] = set()
    for release in sorted(releases, key=lambda item: (item.reported_period_end or date.min, item.id)):
        if release.reported_period_end is None:
            continue
        if release.accession_number in seen_accessions:
            continue
        if release.revenue is None and release.diluted_eps is None:
            continue
        seen_accessions.add(release.accession_number)
        index.append((release.reported_period_end, release.id))
    return index


def _release_statement_coverage_ratio(
    coverage_index: list[tuple[date, int]],
    *,
    cutoff: date,
    period_count: int,
) -> tuple[list[int], float | None]:
    covered = [release_id for release_period, release_id in coverage_index if release_period <= cutoff]
    if period_count <= 0:
        return covered, None
    return covered, len(covered) / float(period_count)


def _segment_contribution_delta(
    row: dict[str, Any],
    previous: dict[str, Any] | None,
) -> tuple[float | None, list[dict[str, Any]]]:
    current_payload = row.get("data", {}).get("segment_breakdown")
    previous_payload = (previous or {}).get("data", {}).get("segment_breakdown")
    if not isinstance(current_payload, list) or not isinstance(previous_payload, list):
        return None, []

    current_map = _segment_share_map(current_payload)
    previous_map = _segment_share_map(previous_payload)
    if not current_map or not previous_map:
        return None, []

    rows: list[dict[str, Any]] = []
    for segment_id, current_data in current_map.items():
        previous_data = previous_map.get(segment_id)
        if previous_data is None:
            continue
        delta = current_data["share"] - previous_data["share"]
        rows.append(
            {
                "segment_id": segment_id,
                "segment_name": current_data["name"],
                "current_share": current_data["share"],
                "previous_share": previous_data["share"],
                "delta": delta,
            }
        )

    if not rows:
        return None, []

    rows.sort(key=lambda item: abs(float(item["delta"])), reverse=True)
    max_delta = float(rows[0]["delta"])
    return max_delta, rows[:10]


def _segment_share_map(payload: list[Any]) -> dict[str, dict[str, Any]]:
    rows = [item for item in payload if isinstance(item, dict) and item.get("revenue") is not None]
    if not rows:
        return {}

    total_revenue = sum(abs(float(item.get("revenue") or 0.0)) for item in rows)
    if total_revenue == 0:
        return {}

    output: dict[str, dict[str, Any]] = {}
    for item in rows:
        segment_id = str(item.get("segment_id") or item.get("segment_name") or "unknown")
        revenue = abs(float(item.get("revenue") or 0.0))
        share = float(item.get("share_of_revenue")) if item.get("share_of_revenue") is not None else revenue / total_revenue
        output[segment_id] = {
            "name": str(item.get("segment_name") or segment_id),
            "share": share,
        }
    return output


def _latest_peer_metric_values(session: Session, company: Company, *, basis: str) -> dict[str, list[float]]:
    market_sector, market_industry = _company_market_classification(company)
    if basis == "market_industry":
        value = market_industry
        filter_column = Company.market_industry
    else:
        value = market_sector
        filter_column = Company.market_sector

    if not value:
        return {"quality": [], "eps_drift": []}

    if settings.strict_official_mode:
        latest_periods = (
            select(
                EarningsModelPoint.company_id.label("company_id"),
                func.max(EarningsModelPoint.period_end).label("period_end"),
            )
            .group_by(EarningsModelPoint.company_id)
            .subquery()
        )

        statement = (
            select(Company, EarningsModelPoint.quality_score, EarningsModelPoint.eps_drift)
            .join(
                latest_periods,
                (latest_periods.c.company_id == EarningsModelPoint.company_id)
                & (latest_periods.c.period_end == EarningsModelPoint.period_end),
            )
            .join(Company, Company.id == EarningsModelPoint.company_id)
            .where(Company.id != company.id)
        )

        quality_values: list[float] = []
        eps_values: list[float] = []
        for peer_company, quality_score, eps_drift in session.execute(statement).all():
            peer_market_sector, peer_market_industry = _company_market_classification(peer_company)
            peer_value = peer_market_industry if basis == "market_industry" else peer_market_sector
            if peer_value != value:
                continue
            if quality_score is not None:
                quality_values.append(float(quality_score))
            if eps_drift is not None:
                eps_values.append(float(eps_drift))

        return {"quality": quality_values, "eps_drift": eps_values}

    latest_periods = (
        select(
            EarningsModelPoint.company_id.label("company_id"),
            func.max(EarningsModelPoint.period_end).label("period_end"),
        )
        .group_by(EarningsModelPoint.company_id)
        .subquery()
    )

    statement = (
        select(EarningsModelPoint.quality_score, EarningsModelPoint.eps_drift)
        .join(latest_periods, (latest_periods.c.company_id == EarningsModelPoint.company_id) & (latest_periods.c.period_end == EarningsModelPoint.period_end))
        .join(Company, Company.id == EarningsModelPoint.company_id)
        .where(
            Company.id != company.id,
            filter_column == value,
        )
    )

    quality_values: list[float] = []
    eps_values: list[float] = []
    for quality_score, eps_drift in session.execute(statement).all():
        if quality_score is not None:
            quality_values.append(float(quality_score))
        if eps_drift is not None:
            eps_values.append(float(eps_drift))

    return {"quality": quality_values, "eps_drift": eps_values}


def _company_market_classification(company: Company) -> tuple[str | None, str | None]:
    if not settings.strict_official_mode:
        return company.market_sector, company.market_industry
    profile = resolve_sec_sic_profile(None, company.sector)
    return profile.market_sector, profile.market_industry


def _price_on_or_before(prices: list[PriceHistory], trade_date: date) -> PriceHistory | None:
    if not prices:
        return None
    dates = [point.trade_date for point in prices]
    insertion = bisect_right(dates, trade_date)
    if insertion <= 0:
        return None
    return prices[insertion - 1]


def _price_after_sessions(prices: list[PriceHistory], trade_date: date, sessions: int) -> PriceHistory | None:
    if not prices:
        return None
    dates = [point.trade_date for point in prices]
    insertion = bisect_right(dates, trade_date)
    target = insertion + max(0, sessions - 1)
    if target >= len(prices):
        return None
    return prices[target]


def _num(row: dict[str, Any] | None, key: str) -> float | None:
    if row is None:
        return None
    data = row.get("data") or {}
    value = data.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _safe_ratio_with_proxy(
    *,
    numerator: float | None,
    denominator: float | None,
    proxy_numerator: float | None,
    proxy_label: str,
) -> tuple[float | None, bool]:
    if numerator is not None and denominator not in {None, 0}:
        return numerator / denominator, False
    if proxy_numerator is not None and denominator not in {None, 0}:
        _ = proxy_label
        return proxy_numerator / denominator, True
    return None, False


def _accrual_ratio(
    net_income: float | None,
    operating_cash_flow: float | None,
    total_assets: float | None,
    revenue: float | None,
) -> tuple[float | None, bool]:
    if net_income is None or operating_cash_flow is None:
        return None, False
    if total_assets not in {None, 0}:
        return abs(net_income - operating_cash_flow) / abs(total_assets), False
    if revenue not in {None, 0}:
        return abs(net_income - operating_cash_flow) / abs(revenue), True
    return None, False


def _compute_quality_score(
    fcf_margin: float | None,
    cash_conversion: float | None,
    accrual_ratio: float | None,
) -> float | None:
    components: list[float] = []
    if fcf_margin is not None:
        components.append(_scale_range(fcf_margin, -0.08, 0.20))
    if cash_conversion is not None:
        components.append(_scale_range(cash_conversion, 0.5, 1.5))
    if accrual_ratio is not None:
        components.append(_scale_inverse(accrual_ratio, 0.0, 0.18))
    if not components:
        return None
    return sum(components) / float(len(components)) * 100.0


def _scale_range(value: float, min_value: float, max_value: float) -> float:
    if max_value <= min_value:
        return 0.0
    scaled = (value - min_value) / (max_value - min_value)
    return max(0.0, min(1.0, scaled))


def _scale_inverse(value: float, best_value: float, worst_value: float) -> float:
    if worst_value <= best_value:
        return 0.0
    scaled = 1.0 - (value - best_value) / (worst_value - best_value)
    return max(0.0, min(1.0, scaled))


def _explain_input(field: str, value: float | None, period_end: date) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "period_end": period_end.isoformat(),
        "sec_tags": _tag_hints(field),
    }


def _tag_hints(field: str) -> list[str]:
    if field in _TAG_HINTS:
        return list(_TAG_HINTS[field])
    return list(_CANONICAL_TAG_HINTS.get(field, []))


def _quality_regime(
    value: float | None,
    *,
    mid_threshold: float = QUALITY_MID_THRESHOLD,
    high_threshold: float = QUALITY_HIGH_THRESHOLD,
) -> str:
    if value is None:
        return "unknown"
    if value >= high_threshold:
        return "high"
    if value >= mid_threshold:
        return "mid"
    return "low"


def _percentile_value(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    clamped = max(0.0, min(1.0, percentile))
    index = int(round((len(ordered) - 1) * clamped))
    return ordered[index]


def _percentile_rank(values: list[float], value: float | None) -> float | None:
    if value is None or not values:
        return None
    ordered = sorted(values)
    position = bisect_right(ordered, value)
    return position / float(len(ordered))


def _signal(value: float | None) -> int:
    if value is None:
        return 0
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / float(denominator)
