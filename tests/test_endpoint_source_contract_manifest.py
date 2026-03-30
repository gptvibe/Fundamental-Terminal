from __future__ import annotations

from fastapi.routing import APIRoute

from app.api.endpoint_source_contract_manifest import USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS
from app.api.source_contracts import (
    ROUTE_SOURCE_CONTRACT_OPENAPI_KEY,
    build_endpoint_source_contract_metadata,
    is_user_visible_route,
)
from app.main import app


def _iter_user_visible_routes():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods or ()):
            if is_user_visible_route(method, route.path):
                yield method.upper(), route


def test_source_contract_manifest_covers_every_user_visible_route() -> None:
    actual_routes = {(method, route.path) for method, route in _iter_user_visible_routes()}
    assert actual_routes == set(USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS)


def test_user_visible_routes_publish_manifest_backed_source_contract_metadata() -> None:
    for method, route in _iter_user_visible_routes():
        expected_metadata = build_endpoint_source_contract_metadata(
            method,
            route.path,
            USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS[(method, route.path)],
        )
        assert route.openapi_extra is not None
        assert route.openapi_extra.get(ROUTE_SOURCE_CONTRACT_OPENAPI_KEY) == expected_metadata