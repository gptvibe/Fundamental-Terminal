from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.model_engine.calculation_versions import has_current_calculation_version
from app.models import (
    BeneficialOwnershipReport,
    CapitalMarketsEvent,
    CapitalStructureSnapshot,
    CommentLetter,
    Company,
    DerivedMetricPoint,
    DatasetRefreshState,
    EarningsModelPoint,
    EarningsRelease,
    ExecutiveCompensation,
    FilingEvent,
    FinancialRestatement,
    FinancialStatement,
    Form144Filing,
    InsiderTrade,
    InstitutionalHolding,
    ModelRun,
    PriceHistory,
    ProxyStatement,
)
from app.services.refresh_state import cache_state_for_dataset, mark_dataset_checked
from app.services.regulated_financials import BANK_REGULATORY_STATEMENT_TYPE
from app.services.sec_edgar import CANONICAL_STATEMENT_TYPE, FILING_PARSER_STATEMENT_TYPE


@dataclass(slots=True)
class CompanyCacheSnapshot:
    company: Company
    last_checked: datetime | None
    cache_state: str

    @property
    def is_stale(self) -> bool:
        return self.cache_state == "stale"


def _normalize_company_ids(company_ids: list[int]) -> list[int]:
    return sorted({int(company_id) for company_id in company_ids})


def _group_rows_by_company_id(company_ids: list[int], rows: list[Any]) -> dict[int, list[Any]]:
    grouped: dict[int, list[Any]] = {company_id: [] for company_id in company_ids}
    for row in rows:
        grouped.setdefault(int(row.company_id), []).append(row)
    return grouped


def _load_rows_by_company_ids(
    session: Session,
    model: Any,
    company_ids: list[int],
    *,
    filters: tuple[Any, ...] = (),
    order_by: tuple[Any, ...],
    options: tuple[Any, ...] = (),
) -> dict[int, list[Any]]:
    normalized_ids = _normalize_company_ids(company_ids)
    if not normalized_ids:
        return {}

    statement = select(model).where(model.company_id.in_(normalized_ids), *filters)
    for option in options:
        statement = statement.options(option)
    statement = statement.order_by(model.company_id.asc(), *order_by)
    return _group_rows_by_company_id(normalized_ids, list(session.execute(statement).scalars()))


def _load_top_rows_by_company_ids(
    session: Session,
    model: Any,
    company_ids: list[int],
    *,
    limit: int,
    filters: tuple[Any, ...] = (),
    order_by: tuple[Any, ...],
    options: tuple[Any, ...] = (),
) -> dict[int, list[Any]]:
    normalized_ids = _normalize_company_ids(company_ids)
    if not normalized_ids:
        return {}

    ranked = (
        select(
            model.id.label("id"),
            model.company_id.label("company_id"),
            func.row_number().over(
                partition_by=model.company_id,
                order_by=order_by,
            ).label("rn"),
        )
        .where(model.company_id.in_(normalized_ids), *filters)
        .subquery()
    )

    statement = select(model).join(ranked, model.id == ranked.c.id).where(ranked.c.rn <= limit)
    for option in options:
        statement = statement.options(option)
    statement = statement.order_by(model.company_id.asc(), *order_by)
    return _group_rows_by_company_id(normalized_ids, list(session.execute(statement).scalars()))


