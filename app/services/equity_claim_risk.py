from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy.orm import Session

from app.research_brief_contracts import (
    CapitalStructureNetDilutionBridgePayload,
    CompanyEquityClaimRiskResponse,
    CompanyPayload,
    DataQualityDiagnosticsPayload,
    EquityClaimRiskAtmDependencyPayload,
    EquityClaimRiskDebtMaturityWallPayload,
    EquityClaimRiskEvidencePayload,
    EquityClaimRiskHybridSecuritiesPayload,
    EquityClaimRiskKeywordSignalPayload,
    EquityClaimRiskReportingPayload,
    EquityClaimRiskSbcAndDilutionPayload,
    EquityClaimRiskShareCountBridgePayload,
    EquityClaimRiskShelfCapacityPayload,
    EquityClaimRiskSummaryPayload,
    ProvenanceEntryPayload,
    RefreshState,
    SourceMixPayload,
)
from app.models import CapitalMarketsEvent, CapitalStructureSnapshot, FilingEvent, FinancialRestatement, FinancialStatement
from app.services.cache_queries import (
    get_company_capital_markets_events,
    get_company_capital_structure_snapshots,
    get_company_filing_events,
    get_company_financial_restatements,
    get_company_financials,
    select_point_in_time_financials,
)
from app.services.capital_structure_intelligence import snapshot_effective_at
from app.source_registry import SourceUsage, build_provenance_entries, build_source_mix


