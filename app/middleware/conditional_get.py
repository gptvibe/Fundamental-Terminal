from __future__ import annotations

import hashlib
import inspect
import logging
from datetime import datetime

from fastapi import FastAPI, Request, Response, status

from app.api.handlers import _shared
from app.db import async_session_maker, get_async_engine
from app.middleware.company_cache import (
    COMPANY_ROUTE_CACHE_CONTROL,
    _canonicalize_company_query_string,
    _company_route_hot_cache_keys,
    _format_company_cache_last_modified,
    _normalize_company_cache_datetime,
    _resolved_company_as_of,
    _should_apply_company_route_cache,
)
from app.services.cache_queries import get_company_snapshot, get_company_snapshots_by_ticker


def _legacy_or_shared_attr(name: str):
    try:
        import app.main as main_module
    except Exception:  # pragma: no cover - defensive during bootstrap
        main_module = None

    if main_module is not None and hasattr(main_module, name):
        return getattr(main_module, name)

    try:
        import app.legacy_api as legacy_module
    except Exception:  # pragma: no cover - defensive during bootstrap
        legacy_module = None

    if legacy_module is not None and hasattr(legacy_module, name):
        return getattr(legacy_module, name)
    return getattr(_shared, name, None)


def _cache_query_attr(name: str, fallback):
    candidate = _legacy_or_shared_attr(name)
    if candidate is not None:
        return candidate
    return fallback


def _build_company_cache_etag(request: Request, *, scope_key: str, last_refreshed_at: datetime) -> str:
    normalized = _normalize_company_cache_datetime(last_refreshed_at)
    assert normalized is not None
    canonical_query = _canonicalize_company_query_string(request)
    canonical = f"{scope_key}|{request.url.path}|{canonical_query}|{normalized.isoformat()}".encode("utf-8")
    return f'W/"company-{hashlib.sha256(canonical).hexdigest()[:16]}"'


def _company_request_etag_matches(request: Request, etag: str) -> bool:
    raw_value = request.headers.get("if-none-match")
    if not raw_value:
        return False
    for candidate in raw_value.split(","):
        normalized = candidate.strip()
        if normalized == "*" or normalized == etag:
            return True
    return False


def _load_company_snapshot_for_cache(sync_session, ticker: str):
    loader = _legacy_or_shared_attr("_resolve_cached_company_snapshot")
    if callable(loader):
        snapshot = loader(sync_session, ticker)
        if snapshot is not None:
            return snapshot
    get_snapshot = _cache_query_attr("get_company_snapshot", get_company_snapshot)
    return get_snapshot(sync_session, ticker)


async def _resolve_company_route_hot_cache_metadata(request: Request) -> tuple[str, str | None, bool] | None:
    resolver = _legacy_or_shared_attr("_get_hot_cached_payload")
    if not callable(resolver):
        return None

    for cache_key in _company_route_hot_cache_keys(request):
        lookup = resolver(cache_key)
        if inspect.isawaitable(lookup):
            lookup = await lookup
        if lookup is None or not getattr(lookup, "is_fresh", False):
            continue
        etag = getattr(lookup, "etag", None)
        if not etag:
            continue
        return etag, getattr(lookup, "last_modified", None), True

    return None


async def _run_company_cache_lookup(callback):
    session_scope = _legacy_or_shared_attr("_session_scope")
    run_with_binding = _legacy_or_shared_attr("_run_with_session_binding")
    if callable(session_scope):
        async with session_scope() as session:
            if callable(run_with_binding):
                return await run_with_binding(session, callback)
            if hasattr(session, "run_sync"):
                return await session.run_sync(callback)
            return callback(session)

    get_async_engine()
    async with async_session_maker() as session:
        return await session.run_sync(callback)


