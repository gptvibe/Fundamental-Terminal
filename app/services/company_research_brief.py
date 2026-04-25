from __future__ import annotations

from copy import deepcopy
from datetime import date as DateType, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.research_brief_contracts import (
    ActivityFeedEntryPayload,
    AlertPayload,
    AlertsSummaryPayload,
    BeneficialOwnershipFilingPayload,
    BeneficialOwnershipPartyPayload,
    BeneficialOwnershipSummaryPayload,
    CapitalMarketsSummaryPayload,
    CapitalRaisePayload,
    CapitalStructureCapitalReturnsPayload,
    CapitalStructureDebtMaturityPayload,
    CapitalStructureDebtRollforwardPayload,
    CapitalStructureInterestBurdenPayload,
    CapitalStructureLeaseObligationsPayload,
    CapitalStructureNetDilutionBridgePayload,
    CapitalStructureSnapshotPayload,
    CapitalStructureSummaryPayload,
    ChangesSinceLastFilingSummaryPayload,
    CompanyActivityOverviewResponse,
    CompanyBeneficialOwnershipSummaryResponse,
    CompanyCapitalMarketsSummaryResponse,
    CompanyCapitalStructureResponse,
    CompanyChangesSinceLastFilingResponse,
    CompanyGovernanceSummaryResponse,
    CompanyModelsResponse,
    CompanyPayload,
    CompanyPeersResponse,
    CompanyResearchBriefBusinessQualitySection,
    CompanyResearchBriefCapitalAndRiskSection,
    CompanyResearchBriefMonitorSection,
    CompanyResearchBriefResponse,
    CompanyResearchBriefSnapshotSection,
    CompanyResearchBriefValuationSection,
    CompanyResearchBriefWhatChangedSection,
    CompanyEarningsSummaryResponse,
    DataQualityDiagnosticsPayload,
    EarningsReleasePayload,
    EarningsSummaryPayload,
    GovernanceSummaryPayload,
    GovernanceVoteOutcomePayload,
    ModelPayload,
    PeerMetricsPayload,
    PeerOptionPayload,
    ProvenanceEntryPayload,
    RefreshState,
    ResearchBriefBusinessQualitySummaryPayload,
    ResearchBriefSnapshotSummaryPayload,
    SourceMixPayload,
)
from app.config import settings
from app.model_engine.output_normalization import standardize_model_result
from app.model_engine.utils import status_explanation
from app.models import Company, CompanyResearchBriefSnapshot, ModelRun
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix, infer_source_id
from app.services.cache_queries import (
    CompanyCacheSnapshot,
    filter_price_history_as_of,
    get_company_beneficial_ownership_reports,
    get_company_capital_markets_events,
    get_company_capital_structure_last_checked,
    get_company_capital_structure_snapshots,
    get_company_comment_letters,
    get_company_earnings_cache_status,
    get_company_earnings_releases,
    get_company_filing_events,
    get_company_filing_insights,
    get_company_financial_restatements,
    get_company_financials,
    get_company_form144_filings,
    get_company_insider_trades,
    get_company_institutional_holdings,
    get_company_models,
    get_company_price_cache_status,
    get_company_price_history,
    get_company_proxy_statements,
    get_company_snapshot,
    latest_price_as_of,
    select_point_in_time_financials,
)
from app.services.equity_claim_risk import build_company_equity_claim_risk_response
from app.services.filing_changes import build_changes_since_last_filing
from app.services.macro_persistence import read_global_macro_snapshot_with_meta
from app.services.oil_exposure import classify_oil_exposure
from app.services.peer_comparison import build_peer_comparison
from app.services.refresh_state import mark_dataset_checked
from app.services.sec_sic import resolve_sec_sic_profile


BRIEF_SCHEMA_VERSION = "company_research_brief_v1"
BRIEF_MODEL_NAMES = ["dcf", "reverse_dcf", "roic", "capital_allocation", "dupont", "piotroski", "altman_z", "ratios"]
ANNUAL_FILING_TYPES = {"10-K", "20-F", "40-F"}


def get_company_research_brief_snapshot(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None = None,
    schema_version: str = BRIEF_SCHEMA_VERSION,
) -> CompanyResearchBriefSnapshot | None:
    statement = select(CompanyResearchBriefSnapshot).where(
        CompanyResearchBriefSnapshot.company_id == company_id,
        CompanyResearchBriefSnapshot.as_of_key == _as_of_key(as_of),
        CompanyResearchBriefSnapshot.schema_version == schema_version,
    )
    return session.execute(statement).scalar_one_or_none()


def get_company_research_brief_snapshots(
    session: Session,
    company_ids: list[int],
    *,
    as_of: datetime | None = None,
    schema_version: str = BRIEF_SCHEMA_VERSION,
) -> dict[int, CompanyResearchBriefSnapshot | None]:
    normalized_ids = sorted({int(company_id) for company_id in company_ids})
    if not normalized_ids:
        return {}

    statement = select(CompanyResearchBriefSnapshot).where(
        CompanyResearchBriefSnapshot.company_id.in_(normalized_ids),
        CompanyResearchBriefSnapshot.as_of_key == _as_of_key(as_of),
        CompanyResearchBriefSnapshot.schema_version == schema_version,
    )
    rows = list(session.execute(statement).scalars())
    snapshots_by_company_id: dict[int, CompanyResearchBriefSnapshot | None] = {
        company_id: None for company_id in normalized_ids
    }
    for row in rows:
        snapshots_by_company_id[int(row.company_id)] = row
    return snapshots_by_company_id


