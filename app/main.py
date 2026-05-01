from __future__ import annotations

import logging

from fastapi import FastAPI

from app import legacy_api as _legacy_api
from app.api import register_routers
from app.middleware import (
    SecurityHeadersMiddleware,
    register_auth_middleware,
    register_company_conditional_get_middleware,
    register_performance_audit_middleware,
    register_rate_limit_middleware,
)
from app.middleware.company_cache import _canonicalize_company_query_string, _company_route_hot_cache_keys
from app.middleware.conditional_get import _build_company_cache_etag
from app.performance_audit import PerformanceAuditJSONResponse


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(title="Financial Cache API", version="1.1.0", default_response_class=PerformanceAuditJSONResponse)
    register_auth_middleware(app)
    register_rate_limit_middleware(app)
    register_company_conditional_get_middleware(app)
    register_performance_audit_middleware(app)
    app.add_middleware(SecurityHeadersMiddleware)
    register_routers(app)
    return app


app = create_app()
_legacy_api._export_legacy_api(
    globals(),
    reserved_names=set(globals()) | {"app", "create_app"},
    module_name=__name__,
)


def __getattr__(name: str):
    return getattr(_legacy_api, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_legacy_api)))