def search_company_snapshots(
    session: Session,
    ticker_query: str,
    *,
    limit: int = 20,
    allow_contains_fallback: bool = True,
) -> list[CompanyCacheSnapshot]:
    normalized_query = ticker_query.strip()
    if not normalized_query:
        return []

    normalized_ticker_query = normalized_query.upper()
    normalized_name_query = normalized_query.lower()
    cik_digits_query = "".join(character for character in normalized_query if character.isdigit())
    padded_cik_query = cik_digits_query.zfill(10) if cik_digits_query else None
    escaped_ticker_query = _escape_like_query(normalized_ticker_query)
    escaped_name_query = _escape_like_query(normalized_name_query)
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
            (Company.ticker.like(ticker_prefix_pattern, escape="\\"), 2),
            (func.lower(Company.name) == normalized_name_query, 3),
            (func.lower(Company.name).like(name_prefix_pattern, escape="\\"), 4),
            (func.lower(Company.name).like(name_contains_pattern, escape="\\"), 5),
        ]
    )
    if cik_contains_pattern:
        ranking_clauses.append((Company.cik.like(cik_contains_pattern, escape="\\"), 6))
    match_rank = case(*ranking_clauses, else_=7)

    search_clauses = [
        Company.ticker.like(ticker_prefix_pattern, escape="\\"),
        func.lower(Company.name).like(name_prefix_pattern, escape="\\"),
    ]
    if cik_prefix_pattern:
        search_clauses.append(Company.cik.like(cik_prefix_pattern, escape="\\"))

    statement = (
        select(Company)
        .where(or_(*search_clauses))
        .order_by(match_rank.asc(), func.length(Company.ticker).asc(), Company.ticker.asc())
        .limit(limit)
    )

    companies = list(session.execute(statement).scalars())
    if not allow_contains_fallback or len(companies) >= limit or len(normalized_query) < 3:
        return _build_snapshots_for_companies(session, companies)

    seen_ids = {company.id for company in companies}
    contains_clauses = [func.lower(Company.name).like(name_contains_pattern, escape="\\")]
    if cik_contains_pattern:
        contains_clauses.append(Company.cik.like(cik_contains_pattern, escape="\\"))

    contains_statement = (
        select(Company)
        .where(or_(*contains_clauses))
        .order_by(match_rank.asc(), func.length(Company.ticker).asc(), Company.ticker.asc())
        .limit(limit - len(companies))
    )
    if seen_ids:
        contains_statement = contains_statement.where(~Company.id.in_(seen_ids))

    companies.extend(session.execute(contains_statement).scalars())
    return _build_snapshots_for_companies(session, companies)


def get_company_snapshot(session: Session, ticker: str) -> CompanyCacheSnapshot | None:
    normalized_ticker = ticker.strip().upper()
    statement = select(Company).where(Company.ticker == normalized_ticker)
    company = session.execute(statement).scalar_one_or_none()
    if company is None:
        return None
    return _build_snapshots_for_companies(session, [company])[0]


def get_company_snapshot_by_cik(session: Session, cik: str) -> CompanyCacheSnapshot | None:
    normalized_cik = str(cik).strip().zfill(10)
    statement = select(Company).where(Company.cik == normalized_cik)
    company = session.execute(statement).scalar_one_or_none()
    if company is None:
        return None
    return _build_snapshots_for_companies(session, [company])[0]


def get_company_snapshots_by_ticker(session: Session, tickers: list[str]) -> dict[str, CompanyCacheSnapshot]:
    if not tickers:
        return {}

    normalized_tickers = sorted({ticker.strip().upper() for ticker in tickers if ticker and ticker.strip()})
    if not normalized_tickers:
        return {}

    statement = select(Company).where(Company.ticker.in_(normalized_tickers))
    companies = list(session.execute(statement).scalars())
    return {snapshot.company.ticker: snapshot for snapshot in _build_snapshots_for_companies(session, companies)}


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


