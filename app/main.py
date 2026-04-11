from __future__ import annotations

import hashlib
import inspect
import logging
from datetime import datetime, timezone
from email.utils import formatdate
from types import FunctionType

from fastapi import FastAPI, Request, Response, status

from app.api import register_routers
from app.api.handlers import _shared as _legacy_api
from app.db import async_session_maker, get_async_engine
from app.performance_audit import PerformanceAuditJSONResponse, begin_request, complete_request, end_request, is_enabled, should_skip_path
from app.services.cache_queries import get_company_snapshot


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


COMPANY_ROUTE_CACHE_CONTROL = "public, max-age=20, stale-while-revalidate=300"


def _normalize_company_cache_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_company_cache_last_modified(value: datetime | None) -> str | None:
    normalized = _normalize_company_cache_datetime(value)
    if normalized is None:
        return None
    return formatdate(normalized.timestamp(), usegmt=True)


def _build_company_cache_etag(request: Request, *, scope_key: str, last_refreshed_at: datetime) -> str:
    normalized = _normalize_company_cache_datetime(last_refreshed_at)
    assert normalized is not None
    canonical_query = request.url.query or ""
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
    loader = globals().get("_resolve_cached_company_snapshot")
    if callable(loader):
        snapshot = loader(sync_session, ticker)
        if snapshot is not None:
            return snapshot
    return get_company_snapshot(sync_session, ticker)


async def _resolve_company_route_cache_metadata(request: Request) -> tuple[str, str | None] | None:
    if request.method.upper() != "GET":
        return None

    path = request.url.path
    if not path.startswith("/api/companies/"):
        return None

    try:
        get_async_engine()
        async with async_session_maker() as session:
            if path == "/api/companies/compare":
                raw_tickers = request.query_params.get("tickers", "")
                tickers = [ticker.strip().upper() for ticker in raw_tickers.split(",") if ticker.strip()]
                if not tickers:
                    return None

                def _load_compare_last_refreshed(sync_session):
                    return max(
                        (
                            snapshot.last_checked
                            for ticker in tickers
                            if (snapshot := _load_company_snapshot_for_cache(sync_session, ticker)) is not None and snapshot.last_checked is not None
                        ),
                        default=None,
                    )

                last_refreshed_at = await session.run_sync(_load_compare_last_refreshed)
                if last_refreshed_at is None:
                    return None
                return (
                    _build_company_cache_etag(request, scope_key=f"compare:{','.join(sorted(tickers))}", last_refreshed_at=last_refreshed_at),
                    _format_company_cache_last_modified(last_refreshed_at),
                )

            suffix = path[len("/api/companies/"):]
            ticker, separator, _rest = suffix.partition("/")
            if not separator or not ticker:
                return None
            if ticker in {"search", "resolve", "compare"}:
                return None

            snapshot = await session.run_sync(
                lambda sync_session: _load_company_snapshot_for_cache(sync_session, ticker.strip().upper())
            )
            if snapshot is None or snapshot.last_checked is None:
                return None

            return (
                _build_company_cache_etag(request, scope_key=f"ticker:{snapshot.company.ticker}", last_refreshed_at=snapshot.last_checked),
                _format_company_cache_last_modified(snapshot.last_checked),
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


def create_app() -> FastAPI:
    app = FastAPI(title="Financial Cache API", version="1.1.0", default_response_class=PerformanceAuditJSONResponse)

    @app.middleware("http")
    async def company_route_cache_middleware(request: Request, call_next):
        cache_metadata = await _resolve_company_route_cache_metadata(request)
        if cache_metadata is not None:
            etag, last_modified = cache_metadata
            if _company_request_etag_matches(request, etag):
                not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
                _apply_company_route_cache_headers(not_modified, etag=etag, last_modified=last_modified)
                return not_modified

        response = await call_next(request)

        if request.method.upper() == "GET" and request.url.path.startswith("/api/companies/"):
            if cache_metadata is not None:
                etag, last_modified = cache_metadata
                _apply_company_route_cache_headers(response, etag=etag, last_modified=last_modified)
            else:
                _apply_company_route_cache_headers(
                    response,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                )

        return response

    @app.middleware("http")
    async def performance_audit_middleware(request, call_next):
        if not is_enabled() or should_skip_path(request.url.path):
            return await call_next(request)

        metrics, token = begin_request(request)
        response = None
        try:
            response = await call_next(request)
            body = getattr(response, "body", None)
            if metrics.response_bytes is None and isinstance(body, (bytes, bytearray)):
                metrics.response_bytes = len(body)
            complete_request(request, metrics, status_code=response.status_code)
            return response
        except Exception as exc:
            complete_request(request, metrics, status_code=getattr(response, "status_code", 500), error_type=type(exc).__name__)
            raise
        finally:
            end_request(token)

    register_routers(app)
    return app


app = create_app()


def _clone_legacy_function(function):
    cloned = FunctionType(
        function.__code__,
        globals(),
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__kwdefaults__ = getattr(function, "__kwdefaults__", None)
    cloned.__annotations__ = dict(getattr(function, "__annotations__", {}))
    cloned.__doc__ = function.__doc__
    cloned.__module__ = __name__
    cloned.__qualname__ = function.__qualname__
    cloned.__dict__.update(getattr(function, "__dict__", {}))
    return cloned


def _export_legacy_api() -> None:
    reserved_names = set(globals()) | {"app", "create_app"}
    for name, value in vars(_legacy_api).items():
        if name.startswith("__") or name in reserved_names:
            continue
        if inspect.isfunction(value) and getattr(value, "__module__", None) == _legacy_api.__name__:
            export_value = value
            wrapped = getattr(value, "__wrapped__", None)
            if inspect.iscoroutinefunction(value) and inspect.isfunction(wrapped):
                if getattr(wrapped, "__module__", None) == _legacy_api.__name__ and not inspect.iscoroutinefunction(wrapped):
                    export_value = wrapped
            globals()[name] = _clone_legacy_function(export_value)
            continue
        globals()[name] = value


_export_legacy_api()


def __getattr__(name: str):
    return getattr(_legacy_api, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_legacy_api)))
