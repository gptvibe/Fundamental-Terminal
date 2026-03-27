from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.model_engine.engine import ModelEngine
from app.models import Company, FinancialStatement, ModelRun, PriceHistory
from app.services.cache_queries import CompanyCacheSnapshot, get_company_snapshot
from app.services.sec_sic import resolve_sec_sic_profile
from app.services.sec_edgar import ANNUAL_FORMS, CANONICAL_STATEMENT_TYPE


PEER_MODEL_NAMES = ["ratios", "dupont", "piotroski", "altman_z", "dcf", "reverse_dcf", "roic", "capital_allocation"]
DEFAULT_MAX_PEERS = 4
MAX_AVAILABLE_COMPANIES = 10


def build_peer_comparison(
    session: Session,
    ticker: str,
    *,
    selected_tickers: list[str] | None = None,
    max_peers: int = DEFAULT_MAX_PEERS,
) -> dict[str, Any] | None:
    focus_snapshot = get_company_snapshot(session, ticker)
    if focus_snapshot is None:
        return None

    peer_snapshots = _load_peer_snapshots(session, focus_snapshot.company)
    normalized_selected = _normalize_selected_tickers(selected_tickers, focus_snapshot.company.ticker)
    best_rank = _best_peer_rank(peer_snapshots, focus_snapshot.company)
    default_peer_snapshots = [
        peer for peer in peer_snapshots if _peer_match_rank(peer.company, focus_snapshot.company) == best_rank
    ]

    if normalized_selected:
        selected = [peer.company.ticker for peer in peer_snapshots if peer.company.ticker in normalized_selected][:max_peers]
    else:
        selection_source = default_peer_snapshots or peer_snapshots
        selected = [peer.company.ticker for peer in selection_source[:max_peers]]

    comparison_snapshots = [
        focus_snapshot,
        *[peer for peer in peer_snapshots if peer.company.ticker in set(selected)],
    ]

    available_peers = peer_snapshots[: max(0, MAX_AVAILABLE_COMPANIES - 1)]
    available_tickers = {peer.company.ticker for peer in available_peers}
    for selected_ticker in selected:
        if selected_ticker in available_tickers:
            continue
        selected_snapshot = next((peer for peer in peer_snapshots if peer.company.ticker == selected_ticker), None)
        if selected_snapshot is not None:
            available_peers.append(selected_snapshot)
            available_tickers.add(selected_ticker)

    available_companies = [
        _serialize_option(focus_snapshot, is_focus=True),
        *[_serialize_option(snapshot, is_focus=False) for snapshot in available_peers],
    ]

    if settings.strict_official_mode:
        return {
            "company": focus_snapshot,
            "peer_basis": f"{_peer_basis_label(focus_snapshot.company, best_rank)} (official-only)",
            "available_companies": available_companies,
            "selected_tickers": selected,
            "peers": [],
            "notes": {
                "strict_official_mode": (
                    "Peer comparison is unavailable in strict official mode because this workspace depends on price-derived valuation signals "
                    "and no official end-of-day equity price source is enabled."
                ),
            },
            "source_hints": {
                "financial_statement_sources": ["sec_companyfacts"],
                "price_sources": [],
                "risk_free_sources": [],
            },
        }

    engine = ModelEngine(session)
    wrote_model_cache = False
    rows: list[dict[str, Any]] = []
    for snapshot in comparison_snapshots:
        if snapshot.cache_state == "fresh":
            model_results = engine.compute_models(snapshot.company.id, model_names=PEER_MODEL_NAMES, force=False)
            if any(not result.cached for result in model_results):
                wrote_model_cache = True

    if wrote_model_cache:
        session.commit()

    comparison_company_ids = [snapshot.company.id for snapshot in comparison_snapshots]
    financials_by_company = _load_financials_for_companies(session, comparison_company_ids)
    latest_prices_by_company = _load_latest_prices_for_companies(session, comparison_company_ids)
    models_by_company = _load_latest_models_for_companies(session, comparison_company_ids)
    for snapshot in comparison_snapshots:
        rows.append(
            _build_peer_row(
                snapshot,
                is_focus=snapshot.company.id == focus_snapshot.company.id,
                financials_by_company=financials_by_company,
                latest_prices_by_company=latest_prices_by_company,
                models_by_company=models_by_company,
            )
        )

    financial_statement_sources = sorted(
        {
            statement.source
            for statements in financials_by_company.values()
            for statement in statements
            if getattr(statement, "source", None)
        }
    )
    price_sources = sorted(
        {
            price.source
            for price in latest_prices_by_company.values()
            if getattr(price, "source", None)
        }
    )

    return {
        "company": focus_snapshot,
        "peer_basis": _peer_basis_label(focus_snapshot.company, best_rank),
        "available_companies": available_companies,
        "selected_tickers": selected,
        "peers": rows,
        "notes": {
            "ev_to_ebit": "Approximate EV/EBIT using market cap plus total liabilities as the enterprise-value proxy and operating income as EBIT.",
            "price_to_free_cash_flow": "Uses cached shares outstanding when available, otherwise derives a share-count proxy from net income and EPS.",
            "piotroski": "Piotroski in peer views uses the reported 9-point score when complete; otherwise it scales the available signals proportionally so partial filings still appear in the chart.",
            "fair_value_gap": "Fair value gap uses model fair value per share relative to latest cached price; positive values indicate implied undervaluation.",
            "valuation_band_percentile": "Valuation-band percentile combines where current P/E, P/FCF, and EV/EBIT proxy sit within each company's recent historical range.",
        },
        "source_hints": {
            "financial_statement_sources": financial_statement_sources,
            "price_sources": price_sources,
            "risk_free_sources": _collect_risk_free_sources(models_by_company),
        },
    }


