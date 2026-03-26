from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    BeneficialOwnershipReport,
    CapitalMarketsEvent,
    Company,
    DerivedMetricPoint,
    EarningsModelPoint,
    EarningsRelease,
    ExecutiveCompensation,
    FilingEvent,
    FinancialStatement,
    Form144Filing,
    InsiderTrade,
    InstitutionalHolding,
    ModelRun,
    PriceHistory,
    ProxyStatement,
)
from app.services.sec_edgar import CANONICAL_STATEMENT_TYPE, FILING_PARSER_STATEMENT_TYPE


@dataclass(slots=True)
class CompanyCacheSnapshot:
    company: Company
    last_checked: datetime | None
    cache_state: str

    @property
    def is_stale(self) -> bool:
        return self.cache_state == "stale"


def search_company_snapshots(
    session: Session,
    ticker_query: str,
    *,
    limit: int = 20,
) -> list[CompanyCacheSnapshot]:
    latest_checks = _latest_checks_subquery()
    normalized_query = ticker_query.strip()
    if not normalized_query:
        return []

    normalized_ticker_query = normalized_query.upper()
    normalized_name_query = normalized_query.lower()
    cik_digits_query = "".join(character for character in normalized_query if character.isdigit())
    padded_cik_query = cik_digits_query.zfill(10) if cik_digits_query else None
    escaped_ticker_query = _escape_like_query(normalized_ticker_query)
    escaped_name_query = _escape_like_query(normalized_query)
    escaped_cik_query = _escape_like_query(cik_digits_query) if cik_digits_query else None

    ticker_prefix_pattern = f"{escaped_ticker_query}%"
    name_prefix_pattern = f"{escaped_name_query}%"
    name_contains_pattern = f"%{escaped_name_query}%"
    cik_prefix_pattern = f"{escaped_cik_query}%" if escaped_cik_query else None
    cik_contains_pattern = f"%{escaped_cik_query}%" if escaped_cik_query else None
    ranking_clauses = []
    if padded_cik_query:
        ranking_clauses.append((Company.cik == padded_cik_query, 0))
    ranking_clauses.extend(
        [
            (func.upper(Company.ticker) == normalized_ticker_query, 1),
            (Company.ticker.ilike(ticker_prefix_pattern, escape="\\"), 2),
            (func.lower(Company.name) == normalized_name_query, 3),
            (Company.name.ilike(name_prefix_pattern, escape="\\"), 4),
            (Company.name.ilike(name_contains_pattern, escape="\\"), 5),
        ]
    )
    if cik_contains_pattern:
        ranking_clauses.append((Company.cik.ilike(cik_contains_pattern, escape="\\"), 6))
    match_rank = case(*ranking_clauses, else_=7)

    search_clauses = [
        Company.ticker.ilike(ticker_prefix_pattern, escape="\\"),
        Company.name.ilike(name_prefix_pattern, escape="\\"),
    ]
    if cik_prefix_pattern:
        search_clauses.append(Company.cik.ilike(cik_prefix_pattern, escape="\\"))

    statement = (
        select(Company, latest_checks.c.last_checked)
        .outerjoin(latest_checks, latest_checks.c.company_id == Company.id)
        .where(or_(*search_clauses))
        .order_by(match_rank.asc(), func.length(Company.ticker).asc(), Company.ticker.asc())
        .limit(limit)
    )

    rows = session.execute(statement).all()
    if len(rows) >= limit or len(normalized_query) < 3:
        return [_build_snapshot(company, last_checked) for company, last_checked in rows]

    seen_ids = {company.id for company, _ in rows}
    contains_clauses = [Company.name.ilike(name_contains_pattern, escape="\\")]
    if cik_contains_pattern:
        contains_clauses.append(Company.cik.ilike(cik_contains_pattern, escape="\\"))

    contains_statement = (
        select(Company, latest_checks.c.last_checked)
        .outerjoin(latest_checks, latest_checks.c.company_id == Company.id)
        .where(or_(*contains_clauses))
        .order_by(match_rank.asc(), func.length(Company.ticker).asc(), Company.ticker.asc())
        .limit(limit - len(rows))
    )
    if seen_ids:
        contains_statement = contains_statement.where(~Company.id.in_(seen_ids))

    rows.extend(session.execute(contains_statement).all())
    return [_build_snapshot(company, last_checked) for company, last_checked in rows]