_SHELF_FORMS = {"S-3", "S-3/A", "F-3", "F-3/A"}
_ATM_KEYWORDS = ("at-the-market", "at the market", "atm program", "sales agreement")
_CONVERTIBLE_KEYWORDS = ("convertible", "conversion")
_WARRANT_KEYWORDS = ("warrant", "warrants")
_COVENANT_KEYWORDS = ("covenant", "covenants", "waiver", "forbearance", "default", "minimum liquidity", "borrowing base")
_CONTROL_KEYWORDS = ("material weakness", "material weaknesses", "internal control", "internal controls", "icfr", "disclosure controls", "non-reliance")
_HIGH_COVENANT_TERMS = {"default", "forbearance"}
_HIGH_CONTROL_TERMS = {"material weakness", "material weaknesses", "non-reliance"}
_LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}
_REPORTING_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def build_company_equity_claim_risk_response(
    session: Session,
    company_id: int,
    *,
    company: CompanyPayload | None,
    refresh: RefreshState | None = None,
    as_of: datetime | None = None,
) -> CompanyEquityClaimRiskResponse:
    financials = get_company_financials(session, company_id)
    if as_of is not None:
        financials = select_point_in_time_financials(financials, as_of)

    capital_history = get_company_capital_structure_snapshots(session, company_id, limit=48)
    if as_of is not None:
        floor = datetime.min.replace(tzinfo=timezone.utc)
        capital_history = [item for item in capital_history if (snapshot_effective_at(item) or floor) <= as_of]

    capital_events = get_company_capital_markets_events(session, company_id, limit=200)
    if as_of is not None:
        capital_events = [item for item in capital_events if _event_effective_at(item) <= as_of]

    filing_events = get_company_filing_events(session, company_id, limit=200)
    if as_of is not None:
        filing_events = [item for item in filing_events if _event_effective_at(item) <= as_of]

    restatements = get_company_financial_restatements(session, company_id, limit=200)
    if as_of is not None:
        restatements = [item for item in restatements if _restatement_effective_at(item) <= as_of]

    latest_statement = financials[0] if financials else None
    previous_statement = financials[1] if len(financials) > 1 else None
    latest_snapshot = capital_history[0] if capital_history else None
    latest_snapshot_data = dict((latest_snapshot.data or {}) if latest_snapshot is not None else {})

    share_count_bridge = _build_share_count_bridge(latest_snapshot)
    shelf_registration = _build_shelf_capacity(capital_events)
    atm_and_dependency = _build_atm_dependency(latest_statement, latest_snapshot_data, capital_events, filing_events)
    warrants_and_convertibles = _build_hybrid_securities(capital_events, filing_events)
    sbc_and_dilution = _build_sbc_and_dilution(latest_statement, previous_statement, capital_history)
    debt_maturity_wall = _build_debt_maturity_wall(latest_snapshot_data, latest_snapshot)
    covenant_risk_signals = _build_keyword_signals(
        capital_events=capital_events,
        filing_events=filing_events,
        keywords=_COVENANT_KEYWORDS,
        high_terms=_HIGH_COVENANT_TERMS,
        empty_title="No covenant-related stress language was identified in persisted filing descriptions.",
        positive_title="Potential covenant-related filing language identified.",
    )
    reporting_and_controls = _build_reporting_and_controls(restatements, filing_events)

    dilution_risk_level = _dilution_risk_level(
        current_net_dilution=sbc_and_dilution.current_net_dilution_ratio,
        trailing_net_dilution=sbc_and_dilution.trailing_three_period_net_dilution_ratio,
        sbc_to_revenue=sbc_and_dilution.sbc_to_revenue,
        has_atm=atm_and_dependency.atm_detected,
        hybrid_activity=warrants_and_convertibles.warrant_filing_count + warrants_and_convertibles.convertible_filing_count,
    )
    financing_risk_level = _financing_risk_level(
        negative_free_cash_flow=atm_and_dependency.negative_free_cash_flow,
        cash_runway_years=atm_and_dependency.cash_runway_years,
        debt_due_next_twelve_months=atm_and_dependency.debt_due_next_twelve_months,
        cash_balance=_cash_balance(latest_statement),
        has_atm=atm_and_dependency.atm_detected,
        debt_due_next_twenty_four_months_ratio=debt_maturity_wall.debt_due_next_twenty_four_months_ratio,
        shelf_remaining=shelf_registration.remaining_capacity,
    )
    reporting_risk_level = _reporting_risk_level(reporting_and_controls)
    overall_risk_level = _max_level(dilution_risk_level, financing_risk_level, reporting_risk_level)

    summary = EquityClaimRiskSummaryPayload(
        headline=_build_headline(overall_risk_level, dilution_risk_level, financing_risk_level, reporting_risk_level),
        overall_risk_level=overall_risk_level,
        dilution_risk_level=dilution_risk_level,
        financing_risk_level=financing_risk_level,
        reporting_risk_level=reporting_risk_level,
        latest_period_end=getattr(latest_statement, "period_end", None),
        net_dilution_ratio=sbc_and_dilution.current_net_dilution_ratio,
        sbc_to_revenue=sbc_and_dilution.sbc_to_revenue,
        shelf_capacity_remaining=shelf_registration.remaining_capacity,
        recent_atm_activity=atm_and_dependency.atm_detected,
        recent_warrant_or_convertible_activity=(warrants_and_convertibles.warrant_filing_count + warrants_and_convertibles.convertible_filing_count) > 0,
        debt_due_next_twenty_four_months=debt_maturity_wall.debt_due_next_twenty_four_months,
        restatement_severity=reporting_and_controls.restatement_severity,
        internal_control_flag_count=reporting_and_controls.internal_control_flag_count,
        key_points=_build_key_points(
            share_count_bridge=share_count_bridge,
            shelf_registration=shelf_registration,
            atm_and_dependency=atm_and_dependency,
            warrants_and_convertibles=warrants_and_convertibles,
            sbc_and_dilution=sbc_and_dilution,
            debt_maturity_wall=debt_maturity_wall,
            reporting_and_controls=reporting_and_controls,
        ),
    )

    missing_field_flags: list[str] = []
    available_inputs = 0
    for key, present in (
        ("financials_missing", latest_statement is not None),
        ("capital_structure_missing", latest_snapshot is not None),
        ("capital_markets_missing", bool(capital_events)),
        ("filing_events_missing", bool(filing_events)),
    ):
        if present:
            available_inputs += 1
        else:
            missing_field_flags.append(key)

    diagnostics = DataQualityDiagnosticsPayload(
        coverage_ratio=available_inputs / 4 if 4 else None,
        fallback_ratio=0.0,
        stale_flags=[],
        parser_confidence=None,
        missing_field_flags=missing_field_flags,
        reconciliation_penalty=None,
        reconciliation_disagreement_count=0,
    )

    as_of_value = _normalize_as_of(as_of) or _latest_as_of(
        getattr(latest_statement, "period_end", None),
        shelf_registration.latest_shelf_filing_date,
        atm_and_dependency.latest_atm_filing_date,
        warrants_and_convertibles.latest_security_filing_date,
        reporting_and_controls.latest_restatement_date,
    )
    last_refreshed_at = _merge_last_checked(
        getattr(latest_statement, "last_checked", None),
        getattr(latest_snapshot, "last_checked", None),
        *(item.last_checked for item in capital_events),
        *(item.last_checked for item in filing_events),
        *(item.last_checked for item in restatements),
    )
    confidence_flags = sorted(
        {
            *(_string_list(getattr(latest_snapshot, "quality_flags", None))),
            *(("atm_activity_detected",) if atm_and_dependency.atm_detected else ()),
            *(("warrant_or_convertible_activity",) if summary.recent_warrant_or_convertible_activity else ()),
            *(("covenant_language_detected",) if covenant_risk_signals.match_count else ()),
            *(("internal_control_language_detected",) if reporting_and_controls.internal_control_flag_count else ()),
            *(("restatement_severity_high",) if reporting_and_controls.restatement_severity == "high" else ()),
        }
    )

    usages: list[SourceUsage] = [
        SourceUsage(
            source_id="ft_equity_claim_risk_pack",
            role="derived",
            as_of=as_of_value,
            last_refreshed_at=last_refreshed_at,
        )
    ]
    if latest_statement is not None or latest_snapshot is not None:
        usages.append(
            SourceUsage(
                source_id="sec_companyfacts",
                role="primary",
                as_of=getattr(latest_statement, "period_end", None) or getattr(latest_snapshot, "period_end", None),
                last_refreshed_at=_merge_last_checked(getattr(latest_statement, "last_checked", None), getattr(latest_snapshot, "last_checked", None)),
            )
        )
    if capital_events or filing_events or restatements:
        usages.append(
            SourceUsage(
                source_id="sec_edgar",
                role="supplemental",
                as_of=as_of_value,
                last_refreshed_at=_merge_last_checked(*(item.last_checked for item in capital_events), *(item.last_checked for item in filing_events), *(item.last_checked for item in restatements)),
            )
        )

    provenance_rows = build_provenance_entries(usages)
    source_mix = build_source_mix(provenance_rows)

    return CompanyEquityClaimRiskResponse(
        company=company,
        summary=summary,
        share_count_bridge=share_count_bridge,
        shelf_registration=shelf_registration,
        atm_and_financing_dependency=atm_and_dependency,
        warrants_and_convertibles=warrants_and_convertibles,
        sbc_and_dilution=sbc_and_dilution,
        debt_maturity_wall=debt_maturity_wall,
        covenant_risk_signals=covenant_risk_signals,
        reporting_and_controls=reporting_and_controls,
        refresh=refresh or RefreshState(),
        diagnostics=diagnostics,
        provenance=[ProvenanceEntryPayload.model_validate(item) for item in provenance_rows],
        as_of=as_of_value,
        last_refreshed_at=last_refreshed_at,
        source_mix=SourceMixPayload.model_validate(source_mix),
        confidence_flags=confidence_flags,
    )


