from __future__ import annotations

import inspect
import logging
from types import FunctionType

from fastapi import FastAPI

from app.api import register_routers
from app.api.handlers import _shared as _legacy_api
from app.performance_audit import PerformanceAuditJSONResponse, begin_request, complete_request, end_request, is_enabled, should_skip_path


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(title="Financial Cache API", version="1.1.0", default_response_class=PerformanceAuditJSONResponse)

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
            globals()[name] = _clone_legacy_function(value)
            continue
        globals()[name] = value


_export_legacy_api()


def __getattr__(name: str):
    return getattr(_legacy_api, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_legacy_api)))