def get_company_snapshot(session: Session, ticker: str) -> CompanyCacheSnapshot | None:
    latest_checks = _latest_checks_subquery()
    normalized_ticker = ticker.strip().upper()
    statement = (
        select(Company, latest_checks.c.last_checked)
        .outerjoin(latest_checks, latest_checks.c.company_id == Company.id)
        .where(Company.ticker == normalized_ticker)
    )

    row = session.execute(statement).one_or_none()
    if row is None:
        return None

    company, last_checked = row
    return _build_snapshot(company, last_checked)


def get_company_snapshot_by_cik(session: Session, cik: str) -> CompanyCacheSnapshot | None:
    latest_checks = _latest_checks_subquery()
    normalized_cik = str(cik).strip().zfill(10)
    statement = (
        select(Company, latest_checks.c.last_checked)
        .outerjoin(latest_checks, latest_checks.c.company_id == Company.id)
        .where(Company.cik == normalized_cik)
    )

    row = session.execute(statement).one_or_none()
    if row is None:
        return None

    company, last_checked = row
    return _build_snapshot(company, last_checked)


def get_company_snapshots_by_ticker(session: Session, tickers: list[str]) -> dict[str, CompanyCacheSnapshot]:
    if not tickers:
        return {}

    normalized_tickers = sorted({ticker.strip().upper() for ticker in tickers if ticker and ticker.strip()})
    if not normalized_tickers:
        return {}

    latest_checks = _latest_checks_subquery()
    statement = (
        select(Company, latest_checks.c.last_checked)
        .outerjoin(latest_checks, latest_checks.c.company_id == Company.id)
        .where(Company.ticker.in_(normalized_tickers))
    )
    rows = session.execute(statement).all()
    return {company.ticker: _build_snapshot(company, last_checked) for company, last_checked in rows}


def get_company_coverage_counts(session: Session, company_ids: list[int]) -> dict[int, dict[str, int]]:
    if not company_ids:
        return {}

    normalized_ids = sorted({int(company_id) for company_id in company_ids})
    if not normalized_ids:
        return {}

    financial_counts_statement = (
        select(FinancialStatement.company_id, func.count())
        .where(
            FinancialStatement.company_id.in_(normalized_ids),
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .group_by(FinancialStatement.company_id)
    )
    financial_counts = {int(company_id): int(total) for company_id, total in session.execute(financial_counts_statement).all()}

    price_counts_statement = (
        select(PriceHistory.company_id, func.count())
        .where(PriceHistory.company_id.in_(normalized_ids))
        .group_by(PriceHistory.company_id)
    )
    price_counts = {int(company_id): int(total) for company_id, total in session.execute(price_counts_statement).all()}

    result: dict[int, dict[str, int]] = {}
    for company_id in normalized_ids:
        result[company_id] = {
            "financial_periods": financial_counts.get(company_id, 0),
            "price_points": price_counts.get(company_id, 0),
        }
    return result


def get_company_financials(session: Session, company_id: int) -> list[FinancialStatement]:
    statement = (
        select(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc())
    )
    return list(session.execute(statement).scalars())


def get_company_filing_insights(
    session: Session,
    company_id: int,
    *,
    limit: int = 8,
) -> list[FinancialStatement]:
    statement = (
        select(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == FILING_PARSER_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc())
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_models(
    session: Session,
    company_id: int,
    model_names: list[str] | None = None,
    config_by_model: dict[str, dict[str, Any]] | None = None,
) -> list[ModelRun]:
    statement = select(ModelRun).where(ModelRun.company_id == company_id)
    if model_names:
        normalized_names = [model_name.lower() for model_name in model_names]
        statement = statement.where(func.lower(ModelRun.model_name).in_(normalized_names))

    statement = statement.order_by(func.lower(ModelRun.model_name).asc(), ModelRun.created_at.desc(), ModelRun.id.desc())
    rows = list(session.execute(statement).scalars())

    latest_by_model: dict[str, ModelRun] = {}
    for row in rows:
        key = row.model_name.lower()
        expected_config = config_by_model.get(key) if config_by_model else None
        if expected_config is not None and not _config_matches(row.input_periods, expected_config):
            continue
        if key not in latest_by_model:
            latest_by_model[key] = row

    if not model_names:
        return list(latest_by_model.values())
    return [latest_by_model[name] for name in normalized_names if name in latest_by_model]


def _config_matches(input_periods: Any, expected: dict[str, Any]) -> bool:
    if expected is None:
        return True
    if isinstance(input_periods, dict):
        config = input_periods.get("config")
        if config is None:
            # Legacy runs without config are treated as matching only when expected mode is auto.
            return expected == {"mode": "auto"}
        return config == expected
    return False


def get_company_price_history(session: Session, company_id: int) -> list[PriceHistory]:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.company_id == company_id)
        .order_by(PriceHistory.trade_date.asc())
    )
    return list(session.execute(statement).scalars())


