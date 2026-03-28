from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
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

EIA_SOURCE_ID = "eia_electricity_retail_sales"
EIA_DESCRIPTION = "Official EIA retail electricity demand and pricing context for power-exposed companies."
EIA_KEYWORDS = (
    "utility",
    "utilities",
    "electric",
    "electricity",
    "power",
    "energy",
    "renewable",
    "generation",
)


def _relevance(sector: str | None, market_sector: str | None, market_industry: str | None) -> list[str]:
    return keyword_relevance(
        keywords=EIA_KEYWORDS,
        sector=sector,
        market_sector=market_sector,
        market_industry=market_industry,
    )


def _parse_rows(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    response = payload.get("response")
    if not isinstance(response, dict):
        return {}
    raw_rows = response.get("data")
    if not isinstance(raw_rows, list):
        return {}

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        sector_id = str(row.get("sectorid") or "").upper()
        if not sector_id:
            continue
        grouped.setdefault(sector_id, []).append(row)

    for rows in grouped.values():
        rows.sort(key=lambda item: str(item.get("period") or ""))
    return grouped


def _build_chart(rows: list[dict[str, object]], *, field: str, chart_id: str, title: str, unit: str) -> SectorChartSeries:
    return SectorChartSeries(
        series_key=chart_id,
        label=title,
        unit=unit,
        points=tuple(
            SectorChartPoint(label=str(row.get("period") or ""), value=parse_float(row.get(field)))
            for row in rows[-12:]
        ),
    )


def fetch_plugin() -> SectorPluginResult:
    source_usage = SourceUsage(source_id=EIA_SOURCE_ID, role="primary")
    if not settings.eia_api_key:
        return unavailable_plugin_result(
            plugin_id="eia_power",
            title="Energy & Power",
            description=EIA_DESCRIPTION,
            source_usages=(source_usage,),
            confidence_flags=("eia_api_key_missing",),
        )

    params = {
        "api_key": settings.eia_api_key,
        "frequency": "monthly",
        "data[0]": "price",
        "data[1]": "sales",
        "facets[sectorid][]": ["ALL", "IND"],
        "facets[stateid][]": ["US"],
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 48,
    }

    with build_http_client(timeout_seconds=settings.eia_timeout_seconds) as client:
        response = client.get(f"{settings.eia_api_base_url}/electricity/retail-sales/data/", params=params)
        response.raise_for_status()
        grouped = _parse_rows(response.json())

    all_rows = grouped.get("ALL") or []
    industrial_rows = grouped.get("IND") or []
    if not all_rows and not industrial_rows:
        return unavailable_plugin_result(
            plugin_id="eia_power",
            title="Energy & Power",
            description=EIA_DESCRIPTION,
            source_usages=(source_usage,),
            confidence_flags=("eia_no_rows",),
        )

    latest_all = all_rows[-1] if all_rows else {}
    previous_all = all_rows[-2] if len(all_rows) > 1 else {}
    latest_industrial = industrial_rows[-1] if industrial_rows else {}
    previous_industrial = industrial_rows[-2] if len(industrial_rows) > 1 else {}
    as_of = str(latest_all.get("period") or latest_industrial.get("period") or "") or None
    refreshed_at = datetime.now(timezone.utc)

    return SectorPluginResult(
        plugin_id="eia_power",
        title="Energy & Power",
        description=EIA_DESCRIPTION,
        status="ok",
        summary_metrics=(
            build_metric(
                metric_id="us_total_sales",
                label="U.S. retail sales",
                unit="million_kwh",
                current=parse_float(latest_all.get("sales")),
                previous=parse_float(previous_all.get("sales")),
                as_of=as_of,
            ),
            build_metric(
                metric_id="us_average_price",
                label="U.S. average retail price",
                unit="cents_per_kwh",
                current=parse_float(latest_all.get("price")),
                previous=parse_float(previous_all.get("price")),
                as_of=as_of,
            ),
            build_metric(
                metric_id="industrial_sales",
                label="Industrial retail sales",
                unit="million_kwh",
                current=parse_float(latest_industrial.get("sales")),
                previous=parse_float(previous_industrial.get("sales")),
                as_of=as_of,
            ),
            build_metric(
                metric_id="industrial_average_price",
                label="Industrial average retail price",
                unit="cents_per_kwh",
                current=parse_float(latest_industrial.get("price")),
                previous=parse_float(previous_industrial.get("price")),
                as_of=as_of,
            ),
        ),
        charts=(
            SectorChart(
                chart_id="retail_sales_trend",
                title="Electricity sales trend",
                subtitle="U.S. total versus industrial demand",
                unit="million_kwh",
                series=(
                    _build_chart(all_rows, field="sales", chart_id="all_sales", title="All sectors", unit="million_kwh"),
                    _build_chart(industrial_rows, field="sales", chart_id="industrial_sales", title="Industrial", unit="million_kwh"),
                ),
            ),
            SectorChart(
                chart_id="retail_price_trend",
                title="Retail price trend",
                subtitle="Average electricity price by sector",
                unit="cents_per_kwh",
                series=(
                    _build_chart(all_rows, field="price", chart_id="all_price", title="All sectors", unit="cents_per_kwh"),
                    _build_chart(industrial_rows, field="price", chart_id="industrial_price", title="Industrial", unit="cents_per_kwh"),
                ),
            ),
        ),
        detail_view=SectorDetailView(
            title="Latest EIA retail electricity snapshot",
            rows=(
                build_detail_row(
                    label="All sectors sales",
                    unit="million_kwh",
                    current=parse_float(latest_all.get("sales")),
                    previous=parse_float(previous_all.get("sales")),
                    as_of=as_of,
                ),
                build_detail_row(
                    label="All sectors price",
                    unit="cents_per_kwh",
                    current=parse_float(latest_all.get("price")),
                    previous=parse_float(previous_all.get("price")),
                    as_of=as_of,
                ),
                build_detail_row(
                    label="Industrial sales",
                    unit="million_kwh",
                    current=parse_float(latest_industrial.get("sales")),
                    previous=parse_float(previous_industrial.get("sales")),
                    as_of=as_of,
                ),
                build_detail_row(
                    label="Industrial price",
                    unit="cents_per_kwh",
                    current=parse_float(latest_industrial.get("price")),
                    previous=parse_float(previous_industrial.get("price")),
                    as_of=as_of,
                ),
            ),
        ),
        source_usages=(
            SourceUsage(
                source_id=EIA_SOURCE_ID,
                role="primary",
                as_of=as_of,
                last_refreshed_at=refreshed_at,
            ),
        ),
        as_of=as_of,
        last_refreshed_at=refreshed_at,
    )


PLUGIN = SectorPluginDefinition(
    plugin_id="eia_power",
    title="Energy & Power",
    description=EIA_DESCRIPTION,
    refresh_policy=SectorRefreshPolicy(
        cadence_label="Monthly",
        ttl_seconds=24 * 60 * 60,
        notes=("EIA-826 retail sales release", "Daily backend cache refresh is sufficient for the monthly cadence"),
    ),
    relevance_matcher=_relevance,
    fetch=fetch_plugin,
)