def build_company_research_brief_response(
    session: Session,
    company_id: int,
    *,
    as_of: datetime | None = None,
    generated_at: datetime | None = None,
) -> CompanyResearchBriefResponse | None:
    company = session.get(Company, company_id)
    if company is None:
        return None

    snapshot = get_company_snapshot(session, company.ticker)
    if snapshot is None:
        return None

    timestamp = generated_at or datetime.now(timezone.utc)
    refresh = _refresh_state_for_snapshot(snapshot)
    company_payload = _serialize_company(snapshot)
    financials = get_company_financials(session, company_id)
    if as_of is not None:
        financials = select_point_in_time_financials(financials, as_of)
    annual_statements = [statement for statement in financials if statement.filing_type in ANNUAL_FILING_TYPES]
    latest_statement = financials[0] if financials else None
    previous_annual = annual_statements[1] if len(annual_statements) > 1 else None

    price_history = get_company_price_history(session, company_id)
    if as_of is not None:
        price_history = filter_price_history_as_of(price_history, as_of)
    price_last_checked, _price_cache_state = get_company_price_cache_status(session, company_id)

    activity_overview = _build_activity_overview_response(session, snapshot, refresh)
    changes_response = _build_changes_response(session, snapshot, financials, refresh, as_of)
    earnings_summary = _build_earnings_summary_response(session, snapshot, refresh)
    capital_structure = _build_capital_structure_response(session, snapshot, refresh, as_of)
    capital_markets_summary = _build_capital_markets_summary_response(session, snapshot, refresh)
    governance_summary = _build_governance_summary_response(session, snapshot, refresh)
    ownership_summary = _build_ownership_summary_response(session, snapshot, refresh)
    equity_claim_risk = build_company_equity_claim_risk_response(
        session,
        company_id,
        company=company_payload,
        refresh=refresh,
        as_of=as_of,
    )
    models_response = _build_models_response(session, snapshot, financials, refresh, price_last_checked)
    peers_response = _build_peers_response(session, snapshot, refresh, price_last_checked, as_of)

    snapshot_summary = ResearchBriefSnapshotSummaryPayload(
        latest_filing_type=latest_statement.filing_type if latest_statement is not None else None,
        latest_period_end=latest_statement.period_end if latest_statement is not None else None,
        annual_statement_count=len(annual_statements),
        price_history_points=len(price_history),
        latest_revenue=_statement_value(latest_statement, "revenue"),
        latest_free_cash_flow=_statement_value(latest_statement, "free_cash_flow"),
        top_segment_name=_top_segment_name(latest_statement),
        top_segment_share_of_revenue=_top_segment_share(latest_statement),
        alert_count=activity_overview.summary.total,
    )
    snapshot_section = CompanyResearchBriefSnapshotSection(
        summary=snapshot_summary,
        **_build_provenance_contract(
            [
                _source_usage_from_hint(getattr(latest_statement, "source", None), role="primary", as_of=latest_statement.period_end if latest_statement is not None else None, last_refreshed_at=getattr(latest_statement, "last_checked", None), default_source_id="sec_companyfacts"),
                _source_usage_from_hint("yahoo_finance", role="fallback", as_of=price_history[-1].trade_date if price_history else None, last_refreshed_at=price_last_checked, default_source_id="yahoo_finance") if price_history else None,
            ],
            as_of=_latest_as_of(snapshot_summary.latest_period_end, price_history[-1].trade_date if price_history else None),
            last_refreshed_at=_merge_last_checked(getattr(latest_statement, "last_checked", None), price_last_checked),
            confidence_flags=[*changes_response.confidence_flags[:1]],
        ),
    )

    business_quality_summary = ResearchBriefBusinessQualitySummaryPayload(
        latest_period_end=latest_statement.period_end if latest_statement is not None else None,
        previous_period_end=previous_annual.period_end if previous_annual is not None else None,
        annual_statement_count=len(annual_statements),
        revenue_growth=_growth_rate(_statement_value(latest_statement, "revenue"), _statement_value(previous_annual, "revenue")),
        operating_margin=_safe_divide(_statement_value(latest_statement, "operating_income"), _statement_value(latest_statement, "revenue")),
        free_cash_flow_margin=_safe_divide(_statement_value(latest_statement, "free_cash_flow"), _statement_value(latest_statement, "revenue")),
        share_dilution=_growth_rate(_statement_value(latest_statement, "weighted_average_shares_diluted"), _statement_value(previous_annual, "weighted_average_shares_diluted")),
    )
    business_quality_section = CompanyResearchBriefBusinessQualitySection(
        summary=business_quality_summary,
        **_build_provenance_contract(
            [
                _source_usage_from_hint(getattr(latest_statement, "source", None), role="primary", as_of=latest_statement.period_end if latest_statement is not None else None, last_refreshed_at=getattr(latest_statement, "last_checked", None), default_source_id="sec_companyfacts")
            ],
            as_of=business_quality_summary.latest_period_end,
            last_refreshed_at=getattr(latest_statement, "last_checked", None),
        ),
    )

    return CompanyResearchBriefResponse(
        company=company_payload,
        schema_version=BRIEF_SCHEMA_VERSION,
        generated_at=timestamp,
        as_of=_normalize_as_of(as_of),
        refresh=refresh,
        snapshot=snapshot_section,
        what_changed=CompanyResearchBriefWhatChangedSection(
            activity_overview=activity_overview,
            changes=changes_response,
            earnings_summary=earnings_summary,
            **_build_provenance_contract(
                [
                    SourceUsage(source_id="ft_company_research_brief", role="derived", as_of=changes_response.as_of, last_refreshed_at=timestamp),
                    SourceUsage(source_id="ft_activity_overview", role="derived", as_of=activity_overview.as_of, last_refreshed_at=activity_overview.last_refreshed_at),
                ],
                as_of=_latest_as_of(changes_response.as_of, activity_overview.as_of),
                last_refreshed_at=_merge_last_checked(activity_overview.last_refreshed_at, changes_response.last_refreshed_at, timestamp),
                confidence_flags=sorted(set([*activity_overview.confidence_flags, *changes_response.confidence_flags])),
            ),
        ),
        business_quality=business_quality_section,
        capital_and_risk=CompanyResearchBriefCapitalAndRiskSection(
            capital_structure=capital_structure,
            capital_markets_summary=capital_markets_summary,
            governance_summary=governance_summary,
            ownership_summary=ownership_summary,
            equity_claim_risk_summary=equity_claim_risk.summary,
            **_build_provenance_contract(
                [
                    SourceUsage(source_id="ft_company_research_brief", role="derived", as_of=capital_structure.as_of, last_refreshed_at=timestamp),
                    SourceUsage(source_id="ft_equity_claim_risk_pack", role="derived", as_of=equity_claim_risk.as_of, last_refreshed_at=equity_claim_risk.last_refreshed_at),
                ],
                as_of=_latest_as_of(capital_structure.as_of, equity_claim_risk.as_of),
                last_refreshed_at=_merge_last_checked(capital_structure.last_refreshed_at, equity_claim_risk.last_refreshed_at, timestamp),
                confidence_flags=sorted(set([*capital_structure.confidence_flags, *equity_claim_risk.confidence_flags])),
            ),
        ),
        valuation=CompanyResearchBriefValuationSection(
            models=models_response,
            peers=peers_response,
            **_build_provenance_contract(
                [
                    SourceUsage(source_id="ft_company_research_brief", role="derived", as_of=models_response.as_of or peers_response.as_of, last_refreshed_at=timestamp),
                ],
                as_of=_latest_as_of(models_response.as_of, peers_response.as_of),
                last_refreshed_at=_merge_last_checked(models_response.last_refreshed_at, peers_response.last_refreshed_at, timestamp),
                confidence_flags=sorted(set([*models_response.confidence_flags, *peers_response.confidence_flags])),
            ),
        ),
        monitor=CompanyResearchBriefMonitorSection(
            activity_overview=activity_overview,
            **_build_provenance_contract(
                [SourceUsage(source_id="ft_activity_overview", role="derived", as_of=activity_overview.as_of, last_refreshed_at=activity_overview.last_refreshed_at)],
                as_of=activity_overview.as_of,
                last_refreshed_at=activity_overview.last_refreshed_at,
                confidence_flags=activity_overview.confidence_flags,
            ),
        ),
    )