def get_company_derived_metric_points(
    session: Session,
    company_id: int,
    *,
    period_type: str | None = None,
    max_periods: int = 24,
) -> list[DerivedMetricPoint]:
    period_statement = select(DerivedMetricPoint.period_end).where(DerivedMetricPoint.company_id == company_id)
    if period_type:
        period_statement = period_statement.where(DerivedMetricPoint.period_type == period_type)
    period_statement = period_statement.group_by(DerivedMetricPoint.period_end).order_by(DerivedMetricPoint.period_end.desc()).limit(max_periods)
    period_ends = [value for value in session.execute(period_statement).scalars()]
    if not period_ends:
        return []

    statement = select(DerivedMetricPoint).where(
        DerivedMetricPoint.company_id == company_id,
        DerivedMetricPoint.period_end.in_(period_ends),
    )
    if period_type:
        statement = statement.where(DerivedMetricPoint.period_type == period_type)
    statement = statement.order_by(DerivedMetricPoint.period_type.asc(), DerivedMetricPoint.period_end.asc(), DerivedMetricPoint.metric_key.asc())
    return list(session.execute(statement).scalars())


def get_company_derived_metrics_last_checked(session: Session, company_id: int) -> datetime | None:
    statement = select(func.max(DerivedMetricPoint.last_checked)).where(DerivedMetricPoint.company_id == company_id)
    return _normalize_datetime(session.execute(statement).scalar_one_or_none())