def get_company_financials(
    session: Session,
    company_id: int,
    *,
    limit: int | None = None,
) -> list[FinancialStatement]:
    statement = (
        select(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.execute(statement).scalars())


def get_company_regulated_bank_financials(
    session: Session,
    company_id: int,
    *,
    limit: int | None = None,
) -> list[FinancialStatement]:
    statement = (
        select(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == BANK_REGULATORY_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.execute(statement).scalars())


def get_company_financial_restatements(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
    as_of: datetime | None = None,
) -> list[FinancialRestatement]:
    statement = (
        select(FinancialRestatement)
        .where(FinancialRestatement.company_id == company_id)
        .order_by(
            FinancialRestatement.filing_acceptance_at.desc().nullslast(),
            FinancialRestatement.filing_date.desc().nullslast(),
            FinancialRestatement.period_end.desc(),
            FinancialRestatement.id.desc(),
        )
    )
    if as_of is None:
        statement = statement.limit(limit)
        return list(session.execute(statement).scalars())

    rows: list[FinancialRestatement] = []
    for row in session.execute(statement).scalars():
        effective_at = _financial_restatement_effective_at(row)
        if effective_at is None or effective_at > as_of:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def select_point_in_time_financials(
    financials: list[FinancialStatement],
    as_of: datetime,
) -> list[FinancialStatement]:
    visible: dict[tuple[date, str], FinancialStatement] = {}
    for statement in financials:
        effective_at = _statement_effective_at(statement)
        if effective_at is None or effective_at > as_of:
            continue
        key = (statement.period_end, statement.filing_type)
        current = visible.get(key)
        if current is None or _statement_sort_key(statement) > _statement_sort_key(current):
            visible[key] = statement
    return sorted(visible.values(), key=lambda item: (item.period_end, item.filing_type), reverse=True)


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
    rows_statement = select(ModelRun).where(ModelRun.company_id == company_id)

    normalized_names: list[str] = []
    if model_names:
        normalized_names = [model_name.lower() for model_name in model_names]
        rows_statement = rows_statement.where(func.lower(ModelRun.model_name).in_(normalized_names))
    rows_statement = rows_statement.order_by(func.lower(ModelRun.model_name).asc(), ModelRun.created_at.desc(), ModelRun.id.desc())
    rows = list(session.execute(rows_statement).scalars())

    latest_by_model: dict[str, ModelRun] = {}
    for row in rows:
        key = row.model_name.lower()
        if key in latest_by_model:
            continue
        if not _model_run_has_current_calculation_version(row):
            continue
        expected_config = config_by_model.get(key) if config_by_model else None
        if expected_config is not None and not _config_matches(row.input_periods, expected_config):
            continue
        latest_by_model[key] = row

    if not model_names:
        return list(latest_by_model.values())
    return [latest_by_model[name] for name in normalized_names if name in latest_by_model]


def get_company_models_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    model_names: list[str] | None = None,
    config_by_model: dict[str, dict[str, Any]] | None = None,
) -> dict[int, dict[str, ModelRun]]:
    normalized_ids = _normalize_company_ids(company_ids)
    if not normalized_ids:
        return {}

    normalized_names: list[str] = []
    rows_statement = select(ModelRun).where(ModelRun.company_id.in_(normalized_ids))
    if model_names:
        normalized_names = [model_name.lower() for model_name in model_names]
        rows_statement = rows_statement.where(func.lower(ModelRun.model_name).in_(normalized_names))
    rows_statement = rows_statement.order_by(
        ModelRun.company_id.asc(),
        func.lower(ModelRun.model_name).asc(),
        ModelRun.created_at.desc(),
        ModelRun.id.desc(),
    )
    rows = list(session.execute(rows_statement).scalars())

    result: dict[int, dict[str, ModelRun]] = {company_id: {} for company_id in normalized_ids}
    for row in rows:
        key = row.model_name.lower()
        if not _model_run_has_current_calculation_version(row):
            continue
        expected_config = config_by_model.get(key) if config_by_model else None
        if expected_config is not None and not _config_matches(row.input_periods, expected_config):
            continue
        company_models = result.setdefault(int(row.company_id), {})
        if key not in company_models:
            company_models[key] = row

    if not normalized_names:
        return result

    ordered_result: dict[int, dict[str, ModelRun]] = {}
    for company_id in normalized_ids:
        company_models = result.get(company_id, {})
        ordered_result[company_id] = {
            model_name: company_models[model_name]
            for model_name in normalized_names
            if model_name in company_models
        }
    return ordered_result


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


def _model_run_has_current_calculation_version(model_run: ModelRun) -> bool:
    calculation_version = getattr(model_run, "calculation_version", None)
    if not calculation_version and isinstance(model_run.result, dict):
        raw_value = model_run.result.get("calculation_version")
        calculation_version = raw_value if isinstance(raw_value, str) else None
    return has_current_calculation_version(model_run.model_name, calculation_version)


def _statement_effective_at(statement: FinancialStatement) -> datetime | None:
    acceptance_at = getattr(statement, "filing_acceptance_at", None)
    if acceptance_at is not None:
        return _normalize_datetime(acceptance_at)
    period_end = getattr(statement, "period_end", None)
    if period_end is None:
        return None
    return datetime.combine(period_end, time.max, tzinfo=timezone.utc)


def _statement_sort_key(statement: FinancialStatement) -> tuple[datetime, datetime, int]:
    return (
        _statement_effective_at(statement) or datetime.min.replace(tzinfo=timezone.utc),
        _normalize_datetime(getattr(statement, "last_updated", None)) or datetime.min.replace(tzinfo=timezone.utc),
        int(getattr(statement, "id", 0) or 0),
    )


def _price_observation_at(trade_date: date) -> datetime:
    return datetime.combine(trade_date, time.max, tzinfo=timezone.utc)


def get_company_price_history(session: Session, company_id: int) -> list[PriceHistory]:
    statement = (
        select(PriceHistory)
        .where(PriceHistory.company_id == company_id)
        .order_by(PriceHistory.trade_date.asc())
    )
    return list(session.execute(statement).scalars())


def get_company_financials_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int | None = None,
) -> dict[int, list[FinancialStatement]]:
    normalized_ids = _normalize_company_ids(company_ids)
    if not normalized_ids:
        return {}

    if limit is None:
        return _load_rows_by_company_ids(
            session,
            FinancialStatement,
            normalized_ids,
            filters=(FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,),
            order_by=(FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc()),
        )

    return _load_top_rows_by_company_ids(
        session,
        FinancialStatement,
        normalized_ids,
        limit=limit,
        filters=(FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,),
        order_by=(FinancialStatement.period_end.desc(), FinancialStatement.filing_type.asc()),
    )


