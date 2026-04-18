from __future__ import annotations

import hashlib
import inspect
import logging
from datetime import datetime, timezone
from email.utils import formatdate
from types import FunctionType
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Response, status

from app.api import register_routers
from app.api.handlers import _shared as _legacy_api
from app.config import settings
from app.db import async_session_maker, get_async_engine
from app.performance_audit import PerformanceAuditJSONResponse, begin_request, complete_request, end_request, is_enabled, should_skip_path
from app.query_params import DuplicateSingletonQueryParamError, read_singleton_query_param
from app.services.cache_queries import get_company_snapshot, get_company_snapshots_by_ticker


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


def _canonicalize_company_query_string(request: Request) -> str:
    singleton_values: dict[str, str | None] = {}
    singleton_names = {"as_of"}
    if request.url.path == "/api/companies/compare":
        singleton_names.add("tickers")
    elif request.url.path.startswith("/api/companies/") and request.url.path.endswith("/models"):
        singleton_names.update({"expand", "dupont_mode"})

    for name in singleton_names:
        try:
            singleton_values[name] = read_singleton_query_param(request, name)
        except DuplicateSingletonQueryParamError as exc:
            raise ValueError(str(exc)) from exc

    requested_as_of = singleton_values.get("as_of")
    if requested_as_of is not None:
        validated_as_of = globals().get("_validated_as_of")
        if callable(validated_as_of):
            validated_as_of(requested_as_of)

    if request.url.path.startswith("/api/companies/") and request.url.path.endswith("/models"):
        normalize_models_controls = globals().get("_normalize_company_models_query_controls")
        if callable(normalize_models_controls):
            _parsed_as_of, requested_expansions, normalized_mode, normalized_as_of = normalize_models_controls(
                requested_as_of=singleton_values.get("as_of"),
                expand=singleton_values.get("expand"),
                dupont_mode=singleton_values.get("dupont_mode"),
            )
            singleton_values["as_of"] = None if normalized_as_of == "latest" else normalized_as_of
            singleton_values["expand"] = ",".join(sorted(requested_expansions)) or None
            singleton_values["dupont_mode"] = normalized_mode

    query_items = sorted(
        [
            (name, value)
            for name, value in request.query_params.multi_items()
            if name not in singleton_names
        ]
        + [
            (name, value)
            for name, value in singleton_values.items()
            if value is not None
        ],
        key=lambda item: (item[0], item[1]),
    )
    return urlencode(query_items, doseq=True)


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
    loader = globals().get("_resolve_cached_company_snapshot")
    if callable(loader):
        snapshot = loader(sync_session, ticker)
        if snapshot is not None:
            return snapshot
    return get_company_snapshot(sync_session, ticker)


def _resolved_company_as_of(request: Request) -> tuple[str | None, bool]:
    try:
        requested_as_of = read_singleton_query_param(request, "as_of")
    except DuplicateSingletonQueryParamError:
        return None, False
    if requested_as_of is None:
        return "latest", True

    validated_as_of = globals().get("_validated_as_of")
    normalize_as_of = globals().get("_normalize_as_of")
    try:
        parsed_as_of = validated_as_of(requested_as_of) if callable(validated_as_of) else None
        normalized = normalize_as_of(parsed_as_of) if callable(normalize_as_of) else None
    except Exception:
        return None, False

    if parsed_as_of is None:
        return None, False
    return normalized or requested_as_of, True


def _resolved_company_models_controls(request: Request) -> tuple[dict[str, str | None] | None, bool]:
    try:
        requested_as_of = read_singleton_query_param(request, "as_of")
        requested_expand = read_singleton_query_param(request, "expand")
        requested_dupont_mode = read_singleton_query_param(request, "dupont_mode")
    except DuplicateSingletonQueryParamError:
        return None, False

    normalize_models_controls = globals().get("_normalize_company_models_query_controls")
    if not callable(normalize_models_controls):
        return None, False

    try:
        _parsed_as_of, requested_expansions, normalized_mode, normalized_as_of = normalize_models_controls(
            requested_as_of=requested_as_of,
            expand=requested_expand,
            dupont_mode=requested_dupont_mode,
        )
    except Exception:
        return None, False

    return {
        "as_of": normalized_as_of,
        "expand": ",".join(sorted(requested_expansions)) or "default",
        "dupont_mode": normalized_mode,
    }, True


