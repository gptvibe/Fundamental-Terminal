from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date as DateType, datetime
from typing import Any, Hashable, Protocol, TypeVar

ANNUAL_FORMS = {"10-K", "20-F", "40-F"}


class SnapshotHistoryStatement(Protocol):
    filing_type: str
    period_end: Any


StatementT = TypeVar("StatementT", bound=SnapshotHistoryStatement)


@dataclass(slots=True, frozen=True)
class SnapshotHistoryWindow:
    statement: StatementT
    previous_statement: StatementT | None


def build_snapshot_history_windows(
    statements: Sequence[StatementT],
    *,
    years: int,
    include_statement: Callable[[StatementT], bool],
    prefer_annual: bool = True,
    normalized_period_key: Callable[[StatementT], Hashable] | None = None,
) -> list[SnapshotHistoryWindow]:
    if years < 1:
        return []

    eligible = [statement for statement in statements if include_statement(statement)]
    if not eligible:
        return []

    annual_eligible = [statement for statement in eligible if statement.filing_type in ANNUAL_FORMS]
    source = annual_eligible if prefer_annual and annual_eligible else eligible
    if source is annual_eligible:
        source = _dedupe_by_period_key(source, normalized_period_key or _default_period_key)

    limited = source[:years]
    return [
        SnapshotHistoryWindow(
            statement=statement,
            previous_statement=source[index + 1] if index + 1 < len(source) else None,
        )
        for index, statement in enumerate(limited)
    ]


def statement_fiscal_year(statement: SnapshotHistoryStatement) -> int | None:
    period_end = getattr(statement, "period_end", None)
    if isinstance(period_end, datetime):
        return period_end.year
    if isinstance(period_end, DateType):
        return period_end.year
    if isinstance(period_end, str):
        text = period_end.strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
    return None


def _default_period_key(statement: SnapshotHistoryStatement) -> Hashable:
    fiscal_year = statement_fiscal_year(statement)
    if fiscal_year is not None:
        return fiscal_year
    return f"{getattr(statement, 'period_end', '')}|{getattr(statement, 'filing_type', '')}"


def _dedupe_by_period_key(
    statements: Sequence[StatementT],
    period_key: Callable[[StatementT], Hashable],
) -> list[StatementT]:
    output: list[StatementT] = []
    seen_keys: set[Hashable] = set()
    for statement in statements:
        key = period_key(statement)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        output.append(statement)
    return output