def recompute_and_persist_company_research_brief(
    session: Session,
    company_id: int,
    *,
    checked_at: datetime | None = None,
    as_of: datetime | None = None,
    payload_version_hash: str | None = None,
) -> CompanyResearchBriefResponse | None:
    timestamp = checked_at or datetime.now(timezone.utc)
    response = build_company_research_brief_response(session, company_id, as_of=as_of, generated_at=timestamp)
    if response is None:
        mark_dataset_checked(
            session,
            company_id,
            "company_research_brief",
            checked_at=timestamp,
            success=True,
            payload_version_hash=payload_version_hash or BRIEF_SCHEMA_VERSION,
            invalidate_hot_cache=True,
        )
        return None

    statement = insert(CompanyResearchBriefSnapshot).values(
        company_id=company_id,
        as_of_key=_as_of_key(as_of),
        as_of_value=as_of,
        schema_version=BRIEF_SCHEMA_VERSION,
        payload=response.model_dump(mode="json"),
        last_updated=timestamp,
        last_checked=timestamp,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_company_research_brief_snapshots_company_asof_schema",
        set_={
            "as_of_value": statement.excluded.as_of_value,
            "payload": statement.excluded.payload,
            "last_updated": statement.excluded.last_updated,
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    mark_dataset_checked(
        session,
        company_id,
        "company_research_brief",
        checked_at=timestamp,
        success=True,
        payload_version_hash=payload_version_hash or BRIEF_SCHEMA_VERSION,
        invalidate_hot_cache=True,
    )
    return response


def _build_activity_overview_response(session: Session, snapshot: CompanyCacheSnapshot, refresh: RefreshState) -> CompanyActivityOverviewResponse:
    company_id = snapshot.company.id
    filings = get_company_financials(session, company_id)
    filing_events = get_company_filing_events(session, company_id, limit=120)
    proxy_statements = get_company_proxy_statements(session, company_id)
    beneficial_reports = get_company_beneficial_ownership_reports(session, company_id, limit=120)
    insider_trades = get_company_insider_trades(session, company_id, limit=120)
    form144_filings = get_company_form144_filings(session, company_id, limit=120)
    institutional_holdings = get_company_institutional_holdings(session, company_id, limit=120)
    comment_letters = get_company_comment_letters(session, company_id, limit=120)
    capital_events = get_company_capital_markets_events(session, company_id)

    beneficial_payloads = _enrich_beneficial_ownership_amendment_history([
        _serialize_beneficial_ownership_report(report) for report in beneficial_reports
    ])
    alerts = _build_activity_alerts(
        beneficial_filings=beneficial_payloads,
        capital_filings=[_serialize_capital_markets_event(event) for event in capital_events],
        insider_trades=insider_trades,
        institutional_holdings=institutional_holdings,
        comment_letters=comment_letters,
    )
    entries = _build_activity_feed_entries(
        filings=filings,
        filing_events=filing_events,
        governance_filings=proxy_statements,
        beneficial_filings=beneficial_payloads,
        insider_trades=insider_trades,
        form144_filings=form144_filings,
        institutional_holdings=institutional_holdings,
        comment_letters=comment_letters,
    )
    last_refreshed_at = _merge_last_checked(
        snapshot.last_checked,
        *(getattr(item, "last_checked", None) for item in filings),
        snapshot.company.filing_events_last_checked,
        snapshot.company.beneficial_ownership_last_checked,
        snapshot.company.proxy_statements_last_checked,
        snapshot.company.insider_trades_last_checked,
        snapshot.company.institutional_holdings_last_checked,
        snapshot.company.comment_letters_last_checked,
    )
    market_context_status = _get_persisted_market_context_status(session)
    return CompanyActivityOverviewResponse(
        company=_serialize_company(snapshot),
        entries=entries,
        alerts=alerts,
        summary=AlertsSummaryPayload(
            total=len(alerts),
            high=sum(1 for alert in alerts if alert.level == "high"),
            medium=sum(1 for alert in alerts if alert.level == "medium"),
            low=sum(1 for alert in alerts if alert.level == "low"),
        ),
        market_context_status=market_context_status,
        refresh=refresh,
        error=None,
        **_build_provenance_contract(
            [
                SourceUsage(source_id="ft_activity_overview", role="derived", as_of=max((entry.date for entry in entries if entry.date is not None), default=None), last_refreshed_at=last_refreshed_at),
                SourceUsage(source_id="sec_edgar", role="primary", as_of=max((entry.date for entry in entries if entry.date is not None), default=None), last_refreshed_at=last_refreshed_at),
                SourceUsage(
                    source_id="us_treasury_daily_par_yield_curve",
                    role="supplemental",
                    as_of=market_context_status.get("observation_date") if isinstance(market_context_status, dict) else None,
                    last_refreshed_at=last_refreshed_at,
                ) if market_context_status else None,
            ],
            as_of=max((entry.date for entry in entries if entry.date is not None), default=None),
            last_refreshed_at=last_refreshed_at,
            confidence_flags=["activity_feed_empty"] if not entries else [],
        ),
    )


def _get_persisted_market_context_status(session: Session) -> dict[str, object]:
    payload, is_stale = read_global_macro_snapshot_with_meta(session)
    if not payload:
        return {
            "state": "missing",
            "label": "Market context unavailable",
            "observation_date": None,
            "source": "none",
        }

    curve_points = payload.get("curve_points") if isinstance(payload.get("curve_points"), list) else []
    fred_series = payload.get("fred_series") if isinstance(payload.get("fred_series"), list) else []
    treasury_details = payload.get("treasury") if isinstance(payload.get("treasury"), dict) else {}

    observation_dates = [
        str(item.get("observation_date"))
        for item in curve_points
        if isinstance(item, dict) and item.get("observation_date")
    ]
    observation_date = max(observation_dates) if observation_dates else None
    treasury_status = str(treasury_details.get("status") or ("stale" if is_stale else "ok"))

    return {
        "state": "stale" if is_stale else str(payload.get("status") or "ready"),
        "label": "Treasury + FRED" if fred_series else "Treasury only",
        "observation_date": observation_date,
        "source": "U.S. Treasury Daily Par Yield Curve",
        "treasury_status": treasury_status,
    }


def _build_changes_response(
    session: Session,
    snapshot: CompanyCacheSnapshot,
    financials: list[Any],
    refresh: RefreshState,
    as_of: datetime | None,
) -> CompanyChangesSinceLastFilingResponse:
    restatements = get_company_financial_restatements(session, snapshot.company.id)
    if as_of is not None:
        restatements = [record for record in restatements if _effective_at(record.filing_acceptance_at, record.filing_date, record.period_end) <= as_of]
    parsed_filings = get_company_filing_insights(session, snapshot.company.id, limit=12)
    if as_of is not None:
        parsed_filings = select_point_in_time_financials(parsed_filings, as_of)
    comment_letters = get_company_comment_letters(session, snapshot.company.id, limit=24)
    if as_of is not None:
        comment_letters = [letter for letter in comment_letters if _effective_at(letter.filing_date) <= as_of]
    comparison = build_changes_since_last_filing(
        financials,
        restatements,
        parsed_filings=parsed_filings,
        comment_letters=comment_letters,
    )
    comparison_as_of = _normalize_as_of(as_of) or _latest_as_of(
        (comparison.get("current_filing") or {}).get("filing_acceptance_at"),
        (comparison.get("current_filing") or {}).get("period_end"),
    )
    usages = [
        SourceUsage(
            source_id="ft_changes_since_last_filing",
            role="derived",
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(
                snapshot.last_checked,
                (comparison.get("current_filing") or {}).get("last_checked"),
                (comparison.get("previous_filing") or {}).get("last_checked"),
            ),
        ),
        SourceUsage(source_id="sec_companyfacts", role="primary", as_of=comparison_as_of, last_refreshed_at=snapshot.last_checked),
    ]
    if any(
        str(source or "").startswith("https://www.sec.gov/Archives/")
        for source in [
            *(
                evidence.get("source")
                for item in comparison.get("high_signal_changes", [])
                if isinstance(item, dict)
                for evidence in item.get("evidence", [])
                if isinstance(evidence, dict)
            ),
            *(getattr(letter, "sec_url", None) for letter in comment_letters),
        ]
    ):
        usages.append(
            SourceUsage(
                source_id="sec_edgar",
                role="supplemental",
                as_of=comparison_as_of,
                last_refreshed_at=_merge_last_checked(
                    snapshot.last_checked,
                    *(item.last_checked for item in restatements),
                    *(getattr(item, "last_checked", None) for item in parsed_filings),
                    *(getattr(item, "last_checked", None) for item in comment_letters),
                ),
            )
        )
    return CompanyChangesSinceLastFilingResponse(
        company=_serialize_company(snapshot),
        current_filing=comparison.get("current_filing"),
        previous_filing=comparison.get("previous_filing"),
        summary=comparison.get("summary") or ChangesSinceLastFilingSummaryPayload(),
        metric_deltas=comparison.get("metric_deltas") or [],
        new_risk_indicators=comparison.get("new_risk_indicators") or [],
        segment_shifts=comparison.get("segment_shifts") or [],
        share_count_changes=comparison.get("share_count_changes") or [],
        capital_structure_changes=comparison.get("capital_structure_changes") or [],
        amended_prior_values=comparison.get("amended_prior_values") or [],
        high_signal_changes=comparison.get("high_signal_changes") or [],
        comment_letter_history=comparison.get("comment_letter_history") or {},
        refresh=refresh,
        diagnostics=DataQualityDiagnosticsPayload(stale_flags=[]),
        **_build_provenance_contract(
            usages,
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(
                snapshot.last_checked,
                *(item.last_checked for item in restatements),
                *(getattr(item, "last_checked", None) for item in parsed_filings),
                *(getattr(item, "last_checked", None) for item in comment_letters),
            ),
            confidence_flags=list(comparison.get("confidence_flags") or []),
        ),
    )


def _build_earnings_summary_response(session: Session, snapshot: CompanyCacheSnapshot, refresh: RefreshState) -> CompanyEarningsSummaryResponse:
    earnings_last_checked, _cache_state = get_company_earnings_cache_status(session, snapshot.company)
    releases = get_company_earnings_releases(session, snapshot.company.id)
    payload = [_serialize_earnings_release(release) for release in releases]
    return CompanyEarningsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, earnings_last_checked),
            last_checked_earnings=earnings_last_checked,
        ),
        summary=_build_earnings_summary(payload),
        refresh=refresh,
        diagnostics=DataQualityDiagnosticsPayload(stale_flags=[]),
        error=None,
    )


