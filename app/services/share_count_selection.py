from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ShareSelection:
    value: float | None
    source: str | None
    is_proxy: bool


def point_in_time_shares_outstanding(data: Mapping[str, Any]) -> float | None:
    return _to_float(data.get("shares_outstanding"))


def weighted_average_basic_shares(data: Mapping[str, Any]) -> float | None:
    return _to_float(data.get("weighted_average_basic_shares"))


def weighted_average_diluted_shares(data: Mapping[str, Any]) -> float | None:
    return _to_float(data.get("weighted_average_diluted_shares"))


def shares_for_market_cap(data: Mapping[str, Any]) -> ShareSelection:
    # Market cap should use point-in-time shares whenever possible.
    point_in_time = point_in_time_shares_outstanding(data)
    if point_in_time is not None:
        return ShareSelection(value=point_in_time, source="shares_outstanding", is_proxy=False)

    diluted = weighted_average_diluted_shares(data)
    if diluted is not None:
        return ShareSelection(value=diluted, source="weighted_average_diluted_shares", is_proxy=True)

    return ShareSelection(value=None, source=None, is_proxy=True)


def shares_for_per_share_metric(data: Mapping[str, Any]) -> ShareSelection:
    # Per-share flow metrics prefer weighted-average shares, then point-in-time as a proxy fallback.
    diluted = weighted_average_diluted_shares(data)
    if diluted is not None:
        return ShareSelection(value=diluted, source="weighted_average_diluted_shares", is_proxy=False)

    basic = weighted_average_basic_shares(data)
    if basic is not None:
        return ShareSelection(value=basic, source="weighted_average_basic_shares", is_proxy=False)

    point_in_time = point_in_time_shares_outstanding(data)
    if point_in_time is not None:
        return ShareSelection(value=point_in_time, source="shares_outstanding", is_proxy=True)

    return ShareSelection(value=None, source=None, is_proxy=True)


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value_as_float = float(value)
        if value_as_float == 0:
            return None
        return value_as_float
    return None