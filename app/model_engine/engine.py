from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal, get_engine
from app.observability import emit_structured_log
from app.model_engine.calculation_versions import has_current_calculation_version
from app.model_engine.registry import CORE_MODEL_NAMES, MODEL_REGISTRY
from app.model_engine.types import CompanyDataset, FinancialPoint, MarketSnapshot, ModelDefinition
from app.model_engine.utils import serialize_period
from app.models import Company, FinancialStatement, ModelRun, PriceHistory
from app.services.risk_free_rate import get_latest_risk_free_rate
from app.services.status_stream import JobReporter

logger = logging.getLogger(__name__)

CANONICAL_STATEMENT_TYPE = "canonical_xbrl"


@dataclass(slots=True)
class ModelJobResult:
    company_id: int
    ticker: str
    model_name: str
    model_version: str
    cached: bool
    created_model_run_id: int | None


class ModelEngine:
    def __init__(self, session: Session) -> None:
        self.session = session

    def compute_models(
        self,
        company_id: int,
        *,
        model_names: list[str] | None = None,
        force: bool = False,
        reporter: JobReporter | None = None,
    ) -> list[ModelJobResult]:
        company = self.session.get(Company, company_id)
        if company is None:
            raise ValueError(f"Company {company_id} does not exist")

        statements = _load_canonical_financials(
            self.session,
            company_id,
            limit=settings.model_engine_max_financial_periods,
        )
        market_snapshot = _load_latest_market_snapshot(self.session, company_id)
        dataset = _build_company_dataset(company, statements, market_snapshot)
        emit_structured_log(
            logger,
            "model.compute.start",
            company_id=company.id,
            ticker=company.ticker,
            job_id=reporter.job_id if reporter is not None else None,
            requested_models=model_names or CORE_MODEL_NAMES,
            force=force,
            financial_periods=len(dataset.financials),
            has_market_snapshot=dataset.market_snapshot is not None,
        )
        if not dataset.financials:
            emit_structured_log(
                logger,
                "model.compute.skipped",
                company_id=company.id,
                ticker=company.ticker,
                job_id=reporter.job_id if reporter is not None else None,
                reason="missing_financials",
            )
            return []

        definitions = _select_definitions(model_names)
        cached_by_key = _latest_model_runs(self.session, company_id, definitions)
        results: list[ModelJobResult] = []
        if definitions and reporter is not None and reporter.enabled:
            reporter.step("models", "Computing financial models…")

        for definition in definitions:
            if reporter is not None and reporter.enabled:
                stage = "valuation" if definition.name in {"dcf", "reverse_dcf", "roic", "capital_allocation"} else "models"
                reporter.step(stage, f"Running {definition.name} v{definition.version}…")
            input_payload = _build_input_payload(dataset, definition)
            cached_run = cached_by_key.get((definition.name, definition.version))
            if not force and cached_run is not None and _matching_signature(cached_run.input_periods, input_payload):
                emit_structured_log(
                    logger,
                    "model.compute.cached",
                    company_id=company.id,
                    ticker=company.ticker,
                    job_id=reporter.job_id if reporter is not None else None,
                    model_name=definition.name,
                    model_version=definition.version,
                    model_run_id=cached_run.id,
                )
                results.append(
                    ModelJobResult(
                        company_id=company.id,
                        ticker=company.ticker,
                        model_name=definition.name,
                        model_version=definition.version,
                        cached=True,
                        created_model_run_id=cached_run.id,
                    )
                )
                continue

            started = time.perf_counter()
            computed_result = definition.compute(dataset)
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            model_run = ModelRun(
                company_id=company.id,
                model_name=definition.name,
                model_version=definition.version,
                calculation_version=definition.calculation_version,
                input_periods=input_payload,
                result=computed_result,
            )
            self.session.add(model_run)
            self.session.flush()
            emit_structured_log(
                logger,
                "model.compute.persisted",
                company_id=company.id,
                ticker=company.ticker,
                job_id=reporter.job_id if reporter is not None else None,
                model_name=definition.name,
                model_version=definition.version,
                model_run_id=model_run.id,
                elapsed_ms=elapsed_ms,
                model_status=(computed_result.get("model_status") if isinstance(computed_result, dict) else None),
            )
            results.append(
                ModelJobResult(
                    company_id=company.id,
                    ticker=company.ticker,
                    model_name=definition.name,
                    model_version=definition.version,
                    cached=False,
                    created_model_run_id=model_run.id,
                )
            )

        emit_structured_log(
            logger,
            "model.compute.complete",
            company_id=company.id,
            ticker=company.ticker,
            job_id=reporter.job_id if reporter is not None else None,
            requested_models=[definition.name for definition in definitions],
            result_count=len(results),
            cached_count=sum(1 for item in results if item.cached),
        )
        return results

    def evaluate_models(
        self,
        dataset: CompanyDataset,
        *,
        model_names: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        definitions = _select_definitions(model_names)
        evaluated_at = created_at or datetime.now(timezone.utc)
        payloads: list[dict[str, Any]] = []
        for definition in definitions:
            payloads.append(
                {
                    "model_name": definition.name,
                    "model_version": definition.version,
                    "calculation_version": definition.calculation_version,
                    "created_at": evaluated_at,
                    "input_periods": _build_input_payload(dataset, definition),
                    "result": definition.compute(dataset),
                }
            )
        return payloads


def precompute_core_models(
    session: Session,
    company_id: int,
    reporter: JobReporter | None = None,
) -> list[ModelJobResult]:
    engine = ModelEngine(session)
    return engine.compute_models(company_id, model_names=CORE_MODEL_NAMES, reporter=reporter)


def run_model_job(identifier: str, model_names: list[str] | None = None, force: bool = False) -> list[dict[str, Any]]:
    get_engine()
    with SessionLocal() as session:
        company = _find_company(session, identifier)
        if company is None:
            raise ValueError(f"Company '{identifier}' not found in PostgreSQL cache")

        results = ModelEngine(session).compute_models(company.id, model_names=model_names, force=force)
        session.commit()
        return [asdict(result) for result in results]


def worker_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute cached financial models from PostgreSQL")
    parser.add_argument("identifiers", nargs="+", help="Ticker or company ID already present in PostgreSQL")
    parser.add_argument("--models", default="", help="Comma-separated model names")
    parser.add_argument("--force", action="store_true", help="Recompute even when cached inputs match")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    requested_models = [item.strip().lower() for item in args.models.split(",") if item.strip()] or None

    exit_code = 0
    for identifier in args.identifiers:
        try:
            payload = run_model_job(identifier=identifier, model_names=requested_models, force=args.force)
            print(json.dumps(payload, default=str))
        except Exception as exc:
            exit_code = 1
            logger.exception("Model job failed for %s: %s", identifier, exc)

    return exit_code


def _select_definitions(model_names: list[str] | None) -> list[ModelDefinition]:
    if model_names is None:
        return list(MODEL_REGISTRY.values())

    definitions: list[ModelDefinition] = []
    for model_name in model_names:
        normalized_name = model_name.lower()
        definition = MODEL_REGISTRY.get(normalized_name)
        if definition is None:
            raise ValueError(f"Unsupported model '{model_name}'")
        definitions.append(definition)
    return definitions


def _find_company(session: Session, identifier: str) -> Company | None:
    lookup = identifier.strip()
    if not lookup:
        return None

    if lookup.isdigit():
        company = session.get(Company, int(lookup))
        if company is not None:
            return company

    statement: Select[tuple[Company]] = select(Company).where(Company.ticker == lookup.upper())
    return session.execute(statement).scalar_one_or_none()


def _load_canonical_financials(session: Session, company_id: int, *, limit: int) -> list[FinancialStatement]:
    statement = (
        select(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.period_end.desc(), FinancialStatement.last_updated.desc(), FinancialStatement.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).scalars())


def _load_latest_market_snapshot(session: Session, company_id: int) -> MarketSnapshot | None:
    if settings.strict_official_mode:
        return None

    statement = (
        select(PriceHistory)
        .where(PriceHistory.company_id == company_id)
        .order_by(PriceHistory.trade_date.desc(), PriceHistory.last_updated.desc(), PriceHistory.id.desc())
        .limit(1)
    )
    latest_price = session.execute(statement).scalar_one_or_none()
    if latest_price is None:
        return None
    return build_market_snapshot(latest_price)


def build_market_snapshot(price_row: PriceHistory | Any) -> MarketSnapshot | None:
    if price_row is None:
        return None
    return MarketSnapshot(
        latest_price=float(price_row.close) if getattr(price_row, "close", None) is not None else None,
        price_date=getattr(price_row, "trade_date", None),
        price_source=getattr(price_row, "source", None),
        observation_timestamp=_market_observation_timestamp(getattr(price_row, "trade_date", None)),
        fetch_timestamp=getattr(price_row, "fetch_timestamp", None),
    )


def build_company_dataset(
    company: Company,
    statements: list[FinancialStatement],
    market_snapshot: MarketSnapshot | None,
    *,
    as_of_date: datetime | None = None,
) -> CompanyDataset:
    deduped: dict[tuple[object, ...], FinancialPoint] = {}
    for statement in statements:
        key = (statement.period_start, statement.period_end, statement.filing_type)
        if key in deduped:
            continue
        deduped[key] = FinancialPoint(
            statement_id=statement.id,
            filing_type=statement.filing_type,
            period_start=statement.period_start,
            period_end=statement.period_end,
            source=statement.source,
            last_updated=statement.last_updated,
            filing_acceptance_at=getattr(statement, "filing_acceptance_at", None),
            fetch_timestamp=getattr(statement, "fetch_timestamp", None),
            data=dict(statement.data or {}),
        )

    financials = tuple(deduped.values())
    return CompanyDataset(
        company_id=company.id,
        ticker=company.ticker,
        name=company.name,
        sector=company.sector,
        market_sector=company.market_sector,
        market_industry=company.market_industry,
        market_snapshot=market_snapshot,
        financials=financials,
        as_of_date=as_of_date.date() if as_of_date is not None else None,
    )


def _build_company_dataset(
    company: Company,
    statements: list[FinancialStatement],
    market_snapshot: MarketSnapshot | None,
    *,
    as_of_date: datetime | None = None,
) -> CompanyDataset:
    return build_company_dataset(
        company,
        statements,
        market_snapshot,
        as_of_date=as_of_date,
    )


def _build_input_payload(dataset: CompanyDataset, definition: ModelDefinition) -> dict[str, Any]:
    periods = [serialize_period(point) for point in dataset.financials]
    market_snapshot_payload = _serialize_market_snapshot(dataset.market_snapshot)
    config = _model_config(dataset, definition)
    signature_input = {"periods": periods}
    if definition.calculation_version is not None:
        signature_input["calculation_version"] = definition.calculation_version
    if dataset.as_of_date is not None:
        signature_input["as_of_date"] = dataset.as_of_date.isoformat()
    if market_snapshot_payload:
        signature_input["market_snapshot"] = market_snapshot_payload
    if config:
        signature_input["config"] = config
    signature = hashlib.sha256(
        json.dumps(signature_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "model_name": definition.name,
        "model_version": definition.version,
        "calculation_version": definition.calculation_version,
        "as_of_date": dataset.as_of_date.isoformat() if dataset.as_of_date is not None else None,
        "statement_type": CANONICAL_STATEMENT_TYPE,
        "signature": signature,
        "config": config,
        "market_snapshot": market_snapshot_payload,
        "periods": periods,
    }


def _serialize_market_snapshot(snapshot: MarketSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        "latest_price": snapshot.latest_price,
        "price_date": snapshot.price_date.isoformat() if snapshot.price_date is not None else None,
        "price_source": snapshot.price_source,
        "observation_timestamp": snapshot.observation_timestamp.isoformat() if snapshot.observation_timestamp is not None else None,
        "fetch_timestamp": snapshot.fetch_timestamp.isoformat() if snapshot.fetch_timestamp is not None else None,
    }


def _model_config(dataset: CompanyDataset, definition: ModelDefinition) -> dict[str, Any]:
    if definition.name == "dupont":
        from app.model_engine.models import dupont as dupont_model

        return {"mode": dupont_model.get_mode()}
    if definition.name in {"dcf", "reverse_dcf", "roic"}:
        snapshot = get_latest_risk_free_rate(dataset.as_of_date)
        return {
            "risk_free_rate": {
                "source_name": snapshot.source_name,
                "tenor": snapshot.tenor,
                "observation_date": snapshot.observation_date.isoformat(),
                "rate_used": snapshot.rate_used,
            }
        }
    return {}


def _market_observation_timestamp(trade_date) -> datetime | None:
    if trade_date is None:
        return None
    return datetime.combine(trade_date, datetime.max.time(), tzinfo=timezone.utc)


def _latest_model_run(session: Session, company_id: int, definition: ModelDefinition) -> ModelRun | None:
    return _latest_model_runs(session, company_id, [definition]).get((definition.name, definition.version))


def _latest_model_runs(
    session: Session,
    company_id: int,
    definitions: list[ModelDefinition],
) -> dict[tuple[str, str], ModelRun]:
    if not definitions:
        return {}

    names = sorted({definition.name for definition in definitions})
    versions = sorted({definition.version for definition in definitions})
    statement = (
        select(ModelRun)
        .where(
            ModelRun.company_id == company_id,
            ModelRun.model_name.in_(names),
            ModelRun.model_version.in_(versions),
        )
        .order_by(ModelRun.model_name.asc(), ModelRun.model_version.asc(), ModelRun.created_at.desc(), ModelRun.id.desc())
    )
    rows = list(session.execute(statement).scalars())

    latest: dict[tuple[str, str], ModelRun] = {}
    definitions_by_key = {(definition.name, definition.version): definition for definition in definitions}
    for row in rows:
        key = (row.model_name, row.model_version)
        if key in latest:
            continue
        definition = definitions_by_key.get(key)
        if definition is not None and not _matches_current_calculation_version(row, definition):
            continue
        latest[key] = row
    return latest


def _matching_signature(existing_input: object, new_input: dict[str, Any]) -> bool:
    if not isinstance(existing_input, dict):
        return False
    return existing_input.get("signature") == new_input.get("signature")


def _model_run_calculation_version(model_run: ModelRun) -> str | None:
    calculation_version = getattr(model_run, "calculation_version", None)
    if isinstance(calculation_version, str) and calculation_version.strip():
        return calculation_version.strip()
    result = model_run.result if isinstance(model_run.result, dict) else {}
    raw_value = result.get("calculation_version")
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    return None


def _matches_current_calculation_version(model_run: ModelRun, definition: ModelDefinition) -> bool:
    return has_current_calculation_version(definition.name, _model_run_calculation_version(model_run))