def _load_peer_snapshots(session: Session, focus_company: Company) -> list[CompanyCacheSnapshot]:
    latest_checks = (
        select(
            FinancialStatement.company_id.label("company_id"),
            func.max(FinancialStatement.last_checked).label("last_checked"),
        )
        .where(FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE)
        .group_by(FinancialStatement.company_id)
        .subquery()
    )

    statement = (
        select(Company, latest_checks.c.last_checked)
        .join(latest_checks, latest_checks.c.company_id == Company.id)
        .where(Company.id != focus_company.id)
    )
    rows = session.execute(statement).all()

    snapshots = [_build_snapshot(company, last_checked) for company, last_checked in rows]
    snapshots.sort(key=lambda snapshot: _peer_sort_key(snapshot.company, focus_company))
    return snapshots


def _build_snapshot(company: Company, last_checked: datetime | None) -> CompanyCacheSnapshot:
    normalized = _normalize_datetime(last_checked)
    return CompanyCacheSnapshot(
        company=company,
        last_checked=normalized,
        cache_state=_cache_state_from_last_checked(normalized),
    )


def _cache_state_from_last_checked(last_checked: datetime | None) -> str:
    if last_checked is None:
        return "missing"

    freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.freshness_window_hours)
    if last_checked < freshness_cutoff:
        return "stale"
    return "fresh"


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _peer_sort_key(company: Company, focus_company: Company) -> tuple[int, int, int, str]:
    return (_peer_match_rank(company, focus_company), 0, 0, company.ticker)


def _normalize_selected_tickers(values: list[str] | None, focus_ticker: str) -> list[str]:
    if not values:
        return []

    normalized: list[str] = []
    for value in values:
        ticker = value.strip().upper()
        if not ticker or ticker == focus_ticker or ticker in normalized:
            continue
        normalized.append(ticker)
    return normalized


def _serialize_option(snapshot: CompanyCacheSnapshot, *, is_focus: bool) -> dict[str, Any]:
    market_sector, market_industry = _company_market_classification(snapshot.company)
    return {
        "ticker": snapshot.company.ticker,
        "name": snapshot.company.name,
        "sector": snapshot.company.sector,
        "market_sector": market_sector,
        "market_industry": market_industry,
        "last_checked": snapshot.last_checked,
        "cache_state": snapshot.cache_state,
        "is_focus": is_focus,
    }


