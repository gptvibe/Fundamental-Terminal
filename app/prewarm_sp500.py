from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

from app.db import SessionLocal, get_engine
from app.model_engine.engine import ModelEngine
from app.model_engine.registry import MODEL_REGISTRY
from app.services.sec_edgar import CompanyIdentity, EdgarClient, EdgarIngestionService, upsert_company_identity
from app.services.cache_queries import get_company_snapshot
from app.services.sp500 import DEFAULT_SP500_TICKERS_PATH, load_sp500_tickers, normalize_index_ticker


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SeedSummary:
    upserted: int = 0
    upserted_tickers: list[str] | None = None
    missing_from_sec: list[str] | None = None


def prewarm_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed and prewarm S&P 500 companies into PostgreSQL")
    parser.add_argument(
        "--mode",
        choices=("seed", "core", "refresh"),
        default="refresh",
        help="Seed only, prewarm core financial caches, or run the full refresh pipeline.",
    )
    parser.add_argument(
        "--constituents-file",
        default=str(DEFAULT_SP500_TICKERS_PATH),
        help="Path to a newline-delimited list of S&P 500 tickers.",
    )
    parser.add_argument("--force", action="store_true", help="Bypass the freshness window during refresh mode.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N tickers after --start-at.")
    parser.add_argument("--start-at", type=int, default=1, help="1-based index into the constituent list.")
    parser.add_argument("--dry-run", action="store_true", help="Print the selected workload without touching the DB.")
    args = parser.parse_args(argv)

    if args.start_at < 1:
        parser.error("--start-at must be >= 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    constituents_path = Path(args.constituents_file)
    tickers = load_sp500_tickers(constituents_path)
    selected_tickers = _select_tickers(tickers, start_at=args.start_at, limit=args.limit)
    if not selected_tickers:
        logger.warning("No S&P 500 tickers selected from %s", constituents_path)
        return 0

    logger.info(
        "Loaded %s S&P 500 tickers from %s; processing %s ticker(s) starting at #%s",
        len(tickers),
        constituents_path,
        len(selected_tickers),
        args.start_at,
    )

    if args.dry_run:
        logger.info("Dry run only. First selected tickers: %s", ", ".join(selected_tickers[:10]))
        return 0

    seed_summary = seed_sp500_companies(selected_tickers)
    if seed_summary.missing_from_sec:
        logger.warning(
            "Skipped %s ticker(s) that were missing from the SEC ticker directory: %s",
            len(seed_summary.missing_from_sec),
            ", ".join(seed_summary.missing_from_sec),
        )
    logger.info("Seeded or updated %s company row(s)", seed_summary.upserted)

    if args.mode == "seed":
        return 0

    if not seed_summary.upserted_tickers:
        logger.error("No S&P 500 tickers could be seeded from the SEC directory; aborting refresh phase.")
        return 1

    return _refresh_seeded_companies(
        seed_summary.upserted_tickers or [],
        force=args.force,
        core_only=args.mode == "core",
    )


def seed_sp500_companies(tickers: list[str]) -> SeedSummary:
    client = EdgarClient()
    try:
        identities_by_ticker = _build_sec_identity_map(client)
    finally:
        client.close()

    get_engine()
    missing_from_sec: list[str] = []
    upserted_tickers: list[str] = []
    upserted = 0
    with SessionLocal() as session:
        for ticker in tickers:
            identity = identities_by_ticker.get(normalize_index_ticker(ticker))
            if identity is None:
                missing_from_sec.append(ticker)
                continue

            upsert_company_identity(session, identity)
            upserted += 1
            upserted_tickers.append(identity.ticker)

        session.commit()

    return SeedSummary(upserted=upserted, upserted_tickers=upserted_tickers, missing_from_sec=missing_from_sec)


def _refresh_seeded_companies(tickers: list[str], *, force: bool, core_only: bool) -> int:
    service = EdgarIngestionService()
    refreshed = 0
    skipped = 0
    failed = 0
    try:
        for index, ticker in enumerate(tickers, start=1):
            logger.info("[%s/%s] Refreshing %s", index, len(tickers), ticker)
            try:
                result = service.refresh_company(
                    identifier=ticker,
                    force=force,
                    refresh_insider_data=not core_only,
                    refresh_institutional_data=not core_only,
                )
            except Exception:
                failed += 1
                logger.exception("Prewarm failed for %s", ticker)
                continue

            if result.status == "skipped":
                skipped += 1
            else:
                refreshed += 1

            if not core_only:
                warmed_models, total_models = _warm_company_model_cache(ticker)
                logger.info(
                    "[%s/%s] %s -> warmed %s/%s model outputs",
                    index,
                    len(tickers),
                    ticker,
                    warmed_models,
                    total_models,
                )

            logger.info("[%s/%s] %s -> %s (%s)", index, len(tickers), ticker, result.status, result.detail)
    finally:
        service.close()

    logger.info(
        "Prewarm complete: %s refreshed, %s skipped, %s failed",
        refreshed,
        skipped,
        failed,
    )
    return 1 if failed else 0


def _warm_company_model_cache(ticker: str) -> tuple[int, int]:
    model_names = list(MODEL_REGISTRY.keys())
    if not model_names:
        return 0, 0

    get_engine()
    with SessionLocal() as session:
        snapshot = get_company_snapshot(session, ticker)
        if snapshot is None:
            raise ValueError(f"Unable to warm model cache for unknown ticker '{ticker}'")

        results = ModelEngine(session).compute_models(snapshot.company.id, model_names=model_names, force=False)
        if any(not result.cached for result in results):
            session.commit()

    return sum(1 for result in results if not result.cached), len(results)


def _build_sec_identity_map(client: EdgarClient) -> dict[str, CompanyIdentity]:
    identities: dict[str, CompanyIdentity] = {}
    for item in client.get_company_tickers():
        ticker = normalize_index_ticker(str(item.get("ticker", "")))
        raw_cik = str(item.get("cik_str", "")).strip()
        name = str(item.get("title", "")).strip() or ticker
        if not ticker or not raw_cik:
            continue

        cik = raw_cik.zfill(10)
        identities[ticker] = CompanyIdentity(cik=cik, ticker=ticker, name=name)
    return identities


def _select_tickers(tickers: list[str], *, start_at: int, limit: int | None) -> list[str]:
    selected = tickers[start_at - 1 :]
    if limit is not None:
        selected = selected[:limit]
    return selected


if __name__ == "__main__":
    raise SystemExit(prewarm_main())