def get_company_price_cache_status(session: Session, company_id: int) -> tuple[datetime | None, str]:
    statement = select(func.max(PriceHistory.last_checked)).where(PriceHistory.company_id == company_id)
    last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_insider_trades(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
) -> list[InsiderTrade]:
    statement = (
        select(InsiderTrade)
        .where(InsiderTrade.company_id == company_id)
        .order_by(
            InsiderTrade.transaction_date.desc().nullslast(),
            InsiderTrade.filing_date.desc().nullslast(),
            InsiderTrade.id.desc(),
        )
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_insider_trade_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.insider_trades_last_checked)
    if last_checked is None:
        statement = select(func.max(InsiderTrade.last_checked)).where(InsiderTrade.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_form144_filings(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
) -> list[Form144Filing]:
    statement = (
        select(Form144Filing)
        .where(Form144Filing.company_id == company_id)
        .order_by(
            Form144Filing.planned_sale_date.desc().nullslast(),
            Form144Filing.filing_date.desc().nullslast(),
            Form144Filing.id.desc(),
        )
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_form144_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.form144_filings_last_checked)
    if last_checked is None:
        statement = select(func.max(Form144Filing.last_checked)).where(Form144Filing.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_earnings_releases(
    session: Session,
    company_id: int,
    *,
    limit: int = 100,
) -> list[EarningsRelease]:
    statement = (
        select(EarningsRelease)
        .where(EarningsRelease.company_id == company_id)
        .order_by(
            EarningsRelease.filing_date.desc().nullslast(),
            EarningsRelease.reported_period_end.desc().nullslast(),
            EarningsRelease.id.desc(),
        )
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_earnings_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.earnings_last_checked)
    if last_checked is None:
        statement = select(func.max(EarningsRelease.last_checked)).where(EarningsRelease.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_earnings_model_points(
    session: Session,
    company_id: int,
    *,
    limit: int = 24,
) -> list[EarningsModelPoint]:
    statement = (
        select(EarningsModelPoint)
        .where(EarningsModelPoint.company_id == company_id)
        .order_by(EarningsModelPoint.period_end.desc(), EarningsModelPoint.id.desc())
        .limit(limit)
    )
    rows = list(session.execute(statement).scalars())
    rows.sort(key=lambda item: item.period_end)
    return rows


def get_company_earnings_model_cache_status(session: Session, company_id: int) -> tuple[datetime | None, str]:
    statement = select(func.max(EarningsModelPoint.last_checked)).where(EarningsModelPoint.company_id == company_id)
    last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_institutional_holdings(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
) -> list[InstitutionalHolding]:
    statement = (
        select(InstitutionalHolding)
        .options(selectinload(InstitutionalHolding.fund))
        .where(InstitutionalHolding.company_id == company_id)
        .order_by(InstitutionalHolding.reporting_date.desc(), InstitutionalHolding.market_value.desc().nullslast())
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_institutional_holdings_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.institutional_holdings_last_checked)
    if last_checked is None:
        statement = select(func.max(InstitutionalHolding.last_checked)).where(InstitutionalHolding.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_beneficial_ownership_reports(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
) -> list[BeneficialOwnershipReport]:
    statement = (
        select(BeneficialOwnershipReport)
        .options(selectinload(BeneficialOwnershipReport.parties))
        .where(BeneficialOwnershipReport.company_id == company_id)
        .order_by(BeneficialOwnershipReport.filing_date.desc().nullslast(), BeneficialOwnershipReport.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_beneficial_ownership_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.beneficial_ownership_last_checked)
    if last_checked is None:
        statement = select(func.max(BeneficialOwnershipReport.last_checked)).where(BeneficialOwnershipReport.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_filing_events(
    session: Session,
    company_id: int,
    *,
    limit: int = 300,
) -> list[FilingEvent]:
    statement = (
        select(FilingEvent)
        .where(FilingEvent.company_id == company_id)
        .order_by(
            FilingEvent.filing_date.desc().nullslast(),
            FilingEvent.report_date.desc().nullslast(),
            FilingEvent.accession_number.desc(),
            FilingEvent.item_code.asc(),
        )
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_filing_events_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.filing_events_last_checked)
    if last_checked is None:
        statement = select(func.max(FilingEvent.last_checked)).where(FilingEvent.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_capital_markets_events(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
) -> list[CapitalMarketsEvent]:
    statement = (
        select(CapitalMarketsEvent)
        .where(CapitalMarketsEvent.company_id == company_id)
        .order_by(CapitalMarketsEvent.filing_date.desc().nullslast(), CapitalMarketsEvent.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_capital_markets_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.capital_markets_last_checked)
    if last_checked is None:
        statement = select(func.max(CapitalMarketsEvent.last_checked)).where(CapitalMarketsEvent.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_proxy_statements(
    session: Session,
    company_id: int,
    *,
    limit: int = 60,
) -> list[ProxyStatement]:
    """Return cached proxy statements ordered newest-first, with exec comp and
    vote result rows eagerly loaded."""
    from sqlalchemy.orm import selectinload as _selectinload

    statement = (
        select(ProxyStatement)
        .options(
            _selectinload(ProxyStatement.exec_comp_rows),
            _selectinload(ProxyStatement.vote_results),
        )
        .where(ProxyStatement.company_id == company_id)
        .order_by(ProxyStatement.filing_date.desc().nullslast(), ProxyStatement.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_executive_compensation(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
) -> list[ExecutiveCompensation]:
    """Return all cached executive compensation rows for a company, ordered by
    most recent proxy statement first then by total compensation descending."""
    statement = (
        select(ExecutiveCompensation)
        .where(ExecutiveCompensation.company_id == company_id)
        .order_by(
            ExecutiveCompensation.fiscal_year.desc().nullslast(),
            ExecutiveCompensation.total_compensation.desc().nullslast(),
        )
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_proxy_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    last_checked = _normalize_datetime(company.proxy_statements_last_checked)
    if last_checked is None:
        statement = select(func.max(ProxyStatement.last_checked)).where(ProxyStatement.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    return last_checked, _cache_state_from_last_checked(last_checked)


def _latest_checks_subquery():
    return (
        select(
            FinancialStatement.company_id.label("company_id"),
            func.max(FinancialStatement.last_checked).label("last_checked"),
        )
        .where(FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE)
        .group_by(FinancialStatement.company_id)
        .subquery()
    )


def _build_snapshot(company: Company, last_checked: datetime | None) -> CompanyCacheSnapshot:
    normalized_last_checked = _normalize_datetime(last_checked)
    return CompanyCacheSnapshot(
        company=company,
        last_checked=normalized_last_checked,
        cache_state=_cache_state_from_last_checked(normalized_last_checked),
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


def _escape_like_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