def _build_share_count_bridge(latest_snapshot: CapitalStructureSnapshot | None) -> EquityClaimRiskShareCountBridgePayload:
    if latest_snapshot is None:
        return EquityClaimRiskShareCountBridgePayload()

    bridge = CapitalStructureNetDilutionBridgePayload.model_validate(
        ((latest_snapshot.data or {}).get("net_dilution_bridge") or {})
    )
    detail = (
        f"{latest_snapshot.filing_type} for {latest_snapshot.period_end.isoformat()} shows "
        f"opening shares {_format_number(bridge.opening_shares)} and ending shares {_format_number(bridge.ending_shares)}."
    )
    evidence = [
        EquityClaimRiskEvidencePayload(
            category="capital_structure",
            title="Latest share-count bridge",
            detail=detail,
            form=latest_snapshot.filing_type,
            filing_date=latest_snapshot.period_end,
            accession_number=latest_snapshot.accession_number,
            source_url=latest_snapshot.source,
            source_id="sec_companyfacts",
        )
    ]
    return EquityClaimRiskShareCountBridgePayload(
        latest_period_end=latest_snapshot.period_end,
        bridge=bridge,
        evidence=evidence,
    )


def _build_shelf_capacity(capital_events: Sequence[CapitalMarketsEvent]) -> EquityClaimRiskShelfCapacityPayload:
    shelf_rows = [row for row in capital_events if (row.form or "").upper() in _SHELF_FORMS and row.shelf_size is not None]
    if not shelf_rows:
        return EquityClaimRiskShelfCapacityPayload()

    latest_shelf = max(shelf_rows, key=_event_effective_at)
    shelf_date = _event_effective_at(latest_shelf)
    usage_rows = [
        row
        for row in capital_events
        if row.accession_number != latest_shelf.accession_number
        and _event_effective_at(row) >= shelf_date
        and row.offering_amount is not None
        and ((row.form or "").upper().startswith("424B") or str(row.event_type or "") in {"Registration", "Prospectus"})
    ]
    utilized = sum(float(row.offering_amount or 0.0) for row in usage_rows)
    gross_capacity = _to_float(latest_shelf.shelf_size)
    remaining = None if gross_capacity is None else max(gross_capacity - utilized, 0.0)
    status = "available"
    if gross_capacity is None:
        status = "none"
    elif utilized > 0 and remaining == 0:
        status = "likely_exhausted"
    elif utilized > 0:
        status = "partially_used"

    evidence = [_event_evidence(latest_shelf, category="capital_markets", title="Latest shelf registration")]
    evidence.extend(_event_evidence(row, category="capital_markets", title="Shelf usage filing") for row in usage_rows[:4])
    return EquityClaimRiskShelfCapacityPayload(
        status=status,
        latest_shelf_form=latest_shelf.form,
        latest_shelf_filing_date=latest_shelf.filing_date or latest_shelf.report_date,
        gross_capacity=gross_capacity,
        utilized_capacity=utilized or 0.0,
        remaining_capacity=remaining,
        evidence=list(evidence),
    )


