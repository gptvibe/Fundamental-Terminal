from __future__ import annotations

from starlette.datastructures import QueryParams
from starlette.requests import HTTPConnection


class DuplicateSingletonQueryParamError(ValueError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"{name} may only be provided once")


def _coerce_query_params(source: HTTPConnection | QueryParams) -> QueryParams:
    if isinstance(source, QueryParams):
        return source
    return source.query_params


def read_singleton_query_param(source: HTTPConnection | QueryParams, name: str) -> str | None:
    query_params = _coerce_query_params(source)
    values = query_params.getlist(name)
    if len(values) > 1:
        raise DuplicateSingletonQueryParamError(name)
    if not values:
        return None
    normalized = values[0].strip()
    return normalized or None
