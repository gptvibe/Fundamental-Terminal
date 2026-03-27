from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.api.schemas.common import CompanyPayload, RefreshState


class CompanySearchResponse(BaseModel):
    query: str
    results: list[CompanyPayload]
    refresh: RefreshState


class CompanyResolutionResponse(BaseModel):
    query: str
    resolved: bool
    ticker: str | None = None
    name: str | None = None
    error: Literal["not_found", "lookup_failed"] | None = None
