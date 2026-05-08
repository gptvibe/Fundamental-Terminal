from __future__ import annotations

from fastapi.routing import APIRoute

from app.api.endpoint_source_contract_manifest import (
    USER_VISIBLE_ENDPOINT_SOURCE_CONTRACT_EXCEPTIONS,
    USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS,
)
from app.api.source_contracts import (
    ROUTE_SOURCE_CONTRACT_OPENAPI_KEY,
    build_endpoint_source_contract_metadata,
    is_user_visible_route,
)
from app.main import app
from app.source_registry import get_source_definition


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


def test_only_documented_exceptions_use_empty_source_contracts() -> None:
    empty_contract_routes = {
        key
        for key, contract in USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS.items()
        if not contract.allowed_source_ids
        and contract.fallback_permitted is False
        and contract.strict_official_behavior == "not_applicable"
        and not contract.confidence_penalty_rules
        and not contract.ui_disclosure_requirements
    }

    assert empty_contract_routes == set(USER_VISIBLE_ENDPOINT_SOURCE_CONTRACT_EXCEPTIONS)

    for key, exception in USER_VISIBLE_ENDPOINT_SOURCE_CONTRACT_EXCEPTIONS.items():
        assert exception.method == key[0]
        assert exception.path == key[1]
        assert exception.reason.strip()
        assert exception.exception_kind.strip()


def test_public_research_routes_keep_non_empty_source_contracts() -> None:
    for key, contract in USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS.items():
        if key in USER_VISIBLE_ENDPOINT_SOURCE_CONTRACT_EXCEPTIONS:
            continue

        assert contract.allowed_source_ids, f"expected research/data route to declare allowed sources: {key[0]} {key[1]}"


def test_fallback_backed_research_routes_declare_strict_official_behavior() -> None:
    for key, contract in USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS.items():
        if key in USER_VISIBLE_ENDPOINT_SOURCE_CONTRACT_EXCEPTIONS:
            continue
        if key == ("GET", "/api/source-registry"):
            continue
        fallback_source_ids = {
            source_id
            for source_id in contract.allowed_source_ids
            if (definition := get_source_definition(source_id)) is not None
            and definition.tier in {"commercial_fallback", "manual_override"}
        }
        if not fallback_source_ids:
            continue

        assert contract.strict_official_behavior != "not_applicable", (
            f"expected fallback-capable route to declare strict official mode behavior: {key[0]} {key[1]}"
        )