def _company_route_hot_cache_keys(request: Request) -> list[str]:
    path = request.url.path
    if not path.startswith("/api/companies/"):
        return []

    suffix = path[len("/api/companies/"):]
    ticker, separator, rest = suffix.partition("/")
    if not separator or not ticker or ticker in {"search", "resolve", "compare"}:
        return []

    normalized_ticker = ticker.strip().upper()
    normalized_as_of, as_of_is_valid = _resolved_company_as_of(request)
    if not as_of_is_valid or normalized_as_of is None:
        return []

    route_name = rest.strip()
    if not route_name:
        return []

    if route_name == "financials":
        return [f"financials:{normalized_ticker}:asof={normalized_as_of}"]

    if route_name in {"overview", "brief"}:
        return [f"financials:{normalized_ticker}:asof={normalized_as_of}"]

    if route_name == "charts":
        return [f"charts:{normalized_ticker}:asof={normalized_as_of}"]

    if route_name == "capital-structure":
        try:
            max_periods = int(request.query_params.get("max_periods", "8"))
        except ValueError:
            return []
        return [f"capital_structure:{normalized_ticker}:periods={max_periods}:asof={normalized_as_of}"]

    if route_name == "models":
        model_controls, controls_are_valid = _resolved_company_models_controls(request)
        if not controls_are_valid or model_controls is None:
            return []
        parse_requested_models = globals().get("_parse_requested_models")
        requested_models = parse_requested_models(request.query_params.get("model")) if callable(parse_requested_models) else []
        if not settings.valuation_workbench_enabled:
            requested_models = [
                item
                for item in requested_models
                if item not in {"reverse_dcf", "roic", "capital_allocation"}
            ]
        return [
            (
                f"models:{normalized_ticker}:models={','.join(requested_models)}:dupont={model_controls['dupont_mode'] or 'default'}"
                f":expand={model_controls['expand']}:asof={model_controls['as_of']}"
            )
        ]

    if route_name == "peers":
        parse_csv_values = globals().get("_parse_csv_values")
        selected_tickers = parse_csv_values(request.query_params.get("peers")) if callable(parse_csv_values) else []
        return [f"peers:{normalized_ticker}:selected={','.join(selected_tickers)}:asof={normalized_as_of}"]

    if route_name == "oil-scenario-overlay":
        return [f"oil_scenario_overlay:{normalized_ticker}"]

    if route_name == "oil":
        return [f"oil_scenario:{normalized_ticker}"]

    return []


async def _resolve_company_route_hot_cache_metadata(request: Request) -> tuple[str, str | None, bool] | None:
    resolver = globals().get("_get_hot_cached_payload")
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
    session_scope = globals().get("_session_scope")
    run_with_binding = globals().get("_run_with_session_binding")
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
            try:
                raw_tickers = read_singleton_query_param(request, "tickers") or ""
            except DuplicateSingletonQueryParamError:
                return None
            tickers = [ticker.strip().upper() for ticker in raw_tickers.split(",") if ticker.strip()]
            if not tickers:
                return None

            def _load_compare_last_refreshed(sync_session):
                snapshots = get_company_snapshots_by_ticker(sync_session, tickers)
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

        suffix = path[len("/api/companies/"):]
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


def create_app() -> FastAPI:
    app = FastAPI(title="Financial Cache API", version="1.1.0", default_response_class=PerformanceAuditJSONResponse)

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

        if request.method.upper() == "GET" and request.url.path.startswith("/api/companies/"):
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
