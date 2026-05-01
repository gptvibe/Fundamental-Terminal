from __future__ import annotations

from starlette.requests import Request

from app.middleware.company_cache import _canonicalize_company_query_string, _company_route_hot_cache_keys


def _request_with_query_string(query_string: str, *, path: str) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "query_string": query_string.encode("utf-8"),
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_canonicalize_company_query_string_is_stable_for_reordered_query_params() -> None:
    first_request = _request_with_query_string(
        "foo=summary&model=dcf&foo=input_periods",
        path="/api/companies/AAPL/models",
    )
    second_request = _request_with_query_string(
        "model=dcf&foo=input_periods&foo=summary",
        path="/api/companies/AAPL/models",
    )

    assert _canonicalize_company_query_string(first_request) == "foo=input_periods&foo=summary&model=dcf"
    assert _canonicalize_company_query_string(first_request) == _canonicalize_company_query_string(second_request)


def test_company_route_hot_cache_keys_include_workspace_bootstrap_flags() -> None:
    default_request = _request_with_query_string(
        "",
        path="/api/companies/AAPL/workspace-bootstrap",
    )
    enabled_request = _request_with_query_string(
        "include_insiders=yes",
        path="/api/companies/AAPL/workspace-bootstrap",
    )

    assert _company_route_hot_cache_keys(default_request) == [
        "workspace_bootstrap:AAPL:view=full:asof=latest:overview=0:insiders=0:institutional=0:earnings=0:prices=default"
    ]
    assert _company_route_hot_cache_keys(enabled_request) == [
        "workspace_bootstrap:AAPL:view=full:asof=latest:overview=0:insiders=1:institutional=0:earnings=0:prices=default"
    ]