def _build_capital_structure_response(
    session: Session,
    snapshot: CompanyCacheSnapshot,
    refresh: RefreshState,
    as_of: datetime | None,
) -> CompanyCapitalStructureResponse:
    history = get_company_capital_structure_snapshots(session, snapshot.company.id, limit=48)
    if as_of is not None:
        history = [item for item in history if _effective_at(getattr(item, "filing_acceptance_at", None), None, getattr(item, "period_end", None)) <= as_of]
    history = history[:6]
    last_checked = get_company_capital_structure_last_checked(session, snapshot.company.id)
    serialized_history = [_serialize_capital_structure_snapshot(item) for item in history]
    latest = serialized_history[0] if serialized_history else None
    return CompanyCapitalStructureResponse(
        company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, last_checked)),
        latest=latest,
        history=serialized_history,
        last_capital_structure_check=last_checked,
        refresh=refresh,
        diagnostics=DataQualityDiagnosticsPayload(stale_flags=[]),
        **_build_provenance_contract(
            [
                SourceUsage(source_id="ft_capital_structure_intelligence", role="derived", as_of=latest.period_end if latest is not None else None, last_refreshed_at=last_checked)
            ],
            as_of=latest.period_end if latest is not None else None,
            last_refreshed_at=last_checked,
            confidence_flags=list(latest.quality_flags if latest is not None else []),
        ),
    )


def _build_capital_markets_summary_response(session: Session, snapshot: CompanyCacheSnapshot, refresh: RefreshState) -> CompanyCapitalMarketsSummaryResponse:
    rows = get_company_capital_markets_events(session, snapshot.company.id)
    latest_filing_date = max((row.filing_date or row.report_date for row in rows if row.filing_date or row.report_date), default=None)
    max_offering_amount = max((row.offering_amount for row in rows if row.offering_amount is not None), default=None)
    return CompanyCapitalMarketsSummaryResponse(
        company=_serialize_company(snapshot),
        summary=CapitalMarketsSummaryPayload(
            total_filings=len(rows),
            late_filer_notices=sum(1 for row in rows if row.is_late_filer),
            registration_filings=sum(1 for row in rows if row.event_type == "Registration"),
            prospectus_filings=sum(1 for row in rows if row.event_type == "Prospectus"),
            latest_filing_date=latest_filing_date,
            max_offering_amount=max_offering_amount,
        ),
        refresh=refresh,
        diagnostics=DataQualityDiagnosticsPayload(stale_flags=[]),
        error=None,
    )


def _build_governance_summary_response(session: Session, snapshot: CompanyCacheSnapshot, refresh: RefreshState) -> CompanyGovernanceSummaryResponse:
    rows = get_company_proxy_statements(session, snapshot.company.id)
    latest_meeting_date = max((row.meeting_date for row in rows if row.meeting_date is not None), default=None)
    return CompanyGovernanceSummaryResponse(
        company=_serialize_company(snapshot),
        summary=GovernanceSummaryPayload(
            total_filings=len(rows),
            definitive_proxies=sum(1 for row in rows if row.form == "DEF 14A"),
            supplemental_proxies=sum(1 for row in rows if row.form != "DEF 14A"),
            filings_with_meeting_date=sum(1 for row in rows if row.meeting_date is not None),
            filings_with_exec_comp=sum(1 for row in rows if bool(row.executive_comp_table_detected)),
            filings_with_vote_items=sum(1 for row in rows if row.vote_item_count > 0),
            latest_meeting_date=latest_meeting_date,
            max_vote_item_count=max((row.vote_item_count for row in rows), default=0),
        ),
        refresh=refresh,
        diagnostics=DataQualityDiagnosticsPayload(stale_flags=[]),
        error=None,
    )


def _build_ownership_summary_response(session: Session, snapshot: CompanyCacheSnapshot, refresh: RefreshState) -> CompanyBeneficialOwnershipSummaryResponse:
    filings = _enrich_beneficial_ownership_amendment_history([
        _serialize_beneficial_ownership_report(report) for report in get_company_beneficial_ownership_reports(session, snapshot.company.id)
    ])
    return CompanyBeneficialOwnershipSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_beneficial_ownership_summary(filings),
        refresh=refresh,
        error=None,
    )


def _build_models_response(
    session: Session,
    snapshot: CompanyCacheSnapshot,
    financials: list[Any],
    refresh: RefreshState,
    price_last_checked: datetime | None,
) -> CompanyModelsResponse:
    requested_models = [name for name in BRIEF_MODEL_NAMES if settings.valuation_workbench_enabled or name not in {"reverse_dcf", "roic", "capital_allocation"}]
    models = get_company_models(session, snapshot.company.id, requested_models, config_by_model={"dupont": {"mode": "auto"}})
    serialized = [_serialize_model_payload(model_run, snapshot.company) for model_run in models]
    diagnostics = DataQualityDiagnosticsPayload(stale_flags=[])
    return CompanyModelsResponse(
        company=_serialize_company(snapshot),
        requested_models=requested_models,
        models=serialized,
        refresh=refresh,
        diagnostics=diagnostics,
        **_build_models_provenance_contract(models, financials, price_last_checked=price_last_checked),
    )


def _build_peers_response(
    session: Session,
    snapshot: CompanyCacheSnapshot,
    refresh: RefreshState,
    price_last_checked: datetime | None,
    as_of: datetime | None,
) -> CompanyPeersResponse:
    payload = build_peer_comparison(session, snapshot.company.ticker, as_of=as_of)
    if payload is None:
        return CompanyPeersResponse(
            company=None,
            peer_basis="Cached peer universe",
            available_companies=[],
            selected_tickers=[],
            peers=[],
            notes={},
            refresh=refresh,
            **_build_provenance_contract([], confidence_flags=["peer_data_missing"]),
        )
    return CompanyPeersResponse(
        company=_serialize_company(payload["company"]),
        peer_basis=str(payload.get("peer_basis") or "Cached peer universe"),
        available_companies=[PeerOptionPayload(**item) for item in payload.get("available_companies") or []],
        selected_tickers=list(payload.get("selected_tickers") or []),
        peers=[PeerMetricsPayload(**item) for item in payload.get("peers") or []],
        notes=dict(payload.get("notes") or {}),
        refresh=refresh,
        **_build_peers_provenance_contract(payload, price_last_checked=price_last_checked),
    )


