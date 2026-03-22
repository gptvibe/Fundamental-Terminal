from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

Number = int | float | None


@dataclass(frozen=True, slots=True)
class FinancialPoint:
    statement_id: int
    filing_type: str
    period_start: date
    period_end: date
    source: str
    last_updated: datetime
    data: dict[str, Number]


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    latest_price: float | None
    price_date: date | None
    price_source: str | None


@dataclass(frozen=True, slots=True)
class CompanyDataset:
    company_id: int
    ticker: str
    name: str
    sector: str | None
    market_sector: str | None
    market_industry: str | None
    market_snapshot: MarketSnapshot | None
    financials: tuple[FinancialPoint, ...]


ModelCallable = Callable[[CompanyDataset], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    name: str
    version: str
    compute: ModelCallable
