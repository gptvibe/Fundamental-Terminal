from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import httpx

from app.config import settings
from app.source_registry import SourceUsage

Number = int | float | None


@dataclass(frozen=True, slots=True)
class SectorChartPoint:
    label: str
    value: float | None


@dataclass(frozen=True, slots=True)
class SectorChartSeries:
    series_key: str
    label: str
    unit: str
    points: tuple[SectorChartPoint, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SectorChart:
    chart_id: str
    title: str
    subtitle: str | None
    unit: str
    series: tuple[SectorChartSeries, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SectorMetric:
    metric_id: str
    label: str
    unit: str
    value: float | None
    previous_value: float | None = None
    change: float | None = None
    change_percent: float | None = None
    as_of: str | None = None
    status: str = "ok"


@dataclass(frozen=True, slots=True)
class SectorDetailRow:
    label: str
    unit: str
    current_value: float | None
    prior_value: float | None = None
    change: float | None = None
    change_percent: float | None = None
    as_of: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class SectorDetailView:
    title: str
    rows: tuple[SectorDetailRow, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SectorRefreshPolicy:
    cadence_label: str
    ttl_seconds: int
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SectorPluginResult:
    plugin_id: str
    title: str
    description: str
    status: str
    summary_metrics: tuple[SectorMetric, ...] = field(default_factory=tuple)
    charts: tuple[SectorChart, ...] = field(default_factory=tuple)
    detail_view: SectorDetailView | None = None
    source_usages: tuple[SourceUsage, ...] = field(default_factory=tuple)
    confidence_flags: tuple[str, ...] = field(default_factory=tuple)
    as_of: str | None = None
    last_refreshed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


RelevanceMatcher = Callable[[str | None, str | None, str | None], list[str]]
PluginFetcher = Callable[[], SectorPluginResult]


@dataclass(frozen=True, slots=True)
class SectorPluginDefinition:
    plugin_id: str
    title: str
    description: str
    refresh_policy: SectorRefreshPolicy
    relevance_matcher: RelevanceMatcher
    fetch: PluginFetcher

    def relevance_reasons(
        self,
        *,
        sector: str | None,
        market_sector: str | None,
        market_industry: str | None,
    ) -> list[str]:
        return self.relevance_matcher(sector, market_sector, market_industry)


def keyword_relevance(
    *,
    keywords: tuple[str, ...],
    sector: str | None,
    market_sector: str | None,
    market_industry: str | None,
) -> list[str]:
    matches: list[str] = []
    for field_name, raw_value in (
        ("sector", sector or ""),
        ("market sector", market_sector or ""),
        ("industry", market_industry or ""),
    ):
        lowered = raw_value.lower()
        for keyword in keywords:
            if keyword in lowered:
                reason = f"{field_name}: {keyword}"
                if reason not in matches:
                    matches.append(reason)
    return matches


def build_http_client(*, timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": settings.sec_user_agent,
            "Accept": "application/json,text/csv,text/plain;q=0.8,*/*;q=0.7",
            "Accept-Encoding": "gzip, deflate",
        },
        follow_redirects=True,
        timeout=timeout_seconds,
    )


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def compute_change(current: float | None, previous: float | None) -> tuple[float | None, float | None]:
    if current is None or previous is None:
        return None, None
    delta = current - previous
    if previous == 0:
        return delta, None
    return delta, delta / previous


def build_metric(
    *,
    metric_id: str,
    label: str,
    unit: str,
    current: float | None,
    previous: float | None,
    as_of: str | None,
    status: str = "ok",
) -> SectorMetric:
    change, change_percent = compute_change(current, previous)
    return SectorMetric(
        metric_id=metric_id,
        label=label,
        unit=unit,
        value=current,
        previous_value=previous,
        change=change,
        change_percent=change_percent,
        as_of=as_of,
        status=status,
    )


def build_detail_row(
    *,
    label: str,
    unit: str,
    current: float | None,
    previous: float | None,
    as_of: str | None,
    note: str | None = None,
) -> SectorDetailRow:
    change, change_percent = compute_change(current, previous)
    return SectorDetailRow(
        label=label,
        unit=unit,
        current_value=current,
        prior_value=previous,
        change=change,
        change_percent=change_percent,
        as_of=as_of,
        note=note,
    )


def unavailable_plugin_result(
    *,
    plugin_id: str,
    title: str,
    description: str,
    source_usages: tuple[SourceUsage, ...],
    confidence_flags: tuple[str, ...],
) -> SectorPluginResult:
    return SectorPluginResult(
        plugin_id=plugin_id,
        title=title,
        description=description,
        status="unavailable",
        detail_view=SectorDetailView(title="Current snapshot unavailable", rows=()),
        source_usages=source_usages,
        confidence_flags=confidence_flags,
    )


def unescape_label(value: str) -> str:
    return html.unescape(value).strip()