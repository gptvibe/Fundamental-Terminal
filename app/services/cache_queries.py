from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import Company, FinancialStatement, InsiderTrade, InstitutionalHolding, ModelRun, PriceHistory
from app.services.sec_edgar import CANONICAL_STATEMENT_TYPE


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
    escaped_ticker_query = _escape_like_query(normalized_ticker_query)
    escaped_name_query = _escape_like_query(normalized_query)

    ticker_prefix_pattern = f"{escaped_ticker_query}%"
    name_prefix_pattern = f"{escaped_name_query}%"
    name_contains_pattern = f"%{escaped_name_query}%"
    match_rank = case(
        (func.upper(Company.ticker) == normalized_ticker_query, 0),
        (Company.ticker.ilike(ticker_prefix_pattern, escape="\\"), 1),
        (func.lower(Company.name) == normalized_name_query, 2),
        (Company.name.ilike(name_prefix_pattern, escape="\\"), 3),
        (Company.name.ilike(name_contains_pattern, escape="\\"), 4),
        else_=5,
    )

    statement = (
        select(Company, latest_checks.c.last_checked)
        .outerjoin(latest_checks, latest_checks.c.company_id == Company.id)
        .where(
            or_(
                Company.ticker.ilike(ticker_prefix_pattern, escape="\\"),
                Company.name.ilike(name_prefix_pattern, escape="\\"),
                Company.name.ilike(name_contains_pattern, escape="\\"),
            )
        )
        .order_by(match_rank.asc(), func.length(Company.ticker).asc(), Company.ticker.asc())
        .limit(limit)
    )

    rows = session.execute(statement).all()
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


def get_company_models(
    session: Session,
    company_id: int,
    model_names: list[str] | None = None,
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
        if key not in latest_by_model:
            latest_by_model[key] = row

    if not model_names:
        return list(latest_by_model.values())
    return [latest_by_model[name] for name in normalized_names if name in latest_by_model]


def get_company_price_history(session: Session, company_id: int) -> list[PriceHistory]:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.company_id == company_id)
        .order_by(PriceHistory.trade_date.asc())
    )
    return list(session.execute(statement).scalars())


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
