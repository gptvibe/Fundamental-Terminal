from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.model_engine.calculation_versions import get_model_calculation_version
from app.models import Company, ModelRun

logger = logging.getLogger(__name__)

DEFAULT_MODELS = ["dcf", "reverse_dcf", "piotroski"]
DEFAULT_DB_TIMEOUT_SECONDS = 15.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill cached model rows whose calculation_version predates the current valuation semantics"
    )
    scope_group = parser.add_mutually_exclusive_group(required=False)
    scope_group.add_argument("--tickers", nargs="+", help="One or more cached tickers to backfill, for example: --tickers AAPL MSFT HIMS")
    scope_group.add_argument("--all", action="store_true", help="Backfill all cached companies")
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help="Calculation-versioned models to refresh, for example: --models dcf reverse_dcf piotroski",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would be backfilled without writing new model rows")
    parser.add_argument("--limit", type=int, default=None, help="Only inspect the first N ticker/model work items after scope expansion")
    parser.add_argument(
        "--db-timeout-seconds",
        type=float,
        default=DEFAULT_DB_TIMEOUT_SECONDS,
        help="DB connect and statement timeout in seconds where supported",
    )
    parser.add_argument(
        "--preflight-only",
        "--check-db",
        action="store_true",
        dest="preflight_only",
        help="Create the DB engine/session, run a lightweight SELECT 1 preflight, print status, and exit",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.db_timeout_seconds <= 0:
        parser.error("--db-timeout-seconds must be > 0")
    if not args.preflight_only and not args.all and not args.tickers:
        parser.error("one of the arguments --tickers --all is required unless --preflight-only/--check-db is used")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    requested_models = _normalize_models(args.models, parser)
    requested_tickers = _normalize_tickers(args.tickers or [])

    try:
        logger.info("engine/session creation started")
        engine, session_factory = _create_session_factory(args.db_timeout_seconds)
        logger.info("engine/session creation completed")
    except Exception as exc:
        logger.error("engine/session creation failed: %s", exc)
        _emit_operation_log(phase="engine_session_creation", status="failed", reason=str(exc))
        return 1

    exit_code = 0
    try:
        with session_factory() as session:
            try:
                logger.info("DB preflight started")
                _run_db_preflight(session)
                logger.info("DB preflight completed")
            except Exception as exc:
                logger.error("DB preflight failed: %s", exc)
                _emit_operation_log(phase="db_preflight", status="failed", reason=str(exc))
                return 1

            if args.preflight_only:
                logger.info("DB connectivity status: ok")
                return 0

            try:
                companies = _load_companies(
                    session,
                    tickers=requested_tickers,
                    include_all=args.all,
                    model_count=len(requested_models),
                    limit=args.limit,
                )
            except Exception as exc:
                logger.error("company scope query failed: %s", exc)
                _emit_operation_log(phase="company_scope_query", status="failed", reason=str(exc))
                return 1

            if not companies:
                logger.warning("No cached companies matched the requested scope")
                return 0

            work_items = _build_work_items(companies, requested_models, limit=args.limit)
            if not work_items:
                logger.warning("No ticker/model work items matched the requested scope")
                return 0

            try:
                logger.info("model cache row query started")
                runs_by_company = _load_model_runs_by_company_and_name(
                    session,
                    company_ids=sorted({company.id for company, _model_name in work_items}),
                    model_names=requested_models,
                )
                logger.info("model cache row query completed")
            except Exception as exc:
                logger.error("model cache row query failed: %s", exc)
                _emit_operation_log(phase="model_cache_row_query", status="failed", reason=str(exc))
                return 1

            for company, model_name in work_items:
                runs = runs_by_company.get(company.id, {}).get(model_name, [])
                expected_version = get_model_calculation_version(model_name)
                latest_run = runs[0] if runs else None
                current_run = _current_run(runs, expected_version)
                newer_run = _newer_run(runs, expected_version)
                old_version = _run_calculation_version(latest_run)

                if current_run is not None:
                    _emit_row_log(
                        ticker=company.ticker,
                        model=model_name,
                        old_version=old_version,
                        new_version=expected_version,
                        status="skipped",
                        reason="already_current",
                    )
                    continue

                if newer_run is not None:
                    _emit_row_log(
                        ticker=company.ticker,
                        model=model_name,
                        old_version=old_version,
                        new_version=expected_version,
                        status="skipped",
                        reason=f"newer_calculation_version:{_run_calculation_version(newer_run)}",
                    )
                    continue

                refresh_reason = _refresh_reason(latest_run, expected_version)
                if args.dry_run:
                    _emit_row_log(
                        ticker=company.ticker,
                        model=model_name,
                        old_version=old_version,
                        new_version=expected_version,
                        status="would_recompute",
                        reason=refresh_reason,
                    )
                    continue

                logger.info("ticker/model recomputation started: %s %s", company.ticker, model_name)
                try:
                    results = _compute_model(session, company.id, model_name)
                    session.commit()
                    logger.info("ticker/model recomputation completed: %s %s", company.ticker, model_name)
                except Exception as exc:
                    session.rollback()
                    exit_code = 1
                    logger.error("ticker/model recomputation failed: %s %s -> %s", company.ticker, model_name, exc)
                    _emit_row_log(
                        ticker=company.ticker,
                        model=model_name,
                        old_version=old_version,
                        new_version=expected_version,
                        status="failed",
                        reason=str(exc),
                    )
                    continue

                result = results[0] if results else None
                if result is None:
                    _emit_row_log(
                        ticker=company.ticker,
                        model=model_name,
                        old_version=old_version,
                        new_version=expected_version,
                        status="skipped",
                        reason="model_engine_returned_no_result",
                    )
                    continue

                _emit_row_log(
                    ticker=company.ticker,
                    model=model_name,
                    old_version=old_version,
                    new_version=expected_version,
                    status="cached" if result.cached else "recomputed",
                    reason="already_current_after_recheck" if result.cached else refresh_reason,
                )
    finally:
        engine.dispose()

    return exit_code


def _normalize_models(model_names: list[str], parser: argparse.ArgumentParser) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in model_names:
        for part in raw_value.split(","):
            model_name = part.strip().lower()
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            normalized.append(model_name)
    if not normalized:
        parser.error("At least one model name is required")
    unsupported = [model_name for model_name in normalized if get_model_calculation_version(model_name) is None]
    if unsupported:
        parser.error(
            "--models only supports calculation-versioned models: "
            f"{', '.join(DEFAULT_MODELS)}. Unsupported values: {', '.join(sorted(set(unsupported)))}"
        )
    return normalized


def _normalize_tickers(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        for part in raw_value.split(","):
            ticker = part.strip().upper().replace(".", "-")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            normalized.append(ticker)
    return normalized


def _create_session_factory(timeout_seconds: float) -> tuple[Engine, sessionmaker[Session]]:
    url = make_url(settings.database_url)
    connect_args: dict[str, Any] = {}
    timeout_ceiling = max(1, int(math.ceil(timeout_seconds)))
    if url.get_backend_name() == "postgresql":
        connect_args["connect_timeout"] = timeout_ceiling
        connect_args["options"] = f"-c statement_timeout={int(timeout_seconds * 1000)}"
        if url.host == "localhost" and "hostaddr" not in url.query:
            # Avoid dual-stack localhost retries turning one bounded timeout into two sequential waits.
            connect_args["hostaddr"] = "127.0.0.1"
    else:
        logger.warning(
            "statement timeout is not configured for dialect '%s'; only pool/connect timeouts are enforced",
            url.get_backend_name(),
        )

    engine = create_engine(
        url.render_as_string(hide_password=False),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=timeout_ceiling,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args=connect_args,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return engine, session_factory


def _run_db_preflight(session: Session) -> None:
    result = session.execute(text("SELECT 1"))
    result.scalar_one()


def _load_companies(
    session: Session,
    *,
    tickers: list[str] | None,
    include_all: bool,
    model_count: int,
    limit: int | None,
) -> list[Company]:
    company_limit: int | None = None
    if include_all and limit is not None:
        company_limit = max(1, math.ceil(limit / max(model_count, 1)))

    statement = select(Company).order_by(Company.ticker.asc())
    if include_all:
        if company_limit is not None:
            statement = statement.limit(company_limit)
        return list(session.execute(statement).scalars())

    normalized_tickers = list(tickers or [])
    if not normalized_tickers:
        return []

    statement = statement.where(Company.ticker.in_(normalized_tickers))
    companies = list(session.execute(statement).scalars())
    found_tickers = {company.ticker for company in companies}
    for ticker in normalized_tickers:
        if ticker not in found_tickers:
            _emit_row_log(
                ticker=ticker,
                model="*",
                old_version=None,
                new_version=None,
                status="failed",
                reason="company_not_found",
            )
    return companies


def _build_work_items(companies: list[Company], model_names: list[str], *, limit: int | None) -> list[tuple[Company, str]]:
    work_items: list[tuple[Company, str]] = []
    for company in companies:
        for model_name in model_names:
            work_items.append((company, model_name))
            if limit is not None and len(work_items) >= limit:
                return work_items
    return work_items


def _load_model_runs_by_company_and_name(
    session: Session,
    *,
    company_ids: list[int],
    model_names: list[str],
) -> dict[int, dict[str, list[ModelRun]]]:
    if not company_ids or not model_names:
        return {}
    statement = (
        select(ModelRun)
        .where(ModelRun.company_id.in_(company_ids), ModelRun.model_name.in_(model_names))
        .order_by(ModelRun.company_id.asc(), ModelRun.model_name.asc(), ModelRun.created_at.desc(), ModelRun.id.desc())
    )
    rows = list(session.execute(statement).scalars())
    grouped: dict[int, dict[str, list[ModelRun]]] = {company_id: {model_name: [] for model_name in model_names} for company_id in company_ids}
    for row in rows:
        grouped.setdefault(int(row.company_id), {}).setdefault(row.model_name.lower(), []).append(row)
    return grouped


def _current_run(runs: list[ModelRun], expected_version: str | None) -> ModelRun | None:
    if expected_version is None:
        return None
    for run in runs:
        if _run_calculation_version(run) == expected_version:
            return run
    return None


def _newer_run(runs: list[ModelRun], expected_version: str | None) -> ModelRun | None:
    if expected_version is None:
        return None
    for run in runs:
        actual_version = _run_calculation_version(run)
        if actual_version is None:
            continue
        if _compare_calculation_version(actual_version, expected_version) > 0:
            return run
    return None


def _compare_calculation_version(actual_version: str, expected_version: str) -> int:
    actual_key = _version_sort_key(actual_version)
    expected_key = _version_sort_key(expected_version)
    if actual_key is None or expected_key is None:
        return 0
    actual_base, actual_number = actual_key
    expected_base, expected_number = expected_key
    if actual_base != expected_base:
        return 0
    if actual_number > expected_number:
        return 1
    if actual_number < expected_number:
        return -1
    return 0


def _version_sort_key(value: str) -> tuple[str, int] | None:
    prefix, separator, suffix = value.rpartition("_v")
    if not separator or not suffix.isdigit():
        return None
    return prefix, int(suffix)


def _run_calculation_version(run: ModelRun | None) -> str | None:
    if run is None:
        return None
    calculation_version = getattr(run, "calculation_version", None)
    if isinstance(calculation_version, str) and calculation_version.strip():
        return calculation_version.strip()
    result = getattr(run, "result", None)
    if isinstance(result, dict):
        raw_value = result.get("calculation_version")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    return None


def _refresh_reason(run: ModelRun | None, expected_version: str | None) -> str:
    if run is None:
        return "missing_model_row"
    actual_version = _run_calculation_version(run)
    if actual_version is None:
        return "missing_calculation_version"
    if expected_version is None:
        return "unversioned_model"
    if actual_version != expected_version:
        return f"outdated_calculation_version:{actual_version}"
    return "already_current"


def _emit_operation_log(*, phase: str, status: str, reason: str) -> None:
    print(json.dumps({"phase": phase, "reason": reason, "status": status}, sort_keys=True))


def _emit_row_log(*, ticker: str, model: str, old_version: str | None, new_version: str | None, status: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "ticker": ticker,
                "model": model,
                "old_version": old_version,
                "new_version": new_version,
                "status": status,
                "reason": reason,
            },
            sort_keys=True,
        )
    )


def _compute_model(session: Session, company_id: int, model_name: str):
    from app.model_engine.engine import ModelEngine

    return ModelEngine(session).compute_models(company_id, model_names=[model_name], force=False)


if __name__ == "__main__":
    raise SystemExit(main())
