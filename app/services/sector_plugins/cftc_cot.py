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

CFTC_SOURCE_ID = "cftc_cot"
CFTC_COT_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
CFTC_DESCRIPTION = "Official CFTC Commitments of Traders positioning context for commodity-linked companies."

CFTC_KEYWORDS = (
    "oil",
    "gas",
    "energy",
    "petroleum",
    "refining",
    "chemicals",
    "metals",
    "mining",
    "steel",
    "copper",
    "materials",
)

TARGET_SUBGROUPS = {
    "PETROLEUM AND PRODUCTS",
    "NATURAL GAS AND PRODUCTS",
    "ELECTRICITY AND SOURCES",
    "BASE METALS",
    "PRECIOUS METALS",
    "CHEMICALS",
    "WOOD PRODUCTS",
}


def _relevance(sector: str | None, market_sector: str | None, market_industry: str | None) -> list[str]:
    return keyword_relevance(
        keywords=CFTC_KEYWORDS,
        sector=sector,
        market_sector=market_sector,
        market_industry=market_industry,
    )


def _latest_report_date(client) -> str | None:
    response = client.get(CFTC_COT_URL, params={"$select": "max(report_date_as_yyyy_mm_dd) as latest", "$limit": 1})
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        return None
    latest = rows[0]
    if not isinstance(latest, dict):
        return None
    value = str(latest.get("latest") or "").strip()
    return value or None


