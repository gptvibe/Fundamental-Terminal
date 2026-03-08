from __future__ import annotations

from datetime import date
from typing import Any

from app.model_engine.types import CompanyDataset, FinancialPoint

ANNUAL_FORMS = {"10-K", "20-F", "40-F"}


def safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def average(*values: float | int | None) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def growth_rate(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (float(current) - float(previous)) / abs(float(previous))


def json_number(value: float | int | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return int(value) if float(value).is_integer() else float(value)


def statement_value(point: FinancialPoint, key: str) -> float | int | None:
    return point.data.get(key)


def book_equity(point: FinancialPoint) -> float | None:
    assets = statement_value(point, "total_assets")
    liabilities = statement_value(point, "total_liabilities")
    if assets is None or liabilities is None:
        return None
    return float(assets) - float(liabilities)


def latest_statement(dataset: CompanyDataset) -> FinancialPoint | None:
    return dataset.financials[0] if dataset.financials else None


def latest_annual_statement(dataset: CompanyDataset) -> FinancialPoint | None:
    for point in dataset.financials:
        if point.filing_type in ANNUAL_FORMS:
            return point
    return None


def previous_comparable_statement(
    dataset: CompanyDataset,
    current: FinancialPoint,
) -> FinancialPoint | None:
    current_is_annual = current.filing_type in ANNUAL_FORMS
    for point in dataset.financials:
        if point.statement_id == current.statement_id:
            continue
        if (point.filing_type in ANNUAL_FORMS) == current_is_annual and point.period_end < current.period_end:
            return point
    return None


def annual_series(dataset: CompanyDataset, *, limit: int | None = None) -> list[FinancialPoint]:
    annuals = [point for point in dataset.financials if point.filing_type in ANNUAL_FORMS]
    if limit is not None:
        return annuals[:limit]
    return annuals


def serialize_period(point: FinancialPoint) -> dict[str, Any]:
    return {
        "statement_id": point.statement_id,
        "filing_type": point.filing_type,
        "period_start": point.period_start.isoformat(),
        "period_end": point.period_end.isoformat(),
        "last_updated": point.last_updated.isoformat(),
        "source": point.source,
        "data": point.data,
    }


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None
