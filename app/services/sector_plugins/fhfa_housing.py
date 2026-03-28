from __future__ import annotations

import csv
from io import StringIO
from datetime import datetime, timezone

from app.source_registry import SourceUsage
from app.services.sector_plugins.base import (
    SectorChart,
    SectorChartPoint,
    SectorChartSeries,
    SectorDetailView,
    SectorPluginDefinition,
    SectorPluginResult,
    SectorRefreshPolicy,
    build_detail_row,
    build_http_client,
    build_metric,
    keyword_relevance,
    parse_float,
    unavailable_plugin_result,
)

FHFA_SOURCE_ID = "fhfa_house_price_index"
FHFA_URL = "https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv"
FHFA_DESCRIPTION = "Official FHFA house-price trends for housing- and mortgage-sensitive companies."
FHFA_KEYWORDS = (
    "real estate",
    "reit",
    "home",
    "housing",
    "mortgage",
    "building products",
    "homebuilder",
    "residential",
    "property",
)


def _relevance(sector: str | None, market_sector: str | None, market_industry: str | None) -> list[str]:
    return keyword_relevance(
        keywords=FHFA_KEYWORDS,
        sector=sector,
        market_sector=market_sector,
        market_industry=market_industry,
    )


def _period_key(row: dict[str, str]) -> str:
    return f"{row.get('yr', '')}-{int(row.get('period', '1')):02d}"


def _index_value(row: dict[str, str]) -> float | None:
    return parse_float(row.get("index_sa")) or parse_float(row.get("index_nsa"))


def fetch_plugin() -> SectorPluginResult:
    with build_http_client(timeout_seconds=30.0) as client:
        response = client.get(FHFA_URL)
        response.raise_for_status()
        rows = list(csv.DictReader(StringIO(response.text)))

    national_rows = [row for row in rows if row.get("place_id") == "USA"]
    division_rows = [
        row
        for row in rows
        if row.get("level") == "USA or Census Division" and row.get("place_id") not in {None, "", "USA"}
    ]
    national_rows.sort(key=_period_key)
    if not national_rows:
        return unavailable_plugin_result(
            plugin_id="fhfa_housing",
            title="Housing Exposure",
            description=FHFA_DESCRIPTION,
            source_usages=(SourceUsage(source_id=FHFA_SOURCE_ID, role="primary"),),
            confidence_flags=("fhfa_no_rows",),
        )

    latest = national_rows[-1]
    previous = national_rows[-2] if len(national_rows) > 1 else {}
    previous_year = next(
        (
            row
            for row in reversed(national_rows[:-1])
            if row.get("period") == latest.get("period") and row.get("yr") == str(int(latest.get("yr", "0")) - 1)
        ),
        {},
    )
    as_of = _period_key(latest)
    latest_value = _index_value(latest)
    previous_value = _index_value(previous)
    previous_year_value = _index_value(previous_year)
    refreshed_at = datetime.now(timezone.utc)

    latest_divisions = [row for row in division_rows if _period_key(row) == as_of]
    prior_division_map = {
        row.get("place_id") or "": _index_value(row)
        for row in division_rows
        if row.get("period") == latest.get("period") and row.get("yr") == str(int(latest.get("yr", "0")) - 1)
    }
    division_changes: list[tuple[str, float | None, float | None]] = []
    for row in latest_divisions:
        current_value = _index_value(row)
        prior_value = prior_division_map.get(row.get("place_id") or "")
        division_changes.append((row.get("place_name") or "", current_value, prior_value))
    division_changes = [item for item in division_changes if item[1] is not None and item[2] is not None]
    division_changes.sort(key=lambda item: (item[1] / item[2]) if item[2] else float("-inf"), reverse=True)
    strongest = division_changes[0] if division_changes else ("", None, None)
    weakest = division_changes[-1] if division_changes else ("", None, None)

    return SectorPluginResult(
        plugin_id="fhfa_housing",
        title="Housing Exposure",
        description=FHFA_DESCRIPTION,
        status="ok",
        summary_metrics=(
            build_metric(
                metric_id="national_hpi",
                label="National HPI",
                unit="index",
                current=latest_value,
                previous=previous_value,
                as_of=as_of,
            ),
            build_metric(
                metric_id="national_hpi_yoy",
                label="National HPI YoY",
                unit="ratio",
                current=(latest_value / previous_year_value - 1.0) if latest_value is not None and previous_year_value else None,
                previous=None,
                as_of=as_of,
            ),
        ),
        charts=(
            SectorChart(
                chart_id="national_hpi_trend",
                title="National house price index",
                subtitle="Seasonally adjusted FHFA monthly index",
                unit="index",
                series=(
                    SectorChartSeries(
                        series_key="national_hpi",
                        label="United States",
                        unit="index",
                        points=tuple(
                            SectorChartPoint(label=_period_key(row), value=_index_value(row))
                            for row in national_rows[-24:]
                        ),
                    ),
                ),
            ),
        ),
        detail_view=SectorDetailView(
            title="Latest FHFA housing snapshot",
            rows=(
                build_detail_row(
                    label="United States",
                    unit="index",
                    current=latest_value,
                    previous=previous_year_value,
                    as_of=as_of,
                    note="Prior value is the same month one year earlier",
                ),
                build_detail_row(
                    label=strongest[0] or "Strongest census division",
                    unit="index",
                    current=strongest[1],
                    previous=strongest[2],
                    as_of=as_of,
                    note="Highest year-over-year division move",
                ),
                build_detail_row(
                    label=weakest[0] or "Weakest census division",
                    unit="index",
                    current=weakest[1],
                    previous=weakest[2],
                    as_of=as_of,
                    note="Lowest year-over-year division move",
                ),
            ),
        ),
        source_usages=(
            SourceUsage(
                source_id=FHFA_SOURCE_ID,
                role="primary",
                as_of=as_of,
                last_refreshed_at=refreshed_at,
            ),
        ),
        as_of=as_of,
        last_refreshed_at=refreshed_at,
    )


PLUGIN = SectorPluginDefinition(
    plugin_id="fhfa_housing",
    title="Housing Exposure",
    description=FHFA_DESCRIPTION,
    refresh_policy=SectorRefreshPolicy(
        cadence_label="Monthly",
        ttl_seconds=24 * 60 * 60,
        notes=("FHFA monthly purchase-only HPI",),
    ),
    relevance_matcher=_relevance,
    fetch=fetch_plugin,
)