def get_latest_company_price_points_by_company_ids(session: Session, company_ids: list[int]) -> dict[int, PriceHistory | None]:
    normalized_ids = _normalize_company_ids(company_ids)
    if not normalized_ids:
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
        .where(PriceHistory.company_id.in_(normalized_ids))
        .subquery()
    )
    rows_statement = (
        select(PriceHistory)
        .join(ranked, PriceHistory.id == ranked.c.id)
        .where(ranked.c.rn == 1)
        .order_by(PriceHistory.company_id.asc())
    )
    result: dict[int, PriceHistory | None] = {company_id: None for company_id in normalized_ids}
    for row in session.execute(rows_statement).scalars():
        result[int(row.company_id)] = row
    return result


def filter_price_history_as_of(price_history: list[PriceHistory], as_of: datetime) -> list[PriceHistory]:
    return [point for point in price_history if _price_observation_at(point.trade_date) <= as_of]


def latest_price_as_of(price_history: list[PriceHistory], as_of: datetime) -> PriceHistory | None:
    visible = filter_price_history_as_of(price_history, as_of)
    return visible[-1] if visible else None


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
    last_checked, _cache_state = cache_state_for_dataset(session, company_id, "derived_metrics")
    if last_checked is not None:
        return last_checked

    statement = select(func.max(DerivedMetricPoint.last_checked)).where(DerivedMetricPoint.company_id == company_id)
    scanned = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if scanned is not None:
        mark_dataset_checked(session, company_id, "derived_metrics", checked_at=scanned, success=True)
    return scanned


def get_company_price_cache_status(session: Session, company_id: int) -> tuple[datetime | None, str]:
    last_checked, cache_state = cache_state_for_dataset(session, company_id, "prices")
    if cache_state != "missing":
        return last_checked, cache_state

    statement = (
        select(PriceHistory.last_checked)
        .where(PriceHistory.company_id == company_id)
        .order_by(PriceHistory.last_checked.desc())
        .limit(1)
    )
    scanned = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if scanned is not None:
        mark_dataset_checked(session, company_id, "prices", checked_at=scanned, success=True)
    return scanned, _cache_state_from_last_checked(scanned)


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


def get_company_insider_trades_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 200,
) -> dict[int, list[InsiderTrade]]:
    return _load_top_rows_by_company_ids(
        session,
        InsiderTrade,
        company_ids,
        limit=limit,
        order_by=(
            InsiderTrade.transaction_date.desc().nullslast(),
            InsiderTrade.filing_date.desc().nullslast(),
            InsiderTrade.id.desc(),
        ),
    )


def get_company_insider_trade_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "insiders")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.insider_trades_last_checked)
    if last_checked is None:
        statement = select(func.max(InsiderTrade.last_checked)).where(InsiderTrade.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "insiders", checked_at=last_checked, success=True)
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