def _build_atm_dependency(
    latest_statement: FinancialStatement | None,
    latest_snapshot_data: dict[str, Any],
    capital_events: Sequence[CapitalMarketsEvent],
    filing_events: Sequence[FilingEvent],
) -> EquityClaimRiskAtmDependencyPayload:
    atm_capital_rows = [row for row in capital_events if _matches_keywords(_capital_event_text(row), _ATM_KEYWORDS)]
    atm_filing_rows = [row for row in filing_events if _matches_keywords(_filing_event_text(row), _ATM_KEYWORDS)]
    all_rows: list[Any] = [*atm_capital_rows, *atm_filing_rows]
    all_rows.sort(key=_event_effective_at, reverse=True)
    latest_free_cash_flow = _statement_value(latest_statement, "free_cash_flow")
    negative_free_cash_flow = bool(latest_free_cash_flow is not None and latest_free_cash_flow < 0)
    cash_balance = _cash_balance(latest_statement)
    cash_runway_years = None
    if negative_free_cash_flow and cash_balance is not None and latest_free_cash_flow not in {None, 0.0}:
        cash_runway_years = cash_balance / abs(latest_free_cash_flow)

    debt_due_next_twelve_months = _to_float((latest_snapshot_data.get("summary") or {}).get("debt_due_next_twelve_months"))
    financing_dependency_level = "low"
    if negative_free_cash_flow and ((cash_runway_years is not None and cash_runway_years < 1.5) or (cash_balance is not None and debt_due_next_twelve_months is not None and debt_due_next_twelve_months > cash_balance) or all_rows):
        financing_dependency_level = "high"
    elif negative_free_cash_flow or all_rows:
        financing_dependency_level = "medium"

    evidence: list[EquityClaimRiskEvidencePayload] = []
    for row in all_rows[:6]:
        if isinstance(row, CapitalMarketsEvent):
            evidence.append(_event_evidence(row, category="capital_markets", title="ATM-related capital filing"))
        else:
            evidence.append(_event_evidence(row, category="filing_event", title="ATM-related current report"))

    latest_atm_filing_date = max((item.filing_date or item.report_date for item in all_rows if item.filing_date or item.report_date), default=None)
    return EquityClaimRiskAtmDependencyPayload(
        atm_detected=bool(all_rows),
        recent_atm_filing_count=len(all_rows),
        latest_atm_filing_date=latest_atm_filing_date,
        financing_dependency_level=financing_dependency_level,
        negative_free_cash_flow=negative_free_cash_flow,
        cash_runway_years=cash_runway_years,
        debt_due_next_twelve_months=debt_due_next_twelve_months,
        evidence=evidence,
    )


def _build_hybrid_securities(
    capital_events: Sequence[CapitalMarketsEvent],
    filing_events: Sequence[FilingEvent],
) -> EquityClaimRiskHybridSecuritiesPayload:
    warrant_rows = [*[
        row for row in capital_events if _matches_keywords(_capital_event_text(row), _WARRANT_KEYWORDS)
    ], *[
        row for row in filing_events if _matches_keywords(_filing_event_text(row), _WARRANT_KEYWORDS)
    ]]
    convertible_rows = [*[
        row for row in capital_events if _matches_keywords(_capital_event_text(row), _CONVERTIBLE_KEYWORDS)
    ], *[
        row for row in filing_events if _matches_keywords(_filing_event_text(row), _CONVERTIBLE_KEYWORDS)
    ]]
    latest_date = max(
        (getattr(item, "filing_date", None) or getattr(item, "report_date", None) for item in [*warrant_rows, *convertible_rows] if getattr(item, "filing_date", None) or getattr(item, "report_date", None)),
        default=None,
    )
    evidence: list[EquityClaimRiskEvidencePayload] = []
    for row in warrant_rows[:3]:
        evidence.append(_event_evidence(row, category="capital_markets" if isinstance(row, CapitalMarketsEvent) else "filing_event", title="Warrant-related filing"))
    for row in convertible_rows[:3]:
        evidence.append(_event_evidence(row, category="capital_markets" if isinstance(row, CapitalMarketsEvent) else "filing_event", title="Convertible-related filing"))

    return EquityClaimRiskHybridSecuritiesPayload(
        warrant_filing_count=len(warrant_rows),
        convertible_filing_count=len(convertible_rows),
        latest_security_filing_date=latest_date,
        evidence=evidence,
    )