def _build_peer_row(
    snapshot: CompanyCacheSnapshot,
    *,
    is_focus: bool,
    financials_by_company: dict[int, list[FinancialStatement]],
    latest_prices_by_company: dict[int, PriceHistory],
    models_by_company: dict[int, dict[str, ModelRun]],
) -> dict[str, Any]:
    statements = financials_by_company.get(snapshot.company.id, [])
    current_statement = _latest_preferred_statement(statements)
    previous_statement = _previous_comparable_statement(statements, current_statement)
    latest_price = latest_prices_by_company.get(snapshot.company.id)
    models = models_by_company.get(snapshot.company.id, {})
    market_sector, market_industry = _company_market_classification(snapshot.company)

    current_data = dict(current_statement.data or {}) if current_statement is not None else {}
    previous_data = dict(previous_statement.data or {}) if previous_statement is not None else {}
    ratios_result = _model_result(models.get("ratios"))
    ratio_values = _mapping(ratios_result.get("values"))
    dupont_result = _model_result(models.get("dupont"))
    piotroski_result = _model_result(models.get("piotroski"))
    altman_result = _model_result(models.get("altman_z"))
    dcf_result = _model_result(models.get("dcf"))
    reverse_dcf_result = _model_result(models.get("reverse_dcf"))
    roic_result = _model_result(models.get("roic"))
    capital_allocation_result = _model_result(models.get("capital_allocation"))

    dcf_status = str(dcf_result.get("model_status") or dcf_result.get("status") or "unknown")
    reverse_dcf_status = str(reverse_dcf_result.get("model_status") or reverse_dcf_result.get("status") or "unknown")

    latest_price_value = latest_price.close if latest_price is not None else None
    eps = _as_float(current_data.get("eps"))
    free_cash_flow = _as_float(current_data.get("free_cash_flow"))
    total_liabilities = _as_float(current_data.get("total_liabilities"))
    operating_income = _as_float(current_data.get("operating_income"))
    shares_outstanding = _shares_outstanding(current_data)
    market_cap = latest_price_value * shares_outstanding if latest_price_value is not None and shares_outstanding is not None else None
    enterprise_value_proxy = market_cap + total_liabilities if market_cap is not None and total_liabilities is not None else None

    revenue_growth = _as_float(ratio_values.get("revenue_growth"))
    if revenue_growth is None:
        revenue_growth = _growth_rate(_as_float(current_data.get("revenue")), _as_float(previous_data.get("revenue")))

    roe = _as_float(dupont_result.get("return_on_equity"))
    if roe is None:
        roe = _as_float(ratio_values.get("return_on_equity"))

    piotroski_available = _as_float(piotroski_result.get("available_criteria"))
    piotroski_score_max = _as_float(piotroski_result.get("score_max")) or 9.0
    piotroski_score = _resolve_piotroski_score(piotroski_result, piotroski_available, piotroski_score_max)
    fair_value_per_share = _as_float(dcf_result.get("fair_value_per_share"))
    fair_value_gap = None
    if dcf_status != "unsupported":
        fair_value_gap = _safe_divide(
            fair_value_per_share - latest_price_value if fair_value_per_share is not None and latest_price_value is not None else None,
            latest_price_value,
        )
    shareholder_yield = _as_float(capital_allocation_result.get("shareholder_yield"))
    implied_growth = _as_float(reverse_dcf_result.get("implied_growth")) if reverse_dcf_status != "unsupported" else None
    roic = _as_float(roic_result.get("roic"))
    valuation_band_percentile = _valuation_band_percentile(statements, latest_price_value, shares_outstanding, enterprise_value_proxy)

    return {
        "ticker": snapshot.company.ticker,
        "name": snapshot.company.name,
        "sector": snapshot.company.sector,
        "market_sector": market_sector,
        "market_industry": market_industry,
        "is_focus": is_focus,
        "cache_state": snapshot.cache_state,
        "last_checked": snapshot.last_checked,
        "period_end": current_statement.period_end if current_statement is not None else None,
        "price_date": latest_price.trade_date if latest_price is not None else None,
        "latest_price": latest_price_value,
        "pe": _safe_divide(latest_price_value, eps),
        "ev_to_ebit": _safe_divide(enterprise_value_proxy, operating_income),
        "price_to_free_cash_flow": _safe_divide(market_cap, free_cash_flow),
        "roe": roe,
        "revenue_growth": revenue_growth,
        "piotroski_score": piotroski_score,
        "altman_z_score": _as_float(altman_result.get("z_score_approximate")),
        "fair_value_gap": fair_value_gap,
        "roic": roic,
        "shareholder_yield": shareholder_yield,
        "implied_growth": implied_growth,
        "dcf_model_status": dcf_status,
        "reverse_dcf_model_status": reverse_dcf_status,
        "valuation_band_percentile": valuation_band_percentile,
        "revenue_history": _build_revenue_history(statements),
    }


def _latest_preferred_statement(statements: list[FinancialStatement]) -> FinancialStatement | None:
    annual_statements = [statement for statement in statements if statement.filing_type in ANNUAL_FORMS]
    preferred = annual_statements or statements
    return preferred[0] if preferred else None


def _previous_comparable_statement(
    statements: list[FinancialStatement],
    current_statement: FinancialStatement | None,
) -> FinancialStatement | None:
    if current_statement is None:
        return None

    current_is_annual = current_statement.filing_type in ANNUAL_FORMS
    for statement in statements:
        if statement.id == current_statement.id:
            continue
        if current_is_annual and statement.filing_type not in ANNUAL_FORMS:
            continue
        return statement
    return None


