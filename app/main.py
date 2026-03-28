from __future__ import annotations

import logging
import asyncio
from copy import deepcopy
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
from email.utils import format_datetime
from datetime import date as DateType, datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from starlette.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api import register_routers
from app.api.schemas import *
from app.config import settings
from app.db import get_db_session
from app.model_engine.engine import ModelEngine, build_company_dataset, build_market_snapshot
from app.model_engine.models import dupont as dupont_model
from app.models import EarningsModelPoint, EarningsRelease, ExecutiveCompensation, FinancialRestatement, FinancialStatement, Form144Filing, InsiderTrade, ModelRun, PriceHistory, ProxyStatement
from app.source_registry import SourceTier, SourceUsage, build_provenance_entries, build_source_mix, infer_source_id
from app.services.insider_analytics import build_insider_analytics
from app.services.insider_activity import build_insider_activity_summary
from app.services.institutional_holdings import get_institutional_fund_strategy
from app.services.ownership_analytics import build_ownership_analytics
from app.services.peer_comparison import build_peer_comparison
from app.services.capital_structure_intelligence import snapshot_effective_at
from app.services.segment_analysis import build_segment_analysis
from app.services import (
    CompanyCacheSnapshot,
    build_changes_since_last_filing,
    get_company_capital_markets_events,
    get_company_capital_structure_last_checked,
    get_company_capital_structure_snapshots,
    get_company_coverage_counts,
    get_company_earnings_cache_status,
    get_company_earnings_model_cache_status,
    get_company_earnings_model_points,
    get_company_earnings_releases,
    get_company_derived_metric_points,
    get_company_derived_metrics_last_checked,
    get_company_financial_restatements,
    get_company_executive_compensation,
    get_company_filing_events,
    get_company_filing_insights,
    get_company_financials,
    get_company_regulated_bank_financials,
    get_company_form144_cache_status,
    get_company_form144_filings,
    get_company_insider_trade_cache_status,
    get_company_insider_trades,
    get_company_institutional_holdings,
    get_company_institutional_holdings_cache_status,
    get_company_models,
    get_company_price_cache_status,
    get_company_price_history,
    get_company_proxy_cache_status,
    get_company_proxy_statements,
    get_company_snapshot,
    get_company_snapshot_by_cik,
    get_company_snapshots_by_ticker,
    queue_company_refresh,
    search_company_snapshots,
    status_broker,
)
from app.services.cache_queries import (
    filter_price_history_as_of,
    get_company_beneficial_ownership_reports,
    latest_price_as_of,
    select_point_in_time_financials,
)
from app.services.beneficial_ownership import collect_beneficial_ownership_reports
from app.services.derived_metrics_mart import (
    build_derived_metric_points,
    build_summary_payload,
    build_summary_payload_from_points,
    to_period_payload,
    to_period_payload_from_points,
)
from app.services.market_context import (
    get_cached_market_context_status,
    get_company_market_context_v2,
    get_market_context_snapshot,
    get_market_context_v2,
)
from app.services.sector_context import get_company_sector_context
from app.services.proxy_parser import ExecCompRow, ProxyFilingSignals, ProxyVoteOutcome, parse_proxy_filing_signals
from app.services.derived_metrics import build_metrics_timeseries
from app.services.earnings_intelligence import build_earnings_alerts, build_earnings_directional_backtest, build_earnings_peer_percentiles, build_sector_alert_profile
from app.services.regulated_financials import build_regulated_entity_payload, select_preferred_financials
from app.services.sec_sic import resolve_sec_sic_profile
from app.services.sec_edgar import EdgarClient, FilingMetadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Financial Cache API", version="1.1.0")