def _build_sbc_and_dilution(
    latest_statement: FinancialStatement | None,
    previous_statement: FinancialStatement | None,
    capital_history: Sequence[CapitalStructureSnapshot],
) -> EquityClaimRiskSbcAndDilutionPayload:
    latest_snapshot = capital_history[0] if capital_history else None
    bridge = ((latest_snapshot.data or {}).get("net_dilution_bridge") or {}) if latest_snapshot is not None else {}
    latest_sbc = _statement_value(latest_statement, "stock_based_compensation")
    latest_revenue = _statement_value(latest_statement, "revenue")
    sbc_to_revenue = _safe_divide(latest_sbc, latest_revenue)
    current_net_dilution_ratio = _to_float(bridge.get("net_dilution_ratio"))
    weighted_average_diluted_shares_growth = _growth_rate(
        _statement_value(latest_statement, "weighted_average_diluted_shares"),
        _statement_value(previous_statement, "weighted_average_diluted_shares"),
    )

    trailing_three_period_net_dilution_ratio = None
    comparable_rows = [
        ((item.data or {}).get("net_dilution_bridge") or {})
        for item in capital_history[:3]
    ]
    ratios = [_to_float(item.get("net_dilution_ratio")) for item in comparable_rows]
    numeric_ratios = [item for item in ratios if item is not None]
    if numeric_ratios:
        trailing_three_period_net_dilution_ratio = sum(numeric_ratios)

    evidence: list[EquityClaimRiskEvidencePayload] = []
    if latest_snapshot is not None:
        evidence.append(_eventless_capital_evidence(latest_snapshot, "Latest dilution bridge"))

    return EquityClaimRiskSbcAndDilutionPayload(
        latest_stock_based_compensation=latest_sbc,
        sbc_to_revenue=sbc_to_revenue,
        current_net_dilution_ratio=current_net_dilution_ratio,
        trailing_three_period_net_dilution_ratio=trailing_three_period_net_dilution_ratio,
        weighted_average_diluted_shares_growth=weighted_average_diluted_shares_growth,
        evidence=evidence,
    )


def _build_debt_maturity_wall(
    latest_snapshot_data: dict[str, Any],
    latest_snapshot: CapitalStructureSnapshot | None,
) -> EquityClaimRiskDebtMaturityWallPayload:
    summary = latest_snapshot_data.get("summary") or {}
    debt_buckets = {
        item.get("bucket_key"): _to_float(item.get("amount"))
        for item in ((latest_snapshot_data.get("debt_maturity_ladder") or {}).get("buckets") or [])
        if isinstance(item, dict)
    }
    total_debt = _to_float(summary.get("total_debt"))
    debt_due_next_twelve_months = _to_float(summary.get("debt_due_next_twelve_months")) or debt_buckets.get("debt_maturity_due_next_twelve_months")
    debt_due_year_two = debt_buckets.get("debt_maturity_due_year_two")
    debt_due_next_twenty_four_months = _sum_non_null(debt_due_next_twelve_months, debt_due_year_two)
    debt_due_next_twenty_four_months_ratio = _safe_divide(debt_due_next_twenty_four_months, total_debt)
    interest_coverage_proxy = _to_float((latest_snapshot_data.get("interest_burden") or {}).get("interest_coverage_proxy"))
    evidence = [_eventless_capital_evidence(latest_snapshot, "Debt maturity wall")]
    return EquityClaimRiskDebtMaturityWallPayload(
        total_debt=total_debt,
        debt_due_next_twelve_months=debt_due_next_twelve_months,
        debt_due_year_two=debt_due_year_two,
        debt_due_next_twenty_four_months=debt_due_next_twenty_four_months,
        debt_due_next_twenty_four_months_ratio=debt_due_next_twenty_four_months_ratio,
        interest_coverage_proxy=interest_coverage_proxy,
        evidence=[item for item in evidence if item is not None],
    )