def get_company_form144_filings_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 200,
) -> dict[int, list[Form144Filing]]:
    return _load_top_rows_by_company_ids(
        session,
        Form144Filing,
        company_ids,
        limit=limit,
        order_by=(
            Form144Filing.planned_sale_date.desc().nullslast(),
            Form144Filing.filing_date.desc().nullslast(),
            Form144Filing.id.desc(),
        ),
    )


def get_company_form144_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "form144")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.form144_filings_last_checked)
    if last_checked is None:
        statement = select(func.max(Form144Filing.last_checked)).where(Form144Filing.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "form144", checked_at=last_checked, success=True)
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_earnings_releases(
    session: Session,
    company_id: int,
    *,
    limit: int = 100,
    as_of: datetime | None = None,
) -> list[EarningsRelease]:
    statement = (
        select(EarningsRelease)
        .where(EarningsRelease.company_id == company_id)
        .order_by(
            EarningsRelease.filing_date.desc().nullslast(),
            EarningsRelease.reported_period_end.desc().nullslast(),
            EarningsRelease.id.desc(),
        )
    )
    if as_of is None:
        statement = statement.limit(limit)
        return list(session.execute(statement).scalars())

    rows: list[EarningsRelease] = []
    for row in session.execute(statement).scalars():
        effective_at = _earnings_release_effective_at(row)
        if effective_at is None or effective_at > as_of:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def get_company_earnings_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "earnings")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.earnings_last_checked)
    if last_checked is None:
        statement = select(func.max(EarningsRelease.last_checked)).where(EarningsRelease.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "earnings", checked_at=last_checked, success=True)
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_earnings_model_points(
    session: Session,
    company_id: int,
    *,
    limit: int = 24,
    as_of: datetime | None = None,
) -> list[EarningsModelPoint]:
    statement = (
        select(EarningsModelPoint)
        .where(EarningsModelPoint.company_id == company_id)
        .order_by(EarningsModelPoint.period_end.desc(), EarningsModelPoint.id.desc())
    )
    if as_of is None:
        statement = statement.limit(limit)
        rows = list(session.execute(statement).scalars())
        rows.sort(key=lambda item: item.period_end)
        return rows

    # No-lookahead rule: persisted earnings-model rows only become visible once the
    # derived row itself has been materialized. We therefore filter historical reads
    # by row materialization time instead of period_end so later recomputes do not
    # leak into earlier `as_of` snapshots.
    rows: list[EarningsModelPoint] = []
    for row in session.execute(statement).scalars():
        observed_at = _earnings_model_point_observed_at(row)
        if observed_at is None or observed_at > as_of:
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    rows.sort(key=lambda item: item.period_end)
    return rows


def _earnings_model_point_observed_at(point: EarningsModelPoint) -> datetime | None:
    return _normalize_datetime(getattr(point, "last_updated", None)) or _normalize_datetime(getattr(point, "last_checked", None))


def _earnings_release_effective_at(release: EarningsRelease) -> datetime | None:
    acceptance_at = _normalize_datetime(getattr(release, "filing_acceptance_at", None))
    if acceptance_at is not None:
        return acceptance_at
    filing_date = getattr(release, "filing_date", None)
    if filing_date is not None:
        return datetime.combine(filing_date, time.max, tzinfo=timezone.utc)
    reported_period_end = getattr(release, "reported_period_end", None)
    if reported_period_end is not None:
        return datetime.combine(reported_period_end, time.max, tzinfo=timezone.utc)
    return _normalize_datetime(getattr(release, "last_updated", None)) or _normalize_datetime(getattr(release, "last_checked", None))


def _financial_restatement_effective_at(record: FinancialRestatement) -> datetime | None:
    acceptance_at = _normalize_datetime(getattr(record, "filing_acceptance_at", None))
    if acceptance_at is not None:
        return acceptance_at
    filing_date = getattr(record, "filing_date", None)
    if filing_date is not None:
        return datetime.combine(filing_date, time.max, tzinfo=timezone.utc)
    period_end = getattr(record, "period_end", None)
    if period_end is not None:
        return datetime.combine(period_end, time.max, tzinfo=timezone.utc)
    return _normalize_datetime(getattr(record, "last_updated", None)) or _normalize_datetime(getattr(record, "last_checked", None))