def _latest_price_point(session: Session, company_id: int) -> PriceHistory | None:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.company_id == company_id)
        .order_by(PriceHistory.trade_date.desc())
        .limit(1)
    )
    return session.execute(statement).scalar_one_or_none()


def _load_financials_for_companies(session: Session, company_ids: list[int]) -> dict[int, list[FinancialStatement]]:
    if not company_ids:
        return {}

    statement = (
        select(FinancialStatement)
        .where(
            FinancialStatement.company_id.in_(company_ids),
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.company_id.asc(), FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc())
    )
    rows = list(session.execute(statement).scalars())
    grouped: dict[int, list[FinancialStatement]] = {company_id: [] for company_id in company_ids}
    for row in rows:
        grouped.setdefault(row.company_id, []).append(row)
    return grouped


def _load_latest_prices_for_companies(session: Session, company_ids: list[int]) -> dict[int, PriceHistory]:
    if not company_ids:
        return {}

    ranked = (
        select(
            PriceHistory.id.label("id"),
            PriceHistory.company_id.label("company_id"),
            func.row_number().over(
                partition_by=PriceHistory.company_id,
                order_by=(PriceHistory.trade_date.desc(), PriceHistory.id.desc()),
            ).label("rn"),
        )
        .where(PriceHistory.company_id.in_(company_ids))
        .subquery()
    )
    statement = (
        select(PriceHistory)
        .join(ranked, ranked.c.id == PriceHistory.id)
        .where(ranked.c.rn == 1)
    )
    rows = list(session.execute(statement).scalars())
    return {row.company_id: row for row in rows}


def _load_latest_models_for_companies(session: Session, company_ids: list[int]) -> dict[int, dict[str, ModelRun]]:
    if not company_ids:
        return {}

    ranked = (
        select(
            ModelRun.id.label("id"),
            ModelRun.company_id.label("company_id"),
            func.lower(ModelRun.model_name).label("model_key"),
            func.row_number().over(
                partition_by=(ModelRun.company_id, func.lower(ModelRun.model_name)),
                order_by=(ModelRun.created_at.desc(), ModelRun.id.desc()),
            ).label("rn"),
        )
        .where(
            ModelRun.company_id.in_(company_ids),
            func.lower(ModelRun.model_name).in_(PEER_MODEL_NAMES),
        )
        .subquery()
    )
    statement = (
        select(ModelRun, ranked.c.model_key)
        .join(ranked, ranked.c.id == ModelRun.id)
        .where(ranked.c.rn == 1)
    )
    rows = session.execute(statement).all()
    grouped: dict[int, dict[str, ModelRun]] = {company_id: {} for company_id in company_ids}
    for model_run, model_key in rows:
        grouped.setdefault(model_run.company_id, {})[str(model_key)] = model_run
    return grouped


def _build_revenue_history(statements: list[FinancialStatement], *, limit: int = 6) -> list[dict[str, Any]]:
    preferred = [statement for statement in statements if statement.filing_type in ANNUAL_FORMS] or statements
    by_period: dict[tuple[Any, str], FinancialStatement] = {}
    for statement in preferred:
        key = (statement.period_end, statement.filing_type)
        if key not in by_period:
            by_period[key] = statement

    ordered = sorted(by_period.values(), key=lambda statement: statement.period_end)
    ordered = ordered[-limit:]
    history: list[dict[str, Any]] = []
    previous_revenue: float | None = None
    for statement in ordered:
        revenue = _as_float((statement.data or {}).get("revenue"))
        history.append(
            {
                "period_end": statement.period_end,
                "revenue": revenue,
                "revenue_growth": _growth_rate(revenue, previous_revenue),
            }
        )
        previous_revenue = revenue

    return history


def _peer_basis_label(company: Company, rank: int) -> str:
    market_sector, market_industry = _company_market_classification(company)
    if rank == 0 and market_industry:
        return f"{market_industry} peers"
    if rank == 1 and market_sector:
        return f"{market_sector} peers"
    if rank == 2 and company.sector:
        return f"{company.sector} peers"
    return "Cached peer universe"


def _best_peer_rank(peer_snapshots: list[CompanyCacheSnapshot], focus_company: Company) -> int:
    if not peer_snapshots:
        return 3
    return min(_peer_match_rank(snapshot.company, focus_company) for snapshot in peer_snapshots)