def _build_keyword_signals(
    *,
    capital_events: Sequence[CapitalMarketsEvent],
    filing_events: Sequence[FilingEvent],
    keywords: Sequence[str],
    high_terms: set[str],
    empty_title: str,
    positive_title: str,
) -> EquityClaimRiskKeywordSignalPayload:
    matches: list[tuple[Any, set[str]]] = []
    for row in capital_events:
        matched = _matched_terms(_capital_event_text(row), keywords)
        if matched:
            matches.append((row, matched))
    for row in filing_events:
        matched = _matched_terms(_filing_event_text(row), keywords)
        if matched:
            matches.append((row, matched))

    all_terms = sorted({term for _row, terms in matches for term in terms})
    level = "high" if any(term in high_terms for term in all_terms) else "medium" if matches else "low"
    evidence: list[EquityClaimRiskEvidencePayload] = []
    if matches:
        for row, matched in matches[:6]:
            evidence.append(
                _event_evidence(
                    row,
                    category="capital_markets" if isinstance(row, CapitalMarketsEvent) else "filing_event",
                    title=positive_title,
                    extra_detail=f"Matched terms: {', '.join(sorted(matched))}.",
                )
            )
    else:
        evidence.append(
            EquityClaimRiskEvidencePayload(
                category="filing_event",
                title="No matched filing language",
                detail=empty_title,
                source_id="ft_equity_claim_risk_pack",
            )
        )

    return EquityClaimRiskKeywordSignalPayload(
        level=level,
        match_count=len(matches),
        matched_terms=all_terms,
        evidence=evidence,
    )


def _build_reporting_and_controls(
    restatements: Sequence[FinancialRestatement],
    filing_events: Sequence[FilingEvent],
) -> EquityClaimRiskReportingPayload:
    high_impact_restatements = 0
    severity = "none"
    evidence: list[EquityClaimRiskEvidencePayload] = []

    for row in restatements[:6]:
        impact = row.confidence_impact or {}
        row_severity = str(impact.get("severity") or "low")
        if row_severity not in {"low", "medium", "high"}:
            row_severity = "low"
        if row_severity == "high":
            high_impact_restatements += 1
        if _REPORTING_RANK[row_severity] > _REPORTING_RANK[severity]:
            severity = row_severity
        detail = (
            f"{row.form} restatement for {row.period_end.isoformat()} changed {len(row.changed_metric_keys or [])} metrics "
            f"with {row_severity} confidence impact."
        )
        evidence.append(
            EquityClaimRiskEvidencePayload(
                category="restatement",
                title="Restatement record",
                detail=detail,
                form=row.form,
                filing_date=row.filing_date,
                accession_number=row.accession_number,
                source_url=row.source,
                source_id="sec_edgar" if "sec.gov" in str(row.source or "").lower() else "sec_companyfacts",
            )
        )

    control_matches: list[tuple[FilingEvent, set[str]]] = []
    for row in filing_events:
        matched = _matched_terms(_filing_event_text(row), _CONTROL_KEYWORDS)
        if matched or (row.item_code == "4.02"):
            matched = set(matched)
            if row.item_code == "4.02":
                matched.add("non-reliance")
            control_matches.append((row, matched))

    control_terms = sorted({term for _row, terms in control_matches for term in terms})
    if severity == "none":
        severity = "low" if restatements else "none"
    if control_matches and (severity in {"none", "low"}):
        severity = "high" if any(term in _HIGH_CONTROL_TERMS for term in control_terms) else "medium"

    for row, matched in control_matches[:6]:
        evidence.append(
            _event_evidence(
                row,
                category="filing_event",
                title="Reporting or internal-control flag",
                extra_detail=f"Matched terms: {', '.join(sorted(matched))}." if matched else None,
            )
        )

    return EquityClaimRiskReportingPayload(
        restatement_count=len(restatements),
        restatement_severity=severity,
        high_impact_restatements=high_impact_restatements,
        latest_restatement_date=max((row.filing_date for row in restatements if row.filing_date is not None), default=None),
        internal_control_flag_count=len(control_matches),
        internal_control_terms=control_terms,
        evidence=evidence,
    )


def _dilution_risk_level(
    *,
    current_net_dilution: float | None,
    trailing_net_dilution: float | None,
    sbc_to_revenue: float | None,
    has_atm: bool,
    hybrid_activity: int,
) -> str:
    if (current_net_dilution is not None and current_net_dilution >= 0.05) or (trailing_net_dilution is not None and trailing_net_dilution >= 0.10):
        return "high"
    if (current_net_dilution is not None and current_net_dilution >= 0.02) or (trailing_net_dilution is not None and trailing_net_dilution >= 0.05) or (sbc_to_revenue is not None and sbc_to_revenue >= 0.08) or has_atm or hybrid_activity > 0:
        return "medium"
    return "low"