def get_company_earnings_model_cache_status(session: Session, company_id: int) -> tuple[datetime | None, str]:
    last_checked, cache_state = cache_state_for_dataset(session, company_id, "earnings_models")
    if cache_state != "missing":
        return last_checked, cache_state

    statement = select(func.max(EarningsModelPoint.last_checked)).where(EarningsModelPoint.company_id == company_id)
    scanned = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if scanned is not None:
        mark_dataset_checked(session, company_id, "earnings_models", checked_at=scanned, success=True)
    return scanned, _cache_state_from_last_checked(scanned)


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


def get_company_institutional_holdings_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 200,
) -> dict[int, list[InstitutionalHolding]]:
    return _load_top_rows_by_company_ids(
        session,
        InstitutionalHolding,
        company_ids,
        limit=limit,
        order_by=(
            InstitutionalHolding.reporting_date.desc(),
            InstitutionalHolding.market_value.desc().nullslast(),
        ),
        options=(selectinload(InstitutionalHolding.fund),),
    )


def get_company_institutional_holdings_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "institutional")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.institutional_holdings_last_checked)
    if last_checked is None:
        statement = select(func.max(InstitutionalHolding.last_checked)).where(InstitutionalHolding.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "institutional", checked_at=last_checked, success=True)
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


def get_company_beneficial_ownership_reports_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 200,
) -> dict[int, list[BeneficialOwnershipReport]]:
    return _load_top_rows_by_company_ids(
        session,
        BeneficialOwnershipReport,
        company_ids,
        limit=limit,
        order_by=(
            BeneficialOwnershipReport.filing_date.desc().nullslast(),
            BeneficialOwnershipReport.id.desc(),
        ),
        options=(selectinload(BeneficialOwnershipReport.parties),),
    )


def get_company_beneficial_ownership_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "beneficial_ownership")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.beneficial_ownership_last_checked)
    if last_checked is None:
        statement = select(func.max(BeneficialOwnershipReport.last_checked)).where(BeneficialOwnershipReport.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "beneficial_ownership", checked_at=last_checked, success=True)
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


def get_company_filing_events_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 300,
) -> dict[int, list[FilingEvent]]:
    return _load_top_rows_by_company_ids(
        session,
        FilingEvent,
        company_ids,
        limit=limit,
        order_by=(
            FilingEvent.filing_date.desc().nullslast(),
            FilingEvent.report_date.desc().nullslast(),
            FilingEvent.accession_number.desc(),
            FilingEvent.item_code.asc(),
        ),
    )


def get_company_filing_events_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "filings")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.filing_events_last_checked)
    if last_checked is None:
        statement = select(func.max(FilingEvent.last_checked)).where(FilingEvent.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "filings", checked_at=last_checked, success=True)
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


def get_company_capital_markets_events_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 200,
) -> dict[int, list[CapitalMarketsEvent]]:
    return _load_top_rows_by_company_ids(
        session,
        CapitalMarketsEvent,
        company_ids,
        limit=limit,
        order_by=(
            CapitalMarketsEvent.filing_date.desc().nullslast(),
            CapitalMarketsEvent.id.desc(),
        ),
    )


def get_company_comment_letters(
    session: Session,
    company_id: int,
    *,
    limit: int = 200,
) -> list[CommentLetter]:
    statement = (
        select(CommentLetter)
        .where(CommentLetter.company_id == company_id)
        .order_by(CommentLetter.filing_date.desc().nullslast(), CommentLetter.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_comment_letters_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 200,
) -> dict[int, list[CommentLetter]]:
    return _load_top_rows_by_company_ids(
        session,
        CommentLetter,
        company_ids,
        limit=limit,
        order_by=(
            CommentLetter.filing_date.desc().nullslast(),
            CommentLetter.id.desc(),
        ),
    )


def get_company_capital_structure_snapshots(
    session: Session,
    company_id: int,
    *,
    limit: int = 12,
) -> list[CapitalStructureSnapshot]:
    statement = (
        select(CapitalStructureSnapshot)
        .where(CapitalStructureSnapshot.company_id == company_id)
        .order_by(
            CapitalStructureSnapshot.period_end.desc(),
            CapitalStructureSnapshot.last_updated.desc(),
            CapitalStructureSnapshot.id.desc(),
        )
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def get_company_capital_structure_last_checked(session: Session, company_id: int) -> datetime | None:
    last_checked, cache_state = cache_state_for_dataset(session, company_id, "capital_structure")
    if cache_state != "missing":
        return last_checked

    statement = select(func.max(CapitalStructureSnapshot.last_checked)).where(CapitalStructureSnapshot.company_id == company_id)
    scanned = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if scanned is not None:
        mark_dataset_checked(session, company_id, "capital_structure", checked_at=scanned, success=True)
    return scanned


def get_company_capital_markets_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "capital_markets")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.capital_markets_last_checked)
    if last_checked is None:
        statement = select(func.max(CapitalMarketsEvent.last_checked)).where(CapitalMarketsEvent.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "capital_markets", checked_at=last_checked, success=True)
    return last_checked, _cache_state_from_last_checked(last_checked)