def _serialize_company(
    snapshot: CompanyCacheSnapshot,
    last_checked: datetime | None = None,
    *,
    last_checked_earnings: datetime | None = None,
) -> CompanyPayload:
    market_sector, market_industry = _company_market_classification(snapshot.company)
    oil_classification = classify_oil_exposure(
        sector=snapshot.company.sector,
        market_sector=market_sector,
        market_industry=market_industry,
    )
    return CompanyPayload(
        ticker=snapshot.company.ticker,
        cik=snapshot.company.cik,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        market_sector=market_sector,
        market_industry=market_industry,
        oil_exposure_type=oil_classification.oil_exposure_type,
        oil_support_status=oil_classification.oil_support_status,
        oil_support_reasons=list(oil_classification.oil_support_reasons),
        regulated_entity=None,
        strict_official_mode=settings.strict_official_mode,
        last_checked=last_checked if last_checked is not None else snapshot.last_checked,
        last_checked_financials=snapshot.last_checked,
        last_checked_prices=None,
        last_checked_insiders=snapshot.company.insider_trades_last_checked,
        last_checked_institutional=snapshot.company.institutional_holdings_last_checked,
        last_checked_filings=snapshot.company.filing_events_last_checked,
        earnings_last_checked=last_checked_earnings,
        cache_state=snapshot.cache_state,
    )


def _refresh_state_for_snapshot(snapshot: CompanyCacheSnapshot) -> RefreshState:
    reason = snapshot.cache_state if snapshot.cache_state in {"missing", "stale"} else "fresh"
    return RefreshState(triggered=False, reason=reason, ticker=snapshot.company.ticker, job_id=None)


def _company_market_classification(company: Company) -> tuple[str | None, str | None]:
    if not settings.strict_official_mode:
        return company.market_sector, company.market_industry
    profile = resolve_sec_sic_profile(None, company.sector)
    return profile.market_sector, profile.market_industry


def _statement_value(statement: Any, key: str) -> float | int | None:
    if statement is None:
        return None
    data = getattr(statement, "data", None)
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if isinstance(value, (int, float)):
        return value
    if key == "weighted_average_shares_diluted":
        alias_value = data.get("weighted_average_diluted_shares")
        if isinstance(alias_value, (int, float)):
            return alias_value
    return None


def _top_segment(statement: Any) -> dict[str, Any] | None:
    if statement is None:
        return None
    data = getattr(statement, "data", None)
    segments = data.get("segment_breakdown") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        return None
    valid_segments = [item for item in segments if isinstance(item, dict)]
    if not valid_segments:
        return None
    return max(valid_segments, key=lambda item: float(item.get("share_of_revenue") or 0))


def _top_segment_name(statement: Any) -> str | None:
    segment = _top_segment(statement)
    if not isinstance(segment, dict):
        return None
    name = segment.get("segment_name")
    return str(name) if name else None


def _top_segment_share(statement: Any) -> float | int | None:
    segment = _top_segment(statement)
    if not isinstance(segment, dict):
        return None
    value = segment.get("share_of_revenue")
    return value if isinstance(value, (int, float)) else None