def _financing_risk_level(
    *,
    negative_free_cash_flow: bool,
    cash_runway_years: float | None,
    debt_due_next_twelve_months: float | None,
    cash_balance: float | None,
    has_atm: bool,
    debt_due_next_twenty_four_months_ratio: float | None,
    shelf_remaining: float | None,
) -> str:
    if negative_free_cash_flow and (
        (cash_runway_years is not None and cash_runway_years < 1.5)
        or (cash_balance is not None and debt_due_next_twelve_months is not None and debt_due_next_twelve_months > cash_balance)
        or has_atm
        or (shelf_remaining is not None and shelf_remaining > 0)
    ):
        return "high"
    if negative_free_cash_flow or has_atm or (debt_due_next_twenty_four_months_ratio is not None and debt_due_next_twenty_four_months_ratio >= 0.40):
        return "medium"
    return "low"


def _reporting_risk_level(reporting: EquityClaimRiskReportingPayload) -> str:
    if reporting.restatement_severity == "high" or reporting.internal_control_flag_count > 0 and any(term in _HIGH_CONTROL_TERMS for term in reporting.internal_control_terms):
        return "high"
    if reporting.restatement_count > 0 or reporting.internal_control_flag_count > 0:
        return "medium"
    return "low"


def _build_headline(overall: str, dilution: str, financing: str, reporting: str) -> str:
    if overall == "high":
        if dilution == "high":
            return "Recent SEC evidence points to a pressured equity claim, with dilution risk requiring explicit underwriting." 
        if financing == "high":
            return "Recent SEC evidence points to financing dependency that can reshape the equity claim." 
        return "Recent SEC evidence points to reporting or control risk that can impair confidence in the equity claim." 
    if overall == "medium":
        return "SEC-derived evidence suggests the equity claim needs active monitoring for dilution, financing, or reporting slippage."
    return "Recent SEC-derived evidence shows no immediate shock to the equity claim, though capital structure still needs monitoring."


def _build_key_points(
    *,
    share_count_bridge: EquityClaimRiskShareCountBridgePayload,
    shelf_registration: EquityClaimRiskShelfCapacityPayload,
    atm_and_dependency: EquityClaimRiskAtmDependencyPayload,
    warrants_and_convertibles: EquityClaimRiskHybridSecuritiesPayload,
    sbc_and_dilution: EquityClaimRiskSbcAndDilutionPayload,
    debt_maturity_wall: EquityClaimRiskDebtMaturityWallPayload,
    reporting_and_controls: EquityClaimRiskReportingPayload,
) -> list[str]:
    points: list[str] = []
    bridge = share_count_bridge.bridge
    if bridge.net_dilution_ratio is not None:
        direction = "rose" if bridge.net_dilution_ratio > 0 else "fell"
        points.append(f"Net share count {direction} {abs(bridge.net_dilution_ratio):.1%} in the latest filing bridge.")
    if shelf_registration.gross_capacity is not None:
        if shelf_registration.remaining_capacity is not None:
            points.append(
                f"Latest shelf capacity implies about {_format_currency(shelf_registration.remaining_capacity)} remains against a {_format_currency(shelf_registration.gross_capacity)} registration."
            )
        else:
            points.append(f"Latest shelf registration size is {_format_currency(shelf_registration.gross_capacity)}.")
    if atm_and_dependency.atm_detected:
        points.append(
            f"ATM-related language appears in {atm_and_dependency.recent_atm_filing_count} recent filing{'' if atm_and_dependency.recent_atm_filing_count == 1 else 's'}."
        )
    if sbc_and_dilution.sbc_to_revenue is not None:
        points.append(f"Latest stock-based compensation runs at {sbc_and_dilution.sbc_to_revenue:.1%} of revenue.")
    if warrants_and_convertibles.warrant_filing_count + warrants_and_convertibles.convertible_filing_count > 0:
        points.append(
            f"Recent filings mention {warrants_and_convertibles.warrant_filing_count} warrant and {warrants_and_convertibles.convertible_filing_count} convertible disclosures."
        )
    if debt_maturity_wall.debt_due_next_twenty_four_months is not None:
        points.append(
            f"About {_format_currency(debt_maturity_wall.debt_due_next_twenty_four_months)} of debt matures within 24 months."
        )
    if reporting_and_controls.restatement_count > 0 or reporting_and_controls.internal_control_flag_count > 0:
        points.append(
            f"Reporting risk shows {reporting_and_controls.restatement_count} restatements and {reporting_and_controls.internal_control_flag_count} internal-control flags."
        )
    return points[:5]