def _peer_match_rank(company: Company, focus_company: Company) -> int:
    focus_market_sector, focus_market_industry = _company_market_classification(focus_company)
    company_market_sector, company_market_industry = _company_market_classification(company)
    if focus_market_industry and company_market_industry == focus_market_industry:
        return 0
    if focus_market_sector and company_market_sector == focus_market_sector:
        return 1
    if focus_company.sector and company.sector == focus_company.sector:
        return 2
    return 3


def _company_market_classification(company: Company) -> tuple[str | None, str | None]:
    if not settings.strict_official_mode:
        return company.market_sector, company.market_industry
    profile = resolve_sec_sic_profile(None, company.sector)
    return profile.market_sector, profile.market_industry


def _model_result(model_run: ModelRun | None) -> dict[str, Any]:
    if model_run is None or not isinstance(model_run.result, dict):
        return {}
    return model_run.result


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _collect_risk_free_sources(models_by_company: dict[int, dict[str, ModelRun]]) -> list[str]:
    sources: set[str] = set()
    for company_models in models_by_company.values():
        for model in company_models.values():
            result = model.result if isinstance(model.result, dict) else {}
            assumption_provenance = result.get("assumption_provenance")
            if not isinstance(assumption_provenance, dict):
                continue
            risk_free = assumption_provenance.get("risk_free_rate")
            if not isinstance(risk_free, dict):
                continue
            source_name = str(risk_free.get("source_name") or "").strip()
            if source_name:
                sources.add(source_name)
    return sorted(sources)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number == number:
        return None
    return number


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _growth_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def _resolve_piotroski_score(result: dict[str, Any], available_criteria: float | None, score_max: float) -> float | None:
    normalized_score = _as_float(result.get("normalized_score_9"))
    if normalized_score is not None:
        return normalized_score

    raw_score = _as_float(result.get("score"))
    if raw_score is None:
        return None

    if available_criteria is not None and available_criteria > 0:
        return raw_score * score_max / available_criteria

    return raw_score


def _shares_outstanding(data: dict[str, Any]) -> float | None:
    direct_value = _as_float(data.get("shares_outstanding"))
    if direct_value is not None and direct_value > 0:
        return direct_value

    net_income = _as_float(data.get("net_income"))
    eps = _as_float(data.get("eps"))
    derived_value = _safe_divide(net_income, eps)
    if derived_value is None or derived_value <= 0:
        return None
    return derived_value


def _valuation_band_percentile(
    statements: list[FinancialStatement],
    latest_price: float | None,
    shares_outstanding: float | None,
    latest_enterprise_value_proxy: float | None,
) -> float | None:
    if latest_price is None:
        return None

    preferred = [statement for statement in statements if statement.filing_type in ANNUAL_FORMS] or statements
    if len(preferred) < 3:
        return None

    pe_history: list[float] = []
    pfcf_history: list[float] = []
    evebit_history: list[float] = []
    for statement in preferred[:8]:
        data = dict(statement.data or {})
        eps = _as_float(data.get("eps"))
        fcf = _as_float(data.get("free_cash_flow"))
        liabilities = _as_float(data.get("total_liabilities"))
        op_income = _as_float(data.get("operating_income"))
        shares = _shares_outstanding(data) or shares_outstanding
        market_cap = latest_price * shares if shares is not None else None
        enterprise_value_proxy = market_cap + liabilities if market_cap is not None and liabilities is not None else None
        pe = _safe_divide(latest_price, eps)
        pfcf = _safe_divide(market_cap, fcf)
        evebit = _safe_divide(enterprise_value_proxy, op_income)
        if pe is not None:
            pe_history.append(pe)
        if pfcf is not None:
            pfcf_history.append(pfcf)
        if evebit is not None:
            evebit_history.append(evebit)

    latest_pe = pe_history[0] if pe_history else None
    latest_pfcf = pfcf_history[0] if pfcf_history else None
    latest_evebit = _safe_divide(latest_enterprise_value_proxy, _as_float((preferred[0].data or {}).get("operating_income")))

    percentiles: list[float] = []
    percentiles.extend(_single_percentile(latest_pe, pe_history))
    percentiles.extend(_single_percentile(latest_pfcf, pfcf_history))
    percentiles.extend(_single_percentile(latest_evebit, evebit_history))
    if not percentiles:
        return None
    return sum(percentiles) / len(percentiles)


def _single_percentile(current: float | None, values: list[float]) -> list[float]:
    if current is None or len(values) < 3:
        return []
    ordered = sorted(values)
    less_or_equal = sum(1 for value in ordered if value <= current)
    return [less_or_equal / len(ordered)]