def get_company_comment_letters_cache_status(session: Session, company: Company) -> tuple[datetime | None, str]:
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "comment_letters")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.comment_letters_last_checked)
    if last_checked is None:
        statement = select(func.max(CommentLetter.last_checked)).where(CommentLetter.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "comment_letters", checked_at=last_checked, success=True)
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


def get_company_proxy_statements_by_company_ids(
    session: Session,
    company_ids: list[int],
    *,
    limit: int = 60,
) -> dict[int, list[ProxyStatement]]:
    return _load_top_rows_by_company_ids(
        session,
        ProxyStatement,
        company_ids,
        limit=limit,
        order_by=(
            ProxyStatement.filing_date.desc().nullslast(),
            ProxyStatement.id.desc(),
        ),
        options=(
            selectinload(ProxyStatement.exec_comp_rows),
            selectinload(ProxyStatement.vote_results),
        ),
    )


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
    state_last_checked, state_cache = cache_state_for_dataset(session, company.id, "proxy")
    if state_cache != "missing":
        return state_last_checked, state_cache

    last_checked = _normalize_datetime(company.proxy_statements_last_checked)
    if last_checked is None:
        statement = select(func.max(ProxyStatement.last_checked)).where(ProxyStatement.company_id == company.id)
        last_checked = _normalize_datetime(session.execute(statement).scalar_one_or_none())
    if last_checked is not None:
        mark_dataset_checked(session, company.id, "proxy", checked_at=last_checked, success=True)
    return last_checked, _cache_state_from_last_checked(last_checked)


def _build_snapshots_for_companies(session: Session, companies: list[Company]) -> list[CompanyCacheSnapshot]:
    if not companies:
        return []

    latest_checks_by_company_id = _load_latest_checks_by_company_ids(
        session,
        [company.id for company in companies],
    )
    return [_build_snapshot(company, latest_checks_by_company_id.get(company.id)) for company in companies]


def _load_latest_checks_by_company_ids(session: Session, company_ids: list[int]) -> dict[int, datetime | None]:
    normalized_company_ids = sorted({int(company_id) for company_id in company_ids})
    if not normalized_company_ids:
        return {}

    statement_checks_statement = (
        select(
            FinancialStatement.company_id,
            func.max(FinancialStatement.last_checked),
        )
        .where(
            FinancialStatement.company_id.in_(normalized_company_ids),
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .group_by(FinancialStatement.company_id)
    )
    statement_checks = {
        int(company_id): _normalize_datetime(last_checked)
        for company_id, last_checked in session.execute(statement_checks_statement).all()
    }

    refresh_checks_statement = (
        select(
            DatasetRefreshState.company_id,
            func.max(DatasetRefreshState.last_checked),
        )
        .where(
            DatasetRefreshState.company_id.in_(normalized_company_ids),
            DatasetRefreshState.dataset == "financials",
        )
        .group_by(DatasetRefreshState.company_id)
    )
    refresh_checks = {
        int(company_id): _normalize_datetime(last_checked)
        for company_id, last_checked in session.execute(refresh_checks_statement).all()
    }

    latest_checks_by_company_id: dict[int, datetime | None] = {}
    for company_id in normalized_company_ids:
        latest_checks_by_company_id[company_id] = refresh_checks.get(company_id, statement_checks.get(company_id))
    return latest_checks_by_company_id


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