def _event_evidence(
    row: Any,
    *,
    category: str,
    title: str,
    extra_detail: str | None = None,
) -> EquityClaimRiskEvidencePayload:
    summary = str(getattr(row, "summary", "") or "")
    description = str(getattr(row, "primary_doc_description", "") or "")
    detail = summary or description or "SEC filing evidence."
    if extra_detail:
        detail = f"{detail} {extra_detail}".strip()
    return EquityClaimRiskEvidencePayload(
        category=category,
        title=title,
        detail=detail,
        form=getattr(row, "form", None),
        filing_date=getattr(row, "filing_date", None) or getattr(row, "report_date", None),
        accession_number=getattr(row, "accession_number", None),
        source_url=getattr(row, "source_url", None),
        source_id="sec_edgar",
    )


def _eventless_capital_evidence(snapshot: CapitalStructureSnapshot | None, title: str) -> EquityClaimRiskEvidencePayload | None:
    if snapshot is None:
        return None
    detail = f"{snapshot.filing_type} capital-structure snapshot for {snapshot.period_end.isoformat()}."
    return EquityClaimRiskEvidencePayload(
        category="capital_structure",
        title=title,
        detail=detail,
        form=snapshot.filing_type,
        filing_date=snapshot.period_end,
        accession_number=snapshot.accession_number,
        source_url=snapshot.source,
        source_id="sec_companyfacts",
    )


def _matches_keywords(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _matched_terms(text: str, keywords: Sequence[str]) -> set[str]:
    lowered = text.lower()
    return {keyword for keyword in keywords if keyword in lowered}


def _capital_event_text(row: CapitalMarketsEvent) -> str:
    return " ".join(filter(None, [row.summary, row.primary_doc_description, row.security_type, row.event_type])).lower()


def _filing_event_text(row: FilingEvent) -> str:
    return " ".join(filter(None, [row.summary, row.primary_doc_description, row.items, row.item_code])).lower()


def _event_effective_at(row: Any) -> datetime:
    event_date = getattr(row, "filing_date", None) or getattr(row, "report_date", None)
    if event_date is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.combine(event_date, time.max, tzinfo=timezone.utc)


def _restatement_effective_at(row: FinancialRestatement) -> datetime:
    if row.filing_acceptance_at is not None:
        return _normalize_datetime(row.filing_acceptance_at)
    if row.filing_date is not None:
        return datetime.combine(row.filing_date, time.max, tzinfo=timezone.utc)
    return datetime.combine(row.period_end, time.max, tzinfo=timezone.utc)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric else None


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return numerator / denominator


def _growth_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in {None, 0}:
        return None
    return (current - previous) / abs(previous)


def _sum_non_null(*values: float | None) -> float | None:
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric)


def _cash_balance(statement: FinancialStatement | None) -> float | None:
    if statement is None:
        return None
    return _statement_value(statement, "cash_and_short_term_investments") or _statement_value(statement, "cash_and_cash_equivalents")


def _statement_value(statement: FinancialStatement | None, key: str) -> float | None:
    if statement is None:
        return None
    data = getattr(statement, "data", None)
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    if key == "weighted_average_diluted_shares":
        alias_value = data.get("weighted_average_shares_diluted")
        if isinstance(alias_value, (int, float)):
            return float(alias_value)
    return None


def _merge_last_checked(*values: datetime | None) -> datetime | None:
    normalized = [_normalize_datetime(value) for value in values if value is not None]
    return max(normalized, default=None)


def _normalize_as_of(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _normalize_datetime(value).isoformat()


def _latest_as_of(*values: date | datetime | None) -> str | None:
    normalized: list[datetime] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, datetime):
            normalized.append(_normalize_datetime(value))
        else:
            normalized.append(datetime.combine(value, time.max, tzinfo=timezone.utc))
    return max(normalized).isoformat() if normalized else None


def _string_list(values: Iterable[Any] | None) -> list[str]:
    if values is None:
        return []
    return [str(value) for value in values if value]


def _max_level(*levels: str) -> str:
    best = "low"
    for level in levels:
        if _LEVEL_RANK.get(level, 0) > _LEVEL_RANK[best]:
            best = level
    return best


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


def _format_currency(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.0f}"