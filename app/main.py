from __future__ import annotations

import logging
import asyncio
from datetime import date as DateType, datetime
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.model_engine.engine import ModelEngine
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
    queue_company_refresh,
    search_company_snapshots,
    status_broker,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Financial Cache API", version="1.1.0")

Number = int | float | None


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
    cache_state: Literal["fresh", "stale", "missing"]


class CompanySearchResponse(BaseModel):
    query: str
    results: list[CompanyPayload]
    refresh: RefreshState


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
    ticker: str = Query(..., min_length=1),
    session: Session = Depends(get_db_session),
) -> CompanySearchResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshots = search_company_snapshots(session, normalized_ticker)
    exact_match = next((snapshot for snapshot in snapshots if snapshot.company.ticker == normalized_ticker), None)

    refresh = RefreshState()
    if exact_match is None:
        refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="missing")
    elif exact_match.cache_state in {"missing", "stale"}:
        refresh = _trigger_refresh(background_tasks, exact_match.company.ticker, reason=exact_match.cache_state)
    else:
        refresh = RefreshState(triggered=False, reason="fresh", ticker=normalized_ticker, job_id=None)

    return CompanySearchResponse(
        query=normalized_ticker,
        results=[_serialize_company(snapshot) for snapshot in snapshots],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/financials", response_model=CompanyFinancialsResponse)
def company_financials(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFinancialsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = get_company_snapshot(session, normalized_ticker)
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
        company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked)),
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
    snapshot = get_company_snapshot(session, normalized_ticker)
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
        company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, insider_last_checked)),
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
    snapshot = get_company_snapshot(session, normalized_ticker)
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
        company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, holdings_last_checked)),
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
) -> RefreshQueuedResponse:
    normalized_ticker = _normalize_ticker(ticker)
    job_id = queue_company_refresh(background_tasks, normalized_ticker, force=force)
    return RefreshQueuedResponse(
        status="queued",
        ticker=normalized_ticker,
        force=force,
        refresh=RefreshState(triggered=True, reason="manual", ticker=normalized_ticker, job_id=job_id),
    )


@app.get("/api/companies/{ticker}/models", response_model=CompanyModelsResponse)
def company_models(
    ticker: str,
    background_tasks: BackgroundTasks,
    model: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> CompanyModelsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_models = _parse_requested_models(model)
    snapshot = get_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyModelsResponse(
            company=None,
            requested_models=requested_models,
            models=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    if snapshot.cache_state == "fresh" and requested_models:
        model_job_results = ModelEngine(session).compute_models(snapshot.company.id, model_names=requested_models, force=False)
        if any(not result.cached for result in model_job_results):
            session.commit()

    models = get_company_models(session, snapshot.company.id, requested_models or None)
    return CompanyModelsResponse(
        company=_serialize_company(snapshot),
        requested_models=requested_models,
        models=[_serialize_model(model_run) for model_run in models],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/peers", response_model=CompanyPeersResponse)
def company_peers(
    ticker: str,
    background_tasks: BackgroundTasks,
    peers: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> CompanyPeersResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = get_company_snapshot(session, normalized_ticker)
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
    payload = build_peer_comparison(session, normalized_ticker, selected_tickers=selected_tickers)
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
        company=_serialize_company(payload["company"], last_checked=_merge_last_checked(payload["company"].last_checked, price_last_checked)),
        peer_basis=payload["peer_basis"],
        available_companies=[PeerOptionPayload(**item) for item in payload["available_companies"]],
        selected_tickers=payload["selected_tickers"],
        peers=[PeerMetricsPayload(**item) for item in payload["peers"]],
        notes=payload["notes"],
        refresh=refresh,
    )


def _refresh_for_snapshot(background_tasks: BackgroundTasks, snapshot: CompanyCacheSnapshot) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)

    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


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


def _serialize_company(snapshot: CompanyCacheSnapshot, last_checked: datetime | None = None) -> CompanyPayload:
    return CompanyPayload(
        ticker=snapshot.company.ticker,
        cik=snapshot.company.cik,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        market_sector=snapshot.company.market_sector,
        market_industry=snapshot.company.market_industry,
        last_checked=last_checked if last_checked is not None else snapshot.last_checked,
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


def _parse_requested_models(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _parse_csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _normalize_ticker(value: str) -> str:
    return value.strip().upper()


def _merge_last_checked(*values: datetime | None) -> datetime | None:
    normalized_values = [value for value in values if value is not None]
    if not normalized_values:
        return None
    return min(normalized_values)