def _safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _growth_rate(current: float | int | None, prior: float | int | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return (float(current) - float(prior)) / abs(float(prior))


def _normalize_as_of(value: DateType | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, DateType):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _as_of_key(as_of: datetime | None) -> str:
    return _normalize_as_of(as_of) or "latest"


def _latest_as_of(*values: DateType | datetime | str | None) -> str | None:
    best_text: str | None = None
    best_value: datetime | None = None
    for value in values:
        text = _normalize_as_of(value)
        if text is None:
            continue
        parsed = _parse_as_of(text)
        if parsed is None:
            if best_text is None:
                best_text = text
            continue
        if best_value is None or parsed > best_value:
            best_value = parsed
            best_text = text
    return best_text


def _parse_as_of(value: DateType | datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, DateType):
        return datetime(value.year, value.month, value.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text.count("-") == 2 and "T" not in text:
        parsed_date = DateType.fromisoformat(text)
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _effective_at(*values: DateType | datetime | None) -> datetime:
    for value in values:
        parsed = _parse_as_of(value)
        if parsed is not None:
            return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def _merge_last_checked(*values: datetime | None) -> datetime | None:
    normalized = [value for value in values if value is not None]
    if not normalized:
        return None
    return min(normalized)


def _source_usage_from_hint(
    source_hint: str | None,
    *,
    role: str,
    as_of: DateType | datetime | str | None = None,
    last_refreshed_at: datetime | str | None = None,
    default_source_id: str | None = None,
) -> SourceUsage | None:
    source_id = infer_source_id(source_hint, default=default_source_id)
    if source_id is None:
        return None
    return SourceUsage(source_id=source_id, role=role, as_of=as_of, last_refreshed_at=last_refreshed_at)


def _build_provenance_contract(
    usages: list[SourceUsage | None],
    *,
    as_of: DateType | datetime | str | None = None,
    last_refreshed_at: datetime | None = None,
    confidence_flags: list[str] | None = None,
) -> dict[str, Any]:
    entries = build_provenance_entries(item for item in usages if item is not None)
    source_mix = SourceMixPayload.model_validate(build_source_mix(entries))
    combined_flags = {flag for flag in (confidence_flags or []) if flag}
    if settings.strict_official_mode:
        combined_flags.add("strict_official_mode")
    if source_mix.fallback_source_ids:
        combined_flags.add("commercial_fallback_present")
    return {
        "provenance": [ProvenanceEntryPayload.model_validate(entry) for entry in entries],
        "as_of": _normalize_as_of(as_of),
        "last_refreshed_at": last_refreshed_at,
        "source_mix": source_mix,
        "confidence_flags": sorted(combined_flags),
    }


def _serialize_capital_structure_snapshot(snapshot: Any) -> CapitalStructureSnapshotPayload:
    data = snapshot.data if isinstance(getattr(snapshot, "data", None), dict) else {}
    return CapitalStructureSnapshotPayload(
        accession_number=getattr(snapshot, "accession_number", None),
        filing_type=getattr(snapshot, "filing_type", ""),
        statement_type=getattr(snapshot, "statement_type", ""),
        period_start=getattr(snapshot, "period_start"),
        period_end=getattr(snapshot, "period_end"),
        source=getattr(snapshot, "source", ""),
        filing_acceptance_at=getattr(snapshot, "filing_acceptance_at", None),
        last_updated=getattr(snapshot, "last_updated"),
        last_checked=getattr(snapshot, "last_checked"),
        summary=CapitalStructureSummaryPayload.model_validate(data.get("summary") or {}),
        debt_maturity_ladder=CapitalStructureDebtMaturityPayload.model_validate(data.get("debt_maturity_ladder") or {}),
        lease_obligations=CapitalStructureLeaseObligationsPayload.model_validate(data.get("lease_obligations") or {}),
        debt_rollforward=CapitalStructureDebtRollforwardPayload.model_validate(data.get("debt_rollforward") or {}),
        interest_burden=CapitalStructureInterestBurdenPayload.model_validate(data.get("interest_burden") or {}),
        capital_returns=CapitalStructureCapitalReturnsPayload.model_validate(data.get("capital_returns") or {}),
        net_dilution_bridge=CapitalStructureNetDilutionBridgePayload.model_validate(data.get("net_dilution_bridge") or {}),
        provenance_details=getattr(snapshot, "provenance", None) if isinstance(getattr(snapshot, "provenance", None), dict) else {},
        quality_flags=list(getattr(snapshot, "quality_flags", None) or []),
        confidence_score=getattr(snapshot, "confidence_score", None),
    )


def _serialize_earnings_release(release: Any) -> EarningsReleasePayload:
    return EarningsReleasePayload(
        accession_number=release.accession_number,
        form=release.form,
        filing_date=release.filing_date,
        report_date=release.report_date,
        source_url=release.source_url,
        primary_document=release.primary_document,
        exhibit_document=release.exhibit_document,
        exhibit_type=release.exhibit_type,
        reported_period_label=release.reported_period_label,
        reported_period_end=release.reported_period_end,
        revenue=release.revenue,
        operating_income=release.operating_income,
        net_income=release.net_income,
        diluted_eps=release.diluted_eps,
        revenue_guidance_low=release.revenue_guidance_low,
        revenue_guidance_high=release.revenue_guidance_high,
        eps_guidance_low=release.eps_guidance_low,
        eps_guidance_high=release.eps_guidance_high,
        share_repurchase_amount=release.share_repurchase_amount,
        dividend_per_share=release.dividend_per_share,
        highlights=list(release.highlights or []),
        parse_state=release.parse_state,
    )


def _build_earnings_summary(releases: list[EarningsReleasePayload]) -> EarningsSummaryPayload:
    parsed_releases = [release for release in releases if release.parse_state == "parsed"]
    guidance_releases = [
        release
        for release in releases
        if any(
            value is not None
            for value in (
                release.revenue_guidance_low,
                release.revenue_guidance_high,
                release.eps_guidance_low,
                release.eps_guidance_high,
            )
        )
    ]
    latest = releases[0] if releases else None
    return EarningsSummaryPayload(
        total_releases=len(releases),
        parsed_releases=len(parsed_releases),
        metadata_only_releases=len(releases) - len(parsed_releases),
        releases_with_guidance=len(guidance_releases),
        releases_with_buybacks=sum(1 for release in releases if release.share_repurchase_amount is not None),
        releases_with_dividends=sum(1 for release in releases if release.dividend_per_share is not None),
        latest_filing_date=latest.filing_date if latest is not None else None,
        latest_report_date=latest.report_date if latest is not None else None,
        latest_reported_period_end=latest.reported_period_end if latest is not None else None,
        latest_revenue=latest.revenue if latest is not None else None,
        latest_operating_income=latest.operating_income if latest is not None else None,
        latest_net_income=latest.net_income if latest is not None else None,
        latest_diluted_eps=latest.diluted_eps if latest is not None else None,
    )


def _serialize_beneficial_ownership_report(report: Any) -> BeneficialOwnershipFilingPayload:
    return BeneficialOwnershipFilingPayload(
        accession_number=report.accession_number,
        form=report.form,
        base_form=report.base_form,
        filing_date=report.filing_date,
        report_date=report.report_date,
        is_amendment=report.is_amendment,
        primary_document=report.primary_document,
        primary_doc_description=report.primary_doc_description,
        source_url=report.source_url,
        summary=report.summary,
        parties=[
            BeneficialOwnershipPartyPayload(
                party_name=party.party_name,
                role=party.role,
                filer_cik=getattr(party, "filer_cik", None),
                shares_owned=getattr(party, "shares_owned", None),
                percent_owned=getattr(party, "percent_owned", None),
                event_date=getattr(party, "event_date", None),
                purpose=getattr(party, "purpose", None),
            )
            for party in report.parties
        ],
        previous_accession_number=getattr(report, "previous_accession_number", None),
        amendment_sequence=getattr(report, "amendment_sequence", None),
        amendment_chain_size=getattr(report, "amendment_chain_size", None),
    )


def _build_beneficial_ownership_summary(filings: list[BeneficialOwnershipFilingPayload]) -> Any:
    if not filings:
        return BeneficialOwnershipSummaryPayload(
            total_filings=0,
            initial_filings=0,
            amendments=0,
            unique_reporting_persons=0,
            latest_filing_date=None,
            latest_event_date=None,
            max_reported_percent=None,
            chains_with_amendments=0,
            amendments_with_delta=0,
            ownership_increase_events=0,
            ownership_decrease_events=0,
            ownership_unchanged_events=0,
            largest_increase_pp=None,
            largest_decrease_pp=None,
        )
    unique_people = {
        party.party_name.strip().lower()
        for filing in filings
        for party in filing.parties
        if party.party_name.strip()
    }
    return BeneficialOwnershipSummaryPayload(
        total_filings=len(filings),
        initial_filings=sum(1 for filing in filings if not filing.is_amendment),
        amendments=sum(1 for filing in filings if filing.is_amendment),
        unique_reporting_persons=len(unique_people),
        latest_filing_date=max((filing.filing_date or filing.report_date for filing in filings if filing.filing_date or filing.report_date), default=None),
        latest_event_date=max((party.event_date for filing in filings for party in filing.parties if party.event_date is not None), default=None),
        max_reported_percent=max((party.percent_owned for filing in filings for party in filing.parties if party.percent_owned is not None), default=None),
        chains_with_amendments=len({filing.amendment_chain_size for filing in filings if filing.amendment_chain_size and filing.amendment_chain_size > 1}),
        amendments_with_delta=sum(1 for filing in filings if filing.percent_change_pp is not None),
        ownership_increase_events=sum(1 for filing in filings if filing.change_direction == "increase"),
        ownership_decrease_events=sum(1 for filing in filings if filing.change_direction == "decrease"),
        ownership_unchanged_events=sum(1 for filing in filings if filing.change_direction == "unchanged"),
        largest_increase_pp=max((filing.percent_change_pp for filing in filings if filing.percent_change_pp is not None and filing.percent_change_pp > 0), default=None),
        largest_decrease_pp=min((filing.percent_change_pp for filing in filings if filing.percent_change_pp is not None and filing.percent_change_pp < 0), default=None),
    )


def _beneficial_ownership_primary_percent(filing: BeneficialOwnershipFilingPayload) -> float | None:
    percents = [party.percent_owned for party in filing.parties if party.percent_owned is not None]
    return max(float(percent) for percent in percents) if percents else None


def _group_beneficial_ownership_chains(filings: list[BeneficialOwnershipFilingPayload]) -> dict[str, list[BeneficialOwnershipFilingPayload]]:
    chains: dict[str, list[BeneficialOwnershipFilingPayload]] = {}
    for filing in filings:
        key = None
        for party in filing.parties:
            name = (party.party_name or "").strip().lower()
            if name:
                key = f"{filing.base_form}:name:{name}"
                break
            filer_cik = (party.filer_cik or "").strip()
            if filer_cik:
                key = f"{filing.base_form}:cik:{filer_cik}"
                break
        if key is None and filing.accession_number:
            key = f"{filing.base_form}:accession:{filing.accession_number}"
        if key is None:
            continue
        chains.setdefault(key, []).append(filing)
    for chain in chains.values():
        chain.sort(key=lambda item: (item.filing_date or item.report_date or DateType.min, item.accession_number or ""))
    return chains


def _enrich_beneficial_ownership_amendment_history(filings: list[BeneficialOwnershipFilingPayload]) -> list[BeneficialOwnershipFilingPayload]:
    filing_by_accession = {filing.accession_number: filing for filing in filings if filing.accession_number}
    for filing in filings:
        previous_accession = (filing.previous_accession_number or "").strip() or None
        if not previous_accession:
            continue
        previous_filing = filing_by_accession.get(previous_accession)
        if previous_filing is None:
            continue
        filing.previous_filing_date = previous_filing.filing_date or previous_filing.report_date
        previous_percent = _beneficial_ownership_primary_percent(previous_filing)
        current_percent = _beneficial_ownership_primary_percent(filing)
        filing.previous_percent_owned = previous_percent
        if previous_percent is None or current_percent is None:
            filing.change_direction = filing.change_direction or "unknown"
            continue
        filing.percent_change_pp = current_percent - previous_percent
        filing.change_direction = "increase" if filing.percent_change_pp > 0 else "decrease" if filing.percent_change_pp < 0 else "unchanged"
    for chain in _group_beneficial_ownership_chains(filings).values():
        chain_size = len(chain)
        for index, filing in enumerate(chain):
            filing.amendment_sequence = filing.amendment_sequence or (index + 1)
            filing.amendment_chain_size = filing.amendment_chain_size or chain_size
    return filings


def _build_activity_feed_entries(
    *,
    filings: list[Any],
    filing_events: list[Any],
    governance_filings: list[Any],
    beneficial_filings: list[BeneficialOwnershipFilingPayload],
    insider_trades: list[Any],
    form144_filings: list[Any],
    institutional_holdings: list[Any],
    comment_letters: list[Any],
) -> list[ActivityFeedEntryPayload]:
    entries: list[ActivityFeedEntryPayload] = []
    for filing in filings[:40]:
        accession = _extract_accession_number(getattr(filing, "source", None))
        entries.append(
            ActivityFeedEntryPayload(
                id=f"filing-{accession or filing.id}",
                date=getattr(filing, "filing_date", None) or filing.period_end,
                type="filing",
                badge=filing.filing_type,
                title=_filing_timeline_description(filing.filing_type),
                detail=accession or "SEC filing",
                href=getattr(filing, "source", None),
            )
        )
    for event in filing_events:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"event-{event.accession_number or event.id}",
                date=event.filing_date or event.report_date,
                type="event",
                badge=event.category,
                title=event.summary,
                detail=f"{event.form}{f' - Items {event.items}' if event.items else ''}",
                href=event.source_url,
            )
        )
    for filing in governance_filings:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"governance-{filing.accession_number or filing.id}",
                date=filing.filing_date or filing.report_date,
                type="governance",
                badge=filing.form,
                title=_governance_summary_line(filing.form, filing),
                detail=filing.accession_number or "Proxy filing",
                href=filing.source_url,
            )
        )
    for filing in beneficial_filings:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"ownership-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.report_date,
                type="ownership-change",
                badge=filing.form,
                title=filing.summary,
                detail="Amendment" if filing.is_amendment else "Initial stake disclosure",
                href=filing.source_url,
            )
        )
    for trade in insider_trades[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"insider-{trade.accession_number or f'{trade.insider_name}-{trade.transaction_date}'}",
                date=trade.filing_date or trade.transaction_date,
                type="insider",
                badge=trade.action,
                title=f"{trade.insider_name} {trade.action.lower()} activity",
                detail=f"{trade.role or 'Insider'}{f' - ${trade.value:,.0f}' if trade.value is not None else ''}",
                href=trade.source,
            )
        )
    for filing in form144_filings[:40]:
        title = f"{filing.filer_name} filed Form 144 planned sale" if filing.filer_name else "Form 144 planned sale filing"
        entries.append(
            ActivityFeedEntryPayload(
                id=f"form144-{filing.accession_number or filing.id}",
                date=filing.filing_date or filing.planned_sale_date or filing.report_date,
                type="form144",
                badge="144",
                title=title,
                detail=_build_form144_feed_detail(filing),
                href=filing.source_url,
            )
        )
    for holding in institutional_holdings[:40]:
        fund_name = _institutional_holding_fund_name(holding)
        entries.append(
            ActivityFeedEntryPayload(
                id=f"institutional-{holding.accession_number or f'{fund_name}-{holding.reporting_date}'}",
                date=holding.filing_date or holding.reporting_date,
                type="institutional",
                badge=holding.base_form or holding.filing_form or "13F",
                title=f"{fund_name} updated holdings",
                detail=f"{holding.shares_held:,.0f} shares" if holding.shares_held is not None else "Tracked 13F position",
                href=holding.source,
            )
        )
    for letter in comment_letters[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"comment-letter-{letter.accession_number}",
                date=letter.filing_date,
                type="comment-letter",
                badge="CORRESP",
                title=letter.description,
                detail=letter.accession_number,
                href=letter.sec_url,
            )
        )
    entries.sort(key=lambda item: (item.date or DateType.min, item.id), reverse=True)
    return entries[:220]


