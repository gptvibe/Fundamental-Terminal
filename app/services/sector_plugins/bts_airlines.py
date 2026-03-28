from __future__ import annotations

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

T100_SOURCE_ID = "bts_t100_segment_summary"
FORM41_SOURCE_ID = "bts_form41_financial_review"
T100_URL = "https://data.transportation.gov/resource/bu82-4pwz.json"
FORM41_URL = "https://data.transportation.gov/resource/evch-7vws.json"
BTS_DESCRIPTION = "Official BTS traffic and Form 41 profitability context for passenger airlines and air cargo operators."
BTS_KEYWORDS = (
    "airline",
    "airlines",
    "air cargo",
    "cargo",
    "air freight",
    "parcel",
    "logistics",
    "delivery",
    "transportation",
)


def _relevance(sector: str | None, market_sector: str | None, market_industry: str | None) -> list[str]:
    return keyword_relevance(
        keywords=BTS_KEYWORDS,
        sector=sector,
        market_sector=market_sector,
        market_industry=market_industry,
    )


def _fetch_t100_rows() -> list[dict[str, object]]:
    params = {"$order": "year asc", "$limit": 50}
    with build_http_client(timeout_seconds=30.0) as client:
        response = client.get(T100_URL, params=params)
        response.raise_for_status()
        rows = response.json()
    return [row for row in rows if isinstance(row, dict)]


def _fetch_form41_rows() -> list[dict[str, object]]:
    params = {
        "$select": "year,quarter,group_name,item_name,val",
        "$where": "period_type='Q' AND group_name in('System All Majors','Domestic Cargo Majors') AND item_name in('Operating Revenues','Operating Profit (Loss) to Operating Revenue','Passenger Load Factor (Sch. Svc.)','Ton Load Factor (All Svc.)')",
        "$order": "year asc, quarter asc",
        "$limit": 200,
    }
    with build_http_client(timeout_seconds=30.0) as client:
        response = client.get(FORM41_URL, params=params)
        response.raise_for_status()
        rows = response.json()
    return [row for row in rows if isinstance(row, dict)]


def _find_latest_metric(rows: list[dict[str, object]], *, group_name: str, item_name: str) -> tuple[dict[str, object], dict[str, object]]:
    filtered = [row for row in rows if row.get("group_name") == group_name and row.get("item_name") == item_name]
    if not filtered:
        return {}, {}
    return filtered[-1], filtered[-2] if len(filtered) > 1 else {}