def _load_rows(client, *, report_date: str) -> list[dict[str, object]]:
    response = client.get(
        CFTC_COT_URL,
        params={
            "$select": ",".join(
                (
                    "report_date_as_yyyy_mm_dd",
                    "commodity_name",
                    "commodity_subgroup_name",
                    "open_interest_all",
                    "noncomm_positions_long_all",
                    "noncomm_positions_short_all",
                )
            ),
            "$where": f"report_date_as_yyyy_mm_dd='{report_date}'",
            "$limit": 5000,
        },
    )
    response.raise_for_status()
    rows = response.json()
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _aggregate(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    totals = {
        "energy": {"open_interest": 0.0, "noncomm_long": 0.0, "noncomm_short": 0.0},
        "materials": {"open_interest": 0.0, "noncomm_long": 0.0, "noncomm_short": 0.0},
    }

    energy_subgroups = {
        "PETROLEUM AND PRODUCTS",
        "NATURAL GAS AND PRODUCTS",
        "ELECTRICITY AND SOURCES",
    }
    materials_subgroups = {
        "BASE METALS",
        "PRECIOUS METALS",
        "CHEMICALS",
        "WOOD PRODUCTS",
    }

    for row in rows:
        subgroup = str(row.get("commodity_subgroup_name") or "").strip().upper()
        if subgroup not in TARGET_SUBGROUPS:
            continue

        key = "energy" if subgroup in energy_subgroups else "materials"
        totals[key]["open_interest"] += parse_float(row.get("open_interest_all")) or 0.0
        totals[key]["noncomm_long"] += parse_float(row.get("noncomm_positions_long_all")) or 0.0
        totals[key]["noncomm_short"] += parse_float(row.get("noncomm_positions_short_all")) or 0.0

    return totals


def fetch_plugin() -> SectorPluginResult:
    with build_http_client(timeout_seconds=settings.sec_timeout_seconds) as client:
        latest_date = _latest_report_date(client)
        if latest_date is None:
            return unavailable_plugin_result(
                plugin_id="cftc_cot",
                title="CFTC Commitments of Traders",
                description=CFTC_DESCRIPTION,
                source_usages=(SourceUsage(source_id=CFTC_SOURCE_ID, role="primary"),),
                confidence_flags=("cftc_cot_latest_date_missing",),
            )

        latest_rows = _load_rows(client, report_date=latest_date)
        if not latest_rows:
            return unavailable_plugin_result(
                plugin_id="cftc_cot",
                title="CFTC Commitments of Traders",
                description=CFTC_DESCRIPTION,
                source_usages=(SourceUsage(source_id=CFTC_SOURCE_ID, role="primary"),),
                confidence_flags=("cftc_cot_no_rows",),
            )

        latest_totals = _aggregate(latest_rows)

    refreshed_at = datetime.now(timezone.utc)

    energy_oi = latest_totals["energy"]["open_interest"]
    energy_long = latest_totals["energy"]["noncomm_long"]
    energy_short = latest_totals["energy"]["noncomm_short"]
    energy_net = energy_long - energy_short

    materials_oi = latest_totals["materials"]["open_interest"]
    materials_long = latest_totals["materials"]["noncomm_long"]
    materials_short = latest_totals["materials"]["noncomm_short"]
    materials_net = materials_long - materials_short

    def ratio(net: float, oi: float) -> float | None:
        if oi == 0:
            return None
        return net / oi

    return SectorPluginResult(
        plugin_id="cftc_cot",
        title="CFTC Commitments of Traders",
        description=CFTC_DESCRIPTION,
        status="ok",
        summary_metrics=(
            build_metric(
                metric_id="cftc_energy_open_interest",
                label="Energy open interest",
                unit="contracts",
                current=energy_oi,
                previous=None,
                as_of=latest_date,
            ),
            build_metric(
                metric_id="cftc_energy_noncommercial_net",
                label="Energy non-commercial net",
                unit="contracts",
                current=energy_net,
                previous=None,
                as_of=latest_date,
            ),
            build_metric(
                metric_id="cftc_materials_open_interest",
                label="Materials open interest",
                unit="contracts",
                current=materials_oi,
                previous=None,
                as_of=latest_date,
            ),
            build_metric(
                metric_id="cftc_materials_noncommercial_net",
                label="Materials non-commercial net",
                unit="contracts",
                current=materials_net,
                previous=None,
                as_of=latest_date,
            ),
        ),
        charts=(
            SectorChart(
                chart_id="cftc_positioning_snapshot",
                title="CFTC positioning snapshot",
                subtitle="Non-commercial net positioning as share of open interest",
                unit="ratio",
                series=(
                    SectorChartSeries(
                        series_key="energy_net_ratio",
                        label="Energy",
                        unit="ratio",
                        points=(
                            SectorChartPoint(label=latest_date, value=ratio(energy_net, energy_oi)),
                        ),
                    ),
                    SectorChartSeries(
                        series_key="materials_net_ratio",
                        label="Materials",
                        unit="ratio",
                        points=(
                            SectorChartPoint(label=latest_date, value=ratio(materials_net, materials_oi)),
                        ),
                    ),
                ),
            ),
        ),
        detail_view=SectorDetailView(
            title="Latest CFTC COT grouped positioning",
            rows=(
                build_detail_row(
                    label="Energy non-commercial long",
                    unit="contracts",
                    current=energy_long,
                    previous=None,
                    as_of=latest_date,
                ),
                build_detail_row(
                    label="Energy non-commercial short",
                    unit="contracts",
                    current=energy_short,
                    previous=None,
                    as_of=latest_date,
                ),
                build_detail_row(
                    label="Materials non-commercial long",
                    unit="contracts",
                    current=materials_long,
                    previous=None,
                    as_of=latest_date,
                ),
                build_detail_row(
                    label="Materials non-commercial short",
                    unit="contracts",
                    current=materials_short,
                    previous=None,
                    as_of=latest_date,
                ),
            ),
        ),
        source_usages=(
            SourceUsage(
                source_id=CFTC_SOURCE_ID,
                role="primary",
                as_of=latest_date,
                last_refreshed_at=refreshed_at,
            ),
        ),
        as_of=latest_date,
        last_refreshed_at=refreshed_at,
    )


PLUGIN = SectorPluginDefinition(
    plugin_id="cftc_cot",
    title="CFTC Commitments of Traders",
    description=CFTC_DESCRIPTION,
    refresh_policy=SectorRefreshPolicy(
        cadence_label="Weekly",
        ttl_seconds=24 * 60 * 60,
        notes=("CFTC Commitments of Traders release",),
    ),
    relevance_matcher=_relevance,
    fetch=fetch_plugin,
)