def _build_form144_feed_detail(filing: Any) -> str:
    parts: list[str] = []
    if filing.planned_sale_date is not None:
        parts.append(f"Planned sale {filing.planned_sale_date.isoformat()}")
    if filing.filer_name:
        parts.append(filing.filer_name)
    if filing.shares_to_be_sold is not None:
        parts.append(f"{filing.shares_to_be_sold:,.0f} shares")
    if filing.aggregate_market_value is not None:
        parts.append(f"${filing.aggregate_market_value:,.0f}")
    return " | ".join(parts) if parts else (filing.summary or "Planned insider sale filing")


def _build_activity_alerts(
    *,
    beneficial_filings: list[BeneficialOwnershipFilingPayload],
    capital_filings: list[CapitalRaisePayload],
    insider_trades: list[Any],
    institutional_holdings: list[Any],
    comment_letters: list[Any],
) -> list[AlertPayload]:
    alerts: list[AlertPayload] = []
    for filing in beneficial_filings[:30]:
        max_percent = max((party.percent_owned for party in filing.parties if party.percent_owned is not None), default=None)
        if max_percent is not None and max_percent >= 5:
            alerts.append(
                AlertPayload(
                    id=f"alert-activist-{filing.accession_number or filing.source_url}",
                    level="high" if max_percent >= 10 else "medium",
                    title="Large beneficial ownership stake reported",
                    detail=f"{filing.form} reported up to {max_percent:.2f}% beneficial ownership.",
                    source="beneficial-ownership",
                    date=filing.filing_date or filing.report_date,
                    href=filing.source_url,
                )
            )
    for filing in capital_filings[:40]:
        if filing.is_late_filer:
            alerts.append(AlertPayload(id=f"alert-late-{filing.accession_number or filing.source_url}", level="high", title="Late filer notice", detail=f"{filing.form} indicates a delayed periodic filing.", source="capital-markets", date=filing.filing_date or filing.report_date, href=filing.source_url))
            continue
        if filing.event_type in {"Registration", "Prospectus"}:
            size_hint = filing.offering_amount or filing.shelf_size
            detail = f"Potential financing of approximately ${size_hint:,.0f}." if size_hint is not None else "New financing-related filing detected."
            alerts.append(AlertPayload(id=f"alert-financing-{filing.accession_number or filing.source_url}", level="medium", title="Potential dilution or financing activity", detail=detail, source="capital-markets", date=filing.filing_date or filing.report_date, href=filing.source_url))
    recent_buys = sum(1 for trade in insider_trades[:120] if (trade.action or "").upper() == "BUY")
    recent_sells = sum(1 for trade in insider_trades[:120] if (trade.action or "").upper() == "SELL")
    if recent_buys == 0 and recent_sells > 0:
        alerts.append(AlertPayload(id="alert-insider-buy-drought", level="medium", title="Insider buying drought", detail="Recent filings show sells without offsetting insider buys.", source="insider-trades", date=max((trade.filing_date or trade.transaction_date for trade in insider_trades if trade.filing_date or trade.transaction_date), default=None), href=None))
    for holding in institutional_holdings[:80]:
        if holding.percent_change is not None and holding.percent_change <= -20:
            fund_name = _institutional_holding_fund_name(holding)
            alerts.append(AlertPayload(id=f"alert-inst-exit-{holding.accession_number or f'{fund_name}-{holding.reporting_date}'}", level="medium", title="Large institutional position reduction", detail=f"{fund_name} reported a {holding.percent_change:.2f}% position change.", source="institutional-holdings", date=holding.filing_date or holding.reporting_date, href=holding.source))
    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=90)
    for letter in comment_letters[:80]:
        if letter.filing_date is None or letter.filing_date < cutoff_date:
            continue
        alerts.append(AlertPayload(id=f"alert-comment-letter-{letter.accession_number}", level="medium", title="New SEC comment letter correspondence", detail=letter.description, source="comment-letters", date=letter.filing_date, href=letter.sec_url))
    alerts.sort(key=lambda item: (0 if item.level == "high" else 1 if item.level == "medium" else 2, -(item.date.toordinal() if item.date else 0), item.id))
    return alerts[:30]


