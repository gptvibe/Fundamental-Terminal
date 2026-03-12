from __future__ import annotations

import logging
import asyncio
import html
import json
import re
import time
from datetime import date as DateType, datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db_session
from app.model_engine.engine import ModelEngine
from app.model_engine.models import dupont as dupont_model
from app.models import FinancialStatement, InsiderTrade, ModelRun, PriceHistory
from app.services.insider_activity import build_insider_activity_summary
from app.services.institutional_holdings import get_institutional_fund_strategy
from app.services.peer_comparison import build_peer_comparison
from app.services import (
    CompanyCacheSnapshot,
    get_company_financials,
    get_company_insider_trade_cache_status,
    get_company_insider_trades,
    get_company_institutional_holdings,
    get_company_institutional_holdings_cache_status,
    get_company_models,
    get_company_price_cache_status,
    get_company_price_history,
    get_company_snapshot,
    get_company_snapshot_by_cik,
    queue_company_refresh,
    search_company_snapshots,
    status_broker,
)
from app.services.sec_edgar import EdgarClient, FilingMetadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Financial Cache API", version="1.1.0")

Number = int | float | None
CORE_FILING_TIMELINE_FORMS = {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"}
MAX_FILING_TIMELINE_ITEMS = 60
ALLOWED_SEC_EMBED_HOSTS = {"www.sec.gov", "sec.gov", "data.sec.gov"}
ALLOWED_SEC_EMBED_MIME_PREFIXES = ("text/html", "application/html", "application/xhtml+xml", "text/plain")
ALLOWED_SEC_EMBED_EXTENSIONS = (".htm", ".html", ".xhtml", ".txt")
MAX_SEC_EMBED_BYTES = 5 * 1024 * 1024
FILINGS_TIMELINE_TTL_SECONDS = settings.sec_filings_timeline_ttl_seconds


class RefreshState(BaseModel):
    triggered: bool = Field(default=False)
    reason: Literal["manual", "missing", "stale", "fresh", "none"] = Field(default="none")
    ticker: str | None = Field(default=None)
    job_id: str | None = Field(default=None)


class CompanyPayload(BaseModel):
    ticker: str
    cik: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    last_checked: datetime | None = None
    last_checked_financials: datetime | None = None
    last_checked_prices: datetime | None = None
    last_checked_insiders: datetime | None = None
    last_checked_institutional: datetime | None = None
    last_checked_filings: datetime | None = None
    cache_state: Literal["fresh", "stale", "missing"]


class CompanySearchResponse(BaseModel):
    query: str
    results: list[CompanyPayload]
    refresh: RefreshState


class CompanyResolutionResponse(BaseModel):
    query: str
    resolved: bool
    ticker: str | None = None
    name: str | None = None
    error: Literal["not_found", "lookup_failed"] | None = None


class FinancialSegmentPayload(BaseModel):
    segment_id: str
    segment_name: str
    axis_key: str | None = None
    axis_label: str | None = None
    kind: Literal["business", "geographic", "other"] = "business"
    revenue: Number = None
    share_of_revenue: Number = None


class FinancialPayload(BaseModel):
    filing_type: str
    statement_type: str
    period_start: DateType
    period_end: DateType
    source: str
    last_updated: datetime
    last_checked: datetime
    revenue: Number = None
    gross_profit: Number = None
    operating_income: Number = None
    net_income: Number = None
    total_assets: Number = None
    total_liabilities: Number = None
    operating_cash_flow: Number = None
    capex: Number = None
    acquisitions: Number = None
    debt_changes: Number = None
    dividends: Number = None
    share_buybacks: Number = None
    free_cash_flow: Number = None
    eps: Number = None
    shares_outstanding: Number = None
    segment_breakdown: list[FinancialSegmentPayload] = Field(default_factory=list)


class PriceHistoryPayload(BaseModel):
    date: DateType
    close: float
    volume: int | None = None


class CompanyFinancialsResponse(BaseModel):
    company: CompanyPayload | None
    financials: list[FinancialPayload]
    price_history: list[PriceHistoryPayload]
    refresh: RefreshState


class CompanyFactsResponse(BaseModel):
    facts: dict[str, Any]


class InsiderTradePayload(BaseModel):
    name: str
    role: str | None = None
    date: DateType | None = None
    action: str
    transaction_code: str | None = None
    shares: Number = None
    price: Number = None
    value: Number = None
    ownership_after: Number = None
    is_10b5_1: bool


class InsiderActivityMetricsPayload(BaseModel):
    total_buy_value: float
    total_sell_value: float
    net_value: float
    unique_insiders_buying: int
    unique_insiders_selling: int


class InsiderActivitySummaryPayload(BaseModel):
    sentiment: Literal["bullish", "neutral", "bearish"]
    summary_lines: list[str]
    metrics: InsiderActivityMetricsPayload


class CompanyInsiderTradesResponse(BaseModel):
    company: CompanyPayload | None
    insider_trades: list[InsiderTradePayload]
    summary: InsiderActivitySummaryPayload
    refresh: RefreshState


class InstitutionalHoldingPayload(BaseModel):
    fund_name: str
    fund_strategy: str | None = None
    reporting_date: DateType
    shares_held: Number = None
    market_value: Number = None
    change_in_shares: Number = None
    percent_change: Number = None
    portfolio_weight: Number = None


class CompanyInstitutionalHoldingsResponse(BaseModel):
    company: CompanyPayload | None
    institutional_holdings: list[InstitutionalHoldingPayload]
    refresh: RefreshState


class ModelPayload(BaseModel):
    model_name: str
    model_version: str
    created_at: datetime
    input_periods: dict[str, Any] | list[dict[str, Any]]
    result: dict[str, Any]


class CompanyModelsResponse(BaseModel):
    company: CompanyPayload | None
    requested_models: list[str]
    models: list[ModelPayload]
    refresh: RefreshState


class RefreshQueuedResponse(BaseModel):
    status: Literal["queued"]
    ticker: str
    force: bool
    refresh: RefreshState


class PeerOptionPayload(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    last_checked: datetime | None = None
    cache_state: Literal["fresh", "stale", "missing"]
    is_focus: bool = False


class PeerRevenuePointPayload(BaseModel):
    period_end: DateType
    revenue: Number = None
    revenue_growth: Number = None


class PeerMetricsPayload(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    market_sector: str | None = None
    market_industry: str | None = None
    is_focus: bool = False
    cache_state: Literal["fresh", "stale", "missing"]
    last_checked: datetime | None = None
    period_end: DateType | None = None
    price_date: DateType | None = None
    latest_price: Number = None
    pe: Number = None
    ev_to_ebit: Number = None
    price_to_free_cash_flow: Number = None
    roe: Number = None
    revenue_growth: Number = None
    piotroski_score: Number = None
    altman_z_score: Number = None
    revenue_history: list[PeerRevenuePointPayload] = Field(default_factory=list)


class CompanyPeersResponse(BaseModel):
    company: CompanyPayload | None
    peer_basis: str
    available_companies: list[PeerOptionPayload]
    selected_tickers: list[str]
    peers: list[PeerMetricsPayload]
    notes: dict[str, str]
    refresh: RefreshState


class FilingPayload(BaseModel):
    accession_number: str | None = None
    form: str
    filing_date: DateType | None = None
    report_date: DateType | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None
    items: str | None = None
    source_url: str


class CompanyFilingsResponse(BaseModel):
    company: CompanyPayload | None
    filings: list[FilingPayload]
    timeline_source: Literal["sec_submissions", "cached_financials"]
    refresh: RefreshState
    error: str | None = None


_filings_timeline_cache: dict[str, tuple[float, list[FilingPayload]]] = {}
try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

_redis_client = None
if redis is not None:
    try:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
    except Exception:
        logging.getLogger(__name__).warning("Redis client unavailable; falling back to process cache")
        _redis_client = None


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/jobs/{job_id}/events")
async def stream_job_events(job_id: str, request: Request) -> StreamingResponse:
    if not status_broker.has_job(job_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job ID")

    backlog, queue, unsubscribe = status_broker.subscribe(job_id)

    async def event_generator():
        try:
            for event in backlog:
                yield status_broker.format_sse(job_id, event)
                if event.status in {"completed", "failed"}:
                    return

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                yield status_broker.format_sse(job_id, event)
                if event.status in {"completed", "failed"}:
                    break
        finally:
            unsubscribe()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/companies/search", response_model=CompanySearchResponse)
def search_companies(
    background_tasks: BackgroundTasks,
    query: str | None = Query(default=None, min_length=1),
    ticker: str | None = Query(default=None, min_length=1),
    refresh: bool = Query(default=True),
    session: Session = Depends(get_db_session),
) -> CompanySearchResponse:
    raw_query = query if query is not None else ticker
    if raw_query is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query is required")

    normalized_query = _normalize_search_query(raw_query)
    normalized_ticker = _normalize_ticker(normalized_query)
    normalized_cik = _normalize_cik_query(normalized_query)
    snapshots = search_company_snapshots(session, normalized_query)
    exact_match = next(
        (
            snapshot
            for snapshot in snapshots
            if snapshot.company.ticker == normalized_ticker or (normalized_cik is not None and snapshot.company.cik == normalized_cik)
        ),
        None,
    )

    refresh_state = RefreshState()
    if not refresh:
        if exact_match is None:
            refresh_state = RefreshState(
                triggered=False,
                reason="none",
                ticker=normalized_ticker if _looks_like_ticker(normalized_query) else None,
                job_id=None,
            )
        elif exact_match.cache_state in {"missing", "stale"}:
            refresh_state = RefreshState(
                triggered=False,
                reason=exact_match.cache_state,
                ticker=exact_match.company.ticker,
                job_id=None,
            )
        else:
            refresh_state = RefreshState(triggered=False, reason="fresh", ticker=exact_match.company.ticker, job_id=None)
    elif exact_match is None:
        if not snapshots and _looks_like_ticker(normalized_query):
            refresh_state = _trigger_refresh(background_tasks, normalized_ticker, reason="missing")
        else:
            refresh_state = RefreshState(triggered=False, reason="none", ticker=normalized_ticker if _looks_like_ticker(normalized_query) else None, job_id=None)
    elif exact_match.cache_state in {"missing", "stale"}:
        refresh_state = _trigger_refresh(background_tasks, exact_match.company.ticker, reason=exact_match.cache_state)
    else:
        refresh_state = RefreshState(triggered=False, reason="fresh", ticker=exact_match.company.ticker, job_id=None)

    return CompanySearchResponse(
        query=normalized_query,
        results=[_serialize_company(snapshot) for snapshot in snapshots],
        refresh=refresh_state,
    )


@app.get("/api/companies/resolve", response_model=CompanyResolutionResponse)
def resolve_company_identifier(query: str = Query(..., min_length=1), session: Session = Depends(get_db_session)) -> CompanyResolutionResponse:
    normalized_query = _normalize_search_query(query)

    client = EdgarClient()
    try:
        identity = client.resolve_company(normalized_query)
    except ValueError:
        return CompanyResolutionResponse(query=normalized_query, resolved=False, error="not_found")
    except Exception:
        logging.getLogger(__name__).exception("SEC company resolution failed for '%s'", normalized_query)
        return CompanyResolutionResponse(query=normalized_query, resolved=False, error="lookup_failed")
    finally:
        client.close()

    return CompanyResolutionResponse(
        query=normalized_query,
        resolved=True,
        ticker=_resolve_canonical_ticker(session, identity) or identity.ticker,
        name=identity.name,
        error=None,
    )


@app.get("/api/companies/{ticker}/financials", response_model=CompanyFinancialsResponse)
def company_financials(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFinancialsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFinancialsResponse(
            company=None,
            financials=[],
            price_history=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    financials = get_company_financials(session, snapshot.company.id)
    price_last_checked, price_cache_state = get_company_price_cache_status(session, snapshot.company.id)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    price_history = get_company_price_history(session, snapshot.company.id)
    return CompanyFinancialsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
        ),
        financials=[_serialize_financial(statement) for statement in financials],
        price_history=[_serialize_price_history(point) for point in price_history],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/insider-trades", response_model=CompanyInsiderTradesResponse)
def company_insider_trades(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInsiderTradesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInsiderTradesResponse(
            company=None,
            insider_trades=[],
            summary=_serialize_insider_activity_summary(build_insider_activity_summary([])),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    insider_last_checked, insider_cache_state = get_company_insider_trade_cache_status(session, snapshot.company)
    insider_trades = get_company_insider_trades(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=insider_cache_state)
        if insider_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyInsiderTradesResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, insider_last_checked),
            last_checked_insiders=insider_last_checked,
        ),
        insider_trades=[_serialize_insider_trade(trade) for trade in insider_trades],
        summary=_serialize_insider_activity_summary(build_insider_activity_summary(insider_trades)),
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/institutional-holdings", response_model=CompanyInstitutionalHoldingsResponse)
def company_institutional_holdings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInstitutionalHoldingsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInstitutionalHoldingsResponse(
            company=None,
            institutional_holdings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    holdings_last_checked, holdings_cache_state = get_company_institutional_holdings_cache_status(session, snapshot.company)
    holdings = get_company_institutional_holdings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=holdings_cache_state)
        if holdings_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyInstitutionalHoldingsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, holdings_last_checked),
            last_checked_institutional=holdings_last_checked,
        ),
        institutional_holdings=[_serialize_institutional_holding(holding) for holding in holdings],
        refresh=refresh,
    )


@app.post(
    "/api/companies/{ticker}/refresh",
    response_model=RefreshQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def refresh_company(
    ticker: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    session: Session = Depends(get_db_session),
) -> RefreshQueuedResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    queue_ticker = snapshot.company.ticker if snapshot is not None else normalized_ticker
    job_id = queue_company_refresh(background_tasks, queue_ticker, force=force)
    return RefreshQueuedResponse(
        status="queued",
        ticker=queue_ticker,
        force=force,
        refresh=RefreshState(triggered=True, reason="manual", ticker=queue_ticker, job_id=job_id),
    )


@app.get("/api/companies/{ticker}/models", response_model=CompanyModelsResponse)
def company_models(
    ticker: str,
    background_tasks: BackgroundTasks,
    model: str | None = Query(default=None),
    dupont_mode: str | None = Query(default=None, description="optional DuPont basis: auto|annual|ttm"),
    session: Session = Depends(get_db_session),
) -> CompanyModelsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_models = _parse_requested_models(model)
    normalized_mode = (dupont_mode or "").lower() or None
    if normalized_mode is not None and normalized_mode not in {"auto", "annual", "ttm"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dupont_mode must be one of: auto, annual, ttm")
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyModelsResponse(
            company=None,
            requested_models=requested_models,
            models=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    token = None
    try:
        if normalized_mode is not None:
            token = dupont_model.set_mode_override(normalized_mode)

        refresh = _refresh_for_snapshot(background_tasks, snapshot)
        if snapshot.cache_state == "fresh" and requested_models:
            model_job_results = ModelEngine(session).compute_models(snapshot.company.id, model_names=requested_models, force=False)
            if any(not result.cached for result in model_job_results):
                session.commit()

        models = get_company_models(
            session,
            snapshot.company.id,
            requested_models or None,
            config_by_model={"dupont": {"mode": dupont_model.get_mode()}},
        )
        return CompanyModelsResponse(
            company=_serialize_company(snapshot),
            requested_models=requested_models,
            models=[_serialize_model(model_run) for model_run in models],
            refresh=refresh,
        )
    finally:
        if token is not None:
            dupont_model.reset_mode_override(token)


@app.get("/api/companies/{ticker}/peers", response_model=CompanyPeersResponse)
def company_peers(
    ticker: str,
    background_tasks: BackgroundTasks,
    peers: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> CompanyPeersResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    selected_tickers = _parse_csv_values(peers)
    if snapshot is None:
        return CompanyPeersResponse(
            company=None,
            peer_basis="Cached peer universe",
            available_companies=[],
            selected_tickers=[],
            peers=[],
            notes={},
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    price_last_checked, price_cache_state = get_company_price_cache_status(session, snapshot.company.id)
    financials = get_company_financials(session, snapshot.company.id)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    payload = build_peer_comparison(session, snapshot.company.ticker, selected_tickers=selected_tickers)
    if payload is None:
        return CompanyPeersResponse(
            company=None,
            peer_basis="Cached peer universe",
            available_companies=[],
            selected_tickers=[],
            peers=[],
            notes={},
            refresh=refresh,
        )

    return CompanyPeersResponse(
        company=_serialize_company(
            payload["company"],
            last_checked=_merge_last_checked(payload["company"].last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
        ),
        peer_basis=payload["peer_basis"],
        available_companies=[PeerOptionPayload(**item) for item in payload["available_companies"]],
        selected_tickers=payload["selected_tickers"],
        peers=[PeerMetricsPayload(**item) for item in payload["peers"]],
        notes=payload["notes"],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/filings", response_model=CompanyFilingsResponse)
def company_filings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingsResponse(
            company=None,
            filings=[],
            timeline_source="sec_submissions",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)

    cached_filings = _load_filings_from_cache(snapshot.company.cik)
    if cached_filings is not None:
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(cached_filings)),
            filings=cached_filings,
            timeline_source="sec_submissions",
            refresh=refresh,
            error=None,
        )

    client = EdgarClient()
    try:
        submissions = client.get_submissions(snapshot.company.cik)
        filing_index = client.build_filing_index(submissions)
        filings = _serialize_recent_filings(snapshot.company.cik, filing_index)
        _store_filings_in_cache(snapshot.company.cik, filings)
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(filings)),
            filings=filings,
            timeline_source="sec_submissions",
            refresh=refresh,
            error=None,
        )
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC filing timeline for '%s'", snapshot.company.ticker)
        _evict_filings_cache(snapshot.company.cik)
        fallback_filings = _serialize_cached_statement_filings(get_company_financials(session, snapshot.company.id))
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(fallback_filings)),
            filings=fallback_filings,
            timeline_source="cached_financials",
            refresh=refresh,
            error=(
                "SEC submissions are temporarily unavailable. Showing cached annual and quarterly filings only."
                if fallback_filings
                else "SEC submissions are temporarily unavailable. Try refreshing again shortly."
            ),
        )
    finally:
        client.close()


@app.get("/api/companies/{ticker}/financial-history", response_model=CompanyFactsResponse)
def company_financial_history(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> CompanyFactsResponse:
    normalized = _normalize_search_query(ticker)
    resolved_cik = _normalize_cik_query(normalized)
    if resolved_cik:
        cik = resolved_cik
    else:
        snapshot = _resolve_cached_company_snapshot(session, _normalize_ticker(ticker))
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ticker")
        cik = snapshot.company.cik

    client = EdgarClient()
    try:
        facts = client.get_companyfacts(cik)
        if not isinstance(facts, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unexpected SEC companyfacts payload")
        return CompanyFactsResponse(facts=facts.get("facts", {}))
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC companyfacts for '%s'", cik)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to load SEC companyfacts")
    finally:
        client.close()


@app.get("/api/companies/{ticker}/filings/view", response_class=HTMLResponse)
def company_filing_view(
    ticker: str,
    source_url: str = Query(..., min_length=1),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ticker")

    normalized_source_url = source_url.strip()
    if not _is_allowed_sec_embed_url(normalized_source_url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported filing URL")

    parsed = urlparse(normalized_source_url)
    if parsed.netloc == "data.sec.gov" and parsed.path.endswith(".json"):
        return HTMLResponse(_render_unavailable_filing_view(normalized_source_url))

    client = EdgarClient()
    try:
        payload, content_type = _fetch_sec_document(client, normalized_source_url)
        return HTMLResponse(_build_embedded_filing_html(payload, normalized_source_url, content_type))
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC filing document for '%s'", normalized_source_url)
        return HTMLResponse(_render_unavailable_filing_view(normalized_source_url), status_code=status.HTTP_502_BAD_GATEWAY)
    finally:
        client.close()


def _refresh_for_snapshot(background_tasks: BackgroundTasks, snapshot: CompanyCacheSnapshot) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)

    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _resolve_cached_company_snapshot(session: Session, ticker: str) -> CompanyCacheSnapshot | None:
    snapshot = get_company_snapshot(session, ticker)
    if snapshot is not None:
        return snapshot

    if not _looks_like_ticker(ticker):
        return None

    client = EdgarClient()
    try:
        identity = client.resolve_company(ticker)
    except ValueError:
        return None
    except Exception:
        logging.getLogger(__name__).exception("Company alias resolution failed for '%s'", ticker)
        return None
    finally:
        client.close()

    return get_company_snapshot_by_cik(session, identity.cik)


def _resolve_canonical_ticker(session: Session, identity: Any) -> str | None:
    snapshot = get_company_snapshot_by_cik(session, identity.cik)
    if snapshot is None:
        return None
    return snapshot.company.ticker


def _refresh_for_financial_page(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
    price_cache_state: Literal["fresh", "stale", "missing"],
    financials: list[FinancialStatement],
) -> RefreshState:
    if snapshot.cache_state == "missing" or price_cache_state == "missing":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
    if snapshot.cache_state == "stale" or price_cache_state == "stale":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="stale")
    if _needs_segment_backfill(financials):
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")

    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _trigger_refresh(
    background_tasks: BackgroundTasks,
    ticker: str,
    *,
    reason: Literal["manual", "missing", "stale"],
) -> RefreshState:
    normalized_ticker = _normalize_ticker(ticker)
    job_id = queue_company_refresh(background_tasks, normalized_ticker, force=False)
    return RefreshState(triggered=True, reason=reason, ticker=normalized_ticker, job_id=job_id)


def _serialize_company(
    snapshot: CompanyCacheSnapshot,
    last_checked: datetime | None = None,
    *,
    last_checked_prices: datetime | None = None,
    last_checked_insiders: datetime | None = None,
    last_checked_institutional: datetime | None = None,
    last_checked_filings: datetime | None = None,
) -> CompanyPayload:
    return CompanyPayload(
        ticker=snapshot.company.ticker,
        cik=snapshot.company.cik,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        market_sector=snapshot.company.market_sector,
        market_industry=snapshot.company.market_industry,
        last_checked=last_checked if last_checked is not None else snapshot.last_checked,
        last_checked_financials=snapshot.last_checked,
        last_checked_prices=last_checked_prices,
        last_checked_insiders=last_checked_insiders,
        last_checked_institutional=last_checked_institutional,
        last_checked_filings=last_checked_filings,
        cache_state=snapshot.cache_state,
    )


def _serialize_financial(statement: FinancialStatement) -> FinancialPayload:
    data = statement.data or {}
    return FinancialPayload(
        filing_type=statement.filing_type,
        statement_type=statement.statement_type,
        period_start=statement.period_start,
        period_end=statement.period_end,
        source=statement.source,
        last_updated=statement.last_updated,
        last_checked=statement.last_checked,
        revenue=data.get("revenue"),
        gross_profit=data.get("gross_profit"),
        operating_income=data.get("operating_income"),
        net_income=data.get("net_income"),
        total_assets=data.get("total_assets"),
        total_liabilities=data.get("total_liabilities"),
        operating_cash_flow=data.get("operating_cash_flow"),
        capex=data.get("capex"),
        acquisitions=data.get("acquisitions"),
        debt_changes=data.get("debt_changes"),
        dividends=data.get("dividends"),
        share_buybacks=data.get("share_buybacks"),
        free_cash_flow=data.get("free_cash_flow"),
        eps=data.get("eps"),
        shares_outstanding=data.get("shares_outstanding"),
        segment_breakdown=[_serialize_financial_segment(item) for item in data.get("segment_breakdown", []) if isinstance(item, dict)],
    )


def _serialize_financial_segment(payload: dict[str, Any]) -> FinancialSegmentPayload:
    return FinancialSegmentPayload(
        segment_id=str(payload.get("segment_id") or payload.get("segment_name") or "unknown"),
        segment_name=str(payload.get("segment_name") or payload.get("segment_id") or "Unknown"),
        axis_key=payload.get("axis_key"),
        axis_label=payload.get("axis_label"),
        kind=payload.get("kind") if payload.get("kind") in {"business", "geographic", "other"} else "other",
        revenue=payload.get("revenue"),
        share_of_revenue=payload.get("share_of_revenue"),
    )


def _needs_segment_backfill(financials: list[FinancialStatement]) -> bool:
    if not financials:
        return False

    return not any(
        isinstance(statement.data, dict)
        and isinstance(statement.data.get("segment_breakdown"), list)
        and len(statement.data.get("segment_breakdown") or []) > 0
        for statement in financials
    )


def _serialize_price_history(point: PriceHistory) -> PriceHistoryPayload:
    return PriceHistoryPayload(
        date=point.trade_date,
        close=point.close,
        volume=point.volume,
    )


def _serialize_insider_trade(trade: InsiderTrade) -> InsiderTradePayload:
    return InsiderTradePayload(
        name=trade.insider_name,
        role=trade.role,
        date=trade.transaction_date,
        action=trade.action,
        transaction_code=trade.transaction_code,
        shares=trade.shares,
        price=trade.price,
        value=trade.value,
        ownership_after=trade.ownership_after,
        is_10b5_1=trade.is_10b5_1,
    )


def _serialize_insider_activity_summary(summary) -> InsiderActivitySummaryPayload:
    return InsiderActivitySummaryPayload(
        sentiment=summary.sentiment,
        summary_lines=summary.summary_lines,
        metrics=InsiderActivityMetricsPayload(
            total_buy_value=summary.metrics.total_buy_value,
            total_sell_value=summary.metrics.total_sell_value,
            net_value=summary.metrics.net_value,
            unique_insiders_buying=summary.metrics.unique_insiders_buying,
            unique_insiders_selling=summary.metrics.unique_insiders_selling,
        ),
    )


def _serialize_institutional_holding(holding) -> InstitutionalHoldingPayload:
    return InstitutionalHoldingPayload(
        fund_name=holding.fund.fund_name,
        fund_strategy=get_institutional_fund_strategy(holding.fund.fund_name, getattr(holding.fund, "fund_manager", None)),
        reporting_date=holding.reporting_date,
        shares_held=holding.shares_held,
        market_value=holding.market_value,
        change_in_shares=holding.change_in_shares,
        percent_change=holding.percent_change,
        portfolio_weight=holding.portfolio_weight,
    )


def _serialize_model(model_run: ModelRun) -> ModelPayload:
    return ModelPayload(
        model_name=model_run.model_name,
        model_version=model_run.model_version,
        created_at=model_run.created_at,
        input_periods=model_run.input_periods,
        result=model_run.result,
    )


def _serialize_recent_filings(cik: str, filing_index: dict[str, FilingMetadata]) -> list[FilingPayload]:
    filtered = [
        item
        for item in filing_index.values()
        if _is_core_filing_form(item.form)
    ]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    return [_serialize_filing_metadata(cik, item) for item in ordered[:MAX_FILING_TIMELINE_ITEMS]]


def _serialize_filing_metadata(cik: str, filing: FilingMetadata) -> FilingPayload:
    source_url = _build_filing_document_url(cik, filing.accession_number, filing.primary_document)
    form_display = (filing.form or "UNKNOWN").upper()
    return FilingPayload(
        accession_number=filing.accession_number,
        form=form_display,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=_normalize_optional_text(filing.primary_doc_description),
        items=_normalize_optional_text(filing.items),
        source_url=source_url,
    )


def _filings_cache_last_checked(filings: list[FilingPayload]) -> datetime | None:
    dates = [filing.filing_date for filing in filings if filing.filing_date is not None]
    if not dates:
        return None
    return datetime.combine(max(dates), datetime.min.time(), tzinfo=timezone.utc)


def _serialize_cached_statement_filings(financials: list[FinancialStatement]) -> list[FilingPayload]:
    timeline: list[FilingPayload] = []
    seen_keys: set[tuple[str, str, DateType]] = set()

    for statement in financials:
        form = (statement.filing_type or "").upper()
        if not _is_core_filing_form(form):
            continue
        dedupe_key = (form, statement.source, statement.period_end)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        timeline.append(
            FilingPayload(
                accession_number=_extract_accession_number(statement.source),
                form=form,
                filing_date=None,
                report_date=statement.period_end,
                primary_document=_extract_primary_document_name(statement.source),
                primary_doc_description=None,
                items=None,
                source_url=statement.source,
            )
        )

    return sorted(
        timeline,
        key=lambda item: (item.report_date or DateType.min, item.form, item.accession_number or ""),
        reverse=True,
    )[:MAX_FILING_TIMELINE_ITEMS]


def _build_filing_document_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json#accn={accession_number}"


def _extract_accession_number(source_url: str) -> str | None:
    if not source_url:
        return None
    companyfacts_match = re.search(r"#accn=([0-9-]+)$", source_url)
    if companyfacts_match:
        return companyfacts_match.group(1)
    archive_match = re.search(r"/([0-9]{10}-[0-9]{2}-[0-9]{6})/", source_url)
    if archive_match:
        return archive_match.group(1)
    return None


def _extract_primary_document_name(source_url: str) -> str | None:
    if not source_url or source_url.endswith(".json") or "#accn=" in source_url:
        return None
    document_name = source_url.rsplit("/", 1)[-1]
    return _normalize_optional_text(document_name)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _is_allowed_sec_embed_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    if parsed.scheme != "https":
        return False
    if parsed.netloc.lower() not in ALLOWED_SEC_EMBED_HOSTS:
        return False
    if parsed.netloc.lower().endswith("sec.gov") and not parsed.path:
        return False
    return True


def _is_allowed_sec_content_type(content_type: str | None, source_url: str) -> bool:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type and any(normalized_type.startswith(prefix) for prefix in ALLOWED_SEC_EMBED_MIME_PREFIXES):
        return True
    path = urlparse(source_url).path.lower()
    return any(path.endswith(ext) for ext in ALLOWED_SEC_EMBED_EXTENSIONS)


def _fetch_sec_document(client: EdgarClient, source_url: str) -> tuple[str, str]:
    with client.stream_document(source_url) as response:
        content_type = response.headers.get("content-type", "text/html")
        if not _is_allowed_sec_content_type(content_type, source_url):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Filing document type is not supported for embedded viewing. Open it directly on SEC instead.",
            )

        total = 0
        chunks: list[bytes] = []
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > MAX_SEC_EMBED_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Filing document exceeds the 5 MB embed limit. Open it directly on SEC instead.",
                )
            chunks.append(chunk)

        payload_bytes = b"".join(chunks)
        text = payload_bytes.decode(response.encoding or "utf-8", errors="replace")
        return text, content_type or "text/html"


def _build_embedded_filing_html(payload: str, source_url: str, content_type: str) -> str:
    normalized_type = content_type.lower()
    if "html" in normalized_type or re.search(r"\.(html?|xhtml)$", urlparse(source_url).path, flags=re.IGNORECASE):
        sanitized = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", payload)
        if re.search(r"(?is)<head[^>]*>", sanitized):
            base_tag = f'<base href="{html.escape(source_url, quote=True)}" target="_blank">'
            return re.sub(r"(?is)<head([^>]*)>", rf"<head\1>{base_tag}", sanitized, count=1)
        return (
            "<!doctype html><html><head>"
            f'<base href="{html.escape(source_url, quote=True)}" target="_blank">'
            "</head><body>"
            f"{sanitized}"
            "</body></html>"
        )

    escaped_payload = html.escape(payload)
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        f'<base href="{html.escape(source_url, quote=True)}" target="_blank">'
        "<style>body{margin:0;background:#0c0c0c;color:#e5e7eb;font:14px/1.6 Inter,system-ui,sans-serif;}"
        ".shell{padding:20px;}pre{white-space:pre-wrap;word-break:break-word;font:13px/1.55 SFMono-Regular,Consolas,monospace;}"
        "a{color:#00e5ff;}</style></head><body><div class='shell'>"
        "<pre>"
        f"{escaped_payload}"
        "</pre></div></body></html>"
    )


def _render_unavailable_filing_view(source_url: str) -> str:
    escaped_url = html.escape(source_url, quote=True)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{margin:0;background:#0c0c0c;color:#e5e7eb;font:14px/1.6 Inter,system-ui,sans-serif;}"
        ".shell{padding:24px;max-width:760px;margin:0 auto;}"
        ".card{padding:18px;border-radius:16px;border:1px solid rgba(255,255,255,.08);background:#111111;}"
        "a{color:#00e5ff;text-decoration:none;}a:hover{text-decoration:underline;}</style></head><body>"
        "<div class='shell'><div class='card'><h1>Embedded viewer unavailable</h1>"
        "<p>This filing does not expose a directly embeddable SEC HTML document from the current source URL.</p>"
        f"<p><a href='{escaped_url}' target='_blank' rel='noreferrer'>Open the filing on SEC</a></p>"
        "</div></div></body></html>"
    )


def _parse_requested_models(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _parse_csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _normalize_ticker(value: str) -> str:
    return value.strip().replace("$", "").upper()


def _normalize_search_query(value: str) -> str:
    normalized = value.strip().replace("$", "")
    return re.sub(r"^cik\s*[:#-]?\s*", "", normalized, flags=re.IGNORECASE)


def _normalize_cik_query(value: str) -> str | None:
    digits = "".join(character for character in value if character.isdigit())
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


def _normalize_filing_form(form: str | None) -> tuple[str, bool]:
    if not form:
        return "", False
    normalized = form.upper().strip()
    amended = False
    for suffix in ("/A", "-A"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            amended = True
            break
    return normalized, amended


def _is_core_filing_form(form: str | None) -> bool:
    base_form, _ = _normalize_filing_form(form)
    return bool(base_form) and base_form in CORE_FILING_TIMELINE_FORMS


def _filings_cache_key(cik: str) -> str:
    return f"ft:filings:{cik}"


def _load_filings_from_cache(cik: str) -> list[FilingPayload] | None:
    # Prefer Redis for cross-worker cache
    if _redis_client is not None:
        try:
            cached = _redis_client.get(_filings_cache_key(cik))
            if cached:
                data = json.loads(cached)
                return [FilingPayload(**item) for item in data]
        except Exception:
            logging.getLogger(__name__).warning("Unable to read filings cache from Redis", exc_info=True)

    # Fallback to process-local cache
    cached_entry = _filings_timeline_cache.get(cik)
    if cached_entry:
        cached_age = time.monotonic() - cached_entry[0]
        if cached_age < FILINGS_TIMELINE_TTL_SECONDS:
            return cached_entry[1]

    return None


def _store_filings_in_cache(cik: str, filings: list[FilingPayload]) -> None:
    # Process-local cache
    _filings_timeline_cache[cik] = (time.monotonic(), filings)

    if _redis_client is None:
        return

    try:
        payload = json.dumps([filing.model_dump(mode="json") for filing in filings])
        _redis_client.setex(_filings_cache_key(cik), FILINGS_TIMELINE_TTL_SECONDS, payload)
    except Exception:
        logging.getLogger(__name__).warning("Unable to store filings cache in Redis", exc_info=True)


def _evict_filings_cache(cik: str) -> None:
    _filings_timeline_cache.pop(cik, None)
    if _redis_client is None:
        return
    try:
        _redis_client.delete(_filings_cache_key(cik))
    except Exception:
        logging.getLogger(__name__).warning("Unable to evict filings cache in Redis", exc_info=True)


def _looks_like_ticker(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", value.strip().replace("$", "")))


def _merge_last_checked(*values: datetime | None) -> datetime | None:
    normalized_values = [value for value in values if value is not None]
    if not normalized_values:
        return None
    return min(normalized_values)
