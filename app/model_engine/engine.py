from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_engine
from app.model_engine.registry import CORE_MODEL_NAMES, MODEL_REGISTRY
from app.model_engine.types import CompanyDataset, FinancialPoint, ModelDefinition
from app.model_engine.utils import serialize_period
from app.models import Company, FinancialStatement, ModelRun
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

        statements = _load_canonical_financials(self.session, company_id)
        dataset = _build_company_dataset(company, statements)
        if not dataset.financials:
            return []

        definitions = _select_definitions(model_names)
        results: list[ModelJobResult] = []
        if definitions and reporter is not None and reporter.enabled:
            reporter.step("models", "Computing financial models…")

        for definition in definitions:
            if reporter is not None and reporter.enabled:
                reporter.step("models", f"Running {definition.name} v{definition.version}…")
            input_payload = _build_input_payload(dataset, definition)
            cached_run = _latest_model_run(self.session, company_id, definition)
            if not force and cached_run is not None and _matching_signature(cached_run.input_periods, input_payload):
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

            model_run = ModelRun(
                company_id=company.id,
                model_name=definition.name,
                model_version=definition.version,
                input_periods=input_payload,
                result=definition.compute(dataset),
            )
            self.session.add(model_run)
            self.session.flush()
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

        return results


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


def _load_canonical_financials(session: Session, company_id: int) -> list[FinancialStatement]:
    statement = (
        select(FinancialStatement)
        .where(
            FinancialStatement.company_id == company_id,
            FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
        )
        .order_by(FinancialStatement.period_end.desc(), FinancialStatement.last_updated.desc(), FinancialStatement.id.desc())
    )
    return list(session.execute(statement).scalars())


def _build_company_dataset(company: Company, statements: list[FinancialStatement]) -> CompanyDataset:
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
            data=dict(statement.data or {}),
        )

    financials = tuple(deduped.values())
    return CompanyDataset(
        company_id=company.id,
        ticker=company.ticker,
        name=company.name,
        sector=company.sector,
        financials=financials,
    )


def _build_input_payload(dataset: CompanyDataset, definition: ModelDefinition) -> dict[str, Any]:
    periods = [serialize_period(point) for point in dataset.financials]
    config = _model_config(definition)
    signature_input = {"periods": periods}
    if config:
        signature_input["config"] = config
    signature = hashlib.sha256(
        json.dumps(signature_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "model_name": definition.name,
        "model_version": definition.version,
        "statement_type": CANONICAL_STATEMENT_TYPE,
        "signature": signature,
        "config": config,
        "periods": periods,
    }


def _model_config(definition: ModelDefinition) -> dict[str, Any]:
    if definition.name == "dupont":
        from app.model_engine.models import dupont as dupont_model

        return {"mode": dupont_model.get_mode()}
    return {}


def _latest_model_run(session: Session, company_id: int, definition: ModelDefinition) -> ModelRun | None:
    statement = (
        select(ModelRun)
        .where(
            ModelRun.company_id == company_id,
            ModelRun.model_name == definition.name,
            ModelRun.model_version == definition.version,
        )
        .order_by(ModelRun.created_at.desc(), ModelRun.id.desc())
        .limit(1)
    )
    return session.execute(statement).scalar_one_or_none()


def _matching_signature(existing_input: object, new_input: dict[str, Any]) -> bool:
    if not isinstance(existing_input, dict):
        return False
    return existing_input.get("signature") == new_input.get("signature")