def _serialize_capital_markets_event(event: Any) -> CapitalRaisePayload:
    return CapitalRaisePayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        event_type=event.event_type,
        security_type=event.security_type,
        offering_amount=event.offering_amount,
        shelf_size=event.shelf_size,
        is_late_filer=event.is_late_filer,
    )


def _institutional_holding_fund_name(holding: Any) -> str:
    direct_name = getattr(holding, "fund_name", None)
    if direct_name:
        return str(direct_name)

    fund = getattr(holding, "fund", None)
    related_name = getattr(fund, "fund_name", None)
    if related_name:
        return str(related_name)

    return "Institutional holder"


def _governance_summary_line(form_display: str, statement: Any) -> str:
    segments: list[str] = ["Definitive proxy statement" if form_display == "DEF 14A" else "Additional proxy material"]
    if statement.meeting_date is not None:
        segments.append(f"meeting date {statement.meeting_date.isoformat()}")
    if statement.vote_item_count > 0:
        segments.append(f"{statement.vote_item_count} proposal items detected")
    if bool(statement.executive_comp_table_detected):
        segments.append("executive compensation table detected")
    return "; ".join(segments) + "."


def _filing_timeline_description(form: str) -> str:
    if form == "8-K":
        return "Current report"
    if form == "10-K":
        return "Annual report"
    if form == "10-Q":
        return "Quarterly report"
    return "SEC filing"


def _extract_accession_number(source: str | None) -> str | None:
    if not source:
        return None
    match = __import__("re").search(r"(\d{10}-\d{2}-\d{6})", source)
    return match.group(1) if match else None


def _serialize_model_payload(model_run: ModelRun | dict[str, Any], company: Company) -> ModelPayload:
    model_name = str(model_run.get("model_name") if isinstance(model_run, dict) else model_run.model_name)
    created_at = model_run.get("created_at") if isinstance(model_run, dict) else model_run.created_at
    if not isinstance(created_at, datetime):
        created_at = datetime.now(timezone.utc)
    input_periods = model_run.get("input_periods") if isinstance(model_run, dict) else model_run.input_periods
    if not isinstance(input_periods, (dict, list)):
        input_periods = {}
    raw_result = model_run.get("result") if isinstance(model_run, dict) else model_run.result
    calculation_version = _model_calculation_version(model_run)
    standardized = standardize_model_result(
        model_name,
        raw_result if isinstance(raw_result, dict) else {},
        input_payload=input_periods if isinstance(input_periods, dict) else None,
        company_context=_model_company_context(company),
        calculation_version=calculation_version,
    )
    return ModelPayload(
        schema_version="2.0",
        model_name=model_name,
        model_version=str(model_run.get("model_version") if isinstance(model_run, dict) else model_run.model_version),
        calculation_version=calculation_version,
        created_at=created_at,
        input_periods=input_periods,
        result=_sanitize_model_result_for_strict_official_mode(model_name, standardized),
    )


def _model_calculation_version(model_run: ModelRun | dict[str, Any]) -> str | None:
    if isinstance(model_run, dict):
        raw_value = model_run.get("calculation_version")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        result = model_run.get("result")
        if isinstance(result, dict):
            nested_value = result.get("calculation_version")
            if isinstance(nested_value, str) and nested_value.strip():
                return nested_value.strip()
        return None
    raw_value = getattr(model_run, "calculation_version", None)
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    if isinstance(model_run.result, dict):
        nested_value = model_run.result.get("calculation_version")
        if isinstance(nested_value, str) and nested_value.strip():
            return nested_value.strip()
    return None


def _model_company_context(company: Company) -> dict[str, Any]:
    market_sector, market_industry = _company_market_classification(company)
    oil_classification = classify_oil_exposure(sector=company.sector, market_sector=market_sector, market_industry=market_industry)
    return {
        "sector": company.sector,
        "market_sector": market_sector,
        "market_industry": market_industry,
        "oil_exposure_type": oil_classification.oil_exposure_type,
        "oil_support_status": oil_classification.oil_support_status,
        "oil_support_reasons": list(oil_classification.oil_support_reasons),
    }


def _sanitize_model_result_for_strict_official_mode(model_name: str, result: dict[str, Any]) -> dict[str, Any]:
    if not settings.strict_official_mode:
        return result
    sanitized = deepcopy(result)
    price_snapshot = sanitized.get("price_snapshot")
    if isinstance(price_snapshot, dict):
        price_snapshot["latest_price"] = None
        price_snapshot["price_date"] = None
        price_snapshot["price_source"] = None
        price_snapshot["price_available"] = False
    if str(model_name).lower() == "reverse_dcf":
        sanitized.update(
            {
                "status": "insufficient_data",
                "model_status": "insufficient_data",
                "explanation": status_explanation("insufficient_data"),
                "reason": "Strict official mode disables commercial price inputs, so reverse DCF is unavailable.",
                "implied_growth": None,
                "implied_margin": None,
                "market_cap_proxy": None,
                "heatmap": [],
            }
        )
    return sanitized


def _build_models_provenance_contract(model_runs: list[ModelRun | dict[str, Any]], financials: list[Any], *, price_last_checked: datetime | None) -> dict[str, Any]:
    latest_statement = financials[0] if financials else None
    usages: list[SourceUsage | None] = [
        SourceUsage(source_id="ft_model_engine", role="derived", as_of=latest_statement.period_end if latest_statement is not None else None, last_refreshed_at=_merge_last_checked(*[_model_created_at(item) for item in model_runs])),
    ]
    for statement in financials[:12]:
        usages.append(_source_usage_from_hint(getattr(statement, "source", None), role="primary", as_of=statement.period_end, last_refreshed_at=getattr(statement, "last_checked", None), default_source_id="sec_companyfacts"))
    return _build_provenance_contract(
        usages,
        as_of=latest_statement.period_end if latest_statement is not None else None,
        last_refreshed_at=_merge_last_checked(getattr(latest_statement, "last_checked", None), price_last_checked, *[_model_created_at(item) for item in model_runs]),
    )


def _model_created_at(model_run: ModelRun | dict[str, Any]) -> datetime | None:
    value = model_run.get("created_at") if isinstance(model_run, dict) else model_run.created_at
    return value if isinstance(value, datetime) else None


def _build_peers_provenance_contract(payload: dict[str, Any], *, price_last_checked: datetime | None) -> dict[str, Any]:
    peers = payload.get("peers") or []
    focus_row = next((row for row in peers if isinstance(row, dict) and row.get("is_focus")), None)
    source_hints = payload.get("source_hints") if isinstance(payload.get("source_hints"), dict) else {}
    company = payload.get("company")
    company_last_checked = getattr(company, "last_checked", None)
    as_of = focus_row.get("period_end") if isinstance(focus_row, dict) else None
    usages: list[SourceUsage | None] = [
        SourceUsage(source_id="ft_peer_comparison", role="derived", as_of=as_of, last_refreshed_at=_merge_last_checked(company_last_checked, price_last_checked))
    ]
    for source_hint in source_hints.get("financial_statement_sources") or ["sec_companyfacts"]:
        usages.append(_source_usage_from_hint(str(source_hint), role="primary", as_of=as_of, last_refreshed_at=company_last_checked, default_source_id="sec_companyfacts"))
    for source_hint in source_hints.get("price_sources") or ([] if not isinstance(focus_row, dict) or not focus_row.get("price_date") else ["yahoo_finance"]):
        usages.append(_source_usage_from_hint(str(source_hint), role="fallback", as_of=focus_row.get("price_date") if isinstance(focus_row, dict) else None, last_refreshed_at=price_last_checked, default_source_id="yahoo_finance"))
    return _build_provenance_contract(usages, as_of=as_of, last_refreshed_at=_merge_last_checked(company_last_checked, price_last_checked))
