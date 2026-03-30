from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.responses import Response

from app.source_registry import get_source_definition


SourceContractStrictOfficialBehavior = Literal[
    "not_applicable",
    "official_only",
    "drop_commercial_fallback_inputs",
]

UIDisclosurePresentation = Literal[
    "badge",
    "banner",
    "inline_note",
    "hidden_surface_explanation",
]

ROUTE_SOURCE_CONTRACT_OPENAPI_KEY = "x-ft-source-contract-v1"
_SUPPORTED_ROUTE_METHODS = frozenset({"GET", "POST"})
_FALLBACK_SOURCE_TIERS = frozenset({"commercial_fallback", "manual_override"})


class ConfidencePenaltyRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    applies_when: str
    effect: str


class UIDisclosureRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: str
    applies_when: str
    presentation: UIDisclosurePresentation
    message: str


class SourceContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed_source_ids: tuple[str, ...] = Field(default_factory=tuple)
    fallback_permitted: bool
    strict_official_behavior: SourceContractStrictOfficialBehavior
    confidence_penalty_rules: tuple[ConfidencePenaltyRule, ...] = Field(default_factory=tuple)
    ui_disclosure_requirements: tuple[UIDisclosureRequirement, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_allowed_sources(self) -> SourceContract:
        deduped_source_ids = tuple(dict.fromkeys(self.allowed_source_ids))
        if deduped_source_ids != self.allowed_source_ids:
            raise ValueError("allowed_source_ids must not contain duplicates")

        invalid_source_ids = [source_id for source_id in self.allowed_source_ids if get_source_definition(source_id) is None]
        if invalid_source_ids:
            raise ValueError(f"unknown source ids in source contract: {', '.join(invalid_source_ids)}")

        fallback_source_ids = []
        for source_id in self.allowed_source_ids:
            definition = get_source_definition(source_id)
            if definition is not None and definition.tier in {"commercial_fallback", "manual_override"}:
                fallback_source_ids.append(source_id)

        if fallback_source_ids and not self.fallback_permitted:
            raise ValueError(
                "fallback_permitted must be true when commercial or manual fallback sources are allowed: "
                f"{', '.join(fallback_source_ids)}"
            )

        return self


class EndpointSourceContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: Literal["GET", "POST"]
    path: str
    source_contract: SourceContract


@dataclass(frozen=True, slots=True)
class PayloadSourceContractState:
    source_ids: frozenset[str]
    fallback_source_ids: frozenset[str]
    strict_official_mode: bool


def build_endpoint_source_contract_metadata(
    method: str,
    path: str,
    source_contract: SourceContract,
) -> dict[str, Any]:
    return EndpointSourceContract(
        method=method.upper(),
        path=path,
        source_contract=source_contract,
    ).model_dump(mode="json")


def add_internal_route(
    router: APIRouter,
    path: str,
    endpoint: Callable[..., Any],
    *,
    methods: Sequence[str],
    **kwargs: Any,
) -> None:
    router.add_api_route(path, endpoint, methods=list(_normalize_methods(methods)), **kwargs)


def add_user_visible_route(
    router: APIRouter,
    path: str,
    endpoint: Callable[..., Any],
    *,
    methods: Sequence[str],
    **kwargs: Any,
) -> None:
    normalized_methods = _normalize_methods(methods)
    if len(normalized_methods) != 1:
        raise ValueError(f"user-visible routes must register exactly one manifest-backed method for {path}")

    method = normalized_methods[0]

    from app.api.endpoint_source_contract_manifest import get_user_visible_endpoint_source_contract

    source_contract = get_user_visible_endpoint_source_contract(method, path)
    openapi_extra = dict(kwargs.pop("openapi_extra", None) or {})
    openapi_extra[ROUTE_SOURCE_CONTRACT_OPENAPI_KEY] = build_endpoint_source_contract_metadata(
        method,
        path,
        source_contract,
    )
    wrapped_endpoint = _wrap_endpoint_with_source_contract_validation(
        endpoint,
        method=method,
        path=path,
        source_contract=source_contract,
    )

    router.add_api_route(
        path,
        wrapped_endpoint,
        methods=[method],
        openapi_extra=openapi_extra,
        **kwargs,
    )


def is_user_visible_route(method: str, path: str) -> bool:
    normalized_method = method.upper()
    if normalized_method not in _SUPPORTED_ROUTE_METHODS:
        return False
    if path == "/health":
        return False
    if path.startswith("/api/internal/"):
        return False
    return path.startswith("/api/")


def get_user_visible_route_keys(app: FastAPI) -> set[tuple[str, str]]:
    route_keys: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            if is_user_visible_route(method, route.path):
                route_keys.add((method.upper(), route.path))
    return route_keys


def ensure_user_visible_routes_have_source_contracts(app: FastAPI) -> None:
    from app.api.endpoint_source_contract_manifest import USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS

    registered_route_keys = get_user_visible_route_keys(app)
    missing_manifest_entries = sorted(registered_route_keys - set(USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS))
    orphaned_manifest_entries = sorted(set(USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS) - registered_route_keys)
    missing_route_metadata: list[str] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or ():
            if not is_user_visible_route(method, route.path):
                continue

            normalized_method = method.upper()
            expected_contract = USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS.get((normalized_method, route.path))
            if expected_contract is None:
                continue

            metadata = (route.openapi_extra or {}).get(ROUTE_SOURCE_CONTRACT_OPENAPI_KEY)
            expected_metadata = build_endpoint_source_contract_metadata(normalized_method, route.path, expected_contract)
            if metadata != expected_metadata:
                missing_route_metadata.append(f"{normalized_method} {route.path}")

    if not missing_manifest_entries and not orphaned_manifest_entries and not missing_route_metadata:
        return

    errors: list[str] = []
    if missing_manifest_entries:
        errors.append(
            "missing manifest entries: "
            + ", ".join(f"{method} {path}" for method, path in missing_manifest_entries)
        )
    if orphaned_manifest_entries:
        errors.append(
            "orphaned manifest entries: "
            + ", ".join(f"{method} {path}" for method, path in orphaned_manifest_entries)
        )
    if missing_route_metadata:
        errors.append(
            "routes missing manifest-backed source contract metadata: " + ", ".join(missing_route_metadata)
        )

    raise RuntimeError("Endpoint source contract validation failed: " + "; ".join(errors))


def validate_source_contract_payload(
    source_contract: SourceContract,
    payload: Any,
    *,
    method: str,
    path: str,
) -> None:
    payload_state = _extract_payload_source_contract_state(payload)
    if payload_state is None:
        return

    allowed_source_ids = set(source_contract.allowed_source_ids)
    unauthorized_source_ids = sorted(payload_state.source_ids - allowed_source_ids)
    if unauthorized_source_ids:
        raise RuntimeError(
            f"Source contract violation for {method} {path}: unauthorized source ids in payload: {', '.join(unauthorized_source_ids)}"
        )

    if payload_state.fallback_source_ids and not source_contract.fallback_permitted:
        raise RuntimeError(
            f"Source contract violation for {method} {path}: fallback sources are not permitted but payload exposed: "
            f"{', '.join(sorted(payload_state.fallback_source_ids))}"
        )

    if (
        source_contract.strict_official_behavior == "drop_commercial_fallback_inputs"
        and payload_state.strict_official_mode
        and payload_state.fallback_source_ids
    ):
        raise RuntimeError(
            f"Source contract violation for {method} {path}: strict official mode payload still exposes fallback sources: "
            f"{', '.join(sorted(payload_state.fallback_source_ids))}"
        )


def _normalize_methods(methods: Sequence[str]) -> tuple[str, ...]:
    normalized_methods: list[str] = []
    for method in methods:
        normalized_method = str(method).upper()
        if normalized_method not in _SUPPORTED_ROUTE_METHODS:
            raise ValueError(f"unsupported route method for source-contract enforcement: {normalized_method}")
        if normalized_method not in normalized_methods:
            normalized_methods.append(normalized_method)
    return tuple(normalized_methods)


def _wrap_endpoint_with_source_contract_validation(
    endpoint: Callable[..., Any],
    *,
    method: str,
    path: str,
    source_contract: SourceContract,
) -> Callable[..., Any]:
    endpoint_signature = inspect.signature(endpoint)

    if inspect.iscoroutinefunction(endpoint):
        @wraps(endpoint)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await endpoint(*args, **kwargs)
            validate_source_contract_payload(source_contract, result, method=method, path=path)
            return result

        async_wrapper.__signature__ = endpoint_signature  # type: ignore[attr-defined]
        return async_wrapper

    @wraps(endpoint)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        result = endpoint(*args, **kwargs)
        validate_source_contract_payload(source_contract, result, method=method, path=path)
        return result

    sync_wrapper.__signature__ = endpoint_signature  # type: ignore[attr-defined]
    return sync_wrapper


def _extract_payload_source_contract_state(payload: Any) -> PayloadSourceContractState | None:
    payload_dict = _coerce_payload_mapping(payload)
    if payload_dict is None:
        return None

    provenance_rows = payload_dict.get("provenance")
    source_mix = payload_dict.get("source_mix")
    if not isinstance(provenance_rows, list) and not isinstance(source_mix, Mapping):
        return None

    source_ids: set[str] = set()
    fallback_source_ids: set[str] = set()

    if isinstance(source_mix, Mapping):
        source_ids.update(_coerce_string_list(source_mix.get("source_ids")))
        source_ids.update(_coerce_string_list(source_mix.get("primary_source_ids")))
        mix_fallback_source_ids = _coerce_string_list(source_mix.get("fallback_source_ids"))
        source_ids.update(mix_fallback_source_ids)
        fallback_source_ids.update(mix_fallback_source_ids)

    if isinstance(provenance_rows, list):
        for row in provenance_rows:
            if not isinstance(row, Mapping):
                continue
            source_id = _coerce_string(row.get("source_id"))
            source_tier = _coerce_string(row.get("source_tier"))
            if source_id is None:
                continue
            source_ids.add(source_id)
            if source_tier in _FALLBACK_SOURCE_TIERS:
                fallback_source_ids.add(source_id)

    return PayloadSourceContractState(
        source_ids=frozenset(source_ids),
        fallback_source_ids=frozenset(fallback_source_ids),
        strict_official_mode=_payload_is_strict_official_mode(payload_dict),
    )


def _coerce_payload_mapping(payload: Any) -> Mapping[str, Any] | None:
    if isinstance(payload, Response):
        return None
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="python")
    if isinstance(payload, Mapping):
        return payload
    return None


def _payload_is_strict_official_mode(payload_dict: Mapping[str, Any]) -> bool:
    if "strict_official_mode" in _coerce_string_list(payload_dict.get("confidence_flags")):
        return True

    company = payload_dict.get("company")
    if isinstance(company, Mapping):
        return bool(company.get("strict_official_mode"))
    if isinstance(company, BaseModel):
        return bool(company.model_dump(mode="python").get("strict_official_mode"))
    return False


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [text for item in value if (text := _coerce_string(item)) is not None]


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "ConfidencePenaltyRule",
    "EndpointSourceContract",
    "ROUTE_SOURCE_CONTRACT_OPENAPI_KEY",
    "SourceContract",
    "UIDisclosureRequirement",
    "add_internal_route",
    "add_user_visible_route",
    "build_endpoint_source_contract_metadata",
    "ensure_user_visible_routes_have_source_contracts",
    "get_user_visible_route_keys",
    "is_user_visible_route",
    "validate_source_contract_payload",
]