CORE_FILING_TIMELINE_FORMS = {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K"}
MAX_FILING_TIMELINE_ITEMS = 60
ALLOWED_SEC_EMBED_HOSTS = {"www.sec.gov", "sec.gov", "data.sec.gov"}
ALLOWED_SEC_EMBED_MIME_PREFIXES = ("text/html", "application/html", "application/xhtml+xml", "text/plain")
ALLOWED_SEC_EMBED_EXTENSIONS = (".htm", ".html", ".xhtml", ".txt")
MAX_SEC_EMBED_BYTES = 5 * 1024 * 1024
FILINGS_TIMELINE_TTL_SECONDS = settings.sec_filings_timeline_ttl_seconds
SEARCH_RESPONSE_TTL_SECONDS = 60
_search_response_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_search_response_cache_lock = threading.Lock()
_hot_response_cache: dict[str, tuple[float, float, dict[str, Any]]] = {}
_hot_response_cache_lock = threading.Lock()
_cache_metric_counts: dict[str, int] = {}
_cache_metric_lock = threading.Lock()

PriceCacheState = Literal["fresh", "stale", "missing"]
PRICE_DEPENDENT_DERIVED_METRIC_KEYS = {"buyback_yield_proxy", "dividend_yield_proxy", "shareholder_yield"}
PRICE_DEPENDENT_TIMESERIES_METRIC_KEYS = {"buyback_yield", "dividend_yield"}


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


@app.get("/api/internal/cache-metrics")
def cache_metrics() -> dict[str, dict[str, int]]:
    with _cache_metric_lock:
        return {"metrics": dict(_cache_metric_counts)}


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
    request: Request,
    http_response: Response,
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
    hot_key = f"search:{normalized_query}:refresh={int(refresh)}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload, is_fresh = cached_hot
        cached_response = CompanySearchResponse.model_validate(payload)
        if not is_fresh and _looks_like_ticker(normalized_query):
            stale_refresh = _trigger_refresh(background_tasks, _normalize_ticker(normalized_query), reason="stale")
            cached_response = cached_response.model_copy(update={"refresh": stale_refresh})

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=max(
                (item.last_checked for item in cached_response.results if item.last_checked is not None),
                default=None,
            ),
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    if not refresh:
        cached_response = _get_cached_search_response(normalized_query)
        if cached_response is not None:
            _store_hot_cached_payload(hot_key, cached_response)
            not_modified = _apply_conditional_headers(
                request,
                http_response,
                cached_response,
                last_modified=max(
                    (item.last_checked for item in cached_response.results if item.last_checked is not None),
                    default=None,
                ),
            )
            if not_modified is not None:
                return not_modified  # type: ignore[return-value]
            return cached_response

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

    payload = CompanySearchResponse(
        query=normalized_query,
        results=[_serialize_company(snapshot) for snapshot in snapshots],
        refresh=refresh_state,
    )
    if not refresh:
        _store_cached_search_response(normalized_query, payload)
    _store_hot_cached_payload(hot_key, payload)
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        payload,
        last_modified=max((item.last_checked for item in payload.results if item.last_checked is not None), default=None),
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return payload


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
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyFinancialsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    hot_key = f"financials:{normalized_ticker}:asof={_normalize_as_of(parsed_as_of) or 'latest'}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload_data, is_fresh = cached_hot
        cached_response = CompanyFinancialsResponse.model_validate(payload_data)
        if not is_fresh:
            stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
            cached_response = cached_response.model_copy(
                update={
                    "refresh": stale_refresh,
                    "diagnostics": _with_stale_flags(cached_response.diagnostics, _stale_flags_from_refresh(stale_refresh)),
                    "confidence_flags": sorted(set([*cached_response.confidence_flags, *_confidence_flags_from_refresh(stale_refresh)])),
                }
            )

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=cached_response.company.last_checked if cached_response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyFinancialsResponse(
            company=None,
            financials=[],
            price_history=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        payload = _apply_requested_as_of(payload, requested_as_of)
        _store_hot_cached_payload(hot_key, payload)
        return payload

    financials = _visible_financials_for_company(session, snapshot.company)
    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    price_history = _visible_price_history(session, snapshot.company.id)
    if parsed_as_of is not None:
        financials = select_point_in_time_financials(financials, parsed_as_of)
        price_history = filter_price_history_as_of(price_history, parsed_as_of)
    serialized_financials = [_serialize_financial(statement) for statement in financials]
    segment_analysis_payload = build_segment_analysis(serialized_financials)
    diagnostics = _diagnostics_for_financial_response(serialized_financials, refresh)
    payload = CompanyFinancialsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        financials=serialized_financials,
        price_history=[_serialize_price_history(point) for point in price_history],
        segment_analysis=SegmentAnalysisPayload.model_validate(segment_analysis_payload) if segment_analysis_payload is not None else None,
        refresh=refresh,
        diagnostics=diagnostics,
        **_financials_provenance_contract(
            financials,
            price_history,
            price_last_checked=price_last_checked,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    payload = _apply_requested_as_of(payload, requested_as_of)
    _store_hot_cached_payload(hot_key, payload)
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        payload,
        last_modified=payload.company.last_checked if payload.company else None,
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return payload


def company_capital_structure(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    max_periods: int = Query(default=8, ge=1, le=40),
    session: Session = Depends(get_db_session),
) -> CompanyCapitalStructureResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    hot_key = f"capital_structure:{normalized_ticker}:periods={max_periods}:asof={_normalize_as_of(parsed_as_of) or 'latest'}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload_data, is_fresh = cached_hot
        cached_response = CompanyCapitalStructureResponse.model_validate(payload_data)
        if not is_fresh:
            stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
            cached_response = cached_response.model_copy(
                update={
                    "refresh": stale_refresh,
                    "diagnostics": _with_stale_flags(cached_response.diagnostics, _stale_flags_from_refresh(stale_refresh)),
                    "confidence_flags": sorted(set([*cached_response.confidence_flags, *_confidence_flags_from_refresh(stale_refresh)])),
                }
            )

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=cached_response.company.last_checked if cached_response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyCapitalStructureResponse(
            company=None,
            latest=None,
            history=[],
            last_capital_structure_check=None,
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing", "capital_structure_missing"]),
            **_empty_provenance_contract("company_missing", "capital_structure_missing"),
        )
        payload = _apply_requested_as_of(payload, requested_as_of)
        _store_hot_cached_payload(hot_key, payload)
        return payload

    history = get_company_capital_structure_snapshots(session, snapshot.company.id, limit=max(48, max_periods * 6))
    last_capital_structure_check = get_company_capital_structure_last_checked(session, snapshot.company.id)
    if parsed_as_of is not None:
        floor = datetime.min.replace(tzinfo=timezone.utc)
        history = [item for item in history if (snapshot_effective_at(item) or floor) <= parsed_as_of]
    history = history[:max_periods]
    refresh = _refresh_for_capital_structure(background_tasks, snapshot, last_capital_structure_check, history)
    serialized_history = [_serialize_capital_structure_snapshot(item) for item in history]
    latest = serialized_history[0] if serialized_history else None
    diagnostics = _diagnostics_for_capital_structure(serialized_history, refresh)
    payload = CompanyCapitalStructureResponse(
        company=_serialize_company(snapshot, last_checked=_merge_last_checked(snapshot.last_checked, last_capital_structure_check)),
        latest=latest,
        history=serialized_history,
        last_capital_structure_check=last_capital_structure_check,
        refresh=refresh,
        diagnostics=diagnostics,
        **_capital_structure_provenance_contract(
            history,
            latest=latest,
            last_capital_structure_check=last_capital_structure_check,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    payload = _apply_requested_as_of(payload, requested_as_of)
    _store_hot_cached_payload(hot_key, payload)
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        payload,
        last_modified=payload.company.last_checked if payload.company else None,
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return payload


@app.get("/api/companies/{ticker}/filing-insights", response_model=CompanyFilingInsightsResponse)
def company_filing_insights(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingInsightsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingInsightsResponse(
            company=None,
            insights=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    insights = get_company_filing_insights(session, snapshot.company.id)
    insights_last_checked = max((item.last_checked for item in insights if item.last_checked is not None), default=None)
    refresh = _refresh_for_filing_insights(background_tasks, snapshot)
    serialized_insights = [_serialize_filing_parser_insight(item) for item in insights]
    return CompanyFilingInsightsResponse(
        company=_serialize_company(snapshot, last_checked=insights_last_checked),
        insights=serialized_insights,
        refresh=refresh,
        diagnostics=_diagnostics_for_filing_insights(serialized_insights, refresh),
    )


@app.get("/api/companies/{ticker}/changes-since-last-filing", response_model=CompanyChangesSinceLastFilingResponse)
def company_changes_since_last_filing(
    ticker: str,
    background_tasks: BackgroundTasks,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyChangesSinceLastFilingResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyChangesSinceLastFilingResponse(
            company=None,
            summary=ChangesSinceLastFilingSummaryPayload(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    financials = _visible_financials_for_company(session, snapshot.company)
    if parsed_as_of is not None:
        financials = select_point_in_time_financials(financials, parsed_as_of)
    restatements = get_company_financial_restatements(session, snapshot.company.id)
    if parsed_as_of is not None:
        restatements = [record for record in restatements if _financial_restatement_effective_at(record) <= parsed_as_of]

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    comparison = build_changes_since_last_filing(financials, restatements)
    diagnostics = _diagnostics_for_changes_since_last_filing(comparison, refresh)
    comparison_as_of = requested_as_of or _latest_as_of(
        (comparison.get("current_filing") or {}).get("filing_acceptance_at"),
        (comparison.get("current_filing") or {}).get("period_end"),
    )

    usages: list[SourceUsage] = [
        SourceUsage(
            source_id="ft_changes_since_last_filing",
            role="derived",
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(
                snapshot.last_checked,
                (comparison.get("current_filing") or {}).get("last_checked"),
                (comparison.get("previous_filing") or {}).get("last_checked"),
            ),
        )
    ]
    companyfacts_usage = _source_usage_from_hint(
        "https://data.sec.gov/api/xbrl/companyfacts/",
        role="primary",
        as_of=comparison_as_of,
        last_refreshed_at=snapshot.last_checked,
        default_source_id="sec_companyfacts",
    )
    if companyfacts_usage is not None:
        usages.append(companyfacts_usage)
    if any(
        str(source or "").startswith("https://www.sec.gov/Archives/")
        for source in [
            (comparison.get("current_filing") or {}).get("source"),
            (comparison.get("previous_filing") or {}).get("source"),
            *(item.get("source") for item in comparison.get("amended_prior_values", [])),
        ]
    ):
        filing_usage = _source_usage_from_hint(
            "https://www.sec.gov/Archives/",
            role="supplemental",
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(snapshot.last_checked, *(item.last_checked for item in restatements)),
            default_source_id="sec_edgar",
        )
        if filing_usage is not None:
            usages.append(filing_usage)

    confidence_flags = set(_confidence_flags_from_refresh(refresh))
    confidence_flags.update(str(flag) for flag in comparison.get("confidence_flags", []))
    confidence_flags.update(
        str(item.get("indicator_key") or "")
        for item in comparison.get("new_risk_indicators", [])
        if str(item.get("severity") or "") == "high"
    )
    confidence_flags.discard("")

    payload = CompanyChangesSinceLastFilingResponse(
        company=_serialize_company(snapshot),
        current_filing=comparison.get("current_filing"),
        previous_filing=comparison.get("previous_filing"),
        summary=comparison.get("summary") or ChangesSinceLastFilingSummaryPayload(),
        metric_deltas=comparison.get("metric_deltas") or [],
        new_risk_indicators=comparison.get("new_risk_indicators") or [],
        segment_shifts=comparison.get("segment_shifts") or [],
        share_count_changes=comparison.get("share_count_changes") or [],
        capital_structure_changes=comparison.get("capital_structure_changes") or [],
        amended_prior_values=comparison.get("amended_prior_values") or [],
        refresh=refresh,
        diagnostics=diagnostics,
        **_build_provenance_contract(
            usages,
            as_of=comparison_as_of,
            last_refreshed_at=_merge_last_checked(
                snapshot.last_checked,
                (comparison.get("current_filing") or {}).get("last_checked"),
                (comparison.get("previous_filing") or {}).get("last_checked"),
                *(item.last_checked for item in restatements),
            ),
            confidence_flags=sorted(confidence_flags),
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@app.get("/api/companies/{ticker}/metrics-timeseries", response_model=CompanyMetricsTimeseriesResponse)
def company_metrics_timeseries(
    ticker: str,
    background_tasks: BackgroundTasks,
    cadence: Literal["quarterly", "annual", "ttm"] | None = Query(default=None),
    max_points: int = Query(default=24, ge=1, le=200),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyMetricsTimeseriesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyMetricsTimeseriesResponse(
            company=None,
            series=[],
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    financials = _visible_financials_for_company(session, snapshot.company)
    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    price_history = _visible_price_history(session, snapshot.company.id)
    if parsed_as_of is not None:
        financials = select_point_in_time_financials(financials, parsed_as_of)
        price_history = filter_price_history_as_of(price_history, parsed_as_of)
    series = build_metrics_timeseries(financials, price_history, cadence=cadence, max_points=max_points)
    point_payload = _sanitize_metrics_timeseries_points_for_strict_official_mode(
        [MetricsTimeseriesPointPayload.model_validate(point) for point in series]
    )
    diagnostics = _diagnostics_for_metrics_timeseries(point_payload, refresh, staleness_reason)
    payload = CompanyMetricsTimeseriesResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        series=point_payload,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
        diagnostics=diagnostics,
        **_metrics_timeseries_provenance_contract(
            point_payload,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@app.get("/api/companies/{ticker}/metrics", response_model=CompanyDerivedMetricsResponse)
def company_derived_metrics(
    ticker: str,
    background_tasks: BackgroundTasks,
    period_type: Literal["quarterly", "annual", "ttm"] = Query(default="ttm"),
    max_periods: int = Query(default=24, ge=1, le=200),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyDerivedMetricsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyDerivedMetricsResponse(
            company=None,
            period_type=period_type,
            periods=[],
            available_metric_keys=[],
            last_metrics_check=None,
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    financials = _visible_financials_for_company(session, snapshot.company)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)

    if parsed_as_of is None:
        rows = get_company_derived_metric_points(
            session,
            snapshot.company.id,
            period_type=period_type,
            max_periods=max_periods,
        )
        last_metrics_check = get_company_derived_metrics_last_checked(session, snapshot.company.id)
        if not rows:
            refresh = _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
            if staleness_reason == "fresh":
                staleness_reason = "metrics_missing"

        period_payload = _sanitize_derived_metric_periods_for_strict_official_mode(
            [DerivedMetricPeriodPayload.model_validate(item) for item in to_period_payload(rows)]
        )
        available_metric_keys = sorted({item.metric_key for item in rows})
        metric_values = [metric for period in period_payload for metric in period.metrics]
        latest_period_end = max((period.period_end for period in period_payload), default=None)
        diagnostics = _diagnostics_for_derived_metrics_periods(period_payload, refresh, staleness_reason)
        payload = CompanyDerivedMetricsResponse(
            company=_serialize_company(
                snapshot,
                last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
                last_checked_prices=price_last_checked,
                regulated_entity=_regulated_entity_payload(snapshot.company, financials),
            ),
            period_type=period_type,
            periods=period_payload,
            available_metric_keys=available_metric_keys,
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            staleness_reason=staleness_reason,
            refresh=refresh,
            diagnostics=diagnostics,
            **_derived_metrics_provenance_contract(
                metric_values,
                as_of=latest_period_end,
                derived_source_id="ft_derived_metrics_mart",
                last_metrics_check=last_metrics_check,
                last_financials_check=snapshot.last_checked,
                last_price_check=price_last_checked,
                diagnostics=diagnostics,
                refresh=refresh,
            ),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    filtered_financials = select_point_in_time_financials(financials, parsed_as_of)
    filtered_price_history = filter_price_history_as_of(_visible_price_history(session, snapshot.company.id), parsed_as_of)
    point_rows = [
        row
        for row in build_derived_metric_points(filtered_financials, filtered_price_history)
        if row.get("period_type") == period_type
    ]
    period_rows = to_period_payload_from_points(point_rows)
    if len(period_rows) > max_periods:
        period_rows = period_rows[-max_periods:]
    period_payload = _sanitize_derived_metric_periods_for_strict_official_mode(
        [DerivedMetricPeriodPayload.model_validate(item) for item in period_rows]
    )
    available_metric_keys = sorted({str(item.get("metric_key") or "") for item in point_rows if item.get("metric_key")})
    last_metrics_check = None
    diagnostics = _diagnostics_for_derived_metrics_periods(period_payload, refresh, staleness_reason)
    metric_values = [metric for period in period_payload for metric in period.metrics]
    latest_period_end = max((period.period_end for period in period_payload), default=None)
    payload = CompanyDerivedMetricsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        period_type=period_type,
        periods=period_payload,
        available_metric_keys=available_metric_keys,
        last_metrics_check=last_metrics_check,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
        diagnostics=diagnostics,
        **_derived_metrics_provenance_contract(
            metric_values,
            as_of=requested_as_of or latest_period_end,
            derived_source_id="ft_derived_metrics_engine",
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


@app.get("/api/companies/{ticker}/metrics/summary", response_model=CompanyDerivedMetricsSummaryResponse)
def company_derived_metrics_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    period_type: Literal["quarterly", "annual", "ttm"] = Query(default="ttm"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyDerivedMetricsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyDerivedMetricsSummaryResponse(
            company=None,
            period_type=period_type,
            latest_period_end=None,
            metrics=[],
            last_metrics_check=None,
            last_financials_check=None,
            last_price_check=None,
            staleness_reason="company_missing",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    financials = _visible_financials_for_company(session, snapshot.company)
    staleness_reason = _metrics_staleness_reason(snapshot, price_cache_state, financials)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)

    if parsed_as_of is None:
        rows = get_company_derived_metric_points(session, snapshot.company.id, max_periods=24)
        last_metrics_check = get_company_derived_metrics_last_checked(session, snapshot.company.id)
        if not rows:
            refresh = _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
            if staleness_reason == "fresh":
                staleness_reason = "metrics_missing"

        summary = build_summary_payload(rows, period_type)
        metric_payload = _sanitize_derived_metric_values_for_strict_official_mode(
            [DerivedMetricValuePayload.model_validate(item) for item in summary["metrics"]]
        )
        diagnostics = _diagnostics_for_derived_metrics_values(metric_payload, refresh, staleness_reason)
        payload = CompanyDerivedMetricsSummaryResponse(
            company=_serialize_company(
                snapshot,
                last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
                last_checked_prices=price_last_checked,
                regulated_entity=_regulated_entity_payload(snapshot.company, financials),
            ),
            period_type=summary["period_type"],
            latest_period_end=summary["latest_period_end"],
            metrics=metric_payload,
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            staleness_reason=staleness_reason,
            refresh=refresh,
            diagnostics=diagnostics,
            **_derived_metrics_provenance_contract(
                metric_payload,
                as_of=summary["latest_period_end"],
                derived_source_id="ft_derived_metrics_mart",
                last_metrics_check=last_metrics_check,
                last_financials_check=snapshot.last_checked,
                last_price_check=price_last_checked,
                diagnostics=diagnostics,
                refresh=refresh,
            ),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    filtered_financials = select_point_in_time_financials(financials, parsed_as_of)
    filtered_price_history = filter_price_history_as_of(_visible_price_history(session, snapshot.company.id), parsed_as_of)
    point_rows = build_derived_metric_points(filtered_financials, filtered_price_history)
    summary = build_summary_payload_from_points(point_rows, period_type)
    last_metrics_check = None
    metric_payload = _sanitize_derived_metric_values_for_strict_official_mode(
        [DerivedMetricValuePayload.model_validate(item) for item in summary["metrics"]]
    )
    diagnostics = _diagnostics_for_derived_metrics_values(metric_payload, refresh, staleness_reason)
    payload = CompanyDerivedMetricsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, price_last_checked),
            last_checked_prices=price_last_checked,
            regulated_entity=_regulated_entity_payload(snapshot.company, financials),
        ),
        period_type=summary["period_type"],
        latest_period_end=summary["latest_period_end"],
        metrics=metric_payload,
        last_metrics_check=last_metrics_check,
        last_financials_check=snapshot.last_checked,
        last_price_check=price_last_checked,
        staleness_reason=staleness_reason,
        refresh=refresh,
        diagnostics=diagnostics,
        **_derived_metrics_provenance_contract(
            metric_payload,
            as_of=requested_as_of or summary["latest_period_end"],
            derived_source_id="ft_derived_metrics_engine",
            last_metrics_check=last_metrics_check,
            last_financials_check=snapshot.last_checked,
            last_price_check=price_last_checked,
            diagnostics=diagnostics,
            refresh=refresh,
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


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


@app.get("/api/companies/{ticker}/institutional-holdings/summary", response_model=CompanyInstitutionalHoldingsSummaryResponse)
def company_institutional_holdings_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyInstitutionalHoldingsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyInstitutionalHoldingsSummaryResponse(
            company=None,
            summary=InstitutionalHoldingsSummaryPayload(total_rows=0, unique_managers=0, amended_rows=0, latest_reporting_date=None),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    holdings_last_checked, holdings_cache_state = get_company_institutional_holdings_cache_status(session, snapshot.company)
    holdings = get_company_institutional_holdings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=holdings_cache_state)
        if holdings_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    rows = [_serialize_institutional_holding(holding) for holding in holdings]
    return CompanyInstitutionalHoldingsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, holdings_last_checked),
            last_checked_institutional=holdings_last_checked,
        ),
        summary=_build_institutional_holdings_summary(rows),
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/form-144-filings", response_model=CompanyForm144Response)
def company_form144_filings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyForm144Response:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyForm144Response(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
        )

    form144_last_checked, form144_cache_state = get_company_form144_cache_status(session, snapshot.company)
    filings = get_company_form144_filings(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(background_tasks, snapshot.company.ticker, reason=form144_cache_state)
        if form144_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    return CompanyForm144Response(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, form144_last_checked),
        ),
        filings=[_serialize_form144_filing(filing) for filing in filings],
        refresh=refresh,
    )


@app.get("/api/companies/{ticker}/earnings", response_model=CompanyEarningsResponse)
def company_earnings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsResponse(
            company=None,
            earnings_releases=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    refresh = _refresh_for_earnings(background_tasks, snapshot, earnings_cache_state)
    payload = [_serialize_earnings_release(release) for release in earnings_releases]
    return CompanyEarningsResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, earnings_last_checked),
            last_checked_earnings=earnings_last_checked,
        ),
        earnings_releases=payload,
        refresh=refresh,
        diagnostics=_diagnostics_for_earnings_releases(payload, refresh),
    )


@app.get("/api/companies/{ticker}/earnings/summary", response_model=CompanyEarningsSummaryResponse)
def company_earnings_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsSummaryResponse(
            company=None,
            summary=_build_earnings_summary([]),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    refresh = _refresh_for_earnings(background_tasks, snapshot, earnings_cache_state)
    payload = [_serialize_earnings_release(release) for release in earnings_releases]
    return CompanyEarningsSummaryResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, earnings_last_checked),
            last_checked_earnings=earnings_last_checked,
        ),
        summary=_build_earnings_summary(payload),
        refresh=refresh,
        diagnostics=_diagnostics_for_earnings_releases(payload, refresh),
    )


@app.get("/api/companies/{ticker}/earnings/workspace", response_model=CompanyEarningsWorkspaceResponse)
def company_earnings_workspace(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEarningsWorkspaceResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEarningsWorkspaceResponse(
            company=None,
            earnings_releases=[],
            summary=_build_earnings_summary([]),
            model_points=[],
            backtests=EarningsBacktestPayload(
                window_sessions=3,
                quality_directional_consistency=None,
                quality_total_windows=0,
                quality_consistent_windows=0,
                eps_directional_consistency=None,
                eps_total_windows=0,
                eps_consistent_windows=0,
                windows=[],
            ),
            peer_context=EarningsPeerContextPayload(
                peer_group_basis="market_sector",
                peer_group_size=0,
                quality_percentile=None,
                eps_drift_percentile=None,
                sector_group_size=0,
                sector_quality_percentile=None,
                sector_eps_drift_percentile=None,
            ),
            alerts=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    earnings_last_checked, earnings_cache_state = get_company_earnings_cache_status(session, snapshot.company)
    model_last_checked, model_cache_state = get_company_earnings_model_cache_status(session, snapshot.company.id)
    earnings_releases = get_company_earnings_releases(session, snapshot.company.id)
    model_rows = get_company_earnings_model_points(session, snapshot.company.id)
    refresh = _refresh_for_earnings_workspace(background_tasks, snapshot, earnings_cache_state, model_cache_state)

    release_payload = [_serialize_earnings_release(release) for release in earnings_releases]
    model_payload = [_serialize_earnings_model_point(point) for point in model_rows]
    backtest_payload = EarningsBacktestPayload.model_validate(
        build_earnings_directional_backtest(
            model_rows,
            earnings_releases,
            _visible_price_history(session, snapshot.company.id),
        )
    )
    latest_point = model_rows[-1] if model_rows else None
    peer_payload = EarningsPeerContextPayload.model_validate(
        build_earnings_peer_percentiles(session, snapshot.company, latest_point)
    )
    alert_profile = build_sector_alert_profile(session, snapshot.company)
    alerts_payload = [EarningsAlertPayload.model_validate(item) for item in build_earnings_alerts(model_rows, profile=alert_profile)]

    return CompanyEarningsWorkspaceResponse(
        company=_serialize_company(
            snapshot,
            last_checked=_merge_last_checked(snapshot.last_checked, _merge_last_checked(earnings_last_checked, model_last_checked)),
            last_checked_earnings=_merge_last_checked(earnings_last_checked, model_last_checked),
        ),
        earnings_releases=release_payload,
        summary=_build_earnings_summary(release_payload),
        model_points=model_payload,
        backtests=backtest_payload,
        peer_context=peer_payload,
        alerts=alerts_payload,
        refresh=refresh,
        diagnostics=_diagnostics_for_earnings_releases(release_payload, refresh, model_payload),
    )


@app.get("/api/insiders/{ticker}", response_model=InsiderAnalyticsResponse)
def insider_analytics(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> InsiderAnalyticsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    trades = get_company_insider_trades(session, snapshot.company.id, limit=400)
    return _serialize_insider_analytics(build_insider_analytics(trades))


@app.get("/api/ownership/{ticker}", response_model=OwnershipAnalyticsResponse)
def ownership_analytics(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> OwnershipAnalyticsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    holdings = get_company_institutional_holdings(session, snapshot.company.id, limit=600)
    analytics = build_ownership_analytics(holdings)
    return _serialize_ownership_analytics(analytics)


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
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    model: str | None = Query(default=None),
    dupont_mode: str | None = Query(default=None, description="optional DuPont basis: auto|annual|ttm"),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyModelsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    requested_models = _parse_requested_models(model)
    if not settings.valuation_workbench_enabled:
        requested_models = [
            item
            for item in requested_models
            if item not in {"reverse_dcf", "roic", "capital_allocation"}
        ]
    normalized_mode = (dupont_mode or "").lower() or None
    if normalized_mode is not None and normalized_mode not in {"auto", "annual", "ttm"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dupont_mode must be one of: auto, annual, ttm")
    hot_key = (
        f"models:{normalized_ticker}:models={','.join(requested_models)}:dupont={normalized_mode or 'default'}"
        f":asof={_normalize_as_of(parsed_as_of) or 'latest'}"
    )
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload_data, is_fresh = cached_hot
        cached_response = CompanyModelsResponse.model_validate(payload_data)
        if not is_fresh:
            stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
            cached_response = cached_response.model_copy(
                update={
                    "refresh": stale_refresh,
                    "diagnostics": _with_stale_flags(cached_response.diagnostics, _stale_flags_from_refresh(stale_refresh)),
                    "confidence_flags": sorted(set([*cached_response.confidence_flags, *_confidence_flags_from_refresh(stale_refresh)])),
                }
            )

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=cached_response.company.last_checked if cached_response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyModelsResponse(
            company=None,
            requested_models=requested_models,
            models=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            **_empty_provenance_contract("company_missing"),
        )
        payload = _apply_requested_as_of(payload, requested_as_of)
        _store_hot_cached_payload(hot_key, payload)
        return payload

    token = None
    try:
        if normalized_mode is not None:
            token = dupont_model.set_mode_override(normalized_mode)

        refresh = _refresh_for_snapshot(background_tasks, snapshot)
        financials = get_company_financials(session, snapshot.company.id)
        price_last_checked, _price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
        price_history: list[PriceHistory] = []
        if parsed_as_of is not None:
            price_history = _visible_price_history(session, snapshot.company.id)
            financials = select_point_in_time_financials(financials, parsed_as_of)
            price_history = filter_price_history_as_of(price_history, parsed_as_of)

        if parsed_as_of is None and snapshot.cache_state == "fresh" and requested_models:
            model_job_results = ModelEngine(session).compute_models(snapshot.company.id, model_names=requested_models, force=False)
            if any(not result.cached for result in model_job_results):
                session.commit()

        if parsed_as_of is None:
            models: list[ModelRun | dict[str, Any]] = get_company_models(
                session,
                snapshot.company.id,
                requested_models or None,
                config_by_model={"dupont": {"mode": dupont_model.get_mode()}},
            )
        else:
            latest_price = latest_price_as_of(price_history, parsed_as_of)
            dataset = build_company_dataset(
                snapshot.company,
                financials,
                build_market_snapshot(latest_price),
                as_of_date=parsed_as_of,
            )
            models = ModelEngine(session).evaluate_models(
                dataset,
                model_names=requested_models or None,
                created_at=datetime.now(timezone.utc),
            )
        status_counts: dict[str, int] = {}
        for model_run in models:
            result = _model_result_payload(model_run)
            model_status = str(result.get("model_status") or result.get("status") or "unknown")
            status_counts[model_status] = status_counts.get(model_status, 0) + 1
        logging.getLogger(__name__).info(
            "TELEMETRY model_view ticker=%s models=%s status_counts=%s",
            snapshot.company.ticker,
            ",".join(requested_models) if requested_models else "all",
            status_counts,
        )
        serialized_models = [_serialize_model_payload(model_run) for model_run in models]
        diagnostics = _diagnostics_for_models(serialized_models, refresh)
        payload = CompanyModelsResponse(
            company=_serialize_company(snapshot),
            requested_models=requested_models,
            models=serialized_models,
            refresh=refresh,
            diagnostics=diagnostics,
            **_models_provenance_contract(
                models,
                financials,
                price_last_checked=price_last_checked,
                diagnostics=diagnostics,
                refresh=refresh,
            ),
        )
        payload = _apply_requested_as_of(payload, requested_as_of)
        _store_hot_cached_payload(hot_key, payload)
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            payload,
            last_modified=payload.company.last_checked if payload.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return payload
    finally:
        if token is not None:
            dupont_model.reset_mode_override(token)


@app.get("/api/companies/{ticker}/market-context", response_model=CompanyMarketContextResponse)
def company_market_context(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyMarketContextResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = {
            "status": "insufficient_data",
            "curve_points": [],
            "slope_2s10s": {},
            "slope_3m10y": {},
            "fred_series": [],
            "provenance": {
                "treasury": {"status": "missing"},
                "fred": {
                    "enabled": bool(settings.fred_api_key),
                    "status": "missing_api_key" if not settings.fred_api_key else "missing",
                },
            },
            "rates_credit": [],
            "inflation_labor": [],
            "growth_activity": [],
            "relevant_series": [],
            "sector_exposure": [],
            "hqm_snapshot": None,
        }
        refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="missing")
        fetched_at = datetime.now(timezone.utc)
        return CompanyMarketContextResponse(
            company=None,
            status="insufficient_data",
            curve_points=[],
            slope_2s10s=MarketSlopePayload(label="2s10s", value=None, short_tenor="2y", long_tenor="10y", observation_date=None),
            slope_3m10y=MarketSlopePayload(label="3m10y", value=None, short_tenor="3m", long_tenor="10y", observation_date=None),
            fred_series=[],
            provenance_details=payload["provenance"],
            fetched_at=fetched_at,
            refresh=refresh,
            **_market_context_provenance_contract(payload, fetched_at=fetched_at, refresh=refresh),
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    company = snapshot.company
    payload = get_company_market_context_v2(
        session,
        company.id,
        sector=company.sector,
        market_sector=company.market_sector,
        market_industry=company.market_industry,
    )
    return _v2_dict_to_response(payload, company=_serialize_company(snapshot), refresh=refresh)


def _v2_dict_to_response(
    payload: dict[str, Any],
    *,
    company: "CompanyPayload | None",
    refresh: "RefreshState",
) -> "CompanyMarketContextResponse":
    """Convert a v2 macro payload dict to CompanyMarketContextResponse."""
    # Legacy curve_points
    curve_points = [
        MarketCurvePointPayload(
            tenor=p["tenor"],
            rate=p["rate"],
            observation_date=p["observation_date"],
        )
        for p in (payload.get("curve_points") or [])
    ]
    s2 = payload.get("slope_2s10s") or {}
    s3 = payload.get("slope_3m10y") or {}
    slope_2s10s = MarketSlopePayload(
        label=str(s2.get("label") or "2s10s"),
        value=s2.get("value"),
        short_tenor=str(s2.get("short_tenor") or "2y"),
        long_tenor=str(s2.get("long_tenor") or "10y"),
        observation_date=s2.get("observation_date"),
    )
    slope_3m10y = MarketSlopePayload(
        label=str(s3.get("label") or "3m10y"),
        value=s3.get("value"),
        short_tenor=str(s3.get("short_tenor") or "3m"),
        long_tenor=str(s3.get("long_tenor") or "10y"),
        observation_date=s3.get("observation_date"),
    )
    fred_series = [
        MarketFredSeriesPayload(
            series_id=str(item.get("series_id", "")),
            label=str(item.get("label", "")),
            category=str(item.get("category", "")),
            units=str(item.get("units", "")),
            value=item.get("value"),
            observation_date=item.get("observation_date"),
            state=str(item.get("state", "ok")),
        )
        for item in (payload.get("fred_series") or [])
    ]
    # v2 grouped sections
    def _items(section_key: str) -> list[MacroSeriesItemPayload]:
        return [
            MacroSeriesItemPayload(
                series_id=str(d.get("series_id", "")),
                label=str(d.get("label", "")),
                source_name=str(d.get("source_name", "")),
                source_url=str(d.get("source_url", "")),
                units=str(d.get("units", "")),
                value=d.get("value"),
                previous_value=d.get("previous_value"),
                change=d.get("change"),
                change_percent=d.get("change_percent"),
                observation_date=d.get("observation_date"),
                release_date=d.get("release_date"),
                history=[
                    MacroHistoryPointPayload(date=h["date"], value=h["value"])
                    for h in (d.get("history") or [])
                ],
                status=str(d.get("status", "ok")),
            )
            for d in (payload.get(section_key) or [])
        ]

    fetched_raw = payload.get("fetched_at") or ""
    try:
        fetched_at = datetime.fromisoformat(str(fetched_raw))
    except Exception:
        fetched_at = datetime.now(timezone.utc)

    return CompanyMarketContextResponse(
        company=company,
        status=str(payload.get("status") or "ok"),
        curve_points=curve_points,
        slope_2s10s=slope_2s10s,
        slope_3m10y=slope_3m10y,
        fred_series=fred_series,
        provenance_details=payload.get("provenance") or {},
        fetched_at=fetched_at,
        refresh=refresh,
        rates_credit=_items("rates_credit"),
        inflation_labor=_items("inflation_labor"),
        growth_activity=_items("growth_activity"),
        cyclical_demand=_items("cyclical_demand"),
        cyclical_costs=_items("cyclical_costs"),
        relevant_series=list(payload.get("relevant_series") or []),
        relevant_indicators=_items("relevant_indicators"),
        sector_exposure=list(payload.get("sector_exposure") or []),
        hqm_snapshot=payload.get("hqm_snapshot"),
        **_market_context_provenance_contract(payload, fetched_at=fetched_at, refresh=refresh),
    )


@app.get("/api/market-context", response_model=CompanyMarketContextResponse)
def global_market_context(
    session: Session = Depends(get_db_session),
) -> CompanyMarketContextResponse:
    payload = get_market_context_v2(session)
    return _v2_dict_to_response(
        payload,
        company=None,
        refresh=RefreshState(triggered=False, reason="none", ticker=None, job_id=None),
    )


@app.get("/api/companies/{ticker}/sector-context", response_model=CompanySectorContextResponse)
def company_sector_context(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanySectorContextResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="missing")
        fetched_at = datetime.now(timezone.utc)
        return CompanySectorContextResponse(
            company=None,
            status="insufficient_data",
            matched_plugin_ids=[],
            plugins=[],
            fetched_at=fetched_at,
            refresh=refresh,
            provenance=[],
            as_of=None,
            last_refreshed_at=fetched_at.isoformat(),
            source_mix={
                "source_ids": [],
                "source_tiers": [],
                "primary_source_ids": [],
                "fallback_source_ids": [],
                "official_only": False,
            },
            confidence_flags=["company_missing", "no_relevant_sector_plugins"],
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    company = snapshot.company
    payload = get_company_sector_context(
        session,
        company.id,
        sector=company.sector,
        market_sector=company.market_sector,
        market_industry=company.market_industry,
    )
    return CompanySectorContextResponse(
        company=_serialize_company(snapshot),
        status=str(payload.get("status") or "unavailable"),
        matched_plugin_ids=list(payload.get("matched_plugin_ids") or []),
        plugins=list(payload.get("plugins") or []),
        fetched_at=payload.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
        refresh=refresh,
        provenance=list(payload.get("provenance") or []),
        as_of=payload.get("as_of"),
        last_refreshed_at=payload.get("last_refreshed_at"),
        source_mix=dict(payload.get("source_mix") or {}),
        confidence_flags=list(payload.get("confidence_flags") or []),
    )


@app.get("/api/companies/{ticker}/peers", response_model=CompanyPeersResponse)
def company_peers(
    request: Request,
    http_response: Response,
    ticker: str,
    background_tasks: BackgroundTasks,
    peers: str | None = Query(default=None),
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyPeersResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    selected_tickers = _parse_csv_values(peers)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    hot_key = f"peers:{normalized_ticker}:selected={','.join(selected_tickers)}:asof={_normalize_as_of(parsed_as_of) or 'latest'}"
    cached_hot = _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        payload_data, is_fresh = cached_hot
        cached_response = CompanyPeersResponse.model_validate(payload_data)
        if not is_fresh:
            stale_refresh = _trigger_refresh(background_tasks, normalized_ticker, reason="stale")
            cached_response = cached_response.model_copy(
                update={
                    "refresh": stale_refresh,
                    "confidence_flags": sorted(set([*cached_response.confidence_flags, *_confidence_flags_from_refresh(stale_refresh)])),
                }
            )

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=cached_response.company.last_checked if cached_response.company else None,
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    if snapshot is None:
        payload = CompanyPeersResponse(
            company=None,
            peer_basis="Cached peer universe",
            available_companies=[],
            selected_tickers=[],
            peers=[],
            notes={},
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            **_empty_provenance_contract("company_missing"),
        )
        payload = _apply_requested_as_of(payload, requested_as_of)
        _store_hot_cached_payload(hot_key, payload)
        return payload

    price_last_checked, price_cache_state = _visible_price_cache_status(session, snapshot.company.id)
    financials = get_company_financials(session, snapshot.company.id)
    refresh = _refresh_for_financial_page(background_tasks, snapshot, price_cache_state, financials)
    payload = build_peer_comparison(session, snapshot.company.ticker, selected_tickers=selected_tickers, as_of=parsed_as_of)
    logging.getLogger(__name__).info(
        "TELEMETRY peer_view ticker=%s selected=%s count=%s",
        snapshot.company.ticker,
        selected_tickers,
        len(payload.get("peers") or []) if payload else 0,
    )
    if payload is None:
        empty_payload = CompanyPeersResponse(
            company=None,
            peer_basis="Cached peer universe",
            available_companies=[],
            selected_tickers=[],
            peers=[],
            notes={},
            refresh=refresh,
            **_empty_provenance_contract("peer_data_missing"),
        )
        empty_payload = _apply_requested_as_of(empty_payload, requested_as_of)
        _store_hot_cached_payload(hot_key, empty_payload)
        return empty_payload

    response_payload = CompanyPeersResponse(
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
        **_peers_provenance_contract(payload, price_last_checked=price_last_checked, refresh=refresh),
    )
    response_payload = _apply_requested_as_of(response_payload, requested_as_of)
    _store_hot_cached_payload(hot_key, response_payload)
    not_modified = _apply_conditional_headers(
        request,
        http_response,
        response_payload,
        last_modified=response_payload.company.last_checked if response_payload.company else None,
    )
    if not_modified is not None:
        return not_modified  # type: ignore[return-value]
    return response_payload


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
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
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
            diagnostics=_diagnostics_for_filings_timeline(cached_filings, refresh, "sec_submissions"),
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
            diagnostics=_diagnostics_for_filings_timeline(filings, refresh, "sec_submissions"),
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
            diagnostics=_diagnostics_for_filings_timeline(fallback_filings, refresh, "cached_financials"),
            error=(
                "SEC submissions are temporarily unavailable. Showing cached annual and quarterly filings only."
                if fallback_filings
                else "SEC submissions are temporarily unavailable. Try refreshing again shortly."
            ),
        )
    finally:
        client.close()


@app.get("/api/companies/{ticker}/beneficial-ownership", response_model=CompanyBeneficialOwnershipResponse)
def company_beneficial_ownership(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyBeneficialOwnershipResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyBeneficialOwnershipResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    cached_reports = get_company_beneficial_ownership_reports(session, snapshot.company.id)
    filings = _enrich_beneficial_ownership_amendment_history(
        [_serialize_cached_beneficial_ownership_report(report) for report in cached_reports]
    )
    return CompanyBeneficialOwnershipResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/beneficial-ownership/summary", response_model=CompanyBeneficialOwnershipSummaryResponse)
def company_beneficial_ownership_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyBeneficialOwnershipSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyBeneficialOwnershipSummaryResponse(
            company=None,
            summary=_empty_beneficial_ownership_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    cached_reports = get_company_beneficial_ownership_reports(session, snapshot.company.id)
    filings = _enrich_beneficial_ownership_amendment_history(
        [_serialize_cached_beneficial_ownership_report(report) for report in cached_reports]
    )
    return CompanyBeneficialOwnershipSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_beneficial_ownership_summary(filings),
        refresh=refresh,
        error=None,
    )


@app.get("/api/companies/{ticker}/governance", response_model=CompanyGovernanceResponse)
def company_governance(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyGovernanceResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyGovernanceResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_proxy = get_company_proxy_statements(session, snapshot.company.id)
    filings = [_serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    if not filings:
        filings = _load_live_governance_filings(snapshot.company.cik)
    return CompanyGovernanceResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        diagnostics=_diagnostics_for_governance(filings, refresh),
        error=None,
    )


@app.get("/api/companies/{ticker}/governance/summary", response_model=CompanyGovernanceSummaryResponse)
def company_governance_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyGovernanceSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyGovernanceSummaryResponse(
            company=None,
            summary=_empty_governance_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_proxy = get_company_proxy_statements(session, snapshot.company.id)
    filings = [_serialize_cached_proxy_statement(statement) for statement in cached_proxy]
    if not filings:
        filings = _load_live_governance_filings(snapshot.company.cik)
    return CompanyGovernanceSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_governance_summary(filings),
        refresh=refresh,
        diagnostics=_diagnostics_for_governance(filings, refresh),
        error=None,
    )


@app.get("/api/companies/{ticker}/executive-compensation", response_model=CompanyExecutiveCompensationResponse)
def company_executive_compensation(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyExecutiveCompensationResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyExecutiveCompensationResponse(
            company=None,
            rows=[],
            fiscal_years=[],
            source="none",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
        )

    refresh = _refresh_for_governance(background_tasks, session, snapshot)
    cached_rows = get_company_executive_compensation(session, snapshot.company.id)
    source = "cached" if cached_rows else "none"
    if cached_rows:
        serialized = [_serialize_exec_comp_row(row) for row in cached_rows]
    else:
        serialized = _load_live_exec_comp_rows(snapshot.company.cik)
        if serialized:
            source = "live"

    fiscal_years = sorted({row.fiscal_year for row in serialized if row.fiscal_year is not None}, reverse=True)
    return CompanyExecutiveCompensationResponse(
        company=_serialize_company(snapshot),
        rows=serialized,
        fiscal_years=fiscal_years,
        source=source,
        refresh=refresh,
        error=None,
    )


REGISTRATION_FORMS = {
    "S-1", "S-1/A",
    "S-3", "S-3/A",
    "S-4", "S-4/A",
    "F-1", "F-1/A",
    "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4", "424B5",
}

_REGISTRATION_FORM_SUMMARIES: dict[str, str] = {
    "S-1": "Initial registration statement for a domestic IPO or initial public offering.",
    "S-1/A": "Amendment to an S-1 registration statement.",
    "S-3": "Shelf registration statement for eligible domestic issuers.",
    "S-3/A": "Amendment to an S-3 shelf registration.",
    "S-4": "Registration statement for securities issued in business combination transactions.",
    "S-4/A": "Amendment to an S-4 registration statement.",
    "F-1": "Initial registration statement for foreign private issuers.",
    "F-1/A": "Amendment to an F-1 registration statement.",
    "F-3": "Shelf registration for eligible foreign private issuers.",
    "F-3/A": "Amendment to an F-3 registration statement.",
    "424B1": "Prospectus supplement filed under Rule 424(b)(1).",
    "424B2": "Prospectus supplement filed under Rule 424(b)(2).",
    "424B3": "Prospectus supplement filed under Rule 424(b)(3).",
    "424B4": "Prospectus supplement filed under Rule 424(b)(4).",
    "424B5": "Prospectus supplement filed under Rule 424(b)(5).",
}


@app.get("/api/companies/{ticker}/capital-raises", response_model=CompanyCapitalRaisesResponse)
def company_capital_raises(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCapitalRaisesResponse(
            company=None,
            filings=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    cached_events = get_company_capital_markets_events(session, snapshot.company.id)
    filings = [_serialize_cached_capital_markets_event(event) for event in cached_events]
    return CompanyCapitalRaisesResponse(
        company=_serialize_company(snapshot),
        filings=filings,
        refresh=refresh,
        diagnostics=_diagnostics_for_capital_markets(filings, refresh),
        error=None,
    )


@app.get("/api/companies/{ticker}/capital-markets", response_model=CompanyCapitalRaisesResponse)
def company_capital_markets(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalRaisesResponse:
    return company_capital_raises(ticker=ticker, background_tasks=background_tasks, session=session)


@app.get("/api/companies/{ticker}/capital-markets/summary", response_model=CompanyCapitalMarketsSummaryResponse)
def company_capital_markets_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyCapitalMarketsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyCapitalMarketsSummaryResponse(
            company=None,
            summary=_empty_capital_markets_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    rows = [_serialize_cached_capital_markets_event(event) for event in get_company_capital_markets_events(session, snapshot.company.id)]
    return CompanyCapitalMarketsSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_capital_markets_summary(rows),
        refresh=refresh,
        diagnostics=_diagnostics_for_capital_markets(rows, refresh),
        error=None,
    )


@app.get("/api/companies/{ticker}/events", response_model=CompanyEventsResponse)
def company_events(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEventsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyEventsResponse(
            company=None,
            events=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    events = [_serialize_cached_filing_event(event) for event in get_company_filing_events(session, snapshot.company.id)]
    return CompanyEventsResponse(
        company=_serialize_company(snapshot),
        events=events,
        refresh=refresh,
        diagnostics=_diagnostics_for_filing_events(events, refresh),
        error=None,
    )


@app.get("/api/companies/{ticker}/filing-events", response_model=CompanyEventsResponse)
def company_filing_events(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyEventsResponse:
    return company_events(ticker=ticker, background_tasks=background_tasks, session=session)


@app.get("/api/companies/{ticker}/filing-events/summary", response_model=CompanyFilingEventsSummaryResponse)
def company_filing_events_summary(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingEventsSummaryResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingEventsSummaryResponse(
            company=None,
            summary=_empty_filing_events_summary(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    rows = [_serialize_cached_filing_event(event) for event in get_company_filing_events(session, snapshot.company.id)]
    return CompanyFilingEventsSummaryResponse(
        company=_serialize_company(snapshot),
        summary=_build_filing_events_summary(rows),
        refresh=refresh,
        diagnostics=_diagnostics_for_filing_events(rows, refresh),
        error=None,
    )


@app.get("/api/companies/{ticker}/activity-feed", response_model=CompanyActivityFeedResponse)
def company_activity_feed(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyActivityFeedResponse:
    overview = _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)
    return CompanyActivityFeedResponse(
        company=overview.company,
        entries=overview.entries,
        refresh=overview.refresh,
        error=overview.error,
    )


@app.get("/api/companies/{ticker}/alerts", response_model=CompanyAlertsResponse)
def company_alerts(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyAlertsResponse:
    overview = _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)
    return CompanyAlertsResponse(
        company=overview.company,
        alerts=overview.alerts,
        summary=overview.summary,
        refresh=overview.refresh,
        error=overview.error,
    )


@app.get("/api/companies/{ticker}/activity-overview", response_model=CompanyActivityOverviewResponse)
def company_activity_overview(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyActivityOverviewResponse:
    return _build_company_activity_overview_response(ticker=ticker, background_tasks=background_tasks, session=session)


@app.post("/api/watchlist/summary", response_model=WatchlistSummaryResponse)
def watchlist_summary(
    payload: WatchlistSummaryRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> WatchlistSummaryResponse:
    normalized_tickers = _normalize_watchlist_tickers(payload.tickers)
    if len(normalized_tickers) > 50:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A maximum of 50 tickers is allowed")

    snapshots_by_ticker = get_company_snapshots_by_ticker(session, normalized_tickers)
    coverage_counts = get_company_coverage_counts(
        session,
        [snapshot.company.id for snapshot in snapshots_by_ticker.values()],
    )

    companies: list[WatchlistSummaryItemPayload] = []
    for ticker in normalized_tickers:
        snapshot = snapshots_by_ticker.get(ticker)
        if snapshot is None:
            companies.append(_build_missing_watchlist_summary_item(background_tasks, ticker))
            continue
        try:
            companies.append(
                _build_watchlist_summary_item(
                    session,
                    background_tasks,
                    ticker,
                    snapshot=snapshot,
                    coverage_counts=coverage_counts.get(snapshot.company.id),
                )
            )
        except Exception:
            logging.getLogger(__name__).exception("Unable to build watchlist summary item for '%s'", ticker)
            companies.append(_build_missing_watchlist_summary_item(background_tasks, ticker))
    logging.getLogger(__name__).info(
        "TELEMETRY watchlist_summary tickers=%s companies=%s",
        len(normalized_tickers),
        len(companies),
    )
    return WatchlistSummaryResponse(tickers=normalized_tickers, companies=companies)


@app.get("/api/filings/{ticker}", response_model=list[FilingTimelineItemPayload])
def filings_timeline(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> list[FilingTimelineItemPayload]:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    client = EdgarClient()
    try:
        submissions = client.get_submissions(snapshot.company.cik)
        filing_index = client.build_filing_index(submissions)
        filings = _serialize_recent_filings(snapshot.company.cik, filing_index)
        timeline: list[FilingTimelineItemPayload] = []
        for filing in filings:
            timeline.append(
                FilingTimelineItemPayload(
                    date=filing.filing_date or filing.report_date,
                    form=filing.form,
                    description=_filing_timeline_description(filing),
                    accession=filing.accession_number,
                )
            )
        return timeline
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load normalized filing timeline for '%s'", snapshot.company.ticker)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to load filings")
    finally:
        client.close()


@app.get("/api/search_filings", response_model=list[FilingSearchResultPayload])
def search_filings(
    q: str = Query(..., min_length=2, max_length=120),
) -> list[FilingSearchResultPayload]:
    client = EdgarClient()
    try:
        response = client._request("GET", settings.sec_search_base_url, params={"q": q})
        payload = response.json()
        hits = ((payload or {}).get("hits") or {}).get("hits") or []
        results: list[FilingSearchResultPayload] = []
        for item in hits:
            parsed = _serialize_search_filing_hit(item)
            if parsed is not None:
                results.append(parsed)
        return results
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to search SEC filings for query '%s'", q)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to search filings")
    finally:
        client.close()


@app.get("/api/companies/{ticker}/financial-restatements", response_model=CompanyFinancialRestatementsResponse)
def company_financial_restatements(
    ticker: str,
    background_tasks: BackgroundTasks,
    as_of: str | None = Query(default=None, description="Point-in-time cutoff as an ISO-8601 date or timestamp"),
    session: Session = Depends(get_db_session),
) -> CompanyFinancialRestatementsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    requested_as_of = (as_of or "").strip() or None
    parsed_as_of = _validated_as_of(requested_as_of)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        payload = CompanyFinancialRestatementsResponse(
            company=None,
            summary=_empty_financial_restatements_summary(),
            restatements=[],
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            **_empty_provenance_contract("company_missing"),
        )
        return _apply_requested_as_of(payload, requested_as_of)

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    records = get_company_financial_restatements(session, snapshot.company.id)
    if parsed_as_of is not None:
        records = [record for record in records if _financial_restatement_effective_at(record) <= parsed_as_of]

    serialized = [_serialize_financial_restatement(record) for record in records]
    confidence_flags = set(_confidence_flags_from_refresh(refresh))
    for record in serialized:
        confidence_flags.update(record.confidence_impact.flags)

    usages: list[SourceUsage] = []
    companyfacts_usage = _source_usage_from_hint(
        "https://data.sec.gov/api/xbrl/companyfacts/",
        role="primary",
        as_of=requested_as_of or _latest_financial_restatement_as_of(records),
        last_refreshed_at=snapshot.last_checked,
        default_source_id="sec_companyfacts",
    )
    if companyfacts_usage is not None:
        usages.append(companyfacts_usage)
    if any(record.source.startswith("https://www.sec.gov/Archives/") for record in records):
        filing_usage = _source_usage_from_hint(
            "https://www.sec.gov/Archives/",
            role="supplemental",
            as_of=requested_as_of or _latest_financial_restatement_as_of(records),
            last_refreshed_at=snapshot.last_checked,
            default_source_id="sec_edgar",
        )
        if filing_usage is not None:
            usages.append(filing_usage)

    payload = CompanyFinancialRestatementsResponse(
        company=_serialize_company(snapshot),
        summary=_build_financial_restatements_summary(serialized),
        restatements=serialized,
        refresh=refresh,
        **_build_provenance_contract(
            usages,
            as_of=requested_as_of or _latest_financial_restatement_as_of(records),
            last_refreshed_at=_merge_last_checked(snapshot.last_checked, *(record.last_checked for record in records)),
            confidence_flags=sorted(confidence_flags),
        ),
    )
    return _apply_requested_as_of(payload, requested_as_of)


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


def _refresh_for_capital_structure(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
    last_capital_structure_check: datetime | None,
    history: list[Any],
) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)
    if last_capital_structure_check is None or not history:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _refresh_for_governance(
    background_tasks: BackgroundTasks,
    session: Session,
    snapshot: CompanyCacheSnapshot,
) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)

    _last_checked, proxy_cache_state = get_company_proxy_cache_status(session, snapshot.company)
    if proxy_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=proxy_cache_state)

    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _refresh_for_earnings(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
    earnings_cache_state: Literal["fresh", "stale", "missing"],
) -> RefreshState:
    if snapshot.cache_state == "missing":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
    if snapshot.cache_state == "stale":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="stale")
    if earnings_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=earnings_cache_state)
    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _refresh_for_earnings_workspace(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
    earnings_cache_state: Literal["fresh", "stale", "missing"],
    model_cache_state: Literal["fresh", "stale", "missing"],
) -> RefreshState:
    if snapshot.cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=snapshot.cache_state)
    if earnings_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=earnings_cache_state)
    if model_cache_state in {"missing", "stale"}:
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason=model_cache_state)
    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _get_cached_search_response(query: str) -> CompanySearchResponse | None:
    now = time.monotonic()
    with _search_response_cache_lock:
        cached = _search_response_cache.get(query)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _search_response_cache.pop(query, None)
            return None
        return CompanySearchResponse.model_validate(payload)


def _store_cached_search_response(query: str, response: CompanySearchResponse) -> None:
    expires_at = time.monotonic() + SEARCH_RESPONSE_TTL_SECONDS
    with _search_response_cache_lock:
        _search_response_cache[query] = (expires_at, response.model_dump())


def _get_hot_cached_payload(key: str) -> tuple[dict[str, Any], bool] | None:
    now = time.monotonic()
    with _hot_response_cache_lock:
        cached = _hot_response_cache.get(key)
        if cached is None:
            _record_cache_metric("hot_cache.miss")
            return None

        fresh_until, stale_until, payload = cached
        if now <= stale_until:
            _record_cache_metric("hot_cache.hit_fresh" if now <= fresh_until else "hot_cache.hit_stale")
            return payload, now <= fresh_until

        _hot_response_cache.pop(key, None)
        _record_cache_metric("hot_cache.expired")
        return None


def _store_hot_cached_payload(key: str, payload: BaseModel) -> None:
    now = time.monotonic()
    fresh_until = now + settings.hot_response_cache_ttl_seconds
    stale_until = fresh_until + settings.hot_response_cache_stale_ttl_seconds
    with _hot_response_cache_lock:
        _hot_response_cache[key] = (fresh_until, stale_until, payload.model_dump(mode="json"))
    _record_cache_metric("hot_cache.store")


def _apply_conditional_headers(
    request: Request,
    response: Response,
    payload: BaseModel,
    *,
    last_modified: datetime | None,
) -> Response | None:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    etag = f'W/"{hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]}"'
    response.headers["ETag"] = etag

    if last_modified is not None:
        normalized = last_modified if last_modified.tzinfo else last_modified.replace(tzinfo=timezone.utc)
        response.headers["Last-Modified"] = format_datetime(normalized, usegmt=True)

    response.headers["Cache-Control"] = "private, max-age=0, stale-while-revalidate=120"

    if request.headers.get("if-none-match") == etag:
        _record_cache_metric("conditional.etag_304")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))

    if last_modified is not None:
        if_modified_since = request.headers.get("if-modified-since")
        if if_modified_since and response.headers.get("Last-Modified") == if_modified_since:
            _record_cache_metric("conditional.last_modified_304")
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))

    _record_cache_metric("conditional.cacheable_200")

    return None


def _record_cache_metric(key: str) -> None:
    with _cache_metric_lock:
        _cache_metric_counts[key] = _cache_metric_counts.get(key, 0) + 1


def _company_market_classification(company: Any) -> tuple[str | None, str | None]:
    if not settings.strict_official_mode:
        return getattr(company, "market_sector", None), getattr(company, "market_industry", None)
    profile = resolve_sec_sic_profile(None, getattr(company, "sector", None))
    return profile.market_sector, profile.market_industry


def _visible_price_cache_status(session: Session, company_id: int) -> tuple[datetime | None, PriceCacheState]:
    if settings.strict_official_mode:
        return None, "fresh"
    return get_company_price_cache_status(session, company_id)


def _visible_price_history(session: Session, company_id: int) -> list[PriceHistory]:
    if settings.strict_official_mode:
        return []
    return get_company_price_history(session, company_id)


def _visible_financials_for_company(session: Session, company: Any) -> list[FinancialStatement]:
    sec_financials = get_company_financials(session, company.id)
    regulated_financials = get_company_regulated_bank_financials(session, company.id)
    return select_preferred_financials(company, sec_financials, regulated_financials)


def _regulated_entity_payload(company: Any, financials: list[Any] | None = None) -> RegulatedEntityPayload | None:
    payload = build_regulated_entity_payload(company, financials)
    return RegulatedEntityPayload.model_validate(payload) if payload is not None else None


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


def _metrics_staleness_reason(
    snapshot: CompanyCacheSnapshot,
    price_cache_state: Literal["fresh", "stale", "missing"],
    financials: list[FinancialStatement],
) -> str:
    if snapshot.cache_state == "missing":
        return "financials_missing"
    if snapshot.cache_state == "stale":
        return "financials_stale"
    if price_cache_state == "missing":
        return "price_missing"
    if price_cache_state == "stale":
        return "price_stale"
    if _needs_segment_backfill(financials):
        return "segment_backfill_missing"
    return "fresh"


def _sanitize_metric_provenance_for_strict_official_mode(provenance: dict[str, Any]) -> dict[str, Any]:
    if not settings.strict_official_mode:
        return provenance
    sanitized = dict(provenance)
    if "price_source" in sanitized:
        sanitized["price_source"] = None
    return sanitized


def _sanitize_metrics_timeseries_points_for_strict_official_mode(
    points: list[MetricsTimeseriesPointPayload],
) -> list[MetricsTimeseriesPointPayload]:
    if not settings.strict_official_mode:
        return points

    sanitized_points: list[MetricsTimeseriesPointPayload] = []
    for point in points:
        metrics_updates = {
            metric_key: None
            for metric_key in PRICE_DEPENDENT_TIMESERIES_METRIC_KEYS
            if getattr(point.metrics, metric_key, None) is not None
        }
        quality_flags = list(point.quality.flags)
        if metrics_updates:
            quality_flags = sorted(set([*quality_flags, "strict_official_mode_price_disabled"]))
        sanitized_points.append(
            point.model_copy(
                update={
                    "metrics": point.metrics.model_copy(update=metrics_updates),
                    "provenance": point.provenance.model_copy(
                        update=_sanitize_metric_provenance_for_strict_official_mode(point.provenance.model_dump())
                    ),
                    "quality": point.quality.model_copy(update={"flags": quality_flags}),
                }
            )
        )
    return sanitized_points


def _sanitize_derived_metric_values_for_strict_official_mode(
    metrics: list[DerivedMetricValuePayload],
) -> list[DerivedMetricValuePayload]:
    if not settings.strict_official_mode:
        return metrics

    sanitized_metrics: list[DerivedMetricValuePayload] = []
    for metric in metrics:
        provenance = metric.provenance if isinstance(metric.provenance, dict) else {}
        next_quality_flags = list(metric.quality_flags)
        next_value = metric.metric_value
        if metric.metric_key in PRICE_DEPENDENT_DERIVED_METRIC_KEYS:
            next_value = None
            next_quality_flags = sorted(set([*next_quality_flags, "strict_official_mode_price_disabled"]))
        sanitized_metrics.append(
            metric.model_copy(
                update={
                    "metric_value": next_value,
                    "provenance": _sanitize_metric_provenance_for_strict_official_mode(dict(provenance)),
                    "quality_flags": next_quality_flags,
                }
            )
        )
    return sanitized_metrics


def _sanitize_derived_metric_periods_for_strict_official_mode(
    periods: list[DerivedMetricPeriodPayload],
) -> list[DerivedMetricPeriodPayload]:
    if not settings.strict_official_mode:
        return periods
    return [
        period.model_copy(update={"metrics": _sanitize_derived_metric_values_for_strict_official_mode(period.metrics)})
        for period in periods
    ]


def _sanitize_price_snapshot_for_strict_official_mode(snapshot: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(snapshot)
    sanitized["latest_price"] = None
    sanitized["price_date"] = None
    sanitized["price_source"] = None
    sanitized["price_available"] = False
    return sanitized


def _sanitize_model_result_for_strict_official_mode(model_name: str, result: dict[str, Any]) -> dict[str, Any]:
    if not settings.strict_official_mode:
        return result

    sanitized = deepcopy(result)
    price_snapshot = sanitized.get("price_snapshot")
    if isinstance(price_snapshot, dict):
        sanitized["price_snapshot"] = _sanitize_price_snapshot_for_strict_official_mode(price_snapshot)

    assumption_provenance = sanitized.get("assumption_provenance")
    if isinstance(assumption_provenance, dict):
        nested_price_snapshot = assumption_provenance.get("price_snapshot")
        if isinstance(nested_price_snapshot, dict):
            assumption_provenance["price_snapshot"] = _sanitize_price_snapshot_for_strict_official_mode(nested_price_snapshot)

    if str(model_name).lower() == "reverse_dcf":
        sanitized.update(
            {
                "status": "insufficient_data",
                "model_status": "insufficient_data",
                "explanation": status_explanation("insufficient_data"),
                "reason": "Strict official mode disables commercial price inputs, so reverse DCF is unavailable.",
                "implied_growth": None,
                "implied_margin": None,
                "market_cap_proxy": None,
                "heatmap": [],
            }
        )

    return sanitized


def _refresh_for_filing_insights(
    background_tasks: BackgroundTasks,
    snapshot: CompanyCacheSnapshot,
) -> RefreshState:
    if snapshot.cache_state == "missing":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="missing")
    if snapshot.cache_state == "stale":
        return _trigger_refresh(background_tasks, snapshot.company.ticker, reason="stale")
    return RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)


def _trigger_refresh(
    background_tasks: BackgroundTasks,
    ticker: str,
    *,
    reason: Literal["manual", "missing", "stale"],
) -> RefreshState:
    normalized_ticker = _normalize_ticker(ticker)
    job_id = queue_company_refresh(background_tasks, normalized_ticker, force=(reason == "missing"))
    return RefreshState(triggered=True, reason=reason, ticker=normalized_ticker, job_id=job_id)


def _serialize_company(
    snapshot: CompanyCacheSnapshot,
    last_checked: datetime | None = None,
    *,
    last_checked_prices: datetime | None = None,
    last_checked_insiders: datetime | None = None,
    last_checked_institutional: datetime | None = None,
    last_checked_filings: datetime | None = None,
    last_checked_earnings: datetime | None = None,
    regulated_entity: RegulatedEntityPayload | None = None,
) -> CompanyPayload:
    market_sector, market_industry = _company_market_classification(snapshot.company)
    return CompanyPayload(
        ticker=snapshot.company.ticker,
        cik=snapshot.company.cik,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        market_sector=market_sector,
        market_industry=market_industry,
        regulated_entity=regulated_entity,
        strict_official_mode=settings.strict_official_mode,
        last_checked=last_checked if last_checked is not None else snapshot.last_checked,
        last_checked_financials=snapshot.last_checked,
        last_checked_prices=last_checked_prices,
        last_checked_insiders=last_checked_insiders,
        last_checked_institutional=last_checked_institutional,
        last_checked_filings=last_checked_filings,
        earnings_last_checked=last_checked_earnings,
        cache_state=snapshot.cache_state,
    )


_FINANCIAL_DIAGNOSTIC_FIELDS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "total_assets",
    "current_assets",
    "total_liabilities",
    "current_liabilities",
    "sga",
    "research_and_development",
    "cash_and_cash_equivalents",
    "stockholders_equity",
    "operating_cash_flow",
    "free_cash_flow",
    "eps",
)


def _round_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _mean_ratio(values: list[float | None]) -> float | None:
    observed = [float(value) for value in values if value is not None]
    if not observed:
        return None
    return _round_ratio(sum(observed) / len(observed))


def _build_data_quality_diagnostics(
    *,
    coverage_ratio: float | None = None,
    fallback_ratio: float | None = None,
    stale_flags: list[str] | None = None,
    parser_confidence: float | None = None,
    missing_field_flags: list[str] | None = None,
    reconciliation_penalty: float | None = None,
    reconciliation_disagreement_count: int = 0,
) -> DataQualityDiagnosticsPayload:
    return DataQualityDiagnosticsPayload(
        coverage_ratio=_round_ratio(coverage_ratio),
        fallback_ratio=_round_ratio(fallback_ratio),
        stale_flags=sorted(set(stale_flags or [])),
        parser_confidence=_round_ratio(parser_confidence),
        missing_field_flags=sorted(set(missing_field_flags or [])),
        reconciliation_penalty=_round_ratio(reconciliation_penalty),
        reconciliation_disagreement_count=max(0, int(reconciliation_disagreement_count or 0)),
    )


def _with_stale_flags(
    diagnostics: DataQualityDiagnosticsPayload | None,
    stale_flags: list[str],
) -> DataQualityDiagnosticsPayload:
    current = diagnostics or DataQualityDiagnosticsPayload()
    return current.model_copy(update={"stale_flags": sorted(set([*current.stale_flags, *stale_flags]))})


def _stale_flags_from_refresh(refresh: RefreshState | None, *reasons: str | None) -> list[str]:
    flags: list[str] = []
    if refresh is not None and refresh.reason in {"stale", "missing"}:
        flags.append(f"refresh_{refresh.reason}_queued")
    for reason in reasons:
        if reason and reason not in {"fresh", "none"}:
            flags.append(reason)
    return sorted(set(flags))


def _normalize_as_of(value: DateType | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, DateType):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _parse_as_of(value: DateType | datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, DateType):
        return datetime(value.year, value.month, value.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text.count("-") == 2 and "T" not in text and " " not in text:
        try:
            parsed_date = DateType.fromisoformat(text)
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed_date = DateType.fromisoformat(text)
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validated_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = _parse_as_of(value)
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="as_of must be an ISO-8601 date or timestamp")
    return parsed


def _apply_requested_as_of(payload: BaseModel, as_of: str | None) -> Any:
    if as_of is None:
        return payload
    return payload.model_copy(update={"as_of": as_of})


def _latest_as_of(*values: DateType | datetime | str | None) -> str | None:
    best_text: str | None = None
    best_value: datetime | None = None
    for value in values:
        text = _normalize_as_of(value)
        if text is None:
            continue
        parsed = _parse_as_of(text)
        if parsed is None:
            if best_text is None:
                best_text = text
            continue
        if best_value is None or parsed > best_value:
            best_value = parsed
            best_text = text
    return best_text


def _source_usage_from_hint(
    source_hint: str | None,
    *,
    role: Literal["primary", "supplemental", "derived", "fallback"],
    as_of: DateType | datetime | str | None = None,
    last_refreshed_at: datetime | str | None = None,
    default_source_id: str | None = None,
) -> SourceUsage | None:
    source_id = infer_source_id(source_hint, default=default_source_id)
    if source_id is None:
        return None
    return SourceUsage(
        source_id=source_id,
        role=role,
        as_of=as_of,
        last_refreshed_at=last_refreshed_at,
    )


def _build_provenance_contract(
    usages: list[SourceUsage],
    *,
    as_of: DateType | datetime | str | None = None,
    last_refreshed_at: datetime | None = None,
    confidence_flags: list[str] | None = None,
) -> dict[str, Any]:
    entries = build_provenance_entries(usages)
    source_mix = SourceMixPayload.model_validate(build_source_mix(entries))
    combined_flags = {flag for flag in (confidence_flags or []) if flag}
    if settings.strict_official_mode:
        combined_flags.add("strict_official_mode")
    if source_mix.fallback_source_ids:
        combined_flags.add("commercial_fallback_present")
    if any(str(entry.get("source_tier") or "") == "manual_override" for entry in entries):
        combined_flags.add("manual_override_present")
    return {
        "provenance": [ProvenanceEntryPayload.model_validate(entry) for entry in entries],
        "as_of": _normalize_as_of(as_of),
        "last_refreshed_at": last_refreshed_at,
        "source_mix": source_mix,
        "confidence_flags": sorted(combined_flags),
    }


def _empty_provenance_contract(*flags: str) -> dict[str, Any]:
    return _build_provenance_contract([], confidence_flags=[flag for flag in flags if flag])


def _confidence_flags_from_diagnostics(diagnostics: DataQualityDiagnosticsPayload | None) -> list[str]:
    if diagnostics is None:
        return []
    flags = set(diagnostics.stale_flags)
    flags.update(diagnostics.missing_field_flags)
    if diagnostics.fallback_ratio not in (None, 0):
        flags.add("fallback_path_present")
    if diagnostics.reconciliation_disagreement_count > 0:
        flags.add("financial_reconciliation_disagreement")
    if diagnostics.parser_confidence is not None and diagnostics.parser_confidence < 0.75:
        flags.add("reduced_parser_confidence")
    return sorted(flags)


def _confidence_flags_from_refresh(refresh: RefreshState | None) -> list[str]:
    if refresh is None:
        return []
    if refresh.reason == "stale":
        return ["stale_data"]
    if refresh.reason == "missing":
        return ["missing_data"]
    return []


def _coverage_ratio_for_fields(payload: Any, field_names: tuple[str, ...]) -> float | None:
    if not field_names:
        return None
    present = sum(1 for field_name in field_names if getattr(payload, field_name, None) is not None)
    return present / len(field_names)


def _missing_fields_for_fields(payload: Any, field_names: tuple[str, ...]) -> list[str]:
    return [field_name for field_name in field_names if getattr(payload, field_name, None) is None]


def _diagnostics_for_financial_response(
    financials: list[FinancialPayload],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    coverage_ratio = _mean_ratio([_coverage_ratio_for_fields(item, _FINANCIAL_DIAGNOSTIC_FIELDS) for item in financials])
    latest_missing = _missing_fields_for_fields(financials[0], _FINANCIAL_DIAGNOSTIC_FIELDS) if financials else []
    latest_reconciliation = financials[0].reconciliation if financials else None
    return _build_data_quality_diagnostics(
        coverage_ratio=coverage_ratio,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=(latest_reconciliation.confidence_score if latest_reconciliation is not None else coverage_ratio),
        missing_field_flags=sorted(
            set(
                [
                    *latest_missing,
                    *(latest_reconciliation.missing_field_flags if latest_reconciliation is not None else []),
                ]
            )
        ),
        reconciliation_penalty=(latest_reconciliation.confidence_penalty if latest_reconciliation is not None else None),
        reconciliation_disagreement_count=(latest_reconciliation.disagreement_count if latest_reconciliation is not None else 0),
    )


def _diagnostics_for_capital_structure(
    history: list[CapitalStructureSnapshotPayload],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    if not history:
        return _build_data_quality_diagnostics(
            coverage_ratio=0.0,
            stale_flags=_stale_flags_from_refresh(refresh),
            parser_confidence=0.0,
            missing_field_flags=["capital_structure_missing"],
        )

    latest = history[0]
    section_scores = [
        latest.debt_maturity_ladder.meta.confidence_score,
        latest.lease_obligations.meta.confidence_score,
        latest.debt_rollforward.meta.confidence_score,
        latest.interest_burden.meta.confidence_score,
        latest.capital_returns.meta.confidence_score,
        latest.net_dilution_bridge.meta.confidence_score,
    ]
    coverage_ratio = _mean_ratio([float(score) for score in section_scores if score is not None])
    return _build_data_quality_diagnostics(
        coverage_ratio=coverage_ratio,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=latest.confidence_score if latest.confidence_score is not None else coverage_ratio,
        missing_field_flags=sorted(set(latest.quality_flags)),
    )


def _diagnostics_for_filing_insights(
    insights: list[FilingParserInsightPayload],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    coverage_fields = ("revenue", "net_income", "operating_income")
    coverage_values: list[float] = []
    missing_flags: list[str] = []
    for insight in insights:
        base_ratio = _coverage_ratio_for_fields(insight, coverage_fields) or 0.0
        coverage_values.append((base_ratio * 3 + (1.0 if insight.segments else 0.0)) / 4)
    if insights:
        missing_flags.extend(_missing_fields_for_fields(insights[0], coverage_fields))
        if not insights[0].segments:
            missing_flags.append("segments")
    confidence = _mean_ratio(coverage_values)
    return _build_data_quality_diagnostics(
        coverage_ratio=confidence,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=confidence,
        missing_field_flags=missing_flags,
    )


def _diagnostics_for_changes_since_last_filing(
    comparison: dict[str, Any],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    sections = [
        comparison.get("metric_deltas") or [],
        comparison.get("new_risk_indicators") or [],
        comparison.get("segment_shifts") or [],
        comparison.get("share_count_changes") or [],
        comparison.get("capital_structure_changes") or [],
    ]
    populated_sections = sum(1 for section in sections if section)
    missing_field_flags: list[str] = []
    if comparison.get("previous_filing") is None:
        missing_field_flags.append("previous_comparable_filing_missing")
    if not comparison.get("segment_shifts"):
        missing_field_flags.append("segment_shift_data_unavailable")
    if not comparison.get("amended_prior_values"):
        missing_field_flags.append("amended_prior_value_data_unavailable")
    return _build_data_quality_diagnostics(
        coverage_ratio=populated_sections / float(len(sections)) if sections else None,
        stale_flags=_stale_flags_from_refresh(refresh),
        missing_field_flags=missing_field_flags,
    )


def _diagnostics_for_metrics_timeseries(
    series: list[MetricsTimeseriesPointPayload],
    refresh: RefreshState,
    staleness_reason: str | None,
) -> DataQualityDiagnosticsPayload:
    coverage_ratio = _mean_ratio([point.quality.coverage_ratio for point in series])
    missing_flags = list(series[-1].quality.missing_metrics) if series else []
    return _build_data_quality_diagnostics(
        coverage_ratio=coverage_ratio,
        stale_flags=_stale_flags_from_refresh(refresh, staleness_reason),
        missing_field_flags=missing_flags,
    )


def _diagnostics_for_derived_metrics_periods(
    periods: list[DerivedMetricPeriodPayload],
    refresh: RefreshState,
    staleness_reason: str | None,
) -> DataQualityDiagnosticsPayload:
    metrics = [metric for period in periods for metric in period.metrics]
    if not metrics:
        return _build_data_quality_diagnostics(stale_flags=_stale_flags_from_refresh(refresh, staleness_reason))
    available = sum(1 for metric in metrics if metric.metric_value is not None)
    proxy_count = sum(1 for metric in metrics if metric.is_proxy)
    latest_missing = [metric.metric_key for metric in periods[-1].metrics if metric.metric_value is None] if periods else []
    return _build_data_quality_diagnostics(
        coverage_ratio=available / len(metrics),
        fallback_ratio=proxy_count / len(metrics),
        stale_flags=_stale_flags_from_refresh(refresh, staleness_reason),
        missing_field_flags=latest_missing,
    )


def _diagnostics_for_derived_metrics_values(
    metrics: list[DerivedMetricValuePayload],
    refresh: RefreshState,
    staleness_reason: str | None,
) -> DataQualityDiagnosticsPayload:
    if not metrics:
        return _build_data_quality_diagnostics(stale_flags=_stale_flags_from_refresh(refresh, staleness_reason))
    available = sum(1 for metric in metrics if metric.metric_value is not None)
    proxy_count = sum(1 for metric in metrics if metric.is_proxy)
    latest_missing = [metric.metric_key for metric in metrics if metric.metric_value is None]
    return _build_data_quality_diagnostics(
        coverage_ratio=available / len(metrics),
        fallback_ratio=proxy_count / len(metrics),
        stale_flags=_stale_flags_from_refresh(refresh, staleness_reason),
        missing_field_flags=latest_missing,
    )


def _diagnostics_for_earnings_releases(
    releases: list[EarningsReleasePayload],
    refresh: RefreshState,
    model_points: list[EarningsModelPointPayload] | None = None,
) -> DataQualityDiagnosticsPayload:
    coverage_values: list[float] = []
    missing_flags: list[str] = []
    for release in releases:
        coverage_bits = [
            release.revenue,
            release.operating_income,
            release.net_income,
            release.diluted_eps,
            release.reported_period_end,
            release.exhibit_document or release.primary_document,
        ]
        coverage_values.append(sum(1 for value in coverage_bits if value is not None) / len(coverage_bits))
    if releases:
        latest = releases[0]
        if latest.revenue is None:
            missing_flags.append("revenue")
        if latest.operating_income is None:
            missing_flags.append("operating_income")
        if latest.net_income is None:
            missing_flags.append("net_income")
        if latest.diluted_eps is None:
            missing_flags.append("diluted_eps")
        if latest.exhibit_document is None and latest.primary_document is None:
            missing_flags.append("document_reference")
    fallback_ratio = None
    if releases:
        metadata_only = sum(1 for release in releases if release.parse_state != "parsed")
        fallback_ratio = metadata_only / len(releases)
    if model_points:
        observed_fallbacks = [point.fallback_ratio for point in model_points if point.fallback_ratio is not None]
        if observed_fallbacks:
            fallback_ratio = _mean_ratio(observed_fallbacks)
    confidence = _mean_ratio(coverage_values)
    return _build_data_quality_diagnostics(
        coverage_ratio=confidence,
        fallback_ratio=fallback_ratio,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=confidence,
        missing_field_flags=missing_flags,
    )


def _diagnostics_for_governance(
    filings: list[GovernanceFilingPayload],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    coverage_values: list[float] = []
    missing_flags: list[str] = []
    for filing in filings:
        score = sum(
            1
            for present in (
                filing.meeting_date is not None,
                filing.executive_comp_table_detected,
                filing.vote_item_count > 0,
                filing.board_nominee_count is not None,
                bool(filing.vote_outcomes),
            )
            if present
        )
        coverage_values.append(score / 5)
    if filings:
        latest = filings[0]
        if latest.meeting_date is None:
            missing_flags.append("meeting_date")
        if not latest.executive_comp_table_detected:
            missing_flags.append("summary_compensation_table")
        if latest.vote_item_count <= 0:
            missing_flags.append("vote_items")
        if latest.board_nominee_count is None:
            missing_flags.append("board_nominee_count")
    confidence = _mean_ratio(coverage_values)
    return _build_data_quality_diagnostics(
        coverage_ratio=confidence,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=confidence,
        missing_field_flags=missing_flags,
    )


def _diagnostics_for_capital_markets(
    filings: list[CapitalRaisePayload],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    coverage_values = [
        sum(1 for present in (filing.event_type, filing.security_type, filing.offering_amount) if present is not None) / 3
        for filing in filings
    ]
    missing_flags: list[str] = []
    if filings:
        latest = filings[0]
        if latest.event_type is None:
            missing_flags.append("event_type")
        if latest.security_type is None:
            missing_flags.append("security_type")
        if latest.offering_amount is None and not latest.is_late_filer:
            missing_flags.append("offering_amount")
    confidence = _mean_ratio(coverage_values)
    return _build_data_quality_diagnostics(
        coverage_ratio=confidence,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=confidence,
        missing_field_flags=missing_flags,
    )


def _diagnostics_for_filing_events(
    events: list[FilingEventPayload],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    coverage_values = [
        sum(
            1
            for present in (
                event.item_code not in {None, "UNSPECIFIED"},
                bool(event.category),
                bool(event.summary),
                bool(event.key_amounts) or bool(event.exhibit_references),
            )
            if present
        )
        / 4
        for event in events
    ]
    missing_flags: list[str] = []
    if events:
        latest = events[0]
        if latest.item_code in {None, "UNSPECIFIED"}:
            missing_flags.append("item_code")
        if not latest.key_amounts:
            missing_flags.append("key_amounts")
        if not latest.exhibit_references:
            missing_flags.append("exhibit_references")
    confidence = _mean_ratio(coverage_values)
    return _build_data_quality_diagnostics(
        coverage_ratio=confidence,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=confidence,
        missing_field_flags=missing_flags,
    )


def _diagnostics_for_filings_timeline(
    filings: list[FilingPayload],
    refresh: RefreshState,
    timeline_source: str,
) -> DataQualityDiagnosticsPayload:
    coverage_values = [
        sum(1 for present in (filing.accession_number, filing.primary_document, filing.filing_date or filing.report_date, filing.source_url) if present is not None) / 4
        for filing in filings
    ]
    missing_flags: list[str] = []
    if filings:
        latest = filings[0]
        if latest.accession_number is None:
            missing_flags.append("accession_number")
        if latest.primary_document is None:
            missing_flags.append("primary_document")
    stale_flags = _stale_flags_from_refresh(refresh)
    if timeline_source == "cached_financials":
        stale_flags.append("timeline_cached_financials")
    return _build_data_quality_diagnostics(
        coverage_ratio=_mean_ratio(coverage_values),
        fallback_ratio=1.0 if timeline_source == "cached_financials" else 0.0,
        stale_flags=stale_flags,
        parser_confidence=0.65 if timeline_source == "cached_financials" else 1.0,
        missing_field_flags=missing_flags,
    )


def _model_missing_field_flags(model: ModelPayload) -> list[str]:
    result = model.result if isinstance(model.result, dict) else {}
    missing_fields = result.get("missing_required_fields_last_3y") or result.get("missing_fields") or []
    if isinstance(missing_fields, list):
        return [str(field_name) for field_name in missing_fields]
    return []


def _model_confidence_score(model: ModelPayload) -> float | None:
    result = model.result if isinstance(model.result, dict) else {}
    status_value = str(result.get("model_status") or result.get("status") or "unknown").lower()
    if status_value == "ok":
        return 1.0
    if status_value == "partial":
        return 0.75
    if status_value == "proxy":
        return 0.5
    if status_value == "insufficient_data":
        return 0.2
    if status_value == "unsupported":
        return 0.0
    summary_value = str(result.get("confidence_summary") or result.get("trust_summary") or "").lower()
    if "high" in summary_value or "strong" in summary_value:
        return 1.0
    if "partial" in summary_value or "moderate" in summary_value:
        return 0.6
    if summary_value:
        return 0.4
    return None


def _diagnostics_for_models(
    models: list[ModelPayload],
    refresh: RefreshState,
) -> DataQualityDiagnosticsPayload:
    if not models:
        return _build_data_quality_diagnostics(stale_flags=_stale_flags_from_refresh(refresh))
    statuses = [
        str((model.result or {}).get("model_status") if isinstance(model.result, dict) else "unknown").lower()
        for model in models
    ]
    coverage_ratio = sum(1 for status_value in statuses if status_value in {"ok", "partial", "proxy"}) / len(models)
    fallback_ratio = sum(1 for status_value in statuses if status_value == "proxy") / len(models)
    missing_flags = sorted({flag for model in models for flag in _model_missing_field_flags(model)})
    confidence = _mean_ratio([_model_confidence_score(model) for model in models])
    return _build_data_quality_diagnostics(
        coverage_ratio=coverage_ratio,
        fallback_ratio=fallback_ratio,
        stale_flags=_stale_flags_from_refresh(refresh),
        parser_confidence=confidence,
        missing_field_flags=missing_flags,
    )


def _financials_provenance_contract(
    financials: list[FinancialStatement],
    price_history: list[PriceHistory],
    *,
    price_last_checked: datetime | None,
    diagnostics: DataQualityDiagnosticsPayload,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    latest_statement = financials[0] if financials else None
    latest_price = price_history[-1] if price_history else None
    usages: list[SourceUsage] = []

    for statement in financials[:12]:
        usage = _source_usage_from_hint(
            statement.source,
            role="primary",
            as_of=statement.period_end,
            last_refreshed_at=statement.last_checked,
            default_source_id="sec_companyfacts",
        )
        if usage is not None:
            usages.append(usage)

        reconciliation = getattr(statement, "reconciliation", None)
        if isinstance(reconciliation, dict) and reconciliation.get("status") in {"matched", "disagreement", "parser_missing"}:
            usage = _source_usage_from_hint(
                reconciliation.get("matched_source"),
                role="supplemental",
                as_of=reconciliation.get("matched_period_end") or statement.period_end,
                last_refreshed_at=reconciliation.get("last_refreshed_at") or statement.last_checked,
                default_source_id="sec_edgar",
            )
            if usage is not None:
                usages.append(usage)

    if latest_price is not None:
        usage = _source_usage_from_hint(
            latest_price.source,
            role="fallback",
            as_of=latest_price.trade_date,
            last_refreshed_at=price_last_checked,
            default_source_id="yahoo_finance",
        )
        if usage is not None:
            usages.append(usage)

    confidence_flags = [
        *_confidence_flags_from_diagnostics(diagnostics),
        *_confidence_flags_from_refresh(refresh),
    ]
    return _build_provenance_contract(
        usages,
        as_of=latest_statement.period_end if latest_statement is not None else (latest_price.trade_date if latest_price is not None else None),
        last_refreshed_at=_merge_last_checked(
            latest_statement.last_checked if latest_statement is not None else None,
            price_last_checked,
        ),
        confidence_flags=confidence_flags,
    )


def _capital_structure_provenance_contract(
    snapshots: list[Any],
    *,
    latest: CapitalStructureSnapshotPayload | None,
    last_capital_structure_check: datetime | None,
    diagnostics: DataQualityDiagnosticsPayload,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    usages: list[SourceUsage] = []
    if latest is not None:
        usages.append(
            SourceUsage(
                source_id="ft_capital_structure_intelligence",
                role="derived",
                as_of=latest.period_end,
                last_refreshed_at=last_capital_structure_check,
            )
        )

    for snapshot in snapshots[:12]:
        provenance_details = getattr(snapshot, "provenance", None)
        official_source_id = provenance_details.get("official_source_id") if isinstance(provenance_details, dict) else None
        if official_source_id:
            usages.append(
                SourceUsage(
                    source_id=str(official_source_id),
                    role="primary",
                    as_of=getattr(snapshot, "period_end", None),
                    last_refreshed_at=getattr(snapshot, "last_checked", None),
                )
            )
        statement_usage = _source_usage_from_hint(
            getattr(snapshot, "source", None),
            role="supplemental" if official_source_id else "primary",
            as_of=getattr(snapshot, "period_end", None),
            last_refreshed_at=getattr(snapshot, "last_checked", None),
            default_source_id="sec_companyfacts",
        )
        if statement_usage is not None:
            usages.append(statement_usage)

    confidence_flags = [
        *_confidence_flags_from_diagnostics(diagnostics),
        *(latest.quality_flags if latest is not None else []),
        *_confidence_flags_from_refresh(refresh),
    ]
    return _build_provenance_contract(
        usages,
        as_of=latest.period_end if latest is not None else None,
        last_refreshed_at=last_capital_structure_check,
        confidence_flags=confidence_flags,
    )


def _metrics_timeseries_provenance_contract(
    series: list[MetricsTimeseriesPointPayload],
    *,
    last_financials_check: datetime | None,
    last_price_check: datetime | None,
    diagnostics: DataQualityDiagnosticsPayload,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    latest_point = series[-1] if series else None
    usages: list[SourceUsage] = []

    if latest_point is not None:
        usages.append(
            SourceUsage(
                source_id="ft_derived_metrics_engine",
                role="derived",
                as_of=latest_point.period_end,
                last_refreshed_at=_merge_last_checked(last_financials_check, last_price_check),
            )
        )

    for point in series:
        statement_usage = _source_usage_from_hint(
            point.provenance.statement_source,
            role="primary",
            as_of=point.period_end,
            last_refreshed_at=last_financials_check,
            default_source_id="sec_companyfacts",
        )
        if statement_usage is not None:
            usages.append(statement_usage)
        if point.provenance.price_source:
            price_usage = _source_usage_from_hint(
                point.provenance.price_source,
                role="fallback",
                as_of=point.period_end,
                last_refreshed_at=last_price_check,
                default_source_id="yahoo_finance",
            )
            if price_usage is not None:
                usages.append(price_usage)

    confidence_flags = [
        *_confidence_flags_from_diagnostics(diagnostics),
        *(latest_point.quality.flags if latest_point is not None else []),
        *_confidence_flags_from_refresh(refresh),
    ]
    return _build_provenance_contract(
        usages,
        as_of=latest_point.period_end if latest_point is not None else None,
        last_refreshed_at=_merge_last_checked(last_financials_check, last_price_check),
        confidence_flags=confidence_flags,
    )


def _derived_metrics_provenance_contract(
    metric_values: list[DerivedMetricValuePayload],
    *,
    as_of: DateType | datetime | str | None,
    derived_source_id: str,
    last_metrics_check: datetime | None,
    last_financials_check: datetime | None,
    last_price_check: datetime | None,
    diagnostics: DataQualityDiagnosticsPayload,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    usages: list[SourceUsage] = []
    if as_of is not None:
        usages.append(
            SourceUsage(
                source_id=derived_source_id,
                role="derived",
                as_of=as_of,
                last_refreshed_at=_merge_last_checked(last_metrics_check, last_financials_check, last_price_check),
            )
        )

    quality_flags: set[str] = set()
    for metric in metric_values:
        provenance = metric.provenance if isinstance(metric.provenance, dict) else {}
        statement_usage = _source_usage_from_hint(
            provenance.get("statement_source"),
            role="primary",
            as_of=as_of,
            last_refreshed_at=last_financials_check,
            default_source_id="sec_companyfacts",
        )
        if statement_usage is not None:
            usages.append(statement_usage)
        price_source = provenance.get("price_source")
        if price_source:
            price_usage = _source_usage_from_hint(
                str(price_source),
                role="fallback",
                as_of=as_of,
                last_refreshed_at=last_price_check,
                default_source_id="yahoo_finance",
            )
            if price_usage is not None:
                usages.append(price_usage)
        quality_flags.update(str(flag) for flag in metric.quality_flags if flag)

    confidence_flags = [
        *_confidence_flags_from_diagnostics(diagnostics),
        *sorted(quality_flags),
        *_confidence_flags_from_refresh(refresh),
    ]
    return _build_provenance_contract(
        usages,
        as_of=as_of,
        last_refreshed_at=_merge_last_checked(last_metrics_check, last_financials_check, last_price_check),
        confidence_flags=confidence_flags,
    )


def _models_provenance_contract(
    model_runs: list[ModelRun | dict[str, Any]],
    financials: list[FinancialStatement],
    *,
    price_last_checked: datetime | None,
    diagnostics: DataQualityDiagnosticsPayload,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    usages: list[SourceUsage] = []
    latest_statement = financials[0] if financials else None
    model_created_at = _merge_last_checked(*(_model_created_at(model_run) for model_run in model_runs)) if model_runs else None
    model_as_of = latest_statement.period_end if latest_statement is not None else _model_response_as_of(model_runs)

    if model_as_of is not None:
        usages.append(
            SourceUsage(
                source_id="ft_model_engine",
                role="derived",
                as_of=model_as_of,
                last_refreshed_at=model_created_at,
            )
        )

    for statement in financials[:12]:
        statement_usage = _source_usage_from_hint(
            statement.source,
            role="primary",
            as_of=statement.period_end,
            last_refreshed_at=statement.last_checked,
            default_source_id="sec_companyfacts",
        )
        if statement_usage is not None:
            usages.append(statement_usage)

    extra_flags: set[str] = set()
    for model_run in model_runs:
        result = _sanitize_model_result_for_strict_official_mode(
            _model_name(model_run),
            _model_result_payload(model_run),
        )
        status_value = str(result.get("model_status") or result.get("status") or "").lower()
        if status_value == "partial":
            extra_flags.add("partial_model_inputs")
        elif status_value == "proxy":
            extra_flags.add("proxy_model_outputs")
        elif status_value == "insufficient_data":
            extra_flags.add("insufficient_model_inputs")
        elif status_value == "unsupported":
            extra_flags.add("unsupported_model_present")
        for flag in result.get("status_flags") or []:
            if flag:
                extra_flags.add(str(flag))

        price_snapshot = result.get("price_snapshot")
        if isinstance(price_snapshot, dict):
            price_source = price_snapshot.get("price_source")
            if price_source:
                price_usage = _source_usage_from_hint(
                    str(price_source),
                    role="fallback",
                    as_of=price_snapshot.get("price_date") or model_as_of,
                    last_refreshed_at=price_last_checked,
                    default_source_id="yahoo_finance",
                )
                if price_usage is not None:
                    usages.append(price_usage)

        assumption_provenance = result.get("assumption_provenance")
        if isinstance(assumption_provenance, dict):
            risk_free = assumption_provenance.get("risk_free_rate")
            if isinstance(risk_free, dict):
                risk_free_usage = _source_usage_from_hint(
                    str(risk_free.get("source_name") or ""),
                    role="supplemental",
                    as_of=risk_free.get("observation_date"),
                    last_refreshed_at=_model_created_at(model_run),
                )
                if risk_free_usage is not None:
                    usages.append(risk_free_usage)

    confidence_flags = [
        *_confidence_flags_from_diagnostics(diagnostics),
        *sorted(extra_flags),
        *_confidence_flags_from_refresh(refresh),
    ]
    return _build_provenance_contract(
        usages,
        as_of=model_as_of,
        last_refreshed_at=_merge_last_checked(
            model_created_at,
            latest_statement.last_checked if latest_statement is not None else None,
            price_last_checked,
        ),
        confidence_flags=confidence_flags,
    )


def _market_context_provenance_contract(
    payload: dict[str, Any],
    *,
    fetched_at: datetime,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    usages: list[SourceUsage] = []
    provenance_details = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    treasury_details = provenance_details.get("treasury") if isinstance(provenance_details.get("treasury"), dict) else {}
    fred_details = provenance_details.get("fred") if isinstance(provenance_details.get("fred"), dict) else {}

    treasury_usage = _source_usage_from_hint(
        str(treasury_details.get("source_name") or treasury_details.get("source_url") or ""),
        role="primary",
        as_of=treasury_details.get("observation_date"),
        last_refreshed_at=fetched_at,
        default_source_id="us_treasury_daily_par_yield_curve",
    )
    if treasury_usage is not None:
        usages.append(treasury_usage)

    fred_usage = _source_usage_from_hint(
        str(fred_details.get("source") or fred_details.get("source_name") or ""),
        role="supplemental",
        as_of=_latest_as_of(*[item.get("observation_date") for item in payload.get("fred_series") or [] if isinstance(item, dict)]),
        last_refreshed_at=fetched_at,
    )
    if fred_usage is not None:
        usages.append(fred_usage)

    for section_key in ("rates_credit", "inflation_labor", "growth_activity", "cyclical_demand", "cyclical_costs", "relevant_indicators"):
        for item in payload.get(section_key) or []:
            if not isinstance(item, dict):
                continue
            usage = _source_usage_from_hint(
                str(item.get("source_url") or item.get("source_name") or ""),
                role="supplemental",
                as_of=item.get("observation_date") or item.get("release_date"),
                last_refreshed_at=fetched_at,
            )
            if usage is not None:
                usages.append(usage)

    hqm_snapshot = payload.get("hqm_snapshot")
    if isinstance(hqm_snapshot, dict):
        hqm_usage = _source_usage_from_hint(
            str(hqm_snapshot.get("source_url") or hqm_snapshot.get("source_name") or ""),
            role="supplemental",
            as_of=hqm_snapshot.get("observation_date"),
            last_refreshed_at=fetched_at,
        )
        if hqm_usage is not None:
            usages.append(hqm_usage)

    as_of_values: list[DateType | datetime | str | None] = []
    as_of_values.extend(point.get("observation_date") for point in payload.get("curve_points") or [] if isinstance(point, dict))
    as_of_values.extend(item.get("observation_date") for item in payload.get("fred_series") or [] if isinstance(item, dict))
    as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("rates_credit") or [] if isinstance(item, dict))
    as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("inflation_labor") or [] if isinstance(item, dict))
    as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("growth_activity") or [] if isinstance(item, dict))
    as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("cyclical_demand") or [] if isinstance(item, dict))
    as_of_values.extend(item.get("observation_date") or item.get("release_date") for item in payload.get("cyclical_costs") or [] if isinstance(item, dict))
    if isinstance(hqm_snapshot, dict):
        as_of_values.append(hqm_snapshot.get("observation_date"))

    status_value = str(payload.get("status") or "ok")
    confidence_flags = [
        *_confidence_flags_from_refresh(refresh),
    ]
    if status_value != "ok":
        confidence_flags.append(f"market_context_{status_value}")
    treasury_status = str(treasury_details.get("status") or "ok")
    if treasury_status != "ok":
        confidence_flags.append(f"treasury_{treasury_status}")
    if bool(treasury_details.get("fallback_used")):
        confidence_flags.append("treasury_fallback_used")
    fred_status = str(fred_details.get("status") or "ok")
    if fred_status == "missing_api_key":
        confidence_flags.append("supplemental_fred_unconfigured")
    elif fred_status != "ok":
        confidence_flags.append(f"fred_{fred_status}")
    census_details = provenance_details.get("census") if isinstance(provenance_details.get("census"), dict) else {}
    census_status = str(census_details.get("status") or "ok")
    if census_status != "ok":
        confidence_flags.append(f"census_{census_status}")
    bls_details = provenance_details.get("bls") if isinstance(provenance_details.get("bls"), dict) else {}
    bls_status = str(bls_details.get("status") or "ok")
    if bls_status != "ok":
        confidence_flags.append(f"bls_{bls_status}")
    bea_details = provenance_details.get("bea") if isinstance(provenance_details.get("bea"), dict) else {}
    if not bool(bea_details.get("configured", True)):
        confidence_flags.append("bea_unconfigured")
    bea_status = str(bea_details.get("status") or "ok")
    if bea_status != "ok":
        confidence_flags.append(f"bea_{bea_status}")

    return _build_provenance_contract(
        usages,
        as_of=_latest_as_of(*as_of_values),
        last_refreshed_at=fetched_at,
        confidence_flags=confidence_flags,
    )


def _peers_provenance_contract(
    payload: dict[str, Any],
    *,
    price_last_checked: datetime | None,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    usages: list[SourceUsage] = []
    peers = payload.get("peers") or []
    focus_row = next((row for row in peers if isinstance(row, dict) and row.get("is_focus")), None)
    source_hints = payload.get("source_hints") if isinstance(payload.get("source_hints"), dict) else {}
    company = payload.get("company")
    company_last_checked = getattr(company, "last_checked", None)
    as_of = None
    if isinstance(focus_row, dict):
        as_of = focus_row.get("period_end") or focus_row.get("price_date")

    usages.append(
        SourceUsage(
            source_id="ft_peer_comparison",
            role="derived",
            as_of=as_of,
            last_refreshed_at=_merge_last_checked(company_last_checked, price_last_checked),
        )
    )

    financial_sources = source_hints.get("financial_statement_sources") if isinstance(source_hints.get("financial_statement_sources"), list) else []
    for source_hint in financial_sources or ["sec_companyfacts"]:
        statement_usage = _source_usage_from_hint(
            str(source_hint),
            role="primary",
            as_of=as_of,
            last_refreshed_at=company_last_checked,
            default_source_id="sec_companyfacts",
        )
        if statement_usage is not None:
            usages.append(statement_usage)

    price_sources = source_hints.get("price_sources") if isinstance(source_hints.get("price_sources"), list) else []
    if not price_sources and isinstance(focus_row, dict) and focus_row.get("price_date"):
        price_sources = ["yahoo_finance"]
    for source_hint in price_sources:
        price_usage = _source_usage_from_hint(
            str(source_hint),
            role="fallback",
            as_of=focus_row.get("price_date") if isinstance(focus_row, dict) else None,
            last_refreshed_at=price_last_checked,
            default_source_id="yahoo_finance",
        )
        if price_usage is not None:
            usages.append(price_usage)

    risk_free_sources = source_hints.get("risk_free_sources") if isinstance(source_hints.get("risk_free_sources"), list) else []
    for source_hint in risk_free_sources:
        risk_free_usage = _source_usage_from_hint(
            str(source_hint),
            role="supplemental",
            as_of=as_of,
            last_refreshed_at=company_last_checked,
        )
        if risk_free_usage is not None:
            usages.append(risk_free_usage)

    confidence_flags = set(_confidence_flags_from_refresh(refresh))
    if any(isinstance(row, dict) and str(row.get("cache_state") or "") != "fresh" for row in peers):
        confidence_flags.add("stale_peer_inputs")
    if any(isinstance(row, dict) and str(row.get("dcf_model_status") or "") == "partial" for row in peers):
        confidence_flags.add("partial_peer_models")
    if any(isinstance(row, dict) and str(row.get("dcf_model_status") or "") == "proxy" for row in peers):
        confidence_flags.add("proxy_peer_models")
    if any(isinstance(row, dict) and str(row.get("dcf_model_status") or "") == "unsupported" for row in peers):
        confidence_flags.add("unsupported_peer_models")
    if any(isinstance(row, dict) and str(row.get("reverse_dcf_model_status") or "") == "unsupported" for row in peers):
        confidence_flags.add("unsupported_peer_models")

    return _build_provenance_contract(
        usages,
        as_of=as_of,
        last_refreshed_at=_merge_last_checked(company_last_checked, price_last_checked),
        confidence_flags=sorted(confidence_flags),
    )


def _activity_overview_provenance_contract(
    entries: list[ActivityFeedEntryPayload],
    *,
    market_context_status: dict[str, Any] | None,
    last_refreshed_at: datetime | None,
    refresh: RefreshState | None = None,
) -> dict[str, Any]:
    latest_entry_date = max((entry.date for entry in entries if entry.date is not None), default=None)
    usages: list[SourceUsage] = [
        SourceUsage(
            source_id="ft_activity_overview",
            role="derived",
            as_of=latest_entry_date,
            last_refreshed_at=last_refreshed_at,
        ),
        SourceUsage(
            source_id="sec_edgar",
            role="primary",
            as_of=latest_entry_date,
            last_refreshed_at=last_refreshed_at,
        ),
    ]

    if market_context_status:
        macro_usage = _source_usage_from_hint(
            str(market_context_status.get("source") or ""),
            role="supplemental",
            as_of=market_context_status.get("observation_date"),
            last_refreshed_at=last_refreshed_at,
        )
        if macro_usage is not None:
            usages.append(macro_usage)

    confidence_flags = set(_confidence_flags_from_refresh(refresh))
    if not entries:
        confidence_flags.add("activity_feed_empty")
    if market_context_status:
        state = str(market_context_status.get("state") or "ok")
        if state != "ok":
            confidence_flags.add(f"market_context_{state}")

    return _build_provenance_contract(
        usages,
        as_of=latest_entry_date,
        last_refreshed_at=last_refreshed_at,
        confidence_flags=sorted(confidence_flags),
    )


def _model_response_as_of(model_runs: list[ModelRun | dict[str, Any]]) -> str | None:
    values: list[DateType | datetime | str | None] = []
    for model_run in model_runs:
        result = _model_result_payload(model_run)
        values.append(result.get("base_period_end"))
        values.append(result.get("period_end"))
        price_snapshot = result.get("price_snapshot")
        if isinstance(price_snapshot, dict):
            values.append(price_snapshot.get("price_date"))

        input_periods = model_run.get("input_periods") if isinstance(model_run, dict) else model_run.input_periods
        if isinstance(input_periods, dict):
            values.append(input_periods.get("period_end"))
        elif isinstance(input_periods, list):
            for item in input_periods:
                if isinstance(item, dict):
                    values.append(item.get("period_end"))
    return _latest_as_of(*values)


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
        current_assets=data.get("current_assets"),
        total_liabilities=data.get("total_liabilities"),
        current_liabilities=data.get("current_liabilities"),
        retained_earnings=data.get("retained_earnings"),
        sga=data.get("sga"),
        research_and_development=data.get("research_and_development"),
        interest_expense=data.get("interest_expense"),
        income_tax_expense=data.get("income_tax_expense"),
        inventory=data.get("inventory"),
        cash_and_cash_equivalents=data.get("cash_and_cash_equivalents"),
        short_term_investments=data.get("short_term_investments"),
        cash_and_short_term_investments=data.get("cash_and_short_term_investments"),
        accounts_receivable=data.get("accounts_receivable"),
        accounts_payable=data.get("accounts_payable"),
        goodwill_and_intangibles=data.get("goodwill_and_intangibles"),
        current_debt=data.get("current_debt"),
        long_term_debt=data.get("long_term_debt"),
        stockholders_equity=data.get("stockholders_equity"),
        lease_liabilities=data.get("lease_liabilities"),
        operating_cash_flow=data.get("operating_cash_flow"),
        depreciation_and_amortization=data.get("depreciation_and_amortization"),
        capex=data.get("capex"),
        acquisitions=data.get("acquisitions"),
        debt_changes=data.get("debt_changes"),
        dividends=data.get("dividends"),
        share_buybacks=data.get("share_buybacks"),
        free_cash_flow=data.get("free_cash_flow"),
        eps=data.get("eps"),
        shares_outstanding=data.get("shares_outstanding"),
        stock_based_compensation=data.get("stock_based_compensation"),
        weighted_average_diluted_shares=data.get("weighted_average_diluted_shares"),
        regulated_bank=_serialize_regulated_bank_financial(data),
        segment_breakdown=[_serialize_financial_segment(item) for item in data.get("segment_breakdown", []) if isinstance(item, dict)],
        reconciliation=_serialize_financial_reconciliation(getattr(statement, "reconciliation", None)),
    )


def _serialize_regulated_bank_financial(data: dict[str, Any]) -> RegulatedBankFinancialPayload | None:
    source_id = data.get("regulated_bank_source_id")
    reporting_basis = data.get("regulated_bank_reporting_basis")
    if source_id not in {"fdic_bankfind_financials", "federal_reserve_fr_y9c"}:
        return None
    if reporting_basis not in {"fdic_call_report", "fr_y9c"}:
        return None

    return RegulatedBankFinancialPayload(
        source_id=source_id,
        reporting_basis=reporting_basis,
        confidence_score=data.get("regulated_bank_confidence_score"),
        confidence_flags=[str(flag) for flag in data.get("regulated_bank_confidence_flags", []) if flag],
        net_interest_income=data.get("net_interest_income"),
        noninterest_income=data.get("noninterest_income"),
        noninterest_expense=data.get("noninterest_expense"),
        pretax_income=data.get("pretax_income"),
        provision_for_credit_losses=data.get("provision_for_credit_losses"),
        deposits_total=data.get("deposits_total"),
        core_deposits=data.get("core_deposits"),
        uninsured_deposits=data.get("uninsured_deposits"),
        loans_net=data.get("loans_net"),
        net_interest_margin=data.get("net_interest_margin"),
        nonperforming_assets_ratio=data.get("nonperforming_assets_ratio"),
        common_equity_tier1_ratio=data.get("common_equity_tier1_ratio"),
        tier1_risk_weighted_ratio=data.get("tier1_risk_weighted_ratio"),
        total_risk_based_capital_ratio=data.get("total_risk_based_capital_ratio"),
        return_on_assets_ratio=data.get("return_on_assets_ratio"),
        return_on_equity_ratio=data.get("return_on_equity_ratio"),
        tangible_common_equity=data.get("tangible_common_equity"),
    )


def _serialize_capital_structure_snapshot(snapshot: Any) -> CapitalStructureSnapshotPayload:
    data = snapshot.data if isinstance(getattr(snapshot, "data", None), dict) else {}
    return CapitalStructureSnapshotPayload(
        accession_number=getattr(snapshot, "accession_number", None),
        filing_type=getattr(snapshot, "filing_type", ""),
        statement_type=getattr(snapshot, "statement_type", ""),
        period_start=getattr(snapshot, "period_start"),
        period_end=getattr(snapshot, "period_end"),
        source=getattr(snapshot, "source", ""),
        filing_acceptance_at=getattr(snapshot, "filing_acceptance_at", None),
        last_updated=getattr(snapshot, "last_updated"),
        last_checked=getattr(snapshot, "last_checked"),
        summary=CapitalStructureSummaryPayload.model_validate(data.get("summary") or {}),
        debt_maturity_ladder=CapitalStructureDebtMaturityPayload.model_validate(data.get("debt_maturity_ladder") or {}),
        lease_obligations=CapitalStructureLeaseObligationsPayload.model_validate(data.get("lease_obligations") or {}),
        debt_rollforward=CapitalStructureDebtRollforwardPayload.model_validate(data.get("debt_rollforward") or {}),
        interest_burden=CapitalStructureInterestBurdenPayload.model_validate(data.get("interest_burden") or {}),
        capital_returns=CapitalStructureCapitalReturnsPayload.model_validate(data.get("capital_returns") or {}),
        net_dilution_bridge=CapitalStructureNetDilutionBridgePayload.model_validate(data.get("net_dilution_bridge") or {}),
        provenance_details=getattr(snapshot, "provenance", None) if isinstance(getattr(snapshot, "provenance", None), dict) else {},
        quality_flags=list(getattr(snapshot, "quality_flags", None) or []),
        confidence_score=getattr(snapshot, "confidence_score", None),
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
        operating_income=payload.get("operating_income"),
        assets=payload.get("assets"),
    )


def _serialize_filing_parser_segment(payload: dict[str, Any]) -> FilingParserSegmentPayload:
    return FilingParserSegmentPayload(
        name=str(payload.get("name") or payload.get("segment") or payload.get("segment_name") or "Unknown"),
        revenue=payload.get("revenue"),
    )


def _serialize_filing_parser_insight(statement: FinancialStatement) -> FilingParserInsightPayload:
    data = statement.data or {}
    return FilingParserInsightPayload(
        accession_number=_extract_accession_number(statement.source),
        filing_type=statement.filing_type,
        period_start=statement.period_start,
        period_end=statement.period_end,
        source=statement.source,
        last_updated=statement.last_updated,
        last_checked=statement.last_checked,
        revenue=data.get("revenue"),
        net_income=data.get("net_income"),
        operating_income=data.get("operating_income"),
        segments=[
            _serialize_filing_parser_segment(item)
            for item in data.get("segments", [])
            if isinstance(item, dict)
        ],
    )


def _serialize_financial_reconciliation(payload: Any) -> FinancialReconciliationPayload | None:
    if not isinstance(payload, dict) or not payload:
        return None
    status = str(payload.get("status") or "parser_missing")
    if status not in {"matched", "disagreement", "parser_missing", "unsupported_form"}:
        status = "parser_missing"
    return FinancialReconciliationPayload(
        status=status,
        as_of=payload.get("as_of"),
        last_refreshed_at=payload.get("last_refreshed_at"),
        provenance_sources=[str(source) for source in payload.get("provenance_sources", []) if source],
        confidence_score=payload.get("confidence_score"),
        confidence_penalty=payload.get("confidence_penalty"),
        confidence_flags=[str(flag) for flag in payload.get("confidence_flags", []) if flag],
        missing_field_flags=[str(flag) for flag in payload.get("missing_field_flags", []) if flag],
        matched_accession_number=payload.get("matched_accession_number"),
        matched_filing_type=payload.get("matched_filing_type"),
        matched_period_start=payload.get("matched_period_start"),
        matched_period_end=payload.get("matched_period_end"),
        matched_source=payload.get("matched_source"),
        disagreement_count=int(payload.get("disagreement_count") or 0),
        comparisons=[
            _serialize_financial_reconciliation_comparison(item)
            for item in payload.get("comparisons", [])
            if isinstance(item, dict)
        ],
    )


def _serialize_financial_reconciliation_comparison(payload: dict[str, Any]) -> FinancialReconciliationComparisonPayload:
    status = str(payload.get("status") or "unavailable")
    if status not in {"match", "disagreement", "companyfacts_only", "parser_only", "unavailable"}:
        status = "unavailable"
    return FinancialReconciliationComparisonPayload(
        metric_key=str(payload.get("metric_key") or "unknown"),
        status=status,
        companyfacts_value=payload.get("companyfacts_value"),
        filing_parser_value=payload.get("filing_parser_value"),
        delta=payload.get("delta"),
        relative_delta=payload.get("relative_delta"),
        confidence_penalty=payload.get("confidence_penalty"),
        companyfacts_fact=_serialize_financial_fact_reference(payload.get("companyfacts_fact")),
        filing_parser_fact=_serialize_financial_fact_reference(payload.get("filing_parser_fact")),
    )


def _serialize_financial_restatement(record: FinancialRestatement) -> FinancialRestatementPayload:
    return FinancialRestatementPayload(
        accession_number=record.accession_number,
        previous_accession_number=record.previous_accession_number,
        filing_type=record.filing_type,
        form=record.form,
        is_amendment=record.is_amendment,
        detection_kind=(
            record.detection_kind
            if record.detection_kind in {"amended_filing", "companyfacts_revision"}
            else "companyfacts_revision"
        ),
        period_start=record.period_start,
        period_end=record.period_end,
        filing_date=record.filing_date,
        previous_filing_date=record.previous_filing_date,
        filing_acceptance_at=record.filing_acceptance_at,
        previous_filing_acceptance_at=record.previous_filing_acceptance_at,
        source=record.source,
        previous_source=record.previous_source,
        changed_metric_keys=list(record.changed_metric_keys or []),
        normalized_data_changes=[
            _serialize_financial_restatement_metric_change(item)
            for item in (record.normalized_data_changes or [])
            if isinstance(item, dict)
        ],
        companyfacts_changes=[
            _serialize_financial_restatement_metric_change(item)
            for item in (record.companyfacts_changes or [])
            if isinstance(item, dict)
        ],
        confidence_impact=_serialize_financial_restatement_confidence_impact(record.confidence_impact or {}),
        last_updated=record.last_updated,
        last_checked=record.last_checked,
    )


def _serialize_financial_restatement_metric_change(payload: dict[str, Any]) -> FinancialRestatementMetricChangePayload:
    return FinancialRestatementMetricChangePayload(
        metric_key=str(payload.get("metric_key") or "unknown"),
        previous_value=payload.get("previous_value"),
        current_value=payload.get("current_value"),
        delta=payload.get("delta"),
        relative_change=payload.get("relative_change"),
        direction=(
            str(payload.get("direction") or "changed")
            if str(payload.get("direction") or "changed") in {"added", "removed", "increase", "decrease", "changed"}
            else "changed"
        ),
        previous_fact=_serialize_financial_fact_reference(payload.get("previous_fact")),
        current_fact=_serialize_financial_fact_reference(payload.get("current_fact")),
        value_changed=payload.get("value_changed"),
    )


def _serialize_financial_fact_reference(payload: Any) -> FinancialFactReferencePayload | None:
    if not isinstance(payload, dict):
        return None
    if not any(
        key in payload
        for key in ("accession_number", "form", "taxonomy", "tag", "unit", "source", "filed_at", "period_start", "period_end", "value")
    ):
        return None
    return FinancialFactReferencePayload(
        accession_number=payload.get("accession_number"),
        form=payload.get("form"),
        taxonomy=payload.get("taxonomy"),
        tag=payload.get("tag"),
        unit=payload.get("unit"),
        source=payload.get("source"),
        filed_at=payload.get("filed_at"),
        period_start=payload.get("period_start"),
        period_end=payload.get("period_end"),
        value=payload.get("value"),
    )


def _serialize_financial_restatement_confidence_impact(payload: dict[str, Any]) -> FinancialRestatementConfidenceImpactPayload:
    severity = str(payload.get("severity") or "low")
    if severity not in {"low", "medium", "high"}:
        severity = "low"
    return FinancialRestatementConfidenceImpactPayload(
        severity=severity,
        flags=[str(flag) for flag in payload.get("flags", []) if flag],
        largest_relative_change=payload.get("largest_relative_change"),
        changed_metric_count=int(payload.get("changed_metric_count") or 0),
    )


def _build_financial_restatements_summary(
    records: list[FinancialRestatementPayload],
) -> FinancialRestatementSummaryPayload:
    if not records:
        return _empty_financial_restatements_summary()

    periods: dict[tuple[str, DateType, DateType], list[FinancialRestatementPayload]] = {}
    for record in records:
        periods.setdefault((record.filing_type, record.period_start, record.period_end), []).append(record)

    changed_periods: list[FinancialRestatementPeriodSummaryPayload] = []
    for (_filing_type, _period_start, _period_end), grouped in sorted(
        periods.items(),
        key=lambda item: (item[0][2], item[0][0]),
        reverse=True,
    ):
        latest = max(
            grouped,
            key=lambda item: (
                item.filing_acceptance_at or datetime.min.replace(tzinfo=timezone.utc),
                item.filing_date or DateType.min,
                item.accession_number,
            ),
        )
        changed_periods.append(
            FinancialRestatementPeriodSummaryPayload(
                filing_type=latest.filing_type,
                period_start=latest.period_start,
                period_end=latest.period_end,
                restatement_count=len(grouped),
                changed_metric_keys=sorted({metric for item in grouped for metric in item.changed_metric_keys}),
                latest_accession_number=latest.accession_number,
                latest_filing_date=latest.filing_date,
            )
        )

    severity_counts = {
        "high": sum(1 for record in records if record.confidence_impact.severity == "high"),
        "medium": sum(1 for record in records if record.confidence_impact.severity == "medium"),
        "low": sum(1 for record in records if record.confidence_impact.severity == "low"),
    }
    return FinancialRestatementSummaryPayload(
        total_restatements=len(records),
        amended_filings=sum(1 for record in records if record.is_amendment),
        companyfacts_revisions=sum(1 for record in records if record.detection_kind == "companyfacts_revision"),
        amended_metric_keys=sorted({metric for record in records for metric in record.changed_metric_keys}),
        changed_periods=changed_periods,
        high_confidence_impacts=severity_counts["high"],
        medium_confidence_impacts=severity_counts["medium"],
        low_confidence_impacts=severity_counts["low"],
        latest_filing_date=max((record.filing_date for record in records if record.filing_date is not None), default=None),
        latest_filing_acceptance_at=max(
            (record.filing_acceptance_at for record in records if record.filing_acceptance_at is not None),
            default=None,
        ),
    )


def _empty_financial_restatements_summary() -> FinancialRestatementSummaryPayload:
    return FinancialRestatementSummaryPayload(
        total_restatements=0,
        amended_filings=0,
        companyfacts_revisions=0,
        amended_metric_keys=[],
        changed_periods=[],
        high_confidence_impacts=0,
        medium_confidence_impacts=0,
        low_confidence_impacts=0,
        latest_filing_date=None,
        latest_filing_acceptance_at=None,
    )


def _financial_restatement_effective_at(record: FinancialRestatement) -> datetime:
    if record.filing_acceptance_at is not None:
        return _parse_as_of(record.filing_acceptance_at) or datetime.min.replace(tzinfo=timezone.utc)
    if record.filing_date is not None:
        return _parse_as_of(record.filing_date) or datetime.min.replace(tzinfo=timezone.utc)
    return _parse_as_of(record.period_end) or datetime.min.replace(tzinfo=timezone.utc)


def _latest_financial_restatement_as_of(records: list[FinancialRestatement]) -> str | None:
    return _latest_as_of(*(_financial_restatement_effective_at(record) for record in records))


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
        filing_date=trade.filing_date,
        filing_type=trade.filing_type,
        accession_number=trade.accession_number,
        source=trade.source,
        action=trade.action,
        transaction_code=trade.transaction_code,
        shares=trade.shares,
        price=trade.price,
        value=trade.value,
        ownership_after=trade.ownership_after,
        security_title=getattr(trade, "security_title", None),
        is_derivative=getattr(trade, "is_derivative", None),
        ownership_nature=getattr(trade, "ownership_nature", None),
        exercise_price=getattr(trade, "exercise_price", None),
        expiration_date=getattr(trade, "expiration_date", None),
        footnote_tags=getattr(trade, "footnote_tags", None),
        is_10b5_1=trade.is_10b5_1,
    )


def _serialize_form144_filing(filing: Form144Filing) -> Form144FilingPayload:
    return Form144FilingPayload(
        accession_number=filing.accession_number,
        form=filing.form,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        filer_name=filing.filer_name,
        relationship_to_issuer=filing.relationship_to_issuer,
        issuer_name=filing.issuer_name,
        security_title=filing.security_title,
        planned_sale_date=filing.planned_sale_date,
        shares_to_be_sold=filing.shares_to_be_sold,
        aggregate_market_value=filing.aggregate_market_value,
        shares_owned_after_sale=filing.shares_owned_after_sale,
        broker_name=filing.broker_name,
        source_url=filing.source_url,
        summary=filing.summary,
    )


def _serialize_earnings_release(release: EarningsRelease) -> EarningsReleasePayload:
    return EarningsReleasePayload(
        accession_number=release.accession_number,
        form=release.form,
        filing_date=release.filing_date,
        report_date=release.report_date,
        source_url=release.source_url,
        primary_document=release.primary_document,
        exhibit_document=release.exhibit_document,
        exhibit_type=release.exhibit_type,
        reported_period_label=release.reported_period_label,
        reported_period_end=release.reported_period_end,
        revenue=release.revenue,
        operating_income=release.operating_income,
        net_income=release.net_income,
        diluted_eps=release.diluted_eps,
        revenue_guidance_low=release.revenue_guidance_low,
        revenue_guidance_high=release.revenue_guidance_high,
        eps_guidance_low=release.eps_guidance_low,
        eps_guidance_high=release.eps_guidance_high,
        share_repurchase_amount=release.share_repurchase_amount,
        dividend_per_share=release.dividend_per_share,
        highlights=list(release.highlights or []),
        parse_state=release.parse_state,
    )


def _serialize_earnings_model_point(point: EarningsModelPoint) -> EarningsModelPointPayload:
    explainability = dict(point.explainability or {})
    raw_inputs = explainability.get("inputs", [])
    inputs_payload = [
        EarningsModelInputPayload.model_validate(item)
        for item in raw_inputs
        if isinstance(item, dict)
    ]
    explainability_payload = EarningsModelExplainabilityPayload(
        formula_version=str(explainability.get("formula_version") or "sec_earnings_intel_v1"),
        period_end=str(explainability.get("period_end") or point.period_end.isoformat()),
        filing_type=str(explainability.get("filing_type") or point.filing_type),
        inputs=inputs_payload,
        component_values=dict(explainability.get("component_values") or {}),
        proxy_usage=dict(explainability.get("proxy_usage") or {}),
        segment_deltas=list(explainability.get("segment_deltas") or []),
        release_statement_coverage=dict(explainability.get("release_statement_coverage") or {}),
        quality_formula=str(explainability.get("quality_formula") or ""),
        eps_drift_formula=str(explainability.get("eps_drift_formula") or ""),
        momentum_formula=str(explainability.get("momentum_formula") or ""),
    )

    return EarningsModelPointPayload(
        period_start=point.period_start,
        period_end=point.period_end,
        filing_type=point.filing_type,
        quality_score=point.quality_score,
        quality_score_delta=point.quality_score_delta,
        eps_drift=point.eps_drift,
        earnings_momentum_drift=point.earnings_momentum_drift,
        segment_contribution_delta=point.segment_contribution_delta,
        release_statement_coverage_ratio=point.release_statement_coverage_ratio,
        fallback_ratio=point.fallback_ratio,
        stale_period_warning=point.stale_period_warning,
        quality_flags=list(point.quality_flags or []),
        source_statement_ids=[int(value) for value in list(point.source_statement_ids or [])],
        source_release_ids=[int(value) for value in list(point.source_release_ids or [])],
        explainability=explainability_payload,
    )


def _build_earnings_summary(releases: list[EarningsReleasePayload]) -> EarningsSummaryPayload:
    parsed_releases = [release for release in releases if release.parse_state == "parsed"]
    metadata_only_releases = len(releases) - len(parsed_releases)
    guidance_releases = [
        release
        for release in releases
        if any(
            value is not None
            for value in (
                release.revenue_guidance_low,
                release.revenue_guidance_high,
                release.eps_guidance_low,
                release.eps_guidance_high,
            )
        )
    ]
    buyback_releases = [release for release in releases if release.share_repurchase_amount is not None]
    dividend_releases = [release for release in releases if release.dividend_per_share is not None]
    latest = releases[0] if releases else None

    return EarningsSummaryPayload(
        total_releases=len(releases),
        parsed_releases=len(parsed_releases),
        metadata_only_releases=metadata_only_releases,
        releases_with_guidance=len(guidance_releases),
        releases_with_buybacks=len(buyback_releases),
        releases_with_dividends=len(dividend_releases),
        latest_filing_date=latest.filing_date if latest is not None else None,
        latest_report_date=latest.report_date if latest is not None else None,
        latest_reported_period_end=latest.reported_period_end if latest is not None else None,
        latest_revenue=latest.revenue if latest is not None else None,
        latest_operating_income=latest.operating_income if latest is not None else None,
        latest_net_income=latest.net_income if latest is not None else None,
        latest_diluted_eps=latest.diluted_eps if latest is not None else None,
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


def _serialize_insider_analytics(analytics) -> InsiderAnalyticsResponse:
    largest_trade_payload = None
    if analytics.largest_trade is not None:
        largest_trade_payload = LargestInsiderTradePayload(
            insider=analytics.largest_trade.insider,
            type=analytics.largest_trade.type,
            value=analytics.largest_trade.value,
            date=analytics.largest_trade.date,
        )

    return InsiderAnalyticsResponse(
        buy_value_30d=analytics.buy_value_30d,
        sell_value_30d=analytics.sell_value_30d,
        buy_sell_ratio=analytics.buy_sell_ratio,
        largest_trade=largest_trade_payload,
        insider_activity_trend=analytics.insider_activity_trend,
    )


def _serialize_ownership_analytics(analytics) -> OwnershipAnalyticsResponse:
    return OwnershipAnalyticsResponse(
        top_holders=[TopHolderPayload(fund=item.fund, shares=item.shares) for item in analytics.top_holders],
        institutional_ownership=analytics.institutional_ownership,
        ownership_concentration=analytics.ownership_concentration,
        quarterly_inflow=analytics.quarterly_inflow,
        quarterly_outflow=analytics.quarterly_outflow,
        new_positions=analytics.new_positions,
        sold_positions=analytics.sold_positions,
        reporting_date=analytics.reporting_date,
    )


def _serialize_institutional_holding(holding) -> InstitutionalHoldingPayload:
    return InstitutionalHoldingPayload(
        fund_name=holding.fund.fund_name,
        fund_cik=getattr(holding.fund, "fund_cik", None),
        fund_manager=getattr(holding.fund, "fund_manager", None),
        manager_query=getattr(holding.fund, "manager_query", None),
        universe_source=getattr(holding.fund, "universe_source", None),
        fund_strategy=get_institutional_fund_strategy(holding.fund.fund_name, getattr(holding.fund, "fund_manager", None)),
        accession_number=holding.accession_number,
        filing_form=getattr(holding, "filing_form", None),
        base_form=getattr(holding, "base_form", None),
        is_amendment=bool(getattr(holding, "is_amendment", False)),
        reporting_date=holding.reporting_date,
        filing_date=holding.filing_date,
        shares_held=holding.shares_held,
        market_value=holding.market_value,
        change_in_shares=holding.change_in_shares,
        percent_change=holding.percent_change,
        portfolio_weight=holding.portfolio_weight,
        put_call=getattr(holding, "put_call", None),
        investment_discretion=getattr(holding, "investment_discretion", None),
        voting_authority_sole=getattr(holding, "voting_authority_sole", None),
        voting_authority_shared=getattr(holding, "voting_authority_shared", None),
        voting_authority_none=getattr(holding, "voting_authority_none", None),
        source=holding.source,
    )


def _build_institutional_holdings_summary(rows: list[InstitutionalHoldingPayload]) -> InstitutionalHoldingsSummaryPayload:
    if not rows:
        return InstitutionalHoldingsSummaryPayload(total_rows=0, unique_managers=0, amended_rows=0, latest_reporting_date=None)

    unique_managers = len({
        (row.fund_cik or "", row.fund_name.strip().lower())
        for row in rows
        if row.fund_name.strip()
    })
    latest_reporting_date = max((row.reporting_date for row in rows), default=None)
    amended_rows = sum(1 for row in rows if row.is_amendment)
    return InstitutionalHoldingsSummaryPayload(
        total_rows=len(rows),
        unique_managers=unique_managers,
        amended_rows=amended_rows,
        latest_reporting_date=latest_reporting_date,
    )


def _model_result_payload(model_run: ModelRun | dict[str, Any]) -> dict[str, Any]:
    if isinstance(model_run, dict):
        result = model_run.get("result")
        return result if isinstance(result, dict) else {}
    return model_run.result if isinstance(model_run.result, dict) else {}


def _model_name(model_run: ModelRun | dict[str, Any]) -> str:
    if isinstance(model_run, dict):
        return str(model_run.get("model_name") or "")
    return str(model_run.model_name)


def _model_created_at(model_run: ModelRun | dict[str, Any]) -> datetime | None:
    if isinstance(model_run, dict):
        value = model_run.get("created_at")
        return value if isinstance(value, datetime) else None
    return model_run.created_at


def _serialize_model_payload(model_run: ModelRun | dict[str, Any]) -> ModelPayload:
    if isinstance(model_run, dict):
        model_name = _model_name(model_run)
        model_version = str(model_run.get("model_version") or "")
        created_at = _model_created_at(model_run)
        if not isinstance(created_at, datetime):
            created_at = datetime.now(timezone.utc)
        input_periods = model_run.get("input_periods")
        if not isinstance(input_periods, (dict, list)):
            input_periods = {}
        return ModelPayload(
            schema_version="2.0",
            model_name=model_name,
            model_version=model_version,
            created_at=created_at,
            input_periods=input_periods,
            result=_sanitize_model_result_for_strict_official_mode(model_name, _model_result_payload(model_run)),
        )

    return ModelPayload(
        schema_version="2.0",
        model_name=model_run.model_name,
        model_version=model_run.model_version,
        created_at=model_run.created_at,
        input_periods=model_run.input_periods,
        result=_sanitize_model_result_for_strict_official_mode(
            model_run.model_name,
            model_run.result if isinstance(model_run.result, dict) else {},
        ),
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


def _serialize_beneficial_ownership_filings(cik: str, filing_index: dict[str, FilingMetadata]) -> list[BeneficialOwnershipFilingPayload]:
    filtered = [item for item in filing_index.values() if _is_beneficial_ownership_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    return [_serialize_beneficial_ownership_filing(cik, item) for item in ordered[:MAX_FILING_TIMELINE_ITEMS]]


def _serialize_beneficial_ownership_filing(cik: str, filing: FilingMetadata) -> BeneficialOwnershipFilingPayload:
    form_display = (filing.form or "UNKNOWN").upper()
    base_form = "SC 13D" if form_display.startswith("SC 13D") else "SC 13G"
    is_amendment = form_display.endswith("/A")
    description = _normalize_optional_text(filing.primary_doc_description)
    if description:
        summary = description
    elif base_form == "SC 13D":
        summary = "Beneficial ownership filing showing a major stake disclosure or activist-style amendment."
    else:
        summary = "Beneficial ownership filing showing passive ownership disclosure or amendment."

    return BeneficialOwnershipFilingPayload(
        accession_number=filing.accession_number,
        form=form_display,
        base_form=base_form,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        is_amendment=is_amendment,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=description,
        source_url=_build_filing_document_url(cik, filing.accession_number, filing.primary_document),
        summary=summary,
        parties=[],
        previous_accession_number=None,
    )


def _serialize_cached_beneficial_ownership_report(report) -> BeneficialOwnershipFilingPayload:
    return BeneficialOwnershipFilingPayload(
        accession_number=report.accession_number,
        form=report.form,
        base_form=report.base_form,  # type: ignore[arg-type]
        filing_date=report.filing_date,
        report_date=report.report_date,
        is_amendment=report.is_amendment,
        primary_document=report.primary_document,
        primary_doc_description=report.primary_doc_description,
        source_url=report.source_url,
        summary=report.summary,
        parties=[
            BeneficialOwnershipPartyPayload(
                party_name=party.party_name,
                role=party.role,
                filer_cik=getattr(party, "filer_cik", None),
                shares_owned=getattr(party, "shares_owned", None),
                percent_owned=getattr(party, "percent_owned", None),
                event_date=getattr(party, "event_date", None),
                purpose=getattr(party, "purpose", None),
            )
            for party in report.parties
        ],
        previous_accession_number=getattr(report, "previous_accession_number", None),
        amendment_sequence=getattr(report, "amendment_sequence", None),
        amendment_chain_size=getattr(report, "amendment_chain_size", None),
    )


def _serialize_normalized_beneficial_ownership_report(report) -> BeneficialOwnershipFilingPayload:
    return BeneficialOwnershipFilingPayload(
        accession_number=report.accession_number,
        form=report.form,
        base_form=report.base_form,  # type: ignore[arg-type]
        filing_date=report.filing_date,
        report_date=report.report_date,
        is_amendment=report.is_amendment,
        primary_document=report.primary_document,
        primary_doc_description=report.primary_doc_description,
        source_url=report.source_url,
        summary=report.summary,
        parties=[
            BeneficialOwnershipPartyPayload(
                party_name=party.party_name,
                role=party.role,
                filer_cik=party.filer_cik,
                shares_owned=party.shares_owned,
                percent_owned=party.percent_owned,
                event_date=party.event_date,
                purpose=party.purpose,
            )
            for party in report.parties
        ],
        previous_accession_number=getattr(report, "previous_accession_number", None),
        amendment_sequence=getattr(report, "amendment_sequence", None),
        amendment_chain_size=getattr(report, "amendment_chain_size", None),
    )


def _build_beneficial_ownership_summary(
    filings: list[BeneficialOwnershipFilingPayload],
) -> BeneficialOwnershipSummaryPayload:
    if not filings:
        return _empty_beneficial_ownership_summary()

    _enrich_beneficial_ownership_amendment_history(filings)

    unique_people = {
        party.party_name.strip().lower()
        for filing in filings
        for party in filing.parties
        if party.party_name.strip()
    }
    max_percent = max(
        (party.percent_owned for filing in filings for party in filing.parties if party.percent_owned is not None),
        default=None,
    )
    latest_filing_date = max(
        (filing.filing_date or filing.report_date for filing in filings if filing.filing_date or filing.report_date),
        default=None,
    )
    latest_event_date = max(
        (party.event_date for filing in filings for party in filing.parties if party.event_date is not None),
        default=None,
    )
    amendments = sum(1 for filing in filings if filing.is_amendment)
    chains_with_amendments = len(
        {
            key
            for key, chain in _group_beneficial_ownership_chains(filings).items()
            if len(chain) > 1 and any(item.is_amendment for item in chain)
        }
    )

    amendments_with_delta = sum(
        1
        for filing in filings
        if filing.is_amendment and filing.percent_change_pp is not None
    )
    ownership_increase_events = sum(1 for filing in filings if filing.change_direction == "increase")
    ownership_decrease_events = sum(1 for filing in filings if filing.change_direction == "decrease")
    ownership_unchanged_events = sum(1 for filing in filings if filing.change_direction == "unchanged")

    positive_deltas = [
        filing.percent_change_pp
        for filing in filings
        if filing.percent_change_pp is not None and filing.percent_change_pp > 0
    ]
    negative_deltas = [
        filing.percent_change_pp
        for filing in filings
        if filing.percent_change_pp is not None and filing.percent_change_pp < 0
    ]

    return BeneficialOwnershipSummaryPayload(
        total_filings=len(filings),
        initial_filings=len(filings) - amendments,
        amendments=amendments,
        unique_reporting_persons=len(unique_people),
        latest_filing_date=latest_filing_date,
        latest_event_date=latest_event_date,
        max_reported_percent=max_percent,
        chains_with_amendments=chains_with_amendments,
        amendments_with_delta=amendments_with_delta,
        ownership_increase_events=ownership_increase_events,
        ownership_decrease_events=ownership_decrease_events,
        ownership_unchanged_events=ownership_unchanged_events,
        largest_increase_pp=max(positive_deltas, default=None),
        largest_decrease_pp=min(negative_deltas, default=None),
    )


def _empty_beneficial_ownership_summary() -> BeneficialOwnershipSummaryPayload:
    return BeneficialOwnershipSummaryPayload(
        total_filings=0,
        initial_filings=0,
        amendments=0,
        unique_reporting_persons=0,
        latest_filing_date=None,
        latest_event_date=None,
        max_reported_percent=None,
        chains_with_amendments=0,
        amendments_with_delta=0,
        ownership_increase_events=0,
        ownership_decrease_events=0,
        ownership_unchanged_events=0,
        largest_increase_pp=None,
        largest_decrease_pp=None,
    )


def _group_beneficial_ownership_chains(
    filings: list[BeneficialOwnershipFilingPayload],
) -> dict[str, list[BeneficialOwnershipFilingPayload]]:
    chains: dict[str, list[BeneficialOwnershipFilingPayload]] = {}
    for filing in filings:
        key = _beneficial_ownership_chain_key(filing)
        if key is None:
            continue
        chains.setdefault(key, []).append(filing)

    for chain in chains.values():
        chain.sort(
            key=lambda item: (
                item.filing_date or item.report_date or DateType.min,
                item.accession_number or "",
            )
        )
    return chains


def _beneficial_ownership_chain_key(filing: BeneficialOwnershipFilingPayload) -> str | None:
    for party in filing.parties:
        name = (party.party_name or "").strip().lower()
        if name:
            return f"{filing.base_form}:name:{name}"
        filer_cik = (party.filer_cik or "").strip()
        if filer_cik:
            return f"{filing.base_form}:cik:{filer_cik}"

    accession = (filing.accession_number or "").strip()
    document_token = _beneficial_ownership_document_token(filing.primary_document)
    if document_token:
        return f"{filing.base_form}:doc:{document_token}"
    if accession:
        return f"{filing.base_form}:accession:{accession}"
    return None


def _beneficial_ownership_document_token(primary_document: str | None) -> str | None:
    if not primary_document:
        return None
    stem, _ = os.path.splitext(primary_document)
    normalized = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if len(normalized) < 4:
        return None
    return normalized[:96]


def _beneficial_ownership_primary_percent(filing: BeneficialOwnershipFilingPayload) -> float | None:
    percents = [party.percent_owned for party in filing.parties if party.percent_owned is not None]
    if not percents:
        return None
    return max(float(percent) for percent in percents)


def _enrich_beneficial_ownership_amendment_history(
    filings: list[BeneficialOwnershipFilingPayload],
) -> list[BeneficialOwnershipFilingPayload]:
    if not filings:
        return filings

    filing_by_accession = {
        filing.accession_number: filing
        for filing in filings
        if filing.accession_number
    }

    for filing in filings:
        previous_accession = (filing.previous_accession_number or "").strip() or None
        if not previous_accession:
            continue
        previous_filing = filing_by_accession.get(previous_accession)
        if previous_filing is None:
            continue

        filing.previous_filing_date = previous_filing.filing_date or previous_filing.report_date
        previous_percent = _beneficial_ownership_primary_percent(previous_filing)
        current_percent = _beneficial_ownership_primary_percent(filing)
        filing.previous_percent_owned = previous_percent

        if previous_percent is None or current_percent is None:
            filing.change_direction = filing.change_direction or "unknown"
            continue

        percent_change = current_percent - previous_percent
        filing.percent_change_pp = percent_change

        if percent_change > 0:
            filing.change_direction = "increase"
        elif percent_change < 0:
            filing.change_direction = "decrease"
        else:
            filing.change_direction = "unchanged"

    for chain in _group_beneficial_ownership_chains(filings).values():
        chain_size = len(chain)
        for index, filing in enumerate(chain):
            if filing.amendment_sequence is None:
                filing.amendment_sequence = index + 1
            if filing.amendment_chain_size is None:
                filing.amendment_chain_size = chain_size

            if filing.previous_accession_number:
                continue

            if index == 0:
                filing.change_direction = filing.change_direction or ("unknown" if filing.is_amendment else "new")
                continue

            previous_filing = chain[index - 1]
            filing.previous_accession_number = previous_filing.accession_number
            filing.previous_filing_date = previous_filing.filing_date or previous_filing.report_date
            previous_percent = _beneficial_ownership_primary_percent(previous_filing)
            current_percent = _beneficial_ownership_primary_percent(filing)
            filing.previous_percent_owned = previous_percent

            if previous_percent is None or current_percent is None:
                filing.change_direction = filing.change_direction or "unknown"
                continue

            percent_change = current_percent - previous_percent
            filing.percent_change_pp = percent_change

            if percent_change > 0:
                filing.change_direction = "increase"
            elif percent_change < 0:
                filing.change_direction = "decrease"
            else:
                filing.change_direction = "unchanged"

    return filings


def _serialize_governance_filings(
    cik: str,
    filing_index: dict[str, FilingMetadata],
    client: EdgarClient | None = None,
) -> list[GovernanceFilingPayload]:
    filtered = [item for item in filing_index.values() if _is_governance_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    rows: list[GovernanceFilingPayload] = []
    for index, filing in enumerate(ordered[:MAX_FILING_TIMELINE_ITEMS]):
        signals = ProxyFilingSignals()
        if client is not None and filing.primary_document and index < 12:
            try:
                _, payload = client.get_filing_document_text(cik, filing.accession_number, filing.primary_document)
                signals = parse_proxy_filing_signals(payload)
            except Exception:
                signals = ProxyFilingSignals()
        rows.append(_serialize_governance_filing(cik, filing, signals=signals))
    return rows


def _load_live_governance_filings(cik: str) -> list[GovernanceFilingPayload]:
    client = EdgarClient()
    try:
        submissions = client.get_submissions(cik)
        filing_index = client.build_filing_index(submissions)
        return _serialize_governance_filings(cik, filing_index, client=client)
    except Exception:
        logging.getLogger(__name__).exception("Unable to load live governance filings for CIK %s", cik)
        return []
    finally:
        client.close()


def _load_live_exec_comp_rows(cik: str) -> list[ExecCompRowPayload]:
    client = EdgarClient()
    try:
        submissions = client.get_submissions(cik)
        filing_index = client.build_filing_index(submissions)
        filtered = [item for item in filing_index.values() if _is_governance_form(item.form)]
        ordered = sorted(
            filtered,
            key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
            reverse=True,
        )
        rows: list[ExecCompRowPayload] = []
        seen_keys: set[tuple[str, int | None]] = set()
        for filing in ordered[:12]:
            if not filing.primary_document:
                continue
            try:
                _source, payload = client.get_filing_document_text(cik, filing.accession_number, filing.primary_document)
                signals = parse_proxy_filing_signals(payload)
            except Exception:
                continue

            for row in signals.named_exec_rows:
                key = (row.executive_name.strip().lower(), row.fiscal_year)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(_serialize_exec_comp_row_from_signals(row))

        rows.sort(key=lambda item: (item.fiscal_year or 0, item.total_compensation or 0), reverse=True)
        return rows
    except Exception:
        logging.getLogger(__name__).exception("Unable to load live executive compensation rows for CIK %s", cik)
        return []
    finally:
        client.close()


def _serialize_governance_filing(
    cik: str,
    filing: FilingMetadata,
    *,
    signals: ProxyFilingSignals | None = None,
) -> GovernanceFilingPayload:
    resolved_signals = signals or ProxyFilingSignals()
    form_display = (filing.form or "UNKNOWN").upper()
    description = _normalize_optional_text(filing.primary_doc_description)
    if description:
        summary = description
    elif form_display == "DEF 14A":
        summary = _governance_summary_line(form_display, resolved_signals)
    else:
        summary = _governance_summary_line(form_display, resolved_signals)

    return GovernanceFilingPayload(
        accession_number=filing.accession_number,
        form=form_display,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=description,
        source_url=_build_filing_document_url(cik, filing.accession_number, filing.primary_document),
        summary=summary,
        meeting_date=resolved_signals.meeting_date,
        executive_comp_table_detected=resolved_signals.executive_comp_table_detected,
        vote_item_count=resolved_signals.vote_item_count,
        board_nominee_count=resolved_signals.board_nominee_count,
        key_amounts=list(resolved_signals.key_amounts),
        vote_outcomes=[
            GovernanceVoteOutcomePayload(
                proposal_number=item.proposal_number,
                title=item.title,
                for_votes=item.for_votes,
                against_votes=item.against_votes,
                abstain_votes=item.abstain_votes,
                broker_non_votes=item.broker_non_votes,
            )
            for item in resolved_signals.vote_outcomes
        ],
    )


def _governance_summary_line(form_display: str, signals: ProxyFilingSignals) -> str:
    segments: list[str] = []
    if form_display == "DEF 14A":
        segments.append("Definitive proxy statement")
    else:
        segments.append("Additional proxy material")

    if signals.meeting_date is not None:
        segments.append(f"meeting date {signals.meeting_date.isoformat()}")
    if signals.vote_item_count > 0:
        segments.append(f"{signals.vote_item_count} proposal items detected")
    if signals.executive_comp_table_detected:
        segments.append("executive compensation table detected")

    return "; ".join(segments) + "."


def _serialize_exec_comp_row(db_row: ExecutiveCompensation) -> ExecCompRowPayload:
    """Serialize a cached ExecutiveCompensation ORM row to the API payload."""
    return ExecCompRowPayload(
        executive_name=db_row.executive_name,
        executive_title=db_row.executive_title,
        fiscal_year=db_row.fiscal_year,
        salary=db_row.salary,
        bonus=db_row.bonus,
        stock_awards=db_row.stock_awards,
        option_awards=db_row.option_awards,
        non_equity_incentive=db_row.non_equity_incentive,
        other_compensation=db_row.other_compensation,
        total_compensation=db_row.total_compensation,
    )


def _serialize_exec_comp_row_from_signals(row: ExecCompRow) -> ExecCompRowPayload:
    """Serialize an ExecCompRow dataclass (live-parsed) to the API payload."""
    return ExecCompRowPayload(
        executive_name=row.executive_name,
        executive_title=row.executive_title,
        fiscal_year=row.fiscal_year,
        salary=row.salary,
        bonus=row.bonus,
        stock_awards=row.stock_awards,
        option_awards=row.option_awards,
        non_equity_incentive=row.non_equity_incentive,
        other_compensation=row.other_compensation,
        total_compensation=row.total_compensation,
    )


def _build_governance_summary(filings: list[GovernanceFilingPayload]) -> GovernanceSummaryPayload:
    if not filings:
        return _empty_governance_summary()

    definitive = sum(1 for filing in filings if filing.form == "DEF 14A")
    filings_with_meeting = sum(1 for filing in filings if filing.meeting_date is not None)
    filings_with_comp = sum(1 for filing in filings if filing.executive_comp_table_detected)
    filings_with_votes = sum(1 for filing in filings if filing.vote_item_count > 0)
    latest_meeting_date = max((filing.meeting_date for filing in filings if filing.meeting_date is not None), default=None)
    max_vote_items = max((filing.vote_item_count for filing in filings), default=0)

    return GovernanceSummaryPayload(
        total_filings=len(filings),
        definitive_proxies=definitive,
        supplemental_proxies=len(filings) - definitive,
        filings_with_meeting_date=filings_with_meeting,
        filings_with_exec_comp=filings_with_comp,
        filings_with_vote_items=filings_with_votes,
        latest_meeting_date=latest_meeting_date,
        max_vote_item_count=max_vote_items,
    )


def _empty_governance_summary() -> GovernanceSummaryPayload:
    return GovernanceSummaryPayload(
        total_filings=0,
        definitive_proxies=0,
        supplemental_proxies=0,
        filings_with_meeting_date=0,
        filings_with_exec_comp=0,
        filings_with_vote_items=0,
        latest_meeting_date=None,
        max_vote_item_count=0,
    )


def _serialize_filing_events(cik: str, filing_index: dict[str, FilingMetadata]) -> list[FilingEventPayload]:
    filtered = [item for item in filing_index.values() if _is_event_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    return [_serialize_filing_event(cik, item) for item in ordered[:MAX_FILING_TIMELINE_ITEMS]]


def _serialize_filing_event(cik: str, filing: FilingMetadata) -> FilingEventPayload:
    items = _normalize_optional_text(filing.items)
    description = _normalize_optional_text(filing.primary_doc_description)
    category = _classify_filing_event(items, description)
    if description:
        summary = description
    elif items:
        summary = f"Current report covering Item(s) {items}."
    else:
        summary = "Current report with event-driven disclosure."

    return FilingEventPayload(
        accession_number=filing.accession_number,
        form=(filing.form or "UNKNOWN").upper(),
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        items=items,
        item_code=None,
        category=category,
        primary_document=_normalize_optional_text(filing.primary_document),
        primary_doc_description=description,
        source_url=_build_filing_document_url(cik, filing.accession_number, filing.primary_document),
        summary=summary,
        key_amounts=[],
        exhibit_references=[],
    )


def _serialize_cached_filing_event(event) -> FilingEventPayload:
    return FilingEventPayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        items=event.items,
        item_code=event.item_code,
        category=event.category,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        key_amounts=[float(value) for value in (event.key_amounts or [])],
        exhibit_references=[str(value) for value in (getattr(event, "exhibit_references", []) or [])],
    )


def _serialize_normalized_filing_event(event) -> FilingEventPayload:
    return FilingEventPayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        items=event.items,
        item_code=event.item_code,
        category=event.category,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        key_amounts=list(event.key_amounts),
        exhibit_references=list(event.exhibit_references),
    )


def _build_filing_events_summary(events: list[FilingEventPayload]) -> FilingEventsSummaryPayload:
    if not events:
        return _empty_filing_events_summary()

    categories: dict[str, int] = {}
    for event in events:
        categories[event.category] = categories.get(event.category, 0) + 1

    latest_event_date = max(
        (event.filing_date or event.report_date for event in events if event.filing_date or event.report_date),
        default=None,
    )
    max_key_amount = max(
        (amount for event in events for amount in event.key_amounts),
        default=None,
    )
    unique_accessions = len({event.accession_number for event in events if event.accession_number})

    return FilingEventsSummaryPayload(
        total_events=len(events),
        unique_accessions=unique_accessions,
        categories=categories,
        latest_event_date=latest_event_date,
        max_key_amount=max_key_amount,
    )


def _empty_filing_events_summary() -> FilingEventsSummaryPayload:
    return FilingEventsSummaryPayload(
        total_events=0,
        unique_accessions=0,
        categories={},
        latest_event_date=None,
        max_key_amount=None,
    )


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


def _filing_timeline_description(filing: FilingPayload) -> str:
    explicit = _normalize_optional_text(filing.primary_doc_description)
    if explicit:
        return explicit

    items = _normalize_optional_text(filing.items)
    if filing.form == "8-K":
        if items:
            return f"Current report (Items {items})"
        return "Current report"
    if filing.form == "10-K":
        return "Annual report"
    if filing.form == "10-Q":
        return "Quarterly report"
    if items:
        return f"SEC filing (Items {items})"
    return "SEC filing"


def _serialize_search_filing_hit(hit: dict[str, Any]) -> FilingSearchResultPayload | None:
    source = hit.get("_source") if isinstance(hit, dict) else None
    if not isinstance(source, dict):
        return None

    form = str(source.get("form") or "").strip().upper()
    if not form:
        return None

    display_names = source.get("display_names")
    company = ""
    if isinstance(display_names, list) and display_names:
        company = str(display_names[0] or "").strip()
    if not company:
        company = str(source.get("entityName") or source.get("companyName") or "").strip()
    if not company:
        company = "Unknown"

    filing_date = _parse_date(source.get("filed") or source.get("filedAt") or source.get("filingDate"))
    filing_link = _resolve_search_filing_link(source)
    if not filing_link:
        return None

    return FilingSearchResultPayload(
        form=form,
        company=company,
        filing_date=filing_date,
        filing_link=filing_link,
    )


def _resolve_search_filing_link(source: dict[str, Any]) -> str | None:
    for key in ("link", "url", "filingHref", "filingLink", "html_url"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    adsh = str(source.get("adsh") or source.get("accessionNumber") or "").strip()
    ciks = source.get("ciks")
    cik = ""
    if isinstance(ciks, list) and ciks:
        cik = str(ciks[0] or "").strip()
    if not cik:
        cik = str(source.get("cik") or "").strip()

    accession = adsh.replace("-", "")
    if cik.isdigit() and accession.isdigit() and adsh:
        numeric_cik = str(int(cik))
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession}/"

    return None


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


def _is_beneficial_ownership_form(form: str | None) -> bool:
    normalized = (form or "").upper()
    return normalized in {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


def _is_registration_form(form: str | None) -> bool:
    return (form or "").upper() in REGISTRATION_FORMS


def _serialize_capital_raise_filings(
    cik: str, filing_index: dict[str, FilingMetadata]
) -> list[CapitalRaisePayload]:
    filtered = [item for item in filing_index.values() if _is_registration_form(item.form)]
    ordered = sorted(
        filtered,
        key=lambda item: (item.filing_date or DateType.min, item.report_date or DateType.min, item.accession_number),
        reverse=True,
    )
    results: list[CapitalRaisePayload] = []
    for item in ordered[:MAX_FILING_TIMELINE_ITEMS]:
        form_display = (item.form or "UNKNOWN").upper()
        description = _normalize_optional_text(item.primary_doc_description)
        summary = description or _REGISTRATION_FORM_SUMMARIES.get(form_display, "Registration or prospectus filing.")
        results.append(
            CapitalRaisePayload(
                accession_number=item.accession_number,
                form=form_display,
                filing_date=item.filing_date,
                report_date=item.report_date,
                primary_document=_normalize_optional_text(item.primary_document),
                primary_doc_description=description,
                source_url=_build_filing_document_url(cik, item.accession_number, item.primary_document),
                summary=summary,
                event_type=None,
                security_type=None,
                offering_amount=None,
                shelf_size=None,
                is_late_filer=False,
            )
        )
    return results


def _serialize_cached_capital_markets_event(event) -> CapitalRaisePayload:
    return CapitalRaisePayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        event_type=event.event_type,
        security_type=event.security_type,
        offering_amount=event.offering_amount,
        shelf_size=event.shelf_size,
        is_late_filer=event.is_late_filer,
    )


def _serialize_normalized_capital_markets_event(event) -> CapitalRaisePayload:
    return CapitalRaisePayload(
        accession_number=event.accession_number,
        form=event.form,
        filing_date=event.filing_date,
        report_date=event.report_date,
        primary_document=event.primary_document,
        primary_doc_description=event.primary_doc_description,
        source_url=event.source_url,
        summary=event.summary,
        event_type=event.event_type,
        security_type=event.security_type,
        offering_amount=event.offering_amount,
        shelf_size=event.shelf_size,
        is_late_filer=event.is_late_filer,
    )


def _build_capital_markets_summary(filings: list[CapitalRaisePayload]) -> CapitalMarketsSummaryPayload:
    if not filings:
        return _empty_capital_markets_summary()

    latest_filing_date = max(
        (filing.filing_date or filing.report_date for filing in filings if filing.filing_date or filing.report_date),
        default=None,
    )
    max_offering_amount = max((filing.offering_amount for filing in filings if filing.offering_amount is not None), default=None)

    return CapitalMarketsSummaryPayload(
        total_filings=len(filings),
        late_filer_notices=sum(1 for filing in filings if filing.is_late_filer),
        registration_filings=sum(1 for filing in filings if filing.event_type == "Registration"),
        prospectus_filings=sum(1 for filing in filings if filing.event_type == "Prospectus"),
        latest_filing_date=latest_filing_date,
        max_offering_amount=max_offering_amount,
    )


def _empty_capital_markets_summary() -> CapitalMarketsSummaryPayload:
    return CapitalMarketsSummaryPayload(
        total_filings=0,
        late_filer_notices=0,
        registration_filings=0,
        prospectus_filings=0,
        latest_filing_date=None,
        max_offering_amount=None,
    )


def _build_company_activity_overview_response(
    *,
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session,
) -> CompanyActivityOverviewResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyActivityOverviewResponse(
            company=None,
            entries=[],
            alerts=[],
            summary=AlertsSummaryPayload(total=0, high=0, medium=0, low=0),
            market_context_status=get_cached_market_context_status(),
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            error=None,
            **_empty_provenance_contract("company_missing"),
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)
    activity = _load_company_activity_data(session, snapshot)
    entries = _build_activity_feed_entries(
        filings=activity["filings"],
        filing_events=activity["filing_events"],
        governance_filings=activity["governance_filings"],
        beneficial_filings=activity["beneficial_filings"],
        insider_trades=activity["insider_trades"],
        form144_filings=activity["form144_filings"],
        institutional_holdings=activity["institutional_holdings"],
    )
    alerts = _build_activity_alerts(
        beneficial_filings=activity["beneficial_filings"],
        capital_filings=activity["capital_filings"],
        insider_trades=activity["insider_trades"],
        institutional_holdings=activity["institutional_holdings"],
    )
    market_context_status = get_cached_market_context_status()
    return CompanyActivityOverviewResponse(
        company=_serialize_company(snapshot),
        entries=entries,
        alerts=alerts,
        summary=_build_alerts_summary(alerts),
        market_context_status=market_context_status,
        refresh=refresh,
        error=None,
        **_activity_overview_provenance_contract(
            entries,
            market_context_status=market_context_status,
            last_refreshed_at=snapshot.last_checked,
            refresh=refresh,
        ),
    )


def _build_alerts_summary(alerts: list[AlertPayload]) -> AlertsSummaryPayload:
    return AlertsSummaryPayload(
        total=len(alerts),
        high=sum(1 for alert in alerts if alert.level == "high"),
        medium=sum(1 for alert in alerts if alert.level == "medium"),
        low=sum(1 for alert in alerts if alert.level == "low"),
    )


def _load_company_activity_data(session: Session, snapshot: CompanyCacheSnapshot, *, compact: bool = False) -> dict[str, Any]:
    cached_filings = _load_filings_from_cache(snapshot.company.cik)
    fallback_filings = _serialize_cached_statement_filings(get_company_financials(session, snapshot.company.id))
    filings = cached_filings if cached_filings is not None else fallback_filings
    if compact:
        filings = filings[:24]

    filing_events = [
        _serialize_cached_filing_event(event)
        for event in get_company_filing_events(session, snapshot.company.id, limit=80 if compact else 300)
    ]
    beneficial_filings = [
        _serialize_cached_beneficial_ownership_report(report)
        for report in get_company_beneficial_ownership_reports(session, snapshot.company.id, limit=80 if compact else 200)
    ]
    insider_trades = [_serialize_insider_trade(trade) for trade in get_company_insider_trades(session, snapshot.company.id, limit=80 if compact else 200)]
    form144_filings = [_serialize_form144_filing(filing) for filing in get_company_form144_filings(session, snapshot.company.id, limit=80 if compact else 200)]
    institutional_holdings = [
        _serialize_institutional_holding(holding)
        for holding in get_company_institutional_holdings(session, snapshot.company.id, limit=80 if compact else 200)
    ]
    capital_filings = [
        _serialize_cached_capital_markets_event(event)
        for event in get_company_capital_markets_events(session, snapshot.company.id, limit=80 if compact else 200)
    ]
    governance_filings = [
        _serialize_cached_proxy_statement(statement)
        for statement in get_company_proxy_statements(session, snapshot.company.id, limit=40 if compact else 60)
    ]

    return {
        "filings": filings,
        "filing_events": filing_events,
        "governance_filings": governance_filings,
        "beneficial_filings": beneficial_filings,
        "insider_trades": insider_trades,
        "form144_filings": form144_filings,
        "institutional_holdings": institutional_holdings,
        "capital_filings": capital_filings,
    }


def _serialize_cached_proxy_statement(statement: ProxyStatement) -> GovernanceFilingPayload:
    return GovernanceFilingPayload(
        accession_number=statement.accession_number,
        form=statement.form,
        filing_date=statement.filing_date,
        report_date=statement.report_date,
        primary_document=statement.primary_document,
        primary_doc_description=None,
        source_url=statement.source_url,
        summary=_governance_summary_line(statement.form, _proxy_statement_signals(statement)),
        meeting_date=statement.meeting_date,
        executive_comp_table_detected=bool(statement.executive_comp_table_detected),
        vote_item_count=statement.vote_item_count,
        board_nominee_count=statement.board_nominee_count,
        key_amounts=[],
        vote_outcomes=[
            GovernanceVoteOutcomePayload(
                proposal_number=item.proposal_number,
                title=item.title,
                for_votes=item.for_votes,
                against_votes=item.against_votes,
                abstain_votes=item.abstain_votes,
                broker_non_votes=item.broker_non_votes,
            )
            for item in statement.vote_results
        ],
    )


def _proxy_statement_signals(statement: ProxyStatement) -> ProxyFilingSignals:
    return ProxyFilingSignals(
        meeting_date=statement.meeting_date,
        executive_comp_table_detected=bool(statement.executive_comp_table_detected),
        vote_item_count=statement.vote_item_count,
        board_nominee_count=statement.board_nominee_count,
        key_amounts=(),
        vote_outcomes=(),
        named_exec_rows=(),
    )


def _build_activity_feed_entries(
    *,
    filings: list[FilingPayload],
    filing_events: list[FilingEventPayload],
    governance_filings: list[GovernanceFilingPayload],
    beneficial_filings: list[BeneficialOwnershipFilingPayload],
    insider_trades: list[InsiderTradePayload],
    form144_filings: list[Form144FilingPayload],
    institutional_holdings: list[InstitutionalHoldingPayload],
) -> list[ActivityFeedEntryPayload]:
    entries: list[ActivityFeedEntryPayload] = []

    for filing in filings[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"filing-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.report_date,
                type="filing",
                badge=filing.form,
                title=_filing_timeline_description(filing),
                detail=filing.accession_number or "SEC filing",
                href=filing.source_url,
            )
        )

    for event in filing_events:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"event-{event.accession_number or event.source_url}-{event.item_code or 'na'}",
                date=event.filing_date or event.report_date,
                type="event",
                badge=event.category,
                title=event.summary,
                detail=f"{event.form}{f' - Items {event.items}' if event.items else ''}",
                href=event.source_url,
            )
        )

    for filing in governance_filings:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"governance-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.report_date,
                type="governance",
                badge=filing.form,
                title=filing.summary,
                detail=filing.accession_number or "Proxy filing",
                href=filing.source_url,
            )
        )

    for filing in beneficial_filings:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"ownership-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.report_date,
                type="ownership-change",
                badge=filing.form,
                title=filing.summary,
                detail="Amendment" if filing.is_amendment else "Initial stake disclosure",
                href=filing.source_url,
            )
        )

    for trade in insider_trades[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"insider-{trade.accession_number or f'{trade.name}-{trade.date}'}",
                date=trade.filing_date or trade.date,
                type="insider",
                badge=trade.action,
                title=f"{trade.name} {trade.action.lower()} activity",
                detail=f"{trade.role or 'Insider'}{f' - ${trade.value:,.0f}' if trade.value is not None else ''}",
                href=trade.source,
            )
        )

    for filing in form144_filings[:40]:
        title = "Form 144 planned sale filing"
        if filing.filer_name:
            title = f"{filing.filer_name} filed Form 144 planned sale"
        entries.append(
            ActivityFeedEntryPayload(
                id=f"form144-{filing.accession_number or filing.source_url}",
                date=filing.filing_date or filing.planned_sale_date or filing.report_date,
                type="form144",
                badge="144",
                title=title,
                detail=_build_form144_feed_detail(filing),
                href=filing.source_url,
            )
        )

    for holding in institutional_holdings[:40]:
        entries.append(
            ActivityFeedEntryPayload(
                id=f"institutional-{holding.accession_number or f'{holding.fund_name}-{holding.reporting_date}'}",
                date=holding.filing_date or holding.reporting_date,
                type="institutional",
                badge=holding.base_form or holding.filing_form or "13F",
                title=f"{holding.fund_name} updated holdings",
                detail=(
                    f"{holding.shares_held:,.0f} shares"
                    if holding.shares_held is not None
                    else "Tracked 13F position"
                ),
                href=holding.source,
            )
        )

    entries.sort(
        key=lambda item: (
            item.date or DateType.min,
            item.id,
        ),
        reverse=True,
    )
    return entries[:220]


def _build_form144_feed_detail(filing: Form144FilingPayload) -> str:
    detail_parts: list[str] = []

    if filing.planned_sale_date is not None:
        detail_parts.append(f"Planned sale {filing.planned_sale_date.isoformat()}")
    if filing.filer_name:
        detail_parts.append(filing.filer_name)
    if filing.shares_to_be_sold is not None:
        detail_parts.append(f"{filing.shares_to_be_sold:,.0f} shares")
    if filing.aggregate_market_value is not None:
        detail_parts.append(f"${filing.aggregate_market_value:,.0f}")

    if detail_parts:
        return " | ".join(detail_parts)
    if filing.summary:
        return filing.summary
    return "Planned insider sale filing"


def _build_activity_alerts(
    *,
    beneficial_filings: list[BeneficialOwnershipFilingPayload],
    capital_filings: list[CapitalRaisePayload],
    insider_trades: list[InsiderTradePayload],
    institutional_holdings: list[InstitutionalHoldingPayload],
) -> list[AlertPayload]:
    alerts: list[AlertPayload] = []

    for filing in beneficial_filings[:30]:
        max_percent = max((party.percent_owned for party in filing.parties if party.percent_owned is not None), default=None)
        if max_percent is not None and max_percent >= 5:
            alerts.append(
                AlertPayload(
                    id=f"alert-activist-{filing.accession_number or filing.source_url}",
                    level="high" if max_percent >= 10 else "medium",
                    title="Large beneficial ownership stake reported",
                    detail=f"{filing.form} reported up to {max_percent:.2f}% beneficial ownership.",
                    source="beneficial-ownership",
                    date=filing.filing_date or filing.report_date,
                    href=filing.source_url,
                )
            )

    for filing in capital_filings[:40]:
        if filing.is_late_filer:
            alerts.append(
                AlertPayload(
                    id=f"alert-late-{filing.accession_number or filing.source_url}",
                    level="high",
                    title="Late filer notice",
                    detail=f"{filing.form} indicates a delayed periodic filing.",
                    source="capital-markets",
                    date=filing.filing_date or filing.report_date,
                    href=filing.source_url,
                )
            )
            continue

        if filing.event_type in {"Registration", "Prospectus"}:
            size_hint = filing.offering_amount or filing.shelf_size
            detail = "New financing-related filing detected."
            if size_hint is not None:
                detail = f"Potential financing of approximately ${size_hint:,.0f}."
            alerts.append(
                AlertPayload(
                    id=f"alert-financing-{filing.accession_number or filing.source_url}",
                    level="medium",
                    title="Potential dilution or financing activity",
                    detail=detail,
                    source="capital-markets",
                    date=filing.filing_date or filing.report_date,
                    href=filing.source_url,
                )
            )

    recent_buys = sum(1 for trade in insider_trades[:120] if (trade.action or "").upper() == "BUY")
    recent_sells = sum(1 for trade in insider_trades[:120] if (trade.action or "").upper() == "SELL")
    if recent_buys == 0 and recent_sells > 0:
        alerts.append(
            AlertPayload(
                id="alert-insider-buy-drought",
                level="medium",
                title="Insider buying drought",
                detail="Recent filings show sells without offsetting insider buys.",
                source="insider-trades",
                date=max((trade.filing_date or trade.date for trade in insider_trades if trade.filing_date or trade.date), default=None),
                href=None,
            )
        )

    for holding in institutional_holdings[:80]:
        if holding.percent_change is not None and holding.percent_change <= -20:
            alerts.append(
                AlertPayload(
                    id=f"alert-inst-exit-{holding.accession_number or f'{holding.fund_name}-{holding.reporting_date}'}",
                    level="medium",
                    title="Large institutional position reduction",
                    detail=f"{holding.fund_name} reported a {holding.percent_change:.2f}% position change.",
                    source="institutional-holdings",
                    date=holding.filing_date or holding.reporting_date,
                    href=holding.source,
                )
            )

    alerts.sort(
        key=lambda item: (
            0 if item.level == "high" else 1 if item.level == "medium" else 2,
            -(item.date.toordinal() if item.date else 0),
            item.id,
        )
    )
    return alerts[:30]


def _normalize_watchlist_tickers(raw_tickers: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_ticker in raw_tickers:
        ticker = _normalize_ticker(raw_ticker or "")
        if not ticker:
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(ticker)
    return normalized


def _build_watchlist_summary_item(
    session: Session,
    background_tasks: BackgroundTasks,
    ticker: str,
    *,
    snapshot: CompanyCacheSnapshot | None = None,
    coverage_counts: dict[str, int] | None = None,
) -> WatchlistSummaryItemPayload:
    snapshot = snapshot or _resolve_cached_company_snapshot(session, ticker)
    if snapshot is None:
        return _build_missing_watchlist_summary_item(background_tasks, ticker)

    refresh = _refresh_for_snapshot(background_tasks, snapshot)

    financial_periods = int((coverage_counts or {}).get("financial_periods", 0))
    price_points = int((coverage_counts or {}).get("price_points", 0))

    alerts: list[AlertPayload] = []
    entries: list[ActivityFeedEntryPayload] = []
    try:
        activity = _load_company_activity_data(session, snapshot, compact=True)
        alerts = _build_activity_alerts(
            beneficial_filings=activity["beneficial_filings"],
            capital_filings=activity["capital_filings"],
            insider_trades=activity["insider_trades"],
            institutional_holdings=activity["institutional_holdings"],
        )
        entries = _build_activity_feed_entries(
            filings=activity["filings"],
            filing_events=activity["filing_events"],
            governance_filings=activity["governance_filings"],
            beneficial_filings=activity["beneficial_filings"],
            insider_trades=activity["insider_trades"],
            form144_filings=activity["form144_filings"],
            institutional_holdings=activity["institutional_holdings"],
        )
    except Exception:
        logging.getLogger(__name__).exception("Unable to load watchlist activity summary for '%s'", snapshot.company.ticker)

    alert_summary = _build_alerts_summary(alerts)

    latest_alert = alerts[0] if alerts else None
    latest_activity = entries[0] if entries else None

    models: dict[str, ModelRun] = {}
    latest_price = None
    try:
        models = {
            model.model_name.lower(): model
            for model in get_company_models(
                session,
                snapshot.company.id,
                model_names=["dcf", "roic", "reverse_dcf", "capital_allocation", "ratios"],
            )
        }
        latest_price_series = _visible_price_history(session, snapshot.company.id)
        latest_price = latest_price_series[-1].close if latest_price_series else None
    except Exception:
        logging.getLogger(__name__).exception("Unable to load watchlist model metrics for '%s'", snapshot.company.ticker)

    dcf_result = _sanitize_model_result_for_strict_official_mode(
        "dcf",
        models.get("dcf").result if models.get("dcf") is not None and isinstance(models.get("dcf").result, dict) else {},
    )
    roic_result = _sanitize_model_result_for_strict_official_mode(
        "roic",
        models.get("roic").result if models.get("roic") is not None and isinstance(models.get("roic").result, dict) else {},
    )
    reverse_result = _sanitize_model_result_for_strict_official_mode(
        "reverse_dcf",
        models.get("reverse_dcf").result if models.get("reverse_dcf") is not None and isinstance(models.get("reverse_dcf").result, dict) else {},
    )
    capital_result = _sanitize_model_result_for_strict_official_mode(
        "capital_allocation",
        models.get("capital_allocation").result if models.get("capital_allocation") is not None and isinstance(models.get("capital_allocation").result, dict) else {},
    )
    ratios_result = _sanitize_model_result_for_strict_official_mode(
        "ratios",
        models.get("ratios").result if models.get("ratios") is not None and isinstance(models.get("ratios").result, dict) else {},
    )
    ratios_values = ratios_result.get("values") if isinstance(ratios_result.get("values"), dict) else {}
    fair_value_per_share = _coerce_number(dcf_result.get("fair_value_per_share"), None)
    dcf_status = str(dcf_result.get("model_status") or dcf_result.get("status") or "unknown")
    reverse_status = str(reverse_result.get("model_status") or reverse_result.get("status") or "unknown")
    fair_value_gap = None
    if dcf_status != "unsupported":
        fair_value_gap = (
            ((fair_value_per_share - float(latest_price)) / float(latest_price))
            if fair_value_per_share is not None and latest_price not in (None, 0)
            else None
        )

    return WatchlistSummaryItemPayload(
        ticker=snapshot.company.ticker,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        cik=snapshot.company.cik,
        last_checked=snapshot.last_checked,
        refresh=refresh,
        alert_summary=alert_summary,
        latest_alert=_serialize_watchlist_latest_alert(latest_alert),
        latest_activity=_serialize_watchlist_latest_activity(latest_activity),
        coverage=WatchlistCoveragePayload(
            financial_periods=financial_periods,
            price_points=price_points,
        ),
        fair_value_gap=fair_value_gap,
        roic=_coerce_number(roic_result.get("roic"), None),
        shareholder_yield=_coerce_number(capital_result.get("shareholder_yield"), None),
        implied_growth=_coerce_number(reverse_result.get("implied_growth"), None) if reverse_status != "unsupported" else None,
        fair_value_gap_status=dcf_status,
        implied_growth_status=reverse_status,
        valuation_band_percentile=_coerce_number(reverse_result.get("valuation_band_percentile"), None),
        balance_sheet_risk=_coerce_number(ratios_values.get("net_debt_to_fcf") if isinstance(ratios_values, dict) else None, None),
        market_context_status=get_cached_market_context_status(),
    )


def _build_missing_watchlist_summary_item(background_tasks: BackgroundTasks, ticker: str) -> WatchlistSummaryItemPayload:
    return WatchlistSummaryItemPayload(
        ticker=ticker,
        name=None,
        sector=None,
        cik=None,
        last_checked=None,
        refresh=_trigger_refresh(background_tasks, ticker, reason="missing"),
        alert_summary=AlertsSummaryPayload(total=0, high=0, medium=0, low=0),
        latest_alert=None,
        latest_activity=None,
        coverage=WatchlistCoveragePayload(financial_periods=0, price_points=0),
        fair_value_gap=None,
        roic=None,
        shareholder_yield=None,
        implied_growth=None,
        fair_value_gap_status=None,
        implied_growth_status=None,
        valuation_band_percentile=None,
        balance_sheet_risk=None,
        market_context_status=get_cached_market_context_status(),
    )


def _coerce_number(primary: Any, secondary: Any) -> Number:
    value = primary if primary is not None else secondary
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number == number:
        return None
    return number


def _serialize_watchlist_latest_alert(alert: AlertPayload | None) -> WatchlistLatestAlertPayload | None:
    if alert is None:
        return None
    return WatchlistLatestAlertPayload(
        id=alert.id,
        level=alert.level,
        title=alert.title,
        source=alert.source,
        date=alert.date,
        href=alert.href,
    )


def _serialize_watchlist_latest_activity(entry: ActivityFeedEntryPayload | None) -> WatchlistLatestActivityPayload | None:
    if entry is None:
        return None
    return WatchlistLatestActivityPayload(
        id=entry.id,
        type=entry.type,
        badge=entry.badge,
        title=entry.title,
        date=entry.date,
        href=entry.href,
    )


def _is_governance_form(form: str | None) -> bool:
    normalized = (form or "").upper()
    return normalized in {"DEF 14A", "DEFA14A"}


def _is_event_form(form: str | None) -> bool:
    normalized = (form or "").upper()
    return normalized == "8-K"


def _classify_filing_event(items: str | None, description: str | None) -> str:
    normalized_items = (items or "").replace(" ", "")
    item_tokens = {token for token in normalized_items.split(",") if token}
    description_text = (description or "").lower()

    if item_tokens & {"2.02", "7.01", "9.01"}:
        return "Earnings"
    if item_tokens & {"1.01", "2.01"}:
        return "Deal"
    if item_tokens & {"2.03", "2.04", "2.05", "2.06"}:
        return "Financing"
    if item_tokens & {"5.02", "5.03", "5.05"}:
        return "Leadership"
    if item_tokens & {"3.01", "3.02", "3.03"}:
        return "Capital Markets"
    if item_tokens & {"8.01"}:
        return "General Update"
    if "earnings" in description_text or "results" in description_text:
        return "Earnings"
    if "director" in description_text or "officer" in description_text or "chief executive" in description_text:
        return "Leadership"
    if "agreement" in description_text or "acquisition" in description_text or "merger" in description_text:
        return "Deal"
    if "debt" in description_text or "credit" in description_text or "financing" in description_text:
        return "Financing"
    return "Other"


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


app = FastAPI(title="Financial Cache API", version="1.1.0")
register_routers(app, sys.modules[__name__])