def fetch_plugin() -> SectorPluginResult:
    t100_rows = _fetch_t100_rows()
    form41_rows = _fetch_form41_rows()
    if not t100_rows and not form41_rows:
        return unavailable_plugin_result(
            plugin_id="bts_airlines",
            title="Airlines & Air Cargo",
            description=BTS_DESCRIPTION,
            source_usages=(
                SourceUsage(source_id=T100_SOURCE_ID, role="primary"),
                SourceUsage(source_id=FORM41_SOURCE_ID, role="supplemental"),
            ),
            confidence_flags=("bts_no_rows",),
        )

    latest_t100 = t100_rows[-1] if t100_rows else {}
    previous_t100 = t100_rows[-2] if len(t100_rows) > 1 else {}
    as_of_t100 = str(latest_t100.get("year") or "") or None
    system_margin, previous_system_margin = _find_latest_metric(
        form41_rows,
        group_name="System All Majors",
        item_name="Operating Profit (Loss) to Operating Revenue",
    )
    cargo_margin, previous_cargo_margin = _find_latest_metric(
        form41_rows,
        group_name="Domestic Cargo Majors",
        item_name="Operating Profit (Loss) to Operating Revenue",
    )
    system_revenue, previous_system_revenue = _find_latest_metric(
        form41_rows,
        group_name="System All Majors",
        item_name="Operating Revenues",
    )
    cargo_revenue, previous_cargo_revenue = _find_latest_metric(
        form41_rows,
        group_name="Domestic Cargo Majors",
        item_name="Operating Revenues",
    )
    latest_quarter = f"{system_margin.get('year') or cargo_margin.get('year') or ''}-Q{system_margin.get('quarter') or cargo_margin.get('quarter') or ''}".strip("-Q")
    if latest_quarter == "":
        latest_quarter = None
    refreshed_at = datetime.now(timezone.utc)

    def quarter_series(group_name: str, item_name: str, series_key: str, label: str) -> SectorChartSeries:
        filtered = [row for row in form41_rows if row.get("group_name") == group_name and row.get("item_name") == item_name]
        return SectorChartSeries(
            series_key=series_key,
            label=label,
            unit="percent",
            points=tuple(
                SectorChartPoint(
                    label=f"{row.get('year')}-Q{row.get('quarter')}",
                    value=parse_float(row.get("val")),
                )
                for row in filtered[-8:]
            ),
        )

    return SectorPluginResult(
        plugin_id="bts_airlines",
        title="Airlines & Air Cargo",
        description=BTS_DESCRIPTION,
        status="ok",
        summary_metrics=(
            build_metric(
                metric_id="t100_passengers",
                label="T-100 passengers",
                unit="passengers",
                current=parse_float(latest_t100.get("passengers")),
                previous=parse_float(previous_t100.get("passengers")),
                as_of=as_of_t100,
            ),
            build_metric(
                metric_id="t100_freight",
                label="T-100 freight",
                unit="lbs",
                current=parse_float(latest_t100.get("freight_lbs")),
                previous=parse_float(previous_t100.get("freight_lbs")),
                as_of=as_of_t100,
            ),
            build_metric(
                metric_id="t100_load_factor",
                label="T-100 load factor",
                unit="percent",
                current=parse_float(latest_t100.get("load_factor")),
                previous=parse_float(previous_t100.get("load_factor")),
                as_of=as_of_t100,
            ),
            build_metric(
                metric_id="system_operating_margin",
                label="System operating margin",
                unit="percent",
                current=parse_float(system_margin.get("val")),
                previous=parse_float(previous_system_margin.get("val")),
                as_of=latest_quarter,
            ),
        ),
        charts=(
            SectorChart(
                chart_id="passenger_trend",
                title="Passenger demand trend",
                subtitle="Annual BTS T-100 passenger totals",
                unit="passengers",
                series=(
                    SectorChartSeries(
                        series_key="passengers",
                        label="Passengers",
                        unit="passengers",
                        points=tuple(
                            SectorChartPoint(label=str(row.get("year") or ""), value=parse_float(row.get("passengers")))
                            for row in t100_rows[-6:]
                        ),
                    ),
                ),
            ),
            SectorChart(
                chart_id="freight_trend",
                title="Air freight trend",
                subtitle="Annual BTS T-100 freight totals",
                unit="lbs",
                series=(
                    SectorChartSeries(
                        series_key="freight",
                        label="Freight",
                        unit="lbs",
                        points=tuple(
                            SectorChartPoint(label=str(row.get("year") or ""), value=parse_float(row.get("freight_lbs")))
                            for row in t100_rows[-6:]
                        ),
                    ),
                ),
            ),
            SectorChart(
                chart_id="operating_margin_trend",
                title="Form 41 operating margin",
                subtitle="Passenger majors versus domestic cargo majors",
                unit="percent",
                series=(
                    quarter_series(
                        "System All Majors",
                        "Operating Profit (Loss) to Operating Revenue",
                        "system_margin",
                        "System all majors",
                    ),
                    quarter_series(
                        "Domestic Cargo Majors",
                        "Operating Profit (Loss) to Operating Revenue",
                        "cargo_margin",
                        "Domestic cargo majors",
                    ),
                ),
            ),
        ),
        detail_view=SectorDetailView(
            title="Latest BTS and Form 41 snapshot",
            rows=(
                build_detail_row(
                    label="System all majors operating revenue",
                    unit="usd",
                    current=parse_float(system_revenue.get("val")),
                    previous=parse_float(previous_system_revenue.get("val")),
                    as_of=latest_quarter,
                ),
                build_detail_row(
                    label="System all majors operating margin",
                    unit="percent",
                    current=parse_float(system_margin.get("val")),
                    previous=parse_float(previous_system_margin.get("val")),
                    as_of=latest_quarter,
                ),
                build_detail_row(
                    label="Domestic cargo majors operating revenue",
                    unit="usd",
                    current=parse_float(cargo_revenue.get("val")),
                    previous=parse_float(previous_cargo_revenue.get("val")),
                    as_of=latest_quarter,
                ),
                build_detail_row(
                    label="Domestic cargo majors operating margin",
                    unit="percent",
                    current=parse_float(cargo_margin.get("val")),
                    previous=parse_float(previous_cargo_margin.get("val")),
                    as_of=latest_quarter,
                ),
            ),
        ),
        source_usages=(
            SourceUsage(
                source_id=T100_SOURCE_ID,
                role="primary",
                as_of=as_of_t100,
                last_refreshed_at=refreshed_at,
            ),
            SourceUsage(
                source_id=FORM41_SOURCE_ID,
                role="supplemental",
                as_of=latest_quarter,
                last_refreshed_at=refreshed_at,
            ),
        ),
        as_of=latest_quarter or as_of_t100,
        last_refreshed_at=refreshed_at,
    )


PLUGIN = SectorPluginDefinition(
    plugin_id="bts_airlines",
    title="Airlines & Air Cargo",
    description=BTS_DESCRIPTION,
    refresh_policy=SectorRefreshPolicy(
        cadence_label="Quarterly Form 41 + annual T-100",
        ttl_seconds=24 * 60 * 60,
        notes=("T-100 annual summary for traffic", "Form 41 quarterly financial review for profitability and load factors"),
    ),
    relevance_matcher=_relevance,
    fetch=fetch_plugin,
)