async def _resolve_company_route_cache_metadata(request: Request) -> tuple[str, str | None, bool] | None:
    if request.method.upper() != "GET":
        return None

    path = request.url.path
    if not _should_apply_company_route_cache(path):
        return None
    if not path.startswith("/api/companies/"):
        return None

    _normalized_as_of, as_of_is_valid = _resolved_company_as_of(request)
    if not as_of_is_valid:
        return None

    try:
        hot_cache_metadata = await _resolve_company_route_hot_cache_metadata(request)
        if hot_cache_metadata is not None:
            return hot_cache_metadata

        if path == "/api/companies/compare":
            from app.query_params import DuplicateSingletonQueryParamError, read_singleton_query_param

            try:
                raw_tickers = read_singleton_query_param(request, "tickers") or ""
            except DuplicateSingletonQueryParamError:
                return None
            tickers = [ticker.strip().upper() for ticker in raw_tickers.split(",") if ticker.strip()]
            if not tickers:
                return None

            def _load_compare_last_refreshed(sync_session):
                load_snapshots = _cache_query_attr("get_company_snapshots_by_ticker", get_company_snapshots_by_ticker)
                snapshots = load_snapshots(sync_session, tickers)
                if len(snapshots) != len(set(tickers)):
                    return None
                if any(snapshot.cache_state != "fresh" or snapshot.last_checked is None for snapshot in snapshots.values()):
                    return None
                return max(snapshot.last_checked for snapshot in snapshots.values())

            last_refreshed_at = await _run_company_cache_lookup(_load_compare_last_refreshed)
            if last_refreshed_at is None:
                return None
            return (
                _build_company_cache_etag(request, scope_key=f"compare:{','.join(sorted(tickers))}", last_refreshed_at=last_refreshed_at),
                _format_company_cache_last_modified(last_refreshed_at),
                False,
            )

        suffix = path[len("/api/companies/") :]
        ticker, separator, _rest = suffix.partition("/")
        if not separator or not ticker:
            return None
        if ticker in {"search", "resolve", "compare"}:
            return None

        snapshot = await _run_company_cache_lookup(
            lambda sync_session: _load_company_snapshot_for_cache(sync_session, ticker.strip().upper())
        )
        if snapshot is None or snapshot.last_checked is None or getattr(snapshot, "cache_state", None) != "fresh":
            return None

        return (
            _build_company_cache_etag(request, scope_key=f"ticker:{snapshot.company.ticker}", last_refreshed_at=snapshot.last_checked),
            _format_company_cache_last_modified(snapshot.last_checked),
            False,
        )
    except Exception:
        logging.getLogger(__name__).debug("Unable to resolve company cache metadata", exc_info=True)
        return None


def _apply_company_route_cache_headers(response: Response, *, etag: str | None, last_modified: str | None) -> None:
    response.headers["Cache-Control"] = COMPANY_ROUTE_CACHE_CONTROL
    if etag is not None:
        response.headers["ETag"] = etag
    if last_modified is not None:
        response.headers["Last-Modified"] = last_modified


def register_company_conditional_get_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def company_route_cache_middleware(request: Request, call_next):
        cache_metadata = await _resolve_company_route_cache_metadata(request)
        if cache_metadata is not None:
            etag, last_modified, _from_hot_cache = cache_metadata
            if _company_request_etag_matches(request, etag):
                not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
                _apply_company_route_cache_headers(not_modified, etag=etag, last_modified=last_modified)
                return not_modified

        response = await call_next(request)

        if (
            request.method.upper() == "GET"
            and request.url.path.startswith("/api/companies/")
            and _should_apply_company_route_cache(request.url.path)
        ):
            if cache_metadata is not None:
                etag, last_modified, from_hot_cache = cache_metadata
                if not from_hot_cache:
                    hot_cache_metadata = await _resolve_company_route_hot_cache_metadata(request)
                    if hot_cache_metadata is not None:
                        etag, last_modified, _ = hot_cache_metadata
                _apply_company_route_cache_headers(response, etag=etag, last_modified=last_modified)
            else:
                hot_cache_metadata = await _resolve_company_route_hot_cache_metadata(request)
                if hot_cache_metadata is not None:
                    etag, last_modified, _ = hot_cache_metadata
                    _apply_company_route_cache_headers(response, etag=etag, last_modified=last_modified)
                    return response
                _apply_company_route_cache_headers(
                    response,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                )

        return response


__all__ = [
    "_build_company_cache_etag",
    "register_company_conditional_get_middleware",
]
